from datetime import timedelta

from sqlalchemy import select

from app.core.timeutils import studio_day_bounds_utc, studio_today, utcnow
from app.models import Attendance, AuditLog
from tests.conftest import ARTIST, ARTIST2, ARTIST_OTHER_TEAM, LEAD, uid


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


# ---------------- night shifts, forgotten check-outs, days off ----------------

def _open_shift(db, email, work_date, check_in_at):
    from app.models import AttendanceStatus
    rec = Attendance(user_id=uid(db, email), work_date=work_date, check_in_at=check_in_at,
                     status=AttendanceStatus.PRESENT)
    db.add(rec)
    db.commit()
    return rec.id


def test_night_shift_checks_out_after_midnight(client, as_artist, db):
    yesterday = studio_today() - timedelta(days=1)
    _open_shift(db, ARTIST, yesterday, utcnow() - timedelta(hours=9))  # e.g. in 22:00, now 07:00

    t = client.get("/api/v1/attendance/today", headers=as_artist).json()
    assert t["can_check_out"] and not t["can_check_in"]
    assert t["record"]["work_date"] == str(yesterday)

    r = client.post("/api/v1/attendance/check-out", headers=as_artist)
    assert r.status_code == 200, r.text
    assert r.json()["work_date"] == str(yesterday) and r.json()["worked_minutes"] >= 539
    assert r.json()["status"] == "present"

    t = client.get("/api/v1/attendance/today", headers=as_artist).json()
    assert t["can_check_in"] and not t["can_check_out"]  # the new day starts fresh


def test_open_shift_older_than_max_hours_cannot_be_checked_out(client, as_artist, db):
    _open_shift(db, ARTIST, studio_today() - timedelta(days=2), utcnow() - timedelta(hours=40))
    assert client.post("/api/v1/attendance/check-out", headers=as_artist).status_code == 409


def test_forgotten_check_out_is_auto_closed_at_eod(client, as_artist, db):
    from app.core.timeutils import ensure_utc, studio_eod
    from app.services import attendance_service

    day = studio_today() - timedelta(days=2)
    day_shift = _open_shift(db, ARTIST, day, studio_day_bounds_utc(day)[0] + timedelta(hours=10))  # 10:00
    night = _open_shift(db, ARTIST2, day, studio_eod(day) + timedelta(hours=3))  # began after EOD
    fresh = _open_shift(db, LEAD, studio_today(), utcnow() - timedelta(hours=1))  # still working

    assert attendance_service.auto_close_stale(db) == 2
    db.expire_all()
    a, n, f = (db.get(Attendance, i) for i in (day_shift, night, fresh))
    assert ensure_utc(a.check_out_at) == studio_eod(day) and a.status.value == "present"
    assert "Auto-closed" in a.notes
    assert ensure_utc(n.check_out_at) == ensure_utc(n.check_in_at) and n.status.value == "half_day"
    assert f.check_out_at is None
    assert db.scalar(select(AuditLog).where(AuditLog.action == "attendance.auto_close")) is not None
    assert attendance_service.auto_close_stale(db) == 0  # idempotent

    # The forgotten record does not block today's check-in.
    assert client.post("/api/v1/attendance/check-in", headers=as_artist).status_code == 200


def test_non_working_days_and_holidays_are_day_off_not_absent(client, as_lead, db, monkeypatch):
    from app.core.config import get_settings
    _backdate_accounts(db, 30)
    yesterday = studio_today() - timedelta(days=1)
    s = get_settings()
    monkeypatch.setattr(s, "work_days", [d for d in range(7) if d != yesterday.weekday()])

    rows = client.get(f"/api/v1/attendance/roster?on={yesterday}", headers=as_lead).json()
    assert rows and all(r["status"] == "day_off" for r in rows)
    days = client.get("/api/v1/attendance/summary", headers=as_lead).json()
    assert days[-2]["absent"] == 0
    t = client.get(f"/api/v1/reports/metrics?report_date={yesterday}", headers=as_lead).json()["totals"]
    assert t["absent"] == 0 and t["day_off"] == t["team_members"] and t["attendance_rate_pct"] is None

    monkeypatch.setattr(s, "work_days", list(range(7)))
    monkeypatch.setattr(s, "holidays", [yesterday])
    rows = client.get(f"/api/v1/attendance/roster?on={yesterday}", headers=as_lead).json()
    assert all(r["status"] == "day_off" for r in rows)


def test_staff_monthly_export(client, as_lead, as_artist, as_admin, db):
    import csv
    import io
    _backdate_accounts(db, 40)
    client.post("/api/v1/attendance/check-in", headers=as_artist)
    rec = db.scalar(select(Attendance).where(Attendance.user_id == uid(db, ARTIST)))
    rec.check_in_at = utcnow() - timedelta(hours=8)
    db.commit()
    client.post("/api/v1/attendance/check-out", headers=as_artist)
    today = studio_today()

    r = client.get(f"/api/v1/attendance/export?month={today:%Y-%m}", headers=as_lead)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(r.text.lstrip("\ufeff"))))
    assert rows[0][:4] == ["Name", "Email", "Role", "Team"] and rows[0][-2:] == ["Hours worked", "Attendance %"]
    artist = next(x for x in rows if x[1] == ARTIST)
    assert artist[3 + today.day] == "P" and artist[-6] == "1" and artist[-2].startswith("8:")
    assert all(x[1] != ARTIST_OTHER_TEAM for x in rows[1:])  # lead: own team only
    assert client.get("/api/v1/attendance/export?month=2026-13", headers=as_lead).status_code == 422
    assert client.get(f"/api/v1/attendance/export?month={today:%Y-%m}", headers=as_artist).status_code == 403
