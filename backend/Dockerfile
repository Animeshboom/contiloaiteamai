# StudioTrack API (+ bundled Gmail MCP server, spawned over stdio)
# Build from the repository root:  docker build -f backend/Dockerfile .
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app/backend

COPY backend/requirements.txt ./requirements.txt
# Patched packaging tools first (the base image's setuptools has known advisories), then app deps.
RUN pip install --upgrade "pip>=25.1" "setuptools>=84.1" \
    && pip install -r requirements.txt

COPY backend/ /app/backend/
COPY mcp_servers/ /app/mcp_servers/

# Run as an unprivileged user; only the data directory is writable.
# The tr strips any Windows CR characters so the entrypoint runs under /bin/sh.
RUN useradd --system --uid 10001 --home /app app \
    && mkdir -p /app/data/uploads /app/data/mail_outbox \
    && chown -R app:app /app/data \
    && tr -d '\015' < /app/backend/docker-entrypoint.sh > /tmp/entrypoint.sh \
    && mv /tmp/entrypoint.sh /app/backend/docker-entrypoint.sh \
    && chmod 0755 /app/backend/docker-entrypoint.sh

ENV UPLOAD_DIR=/app/data/uploads \
    MAIL_OUTBOX_DIR=/app/data/mail_outbox \
    GMAIL_MCP_DIR=/app/mcp_servers

USER app
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT', '8000')).status == 200 else 1)"

ENTRYPOINT ["/app/backend/docker-entrypoint.sh"]
