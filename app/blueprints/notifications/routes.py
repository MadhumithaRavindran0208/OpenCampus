from __future__ import annotations

from flask import Blueprint, render_template, redirect, url_for, g

from app.core import db
from app.core.security import login_required

bp = Blueprint("notifications", __name__, url_prefix="/notifications")


@bp.route("/")
@login_required
def index():
    notifications = db.query(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 50", (g.user["id"],)
    )
    db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (g.user["id"],))
    return render_template("notifications/index.html", notifications=notifications)


@bp.route("/<int:notification_id>/open")
@login_required
def open_notification(notification_id: int):
    row = db.query_one(
        "SELECT * FROM notifications WHERE id = ? AND user_id = ?", (notification_id, g.user["id"])
    )
    if row is None:
        return redirect(url_for("notifications.index"))
    db.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notification_id,))
    return redirect(row["link"] or url_for("notifications.index"))
