from tests.conftest import LEAD_OTHER, login


def _project(client, h, **kw):
    body = {"code": "MOV-1", "title": "Monsoon Movie", "project_type": "feature_film", "status": "active", **kw}
    return client.post("/api/v1/projects", headers=h, json=body)


def test_admin_creates_project_episodes_and_scenes(client, as_admin):
    r = _project(client, as_admin, team_id=1, start_date="2026-01-01", expected_completion_date="2026-06-30")
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    assert r.json()["code"] == "MOV-1"

    r = client.post(f"/api/v1/projects/{pid}/episodes", headers=as_admin,
                    json={"episode_number": 1, "title": "Opening", "scene_count": 3})
    assert r.status_code == 201
    ep = r.json()
    assert [s["label"] for s in ep["scenes"]] == ["SC01", "SC02", "SC03"]

    r = client.post(f"/api/v1/episodes/{ep['id']}/scenes", headers=as_admin,
                    json={"scene_number": 4, "title": "Rooftop chase"})
    assert r.status_code == 201
    r = client.post(f"/api/v1/episodes/{ep['id']}/scenes/bulk", headers=as_admin, json={"count": 2})
    assert [s["scene_number"] for s in r.json()] == [5, 6]

    detail = client.get(f"/api/v1/projects/{pid}", headers=as_admin).json()
    assert detail["episode_count"] == 1 and detail["scene_count"] == 6


def test_project_validation(client, as_admin):
    assert _project(client, as_admin, start_date="2026-05-01", expected_completion_date="2026-04-01").status_code == 422
    assert _project(client, as_admin, code="bad code!").status_code == 422
    assert _project(client, as_admin).status_code == 201
    assert _project(client, as_admin, code="mov-1").status_code == 409  # codes are case-insensitive


def test_duplicate_episode_and_scene_numbers_rejected(client, as_admin):
    pid = _project(client, as_admin).json()["id"]
    ep = client.post(f"/api/v1/projects/{pid}/episodes", headers=as_admin,
                     json={"episode_number": 1, "title": "A", "scene_count": 1}).json()
    r = client.post(f"/api/v1/projects/{pid}/episodes", headers=as_admin, json={"episode_number": 1, "title": "B"})
    assert r.status_code == 409
    r = client.post(f"/api/v1/episodes/{ep['id']}/scenes", headers=as_admin, json={"scene_number": 1})
    assert r.status_code == 409


def test_lead_creates_project_defaulting_to_own_team(client, as_lead):
    r = _project(client, as_lead)
    assert r.status_code == 201
    assert r.json()["team_name"] == "Animation Unit (Demo)" and r.json()["can_manage"] is True


def test_lead_cannot_edit_other_teams_project(client, as_lead):
    other = login(client, LEAD_OTHER)
    pid = _project(client, other).json()["id"]
    # visible (catalog), but not editable
    r = client.get(f"/api/v1/projects/{pid}", headers=as_lead)
    assert r.status_code == 200 and r.json()["can_manage"] is False
    assert client.patch(f"/api/v1/projects/{pid}", headers=as_lead, json={"title": "Hijack"}).status_code == 403
    assert client.post(f"/api/v1/projects/{pid}/episodes", headers=as_lead,
                       json={"episode_number": 9, "title": "X"}).status_code == 403
    assert _project(client, as_lead, code="X-2", team_id=2).status_code == 422


def test_artist_cannot_create_and_sees_only_assigned_projects(client, as_artist):
    assert _project(client, as_artist).status_code == 403
    assert client.get("/api/v1/projects", headers=as_artist).json() == []
    assert client.get("/api/v1/projects/1", headers=as_artist).status_code == 404


def test_soft_delete_hides_scene_and_project(client, as_admin):
    pid = _project(client, as_admin).json()["id"]
    ep = client.post(f"/api/v1/projects/{pid}/episodes", headers=as_admin,
                     json={"episode_number": 1, "title": "A", "scene_count": 2}).json()
    assert client.delete(f"/api/v1/scenes/{ep['scenes'][0]['id']}", headers=as_admin).status_code == 204
    assert client.get(f"/api/v1/projects/{pid}", headers=as_admin).json()["scene_count"] == 1
    assert client.delete(f"/api/v1/projects/{pid}", headers=as_admin).status_code == 204
    assert client.get(f"/api/v1/projects/{pid}", headers=as_admin).status_code == 404


