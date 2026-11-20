"""Team-lead tools: Today list, reassign, weekly targets, private ratings, feedback phrases, evening summary."""
from datetime import timedelta

from sqlalchemy import select

from app.core.timeutils import utcnow
from app.models import Assignment, AssignmentAssignee, Notification
from app.services import lead_service
from tests.conftest import ARTIST, ARTIST2, ARTIST_OTHER_TEAM, LEAD_OTHER, login, uid
from tests.helpers import _scenes

API = "/api/v1"


def _assign(client, lead, db, who, n=1):
    p, ep, scenes = _scenes(db)
    r = client.post(f"{API}/assignments", headers=lead, json={
        "project_id": p.id, "episode_id": ep.id, "scene_ids": [s.id for s in scenes[:n]], "artist_ids": who})
    assert r.status_code == 201, r.text
    return r.json(), scenes


def _submit(client, h, a, scenes):
    r = client.post(f"{API}/submissions", headers=h, json={
        "assignment_id": a["id"], "scene_ids": [scenes[0].id], "work_description": "First pass", "output_links": []})
    assert r.status_code == 201, r.text
    return r.json()


def test_today_list(client, as_lead, as_artist, db):
    a, scenes = _assign(client, as_lead, db, [uid(db, ARTIST)])
    late, _ = _assign(client, as_lead, db, [uid(db, ARTIST2)])
    db.get(Assignment, late["id"]).deadline = utcnow() - timedelta(hours=1)
    db.commit()
    _submit(client, as_artist, a, scenes)

    t = client.get(f"{API}/lead/today", headers=as_lead).json()
    assert t["counts"]["reviews"] == 1 and t["reviews"][0]["assignment"] == a["title"]
    assert [o["person_id"] for o in t["overdue"]] == [uid(db, ARTIST2)]
    assert all(p["status"] in ("absent", "not_checked_in") for p in t["absent"])
    assert client.get(f"{API}/lead/today", headers=as_artist).status_code == 403


def test_reassign_keeps_history_and_blocks_old_person(client, as_lead, as_artist, db):
    a, scenes = _assign(client, as_lead, db, [uid(db, ARTIST)], n=2)
    _submit(client, as_artist, a, scenes)
    r = client.post(f"{API}/assignments/{a['id']}/reassign", headers=as_lead,
                    json={"from_user_id": uid(db, ARTIST), "to_user_id": uid(db, ARTIST2), "note": "Arjun is out"})
    assert r.status_code == 200, r.text
    slots = {x.user_id: x.status.value for x in db.scalars(
        select(AssignmentAssignee).where(AssignmentAssignee.assignment_id == a["id"]))}
    assert slots == {uid(db, ARTIST): "reassigned", uid(db, ARTIST2): "assigned"}
    # the old person keeps their history but can no longer work on it
    assert client.get(f"{API}/submissions?assignment_id={a['id']}", headers=as_artist).json()
    r = client.put(f"{API}/assignments/{a['id']}/progress", headers=as_artist, json={"reported_progress_pct": 10})
    assert r.status_code == 403
    assert db.scalar(select(Notification).where(Notification.user_id == uid(db, ARTIST),
                                               Notification.event_type == "assignment_reassigned"))
    assert db.scalar(select(Notification).where(Notification.user_id == uid(db, ARTIST2),
                                               Notification.event_type == "assignment_created"))
    # someone outside the lead's people cannot receive it
    r = client.post(f"{API}/assignments/{a['id']}/reassign", headers=as_lead,
                    json={"from_user_id": uid(db, ARTIST2), "to_user_id": uid(db, ARTIST_OTHER_TEAM)})
    assert r.status_code == 403


def test_reassign_without_work_removes_the_slot(client, as_lead, db):
    a, _ = _assign(client, as_lead, db, [uid(db, ARTIST)])
    client.post(f"{API}/assignments/{a['id']}/reassign", headers=as_lead,
                json={"from_user_id": uid(db, ARTIST), "to_user_id": uid(db, ARTIST2)})
    assert [x.user_id for x in db.scalars(select(AssignmentAssignee).where(
        AssignmentAssignee.assignment_id == a["id"]))] == [uid(db, ARTIST2)]


def test_targets_ratings_and_workload(client, as_lead, as_artist, db):
    artist = uid(db, ARTIST)
    r = client.put(f"{API}/targets/{artist}", headers=as_lead, json={"scenes_per_week": 5})
    assert r.status_code == 200 and r.json()["target"] == 5 and r.json()["approved"] == 0
    other = login(client, LEAD_OTHER)
    assert client.put(f"{API}/targets/{artist}", headers=other, json={"scenes_per_week": 9}).status_code == 403

    a, scenes = _assign(client, as_lead, db, [artist])
    sub = _submit(client, as_artist, a, scenes)
    r = client.post(f"{API}/submissions/{sub['id']}/review", headers=as_lead,
                    json={"decision": "approved", "rating": 4, "feedback": "Great work"})
    assert r.status_code == 200 and r.json()["reviews"][0]["rating"] == 4  # the lead sees it
    seen_by_artist = client.get(f"{API}/submissions/{sub['id']}", headers=as_artist).json()
    assert seen_by_artist["reviews"][0]["rating"] is None  # private to leads/admins
    assert client.post(f"{API}/submissions/{sub['id']}/review", headers=as_lead,
                       json={"decision": "approved", "rating": 9}).status_code == 422

    mine = client.get(f"{API}/me/target", headers=as_artist).json()
    assert mine == {**mine, "target": 5, "approved": 1}
    w = next(x for x in client.get(f"{API}/dashboard/overview", headers=as_lead).json()["workload"]
             if x["user_id"] == artist)
    assert w["weekly_target"] == 5 and w["approved_this_week"] == 1 and w["avg_rating"] == 4.0
    assert client.put(f"{API}/targets/{artist}", headers=as_lead, json={"scenes_per_week": None}).json()["target"] is None


def test_feedback_phrases_are_a_studio_list(client, as_admin, as_lead):
    phrases = client.get(f"{API}/feedback-phrases", headers=as_lead).json()
    assert "Fix lighting" in [p["text"] for p in phrases]
    assert client.post(f"{API}/feedback-phrases", headers=as_lead, json={"text": "Nope"}).status_code == 403
    p = client.post(f"{API}/feedback-phrases", headers=as_admin, json={"text": "Add motion blur"}).json()
    assert client.post(f"{API}/feedback-phrases", headers=as_admin, json={"text": "add motion blur"}).status_code == 409
    assert client.delete(f"{API}/feedback-phrases/{p['id']}", headers=as_admin).status_code == 204


def test_evening_summary_once_per_day(client, as_lead, as_artist, db, monkeypatch):
    a, scenes = _assign(client, as_lead, db, [uid(db, ARTIST)])
    _submit(client, as_artist, a, scenes)
    monkeypatch.setattr(lead_service, "studio_eod", lambda d: utcnow() - timedelta(minutes=1))
    assert lead_service.send_evening_summaries(db) >= 1
    assert lead_service.send_evening_summaries(db) == 0
    n = db.scalar(select(Notification).where(Notification.event_type == "evening_summary",
                                            Notification.user_id == uid(db, "lead.anim@studiotrack.demo")))
    assert "1 submission(s) today" in n.message and "1 waiting for review" in n.message
