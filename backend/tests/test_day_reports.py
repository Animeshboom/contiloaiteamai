"""7 PM day report: auto draft for each lead, lead adds issues and sends to the admin, reminder, admin reply."""
from datetime import timedelta

from sqlalchemy import select

from app.core.timeutils import studio_today, utcnow
from app.models import DailyReport, Notification, User
from app.services import lead_service
from tests.conftest import ADMIN, ARTIST, LEAD, login, uid

API = "/api/v1"


def _after(monkeypatch, hours_past_eod):
    monkeypatch.setattr(lead_service, "studio_eod", lambda d: utcnow() - timedelta(hours=hours_past_eod, minutes=1))


def test_evening_draft_send_to_admin_and_reply(client, as_admin, as_lead, db, monkeypatch):
    for u in db.scalars(select(User)):
        u.created_at = utcnow() - timedelta(days=5)
    db.commit()
    artist = login(client, ARTIST)
    client.post(f"{API}/attendance/check-in", headers=artist)
    client.post(f"{API}/attendance/check-out", headers=artist, json={"note": "Finished SC04 comp. Need SC05 plates."})

    _after(monkeypatch, 0)
    assert lead_service.send_evening_summaries(db) >= 1
    draft = db.scalar(select(DailyReport).where(DailyReport.created_by_id == uid(db, LEAD), DailyReport.auto_generated))
    assert draft is not None and draft.report_date == studio_today()
    assert "NOTES FROM THE TEAM" in draft.body and "Need SC05 plates." in draft.body
    note = db.scalar(select(Notification).where(Notification.event_type == "evening_summary",
                                               Notification.user_id == uid(db, LEAD)))
    assert note.link == f"/lead/reports/{draft.id}"
    assert lead_service.send_evening_summaries(db) == 0  # once a day; no second draft

    status = client.get(f"{API}/reports/team-status", headers=as_admin).json()
    mine = next(x for x in status if x["lead_id"] == uid(db, LEAD))
    assert mine["report_id"] == draft.id and mine["submitted_at"] is None
    assert client.get(f"{API}/reports/team-status", headers=as_lead).status_code == 403

    r = client.post(f"{API}/reports/{draft.id}/submit", headers=as_lead, json={"issues": "Render farm slow after 4pm."})
    assert r.status_code == 200 and r.json()["submitted_at"] and r.json()["issues"] == "Render farm slow after 4pm."
    assert client.post(f"{API}/reports/{draft.id}/submit", headers=as_lead, json={}).status_code == 409
    admin_note = db.scalar(select(Notification).where(Notification.event_type == "report_submitted",
                                                     Notification.user_id == uid(db, ADMIN)))
    assert admin_note.link == f"/admin/reports/{draft.id}" and "Render farm" in admin_note.message

    assert client.post(f"{API}/reports/{draft.id}/comment", headers=as_lead, json={"comment": "x"}).status_code == 403
    r = client.post(f"{API}/reports/{draft.id}/comment", headers=as_admin, json={"comment": "Booked extra nodes."})
    assert r.json()["admin_comment"] == "Booked extra nodes."
    assert db.scalar(select(Notification).where(Notification.event_type == "report_comment")).user_id == uid(db, LEAD)

    _after(monkeypatch, 1)
    db.expire_all()  # the report was sent through the API (another session); the real job uses a fresh one
    lead_service.send_report_reminders(db)  # other leads who have not sent get one; this lead has sent
    assert db.scalar(select(Notification).where(Notification.event_type == "report_reminder",
                                               Notification.user_id == uid(db, LEAD))) is None


def test_reminder_when_not_sent(client, as_lead, db, monkeypatch):
    _after(monkeypatch, 1)
    lead_service.send_evening_summaries(db)
    assert lead_service.send_report_reminders(db) >= 1
    assert lead_service.send_report_reminders(db) == 0  # once a day
    rem = db.scalar(select(Notification).where(Notification.event_type == "report_reminder",
                                              Notification.user_id == uid(db, LEAD)))
    assert rem.link.startswith("/lead/reports/")
