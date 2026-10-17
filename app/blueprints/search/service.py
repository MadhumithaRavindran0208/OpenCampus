from __future__ import annotations

from app.core import db


def unified_search(query: str, limit: int = 25) -> dict:
    if not query.strip():
        return {"projects": [], "issues": [], "docs": [], "clubs": []}
    like = f"%{query}%"

    projects = db.query(
        """SELECT p.id, p.name, p.slug, p.description, c.slug AS club_slug
           FROM projects p JOIN clubs c ON c.id = p.club_id
           WHERE p.name LIKE ? OR p.description LIKE ? OR p.tech_stack LIKE ? LIMIT ?""",
        (like, like, like, limit),
    )
    issues = db.query(
        """SELECT i.id, i.title, i.status, p.slug AS project_slug, p.name AS project_name
           FROM issues i JOIN projects p ON p.id = i.project_id
           WHERE i.title LIKE ? OR i.description LIKE ? LIMIT ?""",
        (like, like, limit),
    )
    docs = db.query(
        """SELECT d.id, d.title, d.slug AS doc_slug, p.slug AS project_slug, p.name AS project_name
           FROM documents d JOIN projects p ON p.id = d.project_id
           WHERE d.title LIKE ? OR d.content_md LIKE ? LIMIT ?""",
        (like, like, limit),
    )
    clubs = db.query(
        "SELECT id, name, slug, description FROM clubs WHERE name LIKE ? OR description LIKE ? LIMIT ?",
        (like, like, limit),
    )
    return {"projects": projects, "issues": issues, "docs": docs, "clubs": clubs}
