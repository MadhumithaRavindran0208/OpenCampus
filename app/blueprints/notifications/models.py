"""
Notification and Contribution Log models.
"""
from __future__ import annotations

from datetime import datetime, timezone
from app.extensions import db


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = db.Column(db.String(50), nullable=False)
    message = db.Column(db.Text, nullable=False)
    link = db.Column(db.String(255), default="")
    is_read = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())

    def __getitem__(self, item: str):
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "type": self.type,
            "message": self.message,
            "link": self.link,
            "is_read": self.is_read,
            "created_at": self.created_at,
        }


class ContributionLog(db.Model):
    __tablename__ = "contribution_log"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    activity_type = db.Column(db.String(100), nullable=False)  # issue_closed|doc_added|mentorship_completed|project_created
    points = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())

    def __getitem__(self, item: str):
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)
