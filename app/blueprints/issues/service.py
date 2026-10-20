"""
Issue management and discussion service using SQLAlchemy ORM.
"""
from __future__ import annotations

from datetime import datetime, timezone
from app.extensions import db
from app.core import events
from app.blueprints.projects.models import Issue, IssueComment, Project
from app.blueprints.auth.models import User


class IssueError(Exception):
    pass


def create_issue(project_id: int, title: str, description: str, difficulty: str, created_by: int) -> Issue:
    title = title.strip()
    if not title:
        raise IssueError("Issue title is required.")

    issue = Issue(
        project_id=project_id,
        title=title,
        description=description.strip(),
        difficulty=difficulty,
        created_by=created_by,
        status="open",
    )
    db.session.add(issue)
    db.session.commit()

    events.emit(events.ISSUE_CREATED, issue_id=issue.id, project_id=project_id, created_by=created_by, title=title)
    return issue


def list_issues(project_id: int, status: str = "") -> list[dict]:
    Creator = db.aliased(User)
    Assignee = db.aliased(User)

    q = (
        db.session.query(
            Issue.id,
            Issue.project_id,
            Issue.title,
            Issue.description,
            Issue.status,
            Issue.difficulty,
            Issue.created_by,
            Issue.assigned_to,
            Issue.created_at,
            Issue.updated_at,
            Assignee.full_name.label("assignee_name"),
            Creator.full_name.label("creator_name"),
        )
        .join(Creator, Creator.id == Issue.created_by)
        .outerjoin(Assignee, Assignee.id == Issue.assigned_to)
        .filter(Issue.project_id == project_id)
    )

    if status:
        q = q.filter(Issue.status == status)

    rows = q.order_by(
        db.case(
            (Issue.status == "open", 0),
            (Issue.status == "claimed", 1),
            (Issue.status == "in_review", 2),
            else_=3,
        ),
        Issue.created_at.desc(),
    ).all()

    return [dict(r._mapping) for r in rows]


def get_issue(issue_id: int) -> dict | None:
    Creator = db.aliased(User)
    Assignee = db.aliased(User)

    row = (
        db.session.query(
            Issue.id,
            Issue.project_id,
            Issue.title,
            Issue.description,
            Issue.status,
            Issue.difficulty,
            Issue.created_by,
            Issue.assigned_to,
            Issue.created_at,
            Issue.updated_at,
            Assignee.full_name.label("assignee_name"),
            Creator.full_name.label("creator_name"),
            Project.name.label("project_name"),
            Project.slug.label("project_slug"),
        )
        .join(Creator, Creator.id == Issue.created_by)
        .outerjoin(Assignee, Assignee.id == Issue.assigned_to)
        .join(Project, Project.id == Issue.project_id)
        .filter(Issue.id == issue_id)
        .first()
    )
    return dict(row._mapping) if row else None


def get_comments(issue_id: int) -> list[dict]:
    rows = (
        db.session.query(
            IssueComment.id,
            IssueComment.issue_id,
            IssueComment.user_id,
            IssueComment.body,
            IssueComment.created_at,
            User.full_name,
        )
        .join(User, User.id == IssueComment.user_id)
        .filter(IssueComment.issue_id == issue_id)
        .order_by(IssueComment.created_at.asc())
        .all()
    )
    return [dict(r._mapping) for r in rows]


def add_comment(issue_id: int, user_id: int, body: str) -> None:
    body = body.strip()
    if not body:
        raise IssueError("Comment cannot be empty.")
    comment = IssueComment(issue_id=issue_id, user_id=user_id, body=body)
    db.session.add(comment)
    db.session.commit()


def claim_issue(issue_id: int, user_id: int) -> None:
    issue = Issue.query.get(issue_id)
    if issue is None:
        raise IssueError("Issue not found.")
    if issue.status != "open":
        raise IssueError("This issue has already been claimed.")

    issue.status = "claimed"
    issue.assigned_to = user_id
    issue.updated_at = datetime.now(timezone.utc).isoformat()
    db.session.commit()

    events.emit(events.ISSUE_CLAIMED, issue_id=issue.id, project_id=issue.project_id, claimed_by=user_id, title=issue.title)


def update_status(issue_id: int, status: str, actor_id: int) -> None:
    issue = Issue.query.get(issue_id)
    if issue is None:
        raise IssueError("Issue not found.")

    prev_status = issue.status
    issue.status = status
    issue.updated_at = datetime.now(timezone.utc).isoformat()
    db.session.commit()

    if status in ("done", "closed") and prev_status not in ("done", "closed"):
        events.emit(
            events.ISSUE_CLOSED,
            issue_id=issue.id,
            project_id=issue.project_id,
            closed_by=actor_id,
            title=issue.title,
            assigned_to=issue.assigned_to,
        )
