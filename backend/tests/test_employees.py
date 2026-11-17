from sqlalchemy import select

from app.models import AuditLog
from tests.conftest import ADMIN, ARTIST, ARTIST_OTHER_TEAM, LEAD, login, uid


def _new_user(client, h, **kw):
    body = {"email": "new.artist@studiotrack.demo", "full_name": "New Artist", "role": "artist",
            "password": "Passw0rd!", **kw}
    return client.post("/api/v1/users", headers=h, json=body)


def test_admin_creates_artist_and_lead_who_can_log_in(client, as_admin):
    r = _new_user(client, as_admin, team_id=1, job_title="Animator")
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "artist" and r.json()["team"]["id"] == 1
    login(client, "new.artist@studiotrack.demo", "Passw0rd!")

    r = _new_user(client, as_admin, email="new.lead@studiotrack.demo", role="team_lead")
    assert r.status_code == 201
    assert login(client, "new.lead@studiotrack.demo", "Passw0rd!")


def test_duplicate_email_rejected_case_insensitive(client, as_admin):
    assert _new_user(client, as_admin).status_code == 201
    r = _new_user(client, as_admin, email="NEW.ARTIST@studiotrack.demo")
    assert r.status_code == 409


def test_weak_password_rejected(client, as_admin):
    assert _new_user(client, as_admin, password="short").status_code == 422


def test_only_admin_can_create_or_modify_users(client, as_lead, as_artist, db):
    assert _new_user(client, as_lead).status_code == 403
    assert _new_user(client, as_artist).status_code == 403
    target = uid(db, ARTIST)
    assert client.patch(f"/api/v1/users/{target}", headers=as_lead, json={"full_name": "X"}).status_code == 403
    assert client.post(f"/api/v1/users/{target}/deactivate", headers=as_lead).status_code == 403


def test_artist_cannot_list_users(client, as_artist):
    assert client.get("/api/v1/users", headers=as_artist).status_code == 403


def test_lead_sees_only_own_team(client, as_lead, as_admin):
    emails = {u["email"] for u in client.get("/api/v1/users", headers=as_lead).json()}
    assert ARTIST in emails and LEAD in emails
    assert ARTIST_OTHER_TEAM not in emails and ADMIN not in emails
    all_emails = {u["email"] for u in client.get("/api/v1/users", headers=as_admin).json()}
    assert len(all_emails) == 8


def test_lead_cannot_view_other_team_member(client, as_lead, db):
    assert client.get(f"/api/v1/users/{uid(db, ARTIST_OTHER_TEAM)}", headers=as_lead).status_code == 404


def test_role_change_revokes_tokens_and_is_audited(client, as_admin, db):
    artist_headers = login(client, ARTIST)
    r = client.patch(f"/api/v1/users/{uid(db, ARTIST)}", headers=as_admin, json={"role": "team_lead"})
    assert r.status_code == 200 and r.json()["role"] == "team_lead"
    assert client.get("/api/v1/auth/me", headers=artist_headers).status_code == 401
    entry = db.scalar(select(AuditLog).where(AuditLog.action == "user.update").order_by(AuditLog.id.desc()))
    assert entry.before["role"] == "artist" and entry.after["role"] == "team_lead"


def test_admin_cannot_demote_or_deactivate_self(client, as_admin, db):
    me = uid(db, ADMIN)
    assert client.patch(f"/api/v1/users/{me}", headers=as_admin, json={"role": "artist"}).status_code == 422
    assert client.post(f"/api/v1/users/{me}/deactivate", headers=as_admin).status_code == 422


def test_deactivate_and_reactivate(client, as_admin, db):
    target = uid(db, ARTIST)
    r = client.post(f"/api/v1/users/{target}/deactivate", headers=as_admin)
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert client.post("/api/v1/auth/login", json={"email": ARTIST, "password": "Artist@12345"}).status_code == 401
    listed = {u["email"] for u in client.get("/api/v1/users", headers=as_admin).json()}
    assert ARTIST not in listed
    listed = {u["email"] for u in client.get("/api/v1/users?include_inactive=true", headers=as_admin).json()}
    assert ARTIST in listed
    client.post(f"/api/v1/users/{target}/activate", headers=as_admin)
    login(client, ARTIST)


def test_admin_resets_password(client, as_admin, db):
    r = client.post(f"/api/v1/users/{uid(db, ARTIST)}/reset-password", headers=as_admin,
                    json={"new_password": "Fresh-Pass-1"})
    assert r.status_code == 204
    login(client, ARTIST, "Fresh-Pass-1")


def test_teams_crud_and_lead_configuration(client, as_admin, db):
    new_lead = _new_user(client, as_admin, email="lead.fx@studiotrack.demo", role="team_lead").json()
    r = client.post("/api/v1/teams", headers=as_admin, json={"name": "FX Unit", "department": "VFX",
                                                             "lead_id": new_lead["id"]})
    assert r.status_code == 201, r.text
    team = r.json()
    assert team["lead"]["id"] == new_lead["id"] and team["member_count"] == 1

    # Non-lead cannot be made a team lead
    r = client.patch(f"/api/v1/teams/{team['id']}", headers=as_admin, json={"lead_id": uid(db, ARTIST)})
    assert r.status_code == 422

    # Team with active members cannot be deleted
    assert client.delete(f"/api/v1/teams/{team['id']}", headers=as_admin).status_code == 409
    client.patch(f"/api/v1/users/{new_lead['id']}", headers=as_admin, json={"clear_team": True})
    assert client.delete(f"/api/v1/teams/{team['id']}", headers=as_admin).status_code == 204


def test_lead_sees_only_their_teams(client, as_lead):
    names = [t["name"] for t in client.get("/api/v1/teams", headers=as_lead).json()]
    assert names == ["Animation Unit (Demo)"]


def test_authorized_recipients_admin_only_write(client, as_admin, as_lead):
    r = client.post("/api/v1/recipients", headers=as_admin, json={"email": "cfo@studiotrack.demo", "name": "CFO"})
    assert r.status_code == 201
    assert client.post("/api/v1/recipients", headers=as_lead,
                       json={"email": "x@studiotrack.demo", "name": "X"}).status_code == 403
    rid = r.json()["id"]
    client.patch(f"/api/v1/recipients/{rid}", headers=as_admin, json={"is_active": False})
    active = [x["email"] for x in client.get("/api/v1/recipients?active_only=true", headers=as_lead).json()]
    assert "cfo@studiotrack.demo" not in active and len(active) == 2
