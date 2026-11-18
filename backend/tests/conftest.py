"""Test fixtures.

Tests run against SQLite by default for speed and zero setup. Set TEST_DATABASE_URL to a
Postgres URL to run the same suite against Postgres (the schema is created from models).
"""
import os
import tempfile

_tmpdir = tempfile.mkdtemp(prefix="studiotrack-tests-")
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL", f"sqlite:///{_tmpdir}/test.db")
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["EMAIL_PROVIDER"] = "mock"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["MAIL_OUTBOX_DIR"] = os.path.join(_tmpdir, "mail_outbox")
os.environ["EMAIL_APPROVAL_SECRET"] = "test-approval-secret-0123456789-abcdefghij"
os.environ["GMAIL_BACKEND"] = "mock"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-0123456789abcdef-0123456789"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services.seed import DEMO_PASSWORDS, seed_demo  # noqa: E402
from app.models import RoleName  # noqa: E402

ADMIN = "admin@studiotrack.demo"
LEAD = "lead.anim@studiotrack.demo"
LEAD_OTHER = "lead.comp@studiotrack.demo"
ARTIST = "artist.arjun@studiotrack.demo"
ARTIST2 = "artist.sara@studiotrack.demo"
ARTIST_OTHER_TEAM = "artist.nina@studiotrack.demo"

PASSWORDS = {
    ADMIN: DEMO_PASSWORDS[RoleName.ADMIN],
    LEAD: DEMO_PASSWORDS[RoleName.TEAM_LEAD],
    LEAD_OTHER: DEMO_PASSWORDS[RoleName.TEAM_LEAD],
}


def password_for(email: str) -> str:
    return PASSWORDS.get(email, DEMO_PASSWORDS[RoleName.ARTIST])


@pytest.fixture(autouse=True)
def _fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_demo(db)
    yield


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def login(client: TestClient, email: str, password: str | None = None) -> dict:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password or password_for(email)})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def as_admin(client):
    return login(client, ADMIN)


@pytest.fixture
def as_lead(client):
    return login(client, LEAD)


@pytest.fixture
def as_artist(client):
    return login(client, ARTIST)


def uid(db, email: str) -> int:
    from sqlalchemy import select
    from app.models import User
    return db.scalar(select(User.id).where(User.email == email))
