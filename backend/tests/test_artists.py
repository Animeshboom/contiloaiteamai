"""Artists after merging students in: accounts (email / Employee ID / automatic), CSV import, sign-in by ID,
one device, leave (artists -> lead, leads -> admin), team announcements and holidays, monthly %,
check-out note, 12:00 summaries."""
from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.timeutils import studio_today, utcnow
from app.models import Notification, Team, User
from app.services import lead_service
from tests.conftest import ADMIN, ARTIST, ARTIST2, ARTIST_OTHER_TEAM, LEAD, LEAD_OTHER, login, uid

API = "/api/v1"


def _team_id(db, email):
    return db.scalar(select(User.team_id).where(User.email == email))


def _backdate(db, days=40):
    for u in db.scalars(select(User)):
        u.created_at = utcnow() - timedelta(days=days)
    db.commit()


# ---------------- accounts ----------------

def test_admin_creates_artists_with_email_id_or_automatic_id(client, as_admin, as_lead, db):
    team = _team_id(db, ARTIST)
    r = client.post(f"{API}/artists", headers=as_admin, json={"full_name": "Mira Joshi", "email": "mira@studio.com",
                                                               "team_id": team})
    assert r.status_code == 201, r.text
    assert r.json()["login"] == "mira@studio.com" and len(r.json()["password"]) == 12
    assert r.json()["user"]["role"] == "artist" and r.json()["user"]["team"]["id"] == team

    auto1 = client.post(f"{API}/artists", headers=as_admin, json={"full_name": "Asha Rao"}).json()
    auto2 = client.post(f"{API}/artists", headers=as_admin, json={"full_name": "Ravi Kumar"}).json()
    assert (auto1["login"], auto2["login"]) == ("EMP001", "EMP002")
    typed = client.post(f"{API}/artists", headers=as_admin, json={"full_name": "Dev Shah", "employee_code": "tr-7"})
    assert typed.json()["login"] == "TR-7"

    # sign in with the Employee ID (any case), on the one login box
    h = client.post(f"{API}/auth/login", json={"email": "emp001", "password": auto1["password"]})
    assert h.status_code == 200 and h.json()["user"]["employee_code"] == "EMP001"
    assert client.post(f"{API}/artists", headers=as_admin, json={
        "full_name": "Both", "email": "b@studio.com", "employee_code": "B1"}).status_code == 422
    assert client.post(f"{API}/artists", headers=as_lead, json={"full_name": "Nope"}).status_code == 403
    r = client.post(f"{API}/artists/{auto1['user']['id']}/reset-password", headers=as_admin)
    assert r.status_code == 200 and r.json()["login"] == "EMP001" and r.json()["password"] != auto1["password"]


def test_csv_import(client, as_admin, db):
    content = ("Name,Email,Employee ID,Team,Job title\n"
               "Asha Rao,,,Animation,Trainee\n"
               "Ravi Kumar,ravi@studio.com,,,\n"
               "Bad,,!!,,\n"
               "Dup,ravi@studio.com,,,\n"
               "Nope Team,,,Ghosts,\n"
               ",,,,\n"
               "Both Set,x@studio.com,X1,,\n")
    team = db.get(Team, _team_id(db, ARTIST))
    content = content.replace("Animation", team.name)
    r = client.post(f"{API}/artists/import", headers=as_admin, files={"file": ("a.csv", content, "text/csv")})
    assert r.status_code == 200, r.text
    out = r.json()
    assert [c["login"] for c in out["created"]] == ["EMP001", "ravi@studio.com"]
    assert out["created"][0]["user"]["job_title"] == "Trainee" and out["created"][0]["user"]["team"]["id"] == team.id
    assert {e["row"] for e in out["errors"]} == {4, 5, 6, 8}


def test_artists_one_device_and_no_password_change(client, db):
    first = login(client, ARTIST)
    second = login(client, ARTIST)
    assert client.get(f"{API}/auth/me", headers=first).status_code == 401
    assert client.get(f"{API}/auth/me", headers=second).status_code == 200
    lead_a, lead_b = login(client, LEAD), login(client, LEAD)  # leads may use several devices
    assert client.get(f"{API}/auth/me", headers=lead_a).status_code == 200


# ---------------- leave ----------------

def test_artist_leave_goes_to_team_lead_and_shows_in_attendance(client, as_lead, db):
    _backdate(db)
    artist_h = login(client, ARTIST)
    d = studio_today() - timedelta(days=1)
    r = client.post(f"{API}/me/leave", headers=artist_h, json={"start": str(d), "end": str(d), "reason": "Fever"})
    assert r.status_code == 201, r.text
    leave = r.json()
    assert db.scalar(select(Notification).where(Notification.event_type == "leave_requested")).user_id == uid(db, LEAD)
    other = login(client, LEAD_OTHER)
    assert client.post(f"{API}/leave/{leave['id']}/decide", headers=other, json={"decision": "approved"}).status_code == 403
    assert [x["id"] for x in client.get(f"{API}/leave?status=pending", headers=as_lead).json()] == [leave["id"]]
    assert client.post(f"{API}/leave/{leave['id']}/decide", headers=as_lead,
                       json={"decision": "rejected"}).status_code == 422  # a note is required
    r = client.post(f"{API}/leave/{leave['id']}/decide", headers=as_lead, json={"decision": "approved"})
    assert r.status_code == 200 and r.json()["status"] == "approved"

    roster = {x["user_id"]: x for x in client.get(f"{API}/attendance/roster?on={d}", headers=as_lead).json()}
    assert roster[uid(db, ARTIST)]["status"] == "leave"
    summary = client.get(f"{API}/attendance/summary", headers=as_lead).json()
    assert summary[-2]["leave"] >= 1


