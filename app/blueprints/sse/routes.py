"""
SSE (Server-Sent Events) blueprint.

One route:
    GET /sse/events
    → streams SSE frames to the authenticated browser tab.

The JS client is embedded in base.html and auto-reconnects.
"""
from __future__ import annotations

import logging

from flask import Blueprint, Response, g, stream_with_context

from app.core.security import login_required
from app.core import sse as sse_engine

logger = logging.getLogger("opencampus.sse.routes")

bp = Blueprint("sse", __name__, url_prefix="/sse")


@bp.route("/events")
@login_required
def events():
    """
    Long-lived SSE stream for the currently signed-in user.

    The browser connects here on page load (see base.html) and stays
    connected.  The server pushes JSON-encoded events whenever the user
    receives a notification.

    Response headers:
      Content-Type: text/event-stream   (required by the SSE spec)
      Cache-Control: no-cache           (required by the SSE spec)
      X-Accel-Buffering: no             (disables Nginx proxy buffering)
    """
    user_id: int = g.user["id"]

    response = Response(
        stream_with_context(sse_engine.event_stream(user_id)),
        mimetype="text/event-stream",
    )
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    return response
