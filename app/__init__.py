"""
Application factory configured with central extensions registry.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, g, render_template, request
from flask_login import current_user

from app.core.config import get_config
from app.extensions import db, migrate, login_manager, csrf as csrf_ext
from app.core import security, listeners
from app.core.crash_reporter import write_crash_report
from app.core.logging_config import configure_logging
from app.core import rate_limit as rl
from app.core import telemetry


def create_app(config_overrides: dict | None = None) -> Flask:
    is_production = os.environ.get("OPENCAMPUS_ENV", "development").lower() == "production"

    # Configure structured logging before anything else
    configure_logging(is_production=is_production)

    app = Flask(__name__)
    cfg = get_config()
    app.config.from_object(cfg)
    if config_overrides:
        app.config.update(config_overrides)

    cfg.ensure_data_dir()

    # Initialize extensions decoupled from application
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf_ext.init_app(app)

    # Wire distributed tracing & latency SLO monitoring
    telemetry.init_app(app)

    # Wire in rate limiting (in-memory by default, Redis when REDIS_URL is set).
    rl.init_app(app)

    # Ensure all ORM models are registered and create tables if needed
    if not app.config.get("SKIP_DB_INIT"):
        with app.app_context():
            from app.blueprints.auth import models as _auth_models  # noqa: F401
            from app.blueprints.clubs import models as _clubs_models  # noqa: F401
            from app.blueprints.projects import models as _projects_models  # noqa: F401
            from app.blueprints.announcements import models as _announcements_models  # noqa: F401
            from app.blueprints.docs import models as _docs_models  # noqa: F401
            from app.blueprints.notifications import models as _notifications_models  # noqa: F401
            db.create_all()
            try:
                from sqlalchemy import inspect, text
                inspector = inspect(db.engine)
                tables = inspector.get_table_names()
                if "projects" in tables:
                    cols = [col["name"] for col in inspector.get_columns("projects")]
                    if "looking_for" not in cols:
                        db.session.execute(text("ALTER TABLE projects ADD COLUMN looking_for TEXT DEFAULT ''"))
                    if "source_code_restricted" not in cols:
                        db.session.execute(text("ALTER TABLE projects ADD COLUMN source_code_restricted INTEGER NOT NULL DEFAULT 1"))
                    if "readme" not in cols:
                        db.session.execute(text("ALTER TABLE projects ADD COLUMN readme TEXT DEFAULT ''"))
                    db.session.commit()
                if "clubs" in tables:
                    cols = [col["name"] for col in inspector.get_columns("clubs")]
                    if "admin_id" not in cols:
                        db.session.execute(text("ALTER TABLE clubs ADD COLUMN admin_id INTEGER"))
                    if "admin_secret_code_hash" not in cols:
                        db.session.execute(text("ALTER TABLE clubs ADD COLUMN admin_secret_code_hash VARCHAR(255)"))
                    db.session.commit()
                if "users" in tables:
                    cols = [col["name"] for col in inspector.get_columns("users")]
                    if "is_verified" not in cols:
                        db.session.execute(text("ALTER TABLE users ADD COLUMN is_verified INTEGER NOT NULL DEFAULT 0"))
                        # Accounts that pre-date email verification must not be locked out.
                        db.session.execute(text("UPDATE users SET is_verified = 1"))
                    if "verification_token" not in cols:
                        db.session.execute(text("ALTER TABLE users ADD COLUMN verification_token VARCHAR(255) DEFAULT ''"))
                    db.session.commit()
            except Exception:
                db.session.rollback()

    listeners.register_all()

    app.before_request(security.load_logged_in_user)

    # Log every request in a structured way with duration_ms and trace_id for APM.
    @app.after_request
    def _log_request(response):
        import time
        duration_ms = None
        if hasattr(g, "start_time"):
            duration_ms = round((time.monotonic() - g.start_time) * 1000, 2)

        app.logger.info(
            "%s %s %s (%sms)",
            request.method, request.path, response.status_code, duration_ms or 0,
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "ip": request.remote_addr,
                "trace_id": getattr(g, "trace_id", None),
            },
        )
        if response.content_type and "text/html" in response.content_type:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        return response

    @app.context_processor
    def inject_globals():
        unread_count = 0
        user = current_user if current_user.is_authenticated else None
        if user:
            from app.blueprints.notifications.models import Notification
            unread_count = Notification.query.filter_by(user_id=user.id, is_read=0).count()
        return {
            "current_user": current_user,
            "user": user,
            "unread_notifications": unread_count,
            "now": datetime.now(timezone.utc),
        }

    # -----------------------------------------------------------------------
    # Blueprints
    # -----------------------------------------------------------------------
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
    from app.blueprints.sse.routes import bp as sse_bp
    from app.blueprints.health.routes import bp as health_bp

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
    app.register_blueprint(sse_bp)
    app.register_blueprint(health_bp)

    # Exempt health probes from rate limiting.
    rl.limiter.exempt(health_bp)

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

    @app.errorhandler(429)
    def rate_limited(_e):
        return render_template(
            "errors/error.html", code=429,
            message="You're doing that too fast. Please wait a moment and try again.",
        ), 429

    @app.errorhandler(Exception)
    def handle_unexpected_error(e):
        from werkzeug.exceptions import HTTPException

        if isinstance(e, HTTPException):
            return e

        reports_dir = Path(app.config["DATA_DIR"]) / "crash_reports"
        report_path = write_crash_report(e, f"{request.method} {request.path}", reports_dir)
        app.logger.error("Unhandled exception -- crash report written to %s", report_path)

        return render_template(
            "errors/error.html", code=500,
            message="Something went wrong on our end. The issue has been logged -- please try again shortly.",
        ), 500

    return app