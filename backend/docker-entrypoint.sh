#!/bin/sh
set -e

echo "Applying database migrations..."
alembic upgrade head

if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  echo "Seeding demo data (SEED_DEMO_DATA=true)..."
  python -m scripts.seed
fi

# The API is only reachable through the nginx container, so trust its X-Forwarded-* headers.
# Without this, every user would share nginx's IP for rate limiting and audit logs.
exec uvicorn app.main:app \
  --host 0.0.0.0 --port 8000 \
  --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}" \
  --no-server-header
