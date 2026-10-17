from __future__ import annotations

from app.core import db, events


def list_recent_announcements(limit: int = 20) -> list[dict]:
    return db.query(
        """SELECT a.*, u.full_name AS author_name, c.name AS club_name
           FROM announcements a JOIN users u ON u.id = a.created_by
           LEFT JOIN clubs c ON c.id = a.club_id
           ORDER BY a.created_at DESC LIMIT ?""",
        (limit,),
    )


def post_announcement(title: str, body: str, created_by: int, club_id: int | None = None) -> dict:
    ann_id = db.execute(
        "INSERT INTO announcements (club_id, title, body, created_by) VALUES (?, ?, ?, ?)",
        (club_id, title.strip(), body.strip(), created_by),
    )
    events.emit(events.ANNOUNCEMENT_POSTED, announcement_id=ann_id, club_id=club_id, title=title)
    return db.query_one("SELECT * FROM announcements WHERE id = ?", (ann_id,))
