from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash, g

from app.core.security import login_required
from app.blueprints.announcements import service
from app.blueprints.clubs import service as clubs_service

bp = Blueprint("announcements", __name__, url_prefix="/announcements")


@bp.route("/")
def index():
    return render_template("announcements/index.html", announcements=service.list_recent_announcements(50))


@bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    my_clubs = [c for c in clubs_service.list_clubs()]
    if request.method == "POST":
        club_id = request.form.get("club_id") or None
        service.post_announcement(
            request.form.get("title", ""), request.form.get("body", ""), g.user["id"],
            int(club_id) if club_id else None,
        )
        flash("Announcement posted.", "success")
        return redirect(url_for("announcements.index"))
    return render_template("announcements/new.html", clubs=my_clubs)
