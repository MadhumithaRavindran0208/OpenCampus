"""
Structured logging configuration.

In development (OPENCAMPUS_ENV != production):
  Human-readable, colour-coded lines:
      [2026-10-18 03:01:22] INFO     opencampus.request: GET /projects 200

In production:
  JSON lines, one per record -- suitable for Loki, CloudWatch, Datadog, etc.:
      {"ts":"2026-10-18T03:01:22Z","level":"INFO","logger":"opencampus.request", ...}

Call configure_logging() once from create_app() BEFORE the Flask app starts
accepting requests.  Everything else in the codebase just uses
  import logging; logger = logging.getLogger("opencampus.<module>")
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log record."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        data: dict = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            data["stack"] = self.formatStack(record.stack_info)

        # Inject distributed tracing correlation IDs if in request context
        try:
            from flask import g, has_request_context
            if has_request_context():
                if getattr(g, "trace_id", None):
                    data["trace_id"] = g.trace_id
                if getattr(g, "span_id", None):
                    data["span_id"] = g.span_id
        except Exception:
            pass

        # Any extra keys passed via logger.info("...", extra={"key": val})
        for key, val in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "created", "filename", "funcName",
                "levelname", "levelno", "lineno", "module", "msecs",
                "pathname", "process", "processName", "relativeCreated",
                "stack_info", "thread", "threadName", "exc_info", "exc_text",
                "message",
            }:
                try:
                    json.dumps(val)   # only include JSON-serialisable extras
                    data[key] = val
                except (TypeError, ValueError):
                    data[key] = str(val)
        return json.dumps(data, default=str)


_COLOUR = {
    "DEBUG":    "\033[36m",   # cyan
    "INFO":     "\033[32m",   # green
    "WARNING":  "\033[33m",   # yellow
    "ERROR":    "\033[31m",   # red
    "CRITICAL": "\033[35m",   # magenta
}
_RESET = "\033[0m"


class _DevFormatter(logging.Formatter):
    """Coloured, human-readable single-line format for development."""

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        colour = _COLOUR.get(record.levelname, "")
        level_tag = f"{colour}{record.levelname:<8}{_RESET}"
        msg = record.getMessage()
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return f"[{ts}] {level_tag} {record.name}: {msg}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def configure_logging(is_production: bool = False, level: str = "INFO") -> None:
    """
    Configure the root logger.  Should be called once, early in create_app().

    Parameters
    ----------
    is_production:
        True  → JSON formatter, WARNING level for noisy third-party loggers.
        False → coloured dev formatter, DEBUG allowed.
    level:
        Override the root log level; defaults to INFO.
        Set OPENCAMPUS_LOG_LEVEL=DEBUG for verbose output.
    """
    level_name = os.environ.get("OPENCAMPUS_LOG_LEVEL", level).upper()
    numeric_level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)

    if is_production:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(_DevFormatter())

    root = logging.getLogger()
    root.setLevel(numeric_level)
    # Replace all existing handlers to avoid duplicate lines when Flask also
    # attaches handlers or when create_app() is called more than once in tests.
    root.handlers.clear()
    root.addHandler(handler)

    # Quieten chatty third-party loggers in production.
    if is_production:
        for noisy in ("werkzeug", "urllib3", "asyncio"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("opencampus.logging").info(
        "Logging configured: level=%s, json=%s", level_name, is_production
    )
