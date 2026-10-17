from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort, current_app

from app.core.security import login_required, is_project_member
from app.blueprints.projects import service
from app.blueprints.clubs import service as clubs_service
from app.blueprints.issues import service as issues_service
from app.blueprints.docs import service as docs_service

bp = Blueprint("projects", __name__, url_prefix="/projects")


@bp.route("/")
def index():
    query = request.args.get("q", "").strip()
    difficulty = request.args.get("difficulty", "")
    status = request.args.get("status", "")
    seeking_only = request.args.get("seeking") == "1"
    projects = service.search_projects(query, difficulty, status, seeking_only)
    return render_template(
        "projects/index.html", projects=projects, query=query, difficulty=difficulty, status=status,
        seeking_only=seeking_only,
        difficulties=current_app.config["PROJECT_DIFFICULTIES"], statuses=current_app.config["PROJECT_STATUSES"],
    )


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new_project():
    clubs = clubs_service.list_clubs()
    if request.method == "POST":
        try:
            project = service.create_project(
                club_id=int(request.form.get("club_id")),
                name=request.form.get("name", ""),
                description=request.form.get("description", ""),
                tech_stack=request.form.get("tech_stack", ""),
                repo_url=request.form.get("repo_url", ""),
                difficulty=request.form.get("difficulty", "beginner"),
                created_by=g.user["id"],
                is_seeking_contributors=request.form.get("is_seeking_contributors") == "on",
                required_skills=request.form.get("required_skills", ""),
            )
        except (service.ProjectError, TypeError, ValueError) as e:
            flash(str(e) or "Please select a club.", "danger")
            return render_template("projects/new.html", clubs=clubs, form=request.form,
                                    difficulties=current_app.config["PROJECT_DIFFICULTIES"])
        flash(f'Project "{project["name"]}" created.', "success")
        return redirect(url_for("projects.detail", slug=project["slug"]))
    return render_template("projects/new.html", clubs=clubs, form={}, difficulties=current_app.config["PROJECT_DIFFICULTIES"])


@bp.route("/<slug>")
def detail(slug: str):
    project = service.get_project_by_slug(slug)
    if project is None:
        abort(404)
    members = service.get_members(project["id"])
    issues = issues_service.list_issues(project["id"])
    docs = docs_service.list_documents(project["id"])
    is_member = bool(g.user) and any(m["id"] == g.user["id"] for m in members)
    is_maintainer = bool(g.user) and is_project_member(project["id"], g.user["id"], ("owner", "maintainer"))
    issue_stats = {
        "open": sum(1 for i in issues if i["status"] == "open"),
        "in_progress": sum(1 for i in issues if i["status"] in ("claimed", "in_review")),
        "done": sum(1 for i in issues if i["status"] in ("done", "closed")),
    }
    return render_template(
        "projects/detail.html", project=project, members=members, issues=issues[:8], docs=docs,
        is_member=is_member, is_maintainer=is_maintainer, issue_stats=issue_stats,
        statuses=current_app.config["PROJECT_STATUSES"],
    )


@bp.route("/<slug>/join", methods=["POST"])
@login_required
def join(slug: str):
    project = service.get_project_by_slug(slug)
    if project is None:
        abort(404)
    service.join_as_contributor(project["id"], g.user["id"])
    flash(f'You joined {project["name"]} as a contributor.', "success")
    return redirect(url_for("projects.detail", slug=slug))


@bp.route("/<slug>/status", methods=["POST"])
@login_required
def change_status(slug: str):
    project = service.get_project_by_slug(slug)
    if project is None:
        abort(404)
    if not is_project_member(project["id"], g.user["id"], ("owner", "maintainer")):
        abort(403)
    new_status = request.form.get("status")
    if new_status in current_app.config["PROJECT_STATUSES"]:
        service.update_status(project["id"], new_status)
        flash("Project status updated.", "success")
    return redirect(url_for("projects.detail", slug=slug))


@bp.route("/<slug>/help-wanted", methods=["POST"])
@login_required
def update_help_wanted(slug: str):
    project = service.get_project_by_slug(slug)
    if project is None:
        abort(404)
    if not is_project_member(project["id"], g.user["id"], ("owner", "maintainer")):
        abort(403)
    service.update_help_wanted(
        project["id"],
        request.form.get("is_seeking_contributors") == "on",
        request.form.get("required_skills", ""),
    )
    flash("Help wanted status updated.", "success")
    return redirect(url_for("projects.detail", slug=slug))


@bp.route("/<slug>/transfer-ownership", methods=["POST"])
@login_required
def transfer_ownership(slug: str):
    project = service.get_project_by_slug(slug)
    if project is None:
        abort(404)
    if not is_project_member(project["id"], g.user["id"], ("owner",)):
        abort(403)
    try:
        service.request_ownership_transfer(project["id"], g.user["id"], int(request.form.get("to_user_id")))
        flash("Ownership transfer requested.", "success")
    except (service.ProjectError, TypeError, ValueError) as e:
        flash(str(e) or "Please choose a valid member.", "danger")
    return redirect(url_for("projects.detail", slug=slug))