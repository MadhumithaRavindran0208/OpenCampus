"""
Distributed Tracing, Request Correlation, and P99 Latency SLO Tracking.

Conforms to W3C Trace Context specifications (traceparent).
Features:
- Extracts incoming W3C traceparent or generates new 128-bit trace_id and 64-bit span_id.
- Injects trace_id into request context `g.trace_id` and `g.span_id`.
- Automatically emits `X-Trace-ID` and `Server-Timing` HTTP response headers.
- Evaluates request durations against P99 Latency Service Level Objectives (SLOs)
  (default: 500ms), logging high-latency bottlenecks for APM alerting.
- Optional auto-instrumentation with OpenTelemetry SDK when installed.
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from flask import g, request, current_app

logger = logging.getLogger("opencampus.telemetry")

# Hard SLO latency threshold for API responsiveness (in milliseconds)
SLO_LATENCY_THRESHOLD_MS = float(os.environ.get("SLO_LATENCY_THRESHOLD_MS", 500.0))

try:
    from opentelemetry import trace
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    _OTEL_AVAILABLE = True
except ImportError:
    _OTEL_AVAILABLE = False


def _generate_id(length_bytes: int) -> str:
    """Generate cryptographically secure hexadecimal ID (e.g. 16 bytes for trace_id, 8 for span_id)."""
    return secrets.token_hex(length_bytes)


def extract_or_generate_trace():
    """Extract W3C traceparent header or generate a fresh trace/span pair."""
    traceparent = request.headers.get("traceparent", "").strip()
    if traceparent:
        parts = traceparent.split("-")
        if len(parts) >= 3 and len(parts[1]) == 32:
            return parts[1], parts[2]

    # Check X-Request-ID or X-Trace-ID
    custom_trace = request.headers.get("X-Request-ID") or request.headers.get("X-Trace-ID")
    if custom_trace and len(custom_trace) == 32:
        return custom_trace, _generate_id(8)

    # Generate new W3C-compliant 128-bit trace_id and 64-bit span_id
    return _generate_id(16), _generate_id(8)


def init_app(app) -> None:
    """Register telemetry hooks and tracing middleware."""
    if _OTEL_AVAILABLE and os.environ.get("ENABLE_OTEL", "false").lower() == "true":
        try:
            FlaskInstrumentor().instrument_app(app)
            logger.info("OpenTelemetry SDK instrumentation activated")
        except Exception as exc:
            logger.warning("Failed to initialize OpenTelemetry instrumentation: %s", exc)

    @app.before_request
    def start_trace_timer():
        g.start_time = time.monotonic()
        trace_id, span_id = extract_or_generate_trace()
        g.trace_id = trace_id
        g.span_id = span_id

    @app.after_request
    def record_trace_response(response):
        start = getattr(g, "start_time", None)
        trace_id = getattr(g, "trace_id", None)
        span_id = getattr(g, "span_id", None)

        if start is not None:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            # Add Server-Timing header (RFC 8897) for browser DevTools & APM monitoring
            response.headers["Server-Timing"] = f"app;dur={duration_ms};desc=\"Flask processing\""

            # Check latency against P99 Service Level Objective (SLO)
            if duration_ms > SLO_LATENCY_THRESHOLD_MS:
                logger.warning(
                    "SLO BREACH: Request exceeded P99 threshold (%sms > %sms) | method=%s path=%s trace_id=%s",
                    duration_ms, SLO_LATENCY_THRESHOLD_MS, request.method, request.path, trace_id
                )

        if trace_id:
            response.headers["X-Trace-ID"] = trace_id
            response.headers["X-Span-ID"] = span_id or ""

        return response
