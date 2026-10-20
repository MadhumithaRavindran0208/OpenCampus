"""
User notification listing and status routes using SQLAlchemy ORM.
"""
from __future__ import annotations

from flask import Blueprint, render_template, redirect, url_for, g
from flask_login import login_required, current_user
from app.extensions import db
from app.blueprints.notifications.models import Notification

bp = Blueprint("notifications", __name__, url_prefix="/notifications")


@bp.route("/")
@login_required
def index():
    user_id = current_user.id
    notifications = (
        Notification.query.filter_by(user_id=user_id)
        .order_by(Notification.created_at.desc())
        .limit(50)
        .all()
    )
    # Mark unread notifications as read
    Notification.query.filter_by(user_id=user_id, is_read=0).update({"is_read": 1})
    db.session.commit()
    return render_template("notifications/index.html", notifications=notifications)


@bp.route("/<int:notification_id>/open")
@login_required
def open_notification(notification_id: int):
    user_id = current_user.id
    notif = Notification.query.filter_by(id=notification_id, user_id=user_id).first()
    if notif is None:
        return redirect(url_for("notifications.index"))

    notif.is_read = 1
    db.session.commit()
    return redirect(notif.link or url_for("notifications.index"))
