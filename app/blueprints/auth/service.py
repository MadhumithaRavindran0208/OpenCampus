from __future__ import annotations

import re

from app.core import db, events
from app.core.config import get_config
from app.core.security import hash_password, verify_password


class AuthError(Exception):
    pass


# Deliberately not a fully RFC-5322-compliant pattern (nothing practical
# is) -- this catches the actual gap that mattered: no whitespace, at
# most one @, a non-empty local part, and a domain with a real TLD
# (something.something). Good enough to reject "a@", "@b", "a@b",
# "a b@c.com", "a@@b.com" etc. without rejecting legitimate addresses.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _is_valid_email(value: str) -> bool:
    return bool(_EMAIL_PATTERN.match(value))


def register_user(email: str, password: str, full_name: str, role: str = "student") -> dict:
    email = email.strip().lower()
    if not email or not _is_valid_email(email):
        raise AuthError("Please enter a valid email address.")
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters.")
    if not full_name.strip():
        raise AuthError("Please enter your full name.")

    existing = db.query_one("SELECT id FROM users WHERE email = ?", (email,))
    if existing:
        raise AuthError("An account with that email already exists.")

    if role not in ("student", "mentor"):
        role = "student"  # club_admin/platform_admin can't self-assign at signup

    user_id = db.execute(
        "INSERT INTO users (email, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
        (email, hash_password(password), full_name.strip(), role),
    )
    user = db.query_one("SELECT * FROM users WHERE id = ?", (user_id,))
    events.emit(events.USER_REGISTERED, user_id=user_id, email=email)
    return user


def authenticate(email: str, password: str) -> dict:
    email = email.strip().lower()
    user = db.query_one("SELECT * FROM users WHERE email = ?", (email,))
    if user is None or not verify_password(user["password_hash"], password):
        raise AuthError("Incorrect email or password.")
    if not user["is_active"]:
        raise AuthError("This account has been deactivated. Contact an administrator.")
    return user


ALLOWED_URL_SCHEMES = ("http://", "https://")


def _validate_external_url(value: str, field_label: str) -> str:
    """Empty is fine (field is optional) -- anything non-empty must be a
    plain http(s) URL. Blocks javascript:, data:, vbscript:, and any
    other scheme that a browser would otherwise happily execute if we
    ever render this value as an href (see profile.html /
    projects/detail.html, both use it directly in <a href>)."""
    value = value.strip()
    if not value:
        return ""
    if not value.lower().startswith(ALLOWED_URL_SCHEMES):
        raise AuthError(f"{field_label} must start with http:// or https://.")
    return value


def _validate_contact_email(value: str) -> str:
    """Same gap as the URL fields had before ADR coverage: this field
    was being saved with no format check at all. Empty is fine
    (optional, falls back to the login email -- see
    resolve_external_email below); anything non-empty must look like a
    real email address."""
    value = value.strip()
    if not value:
        return ""
    if not _is_valid_email(value):
        raise AuthError("Contact email doesn't look like a valid email address.")
    return value


def update_profile(
    user_id: int, full_name: str, bio: str, skills: str,
    contact_email: str = "", discord_handle: str = "", linkedin_url: str = "", github_url: str = "",
    age_category: str = "",
) -> None:
    contact_email = _validate_contact_email(contact_email)
    linkedin_url = _validate_external_url(linkedin_url, "LinkedIn URL")
    github_url = _validate_external_url(github_url, "GitHub URL")

    age_category = age_category.strip()
    if age_category and age_category not in get_config().AGE_CATEGORIES:
        raise AuthError("Please choose a valid age category.")

    db.execute(
        """UPDATE users SET full_name = ?, bio = ?, skills = ?,
               contact_email = ?, discord_handle = ?, linkedin_url = ?, github_url = ?, age_category = ?
           WHERE id = ?""",
        (
            full_name.strip(), bio.strip(), skills.strip(),
            contact_email, discord_handle.strip(), linkedin_url, github_url, age_category,
            user_id,
        ),
    )


def get_public_profile(user_id: int) -> dict | None:
    user = db.query_one(
        """SELECT id, full_name, email, role, bio, skills, created_at,
                  contact_email, discord_handle, linkedin_url, github_url, age_category
           FROM users WHERE id = ?""",
        (user_id,),
    )
    if not user:
        return None
    contributions = db.query(
        """SELECT activity_type, COUNT(*) AS count, SUM(points) AS points
           FROM contribution_log WHERE user_id = ? GROUP BY activity_type""",
        (user_id,),
    )
    projects = db.query(
        """SELECT p.id, p.name, p.slug, pm.role FROM project_members pm
           JOIN projects p ON p.id = pm.project_id WHERE pm.user_id = ?""",
        (user_id,),
    )
    return {"user": user, "contributions": contributions, "projects": projects}


def resolve_external_email(user_id: int) -> str | None:
    """The address to use for outbound email: contact_email if the user set
    one, otherwise their login email. Used by app/core/listeners.py."""
    user = db.query_one("SELECT email, contact_email FROM users WHERE id = ?", (user_id,))
    if not user:
        return None
    return user["contact_email"] or user["email"]