from __future__ import annotations

from app.core import db, events


class MentorshipError(Exception):
    pass


def request_mentorship(project_id: int, student_id: int, message: str) -> dict:
    existing = db.query_one(
        """SELECT id FROM mentorship_requests WHERE project_id = ? AND student_id = ?
           AND status IN ('pending', 'accepted')""",
        (project_id, student_id),
    )
    if existing:
        raise MentorshipError("You already have an active mentorship request for this project.")
    request_id = db.execute(
        "INSERT INTO mentorship_requests (project_id, student_id, message) VALUES (?, ?, ?)",
        (project_id, student_id, message.strip()),
    )
    events.emit(events.MENTORSHIP_REQUESTED, request_id=request_id, project_id=project_id, student_id=student_id)
    return db.query_one("SELECT * FROM mentorship_requests WHERE id = ?", (request_id,))


def list_for_student(student_id: int) -> list[dict]:
    return db.query(
        """SELECT mr.*, p.name AS project_name, p.slug AS project_slug, u.full_name AS mentor_name
           FROM mentorship_requests mr JOIN projects p ON p.id = mr.project_id
           LEFT JOIN users u ON u.id = mr.mentor_id
           WHERE mr.student_id = ? ORDER BY mr.created_at DESC""",
        (student_id,),
    )


def list_for_mentor_pool(mentor_id: int) -> list[dict]:
    """Pending requests on projects this mentor maintains, plus ones already assigned to them."""
    return db.query(
        """SELECT mr.*, p.name AS project_name, p.slug AS project_slug, s.full_name AS student_name
           FROM mentorship_requests mr
           JOIN projects p ON p.id = mr.project_id
           JOIN users s ON s.id = mr.student_id
           WHERE mr.mentor_id = ?
              OR (mr.status = 'pending' AND mr.project_id IN (
                    SELECT project_id FROM project_members
                    WHERE user_id = ? AND role IN ('owner', 'maintainer')
                  ))
           ORDER BY mr.created_at DESC""",
        (mentor_id, mentor_id),
    )


def accept_request(request_id: int, mentor_id: int) -> None:
    req = db.query_one("SELECT * FROM mentorship_requests WHERE id = ?", (request_id,))
    if req is None or req["status"] != "pending":
        raise MentorshipError("This request is no longer pending.")
    db.execute(
        "UPDATE mentorship_requests SET status = 'accepted', mentor_id = ?, updated_at = datetime('now') WHERE id = ?",
        (mentor_id, request_id),
    )
    events.emit(events.MENTORSHIP_ACCEPTED, request_id=request_id, student_id=req["student_id"], mentor_id=mentor_id)


def decline_request(request_id: int) -> None:
    db.execute(
        "UPDATE mentorship_requests SET status = 'declined', updated_at = datetime('now') WHERE id = ?",
        (request_id,),
    )


def complete_request(request_id: int) -> None:
    req = db.query_one("SELECT * FROM mentorship_requests WHERE id = ?", (request_id,))
    if req is None or req["status"] != "accepted":
        raise MentorshipError("Only accepted mentorships can be marked complete.")
    db.execute(
        "UPDATE mentorship_requests SET status = 'completed', updated_at = datetime('now') WHERE id = ?",
        (request_id,),
    )
    events.emit(events.MENTORSHIP_COMPLETED, request_id=request_id, student_id=req["student_id"], mentor_id=req["mentor_id"])
