from datetime import timedelta

from sqlalchemy import select

from app.core.config import get_settings
from app.core.timeutils import studio_eod, studio_today, utcnow
from app.models import Episode, Project, Scene
from app.services.assignment_service import aggregate_status
from app.models import AssignmentStatus as S
from tests.conftest import ARTIST, ARTIST2, ARTIST_OTHER_TEAM, LEAD_OTHER, login, uid


def _neon(db):
    """Demo project owned by the lead's team: Neon Monsoon EP01 (6 scenes)."""
    p = db.scalar(select(Project).where(Project.code == "NEON-01"))
    ep = db.scalar(select(Episode).where(Episode.project_id == p.id, Episode.episode_number == 1))
    scenes = list(db.scalars(select(Scene).where(Scene.episode_id == ep.id).order_by(Scene.scene_number)))
    return p, ep, scenes


def _create(client, h, db, **kw):
    p, ep, scenes = _neon(db)
    body = {"project_id": p.id, "episode_id": ep.id, "scene_ids": [scenes[0].id, scenes[1].id],
            "artist_ids": [uid(db, ARTIST)], "description": "Animate the opening shots", **kw}
    return client.post("/api/v1/assignments", headers=h, json=body)


def test_lead_assigns_two_scenes_with_eod_deadline(client, as_lead, db):
    r = _create(client, as_lead, db, priority="high")
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["title"] == "EP01 Pilot: Static Rain — Scenes 01, 02"
    assert [s["label"] for s in a["scenes"]] == ["SC01", "SC02"]
    assert a["status"] == "assigned" and a["priority"] == "high" and not a["is_overdue"]
    assert a["assignment_date"] == str(studio_today())
    from datetime import datetime
    deadline = datetime.fromisoformat(a["deadline"].replace("Z", "+00:00")).astimezone(get_settings().tz)
    assert deadline.date() == studio_today()
    eod = studio_eod(studio_today())
    expected_hour = get_settings().eod_deadline_hour if eod > utcnow() else 23
    assert deadline.hour == expected_hour
    assert [x["full_name"] for x in a["assignees"]] == ["Arjun Mehta (Demo Artist)"]


def test_multi_artist_assignment_tracks_each_artist(client, as_lead, db):
    r = _create(client, as_lead, db, artist_ids=[uid(db, ARTIST), uid(db, ARTIST2)])
    assert r.status_code == 201
    assert len(r.json()["assignees"]) == 2
    assert all(x["status"] == "assigned" and x["reported_progress_pct"] == 0 for x in r.json()["assignees"])


def test_whole_episode_and_non_scene_deliverable(client, as_lead, db):
    p, ep, scenes = _neon(db)
    r = _create(client, as_lead, db, scene_ids=[s.id for s in scenes])
    assert r.status_code == 201 and len(r.json()["scenes"]) == 6
    r = _create(client, as_lead, db, scene_ids=[], expected_deliverables="Character turnaround sheet")
    assert r.status_code == 201 and r.json()["scenes"] == []
    assert r.json()["title"].endswith("deliverable")


def test_assignment_needs_scenes_or_description(client, as_lead, db):
    r = _create(client, as_lead, db, scene_ids=[], description=None)
    assert r.status_code == 422


def test_scene_must_belong_to_episode_and_project(client, as_lead, db):
    p, ep, scenes = _neon(db)
    other_ep = db.scalar(select(Episode).where(Episode.project_id == p.id, Episode.episode_number == 2))
    foreign_scene = db.scalars(select(Scene).where(Scene.episode_id == other_ep.id)).first()
    r = _create(client, as_lead, db, scene_ids=[foreign_scene.id])
    assert r.status_code == 422 and "episode" in r.json()["detail"]
    r = _create(client, as_lead, db, scene_ids=[999999])
    assert r.status_code == 422


def test_cannot_assign_to_non_artist_or_other_team(client, as_lead, db):
    r = _create(client, as_lead, db, artist_ids=[uid(db, ARTIST_OTHER_TEAM)])
    assert r.status_code == 403
    r = _create(client, as_lead, db, artist_ids=[uid(db, "lead.anim@studiotrack.demo")])
    assert r.status_code == 422


def test_lead_cannot_assign_on_other_teams_project(client, db):
    other = login(client, LEAD_OTHER)
    r = _create(client, other, db, artist_ids=[uid(db, ARTIST_OTHER_TEAM)])
    assert r.status_code == 403


def test_artist_cannot_create_assignment(client, as_artist, db):
    assert _create(client, as_artist, db).status_code == 403


def test_deadline_must_be_future(client, as_lead, db):
    r = _create(client, as_lead, db, deadline=(utcnow() - timedelta(hours=1)).isoformat())
    assert r.status_code == 422


