"""
Small helpers shared across blueprints using SQLAlchemy models.
"""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from sqlalchemy import text
from app.extensions import db


def slugify(text_val: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text_val.lower()).strip("-")
    return slug or secrets.token_hex(4)


def unique_slug(text_val: str, table: str, exclude_id: int | None = None) -> str:
    """Slugify text, then disambiguate with -2, -3, ... if it collides."""
    base = slugify(text_val)
    slug = base
    n = 2
    while True:
        res = db.session.execute(
            text(f"SELECT id FROM {table} WHERE slug = :slug"),
            {"slug": slug},
        ).first()
        if res is None or (exclude_id is not None and res[0] == exclude_id):
            return slug
        slug = f"{base}-{n}"
        n += 1


def notify(user_id: int, message: str, notif_type: str = "general", link: str = "") -> None:
    """Create a notification row using SQLAlchemy model."""
    from app.blueprints.notifications.models import Notification
    notif = Notification(user_id=user_id, message=message, type=notif_type, link=link)
    db.session.add(notif)
    db.session.commit()


def notify_bulk(id_expr: str, from_where_clause: str, from_where_params: tuple, message: str, notif_type: str, link: str = "") -> int:
    """Notify every user returned by a SELECT statement."""
    # Convert positional params for SQLAlchemy text
    params_dict = {"notif_type": notif_type, "message": message, "link": link}
    sql_clause = from_where_clause
    if "?" in sql_clause:
        for idx, val in enumerate(from_where_params):
            param_key = f"p_{idx}"
            sql_clause = sql_clause.replace("?", f":{param_key}", 1)
            params_dict[param_key] = val

    params_dict["created_at"] = datetime.now(timezone.utc).isoformat()
    # is_read / created_at are NOT NULL-safe here: raw SQL bypasses the ORM column defaults.
    sql = (
        "INSERT INTO notifications (user_id, type, message, link, is_read, created_at) "
        f"SELECT {id_expr}, :notif_type, :message, :link, 0, :created_at {sql_clause}"
    )
    res = db.session.execute(text(sql), params_dict)
    db.session.commit()
    return getattr(res, "rowcount", 0)


def log_contribution(user_id: int, activity_type: str, project_id: int | None = None, points: int = 1) -> None:
    from app.blueprints.notifications.models import ContributionLog
    entry = ContributionLog(
        user_id=user_id,
        project_id=project_id,
        activity_type=activity_type,
        points=points,
    )
    db.session.add(entry)
    db.session.commit()


def paginate(page: int, page_size: int) -> tuple[int, int]:
    page = max(page, 1)
    page_size = max(1, min(page_size, 100))
    return page_size, (page - 1) * page_size