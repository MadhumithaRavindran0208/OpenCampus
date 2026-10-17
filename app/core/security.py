"""
Auth primitives: password hashing, session-backed identity, and
role/ownership guards used as route decorators.

Auth model: server-side session cookie (signed via Flask's SECRET_KEY),
storing only the user id. Deliberately simple for an MVP demo -- see
ARCHITECTURE.md's ADR-002 for why, and how to add token-based API auth
later without touching these decorators.
"""
from __future__ import annotations

from functools import wraps

from flask import session, g, redirect, url_for, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash

from app.core import db

hash_password = generate_password_hash
verify_password = check_password_hash


def load_logged_in_user() -> None:
    """Runs before each request (see app/__init__.py) to populate g.user."""
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = db.query_one("SELECT * FROM users WHERE id = ? AND is_active = 1", (user_id,))


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapped


def roles_required(*allowed_roles: str):
    """Restrict a view to specific platform-level roles (see Config.USER_ROLES)."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if g.user is None:
                flash("Please sign in to continue.", "warning")
                return redirect(url_for("auth.login"))
            if g.user["role"] not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def is_project_member(project_id: int, user_id: int, roles: tuple[str, ...] = ()) -> bool:
    row = db.query_one(
        "SELECT role FROM project_members WHERE project_id = ? AND user_id = ?",
        (project_id, user_id),
    )
    if row is None:
        return False
    return not roles or row["role"] in roles


def is_club_admin(club_id: int, user_id: int) -> bool:
    row = db.query_one(
        "SELECT role FROM club_members WHERE club_id = ? AND user_id = ?",
        (club_id, user_id),
    )
    return row is not None and row["role"] == "admin"
