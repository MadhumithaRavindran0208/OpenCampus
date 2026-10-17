"""
CSRF protection for the server-rendered forms this app is built from.

Every POST/PUT/PATCH/DELETE form embeds a token (via the `csrf_token()`
Jinja global registered in app/__init__.py) that's tied to the user's
session. A before_request hook (also registered in create_app())
rejects any state-changing request whose token doesn't match.

Deliberately hand-rolled rather than pulling in Flask-WTF: the session
is already signed with SECRET_KEY (see app/core/security.py), so a
random token stored in it and compared with a constant-time check is
exactly what Flask-WTF's CSRFProtect does under the hood, without
adding a dependency for one function's worth of logic.
"""
from __future__ import annotations

import hmac
import secrets

from flask import session

SESSION_KEY = "_csrf_token"
FORM_FIELD = "csrf_token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def get_csrf_token() -> str:
    """Returns the current session's CSRF token, generating one on
    first use. Safe to call from a template on every page render --
    it's the same token for the life of the session, not per-request."""
    token = session.get(SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[SESSION_KEY] = token
    return token


def validate_csrf_token(submitted: str | None) -> bool:
    expected = session.get(SESSION_KEY)
    if not expected or not submitted:
        return False
    return hmac.compare_digest(expected, submitted)