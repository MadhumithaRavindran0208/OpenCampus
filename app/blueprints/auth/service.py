"""
Authentication and profile service using SQLAlchemy ORM.
"""
from __future__ import annotations

import re
import time
from sqlalchemy import func
from app.extensions import db
from app.core import events
from app.core.config import get_config, Config
from app.core.security import hash_password, verify_password, record_audit_log
from app.blueprints.auth.models import User
from app.blueprints.projects.models import Project, ProjectMember
from app.blueprints.notifications.models import ContributionLog


class AuthError(Exception):
    pass


_EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)
# Gmail username specification: 6-30 characters, letters, numbers, dots (cannot start/end with dot, no consecutive dots)
_GMAIL_USERNAME_PATTERN = re.compile(r"^[a-z0-9](?!.*\.\.)[a-z0-9.]{4,28}[a-z0-9]$")
_FAILED_LOGINS: dict[str, dict] = {}


def validate_email_address(value: str) -> None:
    if not value or not _EMAIL_PATTERN.match(value):
        raise AuthError("Please enter a valid email address.")

    cfg = get_config()
    parts = value.split("@")
    if len(parts) != 2:
        raise AuthError("Please enter a valid email address.")
    local_part, domain = parts[0], parts[1]

    # Enforce Gmail validation if domain is gmail.com or googlemail.com, or if ONLY_ALLOW_GMAIL is set
    only_gmail = cfg.get("ONLY_ALLOW_GMAIL", False) if hasattr(cfg, "get") else getattr(cfg, "ONLY_ALLOW_GMAIL", False)
    is_gmail_domain = domain in ("gmail.com", "googlemail.com")

    if only_gmail and not is_gmail_domain:
        raise AuthError("Only Gmail accounts (@gmail.com) are permitted to sign up.")

    if is_gmail_domain:
        # Check Gmail username rules
        if not _GMAIL_USERNAME_PATTERN.match(local_part):
            raise AuthError(
                "Invalid Gmail username: Gmail usernames must be between 6 and 30 characters, "
                "use only lowercase letters (a-z), numbers (0-9), and periods (.), "
                "and cannot have consecutive periods or begin/end with a period."
            )

    # Enforce institutional / college email requirements if configured
    require_college = cfg.get("REQUIRE_COLLEGE_EMAIL", False) if hasattr(cfg, "get") else getattr(cfg, "REQUIRE_COLLEGE_EMAIL", False)
    allowed_domains = cfg.get("ALLOWED_EMAIL_DOMAINS", []) if hasattr(cfg, "get") else getattr(cfg, "ALLOWED_EMAIL_DOMAINS", [])

    if require_college:
        # Recognized college/academic TLDs or explicit allowed domains
        is_academic = (
            domain.endswith(".edu")
            or domain.endswith(".ac.in")
            or domain.endswith(".edu.in")
            or domain.endswith(".ac.uk")
            or domain.endswith(".edu.au")
            or any(domain == d or domain.endswith("." + d) for d in allowed_domains)
        )
        if not is_academic:
            raise AuthError("Please sign up using your college or institutional email address (e.g. .edu or .ac.in).")

    if allowed_domains and not any(domain == d or domain.endswith("." + d) for d in allowed_domains):
        domains_formatted = ", ".join(allowed_domains)
        raise AuthError(f"Email domain '{domain}' is not authorized. Permitted domains: {domains_formatted}")


def register_user(email: str, password: str, full_name: str, role: str = "student") -> User:
    email = email.strip().lower()
    validate_email_address(email)
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters.")
    if not full_name.strip():
        raise AuthError("Please enter your full name.")

    existing = User.query.filter_by(email=email).first()
    if existing:
        raise AuthError("An account with that email already exists.")

    if role not in ("student", "mentor"):
        role = "student"

    import secrets
    cfg = get_config()
    require_verification = cfg.get("REQUIRE_EMAIL_VERIFICATION", True) if hasattr(cfg, "get") else getattr(cfg, "REQUIRE_EMAIL_VERIFICATION", True)
    verification_token = secrets.token_urlsafe(32) if require_verification else ""
    is_verified = 0 if require_verification else 1

    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        role=role,
        is_verified=is_verified,
        verification_token=verification_token,
    )
    db.session.add(user)
    db.session.commit()

    events.emit(events.USER_REGISTERED, user_id=user.id, email=email)
    record_audit_log(
        user_id=user.id,
        action="user_registered",
        target_type="user",
        target_id=str(user.id),
        details=f"User registered with role {role} (is_verified={is_verified})",
    )
    return user


