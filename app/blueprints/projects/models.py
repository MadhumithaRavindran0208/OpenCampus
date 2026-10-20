"""
Project, Member, Issue, Mentorship and Transfer models.
"""
from __future__ import annotations

from datetime import datetime, timezone
from app.extensions import db


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    club_id = db.Column(db.Integer, db.ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, default="")
    tech_stack = db.Column(db.Text, default="")
    repo_url = db.Column(db.String(255), default="")
    difficulty = db.Column(db.String(50), nullable=False, default="beginner")
    status = db.Column(db.String(50), nullable=False, default="active")
    is_seeking_contributors = db.Column(db.Integer, nullable=False, default=0)
    required_skills = db.Column(db.Text, default="")
    looking_for = db.Column(db.Text, default="")
    source_code_restricted = db.Column(db.Integer, nullable=False, default=1)
    readme = db.Column(db.Text, default="")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat(), onupdate=lambda: datetime.now(timezone.utc).isoformat())

    def __getitem__(self, item: str):
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "club_id": self.club_id,
            "name": self.name,
            "slug": self.slug,
            "description": self.description,
            "tech_stack": self.tech_stack,
            "repo_url": self.repo_url,
            "difficulty": self.difficulty,
            "status": self.status,
            "is_seeking_contributors": self.is_seeking_contributors,
            "required_skills": self.required_skills,
            "looking_for": self.looking_for,
            "source_code_restricted": self.source_code_restricted,
            "readme": self.readme,
            "created_by": self.created_by,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class ProjectMember(db.Model):
    __tablename__ = "project_members"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = db.Column(db.String(50), nullable=False, default="contributor")  # owner|maintainer|contributor
    joined_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())

    __table_args__ = (
        db.UniqueConstraint("project_id", "user_id", name="uq_project_user"),
    )

    def __getitem__(self, item: str):
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)


class Issue(db.Model):
    __tablename__ = "issues"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, default="")
    status = db.Column(db.String(50), nullable=False, default="open")  # open|claimed|in_review|done|closed
    difficulty = db.Column(db.String(50), nullable=False, default="beginner")
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    assigned_to = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())

    def __getitem__(self, item: str):
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "difficulty": self.difficulty,
            "created_by": self.created_by,
            "assigned_to": self.assigned_to,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class IssueComment(db.Model):
    __tablename__ = "issue_comments"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    issue_id = db.Column(db.Integer, db.ForeignKey("issues.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())

    def __getitem__(self, item: str):
        return getattr(self, item)


class MentorshipRequest(db.Model):
    __tablename__ = "mentorship_requests"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    mentor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    message = db.Column(db.Text, default="")
    status = db.Column(db.String(50), nullable=False, default="pending")  # pending|accepted|declined|completed
    created_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())
    updated_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())

    def __getitem__(self, item: str):
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)


class OwnershipTransfer(db.Model):
    __tablename__ = "ownership_transfers"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    from_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    to_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(50), nullable=False, default="pending")  # pending|accepted|rejected
    created_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at = db.Column(db.String(50), nullable=True)

    def __getitem__(self, item: str):
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)


class ProjectAccessGrant(db.Model):
    __tablename__ = "project_access_grants"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    granted_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())

    __table_args__ = (
        db.UniqueConstraint("project_id", "user_id", name="uq_project_access_user"),
    )

    def __getitem__(self, item: str):
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "user_id": self.user_id,
            "granted_by": self.granted_by,
            "created_at": self.created_at,
        }


class CollaborationTag(db.Model):
    __tablename__ = "collaboration_tags"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), nullable=False, default="pending")  # pending|approved|rejected
    reviewed_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    rejection_reason = db.Column(db.Text, default="")
    created_at = db.Column(db.String(50), default=lambda: datetime.now(timezone.utc).isoformat())
    reviewed_at = db.Column(db.String(50), nullable=True)

    def __getitem__(self, item: str):
        return getattr(self, item)

    def get(self, item: str, default=None):
        return getattr(self, item, default)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "status": self.status,
            "reviewed_by": self.reviewed_by,
            "rejection_reason": self.rejection_reason,
            "created_at": self.created_at,
            "reviewed_at": self.reviewed_at,
        }
