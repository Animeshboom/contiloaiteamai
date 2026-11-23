"""AI script breakdown: fallback without a key, Claude path (faked), runtime check, multi-episode import."""
from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.services import ai_provider
from app.services import screenplay_ai as sai

SCRIPT = """EPISODE 1

INT. HOUSE - DAY
RAMA
Where is the mango?

EXT. MARKET - MORNING
KOTI
It's here!

EPISODE 2

EXT. RIVER - EVENING
RAMA
Let's swim.
"""


def _scene(num, heading, location, chars, dur, source="estimate", **kw):
    return sai.AIScene(scene_number=num, heading=heading, title=heading, location=location, characters=chars,
                       duration_sec=dur, duration_source=source, summary=f"Scene {num} happens.", **kw)


AI_RESULT = sai.AIBreakdown(
    episodes=[
        sai.AIEpisode(episode_number=1, title="The Mango", scenes=[
            _scene(1, "INT. HOUSE - DAY", "House", ["rama"], 700, mood="Curious", props=["Mango"]),
            _scene(2, "EXT. MARKET - MORNING", "Market", ["KOTI"], 600, source="script"),
        ]),
        sai.AIEpisode(episode_number=2, title="The River", scenes=[
            _scene(1, "EXT. RIVER - EVENING", "River", ["RAMA"], 60),
        ]),
    ],
    issues=[sai.AIIssue(severity="medium", episode_number=1, scene_number=2, message="Koti's age is unclear.")],
)


class FakeStream:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return self.response


class FakeClaude:
    def __init__(self, parsed, stop_reason="end_turn"):
        self.calls = []
        self.response = SimpleNamespace(parsed_output=parsed, stop_reason=stop_reason, model="claude-opus-5-5")
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        self.calls.append(kwargs)
        return FakeStream(self.response)


@pytest.fixture
def claude(monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key")

    def install(fake):
        monkeypatch.setattr(ai_provider, "_anthropic_client", lambda *a, **k: fake)
        return fake
    return install


def test_breakdown_without_key_uses_basic_parser(client, as_admin, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", None)
    r = client.post("/api/v1/screenplay/ai-breakdown-text", headers=as_admin, json={"raw_text": SCRIPT})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["ai_used"] is False and "ANTHROPIC_API_KEY" in data["note"]
    assert data["scene_count"] == 3
    assert data["runtime"][0]["status"] == "unknown"


def test_breakdown_with_claude(client, as_admin, claude):
    fake = claude(FakeClaude(AI_RESULT))
    r = client.post("/api/v1/screenplay/ai-breakdown", headers=as_admin,
                    files={"file": ("ep.txt", SCRIPT.encode(), "text/plain")})
    assert r.status_code == 200, r.text
    data = r.json()
    call = fake.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["output_format"] is sai.AIBreakdown
    assert "<script>" in call["messages"][0]["content"][0]["text"]

    assert data["ai_used"] is True and data["scene_count"] == 3
    ep1, ep2 = data["episodes"]
    s1 = ep1["scenes"][0]
    assert s1["characters"] == ["RAMA"] and s1["location"] == "House"
    assert s1["duration_estimated"] is True and ep1["scenes"][1]["duration_estimated"] is False
    # Scene text is cut from the original script, and artist notes go into the saved description.
    assert s1["script_text"] == "RAMA\nWhere is the mango?"
    assert "Mood: Curious" in s1["description"] and "Props: Mango" in s1["description"]
    assert "Where is the mango?" in s1["description"]
    assert ep2["scenes"][0]["script_text"] == "RAMA\nLet's swim."
    # Runtime is computed in code: 1300s is within 10% of 22:00; 60s is short.
    assert data["runtime"][0]["status"] == "on_target"
    assert data["runtime"][1]["status"] == "short"
    assert data["issues"][0]["message"] == "Koti's age is unclear."


@pytest.mark.parametrize("stop_reason,status", [("refusal", "refused"), ("max_tokens", "truncated")])
def test_breakdown_falls_back_when_ai_cannot_finish(client, as_admin, claude, stop_reason, status):
    claude(FakeClaude(None, stop_reason=stop_reason))
    data = client.post("/api/v1/screenplay/ai-breakdown-text", headers=as_admin, json={"raw_text": SCRIPT}).json()
    assert data["ai_used"] is False and data["status"] == status and data["scene_count"] == 3


def test_scanned_pdf_is_sent_to_claude_as_document(claude, db):
    fake = claude(FakeClaude(AI_RESULT))
    sai.analyze(db, "", pdf_bytes=b"%PDF-1.4 fake", filename="s.pdf")
    block = fake.calls[0]["messages"][0]["content"][0]
    assert block["type"] == "document" and block["source"]["media_type"] == "application/pdf"


def test_runtime_check_flags_outlier_scenes():
    scenes = [sai.BreakdownScene(scene_number=i, duration_sec=d) for i, d in enumerate([60, 60, 60, 600, 10], 1)]
    check = sai.runtime_checks([sai.BreakdownEpisode(episode_number=1, title="E", scenes=scenes)])[0]
    assert check.status == "short" and check.long_scenes == [4] and check.short_scenes == [5]


def test_import_breakdown_creates_episodes_characters_locations(client, as_admin):
    pid = client.post("/api/v1/projects", headers=as_admin,
                      json={"code": "AI-1", "title": "AI Import", "project_type": "series"}).json()["id"]
    body = {"replace_existing": False, "episodes": [
        {"episode_number": 1, "title": "The Mango", "scenes": [
            {"scene_number": 1, "title": "INT. HOUSE - DAY", "duration_sec": 700, "characters": ["RAMA"],
             "location": "House", "description": "ARTIST NOTES\nMood: Curious"},
            {"scene_number": 2, "title": "EXT. MARKET", "characters": ["KOTI", "RAMA"], "location": "Market"}]},
        {"episode_number": 2, "title": "The River", "scenes": [
            {"scene_number": 1, "title": "EXT. RIVER", "location": "House"}]},
    ]}
    r = client.post(f"/api/v1/projects/{pid}/screenplay-import-breakdown", headers=as_admin, json=body)
    assert r.status_code == 201, r.text
    res = r.json()
    assert [(e["episode_number"], e["created"], len(e["scenes"])) for e in res] == [(1, True, 2), (2, True, 1)]
    assert res[0]["scenes"][1]["characters"] == ["KOTI", "RAMA"]

    detail = client.get(f"/api/v1/projects/{pid}", headers=as_admin).json()
    assert detail["episode_count"] == 2 and detail["scene_count"] == 3

    # Re-import is an update, not a duplicate.
    r = client.post(f"/api/v1/projects/{pid}/screenplay-import-breakdown", headers=as_admin, json=body)
    assert r.status_code == 201 and [e["created"] for e in r.json()] == [False, False]
    assert r.json()[0]["scenes"][0]["id"] == res[0]["scenes"][0]["id"]

    bad = {"episodes": [{"episode_number": 1, "scenes": [{"scene_number": 1}]},
                        {"episode_number": 1, "scenes": [{"scene_number": 2}]}]}
    assert client.post(f"/api/v1/projects/{pid}/screenplay-import-breakdown", headers=as_admin,
                       json=bad).status_code == 422