def verify_email_token(token: str) -> User:
    if not token or not token.strip():
        raise AuthError("Invalid verification token.")

    user = User.query.filter_by(verification_token=token.strip()).first()
    if not user:
        raise AuthError("Invalid or expired email verification link.")

    user.is_verified = 1
    user.verification_token = ""
    db.session.commit()

    record_audit_log(
        user_id=user.id,
        action="email_verified",
        target_type="user",
        target_id=str(user.id),
        details="User successfully verified their email address",
    )
    return user


def resend_verification_email(email: str) -> User:
    email = email.strip().lower()
    user = User.query.filter_by(email=email).first()
    if not user:
        raise AuthError("No account found with that email address.")
    if user.is_verified:
        raise AuthError("This account has already been verified.")

    import secrets
    user.verification_token = secrets.token_urlsafe(32)
    db.session.commit()
    return user


def authenticate(
    email: str,
    password: str,
    secret_code: str | None = None,
    ip_address: str | None = None,
) -> User:
    email = email.strip().lower()
    now = time.time()

    # Check lockout
    lock_record = _FAILED_LOGINS.get(email)
    if lock_record and lock_record["count"] >= 5:
        if now < lock_record["locked_until"]:
            remaining = int(lock_record["locked_until"] - now)
            raise AuthError(f"Account temporarily locked due to repeated failed attempts. Please try again in {remaining}s.")
        else:
            _FAILED_LOGINS.pop(email, None)

    user = User.query.filter_by(email=email).first()
    if user is None or not verify_password(user.password_hash, password):
        rec = _FAILED_LOGINS.setdefault(email, {"count": 0, "locked_until": 0.0})
        rec["count"] += 1
        if rec["count"] >= 5:
            rec["locked_until"] = now + 900.0  # 15 minute lockout
        record_audit_log(
            user_id=user.id if user else None,
            action="login_failed",
            target_type="user",
            target_id=email,
            details="Invalid email or password",
            ip_address=ip_address,
        )
        raise AuthError("Incorrect email or password.")

    if not user.is_active:
        raise AuthError("This account has been deactivated. Contact an administrator.")

    cfg = get_config()
    require_verification = cfg.get("REQUIRE_EMAIL_VERIFICATION", True) if hasattr(cfg, "get") else getattr(cfg, "REQUIRE_EMAIL_VERIFICATION", True)
    if require_verification and not user.is_verified:
        raise AuthError("Please verify your email address before signing in. Check your inbox or request a new link.")

    # Main Admin (platform_admin) Authentication
    if user.role == "platform_admin":
        if not secret_code or not secret_code.strip():
            rec = _FAILED_LOGINS.setdefault(email, {"count": 0, "locked_until": 0.0})
            rec["count"] += 1
            if rec["count"] >= 5:
                rec["locked_until"] = now + 900.0
            record_audit_log(
                user_id=user.id,
                action="admin_secret_code_missing",
                target_type="user",
                target_id=str(user.id),
                details="Main Admin secret code required",
                ip_address=ip_address,
            )
            raise AuthError("Main Admin secret code is required.")

        expected_secret = cfg.get("MAIN_ADMIN_SECRET_CODE", None) if hasattr(cfg, "get") else getattr(cfg, "MAIN_ADMIN_SECRET_CODE", None)
        if not expected_secret or secret_code.strip() != expected_secret:
            rec = _FAILED_LOGINS.setdefault(email, {"count": 0, "locked_until": 0.0})
            rec["count"] += 1
            if rec["count"] >= 5:
                rec["locked_until"] = now + 900.0
            record_audit_log(
                user_id=user.id,
                action="admin_secret_code_invalid",
                target_type="user",
                target_id=str(user.id),
                details="Invalid Main Admin secret code attempt",
                ip_address=ip_address,
            )
            raise AuthError("Invalid Main Admin secret code.")

        record_audit_log(
            user_id=user.id,
            action="admin_login_success",
            target_type="user",
            target_id=str(user.id),
            details="Main Admin authenticated with password and secret code",
            ip_address=ip_address,
        )

    # Club Admin Authentication
    elif user.role == "club_admin":
        if not secret_code or not secret_code.strip():
            rec = _FAILED_LOGINS.setdefault(email, {"count": 0, "locked_until": 0.0})
            rec["count"] += 1
            if rec["count"] >= 5:
                rec["locked_until"] = now + 900.0
            record_audit_log(
                user_id=user.id,
                action="club_admin_secret_code_missing",
                target_type="user",
                target_id=str(user.id),
                details="Club Admin secret code required",
                ip_address=ip_address,
            )
            raise AuthError("Club Admin secret code is required.")

        from app.blueprints.clubs.models import Club, ClubMember
        assigned_clubs = Club.query.filter(
            (Club.admin_id == user.id)
            | (Club.id.in_(db.session.query(ClubMember.club_id).filter_by(user_id=user.id, role="admin")))
        ).all()

        if not assigned_clubs:
            raise AuthError("No club currently assigned to this Club Admin account. Contact the Main Admin.")

        # Check secret code against any assigned club
        valid_club = next((c for c in assigned_clubs if c.verify_secret_code(secret_code)), None)
        if not valid_club:
            rec = _FAILED_LOGINS.setdefault(email, {"count": 0, "locked_until": 0.0})
            rec["count"] += 1
            if rec["count"] >= 5:
                rec["locked_until"] = now + 900.0
            record_audit_log(
                user_id=user.id,
                action="club_admin_secret_code_invalid",
                target_type="user",
                target_id=str(user.id),
                details="Invalid Club Admin secret code for assigned club",
                ip_address=ip_address,
            )
            raise AuthError("Invalid Club Admin secret code for assigned club.")

        record_audit_log(
            user_id=user.id,
            action="club_admin_login_success",
            target_type="club",
            target_id=str(valid_club.id),
            details=f"Club Admin authenticated for club '{valid_club.name}'",
            ip_address=ip_address,
        )

    else:
        # Standard Student or Mentor
        record_audit_log(
            user_id=user.id,
            action="user_login_success",
            target_type="user",
            target_id=str(user.id),
            details=f"User authenticated as {user.role}",
            ip_address=ip_address,
        )

    _FAILED_LOGINS.pop(email, None)
    return user


