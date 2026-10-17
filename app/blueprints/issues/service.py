from __future__ import annotations

from app.core import db, events


class IssueError(Exception):
    pass


def create_issue(project_id: int, title: str, description: str, difficulty: str, created_by: int) -> dict:
    title = title.strip()
    if not title:
        raise IssueError("Issue title is required.")
    issue_id = db.execute(
        "INSERT INTO issues (project_id, title, description, difficulty, created_by) VALUES (?, ?, ?, ?, ?)",
        (project_id, title, description.strip(), difficulty, created_by),
    )
    events.emit(events.ISSUE_CREATED, issue_id=issue_id, project_id=project_id, created_by=created_by, title=title)
    return db.query_one("SELECT * FROM issues WHERE id = ?", (issue_id,))


def list_issues(project_id: int, status: str = "") -> list[dict]:
    sql = """SELECT i.*, u.full_name AS assignee_name, cu.full_name AS creator_name
              FROM issues i
              LEFT JOIN users u ON u.id = i.assigned_to
              JOIN users cu ON cu.id = i.created_by
              WHERE i.project_id = ?"""
    params: list = [project_id]
    if status:
        sql += " AND i.status = ?"
        params.append(status)
    sql += " ORDER BY CASE i.status WHEN 'open' THEN 0 WHEN 'claimed' THEN 1 WHEN 'in_review' THEN 2 ELSE 3 END, i.created_at DESC"
    return db.query(sql, tuple(params))


def get_issue(issue_id: int) -> dict | None:
    return db.query_one(
        """SELECT i.*, u.full_name AS assignee_name, cu.full_name AS creator_name,
                  p.name AS project_name, p.slug AS project_slug
           FROM issues i
           LEFT JOIN users u ON u.id = i.assigned_to
           JOIN users cu ON cu.id = i.created_by
           JOIN projects p ON p.id = i.project_id
           WHERE i.id = ?""",
        (issue_id,),
    )


def get_comments(issue_id: int) -> list[dict]:
    return db.query(
        """SELECT ic.*, u.full_name FROM issue_comments ic JOIN users u ON u.id = ic.user_id
           WHERE ic.issue_id = ? ORDER BY ic.created_at ASC""",
        (issue_id,),
    )


def add_comment(issue_id: int, user_id: int, body: str) -> None:
    body = body.strip()
    if not body:
        raise IssueError("Comment cannot be empty.")
    db.execute("INSERT INTO issue_comments (issue_id, user_id, body) VALUES (?, ?, ?)", (issue_id, user_id, body))


def claim_issue(issue_id: int, user_id: int) -> None:
    issue = db.query_one("SELECT * FROM issues WHERE id = ?", (issue_id,))
    if issue is None:
        raise IssueError("Issue not found.")
    if issue["status"] != "open":
        raise IssueError("This issue has already been claimed.")
    db.execute(
        "UPDATE issues SET status = 'claimed', assigned_to = ?, updated_at = datetime('now') WHERE id = ?",
        (user_id, issue_id),
    )
    events.emit(events.ISSUE_CLAIMED, issue_id=issue_id, project_id=issue["project_id"], claimed_by=user_id, title=issue["title"])


def update_status(issue_id: int, status: str, actor_id: int) -> None:
    issue = db.query_one("SELECT * FROM issues WHERE id = ?", (issue_id,))
    if issue is None:
        raise IssueError("Issue not found.")
    db.execute(
        "UPDATE issues SET status = ?, updated_at = datetime('now') WHERE id = ?", (status, issue_id)
    )
    if status in ("done", "closed") and issue["status"] not in ("done", "closed"):
        events.emit(
            events.ISSUE_CLOSED, issue_id=issue_id, project_id=issue["project_id"], closed_by=actor_id,
            title=issue["title"], assigned_to=issue["assigned_to"],
        )
