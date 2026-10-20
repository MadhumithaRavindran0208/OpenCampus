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
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _resolve_secret_key() -> str:
    """Return the session-signing key.

    Uses OPENCAMPUS_SECRET_KEY when set. Otherwise falls back to a key that is
    generated once and persisted in the instance directory, so sessions survive
    restarts, debug-reloader respawns and multiple worker processes (a fresh
    os.urandom() key per process would log everyone out on every restart and
    make sessions fail randomly across workers). Always set the env var in
    production.
    """
    env_key = os.environ.get("OPENCAMPUS_SECRET_KEY")
    if env_key:
        return env_key
    data_dir = Path(os.environ.get("OPENCAMPUS_DATA_DIR", BASE_DIR / "instance"))
    key_file = data_dir / ".secret_key"
    try:
        if key_file.exists():
            existing = key_file.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        data_dir.mkdir(parents=True, exist_ok=True)
        generated = os.urandom(32).hex()
        key_file.write_text(generated, encoding="utf-8")
        try:
            os.chmod(key_file, 0o600)
        except OSError:
            pass
        return generated
    except OSError:
        return os.urandom(32).hex()


class Config:
    # --- Identity / security ---
    SECRET_KEY: str = _resolve_secret_key()
    MAIN_ADMIN_SECRET_CODE: str = os.environ.get("MAIN_ADMIN_SECRET_CODE", "")
    SESSION_COOKIE_NAME: str = "opencampus_session"
    SESSION_LIFETIME_DAYS: int = int(os.environ.get("OPENCAMPUS_SESSION_DAYS", "14"))
    # Cookie hardening. Set OPENCAMPUS_COOKIE_SECURE=true once the site is served
    # over HTTPS (browsers drop Secure cookies on plain http, which would break login).
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"
    SESSION_COOKIE_SECURE: bool = os.environ.get("OPENCAMPUS_COOKIE_SECURE", "false").lower() == "true"
    REMEMBER_COOKIE_HTTPONLY: bool = True
    REMEMBER_COOKIE_SAMESITE: str = "Lax"
    REMEMBER_COOKIE_SECURE: bool = SESSION_COOKIE_SECURE
    REMEMBER_COOKIE_DURATION: timedelta = timedelta(days=SESSION_LIFETIME_DAYS)
    PERMANENT_SESSION_LIFETIME: timedelta = timedelta(days=SESSION_LIFETIME_DAYS)

    # --- Storage ---
    DATA_DIR: Path = Path(os.environ.get("OPENCAMPUS_DATA_DIR", BASE_DIR / "instance"))
    DATABASE_PATH: Path = DATA_DIR / os.environ.get("OPENCAMPUS_DB_FILENAME", "opencampus.db")

    # --- Database (SQLite or PostgreSQL) ---
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "")
    DATABASE_READ_REPLICA_URL: str = os.environ.get("DATABASE_READ_REPLICA_URL", "")
    DB_POOL_MIN: int = int(os.environ.get("DB_POOL_MIN", 2))
    DB_POOL_MAX: int = int(os.environ.get("DB_POOL_MAX", 20))

    # --- Flask-SQLAlchemy ---
    _db_url_env = os.environ.get("DATABASE_URL", "").strip()
    if _db_url_env:
        if _db_url_env.startswith("postgres://"):
            _db_url_env = _db_url_env.replace("postgres://", "postgresql://", 1)
        SQLALCHEMY_DATABASE_URI: str = _db_url_env
    else:
        _db_file = Path(os.environ.get("OPENCAMPUS_DATA_DIR", BASE_DIR / "instance")) / os.environ.get("OPENCAMPUS_DB_FILENAME", "opencampus.db")
        SQLALCHEMY_DATABASE_URI: str = f"sqlite:///{_db_file.as_posix()}"

    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    # --- Redis (optional) ---
    # Used by Flask-Limiter (shared rate-limit state across workers) and
    # optionally by the SSE Pub/Sub backend (see app/core/sse.py).
    # Omit or leave blank to use in-memory fallback (single process only).
    REDIS_URL: str = os.environ.get("REDIS_URL", "")

    # Flask-Limiter reads RATELIMIT_STORAGE_URI automatically; keep it in
    # sync with REDIS_URL so there is a single source of truth.
    RATELIMIT_STORAGE_URI: str = os.environ.get("REDIS_URL", "memory://")

    # --- Celery Background Queue ---
    USE_CELERY: bool = os.environ.get("OPENCAMPUS_USE_CELERY", "false").lower() == "true"
    CELERY_BROKER_URL: str = os.environ.get("CELERY_BROKER_URL", os.environ.get("REDIS_URL", ""))
    CELERY_RESULT_BACKEND: str = os.environ.get("CELERY_RESULT_BACKEND", os.environ.get("REDIS_URL", ""))

    # --- Edge Storage & CDN ---
    CDN_BASE_URL: str = os.environ.get("CDN_BASE_URL", "")
    S3_BUCKET_NAME: str = os.environ.get("S3_BUCKET_NAME", "")

    # --- Observability & SLOs ---
    SLO_LATENCY_THRESHOLD_MS: float = float(os.environ.get("SLO_LATENCY_THRESHOLD_MS", "500.0"))

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
    REQUIRE_EMAIL_VERIFICATION: bool = os.environ.get("OPENCAMPUS_REQUIRE_EMAIL_VERIFICATION", "true").lower() == "true"
    ONLY_ALLOW_GMAIL: bool = os.environ.get("OPENCAMPUS_ONLY_GMAIL", "false").lower() == "true"
    # College/institutional email domain restriction (e.g. .edu, .ac.in, mycollege.edu)
    REQUIRE_COLLEGE_EMAIL: bool = os.environ.get("OPENCAMPUS_REQUIRE_COLLEGE_EMAIL", "false").lower() == "true"
    ALLOWED_EMAIL_DOMAINS: list[str] = [
        d.strip().lower() for d in os.environ.get("OPENCAMPUS_ALLOWED_EMAIL_DOMAINS", "").split(",") if d.strip()
    ]

    @classmethod
    def ensure_data_dir(cls) -> None:
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_config():
    try:
        from flask import current_app
        if current_app:
            return current_app.config
    except Exception:
        pass
    return Config