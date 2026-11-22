from datetime import date, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.config import get_settings
from app.core.timeutils import studio_day_bounds_utc, studio_eod
from app.models import Episode, Role, Scene, Team, User
from tests.fixtures import seed_demo


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_seed_is_idempotent(db):
    before = db.scalar(select(func.count(User.id)))
    seed_demo(db)
    seed_demo(db)
    assert db.scalar(select(func.count(User.id))) == before == 8
    assert db.scalar(select(func.count(Role.id))) == 3  # admin, team lead, artist


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


def test_cors_origin_regex_allows_preview_origins_only():
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    app_ = Starlette()
    app_.add_middleware(CORSMiddleware, allow_origins=["https://studiotrack-ai.pages.dev"], allow_methods=["POST"],
                        allow_origin_regex=r"^https://[a-z0-9-]+\.studiotrack-ai\.pages\.dev$")
    c = TestClient(app_)

    def allowed(origin):
        r = c.options("/x", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
        return r.headers.get("access-control-allow-origin") == origin

    assert allowed("https://studiotrack-ai.pages.dev")
    assert allowed("https://3f2a1b9c.studiotrack-ai.pages.dev")
    assert not allowed("https://evil.pages.dev")
    assert not allowed("https://x.studiotrack-ai.pages.dev.evil.com")


@pytest.mark.parametrize("configured", [
    "https://studiotrack-ai.pages.dev",
    "https://studiotrack-ai.pages.dev/",
    "https://studiotrack-ai.pages.dev//",
    "  https://studiotrack-ai.pages.dev/ ",
])
def test_cors_origins_are_normalized_and_match_browser_origin(configured, monkeypatch):
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    from app.core.config import Settings

    # Exactly as Render passes it: a JSON array in an environment variable.
    monkeypatch.setenv("CORS_ORIGINS", f'["{configured}", "https://studio.example.com:8443/"]')
    origins = Settings(_env_file=None).cors_origins
    assert origins == ["https://studiotrack-ai.pages.dev", "https://studio.example.com:8443"]

    app_ = Starlette()
    app_.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["POST"], allow_headers=["Content-Type"])
    c = TestClient(app_)

    def allowed(origin):
        r = c.options("/x", headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
        return r.headers.get("access-control-allow-origin") == origin

    assert allowed("https://studiotrack-ai.pages.dev")          # what browsers actually send
    assert allowed("https://studio.example.com:8443")
    assert not allowed("https://studiotrack-ai.pages.dev.evil.com")
    assert not allowed("https://evil.example")
    assert not allowed("http://studiotrack-ai.pages.dev")       # scheme still matters


def test_cors_normalization_does_not_weaken_production_checks():
    from app.core.config import Settings

    good = dict(environment="production", jwt_secret_key="x" * 48, email_approval_secret="y" * 48,
                database_url="postgresql+psycopg://u:p@db:5432/studiotrack", app_base_url="https://studiotrack.example.com",
                email_provider="mcp", gmail_backend="gmail")  # the test env defaults these to mock
    for bad in (["*"], ["*/"], ["http://localhost:5173/"], ["/"], ["", " "], []):
        s = Settings(**good, cors_origins=bad)
        assert any("CORS_ORIGINS" in p for p in s.production_problems()), (bad, s.cors_origins)
    assert Settings(**good, cors_origins=["https://studiotrack.example.com/"]).production_problems() == []


def test_production_refuses_placeholder_secrets():
    from app.core.config import Settings
    bad = Settings(environment="production", jwt_secret_key="dev-only-secret-change-me-0123456789abcdef",
                   email_approval_secret="change-me-to-a-long-random-string-at-least-32-chars", email_provider="mock",
                   database_url="postgresql+psycopg://studiotrack:studiotrack@localhost:5434/studiotrack",
                   cors_origins=["http://localhost:5173", "http://127.0.0.1:5173"])
    problems = " ".join(bad.production_problems())
    assert "JWT_SECRET_KEY" in problems and "EMAIL_APPROVAL_SECRET" in problems and "EMAIL_PROVIDER" in problems
    assert "DATABASE_URL" in problems
    assert "GMAIL_BACKEND" in problems  # test env uses the mock backend
    assert "APP_BASE_URL" in problems
    assert "CORS_ORIGINS" in problems  # still the localhost default
    good_kwargs = dict(environment="production", jwt_secret_key="x" * 48, email_approval_secret="y" * 48,
                       email_provider="mcp", database_url="postgresql+psycopg://u:p@db:5432/studiotrack",
                       gmail_backend="gmail", gmail_credentials_file="/s/creds.json", gmail_token_file="/s/token.json",
                       app_base_url="https://studiotrack.example.com", cors_origins=["https://studiotrack.example.com"])
    assert Settings(**good_kwargs).production_problems() == []
    wildcard = Settings(**{**good_kwargs, "cors_origins": ["*"]})
    assert any("CORS_ORIGINS" in p for p in wildcard.production_problems())
    # Gmail can be added after the first deploy: the app starts, emails wait in the outbox.
    no_gmail = Settings(**{**good_kwargs, "gmail_credentials_file": None, "gmail_token_file": None})
    assert no_gmail.production_problems() == [] and not no_gmail.email_configured
    assert Settings(**good_kwargs).email_configured


def test_database_url_accepts_hosted_postgres_scheme():
    from app.core.config import Settings
    for url in ("postgres://u:p@host:5432/db", "postgresql://u:p@host:5432/db"):
        assert Settings(database_url=url).database_url == "postgresql+psycopg://u:p@host:5432/db"


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
    with pytest.raises(SystemExit, match="at least 8"):
        create_admin.main()


def test_bootstrap_creates_three_starter_accounts(db, monkeypatch, capsys):
    from scripts import create_admin
    from app.models import Team
    monkeypatch.setattr("sys.argv", ["create_admin", "--bootstrap"])
    for prefix in ("ADMIN", "LEAD", "ARTIST"):
        monkeypatch.delenv(f"{prefix}_EMAIL", raising=False)
        monkeypatch.delenv(f"{prefix}_PASSWORD", raising=False)
    create_admin.main()  # nothing configured: silently does nothing
    assert capsys.readouterr().out == ""

    monkeypatch.setenv("ADMIN_EMAIL", "Boot@Example.com")
    monkeypatch.setenv("ADMIN_PASSWORD", "a-very-long-admin-password")
    monkeypatch.setenv("LEAD_EMAIL", "lead@example.com")
    monkeypatch.setenv("LEAD_PASSWORD", "a-very-long-lead-password")
    monkeypatch.setenv("ARTIST_EMAIL", "artist@example.com")
    monkeypatch.setenv("ARTIST_PASSWORD", "a-very-long-artist-password")
    monkeypatch.setenv("TEAM_NAME", "Bootstrap Team")
    create_admin.main()
    create_admin.main()  # second start: no error, no duplicates
    assert "already exists" in capsys.readouterr().out

    db.expire_all()
    admin, lead, artist = (db.scalars(select(User).where(User.email == e)).one()
                           for e in ("boot@example.com", "lead@example.com", "artist@example.com"))
    team = db.scalars(select(Team).where(Team.name == "Bootstrap Team")).one()
    assert admin.role_name.value == "admin" and admin.team_id is None
    assert lead.role_name.value == "team_lead" and lead.team_id == team.id and team.lead_id == lead.id
    assert artist.role_name.value == "artist" and artist.team_id == team.id


def test_bootstrap_rejects_short_password(monkeypatch):
    import pytest
    from scripts import create_admin
    monkeypatch.setattr("sys.argv", ["create_admin", "--bootstrap"])
    monkeypatch.setenv("LEAD_EMAIL", "lead@example.com")
    monkeypatch.setenv("LEAD_PASSWORD", "short")
    with pytest.raises(SystemExit, match="LEAD_PASSWORD must be at least 8"):
        create_admin.main()
