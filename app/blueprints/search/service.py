"""
Unified search service using SQLAlchemy ORM.
"""
from __future__ import annotations

from sqlalchemy import or_
from app.extensions import db
from app.blueprints.projects.models import Project, Issue
from app.blueprints.clubs.models import Club
from app.blueprints.docs.models import Document


def unified_search(query: str, limit: int = 25) -> dict:
    if not query.strip():
        return {"projects": [], "issues": [], "docs": [], "clubs": []}
    like = f"%{query}%"

    project_rows = (
        db.session.query(
            Project.id,
            Project.name,
            Project.slug,
            Project.description,
            Club.slug.label("club_slug"),
        )
        .join(Club, Club.id == Project.club_id)
        .filter(
            or_(
                Project.name.ilike(like),
                Project.description.ilike(like),
                Project.tech_stack.ilike(like),
            )
        )
        .limit(limit)
        .all()
    )

    issue_rows = (
        db.session.query(
            Issue.id,
            Issue.title,
            Issue.status,
            Project.slug.label("project_slug"),
            Project.name.label("project_name"),
        )
        .join(Project, Project.id == Issue.project_id)
        .filter(or_(Issue.title.ilike(like), Issue.description.ilike(like)))
        .limit(limit)
        .all()
    )

    doc_rows = (
        db.session.query(
            Document.id,
            Document.title,
            Document.slug.label("doc_slug"),
            Project.slug.label("project_slug"),
            Project.name.label("project_name"),
        )
        .join(Project, Project.id == Document.project_id)
        .filter(or_(Document.title.ilike(like), Document.content_md.ilike(like)))
        .limit(limit)
        .all()
    )

    club_rows = (
        db.session.query(
            Club.id,
            Club.name,
            Club.slug,
            Club.description,
        )
        .filter(or_(Club.name.ilike(like), Club.description.ilike(like)))
        .limit(limit)
        .all()
    )

    return {
        "projects": [dict(r._mapping) for r in project_rows],
        "issues": [dict(r._mapping) for r in issue_rows],
        "docs": [dict(r._mapping) for r in doc_rows],
        "clubs": [dict(r._mapping) for r in club_rows],
    }
