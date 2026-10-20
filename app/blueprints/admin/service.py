"""
Admin platform reporting and user governance service using SQLAlchemy ORM.
"""
from __future__ import annotations

from sqlalchemy import func
from app.extensions import db
from app.blueprints.auth.models import User
from app.blueprints.clubs.models import Club
from app.blueprints.projects.models import (
    Project,
    ProjectMember,
    Issue,
    MentorshipRequest,
    OwnershipTransfer,
)
from app.blueprints.notifications.models import ContributionLog


def platform_stats() -> dict:
    return {
        "users": User.query.count(),
        "active_users": User.query.filter_by(is_active=1).count(),
        "clubs": Club.query.count(),
        "projects": Project.query.count(),
        "projects_seeking_maintainer": Project.query.filter_by(status="seeking_maintainer").count(),
        "open_issues": Issue.query.filter_by(status="open").count(),
        "closed_issues": Issue.query.filter(Issue.status.in_(["done", "closed"])).count(),
        "pending_mentorships": MentorshipRequest.query.filter_by(status="pending").count(),
        "completed_mentorships": MentorshipRequest.query.filter_by(status="completed").count(),
        "pending_transfers": OwnershipTransfer.query.filter_by(status="pending").count(),
        "pending_clubs": Club.query.filter_by(status="pending").count(),
        "projects_seeking_contributors": Project.query.filter_by(is_seeking_contributors=1).count(),
    }


def list_users(limit: int = 100) -> list[dict]:
    users = User.query.order_by(User.created_at.desc()).limit(limit).all()
    return [u.to_dict() for u in users]


def set_user_role(user_id: int, role: str) -> None:
    user = User.query.get(user_id)
    if user:
        user.role = role
        db.session.commit()


def set_user_active(user_id: int, active: bool) -> None:
    user = User.query.get(user_id)
    if user:
        user.is_active = 1 if active else 0
        db.session.commit()


def list_pending_transfers() -> list[dict]:
    FromUser = db.aliased(User)
    ToUser = db.aliased(User)

    rows = (
        db.session.query(
            OwnershipTransfer.id,
            OwnershipTransfer.project_id,
            OwnershipTransfer.from_user_id,
            OwnershipTransfer.to_user_id,
            OwnershipTransfer.status,
            OwnershipTransfer.created_at,
            Project.name.label("project_name"),
            Project.slug.label("project_slug"),
            FromUser.full_name.label("from_name"),
            ToUser.full_name.label("to_name"),
        )
        .join(Project, Project.id == OwnershipTransfer.project_id)
        .join(FromUser, FromUser.id == OwnershipTransfer.from_user_id)
        .join(ToUser, ToUser.id == OwnershipTransfer.to_user_id)
        .filter(OwnershipTransfer.status == "pending")
        .order_by(OwnershipTransfer.created_at.desc())
        .all()
    )
    return [dict(r._mapping) for r in rows]


def top_contributors(limit: int = 10) -> list[dict]:
    rows = (
        db.session.query(
            User.id,
            User.full_name,
            func.sum(ContributionLog.points).label("total_points"),
            func.count(ContributionLog.id).label("activity_count"),
        )
        .join(User, User.id == ContributionLog.user_id)
        .group_by(User.id)
        .order_by(func.sum(ContributionLog.points).desc())
        .limit(limit)
        .all()
    )
    return [dict(r._mapping) for r in rows]


def projects_needing_attention() -> list[dict]:
    """Projects with no maintainer activity signal: seeking_maintainer status, or only one member."""
    rows = (
        db.session.query(
            Project.id,
            Project.club_id,
            Project.name,
            Project.slug,
            Project.description,
            Project.status,
            Project.difficulty,
            Project.updated_at,
            func.count(ProjectMember.id).label("member_count"),
        )
        .outerjoin(ProjectMember, ProjectMember.project_id == Project.id)
        .group_by(Project.id)
        .having((Project.status == "seeking_maintainer") | (func.count(ProjectMember.id) <= 1))
        .order_by(Project.updated_at.asc())
        .all()
    )
    return [dict(r._mapping) for r in rows]