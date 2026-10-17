"""
Central configuration.

Everything that might need to change between environments (dev, demo,
production) lives here and is overridable via environment variables.
No module should hardcode a path, secret, or limit -- import from here.

Extension point: if you outgrow SQLite, add a DATABASE_URL-style setting
here and branch app/core/db.py on its scheme. Nothing outside db.py
needs to know which database engine is in use.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Config:
    # --- Identity / security ---
    SECRET_KEY: str = os.environ.get("OPENCAMPUS_SECRET_KEY", "dev-insecure-secret-change-me")
    SESSION_COOKIE_NAME: str = "opencampus_session"
    SESSION_LIFETIME_DAYS: int = int(os.environ.get("OPENCAMPUS_SESSION_DAYS", "14"))

    # --- Storage ---
    DATA_DIR: Path = Path(os.environ.get("OPENCAMPUS_DATA_DIR", BASE_DIR / "instance"))
    DATABASE_PATH: Path = DATA_DIR / os.environ.get("OPENCAMPUS_DB_FILENAME", "opencampus.db")

    # --- Pagination / limits ---
    DEFAULT_PAGE_SIZE: int = 20
    SEARCH_RESULT_LIMIT: int = 25
    MAX_ISSUES_PER_PROJECT_PAGE: int = 30

    # --- Domain rules (kept here so product changes don't touch business logic) ---
    ISSUE_STATUSES = ["open", "claimed", "in_review", "done", "closed"]
    ISSUE_DIFFICULTIES = ["beginner", "intermediate", "advanced"]
    PROJECT_STATUSES = ["active", "seeking_maintainer", "maintenance", "archived"]
    PROJECT_DIFFICULTIES = ["beginner", "intermediate", "advanced"]
    MENTORSHIP_STATUSES = ["pending", "accepted", "declined", "completed"]
    USER_ROLES = ["student", "mentor", "club_admin", "platform_admin"]
    PROJECT_MEMBER_ROLES = ["owner", "maintainer", "contributor"]
    OWNERSHIP_TRANSFER_STATUSES = ["pending", "accepted", "rejected"]
    CLUB_STATUSES = ["pending", "approved", "rejected"]
    # A bracket, not an exact age -- see migrations/0006_user_age_category.sql
    # for why. "Prefer not to say" is a first-class option, not just an
    # empty/skipped state, so choosing not to answer is explicit.
    AGE_CATEGORIES = ["Under 18", "18-24", "25-34", "35-44", "45-54", "55+", "Prefer not to say"]

    # --- External notification dispatch (email / webhook) ---
    # Both are off by default so a fresh checkout never tries to reach the
    # network unexpectedly. Turn on explicitly once SMTP/webhook details
    # are configured. See app/core/dispatch.py.
    ENABLE_EMAIL_NOTIFICATIONS: bool = os.environ.get("OPENCAMPUS_ENABLE_EMAIL", "false").lower() == "true"
    SMTP_HOST: str = os.environ.get("OPENCAMPUS_SMTP_HOST", "")
    SMTP_PORT: int = int(os.environ.get("OPENCAMPUS_SMTP_PORT", "587"))
    SMTP_USERNAME: str = os.environ.get("OPENCAMPUS_SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.environ.get("OPENCAMPUS_SMTP_PASSWORD", "")
    EMAIL_FROM: str = os.environ.get("OPENCAMPUS_EMAIL_FROM", "noreply@opencampus.local")

    ENABLE_WEBHOOK_NOTIFICATIONS: bool = os.environ.get("OPENCAMPUS_ENABLE_WEBHOOK", "false").lower() == "true"
    WEBHOOK_URL: str = os.environ.get("OPENCAMPUS_WEBHOOK_URL", "")

    # --- Feature flags (toggle without touching code elsewhere) ---
    ALLOW_SELF_REGISTRATION: bool = os.environ.get("OPENCAMPUS_ALLOW_SIGNUP", "true").lower() == "true"
    REQUIRE_ADMIN_APPROVAL_FOR_CLUBS: bool = (
        os.environ.get("OPENCAMPUS_CLUB_APPROVAL", "false").lower() == "true"
    )

    @classmethod
    def ensure_data_dir(cls) -> None:
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_config() -> type[Config]:
    return Config