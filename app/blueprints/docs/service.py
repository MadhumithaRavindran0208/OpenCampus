from __future__ import annotations

from app.core import db, events
from app.core.utils import slugify


class DocError(Exception):
    pass


def create_document(project_id: int, title: str, content_md: str, doc_type: str, created_by: int) -> dict:
    title = title.strip()
    if not title:
        raise DocError("Document title is required.")
    slug = slugify(title)
    existing = db.query_one("SELECT id FROM documents WHERE project_id = ? AND slug = ?", (project_id, slug))
    if existing:
        raise DocError("A document with a similar title already exists for this project.")
    doc_id = db.execute(
        "INSERT INTO documents (project_id, title, slug, content_md, doc_type, created_by) VALUES (?, ?, ?, ?, ?, ?)",
        (project_id, title, slug, content_md, doc_type, created_by),
    )
    events.emit(events.DOCUMENT_PUBLISHED, document_id=doc_id, project_id=project_id, created_by=created_by, title=title)
    return db.query_one("SELECT * FROM documents WHERE id = ?", (doc_id,))


def list_documents(project_id: int) -> list[dict]:
    return db.query(
        "SELECT * FROM documents WHERE project_id = ? ORDER BY CASE doc_type WHEN 'readme' THEN 0 WHEN 'onboarding' THEN 1 ELSE 2 END, title",
        (project_id,),
    )


def get_document(project_id: int, slug: str) -> dict | None:
    return db.query_one("SELECT * FROM documents WHERE project_id = ? AND slug = ?", (project_id, slug))


def update_document(doc_id: int, content_md: str) -> None:
    db.execute(
        "UPDATE documents SET content_md = ?, updated_at = datetime('now') WHERE id = ?", (content_md, doc_id)
    )
