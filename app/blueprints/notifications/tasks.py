"""
Background notification and webhook tasks for Celery.
"""
from __future__ import annotations

import logging
from app.core.celery_app import celery
from app.core.dispatch import send_email, send_webhook

logger = logging.getLogger("opencampus.tasks.notifications")


def _execute_or_delay(task_func, *args, **kwargs):
    """Run via celery .delay() if Celery is available, else execute directly."""
    if celery is not None:
        try:
            return task_func.delay(*args, **kwargs)
        except Exception as exc:
            logger.warning("Celery enqueue failed (%s); running synchronously", exc)
    return task_func(*args, **kwargs)


if celery is not None:
    @celery.task(name="notifications.send_email_notification", bind=True, max_retries=3)
    def send_email_notification(self, to_addr: str, subject: str, message: str):
        try:
            return send_email(to_addr, subject, message)
        except Exception as exc:
            raise self.retry(exc=exc, countdown=5 * (2 ** self.request.retries))

    @celery.task(name="notifications.send_webhook_event", bind=True, max_retries=3)
    def send_webhook_event(self, event_name: str, payload: dict):
        try:
            return send_webhook(event_name, payload)
        except Exception as exc:
            raise self.retry(exc=exc, countdown=5 * (2 ** self.request.retries))

    @celery.task(name="notifications.create_in_app_notification")
    def create_in_app_notification_task(user_id: int, notif_type: str, message: str, link: str = ""):
        from app.extensions import db
        from app.blueprints.notifications.models import Notification
        from app.core.sse import push_event

        notif = Notification(user_id=user_id, type=notif_type, message=message, link=link)
        db.session.add(notif)
        db.session.commit()
        push_event(user_id, "notification", notif.to_dict())
        return notif.id
else:
    def send_email_notification(to_addr: str, subject: str, message: str):
        return send_email(to_addr, subject, message)

    def send_webhook_event(event_name: str, payload: dict):
        return send_webhook(event_name, payload)

    def create_in_app_notification_task(user_id: int, notif_type: str, message: str, link: str = ""):
        from app.extensions import db
        from app.blueprints.notifications.models import Notification
        from app.core.sse import push_event

        notif = Notification(user_id=user_id, type=notif_type, message=message, link=link)
        db.session.add(notif)
        db.session.commit()
        push_event(user_id, "notification", notif.to_dict())
        return notif.id
