"""
User authentication and profile model.
"""
from __future__ import annotations

from datetime import datetime, timezone
from flask_login import UserMixin
from app.extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="student")  # student|mentor|club_admin|platform_admin
    bio = db.Column(db.Text, default="")
    skills = db.Column(db.Text, default="")
    is_active = db.Column(db.Integer, nullable=False, default=1)
    is_verified = db.Column(db.Integer, nullable=False, default=0)
    verification_token = db.Column(db.String(255), default="")
    age_category = db.Column(db.String(50), default="")
    contact_email = db.Column(db.String(255), default="")
    discord_handle = db.Column(db.String(255), default="")
    linkedin_url = db.Column(db.String(255), default="")
    github_url = db.Column(db.String(255), default="")
    created_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())

    def get_id(self) -> str:
        return str(self.id)

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    def __getitem__(self, item: str):
        """Enable dictionary-like access (e.g. user['role']) for backward-compatibility."""
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "email": self.email,
            "full_name": self.full_name,
            "role": self.role,
            "bio": self.bio,
            "skills": self.skills,
            "is_active": self.is_active,
            "is_verified": self.is_verified,
            "age_category": self.age_category,
            "contact_email": self.contact_email,
            "discord_handle": self.discord_handle,
            "linkedin_url": self.linkedin_url,
            "github_url": self.github_url,
            "created_at": self.created_at,
        }


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(50), nullable=True)
    target_id = db.Column(db.String(100), nullable=True)
    details = db.Column(db.Text, default="")
    ip_address = db.Column(db.String(100), default="")
    created_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())

    def __getitem__(self, item: str):
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "created_at": self.created_at,
        }
