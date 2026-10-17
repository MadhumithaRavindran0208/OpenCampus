from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort

from app.core.security import login_required
from app.blueprints.mentorship import service
from app.blueprints.projects import service as projects_service

bp = Blueprint("mentorship", __name__, url_prefix="/mentorship")


@bp.route("/")
@login_required
def index():
    as_student = service.list_for_student(g.user["id"])
    as_mentor = service.list_for_mentor_pool(g.user["id"]) if g.user["role"] in ("mentor", "club_admin", "platform_admin") else []
    return render_template("mentorship/index.html", as_student=as_student, as_mentor=as_mentor)


@bp.route("/<slug>/request", methods=["POST"])
@login_required
def request_mentorship(slug: str):
    project = projects_service.get_project_by_slug(slug)
    if project is None:
        abort(404)
    try:
        service.request_mentorship(project["id"], g.user["id"], request.form.get("message", ""))
        flash("Mentorship requested. A maintainer or mentor will follow up.", "success")
    except service.MentorshipError as e:
        flash(str(e), "danger")
    return redirect(url_for("projects.detail", slug=slug))


@bp.route("/<int:request_id>/accept", methods=["POST"])
@login_required
def accept(request_id: int):
    try:
        service.accept_request(request_id, g.user["id"])
        flash("Mentorship request accepted.", "success")
    except service.MentorshipError as e:
        flash(str(e), "danger")
    return redirect(url_for("mentorship.index"))


@bp.route("/<int:request_id>/decline", methods=["POST"])
@login_required
def decline(request_id: int):
    service.decline_request(request_id)
    flash("Mentorship request declined.", "info")
    return redirect(url_for("mentorship.index"))


@bp.route("/<int:request_id>/complete", methods=["POST"])
@login_required
def complete(request_id: int):
    try:
        service.complete_request(request_id)
        flash("Mentorship marked as completed.", "success")
    except service.MentorshipError as e:
        flash(str(e), "danger")
    return redirect(url_for("mentorship.index"))
