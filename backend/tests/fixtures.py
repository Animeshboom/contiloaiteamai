"""Test fixtures: a small studio (users, teams, projects) loaded before every test.

Test-only. Nothing here ships in the application or is seeded into a real database.
"""
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.core.timeutils import studio_today
from app.models import (
    AuthorizedRecipient, Episode, Project, ProjectStatus, ProjectType, RoleName, Scene, Team, User,
)
from app.services.seed import seed_roles

DEMO_PASSWORDS = {
    RoleName.ADMIN: "Admin@12345",
    RoleName.TEAM_LEAD: "Lead@12345",
    RoleName.ARTIST: "Artist@12345",
}

DEMO_USERS = [
    # email, full name, role, team key, title
    ("admin@studiotrack.demo", "Demo Admin", RoleName.ADMIN, None, "Studio Administrator"),
    ("lead.anim@studiotrack.demo", "Priya Raman (Demo Lead)", RoleName.TEAM_LEAD, "anim", "Animation Lead"),
    ("lead.comp@studiotrack.demo", "Marcus Hale (Demo Lead)", RoleName.TEAM_LEAD, "comp", "Compositing Lead"),
    ("artist.arjun@studiotrack.demo", "Arjun Mehta (Demo Artist)", RoleName.ARTIST, "anim", "AI Animator"),
    ("artist.sara@studiotrack.demo", "Sara Okafor (Demo Artist)", RoleName.ARTIST, "anim", "AI Animator"),
    ("artist.leo@studiotrack.demo", "Leo Tanaka (Demo Artist)", RoleName.ARTIST, "anim", "Prompt Artist"),
    ("artist.nina@studiotrack.demo", "Nina Petrova (Demo Artist)", RoleName.ARTIST, "comp", "Compositor"),
    ("artist.dev@studiotrack.demo", "Dev Kapoor (Demo Artist)", RoleName.ARTIST, "comp", "Compositor"),
]

DEMO_TEAMS = {
    "anim": ("Animation Unit (Demo)", "Animation"),
    "comp": ("Compositing Unit (Demo)", "Compositing"),
}



def seed_demo(db: Session) -> None:
    roles = seed_roles(db)
    if db.scalar(select(User).where(User.email == "admin@studiotrack.demo")):
        db.commit()
        return  # already seeded

    teams: dict[str, Team] = {}
    for key, (name, dept) in DEMO_TEAMS.items():
        teams[key] = Team(name=name, department=dept, description="Demo team")
        db.add(teams[key])
    db.flush()

    hashes = {r: hash_password(p) for r, p in DEMO_PASSWORDS.items()}
    users: dict[str, User] = {}
    for email, name, role, team_key, title in DEMO_USERS:
        u = User(
            email=email, full_name=name, password_hash=hashes[role], role_id=roles[role].id,
            team_id=teams[team_key].id if team_key else None, job_title=title,
        )
        db.add(u)
        users[email] = u
    db.flush()
    teams["anim"].lead_id = users["lead.anim@studiotrack.demo"].id
    teams["comp"].lead_id = users["lead.comp@studiotrack.demo"].id

    db.add_all([
        AuthorizedRecipient(email="producer@studiotrack.demo", name="Demo Producer"),
        AuthorizedRecipient(email="studio.head@studiotrack.demo", name="Demo Studio Head"),
    ])

    today = studio_today()
    admin = users["admin@studiotrack.demo"]
    p1 = Project(
        code="NEON-01", title="Neon Monsoon (Demo)", project_type=ProjectType.SERIES, status=ProjectStatus.ACTIVE,
        description="Demo AI-generated sci-fi series set in a rain-soaked megacity.",
        start_date=today - timedelta(days=30), expected_completion_date=today + timedelta(days=90),
        team_id=teams["anim"].id, created_by_id=admin.id,
    )
    p2 = Project(
        code="LAST-LTR", title="The Last Letter (Demo)", project_type=ProjectType.SHORT_FILM,
        status=ProjectStatus.ACTIVE, description="Demo short film: a postal worker's final delivery.",
        start_date=today - timedelta(days=10), expected_completion_date=today + timedelta(days=45),
        team_id=teams["comp"].id, created_by_id=admin.id,
    )
    db.add_all([p1, p2])
    db.flush()
    _episodes(db, p1, [(1, "Pilot: Static Rain", 6), (2, "Circuit Bloom", 5)])
    _episodes(db, p2, [(1, "Full Film", 8)])
    db.commit()


def _episodes(db: Session, project: Project, spec: list[tuple[int, str, int]]) -> None:
    for number, title, scene_count in spec:
        ep = Episode(project_id=project.id, episode_number=number, title=title)
        db.add(ep)
        db.flush()
        for n in range(1, scene_count + 1):
            db.add(Scene(episode_id=ep.id, scene_number=n, title=f"Scene {n:02d}",
                         description=f"{title} — shot sequence {n:02d}"))
