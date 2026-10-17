from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort, current_app

from app.core.security import login_required, is_project_member
from app.blueprints.issues import service
from app.blueprints.projects import service as projects_service

bp = Blueprint("issues", __name__, url_prefix="/projects")


@bp.route("/<slug>/issues/new", methods=["GET", "POST"])
@login_required
def new_issue(slug: str):
    project = projects_service.get_project_by_slug(slug)
    if project is None:
        abort(404)
    if request.method == "POST":
        try:
            issue = service.create_issue(
                project["id"], request.form.get("title", ""), request.form.get("description", ""),
                request.form.get("difficulty", "beginner"), g.user["id"],
            )
        except service.IssueError as e:
            flash(str(e), "danger")
            return render_template("issues/new.html", project=project, form=request.form,
                                    difficulties=current_app.config["ISSUE_DIFFICULTIES"])
        flash(f'Issue "{issue["title"]}" opened.', "success")
        return redirect(url_for("issues.detail", issue_id=issue["id"]))
    return render_template("issues/new.html", project=project, form={}, difficulties=current_app.config["ISSUE_DIFFICULTIES"])


@bp.route("/issue/<int:issue_id>")
def detail(issue_id: int):
    issue = service.get_issue(issue_id)
    if issue is None:
        abort(404)
    comments = service.get_comments(issue_id)
    can_manage = bool(g.user) and is_project_member(issue["project_id"], g.user["id"], ("owner", "maintainer"))
    return render_template(
        "issues/detail.html", issue=issue, comments=comments, can_manage=can_manage,
        statuses=current_app.config["ISSUE_STATUSES"],
    )


@bp.route("/issue/<int:issue_id>/claim", methods=["POST"])
@login_required
def claim(issue_id: int):
    try:
        service.claim_issue(issue_id, g.user["id"])
        flash("Issue claimed. Good luck!", "success")
    except service.IssueError as e:
        flash(str(e), "danger")
    return redirect(url_for("issues.detail", issue_id=issue_id))


@bp.route("/issue/<int:issue_id>/status", methods=["POST"])
@login_required
def change_status(issue_id: int):
    issue = service.get_issue(issue_id)
    if issue is None:
        abort(404)
    if not is_project_member(issue["project_id"], g.user["id"], ("owner", "maintainer")):
        abort(403)
    new_status = request.form.get("status")
    if new_status in current_app.config["ISSUE_STATUSES"]:
        service.update_status(issue_id, new_status, g.user["id"])
        flash("Issue status updated.", "success")
    return redirect(url_for("issues.detail", issue_id=issue_id))


@bp.route("/issue/<int:issue_id>/comment", methods=["POST"])
@login_required
def comment(issue_id: int):
    try:
        service.add_comment(issue_id, g.user["id"], request.form.get("body", ""))
    except service.IssueError as e:
        flash(str(e), "danger")
    return redirect(url_for("issues.detail", issue_id=issue_id))
