"""
Announcement model.
"""
from __future__ import annotations

from datetime import datetime, timezone
from app.extensions import db


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    club_id = db.Column(db.Integer, db.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=True)
    title = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())

    def __getitem__(self, item: str):
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "club_id": self.club_id,
            "title": self.title,
            "body": self.body,
            "created_by": self.created_by,
            "created_at": self.created_at,
        }
