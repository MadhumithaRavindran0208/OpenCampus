from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app

from app.core.security import roles_required
from app.extensions import db
from app.blueprints.admin import service
from app.blueprints.projects import service as projects_service
from app.blueprints.clubs import service as clubs_service

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/")
@roles_required("platform_admin")
def dashboard():
    return render_template(
        "admin/dashboard.html",
        stats=service.platform_stats(),
        top_contributors=service.top_contributors(),
        attention=service.projects_needing_attention(),
    )


@bp.route("/users")
@roles_required("platform_admin")
def users():
    return render_template("admin/users.html", users=service.list_users(), roles=current_app.config["USER_ROLES"])


@bp.route("/users/<int:user_id>/role", methods=["POST"])
@roles_required("platform_admin")
def set_role(user_id: int):
    role = request.form.get("role")
    if role in current_app.config["USER_ROLES"]:
        service.set_user_role(user_id, role)
        flash("User role updated.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/users/<int:user_id>/toggle-active", methods=["POST"])
@roles_required("platform_admin")
def toggle_active(user_id: int):
    active = request.form.get("active") == "1"
    service.set_user_active(user_id, active)
    flash("User status updated.", "success")
    return redirect(url_for("admin.users"))


@bp.route("/clubs")
@roles_required("platform_admin")
def clubs():
    return render_template("admin/clubs.html", pending_clubs=clubs_service.list_pending_clubs())


@bp.route("/clubs/<int:club_id>/approve", methods=["POST"])
@roles_required("platform_admin")
def approve_club(club_id: int):
    try:
        clubs_service.approve_club(club_id)
        flash("Club approved.", "success")
    except clubs_service.ClubError as e:
        flash(str(e), "danger")
    return redirect(url_for("admin.clubs"))


@bp.route("/clubs/<int:club_id>/reject", methods=["POST"])
@roles_required("platform_admin")
def reject_club(club_id: int):
    try:
        clubs_service.reject_club(club_id)
        flash("Club rejected.", "info")
    except clubs_service.ClubError as e:
        flash(str(e), "danger")
    return redirect(url_for("admin.clubs"))


@bp.route("/transfers")
@roles_required("platform_admin")
def transfers():
    return render_template("admin/transfers.html", transfers=service.list_pending_transfers())


@bp.route("/transfers/<int:transfer_id>/resolve", methods=["POST"])
@roles_required("platform_admin")
def resolve_transfer(transfer_id: int):
    accept = request.form.get("decision") == "accept"
    try:
        projects_service.resolve_ownership_transfer(transfer_id, accept)
        flash("Transfer resolved.", "success")
    except projects_service.ProjectError as e:
        flash(str(e), "danger")
    return redirect(url_for("admin.transfers"))


@bp.route("/audit-logs")
@roles_required("platform_admin")
def audit_logs():
    from app.blueprints.auth.models import AuditLog, User
    UserAlias = db.aliased(User)
    logs = (
        db.session.query(
            AuditLog.id,
            AuditLog.action,
            AuditLog.user_id,
            AuditLog.target_type,
            AuditLog.target_id,
            AuditLog.details,
            AuditLog.ip_address,
            AuditLog.created_at,
            UserAlias.email.label("user_email"),
        )
        .outerjoin(UserAlias, UserAlias.id == AuditLog.user_id)
        .order_by(AuditLog.id.desc())
        .limit(100)
        .all()
    )
    return render_template("admin/audit_logs.html", logs=[dict(r._mapping) for r in logs])