def test_artist_sees_only_own_assignments(client, as_lead, as_artist, db):
    _create(client, as_lead, db)
    _create(client, as_lead, db, artist_ids=[uid(db, ARTIST2)])
    mine = client.get("/api/v1/assignments", headers=as_artist).json()
    assert len(mine) == 1 and mine[0]["assignees"][0]["full_name"].startswith("Arjun")
    other_id = client.get("/api/v1/assignments", headers=as_lead).json()
    ids = {a["id"] for a in other_id} - {mine[0]["id"]}
    assert client.get(f"/api/v1/assignments/{ids.pop()}", headers=as_artist).status_code == 404
    # artist now sees the project they were assigned to
    assert [p["code"] for p in client.get("/api/v1/projects", headers=as_artist).json()] == ["NEON-01"]


def test_other_lead_cannot_see_or_edit(client, as_lead, db):
    aid = _create(client, as_lead, db).json()["id"]
    other = login(client, LEAD_OTHER)
    assert client.get(f"/api/v1/assignments/{aid}", headers=other).status_code == 404
    assert client.patch(f"/api/v1/assignments/{aid}", headers=other, json={"priority": "low"}).status_code == 404


def test_update_add_remove_artists(client, as_lead, db):
    aid = _create(client, as_lead, db).json()["id"]
    r = client.patch(f"/api/v1/assignments/{aid}", headers=as_lead,
                     json={"priority": "urgent", "add_artist_ids": [uid(db, ARTIST2)]})
    assert r.status_code == 200 and r.json()["priority"] == "urgent" and len(r.json()["assignees"]) == 2
    r = client.patch(f"/api/v1/assignments/{aid}", headers=as_lead, json={"remove_artist_ids": [uid(db, ARTIST)]})
    assert [x["full_name"] for x in r.json()["assignees"]] == ["Sara Okafor (Demo Artist)"]
    r = client.patch(f"/api/v1/assignments/{aid}", headers=as_lead, json={"remove_artist_ids": [uid(db, ARTIST2)]})
    assert r.status_code == 422


def test_filters_and_delete(client, as_lead, db):
    aid = _create(client, as_lead, db, priority="urgent").json()["id"]
    _create(client, as_lead, db, priority="low")
    assert len(client.get("/api/v1/assignments?priority=urgent", headers=as_lead).json()) == 1
    assert len(client.get(f"/api/v1/assignments?artist_id={uid(db, ARTIST)}", headers=as_lead).json()) == 2
    assert client.delete(f"/api/v1/assignments/{aid}", headers=as_lead).status_code == 204
    assert len(client.get("/api/v1/assignments", headers=as_lead).json()) == 1


def test_aggregate_status_rules():
    assert aggregate_status([S.ASSIGNED, S.ASSIGNED]) == S.ASSIGNED
    assert aggregate_status([S.ASSIGNED, S.IN_PROGRESS]) == S.IN_PROGRESS
    assert aggregate_status([S.SUBMITTED, S.IN_PROGRESS]) == S.SUBMITTED
    assert aggregate_status([S.REVISION_REQUIRED, S.SUBMITTED]) == S.REVISION_REQUIRED
    assert aggregate_status([S.APPROVED, S.ASSIGNED]) == S.IN_PROGRESS
    assert aggregate_status([S.APPROVED, S.COMPLETED]) == S.APPROVED
    assert aggregate_status([S.COMPLETED]) == S.COMPLETED


def test_dashboards_reflect_real_data(client, as_lead, as_artist, db):
    _create(client, as_lead, db)
    client.post("/api/v1/attendance/check-in", headers=as_artist)
    o = client.get("/api/v1/dashboard/overview", headers=as_lead).json()
    assert o["headcount"] == 4 and o["attendance_today"]["present"] == 1
    assert o["active_assignments"] == 1 and o["due_today"] == 1 and o["overdue"] == 0
    assert o["workload"][0]["full_name"].startswith("Arjun") and o["workload"][0]["active"] == 1
    me = client.get("/api/v1/dashboard/me", headers=as_artist).json()
    assert me["open_assignments"] == 1 and me["attendance"]["can_check_out"] is True
    assert client.get("/api/v1/dashboard/overview", headers=as_artist).status_code == 403


def test_list_returns_open_work_before_finished_history(client, as_lead, db):
    """With more history than the list limit, new and open assignments must never be cut off."""
    from app.models import Assignment
    from app.services import assignment_service
    old = _create(client, as_lead, db, deadline=(utcnow() + timedelta(hours=2)).isoformat()).json()
    new = _create(client, as_lead, db, deadline=(utcnow() + timedelta(days=5)).isoformat()).json()
    a = db.get(Assignment, old["id"])
    a.status = S.COMPLETED  # finished work with the soonest deadline used to sort first
    db.commit()

    lead = db.get(__import__("app.models", fromlist=["User"]).User, uid(db, "lead.anim@studiotrack.demo"))
    rows = assignment_service.list_for(db, lead)
    statuses = [r.status in assignment_service.DONE for r in rows]
    assert statuses == sorted(statuses)  # every open one comes before every finished one
    top = assignment_service.list_for(db, lead, limit=1)
    assert top[0].status not in assignment_service.DONE
    assert new["id"] in [r.id for r in assignment_service.list_for(db, lead, limit=len(rows) - 1)]
