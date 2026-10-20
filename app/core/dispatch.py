"""
Outbound external notifications: email and webhook.

Both channels are off by default (see app/core/config.py) so a fresh
checkout never attempts a network call it wasn't explicitly configured
for. Both fail closed: any error (bad SMTP creds, unreachable webhook
URL, timeout) is caught and logged, never raised -- a broken external
integration must not break the in-app request that triggered it.

This module knows nothing about *why* an email or webhook is being
sent; app/core/listeners.py decides that by subscribing handlers to
domain events and calling these two functions. To swap SMTP for an
API-based email provider, or a single webhook URL for a per-club one,
this is the only file that changes.

send_email()/send_webhook() themselves are still synchronous, blocking
functions -- run_in_background() below is what keeps their network
latency off the request path. listeners.py submits work through it
rather than calling send_email()/send_webhook() directly.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import smtplib
import threading
import time
import urllib.error
import urllib.request
from email.mime.text import MIMEText
from typing import Callable, Any

from flask import current_app

logger = logging.getLogger("opencampus.dispatch")

# A small, bounded pool: this app's dispatch volume is a handful of
# emails/webhooks per user action, not a bulk job queue. If that
# changes, swap this for a real task queue (Celery/RQ) behind the same
# run_in_background() call signature -- nothing calling it needs to change.
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="opencampus-dispatch")

_pending_lock = threading.Lock()
_pending_futures: list[concurrent.futures.Future] = []


def _with_backoff(func: Callable, *args: Any, max_attempts: int = 3,
                  base_delay: float = 1.0, **kwargs: Any) -> Any:
    """Call func(*args, **kwargs) with exponential backoff on failure.

    Attempts: 1 → 2 → 3 with delays 1 s, 2 s (i.e. base_delay × 2^attempt).
    Raises the last exception if all attempts fail.
    This keeps external-network calls from hanging a worker indefinitely:
    each attempt has its own timeout (set inside the called function).
    """
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "Dispatch attempt %d/%d for %r failed (%s); retrying in %.1fs",
                    attempt + 1, max_attempts,
                    getattr(func, "__name__", func), exc, delay,
                )
                time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def run_in_background(app, func, *args, **kwargs) -> None:
    """Fire-and-forget: submit func(*args, **kwargs) to a worker thread
    and return immediately, so the request that triggered it never
    waits on network I/O.

    `app` must be the real Flask application object (e.g.
    current_app._get_current_object()), not the current_app proxy --
    proxies are only valid on the thread/context that pushed them. The
    task pushes its own fresh app context on the worker thread, which
    also means func gets its own SQLite connection (see app/core/db.py)
    rather than sharing the calling request's connection across threads,
    which sqlite3 does not allow safely.

    Any exception func raises is caught and logged here, not
    re-raised: nothing ever calls .result() on the returned Future (by
    design -- that would block), so an uncaught exception would
    otherwise vanish silently instead of merely being logged."""
    def _task():
        with app.app_context():
            try:
                func(*args, **kwargs)
            except Exception:  # noqa: BLE001 -- last line of defense in a background thread
                logger.exception("Background dispatch task %r failed", getattr(func, "__name__", func))

    future = _executor.submit(_task)
    with _pending_lock:
        _pending_futures.append(future)


def wait_for_pending(timeout: float = 5.0) -> None:
    """Test-only helper: block until every background task submitted so
    far has finished (or timeout elapses). Application code must never
    call this -- the entire point of run_in_background() is that
    request handlers don't wait. Used by tests/test_dispatch.py to
    deterministically assert on a webhook/email after triggering it,
    instead of sleeping and hoping the background thread won."""
    with _pending_lock:
        futures = list(_pending_futures)
        _pending_futures.clear()
    concurrent.futures.wait(futures, timeout=timeout)


def send_email(to_addr: str | None, subject: str, body: str) -> bool:
    """Best-effort email send with up to 3 attempts and exponential backoff.
    Routes to Celery if USE_CELERY is configured, otherwise runs in local thread pool."""
    if not to_addr:
        return False
    cfg = current_app.config
    if not cfg.get("ENABLE_EMAIL_NOTIFICATIONS") or not cfg.get("SMTP_HOST"):
        current_app.logger.info("[email dispatch disabled] would send to %s: %s", to_addr, subject)
        return False

    # Check for Celery delegation
    if cfg.get("USE_CELERY", False):
        try:
            from app.core.celery_app import send_email_task, celery
            if celery is not None:
                send_email_task.delay(
                    to_addr=to_addr,
                    subject=subject,
                    body=body,
                    smtp_host=cfg["SMTP_HOST"],
                    smtp_port=cfg.get("SMTP_PORT", 587),
                    smtp_user=cfg.get("SMTP_USERNAME", ""),
                    smtp_pass=cfg.get("SMTP_PASSWORD", ""),
                    from_addr=cfg.get("EMAIL_FROM", "noreply@opencampus.local"),
                )
                return True
        except Exception as exc:  # noqa: BLE001
            current_app.logger.warning("Celery enqueue failed (%s); using thread pool fallback", exc)

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = cfg.get("EMAIL_FROM", "noreply@opencampus.local")
    msg["To"] = to_addr

    def _attempt():
        with smtplib.SMTP(cfg["SMTP_HOST"], cfg.get("SMTP_PORT", 587), timeout=10) as server:
            server.starttls()
            if cfg.get("SMTP_USERNAME"):
                server.login(cfg["SMTP_USERNAME"], cfg.get("SMTP_PASSWORD", ""))
            server.send_message(msg)

    try:
        _with_backoff(_attempt)
        return True
    except Exception as exc:  # noqa: BLE001
        current_app.logger.warning("Email dispatch to %s failed after retries: %s", to_addr, exc)
        return False


def send_webhook(event_name: str, payload: dict) -> bool:
    """Best-effort webhook POST with exponential backoff.
    Routes to Celery if USE_CELERY is configured, otherwise runs in local thread pool."""
    cfg = current_app.config
    url = cfg.get("WEBHOOK_URL")
    if not cfg.get("ENABLE_WEBHOOK_NOTIFICATIONS") or not url:
        return False

    # Check for Celery delegation
    if cfg.get("USE_CELERY", False):
        try:
            from app.core.celery_app import send_webhook_task, celery
            if celery is not None:
                send_webhook_task.delay(url, event_name, payload)
                return True
        except Exception as exc:  # noqa: BLE001
            current_app.logger.warning("Celery enqueue failed (%s); using thread pool fallback", exc)

    body = json.dumps({"event": event_name, "data": payload}, default=str).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")

    def _attempt():
        urllib.request.urlopen(req, timeout=10)

    try:
        _with_backoff(_attempt)
        return True
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        current_app.logger.warning("Webhook dispatch for %s failed after retries: %s", event_name, exc)
        return False