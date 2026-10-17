from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort

from app.core.security import login_required
from app.blueprints.clubs import service

bp = Blueprint("clubs", __name__, url_prefix="/clubs")


@bp.route("/")
def index():
    return render_template("clubs/index.html", clubs=service.list_clubs())


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new_club():
    if request.method == "POST":
        try:
            club = service.create_club(
                request.form.get("name", ""), request.form.get("description", ""), g.user["id"]
            )
        except service.ClubError as e:
            flash(str(e), "danger")
            return render_template("clubs/new.html", form=request.form)
        if club["status"] == "pending":
            flash(f'Club "{club["name"]}" submitted and is awaiting admin approval.', "info")
        else:
            flash(f'Club "{club["name"]}" created.', "success")
        return redirect(url_for("clubs.detail", slug=club["slug"]))
    return render_template("clubs/new.html", form={})


@bp.route("/<slug>")
def detail(slug: str):
    club = service.get_club_by_slug(slug)
    if club is None:
        abort(404)
    members = service.get_club_members(club["id"])
    projects = service.get_club_projects(club["id"])
    is_member = bool(g.user) and any(m["id"] == g.user["id"] for m in members)
    return render_template("clubs/detail.html", club=club, members=members, projects=projects, is_member=is_member)


@bp.route("/<slug>/join", methods=["POST"])
@login_required
def join(slug: str):
    club = service.get_club_by_slug(slug)
    if club is None:
        abort(404)
    try:
        service.join_club(club["id"], g.user["id"])
        flash(f'You joined {club["name"]}.', "success")
    except service.ClubError as e:
        flash(str(e), "danger")
    return redirect(url_for("clubs.detail", slug=slug))