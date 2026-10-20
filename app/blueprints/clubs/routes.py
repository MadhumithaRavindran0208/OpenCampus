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


@bp.route("/<slug>/join", methods=["GET", "POST"])
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


@bp.route("/<slug>/admin")
@login_required
def club_admin_dashboard(slug: str):
    from app.core.security import is_club_admin, is_main_admin
    club = service.get_club_by_slug(slug)
    if club is None:
        abort(404)

    if not (is_main_admin(g.user) or is_club_admin(club["id"], g.user["id"])):
        abort(403)

    data = service.get_club_admin_dashboard_data(club["id"])
    from app.blueprints.auth.models import User
    eligible_admins = User.query.filter_by(is_active=1).all() if is_main_admin(g.user) else []
    return render_template(
        "clubs/admin.html",
        club=data["club"],
        members=data["members"],
        projects=data["projects"],
        pending_tags=data["pending_tags"],
        eligible_admins=eligible_admins,
        is_main_admin=is_main_admin(g.user),
    )


@bp.route("/<slug>/admin/secret-code", methods=["POST"])
@login_required
def update_secret_code(slug: str):
    from app.core.security import is_club_admin, is_main_admin
    club = service.get_club_by_slug(slug)
    if club is None:
        abort(404)

    if not (is_main_admin(g.user) or is_club_admin(club["id"], g.user["id"])):
        abort(403)

    secret_code = request.form.get("secret_code", "")
    try:
        service.set_club_secret_code(club["id"], secret_code)
        flash("Club administrative secret code updated successfully.", "success")
    except service.ClubError as e:
        flash(str(e), "danger")

    return redirect(url_for("clubs.club_admin_dashboard", slug=slug))


@bp.route("/<slug>/admin/assign-admin", methods=["POST"])
@login_required
def assign_admin(slug: str):
    from app.core.security import is_main_admin
    if not is_main_admin(g.user):
        abort(403)

    club = service.get_club_by_slug(slug)
    if club is None:
        abort(404)

    admin_user_id = int(request.form.get("admin_user_id", 0))
    secret_code = request.form.get("secret_code")
    try:
        service.set_club_admin(club["id"], admin_user_id, secret_code)
        flash("Club Admin assigned successfully.", "success")
    except service.ClubError as e:
        flash(str(e), "danger")

    return redirect(url_for("clubs.club_admin_dashboard", slug=slug))