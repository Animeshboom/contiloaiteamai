# Switching StudioTrack to Supabase

StudioTrack runs in **local mode** by default: the API checks passwords itself. Follow these steps to
move the database **and** sign-in to Supabase. Do them in order; the app keeps working in local mode
until step 6.

## What goes where

| Value | Where | Secret? |
|---|---|---|
| Project URL `https://<ref>.supabase.co` | backend `.env` `SUPABASE_URL`, frontend `.env.local` `VITE_SUPABASE_URL` | no |
| Publishable key `sb_publishable_…` | backend `SUPABASE_PUBLISHABLE_KEY`, frontend `VITE_SUPABASE_PUBLISHABLE_KEY` | no |
| Secret key `sb_secret_…` (or legacy `service_role`) | backend `SUPABASE_SERVICE_ROLE_KEY` **only** | **yes** |
| Database connection string | backend `DATABASE_URL` | **yes** |

Never put the secret key or the database password in the frontend, in chat, or in git.

## 1. Lock down sign-ups

Supabase dashboard → **Authentication → Sign In / Providers → Email**:

- Turn **off** "Allow new users to sign up". Accounts are created by the admin inside StudioTrack.
  (Even if someone signs up anyway, the API refuses any Supabase user that is not linked to a
  StudioTrack account, but there is no reason to allow it.)
- "Confirm email" can stay on. Accounts created by StudioTrack are marked as confirmed.

## 2. Copy the keys

**Project Settings → API Keys**: copy the publishable key and the secret key.

## 3. Database connection string

Click **Connect** (top of the dashboard) → **Session pooler** → copy the URI, put in your database password,
and add `?sslmode=require` at the end:

```
DATABASE_URL=postgresql://postgres.<ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres?sslmode=require
```

## 4. Backend `.env`

```
AUTH_PROVIDER=supabase
SUPABASE_URL=https://<ref>.supabase.co
SUPABASE_PUBLISHABLE_KEY=sb_publishable_...
SUPABASE_SERVICE_ROLE_KEY=sb_secret_...
LOGIN_ID_EMAIL_DOMAIN=staff.studiotrack.app
DATABASE_URL=...from step 3...
EMAIL_ENABLED=false
```

`SUPABASE_JWT_SECRET` stays empty for new projects: the API checks tokens against the project's public
signing keys automatically. Only projects still on the legacy HS256 "JWT secret" need it.

## 5. Create the tables and the first admin

```bash
cd backend
python -m alembic upgrade head                     # creates every table and turns on RLS
ADMIN_EMAIL=you@studio.com ADMIN_PASSWORD='a-long-password' ADMIN_NAME="Your Name" \
  python -m scripts.create_admin --bootstrap       # also creates the admin's Supabase login
```

Migration `0005` turns on **Row Level Security** on every table. That matters on Supabase: without it,
anyone with the (public) publishable key could read the tables through Supabase's Data API. The
StudioTrack API connects as the table owner, so it is not affected.

## 6. Frontend `.env.local`

Uncomment the three lines in `frontend/.env.local` (URL, publishable key, login ID email domain), then restart
`npm run dev`. The login page now signs in through Supabase with an email or an Employee ID (EMP001).

## 7. Check

- Sign in as the admin. Add an artist without an email; note the Employee ID and password shown once.
- Sign in as that artist with the Employee ID. Signing in on a second device signs the first one out.
- In Supabase **Authentication → Users** you see `emp001@staff.studiotrack.app` etc.

## Going back to local mode

Set `AUTH_PROVIDER=local` and comment out the frontend `VITE_SUPABASE_*` lines. Accounts created while on
Supabase have no local password: reset them from the admin screens.

## Hosting notes

- Render: add the same backend variables. Vercel: add the three `VITE_*` variables and redeploy (Vite bakes
  them in at build time).
- Email stays off (`EMAIL_ENABLED=false`) until Gmail is set up (`docs/GMAIL_SETUP.md`); notifications are
  in-app only. WhatsApp can be added later as a channel (`backend/app/services/channels.py`).
