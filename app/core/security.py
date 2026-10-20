"""
Authentication primitives backed by Flask-Login and Werkzeug password security.
"""
from __future__ import annotations

from functools import wraps
from flask import g, redirect, url_for, flash, abort
from flask_login import (
    login_user,
    logout_user,
    login_required,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash

hash_password = generate_password_hash
verify_password = check_password_hash


def load_logged_in_user() -> None:
    """Populate g.user with current_user for backwards compatibility across templates and services."""
    if current_user.is_authenticated:
        g.user = current_user
    else:
        g.user = None


def roles_required(*allowed_roles: str):
    """Restrict a view to specific platform-level roles."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                flash("Please sign in to continue.", "warning")
                return redirect(url_for("auth.login"))
            if current_user.role not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def is_project_member(project_id: int, user_id: int, roles: tuple[str, ...] = ()) -> bool:
    from app.blueprints.projects.models import ProjectMember
    member = ProjectMember.query.filter_by(project_id=project_id, user_id=user_id).first()
    if member is None:
        return False
    return not roles or member.role in roles


def is_main_admin(user_id_or_user) -> bool:
    if not user_id_or_user:
        return False
    if hasattr(user_id_or_user, "role"):
        return user_id_or_user.role == "platform_admin"
    from app.blueprints.auth.models import User
    user = User.query.get(user_id_or_user)
    return user is not None and user.role == "platform_admin"


def is_club_admin(club_id: int, user_id: int) -> bool:
    if not user_id:
        return False
    from app.blueprints.auth.models import User
    from app.blueprints.clubs.models import Club, ClubMember
    user = User.query.get(user_id)
    if user and user.role == "platform_admin":
        return True
    club = Club.query.get(club_id)
    if club and club.admin_id == user_id:
        return True
    member = ClubMember.query.filter_by(club_id=club_id, user_id=user_id).first()
    return member is not None and member.role == "admin"


def can_access_source_code(project_id: int, user_id: int | None) -> bool:
    if not user_id:
        return False
    from app.blueprints.auth.models import User
    from app.blueprints.projects.models import (
        Project,
        ProjectMember,
        ProjectAccessGrant,
        MentorshipRequest,
    )
    from app.blueprints.clubs.models import Club, ClubMember

    user = User.query.get(user_id)
    if not user:
        return False
    if user.role == "platform_admin":
        return True

    project = Project.query.get(project_id)
    if not project:
        return False

    # Club Admin of project's club
    club = Club.query.get(project.club_id)
    if club and (club.admin_id == user_id or ClubMember.query.filter_by(club_id=project.club_id, user_id=user_id, role="admin").first()):
        return True

    # Project Owner
    if project.created_by == user_id:
        return True

    # Project Member with owner or maintainer role
    member = ProjectMember.query.filter_by(project_id=project_id, user_id=user_id).first()
    if member and member.role in ("owner", "maintainer"):
        return True

    # Approved Mentor assigned to this project
    accepted_mentorship = MentorshipRequest.query.filter_by(
        project_id=project_id, mentor_id=user_id, status="accepted"
    ).first()
    if accepted_mentorship:
        return True

    # Explicit access grant from project owner
    grant = ProjectAccessGrant.query.filter_by(project_id=project_id, user_id=user_id).first()
    if grant:
        return True

    # If project's source code is publicly accessible
    if getattr(project, "source_code_restricted", 1) == 0:
        return True

    return False


def can_review_project_tags(project_id: int, user_id: int) -> bool:
    if not user_id:
        return False
    from app.blueprints.auth.models import User
    from app.blueprints.projects.models import Project
    from app.blueprints.clubs.models import Club, ClubMember

    user = User.query.get(user_id)
    if not user:
        return False
    if user.role == "platform_admin":
        return True

    project = Project.query.get(project_id)
    if not project:
        return False

    club = Club.query.get(project.club_id)
    if club and (club.admin_id == user_id or ClubMember.query.filter_by(club_id=project.club_id, user_id=user_id, role="admin").first()):
        return True

    return False


def record_audit_log(
    user_id: int | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    details: str = "",
    ip_address: str | None = None,
):
    from app.extensions import db
    from app.blueprints.auth.models import AuditLog

    log_entry = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        details=details,
        ip_address=ip_address or "",
    )
    db.session.add(log_entry)
    db.session.commit()
    return log_entry
