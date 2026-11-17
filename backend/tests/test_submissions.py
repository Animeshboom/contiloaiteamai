from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.core.timeutils import utcnow
from app.models import Assignment, AuditLog, Episode, Project, Review, Scene, Submission, WorkStatus
from tests.conftest import ARTIST, ARTIST2, ARTIST_OTHER_TEAM, LEAD_OTHER, login, uid

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def _scenes(db, n=3):
    p = db.scalar(select(Project).where(Project.code == "NEON-01"))
    ep = db.scalar(select(Episode).where(Episode.project_id == p.id, Episode.episode_number == 1))
    return p, ep, list(db.scalars(select(Scene).where(Scene.episode_id == ep.id).order_by(Scene.scene_number)))[:n]


def _assign(client, lead, db, n=3, artists=None, **kw):
    p, ep, scenes = _scenes(db, n)
    body = {"project_id": p.id, "episode_id": ep.id, "scene_ids": [s.id for s in scenes],
            "artist_ids": artists or [uid(db, ARTIST)], "description": "Animate", **kw}
    r = client.post("/api/v1/assignments", headers=lead, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _submit(client, h, aid, scene_ids, **kw):
    body = {"assignment_id": aid, "scene_ids": scene_ids, "work_description": "Rendered and graded",
            "output_links": ["https://drive.example.com/sc01"], "comments": "Ready", **kw}
    return client.post("/api/v1/submissions", headers=h, json=body)


def _review(client, h, sid, decision, **kw):
    return client.post(f"/api/v1/submissions/{sid}/review", headers=h, json={"decision": decision, **kw})


def _mine(client, h, aid):
    a = client.get(f"/api/v1/assignments/{aid}", headers=h).json()
    return a, a["assignees"][0]


# ---------------- progress ----------------

def test_progress_update_is_self_reported_only(client, as_lead, as_artist, db):
    a = _assign(client, as_lead, db)
    r = client.put(f"/api/v1/assignments/{a['id']}/progress", headers=as_artist,
                   json={"reported_progress_pct": 60, "progress_note": "2 of 3 scenes rendering"})
    assert r.status_code == 200
    x = r.json()["assignees"][0]
    assert x["status"] == "in_progress" and x["reported_progress_pct"] == 60
    assert x["scenes_submitted"] == 0 and x["scenes_approved"] == 0  # progress != delivery
    assert client.put(f"/api/v1/assignments/{a['id']}/progress", headers=as_lead,
                      json={"reported_progress_pct": 10}).status_code == 403
    other = login(client, ARTIST2)
    assert client.put(f"/api/v1/assignments/{a['id']}/progress", headers=other,
                      json={"reported_progress_pct": 10}).status_code == 404


# ---------------- partial submission & approval ----------------

def test_partial_submission_then_full_approval_cycle(client, as_lead, as_artist, db):
    a = _assign(client, as_lead, db, n=3)
    s1, s2, s3 = [s["id"] for s in a["scenes"]]

    r = _submit(client, as_artist, a["id"], [s1, s2])
    assert r.status_code == 201, r.text
    sub = r.json()
    assert sub["status"] == "pending_review" and sub["revision_number"] == 1
    assert [d["label"] for d in sub["deliverables"]] == ["EP01 SC01", "EP01 SC02"]
    assert sub["scenes_completed_count"] == 2 and not sub["is_resubmission"]

    a2, me = _mine(client, as_artist, a["id"])
    assert me["status"] == "submitted" and a2["status"] == "submitted"
    assert me["scene_states"] == {str(s1): "submitted", str(s2): "submitted"}  # SC03 untouched
    assert me["scenes_submitted"] == 2 and me["scenes_approved"] == 0

    r = _review(client, as_lead, sub["id"], "approved")
    assert r.status_code == 200, r.text
    rev = r.json()
    assert rev["status"] == "approved"
    assert all(d["status"] == "approved" and d["approved_by_name"] for d in rev["deliverables"])
    assert rev["reviews"][0]["decision"] == "approved" and rev["reviews"][0]["reviewer_name"].startswith("Priya")

    _, me = _mine(client, as_artist, a["id"])
    assert me["status"] == "in_progress"  # SC03 still outstanding: not falsely complete
    assert me["scenes_approved"] == 2
    assert db.get(Scene, s1).status == WorkStatus.APPROVED and db.get(Scene, s3).status == WorkStatus.NOT_STARTED

    sub2 = _submit(client, as_artist, a["id"], [s3]).json()
    assert sub2["revision_number"] == 2
    _review(client, as_lead, sub2["id"], "approved")
    a3, me = _mine(client, as_artist, a["id"])
    assert me["status"] == "approved" and a3["status"] == "approved" and me["scenes_approved"] == 3

    r = client.post(f"/api/v1/assignments/{a['id']}/complete", headers=as_lead)
    assert r.status_code == 200 and r.json()["status"] == "completed"
    assert _submit(client, as_artist, a["id"], [s1]).status_code == 409


def test_cannot_submit_pending_approved_or_foreign_scenes(client, as_lead, as_artist, db):
    a = _assign(client, as_lead, db, n=2)
    s1, s2 = [s["id"] for s in a["scenes"]]
    sub = _submit(client, as_artist, a["id"], [s1]).json()
    r = _submit(client, as_artist, a["id"], [s1])
    assert r.status_code == 409 and "awaiting review" in r.json()["detail"]
    # a different, non-overlapping scene can be submitted while the first is pending
    assert _submit(client, as_artist, a["id"], [s2]).status_code == 201
    _review(client, as_lead, sub["id"], "approved")
    r = _submit(client, as_artist, a["id"], [s1])
    assert r.status_code == 409 and "already approved" in r.json()["detail"]
    _, _, all_scenes = _scenes(db, 6)
    assert _submit(client, as_artist, a["id"], [all_scenes[5].id]).status_code == 422
    assert _submit(client, as_artist, a["id"], []).status_code == 422


def test_artist_cannot_submit_to_someone_elses_assignment(client, as_lead, db):
    a = _assign(client, as_lead, db)
    other = login(client, ARTIST2)
    assert _submit(client, other, a["id"], [a["scenes"][0]["id"]]).status_code == 404
    assert _submit(client, as_lead, a["id"], [a["scenes"][0]["id"]]).status_code == 403


def test_link_validation(client, as_lead, as_artist, db):
    a = _assign(client, as_lead, db)
    r = _submit(client, as_artist, a["id"], [a["scenes"][0]["id"]], output_links=["javascript:alert(1)"])
    assert r.status_code == 422
    r = _submit(client, as_artist, a["id"], [a["scenes"][0]["id"]], output_links=["ftp://files.example.com/x"])
    assert r.status_code == 422


# ---------------- rejection & revision ----------------

def test_rejection_requires_feedback_and_resubmission_creates_revision(client, as_lead, as_artist, db):
    a = _assign(client, as_lead, db, n=2)
    s1, s2 = [s["id"] for s in a["scenes"]]
    first = _submit(client, as_artist, a["id"], [s1, s2]).json()

    assert _review(client, as_lead, first["id"], "rejected").status_code == 422
    assert _review(client, as_lead, first["id"], "rejected", feedback="  ").status_code == 422
    r = _review(client, as_lead, first["id"], "rejected", feedback="Rain particles flicker in SC01; SC02 too dark")
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    assert all(d["status"] == "rejected" for d in r.json()["deliverables"])

    a2, me = _mine(client, as_artist, a["id"])
    assert me["status"] == "revision_required" and a2["status"] == "revision_required"

    second = _submit(client, as_artist, a["id"], [s1, s2], work_description="Fixed flicker, lifted exposure").json()
    assert second["revision_number"] == 2 and second["previous_submission_id"] == first["id"]
    assert second["is_resubmission"] and second["status"] == "pending_review"

    # the original submission is untouched and keeps its review
    orig = client.get(f"/api/v1/submissions/{first['id']}", headers=as_artist).json()
    assert orig["status"] == "rejected" and orig["work_description"] == "Rendered and graded"
    assert orig["reviews"][0]["feedback"].startswith("Rain particles")

    _, me = _mine(client, as_artist, a["id"])
    assert me["status"] == "submitted"  # revised work goes through review again
    _review(client, as_lead, second["id"], "approved")
    _, me = _mine(client, as_artist, a["id"])
    assert me["status"] == "approved"

    history = client.get(f"/api/v1/submissions?assignment_id={a['id']}", headers=as_artist).json()
    assert [h["revision_number"] for h in history] == [2, 1]
    assert db.query(Review).count() == 2


def test_partial_approval_of_a_submission(client, as_lead, as_artist, db):
    a = _assign(client, as_lead, db, n=2)
    s1, s2 = [s["id"] for s in a["scenes"]]
    sub = _submit(client, as_artist, a["id"], [s1, s2]).json()

    r = _review(client, as_lead, sub["id"], "approved", approved_scene_ids=[s1])
    assert r.status_code == 422  # rejecting SC02 implicitly needs feedback
    r = _review(client, as_lead, sub["id"], "approved", approved_scene_ids=[s1], feedback="SC02 needs a wider lens")
    assert r.status_code == 200
    body = r.json()
    states = {d["scene_id"]: d["status"] for d in body["deliverables"]}
    assert states == {s1: "approved", s2: "rejected"}
    assert body["status"] == "rejected" and body["reviews"][0]["approved_scene_ids"] == [s1]

    _, me = _mine(client, as_artist, a["id"])
    assert me["status"] == "revision_required" and me["scenes_approved"] == 1
    assert me["scene_states"] == {str(s1): "approved", str(s2): "rejected"}
    # only the rejected scene may be resubmitted
    assert _submit(client, as_artist, a["id"], [s1]).status_code == 409
    resub = _submit(client, as_artist, a["id"], [s2]).json()
    assert resub["previous_submission_id"] == sub["id"]


def test_review_rules(client, as_lead, as_artist, db):
    a = _assign(client, as_lead, db, n=1)
    sub = _submit(client, as_artist, a["id"], [a["scenes"][0]["id"]]).json()
    assert _review(client, as_artist, sub["id"], "approved").status_code == 403
    other_lead = login(client, LEAD_OTHER)
    assert _review(client, other_lead, sub["id"], "approved").status_code == 404
    assert _review(client, as_lead, sub["id"], "approved", approved_scene_ids=[999]).status_code == 422
    assert _review(client, as_lead, sub["id"], "approved").status_code == 200
    r = _review(client, as_lead, sub["id"], "rejected", feedback="changed my mind")
    assert r.status_code == 409  # never overwrite a completed review
    assert db.query(Review).count() == 1
    actions = set(db.scalars(select(AuditLog.action)))
    assert {"submission.create", "submission.approved"} <= actions


def test_deliverable_only_assignment_flow(client, as_lead, as_artist, db):
    p, _, _ = _scenes(db)
    a = client.post("/api/v1/assignments", headers=as_lead, json={
        "project_id": p.id, "scene_ids": [], "artist_ids": [uid(db, ARTIST)],
        "expected_deliverables": "Character turnaround sheet"}).json()
    assert _submit(client, as_artist, a["id"], [1]).status_code == 422
    sub = _submit(client, as_artist, a["id"], []).json()
    assert sub["deliverables"][0]["label"] == "Character turnaround sheet"
    assert _submit(client, as_artist, a["id"], []).status_code == 409  # one pending at a time
    _review(client, as_lead, sub["id"], "rejected", feedback="Add back view")
    sub2 = _submit(client, as_artist, a["id"], []).json()
    assert sub2["previous_submission_id"] == sub["id"]
    _review(client, as_lead, sub2["id"], "approved")
    _, me = _mine(client, as_artist, a["id"])
    assert me["status"] == "approved"


def test_multi_artist_contributions_are_separate(client, as_lead, as_artist, db):
    a = _assign(client, as_lead, db, n=2, artists=[uid(db, ARTIST), uid(db, ARTIST2)])
    s1 = a["scenes"][0]["id"]
    sub = _submit(client, as_artist, a["id"], [s1]).json()
    _review(client, as_lead, sub["id"], "approved")
    full = client.get(f"/api/v1/assignments/{a['id']}", headers=as_lead).json()
    by_name = {x["full_name"].split()[0]: x for x in full["assignees"]}
    assert by_name["Arjun"]["scenes_approved"] == 1 and by_name["Sara"]["scenes_approved"] == 0
    assert by_name["Sara"]["status"] == "assigned"


def test_late_flag_and_scoped_listing(client, as_lead, as_artist, db):
    a = _assign(client, as_lead, db, n=1)
    row = db.get(Assignment, a["id"])
    row.deadline = utcnow() - timedelta(hours=1)
    db.commit()
    sub = _submit(client, as_artist, a["id"], [a["scenes"][0]["id"]]).json()
    assert sub["is_late"] is True
    queue = client.get("/api/v1/submissions?status=pending_review", headers=as_lead).json()
    assert [q["id"] for q in queue] == [sub["id"]]
    assert client.get("/api/v1/submissions", headers=login(client, LEAD_OTHER)).json() == []
    assert client.get("/api/v1/submissions", headers=login(client, ARTIST2)).json() == []
    assert client.get("/api/v1/dashboard/overview", headers=as_lead).json()["pending_reviews"] == 1


# ---------------- attachments ----------------

def _pending(client, as_lead, as_artist, db):
    a = _assign(client, as_lead, db, n=1)
    return _submit(client, as_artist, a["id"], [a["scenes"][0]["id"]]).json()


def test_attachment_upload_and_scoped_download(client, as_lead, as_artist, db):
    sub = _pending(client, as_lead, as_artist, db)
    r = client.post(f"/api/v1/submissions/{sub['id']}/attachments", headers=as_artist,
                    files={"file": ("../../frame 01.png", PNG, "image/png")})
    assert r.status_code == 201, r.text
    att = r.json()["attachments"][0]
    assert att["original_filename"] == "frame 01.png" and att["size_bytes"] == len(PNG)

    stored = db.scalar(select(Submission).where(Submission.id == sub["id"])).attachments[0].stored_filename
    assert ".." not in stored and "frame" not in stored  # random server-side name

    url = f"/api/v1/submissions/{sub['id']}/attachments/{att['id']}"
    for h in (as_artist, as_lead):
        d = client.get(url, headers=h)
        assert d.status_code == 200 and d.content == PNG
        assert d.headers["x-content-type-options"] == "nosniff"
        assert d.headers["content-type"] == "application/octet-stream"
    assert client.get(url, headers=login(client, ARTIST2)).status_code == 404
    assert client.get(url, headers=login(client, LEAD_OTHER)).status_code == 404


@pytest.mark.parametrize("name,content,msg", [
    ("tool.exe", b"MZ\x90\x00", "not allowed"),
    ("fake.png", b"MZ\x90\x00 not really png", "Executable"),
    ("fake.pdf", b"<html>hi</html>", "does not match"),
    ("empty.txt", b"", "empty"),
])
def test_attachment_rejections(client, as_lead, as_artist, db, name, content, msg):
    sub = _pending(client, as_lead, as_artist, db)
    r = client.post(f"/api/v1/submissions/{sub['id']}/attachments", headers=as_artist,
                    files={"file": (name, content, "application/octet-stream")})
    assert r.status_code == 422 and msg in r.json()["detail"]


def test_attachment_size_limit(client, as_lead, as_artist, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    sub = _pending(client, as_lead, as_artist, db)
    big = PNG + b"\x00" * (1024 * 1024 + 10)
    r = client.post(f"/api/v1/submissions/{sub['id']}/attachments", headers=as_artist,
                    files={"file": ("big.png", big, "image/png")})
    assert r.status_code == 422 and "limit" in r.json()["detail"]


def test_attachments_locked_after_review_and_owner_only(client, as_lead, as_artist, db):
    sub = _pending(client, as_lead, as_artist, db)
    files = {"file": ("a.png", PNG, "image/png")}
    assert client.post(f"/api/v1/submissions/{sub['id']}/attachments", headers=as_lead, files=files).status_code == 403
    _review(client, as_lead, sub["id"], "approved")
    r = client.post(f"/api/v1/submissions/{sub['id']}/attachments", headers=as_artist, files=files)
    assert r.status_code == 409


def test_other_team_artist_unaffected(client, as_lead, db):
    _assign(client, as_lead, db)
    other = login(client, ARTIST_OTHER_TEAM)
    assert client.get("/api/v1/assignments", headers=other).json() == []
