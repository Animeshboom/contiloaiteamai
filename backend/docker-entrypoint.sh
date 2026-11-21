#!/bin/sh
set -e

# Gmail OAuth files can be supplied as env vars (hosted platforms such as Render) instead of
# mounted files. They are written to the writable data dir so the token can be refreshed.
SECRETS_DIR=/app/data/secrets
if [ -n "$GMAIL_CREDENTIALS_JSON" ]; then
  mkdir -p "$SECRETS_DIR"
  printf '%s' "$GMAIL_CREDENTIALS_JSON" > "$SECRETS_DIR/gmail_credentials.json"
  export GMAIL_CREDENTIALS_FILE="$SECRETS_DIR/gmail_credentials.json"
fi
if [ -n "$GMAIL_TOKEN_JSON" ]; then
  mkdir -p "$SECRETS_DIR"
  printf '%s' "$GMAIL_TOKEN_JSON" > "$SECRETS_DIR/gmail_token.json"
  export GMAIL_TOKEN_FILE="$SECRETS_DIR/gmail_token.json"
fi
[ -d "$SECRETS_DIR" ] && chmod 700 "$SECRETS_DIR" && chmod 600 "$SECRETS_DIR"/*.json
unset GMAIL_CREDENTIALS_JSON GMAIL_TOKEN_JSON

echo "Applying database migrations..."
alembic upgrade head

# Creates the starter admin / team lead / artist from ADMIN_*, LEAD_*, ARTIST_* if set and not yet present.
python -m scripts.create_admin --bootstrap

# Trust X-Forwarded-* from the proxy in front (nginx, Render, Vercel, Hugging Face) so rate limiting and audit
# logs see the real client IP. Restrict FORWARDED_ALLOW_IPS if the API is directly reachable.
exec uvicorn app.main:app \
  --host 0.0.0.0 --port "${PORT:-7860}" \
  --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}" \
  --no-server-header
