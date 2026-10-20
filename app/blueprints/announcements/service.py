"""
Announcement service using SQLAlchemy ORM.
"""
from __future__ import annotations

from app.extensions import db
from app.core import events
from app.blueprints.announcements.models import Announcement
from app.blueprints.auth.models import User
from app.blueprints.clubs.models import Club


def list_recent_announcements(limit: int = 20) -> list[dict]:
    rows = (
        db.session.query(
            Announcement.id,
            Announcement.club_id,
            Announcement.title,
            Announcement.body,
            Announcement.created_by,
            Announcement.created_at,
            User.full_name.label("author_name"),
            Club.name.label("club_name"),
        )
        .join(User, User.id == Announcement.created_by)
        .outerjoin(Club, Club.id == Announcement.club_id)
        .order_by(Announcement.created_at.desc())
        .limit(limit)
        .all()
    )
    return [dict(r._mapping) for r in rows]


def post_announcement(title: str, body: str, created_by: int, club_id: int | None = None) -> Announcement:
    ann = Announcement(
        club_id=club_id,
        title=title.strip(),
        body=body.strip(),
        created_by=created_by,
    )
    db.session.add(ann)
    db.session.commit()

    events.emit(events.ANNOUNCEMENT_POSTED, announcement_id=ann.id, club_id=club_id, title=title)
    return ann
