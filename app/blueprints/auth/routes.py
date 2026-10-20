"""
Authentication routes backed by Flask-Login and Flask-WTF.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse

from flask import Blueprint, render_template, request, redirect, url_for, flash, g, current_app
from flask_login import login_user, logout_user, login_required, current_user

from app.core.rate_limit import limiter
from app.blueprints.auth import service
from app.blueprints.auth.forms import LoginForm, RegisterForm, ProfileForm

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _safe_next_url(target: str | None) -> str | None:
    """Return `target` only if it is a same-site relative path.

    Rejects absolute URLs, scheme-relative URLs (//evil.com) and backslash
    tricks (/\\evil.com) so the post-login redirect can't be used as an
    open redirect for phishing.
    """
    if not target:
        return None
    target = target.strip()
    if not target.startswith("/") or target.startswith("//") or target.startswith("/\\"):
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return None
    return target


def _show_dev_verify_link() -> bool:
    """The one-click verification link may only be shown on-page in local
    development with real email delivery switched off. Showing it anywhere
    else would let the registrant verify an address they don't own."""
    is_production = os.environ.get("OPENCAMPUS_ENV", "development").lower() == "production"
    email_enabled = bool(
        current_app.config.get("ENABLE_EMAIL_NOTIFICATIONS") and current_app.config.get("SMTP_HOST")
    )
    return not is_production and not email_enabled


def _home_for(user):
    if user.role == "platform_admin":
        return url_for("admin.dashboard")
    if user.role == "club_admin":
        from app.extensions import db
        from app.blueprints.clubs.models import Club, ClubMember
        assigned_club = Club.query.filter(
            (Club.admin_id == user.id)
            | (Club.id.in_(db.session.query(ClubMember.club_id).filter_by(user_id=user.id, role="admin")))
        ).first()
        if assigned_club:
            return url_for("clubs.club_admin_dashboard", slug=assigned_club.slug)
        return url_for("clubs.index")
    if user.role == "mentor":
        return url_for("mentorship.index")
    return url_for("projects.index")


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    if not current_app.config["ALLOW_SELF_REGISTRATION"]:
        flash("Self-registration is currently disabled. Contact an administrator.", "warning")
        return redirect(url_for("auth.login"))

    if current_user.is_authenticated:
        return redirect(url_for("home"))

    form = RegisterForm()
    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "")
        role = request.form.get("role", "student")

        try:
            user = service.register_user(
                email=email,
                password=password,
                full_name=full_name,
                role=role,
            )
        except service.AuthError as e:
            flash(str(e), "danger")
            return render_template("auth/register.html", form=request.form)

        if current_app.config.get("REQUIRE_EMAIL_VERIFICATION", True) and not user.is_verified:
            verify_url = url_for("auth.verify_email", token=user.verification_token, _external=True)
            from app.core import dispatch
            subject = "Verify your OpenCampus OSS account"
            body = (
                f"Hello {user.full_name},\n\n"
                f"Thank you for joining OpenCampus OSS! Please click the link below to verify your email address:\n\n"
                f"{verify_url}\n\n"
                f"If you did not sign up for this account, you can safely ignore this email.\n"
            )
            dispatch.send_email(user.email, subject, body)
            return render_template(
                "auth/verify_notice.html", email=user.email,
                verify_url=verify_url if _show_dev_verify_link() else None,
            )

        login_user(user)
        g.user = user
        flash(f"Welcome to OpenCampus OSS, {user.full_name}!", "success")
        return redirect(url_for("home"))

    return render_template("auth/register.html", form={})


@bp.route("/verify-email/<token>")
def verify_email(token: str):
    try:
        user = service.verify_email_token(token)
        login_user(user)
        g.user = user
        flash("Your email address has been successfully verified! Welcome aboard.", "success")
        return redirect(url_for("home"))
    except service.AuthError as e:
        flash(str(e), "danger")
        return redirect(url_for("auth.login"))


@bp.route("/resend-verification", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def resend_verification():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        verify_url = None
        try:
            user = service.resend_verification_email(email)
        except service.AuthError:
            # Same response whether or not the account exists / is already
            # verified, so this form can't be used to probe for registered emails.
            user = None
        if user is not None:
            link = url_for("auth.verify_email", token=user.verification_token, _external=True)
            from app.core import dispatch
            subject = "Verify your OpenCampus OSS account"
            body = (
                f"Hello {user.full_name},\n\n"
                f"Please click the link below to complete your email verification:\n\n"
                f"{link}\n"
            )
            dispatch.send_email(user.email, subject, body)
            if _show_dev_verify_link():
                verify_url = link
        flash("If that address belongs to an unverified account, a new verification link has been sent.", "info")
        return render_template("auth/verify_notice.html", email=email, verify_url=verify_url)
    return render_template("auth/resend_verification.html")


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    form = LoginForm()
    if current_user.is_authenticated and request.method == "GET":
        return redirect(_safe_next_url(request.args.get("next")) or _home_for(current_user))
    if request.method == "POST":
        email = request.form.get("email", "")
        password = request.form.get("password", "")
        secret_code = request.form.get("secret_code", "")

        try:
            user = service.authenticate(
                email=email,
                password=password,
                secret_code=secret_code,
                ip_address=request.remote_addr,
            )
        except service.AuthError as e:
            flash(str(e), "danger")
            return render_template("auth/login.html", email=email, form=form)

        login_user(user, remember=True)
        g.user = user
        flash(f"Welcome back, {user.full_name}.", "success")

        next_url = _safe_next_url(request.args.get("next"))
        if next_url:
            return redirect(next_url)
        return redirect(_home_for(user))

    return render_template("auth/login.html", email="", form=form)


@bp.route("/logout", methods=["GET", "POST"])
def logout():
    from flask import session, make_response
    logout_user()
    session.clear()
    g.user = None
    flash("You've been successfully signed out.", "info")
    response = make_response(redirect(url_for("home")))
    # Login always sets a "remember me" cookie. logout_user() only schedules its
    # removal through the session, which session.clear() above wipes -- so the
    # cookie must be deleted explicitly or the user is silently signed back in.
    response.delete_cookie(current_app.config.get("REMEMBER_COOKIE_NAME", "remember_token"))
    # Prevent caching of authenticated content on backward navigation
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def my_profile():
    user = current_user
    if request.method == "POST":
        try:
            service.update_profile(
                user.id,
                request.form.get("full_name", user.full_name),
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
            profile = service.get_public_profile(user.id)
            return render_template(
                "auth/profile.html", profile=profile, is_self=True,
                age_categories=current_app.config["AGE_CATEGORIES"],
            )
        flash("Profile updated.", "success")
        return redirect(url_for("auth.my_profile"))

    profile = service.get_public_profile(user.id)
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
    is_self = bool(current_user.is_authenticated and current_user.id == user_id)
    return render_template(
        "auth/profile.html", profile=profile, is_self=is_self,
        age_categories=current_app.config["AGE_CATEGORIES"],
    )