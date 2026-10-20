from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort, current_app

from app.core.security import (
    login_required,
    is_project_member,
    can_access_source_code,
    can_review_project_tags,
    is_main_admin,
)
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
    is_owner = bool(g.user) and (project["created_by"] == g.user["id"] or is_project_member(project["id"], g.user["id"], ("owner",)))
    has_source_code_access = can_access_source_code(project["id"], g.user["id"] if g.user else None)
    approved_tags = service.list_collaboration_tags(project["id"], approved_only=True)
    all_tags = service.list_collaboration_tags(project["id"], approved_only=False) if is_maintainer else []
    can_review_tags = bool(g.user) and can_review_project_tags(project["id"], g.user["id"])

    from app.blueprints.auth.models import User
    available_mentors = User.query.filter_by(role="mentor", is_active=1).all()

    issue_stats = {
        "open": sum(1 for i in issues if i["status"] == "open"),
        "in_progress": sum(1 for i in issues if i["status"] in ("claimed", "in_review")),
        "done": sum(1 for i in issues if i["status"] in ("done", "closed")),
    }
    return render_template(
        "projects/detail.html",
        project=project,
        members=members,
        issues=issues[:8],
        docs=docs,
        is_member=is_member,
        is_maintainer=is_maintainer,
        is_owner=is_owner,
        has_source_code_access=has_source_code_access,
        approved_tags=approved_tags,
        all_tags=all_tags,
        can_review_tags=can_review_tags,
        available_mentors=available_mentors,
        issue_stats=issue_stats,
        statuses=current_app.config["PROJECT_STATUSES"],
    )


@bp.route("/<slug>/join", methods=["GET", "POST"])
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


@bp.route("/<slug>/source-code")
def source_code(slug: str):
    project = service.get_project_by_slug(slug)
    if project is None:
        abort(404)

    user_id = g.user["id"] if g.user else None
    if not can_access_source_code(project["id"], user_id):
        flash("Source code access is restricted. You must be an authorized member, mentor, or granted access by the project owner.", "danger")
        abort(403)

    if project["repo_url"]:
        return redirect(project["repo_url"])

    flash(f"Source code access authorized for {project['name']}.", "info")
    return redirect(url_for("projects.detail", slug=slug))


@bp.route("/<slug>/access", methods=["GET", "POST"])
@login_required
def manage_access(slug: str):
    project = service.get_project_by_slug(slug)
    if project is None:
        abort(404)

    if not is_project_member(project["id"], g.user["id"], ("owner", "maintainer")):
        abort(403)

    from app.blueprints.auth.models import User
    if request.method == "POST":
        action = request.form.get("action")
        if action == "grant":
            target_user_id = int(request.form.get("target_user_id", 0))
            try:
                service.grant_source_code_access(project["id"], target_user_id, g.user["id"])
                flash("Source code access granted successfully.", "success")
            except service.ProjectError as e:
                flash(str(e), "danger")
        elif action == "toggle_visibility":
            restricted = request.form.get("restricted") == "1"
            service.update_source_code_restricted(project["id"], restricted, g.user["id"])
            flash("Project source code visibility setting updated.", "success")

        return redirect(url_for("projects.manage_access", slug=slug))

    grants = service.list_source_code_grants(project["id"])
    all_users = User.query.filter(User.id != g.user["id"], User.is_active == 1).order_by(User.full_name).all()

    return render_template(
        "projects/access.html",
        project=project,
        grants=grants,
        all_users=all_users,
    )


@bp.route("/<slug>/access/<int:grant_id>/revoke", methods=["POST"])
@login_required
def revoke_access(slug: str, grant_id: int):
    project = service.get_project_by_slug(slug)
    if project is None:
        abort(404)

    if not is_project_member(project["id"], g.user["id"], ("owner", "maintainer")):
        abort(403)

    from app.blueprints.projects.models import ProjectAccessGrant
    grant = ProjectAccessGrant.query.get(grant_id)
    if grant and grant.project_id == project["id"]:
        service.revoke_source_code_access(project["id"], grant.user_id, g.user["id"])
        flash("Source code access revoked.", "info")

    return redirect(url_for("projects.manage_access", slug=slug))


