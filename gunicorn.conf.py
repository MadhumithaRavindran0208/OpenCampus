"""
Gunicorn configuration for OpenCampus OSS.

Usage:
    gunicorn -c gunicorn.conf.py "app:create_app()"

Environment variables respected at launch time:
    PORT            - TCP port to bind (default: 5000)
    WEB_CONCURRENCY - Number of worker processes (default: 2×CPU+1, capped at 9)
    GUNICORN_TIMEOUT - Worker timeout in seconds (default: 30)
    OPENCAMPUS_ENV  - Set to "production" to use production logging

Reference:
    https://docs.gunicorn.org/en/stable/settings.html
"""
import multiprocessing
import os

# ---------------------------------------------------------------------------
# Binding
# ---------------------------------------------------------------------------
_port = int(os.environ.get("PORT", 5000))
bind = f"0.0.0.0:{_port}"

# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------
# Sync workers are correct for this app (Flask + SQLite WAL = thread-safe
# reads/writes; no async I/O required until you add gevent/eventlet for
# WebSocket support).
worker_class = "sync"

# Standard formula: 2×CPU + 1, capped at 9 to avoid SQLite WAL contention.
# SQLite WAL mode allows concurrent readers + one writer, so more than ~9
# workers rarely helps and increases memory pressure on small VMs.
_cpu = multiprocessing.cpu_count()
_default_workers = min(2 * _cpu + 1, 9)
workers = int(os.environ.get("WEB_CONCURRENCY", _default_workers))

# Each worker can serve multiple clients with threads.
threads = int(os.environ.get("GUNICORN_THREADS", 4))

# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------
# SSE long-poll connections must not be killed by the 30-second default.
# Set the keepalive timeout high; SSE routes emit heartbeats every 25s so
# upstream proxies and the OS TCP stack keep the connection alive.
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 30))
keepalive = 5            # seconds to wait for next request on a keep-alive conn
graceful_timeout = 20    # time for workers to finish inflight requests on reload

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
accesslog = "-"           # stdout → captured by Docker / systemd
errorlog  = "-"           # stderr
loglevel  = os.environ.get("GUNICORN_LOGLEVEL", "info")

# Use the same structured JSON format as the Flask app in production.
_is_production = os.environ.get("OPENCAMPUS_ENV", "development").lower() == "production"
if _is_production:
    # JSON-formatted access log consumed by Loki / CloudWatch / Datadog.
    access_log_format = (
        '{"ts":"%(t)s","method":"%(m)s","path":"%(U)s","status":%(s)s,'
        '"bytes":%(b)s,"duration_ms":%(D)s,"ip":"%(h)s"}'
    )

# ---------------------------------------------------------------------------
# Process naming
# ---------------------------------------------------------------------------
proc_name = "opencampus-oss"

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
# Drop privilege to a non-root user in production if started as root.
# Leave blank for development / Docker containers that already run as non-root.
# user  = "www-data"
# group = "www-data"

# ---------------------------------------------------------------------------
# Server hooks
# ---------------------------------------------------------------------------
def on_starting(server):
    server.log.info("Gunicorn starting: %d workers, port %d", workers, _port)

def worker_exit(server, worker):
    server.log.info("Worker PID %s exited", worker.pid)
