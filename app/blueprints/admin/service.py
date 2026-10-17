from __future__ import annotations

from app.core import db


def platform_stats() -> dict:
    def count(sql, params=()):
        return db.query_one(sql, params)["c"]

    return {
        "users": count("SELECT COUNT(*) AS c FROM users"),
        "active_users": count("SELECT COUNT(*) AS c FROM users WHERE is_active = 1"),
        "clubs": count("SELECT COUNT(*) AS c FROM clubs"),
        "projects": count("SELECT COUNT(*) AS c FROM projects"),
        "projects_seeking_maintainer": count(
            "SELECT COUNT(*) AS c FROM projects WHERE status = 'seeking_maintainer'"
        ),
        "open_issues": count("SELECT COUNT(*) AS c FROM issues WHERE status = 'open'"),
        "closed_issues": count("SELECT COUNT(*) AS c FROM issues WHERE status IN ('done','closed')"),
        "pending_mentorships": count("SELECT COUNT(*) AS c FROM mentorship_requests WHERE status = 'pending'"),
        "completed_mentorships": count("SELECT COUNT(*) AS c FROM mentorship_requests WHERE status = 'completed'"),
        "pending_transfers": count("SELECT COUNT(*) AS c FROM ownership_transfers WHERE status = 'pending'"),
        "pending_clubs": count("SELECT COUNT(*) AS c FROM clubs WHERE status = 'pending'"),
        "projects_seeking_contributors": count(
            "SELECT COUNT(*) AS c FROM projects WHERE is_seeking_contributors = 1"
        ),
    }


def list_users(limit: int = 100) -> list[dict]:
    return db.query("SELECT id, email, full_name, role, is_active, created_at FROM users ORDER BY created_at DESC LIMIT ?", (limit,))


def set_user_role(user_id: int, role: str) -> None:
    db.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))


def set_user_active(user_id: int, active: bool) -> None:
    db.execute("UPDATE users SET is_active = ? WHERE id = ?", (1 if active else 0, user_id))


def list_pending_transfers() -> list[dict]:
    return db.query(
        """SELECT ot.*, p.name AS project_name, p.slug AS project_slug,
                  f.full_name AS from_name, t.full_name AS to_name
           FROM ownership_transfers ot
           JOIN projects p ON p.id = ot.project_id
           JOIN users f ON f.id = ot.from_user_id
           JOIN users t ON t.id = ot.to_user_id
           WHERE ot.status = 'pending' ORDER BY ot.created_at DESC"""
    )


def top_contributors(limit: int = 10) -> list[dict]:
    return db.query(
        """SELECT u.id, u.full_name, SUM(cl.points) AS total_points, COUNT(*) AS activity_count
           FROM contribution_log cl JOIN users u ON u.id = cl.user_id
           GROUP BY u.id ORDER BY total_points DESC LIMIT ?""",
        (limit,),
    )


def projects_needing_attention() -> list[dict]:
    """Projects with no maintainer activity signal: seeking_maintainer status, or only one member."""
    return db.query(
        """SELECT p.*, COUNT(pm.id) AS member_count
           FROM projects p LEFT JOIN project_members pm ON pm.project_id = p.id
           GROUP BY p.id HAVING p.status = 'seeking_maintainer' OR member_count <= 1
           ORDER BY p.updated_at ASC"""
    )