ALLOWED_URL_SCHEMES = ("http://", "https://")


def _validate_external_url(value: str, field_label: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if not value.lower().startswith(ALLOWED_URL_SCHEMES):
        raise AuthError(f"{field_label} must start with http:// or https://.")
    return value


def _is_valid_email(value: str) -> bool:
    try:
        validate_email_address(value)
        return True
    except AuthError:
        return False


def _validate_contact_email(value: str) -> str:
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
    cfg = get_config()
    allowed_categories = cfg.get("AGE_CATEGORIES") if hasattr(cfg, "get") else getattr(cfg, "AGE_CATEGORIES", Config.AGE_CATEGORIES)
    if age_category and age_category not in allowed_categories:
        raise AuthError("Please choose a valid age category.")

    user = User.query.get(user_id)
    if not user:
        raise AuthError("User not found.")

    user.full_name = full_name.strip()
    user.bio = bio.strip()
    user.skills = skills.strip()
    user.contact_email = contact_email
    user.discord_handle = discord_handle.strip()
    user.linkedin_url = linkedin_url
    user.github_url = github_url
    user.age_category = age_category

    db.session.commit()


def get_public_profile(user_id: int) -> dict | None:
    user = User.query.get(user_id)
    if not user:
        return None

    contributions_rows = (
        db.session.query(
            ContributionLog.activity_type,
            func.count(ContributionLog.id).label("count"),
            func.sum(ContributionLog.points).label("points"),
        )
        .filter(ContributionLog.user_id == user_id)
        .group_by(ContributionLog.activity_type)
        .all()
    )
    contributions = [dict(r._mapping) for r in contributions_rows]

    projects_rows = (
        db.session.query(
            Project.id,
            Project.name,
            Project.slug,
            ProjectMember.role,
        )
        .join(ProjectMember, Project.id == ProjectMember.project_id)
        .filter(ProjectMember.user_id == user_id)
        .all()
    )
    projects = [dict(r._mapping) for r in projects_rows]

    return {"user": user, "contributions": contributions, "projects": projects}


def resolve_external_email(user_id: int) -> str | None:
    user = User.query.get(user_id)
    if not user:
        return None
    return user.contact_email or user.email