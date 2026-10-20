"""
Health-check & ops endpoints.

GET /healthz        → 200 OK JSON (liveness: "is the process running?")
GET /readyz          → 200 / 503 JSON (readiness: "can it serve traffic?")
                        Checks DB connectivity.

These are intentionally unauthenticated and rate-limit-exempt so that
load-balancers, Kubernetes probes, and uptime monitors can poll them freely.
"""
from __future__ import annotations

import logging
import time

from flask import Blueprint, jsonify

from app.core import db

logger = logging.getLogger("opencampus.health")

bp = Blueprint("health", __name__)


@bp.route("/healthz")
def liveness():
    """Always 200 if the Flask process is alive."""
    return jsonify({"status": "ok", "ts": time.time()}), 200


@bp.route("/readyz")
def readiness():
    """
    200 if the app can serve traffic (DB reachable).
    503 if not (gives load-balancers a signal to take the instance out of
    rotation while it's warming up or if a dependency has failed).
    """
    checks: dict[str, str] = {}
    ok = True

    try:
        row = db.query_one("SELECT 1 AS ping")
        checks["db"] = "ok" if row and row.get("ping") == 1 else "fail"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Readiness DB check failed: %s", exc)
        checks["db"] = f"fail: {exc}"
        ok = False

    status = "ok" if ok else "degraded"
    http_code = 200 if ok else 503
    return jsonify({"status": status, "checks": checks, "ts": time.time()}), http_code
