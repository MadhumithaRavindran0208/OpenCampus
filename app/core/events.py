"""
Minimal pub/sub event bus.

This is the mechanism behind the Product Bible's "modules exchange data
through clearly defined interfaces" principle. When something happens
(an issue is claimed, a mentorship request comes in), the module that
caused it just emits an event. It doesn't need to know who's listening.

Today, notifications.listeners and analytics (contribution_log) are the
subscribers. Tomorrow, if you add e.g. an email digest module, you
subscribe it here -- you never touch issues/service.py or
mentorship/service.py again. That's the "alter without rebuilding"
property this project asks for.

Kept process-local and synchronous on purpose: no broker, no queue,
nothing to deploy. If this ever needs to survive process restarts or
scale across workers, swap emit()/subscribe() for a real queue (Redis
Streams, RQ, Celery) behind this same two-function interface.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Callable

logger = logging.getLogger("opencampus.events")

_subscribers: dict[str, list[Callable]] = defaultdict(list)


def subscribe(event_name: str, handler: Callable) -> None:
    _subscribers[event_name].append(handler)


def reset_subscribers() -> None:
    """Clear all subscriptions. Called at app startup so that creating more
    than one app in the same process (every test does this) doesn't cause
    handlers to fire multiple times per event -- see listeners.register_all()."""
    _subscribers.clear()


def emit(event_name: str, **payload) -> None:
    """Call every subscriber for event_name. Each handler is isolated in
    its own try/except: a bug in one listener (or a third-party service
    it talks to failing) is logged and skipped, never allowed to stop
    the remaining subscribers from running or to propagate back into
    the request/transaction that triggered the event. A notification
    system falling over must never take down issue creation with it."""
    for handler in _subscribers.get(event_name, []):
        try:
            handler(**payload)
        except Exception:  # noqa: BLE001 -- deliberately broad: isolate every handler from every other
            logger.exception(
                "Event handler %r failed while handling %r",
                getattr(handler, "__name__", handler), event_name,
            )


# --- Canonical event names used across the platform ---
# Keeping these as constants avoids typo'd string mismatches between
# the emitting module and the subscribing module.
USER_REGISTERED = "user.registered"
PROJECT_CREATED = "project.created"
ISSUE_CREATED = "issue.created"
ISSUE_CLAIMED = "issue.claimed"
ISSUE_CLOSED = "issue.closed"
DOCUMENT_PUBLISHED = "document.published"
MENTORSHIP_REQUESTED = "mentorship.requested"
MENTORSHIP_ACCEPTED = "mentorship.accepted"
MENTORSHIP_COMPLETED = "mentorship.completed"
OWNERSHIP_TRANSFER_REQUESTED = "ownership_transfer.requested"
OWNERSHIP_TRANSFER_RESOLVED = "ownership_transfer.resolved"
ANNOUNCEMENT_POSTED = "announcement.posted"
CLUB_SUBMITTED = "club.submitted"
CLUB_APPROVED = "club.approved"
CLUB_REJECTED = "club.rejected"