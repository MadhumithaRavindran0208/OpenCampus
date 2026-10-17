from __future__ import annotations

from flask import current_app

from app.core import db, events
from app.core.utils import unique_slug


class ClubError(Exception):
    pass


def create_club(name: str, description: str, created_by: int) -> dict:
    name = name.strip()
    if not name:
        raise ClubError("Club name is required.")
    slug = unique_slug(name, "clubs")
    requires_approval = current_app.config["REQUIRE_ADMIN_APPROVAL_FOR_CLUBS"]
    status = "pending" if requires_approval else "approved"
    club_id = db.execute(
        "INSERT INTO clubs (name, slug, description, created_by, status) VALUES (?, ?, ?, ?, ?)",
        (name, slug, description.strip(), created_by, status),
    )
    db.execute(
        "INSERT INTO club_members (club_id, user_id, role) VALUES (?, ?, 'admin')",
        (club_id, created_by),
    )
    if requires_approval:
        events.emit(events.CLUB_SUBMITTED, club_id=club_id, name=name, created_by=created_by)
    return db.query_one("SELECT * FROM clubs WHERE id = ?", (club_id,))


def list_clubs() -> list[dict]:
    """Public club listing -- approved clubs only."""
    return db.query(
        """SELECT c.*, COUNT(DISTINCT cm.user_id) AS member_count,
                  COUNT(DISTINCT p.id) AS project_count
           FROM clubs c
           LEFT JOIN club_members cm ON cm.club_id = c.id
           LEFT JOIN projects p ON p.club_id = c.id
           WHERE c.status = 'approved'
           GROUP BY c.id ORDER BY c.name"""
    )


def list_pending_clubs() -> list[dict]:
    return db.query(
        """SELECT c.*, u.full_name AS created_by_name FROM clubs c
           JOIN users u ON u.id = c.created_by
           WHERE c.status = 'pending' ORDER BY c.created_at""",
    )


def approve_club(club_id: int) -> None:
    club = db.query_one("SELECT * FROM clubs WHERE id = ?", (club_id,))
    if club is None or club["status"] != "pending":
        raise ClubError("This club is not awaiting approval.")
    db.execute("UPDATE clubs SET status = 'approved' WHERE id = ?", (club_id,))
    events.emit(events.CLUB_APPROVED, club_id=club_id, name=club["name"], created_by=club["created_by"])


def reject_club(club_id: int) -> None:
    club = db.query_one("SELECT * FROM clubs WHERE id = ?", (club_id,))
    if club is None or club["status"] != "pending":
        raise ClubError("This club is not awaiting approval.")
    db.execute("UPDATE clubs SET status = 'rejected' WHERE id = ?", (club_id,))
    events.emit(events.CLUB_REJECTED, club_id=club_id, name=club["name"], created_by=club["created_by"])


def get_club_by_slug(slug: str) -> dict | None:
    return db.query_one("SELECT * FROM clubs WHERE slug = ?", (slug,))


def get_club_members(club_id: int) -> list[dict]:
    return db.query(
        """SELECT u.id, u.full_name, u.email, u.role AS platform_role, cm.role AS club_role, cm.joined_at
           FROM club_members cm JOIN users u ON u.id = cm.user_id
           WHERE cm.club_id = ? ORDER BY cm.role DESC, u.full_name""",
        (club_id,),
    )


def join_club(club_id: int, user_id: int) -> None:
    club = db.query_one("SELECT status FROM clubs WHERE id = ?", (club_id,))
    if club is None or club["status"] != "approved":
        raise ClubError("This club isn't open to new members yet.")
    existing = db.query_one(
        "SELECT id FROM club_members WHERE club_id = ? AND user_id = ?", (club_id, user_id)
    )
    if existing:
        return
    db.execute("INSERT INTO club_members (club_id, user_id, role) VALUES (?, ?, 'member')", (club_id, user_id))


def get_club_projects(club_id: int) -> list[dict]:
    return db.query(
        """SELECT p.*, COUNT(i.id) AS open_issue_count
           FROM projects p
           LEFT JOIN issues i ON i.project_id = p.id AND i.status = 'open'
           WHERE p.club_id = ? GROUP BY p.id ORDER BY p.updated_at DESC""",
        (club_id,),
    )