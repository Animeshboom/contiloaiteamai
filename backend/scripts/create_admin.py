"""Create the first accounts for a real deployment.

Interactive (one administrator):
    python -m scripts.create_admin --email ops@yourstudio.com --name "Studio Ops"
    (password is read with getpass, or from ADMIN_PASSWORD; never echoed)

Container bootstrap (run by docker-entrypoint.sh on every start):
    python -m scripts.create_admin --bootstrap
    Creates up to three starter accounts from environment variables:
        ADMIN_EMAIL  / ADMIN_PASSWORD  / ADMIN_NAME    -> Admin
        LEAD_EMAIL   / LEAD_PASSWORD   / LEAD_NAME     -> Team Lead of TEAM_NAME
        ARTIST_EMAIL / ARTIST_PASSWORD / ARTIST_NAME   -> Artist in TEAM_NAME
    TEAM_NAME defaults to "Production Team". Any pair left unset is skipped, and accounts that
    already exist are left untouched, so it is safe to keep configured. Remove the *_PASSWORD
    variables from the host once everyone has signed in and changed their password.
"""
import argparse
import getpass
import os
import sys

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.config import get_settings
from app.models import RoleName, Team, User
from app.services import identity
from app.services.seed import seed_roles

MIN_PASSWORD = 8

# env prefix, role, default display name, job title
BOOTSTRAP_ACCOUNTS = [
    ("ADMIN", RoleName.ADMIN, "Studio Admin", "Administrator"),
    ("LEAD", RoleName.TEAM_LEAD, "Team Lead", "Team Lead"),
    ("ARTIST", RoleName.ARTIST, "Artist", "Artist"),
]


def _find(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == email))


def _link_if_needed(user: User, password: str) -> None:
    """With Supabase Auth, an account created before the switch gets (or is linked to) a Supabase login."""
    if get_settings().uses_supabase and not user.auth_user_id:
        user.password_hash, user.auth_user_id = identity.create_login(user.email, password, link_existing=True)
        print(f"Bootstrap: {user.email} linked to Supabase Auth.")


def create(email: str, name: str, password: str, *, exist_ok: bool) -> None:
    """Create one administrator (interactive / ADMIN_* path)."""
    if len(password) < MIN_PASSWORD:
        sys.exit(f"Password must be at least {MIN_PASSWORD} characters.")
    with SessionLocal() as db:
        roles = seed_roles(db)
        email = email.strip().lower()
        existing = _find(db, email)
        if existing:
            _link_if_needed(existing, password)
            db.commit()  # keep the seeded roles
            if exist_ok:
                print(f"Bootstrap: {email} already exists, nothing to do.")
                return
            sys.exit(f"A user with email {email} already exists.")
        password_hash, auth_user_id = identity.create_login(email, password, link_existing=True)
        db.add(User(email=email, full_name=name.strip(), role_id=roles[RoleName.ADMIN].id,
                    password_hash=password_hash, auth_user_id=auth_user_id, job_title="Administrator"))
        db.commit()
    print(f"Administrator {email} created.")


def bootstrap() -> None:
    wanted = []
    for prefix, role, default_name, title in BOOTSTRAP_ACCOUNTS:
        email = os.environ.get(f"{prefix}_EMAIL", "").strip().lower()
        password = os.environ.get(f"{prefix}_PASSWORD", "")
        if not email or not password:
            continue
        if len(password) < MIN_PASSWORD:
            sys.exit(f"{prefix}_PASSWORD must be at least {MIN_PASSWORD} characters.")
        wanted.append((role, email, os.environ.get(f"{prefix}_NAME") or default_name, password, title))
    if not wanted:
        return

    with SessionLocal() as db:
        roles = seed_roles(db)
        team = None
        if any(role != RoleName.ADMIN for role, *_ in wanted):
            team_name = os.environ.get("TEAM_NAME") or "Production Team"
            team = db.scalar(select(Team).where(Team.name == team_name))
            if team is None:
                team = Team(name=team_name, description="Created at first deployment")
                db.add(team)
                db.flush()
                print(f"Bootstrap: team '{team_name}' created.")

        for role, email, name, password, title in wanted:
            existing = _find(db, email)
            if existing:
                _link_if_needed(existing, password)
                print(f"Bootstrap: {email} already exists, nothing to do.")
                continue
            password_hash, auth_user_id = identity.create_login(email, password, link_existing=True)
            user = User(email=email, full_name=name.strip(), role_id=roles[role].id, job_title=title,
                        password_hash=password_hash, auth_user_id=auth_user_id,
                        team_id=team.id if team is not None and role != RoleName.ADMIN else None)
            db.add(user)
            db.flush()
            if role == RoleName.TEAM_LEAD and team.lead_id is None:
                team.lead_id = user.id
            print(f"Bootstrap: {role.value} {email} created.")
        db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create StudioTrack starter accounts")
    parser.add_argument("--email")
    parser.add_argument("--name")
    parser.add_argument("--bootstrap", action="store_true",
                        help="non-interactive: create ADMIN_/LEAD_/ARTIST_ accounts from env vars, skip existing")
    parser.add_argument("--reset-two-step", metavar="EMAIL",
                        help="turn off two-step login for this account (lost phone), so it can be set up again")
    args = parser.parse_args()

    if args.reset_two_step:
        with SessionLocal() as db:
            u = _find(db, args.reset_two_step.strip().lower())
            if not u:
                sys.exit("No account with that email.")
            u.totp_secret, u.totp_enabled = None, False
            u.token_version += 1
            db.commit()
        print(f"Two-step login reset for {args.reset_two_step}. They set it up again at their next sign-in.")
        return

    if args.bootstrap:
        bootstrap()
        return

    if not args.email or not args.name:
        parser.error("--email and --name are required (or use --bootstrap)")
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass(f"Password (min {MIN_PASSWORD} chars): ")
    create(args.email, args.name, password, exist_ok=False)


if __name__ == "__main__":
    main()
