"""
CSRF protection backed by Flask-WTF's CSRFProtect.
"""
from __future__ import annotations

from flask_wtf.csrf import generate_csrf, validate_csrf

FORM_FIELD = "csrf_token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def get_csrf_token() -> str:
    return generate_csrf()


def validate_csrf_token(submitted: str | None) -> bool:
    try:
        validate_csrf(submitted)
        return True
    except Exception:
        return False