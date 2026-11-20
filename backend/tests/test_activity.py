"""Admin activity log."""
from datetime import timedelta

from app.core.timeutils import studio_today, utcnow
from app.models import User
from tests.conftest import ARTIST2, LEAD, uid

API = "/api/v1"


def test_activity_log_shows_who_changed_what(client, as_admin, as_lead, as_artist, db):
    sara = uid(db, ARTIST2)
    db.get(User, sara).created_at = utcnow() - timedelta(days=5)
    db.commit()
    day = studio_today() - timedelta(days=1)
    r = client.put(f"{API}/attendance/correct", headers=as_lead,
                   json={"user_id": sara, "work_date": str(day), "status": "leave", "reason": "Was on leave"})
    assert r.status_code == 200, r.text
    client.post(f"{API}/attendance/check-in", headers=as_artist)
    client.post(f"{API}/teams", headers=as_admin, json={"name": "Lighting"})

    rows = client.get(f"{API}/activity", headers=as_admin).json()
    correction = next(r for r in rows if r["action"] == "attendance.correct")
    assert correction["actor_id"] == uid(db, LEAD) and correction["actor"]
    assert "corrected staff attendance — " in correction["summary"] and "Was on leave" in correction["summary"]
    assert not any(r["action"] == "attendance.check_in" for r in rows)  # routine, hidden by default
    noisy = client.get(f"{API}/activity?include_noisy=true", headers=as_admin).json()
    assert any(r["action"] == "attendance.check_in" for r in noisy)

    about = client.get(f"{API}/activity?subject_id={sara}", headers=as_admin).json()
    assert {r["action"] for r in about} >= {"attendance.correct"}
    by_lead = client.get(f"{API}/activity?actor_id={uid(db, LEAD)}", headers=as_admin).json()
    assert by_lead and all(r["actor_id"] == uid(db, LEAD) for r in by_lead)
    assert client.get(f"{API}/activity?action=team", headers=as_admin).json()[0]["summary"] == "created a team"
    assert client.get(f"{API}/activity", headers=as_lead).status_code == 403
