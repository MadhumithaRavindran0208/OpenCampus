"""
Subscribes the notification system and contribution log to domain events.

This module is the *only* place that wires cross-cutting concerns
(notifications, contribution history) to the modules that trigger them.
To add a new reaction to an existing event, edit here -- never the
module that emits the event. To add a brand-new event, emit it from
the module, then add a handler here; nothing else changes.
"""
from __future__ import annotations

from flask import current_app

from app.core import db, events, dispatch
from app.core.utils import notify, notify_bulk, log_contribution
import app.core.sse as sse_engine


def _project_maintainers(project_id: int) -> list[int]:
    rows = db.query(
        "SELECT user_id FROM project_members WHERE project_id = ? AND role IN ('owner','maintainer')",
        (project_id,),
    )
    return [r["user_id"] for r in rows]


def _external_email(user_id: int) -> str | None:
    """Preferred outbound address: contact_email if set, else login email.
    Kept local to core (rather than importing auth/service.py) so
    app/core never depends on app/blueprints."""
    user = db.query_one("SELECT email, contact_email FROM users WHERE id = ?", (user_id,))
    if not user:
        return None
    return user["contact_email"] or user["email"]


# --- In-app notifications + contribution log ---
# These stay synchronous and in-transaction: they're a single local
# INSERT, not a network call, so there's nothing to gain from
# backgrounding them and doing so would only add complexity. Only
# email/webhook (real network I/O) are offloaded below.

def on_issue_created(issue_id: int, project_id: int, created_by: int, title: str):
    for uid in _project_maintainers(project_id):
        if uid != created_by:
            notify(uid, f'New issue opened: "{title}"', "issue_created", f"/projects/issue/{issue_id}")
            sse_engine.push_event(uid, "notification", {"type": "issue_created", "message": f'New issue opened: "{title}"', "link": f"/projects/issue/{issue_id}"})


def on_issue_claimed(issue_id: int, project_id: int, claimed_by: int, title: str):
    for uid in _project_maintainers(project_id):
        if uid != claimed_by:
            notify(uid, f'Issue claimed: "{title}"', "issue_claimed", f"/projects/issue/{issue_id}")
            sse_engine.push_event(uid, "notification", {"type": "issue_claimed", "message": f'Issue claimed: "{title}"', "link": f"/projects/issue/{issue_id}"})


def on_issue_closed(issue_id: int, project_id: int, closed_by: int, title: str, assigned_to: int | None):
    if assigned_to:
        log_contribution(assigned_to, "issue_closed", project_id, points=3)
        notify(assigned_to, f'Your issue "{title}" was marked done. Nice work!', "issue_closed", f"/projects/issue/{issue_id}")
        sse_engine.push_event(assigned_to, "notification", {"type": "issue_closed", "message": f'Your issue "{title}" was marked done. Nice work!', "link": f"/projects/issue/{issue_id}"})


def on_document_published(document_id: int, project_id: int, created_by: int, title: str):
    log_contribution(created_by, "doc_added", project_id, points=2)
    for uid in _project_maintainers(project_id):
        if uid != created_by:
            notify(uid, f'New documentation: "{title}"', "document_published", f"/projects/{project_id}/docs")
            sse_engine.push_event(uid, "notification", {"type": "document_published", "message": f'New documentation: "{title}"', "link": f"/projects/{project_id}/docs"})


def on_mentorship_requested(request_id: int, project_id: int, student_id: int, mentor_id: int | None = None):
    for uid in _project_maintainers(project_id):
        notify(uid, "A student requested mentorship on your project.", "mentorship_requested", "/mentorship/")
        sse_engine.push_event(uid, "notification", {"type": "mentorship_requested", "message": "A student requested mentorship on your project.", "link": "/mentorship/"})
    if mentor_id and mentor_id not in _project_maintainers(project_id):
        notify(mentor_id, "A student requested you as a mentor on a project.", "mentorship_requested", "/mentorship/")
        sse_engine.push_event(mentor_id, "notification", {"type": "mentorship_requested", "message": "A student requested you as a mentor on a project.", "link": "/mentorship/"})


def on_mentorship_accepted(request_id: int, student_id: int, mentor_id: int):
    notify(student_id, "Your mentorship request was accepted!", "mentorship_accepted", "/mentorship/")
    sse_engine.push_event(student_id, "notification", {"type": "mentorship_accepted", "message": "Your mentorship request was accepted!", "link": "/mentorship/"})


