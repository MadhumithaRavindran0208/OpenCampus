"""
Project service using SQLAlchemy ORM.
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import func, or_
from app.extensions import db
from app.core import events
from app.core.utils import unique_slug, log_contribution
from app.core.security import record_audit_log, can_access_source_code
from app.blueprints.projects.models import (
    Project,
    ProjectMember,
    Issue,
    OwnershipTransfer,
    ProjectAccessGrant,
    CollaborationTag,
    MentorshipRequest,
)
from app.blueprints.notifications.models import Notification, ContributionLog
from app.blueprints.clubs.models import Club
from app.blueprints.auth.models import User


class ProjectError(Exception):
    pass


def create_project(
    club_id: int, name: str, description: str, tech_stack: str, repo_url: str,
    difficulty: str, created_by: int, is_seeking_contributors: bool = False, required_skills: str = "",
) -> Project:
    name = name.strip()
    if not name:
        raise ProjectError("Project name is required.")
    slug = unique_slug(name, "projects")

    project = Project(
        club_id=club_id,
        name=name,
        slug=slug,
        description=description.strip(),
        tech_stack=tech_stack.strip(),
        repo_url=repo_url.strip(),
        difficulty=difficulty,
        created_by=created_by,
        is_seeking_contributors=1 if is_seeking_contributors else 0,
        required_skills=required_skills.strip(),
    )
    db.session.add(project)
    db.session.flush()

    member = ProjectMember(project_id=project.id, user_id=created_by, role="owner")
    db.session.add(member)
    db.session.commit()

    log_contribution(created_by, "project_created", project.id, points=5)
    events.emit(events.PROJECT_CREATED, project_id=project.id, created_by=created_by, name=name)
    return project


def list_projects_for_feed(limit: int = 10) -> list[dict]:
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
            Club.name.label("club_name"),
            Club.slug.label("club_slug"),
            func.count(func.distinct(Issue.id)).label("open_issue_count"),
        )
        .join(Club, Club.id == Project.club_id)
        .outerjoin(Issue, (Issue.project_id == Project.id) & (Issue.status == "open"))
        .filter(Project.status.in_(["active", "seeking_maintainer"]))
        .group_by(Project.id)
        .order_by(Project.updated_at.desc())
        .limit(limit)
        .all()
    )
    return [dict(r._mapping) for r in rows]


def search_projects(
    query: str = "", difficulty: str = "", status: str = "", seeking_only: bool = False, limit: int = 50,
) -> list[dict]:
    q = (
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
            Club.name.label("club_name"),
            Club.slug.label("club_slug"),
            func.count(func.distinct(Issue.id)).label("open_issue_count"),
        )
        .join(Club, Club.id == Project.club_id)
        .outerjoin(Issue, (Issue.project_id == Project.id) & (Issue.status == "open"))
    )

    if query:
        pattern = f"%{query}%"
        q = q.filter(
            or_(
                Project.name.ilike(pattern),
                Project.description.ilike(pattern),
                Project.tech_stack.ilike(pattern),
                Project.required_skills.ilike(pattern),
            )
        )
    if difficulty:
        q = q.filter(Project.difficulty == difficulty)
    if status:
        q = q.filter(Project.status == status)
    if seeking_only:
        q = q.filter(Project.is_seeking_contributors == 1)

    rows = (
        q.group_by(Project.id)
        .order_by(Project.is_seeking_contributors.desc(), Project.updated_at.desc())
        .limit(limit)
        .all()
    )
    return [dict(r._mapping) for r in rows]


def get_project_by_slug(slug: str) -> dict | None:
    row = (
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
            Club.name.label("club_name"),
            Club.slug.label("club_slug"),
        )
        .join(Club, Club.id == Project.club_id)
        .filter(Project.slug == slug)
        .first()
    )
    return dict(row._mapping) if row else None


def get_project(project_id: int) -> Project | None:
    return Project.query.get(project_id)


def get_members(project_id: int) -> list[dict]:
    rows = (
        db.session.query(
            User.id,
            User.full_name,
            User.email,
            User.contact_email,
            User.discord_handle,
            User.linkedin_url,
            User.github_url,
            ProjectMember.role,
            ProjectMember.joined_at,
        )
        .join(User, User.id == ProjectMember.user_id)
        .filter(ProjectMember.project_id == project_id)
        .order_by(
            db.case(
                (ProjectMember.role == "owner", 0),
                (ProjectMember.role == "maintainer", 1),
                else_=2,
            ),
            User.full_name,
        )
        .all()
    )
    return [dict(r._mapping) for r in rows]


def join_as_contributor(project_id: int, user_id: int) -> None:
    existing = ProjectMember.query.filter_by(project_id=project_id, user_id=user_id).first()
    if existing:
        return
    member = ProjectMember(project_id=project_id, user_id=user_id, role="contributor")
    db.session.add(member)
    db.session.commit()


def update_status(project_id: int, status: str) -> None:
    project = Project.query.get(project_id)
    if project:
        project.status = status
        project.updated_at = datetime.now(timezone.utc).isoformat()
        db.session.commit()


def update_help_wanted(project_id: int, is_seeking_contributors: bool, required_skills: str) -> None:
    project = Project.query.get(project_id)
    if project:
        project.is_seeking_contributors = 1 if is_seeking_contributors else 0
        project.required_skills = required_skills.strip()
        project.updated_at = datetime.now(timezone.utc).isoformat()
        db.session.commit()


def request_ownership_transfer(project_id: int, from_user_id: int, to_user_id: int) -> int:
    if from_user_id == to_user_id:
        raise ProjectError("Choose a different member to transfer ownership to.")
    member = ProjectMember.query.filter_by(project_id=project_id, user_id=to_user_id).first()
    if member is None:
        raise ProjectError("That user is not a member of this project.")

    transfer = OwnershipTransfer(
        project_id=project_id,
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        status="pending",
    )
    db.session.add(transfer)
    db.session.commit()

    events.emit(
        events.OWNERSHIP_TRANSFER_REQUESTED,
        transfer_id=transfer.id,
        project_id=project_id,
        from_user_id=from_user_id,
        to_user_id=to_user_id,
    )
    return transfer.id


def resolve_ownership_transfer(transfer_id: int, user_id: int, accept: bool) -> None:
    transfer = OwnershipTransfer.query.get(transfer_id)
    if transfer is None or transfer.status != "pending":
        raise ProjectError("This transfer is no longer pending.")
    if transfer.to_user_id != user_id:
        raise ProjectError("Only the recipient can accept or reject this transfer.")

    new_status = "accepted" if accept else "rejected"
    now_iso = datetime.now(timezone.utc).isoformat()
    transfer.status = new_status
    transfer.resolved_at = now_iso

    if accept:
        # Demote previous owner to maintainer
        prev_owner = ProjectMember.query.filter_by(
            project_id=transfer.project_id, user_id=transfer.from_user_id
        ).first()
        if prev_owner:
            prev_owner.role = "maintainer"

        # Promote recipient to owner
        new_owner = ProjectMember.query.filter_by(
            project_id=transfer.project_id, user_id=transfer.to_user_id
        ).first()
        if new_owner:
            new_owner.role = "owner"
        else:
            db.session.add(
                ProjectMember(project_id=transfer.project_id, user_id=transfer.to_user_id, role="owner")
            )

    db.session.commit()
    events.emit(
        events.OWNERSHIP_TRANSFER_RESOLVED,
        transfer_id=transfer.id,
        project_id=transfer.project_id,
        to_user_id=transfer.to_user_id,
        accepted=accept,
    )


def get_pending_transfers(user_id: int) -> list[dict]:
    rows = (
        db.session.query(
            OwnershipTransfer.id,
            OwnershipTransfer.project_id,
            OwnershipTransfer.created_at,
            Project.name.label("project_name"),
            Project.slug.label("project_slug"),
            User.full_name.label("from_user_name"),
        )
        .join(Project, Project.id == OwnershipTransfer.project_id)
        .join(User, User.id == OwnershipTransfer.from_user_id)
        .filter(OwnershipTransfer.to_user_id == user_id, OwnershipTransfer.status == "pending")
        .all()
    )
    return [dict(r._mapping) for r in rows]


def grant_source_code_access(project_id: int, target_user_id: int, granted_by: int) -> ProjectAccessGrant:
    project = Project.query.get(project_id)
    if not project:
        raise ProjectError("Project not found.")
    user = User.query.get(target_user_id)
    if not user:
        raise ProjectError("User not found.")

    existing = ProjectAccessGrant.query.filter_by(project_id=project_id, user_id=target_user_id).first()
    if existing:
        return existing

    grant = ProjectAccessGrant(project_id=project_id, user_id=target_user_id, granted_by=granted_by)
    db.session.add(grant)

    # Notify user
    notif = Notification(
        user_id=target_user_id,
        type="access_granted",
        message=f"You have been granted source code access to project '{project.name}'.",
        link=f"/projects/{project.slug}",
    )
    db.session.add(notif)
    db.session.commit()

    record_audit_log(
        user_id=granted_by,
        action="source_code_access_granted",
        target_type="project",
        target_id=str(project_id),
        details=f"Access granted to user {user.full_name} ({user.email})",
    )
    return grant


def revoke_source_code_access(project_id: int, target_user_id: int, revoked_by: int) -> None:
    project = Project.query.get(project_id)
    if not project:
        raise ProjectError("Project not found.")
    grant = ProjectAccessGrant.query.filter_by(project_id=project_id, user_id=target_user_id).first()
    if not grant:
        return

    db.session.delete(grant)

    # Notify user
    notif = Notification(
        user_id=target_user_id,
        type="access_revoked",
        message=f"Your source code access to project '{project.name}' has been revoked.",
        link=f"/projects/{project.slug}",
    )
    db.session.add(notif)
    db.session.commit()

    record_audit_log(
        user_id=revoked_by,
        action="source_code_access_revoked",
        target_type="project",
        target_id=str(project_id),
        details=f"Access revoked from user_id {target_user_id}",
    )


def list_source_code_grants(project_id: int) -> list[dict]:
    rows = (
        db.session.query(
            ProjectAccessGrant.id,
            ProjectAccessGrant.project_id,
            ProjectAccessGrant.user_id,
            ProjectAccessGrant.created_at,
            User.full_name.label("user_name"),
            User.email.label("user_email"),
            User.role.label("user_role"),
        )
        .join(User, User.id == ProjectAccessGrant.user_id)
        .filter(ProjectAccessGrant.project_id == project_id)
        .order_by(ProjectAccessGrant.created_at.desc())
        .all()
    )
    return [dict(r._mapping) for r in rows]


def update_source_code_restricted(project_id: int, restricted: bool, updated_by: int) -> None:
    project = Project.query.get(project_id)
    if not project:
        raise ProjectError("Project not found.")
    project.source_code_restricted = 1 if restricted else 0
    db.session.commit()

    record_audit_log(
        user_id=updated_by,
        action="project_visibility_updated",
        target_type="project",
        target_id=str(project_id),
        details=f"Source code restricted set to {restricted}",
    )


def add_collaboration_tag(project_id: int, name: str, user_id: int) -> CollaborationTag:
    name = name.strip()
    if not name:
        raise ProjectError("Tag name is required.")
    project = Project.query.get(project_id)
    if not project:
        raise ProjectError("Project not found.")

    existing = CollaborationTag.query.filter_by(project_id=project_id, name=name).first()
    if existing:
        if existing.status == "rejected":
            existing.status = "pending"
            existing.rejection_reason = ""
            existing.created_at = datetime.now(timezone.utc).isoformat()
            db.session.commit()
            return existing
        return existing

    tag = CollaborationTag(project_id=project_id, name=name, status="pending")
    db.session.add(tag)
    db.session.commit()

    record_audit_log(
        user_id=user_id,
        action="collaboration_tag_submitted",
        target_type="project",
        target_id=str(project_id),
        details=f"Submitted collaboration tag '{name}' for approval",
    )
    return tag


def approve_collaboration_tag(tag_id: int, reviewer_id: int) -> None:
    tag = CollaborationTag.query.get(tag_id)
    if not tag:
        raise ProjectError("Tag not found.")
    tag.status = "approved"
    tag.reviewed_by = reviewer_id
    tag.reviewed_at = datetime.now(timezone.utc).isoformat()
    tag.rejection_reason = ""

    project = Project.query.get(tag.project_id)
    if project:
        notif = Notification(
            user_id=project.created_by,
            type="tag_approved",
            message=f"Your collaboration tag '{tag.name}' for project '{project.name}' was approved!",
            link=f"/projects/{project.slug}",
        )
        db.session.add(notif)

    db.session.commit()

    record_audit_log(
        user_id=reviewer_id,
        action="collaboration_tag_approved",
        target_type="collaboration_tag",
        target_id=str(tag.id),
        details=f"Approved tag '{tag.name}' on project_id {tag.project_id}",
    )


def reject_collaboration_tag(tag_id: int, reviewer_id: int, reason: str) -> None:
    tag = CollaborationTag.query.get(tag_id)
    if not tag:
        raise ProjectError("Tag not found.")
    reason = reason.strip()
    if not reason:
        raise ProjectError("Rejection reason is required.")

    tag.status = "rejected"
    tag.rejection_reason = reason
    tag.reviewed_by = reviewer_id
    tag.reviewed_at = datetime.now(timezone.utc).isoformat()

    project = Project.query.get(tag.project_id)
    if project:
        notif = Notification(
            user_id=project.created_by,
            type="tag_rejected",
            message=f"Collaboration tag '{tag.name}' for project '{project.name}' was rejected: {reason}",
            link=f"/projects/{project.slug}",
        )
        db.session.add(notif)

    db.session.commit()

    record_audit_log(
        user_id=reviewer_id,
        action="collaboration_tag_rejected",
        target_type="collaboration_tag",
        target_id=str(tag.id),
        details=f"Rejected tag '{tag.name}' on project_id {tag.project_id}. Reason: {reason}",
    )


def list_collaboration_tags(project_id: int, approved_only: bool = True) -> list[dict]:
    query = CollaborationTag.query.filter_by(project_id=project_id)
    if approved_only:
        query = query.filter_by(status="approved")
    tags = query.order_by(CollaborationTag.created_at).all()
    return [t.to_dict() for t in tags]


def record_verified_contribution(
    project_id: int, user_id: int, activity_type: str, points: int, verified_by: int, details: str = ""
) -> ContributionLog:
    project = Project.query.get(project_id)
    if not project:
        raise ProjectError("Project not found.")
    user = User.query.get(user_id)
    if not user:
        raise ProjectError("User not found.")

    contrib = ContributionLog(
        user_id=user_id,
        project_id=project_id,
        activity_type=activity_type.strip(),
        points=points,
    )
    db.session.add(contrib)

    # Notify contributor
    notif = Notification(
        user_id=user_id,
        type="contribution_verified",
        message=f"Your verified contribution ({activity_type.replace('_', ' ')}) on '{project.name}' was recorded (+{points} pts)!",
        link=f"/projects/{project.slug}/people",
    )
    db.session.add(notif)
    db.session.commit()

    record_audit_log(
        user_id=verified_by,
        action="contribution_verified",
        target_type="project",
        target_id=str(project_id),
        details=f"Verified contribution '{activity_type}' (+{points} pts) for user {user.full_name}: {details}",
    )
    return contrib


def get_project_people_and_contributions(project_id: int) -> dict:
    project = Project.query.get(project_id)
    if not project:
        raise ProjectError("Project not found.")

    # Team members
    members = (
        db.session.query(
            User.id,
            User.full_name,
            User.email,
            User.role.label("platform_role"),
            ProjectMember.role.label("project_role"),
            ProjectMember.joined_at,
        )
        .join(User, User.id == ProjectMember.user_id)
        .filter(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.joined_at)
        .all()
    )

    # Assigned active mentors
    assigned_mentors = (
        db.session.query(
            User.id,
            User.full_name,
            User.email,
            MentorshipRequest.status,
            MentorshipRequest.created_at,
        )
        .join(User, User.id == MentorshipRequest.mentor_id)
        .filter(MentorshipRequest.project_id == project_id, MentorshipRequest.status == "accepted")
        .all()
    )

    # Verified contributions
    contributions = (
        db.session.query(
            ContributionLog.id,
            ContributionLog.user_id,
            ContributionLog.activity_type,
            ContributionLog.points,
            ContributionLog.created_at,
            User.full_name.label("user_name"),
            User.email.label("user_email"),
        )
        .join(User, User.id == ContributionLog.user_id)
        .filter(ContributionLog.project_id == project_id)
        .order_by(ContributionLog.created_at.desc())
        .all()
    )

    # Explicit access grants
    access_grants = list_source_code_grants(project_id)

    return {
        "project": project,
        "members": [dict(m._mapping) for m in members],
        "assigned_mentors": [dict(m._mapping) for m in assigned_mentors],
        "contributions": [dict(c._mapping) for c in contributions],
        "access_grants": access_grants,
    }