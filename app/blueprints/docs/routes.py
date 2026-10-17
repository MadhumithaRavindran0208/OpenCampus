from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort, current_app

from app.core.security import login_required, is_project_member
from app.core.sanitize import render_markdown_safe
from app.blueprints.docs import service
from app.blueprints.projects import service as projects_service

bp = Blueprint("docs", __name__, url_prefix="/projects")

DOC_TYPES = ["readme", "onboarding", "architecture", "guide"]


@bp.route("/<slug>/docs")
def index(slug: str):
    project = projects_service.get_project_by_slug(slug)
    if project is None:
        abort(404)
    docs = service.list_documents(project["id"])
    return render_template("docs/index.html", project=project, docs=docs)


@bp.route("/<slug>/docs/new", methods=["GET", "POST"])
@login_required
def new_doc(slug: str):
    project = projects_service.get_project_by_slug(slug)
    if project is None:
        abort(404)
    if not is_project_member(project["id"], g.user["id"]):
        flash("Join the project before adding documentation.", "warning")
        return redirect(url_for("projects.detail", slug=slug))
    if request.method == "POST":
        try:
            doc = service.create_document(
                project["id"], request.form.get("title", ""), request.form.get("content_md", ""),
                request.form.get("doc_type", "guide"), g.user["id"],
            )
        except service.DocError as e:
            flash(str(e), "danger")
            return render_template("docs/new.html", project=project, form=request.form, doc_types=DOC_TYPES)
        flash(f'Document "{doc["title"]}" published.', "success")
        return redirect(url_for("docs.view", slug=slug, doc_slug=doc["slug"]))
    return render_template("docs/new.html", project=project, form={}, doc_types=DOC_TYPES)


@bp.route("/<slug>/docs/<doc_slug>")
def view(slug: str, doc_slug: str):
    project = projects_service.get_project_by_slug(slug)
    if project is None:
        abort(404)
    doc = service.get_document(project["id"], doc_slug)
    if doc is None:
        abort(404)
    rendered_html = render_markdown_safe(doc["content_md"])
    return render_template("docs/view.html", project=project, doc=doc, rendered_html=rendered_html)