"""
Document service using SQLAlchemy ORM.
"""
from __future__ import annotations

from datetime import datetime, timezone
from app.extensions import db
from app.core import events
from app.core.utils import slugify
from app.blueprints.docs.models import Document


class DocError(Exception):
    pass


def create_document(project_id: int, title: str, content_md: str, doc_type: str, created_by: int) -> Document:
    title = title.strip()
    if not title:
        raise DocError("Document title is required.")
    slug = slugify(title)

    existing = Document.query.filter_by(project_id=project_id, slug=slug).first()
    if existing:
        raise DocError("A document with a similar title already exists for this project.")

    doc = Document(
        project_id=project_id,
        title=title,
        slug=slug,
        content_md=content_md,
        doc_type=doc_type,
        created_by=created_by,
    )
    db.session.add(doc)
    db.session.commit()

    events.emit(events.DOCUMENT_PUBLISHED, document_id=doc.id, project_id=project_id, created_by=created_by, title=title)
    return doc


def list_documents(project_id: int) -> list[dict]:
    docs = (
        Document.query.filter_by(project_id=project_id)
        .order_by(
            db.case(
                (Document.doc_type == "readme", 0),
                (Document.doc_type == "onboarding", 1),
                else_=2,
            ),
            Document.title,
        )
        .all()
    )
    return [d.to_dict() for d in docs]


def get_document(project_id: int, slug: str) -> Document | None:
    return Document.query.filter_by(project_id=project_id, slug=slug).first()


def update_document(doc_id: int, content_md: str) -> None:
    doc = Document.query.get(doc_id)
    if doc:
        doc.content_md = content_md
        doc.updated_at = datetime.now(timezone.utc).isoformat()
        db.session.commit()
