from datetime import timedelta

import jwt
import pytest
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import require_admin, require_lead_or_admin
from app.core.timeutils import utcnow
from app.main import app
from app.models import AuditLog, User
from tests.conftest import ADMIN, ARTIST, LEAD, login, password_for

# Probe routes used only by tests to exercise the RBAC guards in isolation.
_probe = APIRouter(prefix="/__probe")


@_probe.get("/admin")
def _admin_only(_=Depends(require_admin)):
    return {"ok": True}


@_probe.get("/lead")
def _lead_or_admin(_=Depends(require_lead_or_admin)):
    return {"ok": True}


app.include_router(_probe)


def test_login_success_returns_token_and_user(client):
    r = client.post("/api/v1/auth/login", json={"email": ADMIN, "password": password_for(ADMIN)})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == ADMIN
    assert body["user"]["role"] == "admin"
    assert "password_hash" not in body["user"]


def test_login_is_case_insensitive_on_email(client):
    r = client.post("/api/v1/auth/login", json={"email": ADMIN.upper(), "password": password_for(ADMIN)})
    assert r.status_code == 200


@pytest.mark.parametrize("email,password", [(ADMIN, "wrong-password"), ("nobody@studiotrack.demo", "x")])
def test_login_failure_is_generic(client, email, password):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 401
    assert r.json()["detail"] == "Invalid email or password"


def test_login_validation_error(client):
    r = client.post("/api/v1/auth/login", json={"email": "not-an-email", "password": ""})
    assert r.status_code == 422


def test_login_writes_audit_log(client, db):
    login(client, ARTIST)
    client.post("/api/v1/auth/login", json={"email": ARTIST, "password": "bad"})
    actions = db.scalars(select(AuditLog.action).order_by(AuditLog.id)).all()
    assert "auth.login" in actions and "auth.login_failed" in actions


def test_me_requires_auth(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    bad = {"Authorization": "Bearer not.a.jwt"}
    assert client.get("/api/v1/auth/me", headers=bad).status_code == 401


def test_me_returns_current_user(client, as_lead):
    r = client.get("/api/v1/auth/me", headers=as_lead)
    assert r.status_code == 200
    assert r.json()["email"] == LEAD
    assert r.json()["role"] == "team_lead"
    assert r.json()["team"]["name"] == "Animation Unit (Demo)"


def test_expired_token_rejected(client, db):
    user = db.scalar(select(User).where(User.email == ADMIN))
    s = get_settings()
    token = jwt.encode(
        {"sub": str(user.id), "tv": 0, "exp": utcnow() - timedelta(minutes=1)}, s.jwt_secret_key, algorithm="HS256"
    )
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_forged_token_with_wrong_secret_rejected(client, db):
    user = db.scalar(select(User).where(User.email == ARTIST))
    token = jwt.encode({"sub": str(user.id), "role": "admin", "tv": 0, "exp": utcnow() + timedelta(hours=1)},
                       "attacker-secret-attacker-secret-1234", algorithm="HS256")
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_role_claim_in_token_is_not_trusted(client, db):
    """Even a validly-signed token claiming 'admin' only gets the DB role's permissions."""
    user = db.scalar(select(User).where(User.email == ARTIST))
    s = get_settings()
    token = jwt.encode({"sub": str(user.id), "role": "admin", "tv": 0, "exp": utcnow() + timedelta(hours=1)},
                       s.jwt_secret_key, algorithm="HS256")
    assert client.get("/__probe/admin", headers={"Authorization": f"Bearer {token}"}).status_code == 403


def test_deactivated_user_cannot_login_or_use_existing_token(client, db):
    headers = login(client, ARTIST)
    user = db.scalar(select(User).where(User.email == ARTIST))
    user.is_active = False
    db.commit()
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    r = client.post("/api/v1/auth/login", json={"email": ARTIST, "password": password_for(ARTIST)})
    assert r.status_code == 401


def test_change_password_revokes_old_tokens(client):
    old = login(client, ARTIST)
    r = client.post("/api/v1/auth/change-password", headers=old,
                    json={"current_password": password_for(ARTIST), "new_password": "NewPassw0rd!"})
    assert r.status_code == 200
    new = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert client.get("/api/v1/auth/me", headers=old).status_code == 401
    assert client.get("/api/v1/auth/me", headers=new).status_code == 200
    login(client, ARTIST, "NewPassw0rd!")


def test_change_password_requires_correct_current(client, as_artist):
    r = client.post("/api/v1/auth/change-password", headers=as_artist,
                    json={"current_password": "wrong", "new_password": "NewPassw0rd!"})
    assert r.status_code == 422


@pytest.mark.parametrize("who,admin_code,lead_code", [(ADMIN, 200, 200), (LEAD, 403, 200), (ARTIST, 403, 403)])
def test_role_guards(client, who, admin_code, lead_code):
    h = login(client, who)
    assert client.get("/__probe/admin", headers=h).status_code == admin_code
    assert client.get("/__probe/lead", headers=h).status_code == lead_code
