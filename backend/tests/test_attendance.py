from datetime import timedelta

from sqlalchemy import select

from app.core.timeutils import studio_day_bounds_utc, studio_today, utcnow
from app.models import Attendance, AuditLog
from tests.conftest import ARTIST, ARTIST_OTHER_TEAM, uid


def test_check_in_and_out_flow(client, as_artist, db):
    r = client.get("/api/v1/attendance/today", headers=as_artist).json()
    assert r["can_check_in"] and not r["can_check_out"]

    r = client.post("/api/v1/attendance/check-in", headers=as_artist)
    assert r.status_code == 200 and r.json()["status"] == "present" and r.json()["check_in_at"]

    # Simulate a full shift before checking out.
    rec = db.scalar(select(Attendance).where(Attendance.user_id == uid(db, ARTIST)))
    rec.check_in_at = utcnow() - timedelta(hours=8)
    db.commit()

    r = client.post("/api/v1/attendance/check-out", headers=as_artist)
    assert r.status_code == 200
    assert r.json()["status"] == "present" and r.json()["worked_minutes"] >= 479
    t = client.get("/api/v1/attendance/today", headers=as_artist).json()
    assert not t["can_check_in"] and not t["can_check_out"]


def test_duplicate_check_in_rejected(client, as_artist):
    assert client.post("/api/v1/attendance/check-in", headers=as_artist).status_code == 200
    r = client.post("/api/v1/attendance/check-in", headers=as_artist)
    assert r.status_code == 409 and "Already checked in" in r.json()["detail"]


def test_check_out_without_check_in_rejected(client, as_artist):
    r = client.post("/api/v1/attendance/check-out", headers=as_artist)
    assert r.status_code == 409


def test_double_check_out_rejected(client, as_artist):
    client.post("/api/v1/attendance/check-in", headers=as_artist)
    assert client.post("/api/v1/attendance/check-out", headers=as_artist).status_code == 200
    assert client.post("/api/v1/attendance/check-out", headers=as_artist).status_code == 409


def test_short_shift_becomes_half_day(client, as_artist):
    client.post("/api/v1/attendance/check-in", headers=as_artist)
    r = client.post("/api/v1/attendance/check-out", headers=as_artist)
    assert r.json()["status"] == "half_day"


def test_cannot_check_in_on_leave_day(client, as_artist, as_lead, db):
    client.put("/api/v1/attendance/correct", headers=as_lead, json={
        "user_id": uid(db, ARTIST), "work_date": str(studio_today()), "status": "leave", "reason": "Sick leave"})
    r = client.post("/api/v1/attendance/check-in", headers=as_artist)
    assert r.status_code == 409 and "leave" in r.json()["detail"]


def test_roster_shows_not_checked_in_and_absent(client, as_lead, as_artist, db):
    _backdate_accounts(db, 5)
    client.post("/api/v1/attendance/check-in", headers=as_artist)
    rows = {r["full_name"]: r["status"] for r in client.get("/api/v1/attendance/roster", headers=as_lead).json()}
    assert rows["Arjun Mehta (Demo Artist)"] == "present"
    assert rows["Sara Okafor (Demo Artist)"] == "not_checked_in"
    assert "Nina Petrova (Demo Artist)" not in rows  # other team

    yesterday = studio_today() - timedelta(days=1)
    rows = client.get(f"/api/v1/attendance/roster?on={yesterday}", headers=as_lead).json()
    assert all(r["status"] == "absent" for r in rows)


def test_correction_by_lead_is_audited(client, as_lead, db):
    d = studio_today() - timedelta(days=1)
    start, _ = studio_day_bounds_utc(d)
    body = {"user_id": uid(db, ARTIST), "work_date": str(d), "status": "present",
            "check_in_at": (start + timedelta(hours=10)).isoformat(),
            "check_out_at": (start + timedelta(hours=18)).isoformat(), "reason": "Forgot to check in"}
    r = client.put("/api/v1/attendance/correct", headers=as_lead, json=body)
    assert r.status_code == 200, r.text
    assert r.json()["corrected_by_id"] is not None and r.json()["notes"] == "Forgot to check in"

    body["status"] = "half_day"
    client.put("/api/v1/attendance/correct", headers=as_lead, json=body)
    logs = db.scalars(select(AuditLog).where(AuditLog.action == "attendance.correct").order_by(AuditLog.id)).all()
    assert len(logs) == 2
    assert logs[0].before is None and logs[1].before["status"] == "present"
    assert logs[1].after["status"] == "half_day"