def on_mentorship_completed(request_id: int, student_id: int, mentor_id: int):
    log_contribution(mentor_id, "mentorship_completed", points=5)
    notify(student_id, "Your mentorship engagement was marked complete.", "mentorship_completed", "/mentorship/")
    sse_engine.push_event(student_id, "notification", {"type": "mentorship_completed", "message": "Your mentorship engagement was marked complete.", "link": "/mentorship/"})


def on_ownership_transfer_requested(transfer_id: int, project_id: int, from_user_id: int, to_user_id: int):
    notify(to_user_id, "You've been offered ownership of a project.", "ownership_transfer", "/admin/transfers")
    sse_engine.push_event(to_user_id, "notification", {"type": "ownership_transfer", "message": "You've been offered ownership of a project.", "link": "/admin/transfers"})


def on_ownership_transfer_resolved(transfer_id: int, project_id: int, from_user_id: int, status: str):
    notify(from_user_id, f"Your ownership transfer was {status}.", "ownership_transfer", "/admin/transfers")
    sse_engine.push_event(from_user_id, "notification", {"type": "ownership_transfer", "message": f"Your ownership transfer was {status}.", "link": "/admin/transfers"})


def on_announcement_posted(announcement_id: int, club_id: int | None, title: str):
    # Potentially every active user (platform-wide) or every club member
    # (club-scoped) -- one INSERT...SELECT instead of a per-recipient
    # loop, see notify_bulk()'s docstring.
    message = f'Announcement: "{title}"'
    if club_id is None:
        notify_bulk("id", "FROM users WHERE is_active = 1", (), message, "announcement", "/announcements/")
    else:
        notify_bulk("user_id", "FROM club_members WHERE club_id = ?", (club_id,), message, "announcement", "/announcements/")


def on_club_submitted(club_id: int, name: str, created_by: int):
    notify_bulk(
        "id", "FROM users WHERE role = 'platform_admin'", (),
        f'New club "{name}" is awaiting approval.', "club_submitted", "/admin/clubs",
    )


def on_club_approved(club_id: int, name: str, created_by: int):
    notify(created_by, f'Your club "{name}" was approved and is now live.', "club_approved", f"/clubs/{club_id}")


def on_club_rejected(club_id: int, name: str, created_by: int):
    notify(created_by, f'Your club "{name}" was not approved.', "club_rejected", "/clubs/")


# --- External dispatch: email for time-sensitive, personal items ---
# These are ADDED subscribers on the same events already handled above --
# the in-app notify() calls above are untouched. This is exactly the
# "add a new reaction without touching existing code" extension point
# described in ARCHITECTURE.md (ADR-003).
#
# Each handler only captures the real Flask app object (synchronously,
# while still on the request's own thread/context) and hands the actual
# work -- DB lookups AND the network call -- to dispatch.run_in_background(),
# which gives the background thread its own fresh app context (and, as
# a consequence, its own SQLite connection; see db.py). This keeps a
# slow SMTP server or an unreachable webhook endpoint from ever making
# a user wait on their click.

def _email_mentorship_requested(project_id: int, student_id: int, mentor_id: int | None = None):
    targets = set(_project_maintainers(project_id))
    if mentor_id:
        targets.add(mentor_id)
    for uid in targets:
        dispatch.send_email(
            _external_email(uid),
            "New mentorship request on your project",
            "A student has requested mentorship on one of your projects. "
            "Sign in to OpenCampus OSS to accept or decline.",
        )


def dispatch_email_mentorship_requested(request_id: int, project_id: int, student_id: int, mentor_id: int | None = None):
    app = current_app._get_current_object()
    dispatch.run_in_background(app, _email_mentorship_requested, project_id, student_id, mentor_id)


def _email_mentorship_accepted(student_id: int, mentor_id: int):
    dispatch.send_email(
        _external_email(student_id),
        "Your mentorship request was accepted",
        "Good news -- a mentor accepted your request. Sign in to see next steps.",
    )


def dispatch_email_mentorship_accepted(request_id: int, student_id: int, mentor_id: int):
    app = current_app._get_current_object()
    dispatch.run_in_background(app, _email_mentorship_accepted, student_id, mentor_id)


