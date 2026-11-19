"""Create the first administrator for a real deployment.

Interactive:
    python -m scripts.create_admin --email ops@yourstudio.com --name "Studio Ops"
    (password is read with getpass, or from ADMIN_PASSWORD; never echoed)

Container bootstrap (run by docker-entrypoint.sh on every start):
    python -m scripts.create_admin --bootstrap
    Reads ADMIN_EMAIL / ADMIN_PASSWORD / ADMIN_NAME. Does nothing if they are unset or the
    account already exists, so it is safe to leave configured. Remove ADMIN_PASSWORD from the
    host's environment once you have signed in and changed the password.
"""
import argparse
import getpass
import os
import sys

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import RoleName, User
from app.services.seed import seed_roles

MIN_PASSWORD = 12


def create(email: str, name: str, password: str, *, exist_ok: bool) -> None:
    if len(password) < MIN_PASSWORD:
        sys.exit(f"Password must be at least {MIN_PASSWORD} characters.")
    with SessionLocal() as db:
        roles = seed_roles(db)
        email = email.strip().lower()
        if db.scalar(select(User.id).where(func.lower(User.email) == email)):
            db.commit()  # keep the seeded roles
            if exist_ok:
                print(f"Administrator bootstrap: {email} already exists, nothing to do.")
                return
            sys.exit(f"A user with email {email} already exists.")
        db.add(User(email=email, full_name=name.strip(), role_id=roles[RoleName.ADMIN].id,
                    password_hash=hash_password(password), job_title="Administrator"))
        db.commit()
    print(f"Administrator {email} created.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a StudioTrack administrator")
    parser.add_argument("--email")
    parser.add_argument("--name")
    parser.add_argument("--bootstrap", action="store_true",
                        help="non-interactive: use ADMIN_EMAIL/ADMIN_PASSWORD/ADMIN_NAME, skip if present")
    args = parser.parse_args()

    if args.bootstrap:
        email, password = os.environ.get("ADMIN_EMAIL", ""), os.environ.get("ADMIN_PASSWORD", "")
        if not email or not password:
            return  # not configured: nothing to bootstrap
        create(email, os.environ.get("ADMIN_NAME") or "Administrator", password, exist_ok=True)
        return

    if not args.email or not args.name:
        parser.error("--email and --name are required (or use --bootstrap)")
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass(f"Password (min {MIN_PASSWORD} chars): ")
    create(args.email, args.name, password, exist_ok=False)


if __name__ == "__main__":
    main()
