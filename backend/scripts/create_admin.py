"""Create the first administrator for a real deployment (no demo data).

    python -m scripts.create_admin --email ops@yourstudio.com --name "Studio Ops"
    docker compose --profile app run --rm api python -m scripts.create_admin --email ... --name ...

The password is read interactively (or from ADMIN_PASSWORD for automation) and never echoed.
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a StudioTrack administrator")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()

    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Password (min 12 chars): ")
    if len(password) < 12:
        sys.exit("Password must be at least 12 characters.")

    with SessionLocal() as db:
        roles = seed_roles(db)
        email = args.email.strip().lower()
        if db.scalar(select(User.id).where(func.lower(User.email) == email)):
            sys.exit(f"A user with email {email} already exists.")
        db.add(User(email=email, full_name=args.name.strip(), role_id=roles[RoleName.ADMIN].id,
                    password_hash=hash_password(password), job_title="Administrator"))
        db.commit()
    print(f"Administrator {email} created.")


if __name__ == "__main__":
    main()
