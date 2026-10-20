# ============================================================
# OpenCampus OSS — Docker image
# ============================================================
# Multi-stage build:
#   builder  — installs Python dependencies into a venv
#   runtime  — slim final image without build tools
#
# Build:
#   docker build -t opencampus-oss .
#
# Run (development, SQLite):
#   docker run -p 5000:5000 opencampus-oss
#
# Run (production, with docker-compose):
#   docker-compose up

# ── Stage 1: dependency builder ──────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build deps for any C-extension wheels (psycopg2-binary, nh3, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only the dependency manifest first so Docker's layer cache is
# invalidated only when requirements.txt changes, not on every code edit.
COPY requirements.txt .

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt


# ── Stage 2: runtime image ───────────────────────────────────
FROM python:3.12-slim AS runtime

# Non-root user for security.
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid 1000 --no-create-home appuser

WORKDIR /app

# Copy the pre-built venv from the builder stage.
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application source.
COPY . .

# Create the instance directory (SQLite file + crash reports) and fix ownership.
RUN mkdir -p /app/instance/crash_reports \
    && chown -R appuser:appgroup /app

USER appuser

# ── Runtime defaults ─────────────────────────────────────────
ENV OPENCAMPUS_ENV=production \
    PORT=5000 \
    OPENCAMPUS_DATA_DIR=/app/instance \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 5000

# Health check — Docker/Compose will mark the container healthy once /healthz
# returns 200 a few times in a row.
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/healthz')"

# Gunicorn via gunicorn.conf.py.  Falls back to waitress if gunicorn is not
# installed (Windows hosts / non-Linux CI runners).
CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:create_app()"]
