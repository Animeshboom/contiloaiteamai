from datetime import date, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.timeutils import studio_day_bounds_utc, studio_eod
from app.models import Episode, Role, Scene, Team, User
from app.services.seed import seed_demo


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_seed_is_idempotent(db):
    before = db.scalar(select(func.count(User.id)))
    seed_demo(db)
    seed_demo(db)
    assert db.scalar(select(func.count(User.id))) == before == 8
    assert db.scalar(select(func.count(Role.id))) == 3


def test_seed_links_team_leads(db):
    team = db.scalar(select(Team).where(Team.name == "Animation Unit (Demo)"))
    assert team.lead.email == "lead.anim@studiotrack.demo"
    assert {m.email for m in team.members} >= {"artist.arjun@studiotrack.demo", "artist.sara@studiotrack.demo"}


def test_unique_scene_number_per_episode(db):
    ep = db.scalars(select(Episode)).first()
    db.add(Scene(episode_id=ep.id, scene_number=1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_studio_day_bounds_use_configured_timezone():
    tz = get_settings().tz
    start, end = studio_day_bounds_utc(date(2026, 3, 10))
    assert start.tzinfo == timezone.utc
    assert start.astimezone(tz).hour == 0 and end.astimezone(tz).hour == 23
    eod = studio_eod(date(2026, 3, 10))
    assert eod.astimezone(tz).hour == get_settings().eod_deadline_hour


def test_unknown_routes_and_errors_do_not_leak_internals(client):
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert "Traceback" not in r.text


def test_cors_allows_frontend_origin(client):
    r = client.options("/api/v1/auth/login", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
    })
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    r = client.options("/api/v1/auth/login", headers={
        "Origin": "http://evil.example", "Access-Control-Request-Method": "POST",
    })
    assert "access-control-allow-origin" not in r.headers



def test_production_refuses_placeholder_secrets():
    from app.core.config import Settings
    bad = Settings(environment="production", jwt_secret_key="dev-only-secret-change-me-0123456789abcdef",
                   email_approval_secret="change-me-to-a-long-random-string-at-least-32-chars", email_provider="mock",
                   database_url="postgresql+psycopg://studiotrack:studiotrack@localhost:5434/studiotrack")
    problems = " ".join(bad.production_problems())
    assert "JWT_SECRET_KEY" in problems and "EMAIL_APPROVAL_SECRET" in problems and "EMAIL_PROVIDER" in problems
    assert "DATABASE_URL" in problems
    good = Settings(environment="production", jwt_secret_key="x" * 48, email_approval_secret="y" * 48,
                    email_provider="mcp", database_url="postgresql+psycopg://u:p@db:5432/studiotrack")
    assert good.production_problems() == []


def test_create_admin_script(db, monkeypatch, capsys):
    import pytest
    from scripts import create_admin
    from app.core.security import verify_password
    monkeypatch.setenv("ADMIN_PASSWORD", "a-very-long-admin-password")
    monkeypatch.setattr("sys.argv", ["create_admin", "--email", "Ops@Example.com", "--name", "Studio Ops"])
    create_admin.main()
    u = db.scalar(select(User).where(User.email == "ops@example.com"))
    assert u.role_name.value == "admin" and verify_password("a-very-long-admin-password", u.password_hash)
    with pytest.raises(SystemExit, match="already exists"):
        create_admin.main()
    monkeypatch.setenv("ADMIN_PASSWORD", "short")
    monkeypatch.setattr("sys.argv", ["create_admin", "--email", "x@example.com", "--name", "X"])
    with pytest.raises(SystemExit, match="at least 12"):
        create_admin.main()