def test_correction_validation(client, as_lead, db):
    d = studio_today() - timedelta(days=1)
    start, _ = studio_day_bounds_utc(d)
    base = {"user_id": uid(db, ARTIST), "work_date": str(d), "reason": "fix"}
    # times on a different date
    r = client.put("/api/v1/attendance/correct", headers=as_lead, json={
        **base, "status": "present", "check_in_at": (start - timedelta(hours=5)).isoformat()})
    assert r.status_code == 422
    # check-out before check-in
    r = client.put("/api/v1/attendance/correct", headers=as_lead, json={
        **base, "status": "present", "check_in_at": (start + timedelta(hours=12)).isoformat(),
        "check_out_at": (start + timedelta(hours=11)).isoformat()})
    assert r.status_code == 422
    # future dates only allow leave
    future = str(studio_today() + timedelta(days=3))
    r = client.put("/api/v1/attendance/correct", headers=as_lead,
                   json={**base, "work_date": future, "status": "present"})
    assert r.status_code == 422
    r = client.put("/api/v1/attendance/correct", headers=as_lead,
                   json={**base, "work_date": future, "status": "leave"})
    assert r.status_code == 200


def test_lead_cannot_correct_other_team_and_artist_cannot_correct(client, as_lead, as_artist, db):
    body = {"user_id": uid(db, ARTIST_OTHER_TEAM), "work_date": str(studio_today()), "status": "leave",
            "reason": "x" * 5}
    assert client.put("/api/v1/attendance/correct", headers=as_lead, json=body).status_code == 403
    body["user_id"] = uid(db, ARTIST)
    assert client.put("/api/v1/attendance/correct", headers=as_artist, json=body).status_code == 403


def test_history_scoping(client, as_artist, as_lead, as_admin, db):
    client.post("/api/v1/attendance/check-in", headers=as_artist)
    assert len(client.get("/api/v1/attendance/me", headers=as_artist).json()) == 1
    assert client.get(f"/api/v1/attendance/users/{uid(db, ARTIST)}", headers=as_artist).status_code == 403
    assert len(client.get(f"/api/v1/attendance/users/{uid(db, ARTIST)}", headers=as_lead).json()) == 1
    assert client.get(f"/api/v1/attendance/users/{uid(db, ARTIST_OTHER_TEAM)}", headers=as_lead).status_code == 404
    assert client.get(f"/api/v1/attendance/users/{uid(db, ARTIST_OTHER_TEAM)}", headers=as_admin).status_code == 200


def _backdate_accounts(db, days: int):
    from app.models import User
    for u in db.scalars(select(User)):
        u.created_at = utcnow() - timedelta(days=days)
    db.commit()


def test_summary_counts(client, as_lead, as_artist, db):
    _backdate_accounts(db, 30)
    client.post("/api/v1/attendance/check-in", headers=as_artist)
    days = client.get("/api/v1/attendance/summary", headers=as_lead).json()
    assert len(days) == 14
    assert days[-1]["present"] == 1
    assert days[-2]["absent"] == 4  # lead + 3 artists, nobody checked in yesterday


def test_no_absences_before_account_existed(client, as_lead):
    """Accounts created today must not show as absent on earlier days."""
    days = client.get("/api/v1/attendance/summary", headers=as_lead).json()
    assert all(d["absent"] == 0 for d in days[:-1])
    yesterday = studio_today() - timedelta(days=1)
    assert client.get(f"/api/v1/attendance/roster?on={yesterday}", headers=as_lead).json() == []
