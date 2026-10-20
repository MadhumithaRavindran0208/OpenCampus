"""
Project Document model.
"""
from __future__ import annotations

from datetime import datetime, timezone
from app.extensions import db


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), nullable=False)
    content_md = db.Column(db.Text, default="")
    doc_type = db.Column(db.String(50), nullable=False, default="guide")  # readme|onboarding|architecture|guide
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    updated_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())

    __table_args__ = (
        db.UniqueConstraint("project_id", "slug", name="uq_project_doc_slug"),
    )

    def __getitem__(self, item: str):
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "slug": self.slug,
            "content_md": self.content_md,
            "doc_type": self.doc_type,
            "created_by": self.created_by,
            "updated_at": self.updated_at,
        }
