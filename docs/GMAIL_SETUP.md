# Gmail MCP integration

StudioTrack sends email only through its own **Gmail MCP server** (`mcp_servers/gmail_mcp`), which runs inside the application's deployment. Claude Code's MCP connections are not used by the app.

```
backend ──(MCP: stdio subprocess, or streamable HTTP)──▶ gmail_mcp server ──▶ Gmail API (OAuth 2.0)
   │                                                        │                     or mock (.eml files)
   └── email_logs outbox (idempotency keys, retries)        └── read-only policy checks against the StudioTrack DB
```

## Tools

| Tool | Purpose | Server-side checks |
|---|---|---|
| `send_artist_notification` | New assignment, approval, deadline reminder | Recipient must be an **active artist**; the idempotency key must not have been delivered already |
| `send_task_revision_notification` | Revision requested, with the lead's feedback | Same as above; feedback is required |
| `create_daily_report_draft` | Gmail **draft** of an EOD report (never sends) | Every recipient must be an active **authorized recipient** |
| `send_daily_report` | Sends an **approved** EOD report | Report status is `approved`. The recipients must exactly match the approved list. An HMAC `approval_reference` issued by StudioTrack at approval is required. Subject and body are loaded from the DB, not taken from the caller. Not already delivered |

Errors carry a marker the backend uses for retry decisions:
- `BLOCKED:` — policy refusal. The email is never retried.
- `RETRYABLE:` — temporary failure (Gmail 429/5xx or network). Retried with exponential backoff.
- `AUTH:` — the token is missing, expired or revoked. An operator must re-authorize.
- `FAILED:` — a permanent error.

Addresses are masked in server logs, and message bodies are never logged.

## Local development (no Google account needed)

`.env` defaults: `EMAIL_PROVIDER=mcp`, `GMAIL_BACKEND=mock`.

The backend spawns the MCP server and real MCP calls happen. Delivered messages are written to `backend/mail_outbox/*.eml`, so you can open them in any mail client. Admins can see every attempt under **Settings → Email delivery log**.

For tests, `EMAIL_PROVIDER=mock` runs the same tool code in-process (no subprocess) with the same policy checks.

## Production: connect a real Gmail account

1. **Google Cloud Console** → create or select a project → **APIs & Services → Library** → enable **Gmail API**.
2. **OAuth consent screen** → set the user type (Internal if you use Google Workspace) and add the scope `https://www.googleapis.com/auth/gmail.compose`. This is the only scope required: it covers creating drafts and sending. Reading mail is never requested.
3. **Credentials → Create credentials → OAuth client ID → Desktop app**. Download the JSON to `secrets/client_secret.json` (this path is gitignored).
4. Authorize once, as the mailbox that should send studio email:
   ```bash
   cd mcp_servers
   GMAIL_CREDENTIALS_FILE=../secrets/client_secret.json GMAIL_TOKEN_FILE=../secrets/gmail_token.json \
     ../backend/.venv/Scripts/python -m gmail_mcp.authorize
   ```
5. Set the following in `.env`:
   ```
   EMAIL_PROVIDER=mcp
   GMAIL_BACKEND=gmail
   GMAIL_CREDENTIALS_FILE=../secrets/client_secret.json
   GMAIL_TOKEN_FILE=../secrets/gmail_token.json
   EMAIL_APPROVAL_SECRET=<long random value, shared with the MCP server>
   ```
6. Restart the backend. Access tokens refresh automatically, and refreshed tokens are written back to `GMAIL_TOKEN_FILE`. If Google revokes the refresh token, deliveries fail with `AUTH:` and stay queued; re-run step 4, then use **Retry** in the email log.

### Hardening checklist
- Give the MCP server a **read-only** database role. It only runs `SELECT`s on `users`, `roles`, `authorized_recipients`, `daily_reports` and `email_logs`.
- Never expose the MCP HTTP port publicly. In Docker, keep it on the internal network only.
- Store `client_secret.json` and `gmail_token.json` in a secrets manager or a mounted secret, never in the image.
- Rotate `EMAIL_APPROVAL_SECRET` if it leaks. Outstanding report approvals then become invalid and have to be re-approved, which is the safe failure mode.
