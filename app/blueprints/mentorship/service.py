"""
Mentorship request and matching service using SQLAlchemy ORM.
"""
from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import or_
from app.extensions import db
from app.core import events
from app.blueprints.projects.models import MentorshipRequest, Project, ProjectMember
from app.blueprints.auth.models import User


class MentorshipError(Exception):
    pass


def request_mentorship(project_id: int, student_id: int, message: str, mentor_id: int | None = None) -> MentorshipRequest:
    existing = MentorshipRequest.query.filter(
        MentorshipRequest.project_id == project_id,
        MentorshipRequest.student_id == student_id,
        MentorshipRequest.status.in_(["pending", "accepted"]),
    ).first()
    if existing:
        raise MentorshipError("You already have an active mentorship request for this project.")

    req = MentorshipRequest(
        project_id=project_id,
        student_id=student_id,
        mentor_id=mentor_id,
        message=message.strip(),
        status="pending",
    )
    db.session.add(req)
    db.session.commit()

    events.emit(events.MENTORSHIP_REQUESTED, request_id=req.id, project_id=project_id, student_id=student_id, mentor_id=mentor_id)
    return req


def list_for_student(student_id: int) -> list[dict]:
    Mentor = db.aliased(User)
    rows = (
        db.session.query(
            MentorshipRequest.id,
            MentorshipRequest.project_id,
            MentorshipRequest.student_id,
            MentorshipRequest.mentor_id,
            MentorshipRequest.message,
            MentorshipRequest.status,
            MentorshipRequest.created_at,
            MentorshipRequest.updated_at,
            Project.name.label("project_name"),
            Project.slug.label("project_slug"),
            Mentor.full_name.label("mentor_name"),
        )
        .join(Project, Project.id == MentorshipRequest.project_id)
        .outerjoin(Mentor, Mentor.id == MentorshipRequest.mentor_id)
        .filter(MentorshipRequest.student_id == student_id)
        .order_by(MentorshipRequest.created_at.desc())
        .all()
    )
    return [dict(r._mapping) for r in rows]


def list_for_mentor_pool(mentor_id: int) -> list[dict]:
    Student = db.aliased(User)

    maintained_project_ids = (
        db.select(ProjectMember.project_id)
        .where(
            ProjectMember.user_id == mentor_id,
            ProjectMember.role.in_(["owner", "maintainer"]),
        )
    )

    rows = (
        db.session.query(
            MentorshipRequest.id,
            MentorshipRequest.project_id,
            MentorshipRequest.student_id,
            MentorshipRequest.mentor_id,
            MentorshipRequest.message,
            MentorshipRequest.status,
            MentorshipRequest.created_at,
            MentorshipRequest.updated_at,
            Project.name.label("project_name"),
            Project.slug.label("project_slug"),
            Student.full_name.label("student_name"),
        )
        .join(Project, Project.id == MentorshipRequest.project_id)
        .join(Student, Student.id == MentorshipRequest.student_id)
        .filter(
            or_(
                MentorshipRequest.mentor_id == mentor_id,
                (
                    (MentorshipRequest.status == "pending")
                    & (MentorshipRequest.project_id.in_(maintained_project_ids))
                ),
            )
        )
        .order_by(MentorshipRequest.created_at.desc())
        .all()
    )
    return [dict(r._mapping) for r in rows]


def cancel_request(request_id: int, student_id: int) -> None:
    req = MentorshipRequest.query.get(request_id)
    if req is None:
        raise MentorshipError("Request not found.")
    if req.student_id != student_id:
        raise MentorshipError("You can only cancel your own requests.")
    if req.status != "pending":
        raise MentorshipError("Only pending requests can be cancelled.")
    req.status = "cancelled"
    req.updated_at = datetime.now(timezone.utc).isoformat()
    db.session.commit()


def accept_request(request_id: int, mentor_id: int) -> None:
    req = MentorshipRequest.query.get(request_id)
    if req is None or req.status != "pending":
        raise MentorshipError("This request is no longer pending.")

    req.status = "accepted"
    req.mentor_id = mentor_id
    req.updated_at = datetime.now(timezone.utc).isoformat()
    db.session.commit()

    events.emit(events.MENTORSHIP_ACCEPTED, request_id=req.id, student_id=req.student_id, mentor_id=mentor_id)


def decline_request(request_id: int) -> None:
    req = MentorshipRequest.query.get(request_id)
    if req:
        req.status = "declined"
        req.updated_at = datetime.now(timezone.utc).isoformat()
        db.session.commit()


def complete_request(request_id: int) -> None:
    req = MentorshipRequest.query.get(request_id)
    if req is None or req.status != "accepted":
        raise MentorshipError("Only accepted mentorships can be marked complete.")

    req.status = "completed"
    req.updated_at = datetime.now(timezone.utc).isoformat()
    db.session.commit()

    events.emit(events.MENTORSHIP_COMPLETED, request_id=req.id, student_id=req.student_id, mentor_id=req.mentor_id)
