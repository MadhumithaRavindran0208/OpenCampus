from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g, current_app

from app.core.security import login_required
from app.blueprints.auth import service

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if not current_app.config["ALLOW_SELF_REGISTRATION"]:
        flash("Self-registration is currently disabled. Contact an administrator.", "warning")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        try:
            user = service.register_user(
                email=request.form.get("email", ""),
                password=request.form.get("password", ""),
                full_name=request.form.get("full_name", ""),
                role=request.form.get("role", "student"),
            )
        except service.AuthError as e:
            flash(str(e), "danger")
            return render_template("auth/register.html", form=request.form)

        session.clear()
        session["user_id"] = user["id"]
        flash(f"Welcome to OpenCampus OSS, {user['full_name']}!", "success")
        return redirect(url_for("home"))

    return render_template("auth/register.html", form={})


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        try:
            user = service.authenticate(
                email=request.form.get("email", ""), password=request.form.get("password", "")
            )
        except service.AuthError as e:
            flash(str(e), "danger")
            return render_template("auth/login.html", email=request.form.get("email", ""))

        session.clear()
        session["user_id"] = user["id"]
        session.permanent = True
        flash(f"Welcome back, {user['full_name']}.", "success")
        next_url = request.args.get("next") or url_for("home")
        return redirect(next_url)

    return render_template("auth/login.html", email="")


@bp.route("/logout")
def logout():
    session.clear()
    flash("You've been signed out.", "info")
    return redirect(url_for("home"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def my_profile():
    if request.method == "POST":
        try:
            service.update_profile(
                g.user["id"],
                request.form.get("full_name", g.user["full_name"]),
                request.form.get("bio", ""),
                request.form.get("skills", ""),
                request.form.get("contact_email", ""),
                request.form.get("discord_handle", ""),
                request.form.get("linkedin_url", ""),
                request.form.get("github_url", ""),
                request.form.get("age_category", ""),
            )
        except service.AuthError as e:
            flash(str(e), "danger")
            profile = service.get_public_profile(g.user["id"])
            return render_template(
                "auth/profile.html", profile=profile, is_self=True,
                age_categories=current_app.config["AGE_CATEGORIES"],
            )
        flash("Profile updated.", "success")
        return redirect(url_for("auth.my_profile"))

    profile = service.get_public_profile(g.user["id"])
    return render_template(
        "auth/profile.html", profile=profile, is_self=True,
        age_categories=current_app.config["AGE_CATEGORIES"],
    )


@bp.route("/users/<int:user_id>")
def view_profile(user_id: int):
    profile = service.get_public_profile(user_id)
    if profile is None:
        from flask import abort

        abort(404)
    is_self = bool(g.user and g.user["id"] == user_id)
    return render_template(
        "auth/profile.html", profile=profile, is_self=is_self,
        age_categories=current_app.config["AGE_CATEGORIES"],
    )