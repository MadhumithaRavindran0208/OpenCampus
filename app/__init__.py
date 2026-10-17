"""
Application factory. This is the single place that knows every module
exists -- individual blueprints never import each other's routes, only
shared services in app/core. That's what keeps modules independently
replaceable (see ARCHITECTURE.md).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, g, render_template, request

from app.core.config import get_config
from app.core import db as db_module
from app.core import security, listeners, csrf
from app.core.crash_reporter import write_crash_report


def create_app(config_overrides: dict | None = None) -> Flask:
    app = Flask(__name__)
    cfg = get_config()
    app.config.from_object(cfg)
    if config_overrides:
        app.config.update(config_overrides)

    cfg.ensure_data_dir()
    db_module.init_app(app)

    # Apply any pending migrations at startup so `python run.py` always
    # results in an up-to-date schema -- no manual migration step to forget.
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
    db_module.apply_migrations(Path(app.config["DATABASE_PATH"]), migrations_dir)

    listeners.register_all()

    app.before_request(security.load_logged_in_user)

    @app.before_request
    def _enforce_csrf():
        # Skipped under TESTING so the rest of the suite doesn't need to
        # know about CSRF at all -- tests/test_csrf.py exercises the real
        # enforcement path explicitly with TESTING off.
        if app.testing:
            return None
        if request.method in csrf.SAFE_METHODS:
            return None
        submitted = request.form.get(csrf.FORM_FIELD) or request.headers.get("X-CSRF-Token")
        if not csrf.validate_csrf_token(submitted):
            return render_template(
                "errors/error.html", code=400,
                message="Your session expired or the form was out of date. Please go back and try again.",
            ), 400
        return None

    app.jinja_env.globals["csrf_token"] = csrf.get_csrf_token

    @app.context_processor
    def inject_globals():
        unread_count = 0
        if g.get("user"):
            row = db_module.query_one(
                "SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND is_read = 0",
                (g.user["id"],),
            )
            unread_count = row["c"] if row else 0
        return {"current_user": g.get("user"), "unread_notifications": unread_count, "now": datetime.now(timezone.utc)}

    from app.blueprints.auth.routes import bp as auth_bp
    from app.blueprints.clubs.routes import bp as clubs_bp
    from app.blueprints.projects.routes import bp as projects_bp
    from app.blueprints.issues.routes import bp as issues_bp
    from app.blueprints.docs.routes import bp as docs_bp
    from app.blueprints.mentorship.routes import bp as mentorship_bp
    from app.blueprints.announcements.routes import bp as announcements_bp
    from app.blueprints.notifications.routes import bp as notifications_bp
    from app.blueprints.search.routes import bp as search_bp
    from app.blueprints.admin.routes import bp as admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(clubs_bp)
    app.register_blueprint(projects_bp)
    app.register_blueprint(issues_bp)
    app.register_blueprint(docs_bp)
    app.register_blueprint(mentorship_bp)
    app.register_blueprint(announcements_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(admin_bp)

    @app.route("/")
    def home():
        from app.blueprints.projects.service import list_projects_for_feed
        from app.blueprints.announcements.service import list_recent_announcements

        return render_template(
            "home.html",
            projects=list_projects_for_feed(limit=6),
            announcements=list_recent_announcements(limit=5),
        )

    @app.errorhandler(403)
    def forbidden(_e):
        return render_template("errors/error.html", code=403, message="You don't have access to that."), 403

    @app.errorhandler(404)
    def not_found(_e):
        return render_template("errors/error.html", code=404, message="That page doesn't exist."), 404

    @app.errorhandler(Exception)
    def handle_unexpected_error(e):
        from werkzeug.exceptions import HTTPException

        # 403/404/etc. are expected control flow, not bugs -- let Flask's
        # normal handling (including the two handlers above) deal with
        # those. Only genuinely unexpected exceptions get a crash report.
        if isinstance(e, HTTPException):
            return e

        reports_dir = Path(app.config["DATA_DIR"]) / "crash_reports"
        report_path = write_crash_report(e, f"{request.method} {request.path}", reports_dir)
        # The report's path is logged for whoever operates this deployment,
        # never shown in the response: a file path or instance-directory
        # layout is internal information disclosure and of no use to the
        # person who hit the bug.
        app.logger.error("Unhandled exception -- crash report written to %s", report_path)

        return render_template(
            "errors/error.html", code=500,
            message="Something went wrong on our end. The issue has been logged -- please try again shortly.",
        ), 500

    return app