def _email_ownership_transfer_requested(to_user_id: int):
    dispatch.send_email(
        _external_email(to_user_id),
        "You've been offered project ownership",
        "You've been offered ownership of a project on OpenCampus OSS. "
        "Sign in to accept or decline the transfer.",
    )


def dispatch_email_ownership_transfer_requested(transfer_id: int, project_id: int, from_user_id: int, to_user_id: int):
    app = current_app._get_current_object()
    dispatch.run_in_background(app, _email_ownership_transfer_requested, to_user_id)


def _email_issue_claimed(project_id: int, claimed_by: int, title: str):
    for uid in _project_maintainers(project_id):
        if uid != claimed_by:
            dispatch.send_email(
                _external_email(uid),
                f'Issue claimed: "{title}"',
                "Sign in to OpenCampus OSS to follow progress or leave a comment.",
            )


def dispatch_email_issue_claimed(issue_id: int, project_id: int, claimed_by: int, title: str):
    app = current_app._get_current_object()
    dispatch.run_in_background(app, _email_issue_claimed, project_id, claimed_by, title)


# --- External dispatch: generic webhook relay ---
# Forwards a normalized {event, data} payload for any event in this list --
# useful for a Slack/Discord bot or an external activity feed. Add an
# event name here to start relaying it; no other code changes needed.

WEBHOOK_RELAY_EVENTS = [
    events.PROJECT_CREATED,
    events.ISSUE_CREATED,
    events.ISSUE_CLAIMED,
    events.ISSUE_CLOSED,
    events.DOCUMENT_PUBLISHED,
    events.MENTORSHIP_REQUESTED,
    events.MENTORSHIP_ACCEPTED,
    events.MENTORSHIP_COMPLETED,
    events.OWNERSHIP_TRANSFER_REQUESTED,
    events.OWNERSHIP_TRANSFER_RESOLVED,
    events.ANNOUNCEMENT_POSTED,
    events.CLUB_SUBMITTED,
    events.CLUB_APPROVED,
    events.CLUB_REJECTED,
]


def _make_webhook_relay(event_name: str):
    def handler(**payload):
        app = current_app._get_current_object()
        dispatch.run_in_background(app, dispatch.send_webhook, event_name, payload)
    return handler


def register_all() -> None:
    events.reset_subscribers()  # idempotent: safe to call every time create_app() runs

    # In-app notifications + contribution log (unchanged from before)
    events.subscribe(events.ISSUE_CREATED, on_issue_created)
    events.subscribe(events.ISSUE_CLAIMED, on_issue_claimed)
    events.subscribe(events.ISSUE_CLOSED, on_issue_closed)
    events.subscribe(events.DOCUMENT_PUBLISHED, on_document_published)
    events.subscribe(events.MENTORSHIP_REQUESTED, on_mentorship_requested)
    events.subscribe(events.MENTORSHIP_ACCEPTED, on_mentorship_accepted)
    events.subscribe(events.MENTORSHIP_COMPLETED, on_mentorship_completed)
    events.subscribe(events.OWNERSHIP_TRANSFER_REQUESTED, on_ownership_transfer_requested)
    events.subscribe(events.OWNERSHIP_TRANSFER_RESOLVED, on_ownership_transfer_resolved)
    events.subscribe(events.ANNOUNCEMENT_POSTED, on_announcement_posted)
    events.subscribe(events.CLUB_SUBMITTED, on_club_submitted)
    events.subscribe(events.CLUB_APPROVED, on_club_approved)
    events.subscribe(events.CLUB_REJECTED, on_club_rejected)

    # External email -- added subscribers on the SAME events above, not
    # modifications to the handlers already registered for them.
    events.subscribe(events.MENTORSHIP_REQUESTED, dispatch_email_mentorship_requested)
    events.subscribe(events.MENTORSHIP_ACCEPTED, dispatch_email_mentorship_accepted)
    events.subscribe(events.OWNERSHIP_TRANSFER_REQUESTED, dispatch_email_ownership_transfer_requested)
    events.subscribe(events.ISSUE_CLAIMED, dispatch_email_issue_claimed)

    # External webhook relay -- one generic subscriber per relayed event
    for event_name in WEBHOOK_RELAY_EVENTS:
        events.subscribe(event_name, _make_webhook_relay(event_name))