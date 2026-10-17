"""Small helpers shared across blueprints. Keep this file boring on purpose."""
from __future__ import annotations

import re
import secrets

from app.core import db


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or secrets.token_hex(4)


def unique_slug(text: str, table: str, exclude_id: int | None = None) -> str:
    """Slugify text, then disambiguate with -2, -3, ... if it collides."""
    base = slugify(text)
    slug = base
    n = 2
    while True:
        row = db.query_one(f"SELECT id FROM {table} WHERE slug = ?", (slug,))
        if row is None or (exclude_id is not None and row["id"] == exclude_id):
            return slug
        slug = f"{base}-{n}"
        n += 1


def notify(user_id: int, message: str, notif_type: str = "general", link: str = "") -> None:
    """Create a notification row. Subscribed to events.py -- see listeners.py."""
    db.execute(
        "INSERT INTO notifications (user_id, type, message, link) VALUES (?, ?, ?, ?)",
        (user_id, notif_type, message, link),
    )


def notify_bulk(id_expr: str, from_where_clause: str, from_where_params: tuple, message: str, notif_type: str, link: str = "") -> int:
    """Notify every user returned by a SELECT, in one INSERT...SELECT
    statement instead of looping and inserting one row per recipient
    (an N+1 query pattern that shows up fast once a club or the whole
    platform is the audience, e.g. an announcement).

    id_expr: the column/expression that yields the recipient's user id
        for the FROM clause given (e.g. "id" for `users`, "user_id" for
        `club_members`).
    from_where_clause: a trusted, hardcoded SQL fragment starting with
        FROM (e.g. "FROM users WHERE is_active = 1") -- never build this
        from user input, exactly like every other f-string-composed
        query in this codebase (see db.py, admin/service.py).
    from_where_params: parameters for any `?` placeholders inside
        from_where_clause.

    Returns the number of notifications inserted.
    """
    sql = f"INSERT INTO notifications (user_id, type, message, link) SELECT {id_expr}, ?, ?, ? {from_where_clause}"
    conn = db.get_db()
    cur = conn.execute(sql, (notif_type, message, link, *from_where_params))
    conn.commit()
    return cur.rowcount


def log_contribution(user_id: int, activity_type: str, project_id: int | None = None, points: int = 1) -> None:
    db.execute(
        "INSERT INTO contribution_log (user_id, project_id, activity_type, points) VALUES (?, ?, ?, ?)",
        (user_id, project_id, activity_type, points),
    )


def paginate(page: int, page_size: int) -> tuple[int, int]:
    """Returns (limit, offset) with sane defaults for invalid input."""
    page = max(page, 1)
    page_size = max(1, min(page_size, 100))
    return page_size, (page - 1) * page_size