"""Idempotent seeding of the fixed roles (admin, team lead, artist).

There is no demo data in the application: the first administrator is created with
`python -m scripts.create_admin` (or the ADMIN_EMAIL/ADMIN_PASSWORD bootstrap at container start).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Role, RoleName

ROLE_DESCRIPTIONS = {
    RoleName.ADMIN: "Full administrative access",
    RoleName.TEAM_LEAD: "Assigns, reviews and reports on team work",
    RoleName.ARTIST: "Performs assigned production work",
}


def seed_roles(db: Session) -> dict[RoleName, Role]:
    existing = {r.name: r for r in db.scalars(select(Role))}
    for name, desc in ROLE_DESCRIPTIONS.items():
        if name not in existing:
            role = Role(name=name, description=desc)
            db.add(role)
            existing[name] = role
    db.flush()
    from app.services.lead_service import ensure_default_phrases  # noqa: PLC0415 (avoid an import cycle)
    ensure_default_phrases(db)
    return existing