@bp.route("/<slug>/tags/new", methods=["POST"])
@login_required
def new_tag(slug: str):
    project = service.get_project_by_slug(slug)
    if project is None:
        abort(404)

    if not is_project_member(project["id"], g.user["id"], ("owner", "maintainer")):
        abort(403)

    tag_name = request.form.get("tag_name", "").strip()
    try:
        service.add_collaboration_tag(project["id"], tag_name, g.user["id"])
        flash(f'Collaboration tag "{tag_name}" submitted and awaiting administrator approval.', "info")
    except service.ProjectError as e:
        flash(str(e), "danger")

    return redirect(url_for("projects.detail", slug=slug))


@bp.route("/tags/<int:tag_id>/approve", methods=["POST"])
@login_required
def approve_tag(tag_id: int):
    from app.blueprints.projects.models import CollaborationTag, Project
    tag = CollaborationTag.query.get(tag_id)
    if not tag:
        abort(404)

    if not can_review_project_tags(tag.project_id, g.user["id"]):
        abort(403)

    service.approve_collaboration_tag(tag_id, g.user["id"])
    flash(f'Collaboration tag "{tag.name}" approved.', "success")

    project = Project.query.get(tag.project_id)
    if request.referrer and "admin" in request.referrer:
        return redirect(request.referrer)
    return redirect(url_for("projects.detail", slug=project.slug if project else ""))


@bp.route("/tags/<int:tag_id>/reject", methods=["POST"])
@login_required
def reject_tag(tag_id: int):
    from app.blueprints.projects.models import CollaborationTag, Project
    tag = CollaborationTag.query.get(tag_id)
    if not tag:
        abort(404)

    if not can_review_project_tags(tag.project_id, g.user["id"]):
        abort(403)

    reason = request.form.get("reason", "").strip() or "Does not meet club collaboration criteria"
    service.reject_collaboration_tag(tag_id, g.user["id"], reason)
    flash(f'Collaboration tag "{tag.name}" rejected.', "info")

    project = Project.query.get(tag.project_id)
    if request.referrer and "admin" in request.referrer:
        return redirect(request.referrer)
    return redirect(url_for("projects.detail", slug=project.slug if project else ""))


@bp.route("/<slug>/people")
def people(slug: str):
    project = service.get_project_by_slug(slug)
    if project is None:
        abort(404)

    data = service.get_project_people_and_contributions(project["id"])
    is_maintainer = bool(g.user) and is_project_member(project["id"], g.user["id"], ("owner", "maintainer"))

    return render_template(
        "projects/people.html",
        project=project,
        members=data["members"],
        assigned_mentors=data["assigned_mentors"],
        contributions=data["contributions"],
        access_grants=data["access_grants"],
        is_maintainer=is_maintainer,
    )


@bp.route("/<slug>/people/verify-contribution", methods=["POST"])
@login_required
def verify_contribution(slug: str):
    project = service.get_project_by_slug(slug)
    if project is None:
        abort(404)

    if not is_project_member(project["id"], g.user["id"], ("owner", "maintainer")):
        abort(403)

    target_user_id = int(request.form.get("user_id", 0))
    activity_type = request.form.get("activity_type", "pull_request")
    details = request.form.get("details", "")
    points = int(request.form.get("points", 10))

    try:
        service.record_verified_contribution(
            project["id"], target_user_id, activity_type, points, g.user["id"], details
        )
        flash("Contribution verified and recorded on project People page.", "success")
    except service.ProjectError as e:
        flash(str(e), "danger")

    return redirect(url_for("projects.people", slug=slug))