def test_lead_leave_is_decided_by_admin(client, as_admin, db):
    lead_h = login(client, LEAD)
    d = studio_today() + timedelta(days=3)
    leave = client.post(f"{API}/me/leave", headers=lead_h, json={"start": str(d), "end": str(d), "reason": "Wedding"}).json()
    note = db.scalar(select(Notification).where(Notification.event_type == "leave_requested"))
    assert note.user_id == uid(db, ADMIN)
    other = login(client, LEAD_OTHER)
    assert client.post(f"{API}/leave/{leave['id']}/decide", headers=other, json={"decision": "approved"}).status_code == 403
    assert client.post(f"{API}/leave/{leave['id']}/decide", headers=lead_h, json={"decision": "approved"}).status_code == 403
    assert client.post(f"{API}/leave/{leave['id']}/decide", headers=as_admin,
                       json={"decision": "approved"}).json()["status"] == "approved"


# ---------------- announcements and holidays by team ----------------

def test_team_announcements(client, as_admin, as_lead, db):
    my_team, other_team = _team_id(db, ARTIST), _team_id(db, ARTIST_OTHER_TEAM)
    r = client.post(f"{API}/announcements", headers=as_lead, json={"title": "Render farm down", "body": "Until 3pm.",
                                                                    "team_ids": [my_team]})
    assert r.status_code == 201, r.text
    assert client.post(f"{API}/announcements", headers=as_lead, json={
        "title": "Not my team", "body": "x", "team_ids": [other_team]}).status_code == 403
    assert client.post(f"{API}/announcements", headers=as_lead, json={"title": "xx", "body": "x"}).status_code == 422
    client.post(f"{API}/announcements", headers=as_admin, json={"title": "Diwali party", "body": "Friday 6pm"})

    mine = [a["title"] for a in client.get(f"{API}/me/announcements", headers=login(client, ARTIST)).json()]
    theirs = [a["title"] for a in client.get(f"{API}/me/announcements", headers=login(client, ARTIST_OTHER_TEAM)).json()]
    assert mine == ["Diwali party", "Render farm down"] and theirs == ["Diwali party"]


def test_team_holiday(client, as_admin, as_lead, db):
    _backdate(db)
    d = studio_today() - timedelta(days=1)
    r = client.post(f"{API}/holidays", headers=as_admin,
                    json={"date": str(d), "name": "Team outing", "team_ids": [_team_id(db, ARTIST)]})
    assert r.status_code == 201 and r.json()["teams"][0]["id"] == _team_id(db, ARTIST)
    lead_roster = {x["user_id"]: x["status"] for x in client.get(
        f"{API}/attendance/roster?on={d}", headers=as_admin).json()}
    assert lead_roster[uid(db, ARTIST)] == "day_off" and lead_roster[uid(db, ARTIST_OTHER_TEAM)] == "absent"


# ---------------- monthly %, check-out note, noon summaries ----------------

def test_month_stats_and_checkout_note(client, as_lead, db, monkeypatch):
    _backdate(db)
    artist_h = login(client, ARTIST)
    client.post(f"{API}/attendance/check-in", headers=artist_h)
    r = client.post(f"{API}/attendance/check-out", headers=artist_h, json={"note": "Lit SC01-02. Blocked on SC03 refs."})
    assert r.status_code == 200 and r.json()["work_note"] == "Lit SC01-02. Blocked on SC03 refs."
    month = client.get(f"{API}/attendance/me/month", headers=artist_h).json()
    assert month["month"] == f"{studio_today():%Y-%m}" and month["counted_days"] >= 1
    row = next(x for x in client.get(f"{API}/attendance/roster", headers=as_lead).json() if x["user_id"] == uid(db, ARTIST))
    assert row["month"]["pct"] is not None
    assert row["month"]["low"] == (row["month"]["pct"] < get_settings().low_attendance_pct)


def test_noon_summaries_for_leads_and_admin(client, as_lead, db, monkeypatch):
    _backdate(db)
    monkeypatch.setattr(get_settings(), "staff_checkin_cutoff_hour", 0)
    client.post(f"{API}/attendance/check-in", headers=login(client, ARTIST))
    assert lead_service.send_noon_summaries(db) >= 2
    assert lead_service.send_noon_summaries(db) == 0  # once per day
    lead_note = db.scalar(select(Notification).where(Notification.event_type == "noon_attendance_summary",
                                                    Notification.user_id == uid(db, LEAD)))
    admin_note = db.scalar(select(Notification).where(Notification.event_type == "noon_attendance_summary",
                                                     Notification.user_id == uid(db, ADMIN)))
    assert lead_note.message.startswith("1 present") and "absent" in lead_note.message
    assert admin_note.message.startswith("Studio: ")
