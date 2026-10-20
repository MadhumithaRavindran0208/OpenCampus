"""
Club and Club Membership models.
"""
from __future__ import annotations

from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db


class Club(db.Model):
    __tablename__ = "clubs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    admin_secret_code_hash = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(50), nullable=False, default="approved")  # pending|approved|rejected
    created_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())

    def set_secret_code(self, secret_code: str) -> None:
        self.admin_secret_code_hash = generate_password_hash(secret_code.strip())

    def verify_secret_code(self, secret_code: str) -> bool:
        if not self.admin_secret_code_hash:
            return False
        return check_password_hash(self.admin_secret_code_hash, secret_code.strip())

    def __getitem__(self, item: str):
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "created_by": self.created_by,
            "admin_id": self.admin_id,
            "status": self.status,
            "created_at": self.created_at,
        }


class ClubMember(db.Model):
    __tablename__ = "club_members"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    club_id = db.Column(db.Integer, db.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="member")  # member|admin
    joined_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())

    __table_args__ = (
        db.UniqueConstraint("club_id", "user_id", name="uq_club_user"),
    )

    def __getitem__(self, item: str):
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)
