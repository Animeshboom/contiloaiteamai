"""End-to-end workflow test against a running StudioTrack deployment, using dummy data.

Walks the real role workflow through the public API, exactly as the web app does:
  admin  : sign in, create a team, a team lead, an artist, a project, an episode with scenes
  lead   : attendance overview, assign work, review a submission (partial approval + revision feedback)
  artist : sign in, check in, view assignments, submit work, read review feedback, resubmit
  checks : invalid credentials, protected endpoints, role permissions, revoked tokens, CORS headers

Configuration (environment variables, or a git-ignored .e2e.env file in the repo root - never in chat):
  E2E_API_URL         e.g. https://studiotrack-api.onrender.com
  E2E_WEB_ORIGIN      e.g. https://studiotrack-ai.pages.dev   (sent as Origin to verify CORS)
  E2E_ADMIN_EMAIL     an existing admin account
  E2E_ADMIN_PASSWORD

Dummy accounts get random passwords that are never printed, and are deactivated at the end. The dummy
team/project stay (named "E2E ...") so you can inspect them in the UI; delete the project there if you like.
Nothing existing is modified. Run:  python scripts/e2e_workflow.py
"""
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

RESULTS: list[tuple[str, bool, str]] = []


def load_config() -> dict:
    env_file = Path(__file__).resolve().parent.parent / ".e2e.env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    cfg = {k: os.environ.get(k, "").strip() for k in ("E2E_API_URL", "E2E_WEB_ORIGIN", "E2E_ADMIN_EMAIL", "E2E_ADMIN_PASSWORD")}
    missing = [k for k, v in cfg.items() if not v]
    if missing:
        sys.exit(f"Missing configuration: {', '.join(missing)} (set them in .e2e.env or the environment)")
    cfg["E2E_API_URL"] = cfg["E2E_API_URL"].rstrip("/")
    cfg["E2E_WEB_ORIGIN"] = cfg["E2E_WEB_ORIGIN"].rstrip("/")
    return cfg


class Api:
    def __init__(self, base: str, origin: str):
        self.base, self.origin = base, origin

    def call(self, method: str, path: str, body=None, token: str | None = None, timeout: float = 90):
        url = self.base + ("/api/v1" + path if not path.startswith("/api/") else path)
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Origin", self.origin)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw, status, headers = r.read(), r.status, r.headers
        except urllib.error.HTTPError as e:
            raw, status, headers = e.read(), e.code, e.headers
        try:
            payload = json.loads(raw) if raw else None
        except ValueError:
            payload = raw.decode(errors="replace")[:200]
        return status, payload, headers


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail and not ok else ""))
    return bool(ok)


def require(name: str, ok: bool, detail: str = ""):
    if not check(name, ok, detail):
        summary()
        sys.exit(1)


def summary():
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    print(f"\n{passed}/{len(RESULTS)} checks passed")


