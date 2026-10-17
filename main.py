#!/usr/bin/env python3
"""
OpenCampus OSS -- single entry point.

    python main.py

That's the only command needed. This script:
  1. installs missing dependencies automatically (first run only),
  2. applies any pending database migrations (handled inside create_app()),
  3. seeds demo data the first time the database is empty (safe to run
     again -- it's a no-op once there's data),
  4. starts the server.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
REQUIRED_PACKAGES = ("flask", "werkzeug", "jinja2", "itsdangerous")


def _write_startup_crash_report(exc: BaseException, context: str) -> Path:
    """Standalone copy of app/core/crash_reporter.py's logic, deliberately
    not imported from there: importing anything under the `app` package
    triggers app/__init__.py, which imports Flask at module level --  not
    safe to rely on before _ensure_dependencies() has confirmed Flask is
    even installed. This function only uses the standard library so it
    can run no matter what stage of startup failed. Keep both copies in
    sync if the report format changes."""
    reports_dir = BASE_DIR / "instance" / "crash_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    report_path = reports_dir / f"crash_{timestamp}.txt"

    content = "\n".join([
        "OpenCampus OSS crash report",
        "=" * 40,
        f"When:    {datetime.now(timezone.utc).isoformat()} UTC",
        f"Context: {context}",
        f"Python:  {sys.version.split()[0]} ({platform.python_implementation()})",
        f"OS:      {platform.platform()}",
        "",
        "Traceback:",
        "-" * 40,
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    ])
    report_path.write_text(content, encoding="utf-8")
    return report_path


def _ensure_dependencies() -> None:
    missing = []
    for pkg in REQUIRED_PACKAGES:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if not missing:
        return

    print(f"Installing dependencies ({', '.join(missing)})...")
    requirements = BASE_DIR / "requirements.txt"
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(requirements)])
    except subprocess.CalledProcessError as exc:
        print(
            "\nCouldn't install dependencies automatically.\n"
            f"Please run this manually, then try again:\n"
            f"    {sys.executable} -m pip install -r requirements.txt\n"
        )
        raise SystemExit(1) from exc


def _seed_demo_data(app) -> None:
    """Populate demo data if the database is empty. Safe to call on
    every run: scripts/seed_data.py::seed() checks for existing users
    and skips quietly if there's already data, so repeat runs never
    duplicate or error."""
    try:
        from scripts.seed_data import seed
        seed(app)
    except Exception as exc:  # noqa: BLE001 -- a seeding hiccup must never block startup
        print(f"Warning: demo data step failed ({exc}). Starting with whatever is already in the database.")


def _print_banner(port: int, is_production: bool) -> None:
    # Guard against the Flask debug reloader, which re-executes this
    # entire script in a child process -- without this check the banner
    # (and the dependency/seed steps above) would print/run twice.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        return
    mode = "production" if is_production else "development"
    print(f"\nOpenCampus OSS is running at http://localhost:{port} ({mode} mode)")
    print("\nDemo accounts (password: password123):")
    print("  admin@opencampus.dev          (platform admin)")
    print("  arjun.k@opencampus.dev        (project owner / club admin)")
    print("  mentor.das@opencampus.dev     (mentor)")
    print("  student.meera@opencampus.dev  (student contributor)")
    print("\nPress CTRL+C to stop.\n")


def _port_available(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def _run_production_server(app, port: int) -> None:
    """Serve via waitress, a real production-grade WSGI server, instead
    of Werkzeug's development server (which prints its own warning that
    it isn't meant for production traffic -- single-threaded, no
    hardening against slow clients, etc.).

    Falls back to the dev server, with a loud warning, if waitress
    isn't installed rather than refusing to start at all -- a
    degraded-but-running deployment is more useful than a hard failure
    for someone who set OPENCAMPUS_ENV=production without having read
    the deployment docs yet. See requirements.txt for how to install it."""
    try:
        from waitress import serve
    except ImportError:
        print(
            "\nOPENCAMPUS_ENV=production was set, but the 'waitress' production server "
            "isn't installed.\nFalling back to Flask's development server, which is NOT "
            "recommended for production traffic.\nInstall it with:  pip install waitress\n"
        )
        app.run(host="0.0.0.0", port=port, debug=False)
        return

    serve(app, host="0.0.0.0", port=port)


def main() -> None:
    _ensure_dependencies()
    sys.path.insert(0, str(BASE_DIR))

    is_production = os.environ.get("OPENCAMPUS_ENV", "development").lower() == "production"
    port = int(os.environ.get("PORT", "5000"))
    # Debug mode is always forced off in production regardless of
    # FLASK_DEBUG -- Werkzeug's interactive debugger has no business
    # being reachable on a real deployment even if someone left that
    # variable set from local development.
    debug = False if is_production else os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    # Checked up front, before any DB/app setup, rather than relying on
    # catching app.run()'s failure: Werkzeug's dev server already
    # intercepts a bind error itself, prints its own message, and calls
    # sys.exit(1) directly -- an except OSError around app.run() below
    # would never actually be reached.
    if os.environ.get("WERKZEUG_RUN_MAIN") != "true" and not _port_available(port):
        print(f"\nPort {port} is already in use by something else.")
        print(f"Either stop that program, or run on a different port:  PORT=5001 python main.py\n")
        raise SystemExit(1)

    from app import create_app  # deferred: only safe to import once dependencies are confirmed present

    app = create_app()
    _seed_demo_data(app)

    _print_banner(port, is_production)

    try:
        if is_production:
            _run_production_server(app, port)
        else:
            app.run(host="0.0.0.0", port=port, debug=debug)
    except KeyboardInterrupt:
        print("\nStopped.")


def run_with_crash_reporting() -> None:
    """Runs main(), writing a crash report file for any fatal, unexpected
    exception instead of letting it vanish as a raw traceback. Factored
    out (rather than living inline in the `if __name__ == "__main__"`
    block below) so run.py can call this exact same wrapper -- crash
    reporting must not depend on which of the two entry points was used
    to start the app."""
    try:
        main()
    except SystemExit:
        raise  # our own controlled exits (bad port, failed dependency install) aren't "crashes"
    except Exception as exc:  # noqa: BLE001 -- top-level safety net: report it, don't just vanish
        report_path = _write_startup_crash_report(exc, "Fatal error during startup")
        print("\nOpenCampus OSS hit an unexpected error and couldn't start.")
        print(f"A crash report has been saved to:\n    {report_path}\n")
        print("Please share that file if you'd like help figuring out what happened.\n")
        sys.exit(1)


if __name__ == "__main__":
    run_with_crash_reporting()