def test_update_project_status(client, as_admin):
    pid = _project(client, as_admin).json()["id"]
    r = client.patch(f"/api/v1/projects/{pid}", headers=as_admin, json={"status": "on_hold"})
    assert r.json()["status"] == "on_hold"
    assert len(client.get("/api/v1/projects?status=on_hold", headers=as_admin).json()) == 1


def test_import_chota_tenali_screenplay(client, as_admin):
    pid = _project(client, as_admin, title="Chota Tenali").json()["id"]
    ep = client.post(f"/api/v1/projects/{pid}/episodes", headers=as_admin,
                     json={"episode_number": 1, "title": "Episode 1", "scene_count": 0}).json()

    script = """
01 | EXT. VILLAGE / MARKET — MORNING | 01:15
AERIAL WIDE — सूरज की पहली किरणें हरे धान के खेतों पर...
SABZIWALA (O.S.) पकड़ो! अरे पकड़ो! मेरी मिर्च लेकर भागा!
RAMA मदद करेगा, या ऊपर बैठकर बस आँखों देखा हाल सुनाएगा?
PACHCHI हाल सुनाऊँगा!
KOTI लड्डू बच गया!

02 | EXT. GURUKUL — MORNING | 01:30
एक विशाल पेड़ के नीचे गुरुकुल...
MALLANNA देर से आए हो! यहाँ मेरा नियम चलता है।
GUNDU बिल्कुल, जुर्माना!
BONDU बिल्कुल, पूरा जुर्माना!
GURUJI पढ़ाई होगी या पंचायत यहीं लगाओगे?
    """

    # Preview parse
    preview = client.post("/api/v1/screenplay/parse", headers=as_admin, json={"raw_text": script}).json()
    assert len(preview) == 2
    assert preview[0]["scene_number"] == 1
    assert preview[0]["title"] == "EXT. VILLAGE / MARKET — MORNING"
    assert preview[0]["duration_sec"] == 75.0
    assert "RAMA" in preview[0]["characters"]
    assert "SABZIWALA" in preview[0]["characters"]

    assert preview[1]["scene_number"] == 2
    assert preview[1]["duration_sec"] == 90.0
    assert "MALLANNA" in preview[1]["characters"]

    # Import into episode
    imported = client.post(f"/api/v1/episodes/{ep['id']}/scenes/screenplay-import", headers=as_admin,
                           json={"raw_text": script, "replace_existing": True}).json()
    assert len(imported) == 2
    assert imported[0]["duration_sec"] == 75.0
    assert "RAMA" in imported[0]["characters"]
    assert imported[1]["duration_sec"] == 90.0

    # Re-importing with replace_existing=True updates without constraint conflicts
    reimported = client.post(f"/api/v1/episodes/{ep['id']}/scenes/screenplay-import", headers=as_admin,
                             json={"raw_text": script, "replace_existing": True}).json()
    assert len(reimported) == 2
    assert reimported[0]["id"] == imported[0]["id"]
    assert "RAMA" in reimported[0]["characters"]

    # Test uploading a script file
    res = client.post("/api/v1/screenplay/upload-file", headers=as_admin,
                      files={"file": ("script.txt", script.encode("utf-8"), "text/plain")})
    assert res.status_code == 200
    data = res.json()
    assert data["scene_count"] == 2
    assert len(data["scenes"]) == 2

    # Test importing directly into a new project without episodes
    pid2 = _project(client, as_admin, code="MOV-EP", title="Project Without Episodes").json()["id"]
    p_imported = client.post(f"/api/v1/projects/{pid2}/screenplay-import", headers=as_admin,
                             json={"raw_text": script}).json()
    assert len(p_imported) == 2
    assert p_imported[0]["duration_sec"] == 75.0