def main():
    cfg = load_config()
    api = Api(cfg["E2E_API_URL"], cfg["E2E_WEB_ORIGIN"])
    tag = time.strftime("%Y%m%d%H%M%S")
    print(f"StudioTrack E2E against {api.base}  (run tag {tag})\n")

    print("Deployment")
    for attempt in range(12):  # free instances may be asleep
        status, body, headers = api.call("GET", "/api/health")
        if status == 200:
            break
        time.sleep(10)
    require("API health responds and reaches the database", status == 200 and body.get("status") == "ok", f"{status} {body}")
    check("health reports production mode", body.get("environment") == "production", str(body))

    print("\nAuthentication")
    status, body, headers = api.call("POST", "/auth/login", {"email": cfg["E2E_ADMIN_EMAIL"], "password": "definitely-wrong-password"})
    check("invalid credentials are rejected (401, generic message)", status == 401 and body.get("detail") == "Invalid email or password", f"{status} {body}")
    status, body, _ = api.call("POST", "/auth/login", {"email": "not-an-email", "password": ""})
    check("malformed login is rejected (422)", status == 422, str(status))
    status, body, headers = api.call("POST", "/auth/login", {"email": cfg["E2E_ADMIN_EMAIL"], "password": cfg["E2E_ADMIN_PASSWORD"]})
    require("admin login succeeds", status == 200 and body.get("access_token"), f"{status} {body if status != 200 else ''}")
    check("login response carries CORS header for the web origin",
          headers.get("access-control-allow-origin") == api.origin, str(headers.get("access-control-allow-origin")))
    admin = body["access_token"]
    status, me, _ = api.call("GET", "/auth/me", token=admin)
    require("admin /auth/me returns the admin role", status == 200 and me.get("role") == "admin", f"{status} {me}")
    status, _, _ = api.call("GET", "/auth/me")
    check("protected endpoint without a token -> 401", status == 401, str(status))
    status, _, _ = api.call("GET", "/auth/me", token=admin[:-4] + "AAAA")
    check("tampered token -> 401", status == 401, str(status))

    print("\nAdmin: employees, team, project, episode, scenes")
    lead_pw, artist_pw = secrets.token_urlsafe(18), secrets.token_urlsafe(18)
    lead_email, artist_email = f"e2e.lead.{tag}@example.com", f"e2e.artist.{tag}@example.com"
    status, lead, _ = api.call("POST", "/users", {"email": lead_email, "full_name": f"E2E Lead {tag}", "role": "team_lead",
                                                   "job_title": "Team Lead", "password": lead_pw}, admin)
    require("admin creates a team lead", status in (200, 201), f"{status} {lead}")
    status, team, _ = api.call("POST", "/teams", {"name": f"E2E Team {tag}", "description": "Dummy team for E2E test",
                                                   "lead_id": lead["id"]}, admin)
    require("admin creates a team led by the lead", status in (200, 201), f"{status} {team}")
    status, artist, _ = api.call("POST", "/users", {"email": artist_email, "full_name": f"E2E Artist {tag}", "role": "artist",
                                                     "team_id": team["id"], "job_title": "Animator", "password": artist_pw}, admin)
    require("admin creates an artist in the team", status in (200, 201), f"{status} {artist}")
    status, project, _ = api.call("POST", "/projects", {"code": f"E2E{tag[-8:]}", "title": f"E2E Project {tag}",
                                                         "project_type": "series", "status": "active", "team_id": team["id"]}, admin)
    require("admin creates a project", status in (200, 201), f"{status} {project}")
    status, episode, _ = api.call("POST", f"/projects/{project['id']}/episodes",
                                  {"episode_number": 1, "title": "E2E Pilot", "scene_count": 3}, admin)
    require("admin creates an episode with 3 generated scenes", status in (200, 201) and len(episode.get("scenes", [])) == 3, f"{status} {episode}")
    scene_ids = [s["id"] for s in episode["scenes"]]

    print("\nRole permissions")
    status, body, _ = api.call("POST", "/auth/login", {"email": lead_email, "password": lead_pw})
    require("team lead login succeeds", status == 200 and body["user"]["role"] == "team_lead", str(status))
    lead_tok = body["access_token"]
    status, body, _ = api.call("POST", "/auth/login", {"email": artist_email, "password": artist_pw})
    require("artist login succeeds", status == 200 and body["user"]["role"] == "artist", str(status))
    artist_tok = body["access_token"]
    status, _, _ = api.call("POST", "/users", {"email": f"x.{tag}@example.com", "full_name": "Nope", "role": "artist", "password": "x" * 12}, lead_tok)
    check("team lead cannot create employees (403)", status == 403, str(status))
    status, _, _ = api.call("GET", "/users", token=artist_tok)
    check("artist cannot list employees (403)", status == 403, str(status))
    status, _, _ = api.call("GET", "/attendance/roster", token=artist_tok)
    check("artist cannot see the attendance roster (403)", status == 403, str(status))
    status, _, _ = api.call("GET", "/email-logs", token=lead_tok)
    check("team lead cannot read admin email logs (403)", status == 403, str(status))

    print("\nArtist: check-in")
    status, body, _ = api.call("POST", "/attendance/check-in", {}, artist_tok)
    check("artist checks in", status in (200, 201), f"{status} {body}")
    status, body, _ = api.call("POST", "/attendance/check-in", {}, artist_tok)
    check("second check-in the same day is refused (409)", status == 409, str(status))

    print("\nTeam lead: attendance overview and assignment")
    status, roster, _ = api.call("GET", "/attendance/roster", token=lead_tok)
    check("lead sees the attendance roster", status == 200 and isinstance(roster, list), f"{status} {roster}")
    row = next((r for r in roster or [] if r.get("user_id") == artist["id"]), None)
    check("roster shows the artist as checked in", row is not None and row.get("record") and row["status"] != "not_checked_in", str(row))
    status, assignment, _ = api.call("POST", "/assignments", {
        "project_id": project["id"], "episode_id": episode["id"], "scene_ids": scene_ids[:2], "artist_ids": [artist["id"]],
        "title": "E2E animation pass", "description": "Dummy assignment", "priority": "high"}, lead_tok)
    require("lead assigns two scenes to the artist", status in (200, 201), f"{status} {assignment}")

    print("\nArtist: assignments and submission")
    status, mine, _ = api.call("GET", "/assignments", token=artist_tok)
    check("artist sees the new assignment", status == 200 and any(a["id"] == assignment["id"] for a in mine), str(status))
    status, sub1, _ = api.call("POST", "/submissions", {
        "assignment_id": assignment["id"], "scene_ids": scene_ids[:2], "work_description": "E2E: both scenes animated",
        "output_links": ["https://example.com/e2e/render-v1"], "comments": "Dummy submission"}, artist_tok)
    require("artist submits completed work for both scenes", status in (200, 201), f"{status} {sub1}")

    print("\nTeam lead: review, partial approval, revision feedback")
    status, queue, _ = api.call("GET", "/submissions?status=pending_review", token=lead_tok)
    check("submission appears in the lead's review queue", status == 200 and any(s["id"] == sub1["id"] for s in queue), str(status))
    status, body, _ = api.call("POST", f"/submissions/{sub1['id']}/review", {"decision": "approved", "approved_scene_ids": [scene_ids[0]]}, lead_tok)
    check("partial approval without feedback is refused (422)", status == 422, f"{status} {body}")
    feedback = "E2E: scene 2 needs smoother lip sync"
    status, body, _ = api.call("POST", f"/submissions/{sub1['id']}/review",
                               {"decision": "approved", "approved_scene_ids": [scene_ids[0]], "feedback": feedback}, lead_tok)
    require("lead approves scene 1 and requests a revision of scene 2 with feedback", status in (200, 201), f"{status} {body}")
    status, body, _ = api.call("POST", f"/submissions/{sub1['id']}/review", {"decision": "approved"}, lead_tok)
    check("reviewing the same submission twice is refused (409)", status == 409, str(status))

    print("\nArtist: review feedback and resubmission")
    status, detail, _ = api.call("GET", f"/submissions/{sub1['id']}", token=artist_tok)
    check("artist can read the review feedback", status == 200 and feedback in json.dumps(detail), str(status))
    status, notes, _ = api.call("GET", "/notifications", token=artist_tok)
    check("artist received in-app notifications (assignment + review)", status == 200 and len(notes) >= 2, f"{status} {len(notes or [])}")
    status, sub2, _ = api.call("POST", "/submissions", {
        "assignment_id": assignment["id"], "scene_ids": [scene_ids[1]], "work_description": "E2E: scene 2 lip sync fixed",
        "output_links": ["https://example.com/e2e/render-v2"]}, artist_tok)
    require("artist resubmits the revised scene", status in (200, 201), f"{status} {sub2}")
    status, body, _ = api.call("POST", f"/submissions/{sub1['id']}/review", {"decision": "rejected", "feedback": "x"}, artist_tok)
    check("artist cannot review submissions (403)", status == 403, str(status))
    status, body, _ = api.call("POST", f"/submissions/{sub2['id']}/review", {"decision": "approved"}, lead_tok)
    check("lead approves the resubmission", status in (200, 201), f"{status} {body}")
    status, body, _ = api.call("POST", f"/assignments/{assignment['id']}/complete", {}, lead_tok)
    check("lead marks the fully approved assignment complete", status in (200, 201), f"{status} {body}")

    print("\nSession revocation")
    status, body, _ = api.call("POST", f"/users/{artist['id']}/deactivate", {}, admin)
    check("admin deactivates the dummy artist", status in (200, 201, 204), str(status))
    status, _, _ = api.call("GET", "/auth/me", token=artist_tok)
    check("deactivated artist's existing token is rejected (401)", status == 401, str(status))
    status, _, _ = api.call("POST", "/auth/login", {"email": artist_email, "password": artist_pw})
    check("deactivated artist cannot sign in (401)", status == 401, str(status))
    status, body, _ = api.call("POST", f"/users/{lead['id']}/deactivate", {}, admin)
    check("admin deactivates the dummy team lead", status in (200, 201, 204), str(status))

    summary()
    print(f"Dummy data left for inspection: team 'E2E Team {tag}', project 'E2E Project {tag}' (accounts deactivated).")
    sys.exit(0 if all(ok for _, ok, _ in RESULTS) else 1)


if __name__ == "__main__":
    main()
