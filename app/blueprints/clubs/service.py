"""
Club management service using SQLAlchemy ORM.
"""
from __future__ import annotations

from flask import current_app
from sqlalchemy import func
from app.extensions import db
from app.core import events
from app.core.utils import unique_slug
from app.blueprints.clubs.models import Club, ClubMember
from app.blueprints.projects.models import Project, Issue
from app.blueprints.auth.models import User


class ClubError(Exception):
    pass


def create_club(name: str, description: str, created_by: int) -> Club:
    name = name.strip()
    if not name:
        raise ClubError("Club name is required.")
    slug = unique_slug(name, "clubs")
    requires_approval = current_app.config["REQUIRE_ADMIN_APPROVAL_FOR_CLUBS"]
    status = "pending" if requires_approval else "approved"

    club = Club(
        name=name,
        slug=slug,
        description=description.strip(),
        created_by=created_by,
        status=status,
    )
    db.session.add(club)
    db.session.flush()

    member = ClubMember(club_id=club.id, user_id=created_by, role="admin")
    db.session.add(member)
    db.session.commit()

    if requires_approval:
        events.emit(events.CLUB_SUBMITTED, club_id=club.id, name=name, created_by=created_by)
    return club


def list_clubs() -> list[dict]:
    """Public club listing -- approved clubs only."""
    rows = (
        db.session.query(
            Club.id,
            Club.name,
            Club.slug,
            Club.description,
            Club.created_by,
            Club.status,
            Club.created_at,
            func.count(func.distinct(ClubMember.user_id)).label("member_count"),
            func.count(func.distinct(Project.id)).label("project_count"),
        )
        .outerjoin(ClubMember, ClubMember.club_id == Club.id)
        .outerjoin(Project, Project.club_id == Club.id)
        .filter(Club.status == "approved")
        .group_by(Club.id)
        .order_by(Club.name)
        .all()
    )
    return [dict(r._mapping) for r in rows]


def list_pending_clubs() -> list[dict]:
    rows = (
        db.session.query(
            Club.id,
            Club.name,
            Club.slug,
            Club.description,
            Club.created_by,
            Club.status,
            Club.created_at,
            User.full_name.label("created_by_name"),
        )
        .join(User, User.id == Club.created_by)
        .filter(Club.status == "pending")
        .order_by(Club.created_at)
        .all()
    )
    return [dict(r._mapping) for r in rows]


def approve_club(club_id: int) -> None:
    club = Club.query.get(club_id)
    if club is None or club.status != "pending":
        raise ClubError("This club is not awaiting approval.")
    club.status = "approved"
    db.session.commit()
    events.emit(events.CLUB_APPROVED, club_id=club.id, name=club.name, created_by=club.created_by)


def reject_club(club_id: int) -> None:
    club = Club.query.get(club_id)
    if club is None or club.status != "pending":
        raise ClubError("This club is not awaiting approval.")
    club.status = "rejected"
    db.session.commit()
    events.emit(events.CLUB_REJECTED, club_id=club.id, name=club.name, created_by=club.created_by)


def get_club_by_slug(slug: str) -> Club | None:
    return Club.query.filter_by(slug=slug).first()


def get_club_members(club_id: int) -> list[dict]:
    rows = (
        db.session.query(
            User.id,
            User.full_name,
            User.email,
            User.role.label("platform_role"),
            ClubMember.role.label("club_role"),
            ClubMember.joined_at,
        )
        .join(User, User.id == ClubMember.user_id)
        .filter(ClubMember.club_id == club_id)
        .order_by(ClubMember.role.desc(), User.full_name)
        .all()
    )
    return [dict(r._mapping) for r in rows]


def join_club(club_id: int, user_id: int) -> None:
    club = Club.query.get(club_id)
    if club is None or club.status != "approved":
        raise ClubError("This club isn't open to new members yet.")
    existing = ClubMember.query.filter_by(club_id=club_id, user_id=user_id).first()
    if existing:
        return
    member = ClubMember(club_id=club_id, user_id=user_id, role="member")
    db.session.add(member)
    db.session.commit()


def get_club_projects(club_id: int) -> list[dict]:
    rows = (
        db.session.query(
            Project.id,
            Project.club_id,
            Project.name,
            Project.slug,
            Project.description,
            Project.tech_stack,
            Project.repo_url,
            Project.difficulty,
            Project.status,
            Project.is_seeking_contributors,
            Project.required_skills,
            Project.looking_for,
            Project.created_by,
            Project.created_at,
            Project.updated_at,
            func.count(Issue.id).label("open_issue_count"),
        )
        .outerjoin(Issue, (Issue.project_id == Project.id) & (Issue.status == "open"))
        .filter(Project.club_id == club_id)
        .group_by(Project.id)
        .order_by(Project.updated_at.desc())
        .all()
    )
    return [dict(r._mapping) for r in rows]


def set_club_admin(club_id: int, admin_user_id: int, secret_code: str | None = None) -> None:
    club = Club.query.get(club_id)
    if not club:
        raise ClubError("Club not found.")
    user = User.query.get(admin_user_id)
    if not user:
        raise ClubError("User not found.")

    user.role = "club_admin"
    club.admin_id = user.id

    membership = ClubMember.query.filter_by(club_id=club_id, user_id=admin_user_id).first()
    if membership:
        membership.role = "admin"
    else:
        membership = ClubMember(club_id=club_id, user_id=admin_user_id, role="admin")
        db.session.add(membership)

    if secret_code:
        club.set_secret_code(secret_code)

    db.session.commit()
    from app.core.security import record_audit_log
    record_audit_log(
        user_id=None,
        action="club_admin_assigned",
        target_type="club",
        target_id=str(club.id),
        details=f"User {user.full_name} ({user.email}) assigned as admin of '{club.name}'",
    )


def set_club_secret_code(club_id: int, secret_code: str) -> None:
    club = Club.query.get(club_id)
    if not club:
        raise ClubError("Club not found.")
    if len(secret_code.strip()) < 4:
        raise ClubError("Secret code must be at least 4 characters.")
    club.set_secret_code(secret_code.strip())
    db.session.commit()
    from app.core.security import record_audit_log
    record_audit_log(
        user_id=None,
        action="club_secret_code_updated",
        target_type="club",
        target_id=str(club.id),
        details=f"Secret code updated for club '{club.name}'",
    )


def get_club_admin_dashboard_data(club_id: int) -> dict:
    from app.blueprints.projects.models import CollaborationTag, Project
    club = Club.query.get(club_id)
    if not club:
        raise ClubError("Club not found.")
    members = get_club_members(club_id)
    projects = get_club_projects(club_id)

    club_project_ids = [p["id"] for p in projects]
    pending_tags = (
        db.session.query(
            CollaborationTag.id,
            CollaborationTag.project_id,
            CollaborationTag.name,
            CollaborationTag.status,
            CollaborationTag.created_at,
            Project.name.label("project_name"),
            Project.slug.label("project_slug"),
        )
        .join(Project, Project.id == CollaborationTag.project_id)
        .filter(
            CollaborationTag.project_id.in_(club_project_ids),
            CollaborationTag.status == "pending",
        )
        .order_by(CollaborationTag.created_at.desc())
        .all()
    ) if club_project_ids else []

    return {
        "club": club,
        "members": members,
        "projects": projects,
        "pending_tags": [dict(t._mapping) for t in pending_tags],
    }