# syntax=docker/dockerfile:1

# Image for deploying the seating app (e.g. with Dokploy).
# Mirrors the Procfile: gunicorn serving `server:app`.

# ---------------------------------------------------------------------------
# Build stage
#
# psycopg2 is the source distribution (not psycopg2-binary), so it has to be
# compiled here against the libpq headers. Doing that in a throwaway stage
# keeps the compiler and the -dev packages out of the shipped image.
# ---------------------------------------------------------------------------
FROM python:3.14-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copied on its own so the dependency layer is only rebuilt when the pins change.
COPY requirements.txt ./
RUN pip install -r requirements.txt

# ---------------------------------------------------------------------------
# Runtime stage
# ---------------------------------------------------------------------------
FROM python:3.14-slim

# libpq5 is the runtime half of libpq-dev; psycopg2 links against libpq.so.5.
RUN apt-get update \
    && apt-get install --no-install-recommends -y libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 app

COPY --from=builder /opt/venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FLASK_APP=server \
    PORT=5000

WORKDIR /app
COPY --chown=app:app . .

# Flask-Caching stores Cal1Card photos here (CACHE_DIR in server/cache.py), so
# it has to exist and be writable by the unprivileged user.
RUN mkdir -p /app/.cache && chown app:app /app/.cache

USER app

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c 'import os, urllib.request; urllib.request.urlopen("http://127.0.0.1:" + os.environ.get("PORT", "5000") + "/health/")'

# `exec` keeps gunicorn as PID 1 so it gets SIGTERM directly on redeploy.
# Worker count comes from WEB_CONCURRENCY, which gunicorn reads natively.
# The Procfile's 61s timeout was sized for Heroku's 60s router cap; override
# GUNICORN_TIMEOUT if a slower Canvas import needs longer.
CMD ["sh", "-c", "exec gunicorn -b 0.0.0.0:${PORT:-5000} server:app --timeout ${GUNICORN_TIMEOUT:-61} --access-logfile -"]
