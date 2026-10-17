from __future__ import annotations

from app.core import db, events
from app.core.utils import unique_slug


class ProjectError(Exception):
    pass


def create_project(
    club_id: int, name: str, description: str, tech_stack: str, repo_url: str,
    difficulty: str, created_by: int, is_seeking_contributors: bool = False, required_skills: str = "",
) -> dict:
    name = name.strip()
    if not name:
        raise ProjectError("Project name is required.")
    slug = unique_slug(name, "projects")
    project_id = db.execute(
        """INSERT INTO projects (club_id, name, slug, description, tech_stack, repo_url, difficulty,
               created_by, is_seeking_contributors, required_skills)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            club_id, name, slug, description.strip(), tech_stack.strip(), repo_url.strip(), difficulty,
            created_by, 1 if is_seeking_contributors else 0, required_skills.strip(),
        ),
    )
    db.execute(
        "INSERT INTO project_members (project_id, user_id, role) VALUES (?, ?, 'owner')",
        (project_id, created_by),
    )
    from app.core.utils import log_contribution

    log_contribution(created_by, "project_created", project_id, points=5)
    project = db.query_one("SELECT * FROM projects WHERE id = ?", (project_id,))
    events.emit(events.PROJECT_CREATED, project_id=project_id, created_by=created_by, name=name)
    return project


def list_projects_for_feed(limit: int = 10) -> list[dict]:
    return db.query(
        """SELECT p.*, c.name AS club_name, c.slug AS club_slug,
                  COUNT(DISTINCT i.id) AS open_issue_count
           FROM projects p
           JOIN clubs c ON c.id = p.club_id
           LEFT JOIN issues i ON i.project_id = p.id AND i.status = 'open'
           WHERE p.status IN ('active', 'seeking_maintainer')
           GROUP BY p.id ORDER BY p.updated_at DESC LIMIT ?""",
        (limit,),
    )


def search_projects(
    query: str = "", difficulty: str = "", status: str = "", seeking_only: bool = False, limit: int = 50,
) -> list[dict]:
    sql = """SELECT p.*, c.name AS club_name, c.slug AS club_slug,
                    COUNT(DISTINCT i.id) AS open_issue_count
             FROM projects p JOIN clubs c ON c.id = p.club_id
             LEFT JOIN issues i ON i.project_id = p.id AND i.status = 'open'
             WHERE 1=1"""
    params: list = []
    if query:
        sql += " AND (p.name LIKE ? OR p.description LIKE ? OR p.tech_stack LIKE ? OR p.required_skills LIKE ?)"
        like = f"%{query}%"
        params += [like, like, like, like]
    if difficulty:
        sql += " AND p.difficulty = ?"
        params.append(difficulty)
    if status:
        sql += " AND p.status = ?"
        params.append(status)
    if seeking_only:
        sql += " AND p.is_seeking_contributors = 1"
    sql += " GROUP BY p.id ORDER BY p.is_seeking_contributors DESC, p.updated_at DESC LIMIT ?"
    params.append(limit)
    return db.query(sql, tuple(params))


def get_project_by_slug(slug: str) -> dict | None:
    return db.query_one(
        "SELECT p.*, c.name AS club_name, c.slug AS club_slug FROM projects p JOIN clubs c ON c.id = p.club_id WHERE p.slug = ?",
        (slug,),
    )


def get_project(project_id: int) -> dict | None:
    return db.query_one("SELECT * FROM projects WHERE id = ?", (project_id,))


def get_members(project_id: int) -> list[dict]:
    return db.query(
        """SELECT u.id, u.full_name, u.email, u.contact_email, u.discord_handle, u.linkedin_url, u.github_url,
                  pm.role, pm.joined_at
           FROM project_members pm JOIN users u ON u.id = pm.user_id
           WHERE pm.project_id = ? ORDER BY CASE pm.role WHEN 'owner' THEN 0 WHEN 'maintainer' THEN 1 ELSE 2 END, u.full_name""",
        (project_id,),
    )


def join_as_contributor(project_id: int, user_id: int) -> None:
    existing = db.query_one(
        "SELECT id FROM project_members WHERE project_id = ? AND user_id = ?", (project_id, user_id)
    )
    if existing:
        return
    db.execute(
        "INSERT INTO project_members (project_id, user_id, role) VALUES (?, ?, 'contributor')",
        (project_id, user_id),
    )


def update_status(project_id: int, status: str) -> None:
    db.execute(
        "UPDATE projects SET status = ?, updated_at = datetime('now') WHERE id = ?", (status, project_id)
    )


def update_help_wanted(project_id: int, is_seeking_contributors: bool, required_skills: str) -> None:
    db.execute(
        """UPDATE projects SET is_seeking_contributors = ?, required_skills = ?, updated_at = datetime('now')
           WHERE id = ?""",
        (1 if is_seeking_contributors else 0, required_skills.strip(), project_id),
    )


def request_ownership_transfer(project_id: int, from_user_id: int, to_user_id: int) -> int:
    if from_user_id == to_user_id:
        raise ProjectError("Choose a different member to transfer ownership to.")
    member = db.query_one(
        "SELECT id FROM project_members WHERE project_id = ? AND user_id = ?", (project_id, to_user_id)
    )
    if member is None:
        raise ProjectError("That user is not a member of this project.")
    transfer_id = db.execute(
        "INSERT INTO ownership_transfers (project_id, from_user_id, to_user_id) VALUES (?, ?, ?)",
        (project_id, from_user_id, to_user_id),
    )
    events.emit(
        events.OWNERSHIP_TRANSFER_REQUESTED,
        transfer_id=transfer_id, project_id=project_id, from_user_id=from_user_id, to_user_id=to_user_id,
    )
    return transfer_id


def resolve_ownership_transfer(transfer_id: int, accept: bool) -> None:
    transfer = db.query_one("SELECT * FROM ownership_transfers WHERE id = ?", (transfer_id,))
    if transfer is None or transfer["status"] != "pending":
        raise ProjectError("This transfer request is no longer pending.")

    status = "accepted" if accept else "rejected"
    db.execute(
        "UPDATE ownership_transfers SET status = ?, resolved_at = datetime('now') WHERE id = ?",
        (status, transfer_id),
    )
    if accept:
        db.execute(
            "UPDATE project_members SET role = 'maintainer' WHERE project_id = ? AND user_id = ?",
            (transfer["project_id"], transfer["from_user_id"]),
        )
        db.execute(
            "UPDATE project_members SET role = 'owner' WHERE project_id = ? AND user_id = ?",
            (transfer["project_id"], transfer["to_user_id"]),
        )
    events.emit(
        events.OWNERSHIP_TRANSFER_RESOLVED,
        transfer_id=transfer_id, project_id=transfer["project_id"],
        from_user_id=transfer["from_user_id"], status=status,
    )