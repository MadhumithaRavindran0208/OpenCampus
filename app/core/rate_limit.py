"""
Rate limiting.

Uses Flask-Limiter with an in-memory backend by default (good enough for a
single-process deployment) and a Redis backend when REDIS_URL is configured
(required for multi-worker setups).

Usage in routes:
    from app.core.rate_limit import limiter

    @bp.route("/login", methods=["POST"])
    @limiter.limit("10 per minute")  # per-IP
    def login(): ...

Global limits applied in create_app() via init_app().
"""
from __future__ import annotations

import os
import logging

logger = logging.getLogger("opencampus.rate_limit")

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
    _LIMITER_AVAILABLE = True
except ImportError:
    _LIMITER_AVAILABLE = False
    logger.warning(
        "flask-limiter is not installed -- rate limiting is DISABLED. "
        "Install it: pip install flask-limiter"
    )


def _get_storage_uri() -> str:
    """Return the storage URI for Flask-Limiter.

    - If REDIS_URL is set we use Redis, which works across multi-worker
      deployments (Gunicorn / waitress with multiple processes).
    - Otherwise fall back to in-memory storage.  Works fine for a
      single-process local run; not safe for multi-process deploys because
      each worker has its own counter.
    """
    redis_url = os.environ.get("REDIS_URL", "")
    if redis_url:
        logger.info("Rate-limiter backend: Redis at %s", redis_url.split("@")[-1])
        return redis_url
    logger.info("Rate-limiter backend: in-memory (single-process only)")
    return "memory://"


if _LIMITER_AVAILABLE:
    limiter = Limiter(
        key_func=get_remote_address,
        storage_uri=_get_storage_uri(),
        default_limits=["200 per minute", "20 per second"],
        # Don't let a limiter exception kill a real request.
        swallow_errors=True,
    )
else:
    # Provide a do-nothing shim so imports in route files don't break even
    # without flask-limiter installed.
    class _NoopLimiter:  # type: ignore[no-redef]
        def init_app(self, app) -> None:
            pass

        def limit(self, *args, **kwargs):
            def decorator(f):
                return f
            return decorator

        def exempt(self, f):
            return f

    limiter = _NoopLimiter()  # type: ignore[assignment]


def init_app(app) -> None:
    """Wire the limiter into the Flask app.  Called from create_app()."""
    limiter.init_app(app)
