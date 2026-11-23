"""Admin AI provider settings + the OpenAI / Gemini / OpenRouter adapters (HTTP faked)."""
import json

import httpx
import pytest

from app.core.config import get_settings
from app.models import AIProviderSetting
from app.services import ai_provider

URL = "/api/v1/admin/ai-settings"
KEY = "sk-test-1234567890abcd"


class FakeHTTP:
    """Stands in for httpx.post; records the request and returns a canned JSON reply."""

    def __init__(self, reply: dict, status: int = 200):
        self.reply, self.status, self.calls = reply, status, []

    def __call__(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        req = httpx.Request("POST", url)
        return httpx.Response(self.status, json=self.reply, request=req)


def _openai_reply(content: str, finish="stop"):
    return {"model": "gpt-test", "choices": [{"finish_reason": finish, "message": {"content": content}}]}


def _gemini_reply(text: str, finish="STOP"):
    return {"candidates": [{"finishReason": finish, "content": {"parts": [{"text": text}]}}]}


def test_only_admin_can_manage(client, as_lead):
    assert client.get(URL, headers=as_lead).status_code == 403


def test_key_is_encrypted_never_returned_and_admin_wins_over_env(client, as_admin, db, monkeypatch):
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "env-key-abcdefgh")
    data = client.get(URL, headers=as_admin).json()
    assert data["active_source"] == "env" and data["active_provider"] == "anthropic"

    r = client.put(f"{URL}/openai", headers=as_admin, json={"api_key": KEY, "model": "gpt-test", "make_active": True})
    assert r.status_code == 200, r.text
    data = r.json()
    assert KEY not in r.text
    openai = next(p for p in data["providers"] if p["provider"] == "openai")
    assert openai["has_key"] and openai["key_hint"] == "abcd" and openai["is_active"]
    assert data["active_provider"] == "openai" and data["active_source"] == "admin"

    row = db.get(AIProviderSetting, "openai")
    db.refresh(row)
    assert row.api_key_enc and KEY not in row.api_key_enc
    assert ai_provider.decrypt_key(row.api_key_enc) == KEY

    cfg = client.get("/api/v1/meta/config", headers=as_admin).json()
    assert cfg["ai_enabled"] and cfg["ai_provider"] == "OpenAI" and cfg["ai_model"] == "gpt-test"

    # Saving without a key keeps the old one; switching provider deactivates the previous one.
    r = client.put(f"{URL}/gemini", headers=as_admin, json={"api_key": "AIza-test-key-xyz9", "model": "gemini-test",
                                                         "make_active": True}).json()
    assert r["active_provider"] == "gemini"
    assert [p["provider"] for p in r["providers"] if p["is_active"]] == ["gemini"]
    r = client.put(f"{URL}/openai", headers=as_admin, json={"model": "gpt-test-2"}).json()
    assert next(p for p in r["providers"] if p["provider"] == "openai")["key_hint"] == "abcd"

    # Removing the active key falls back to the env key.
    r = client.delete(f"{URL}/gemini/key", headers=as_admin).json()
    assert r["active_provider"] == "anthropic" and r["active_source"] == "env"


def test_validation(client, as_admin):
    r = client.put(f"{URL}/openai", headers=as_admin, json={"model": "gpt-test", "make_active": True})
    assert r.status_code == 422  # no key yet
    r = client.put(f"{URL}/openai", headers=as_admin, json={"api_key": KEY, "make_active": True})
    assert r.status_code == 422  # no model
    r = client.put(f"{URL}/custom", headers=as_admin, json={"api_key": KEY, "model": "m", "base_url": "http://evil.example"})
    assert r.status_code == 422  # http only for localhost
    r = client.put(f"{URL}/custom", headers=as_admin,
                   json={"api_key": KEY, "model": "llama", "base_url": "http://localhost:11434/v1", "make_active": True})
    assert r.status_code == 200
    assert client.put(f"{URL}/nope", headers=as_admin, json={}).status_code == 404


def test_connection_test_openai(client, as_admin, monkeypatch):
    fake = FakeHTTP(_openai_reply('{"ok": true}'))
    monkeypatch.setattr(ai_provider.httpx, "post", fake)
    r = client.post(f"{URL}/test", headers=as_admin, json={"provider": "openai", "api_key": KEY, "model": "gpt-test"})
    assert r.json() == {"ok": True, "message": "Connected to OpenAI", "model": "gpt-test"}
    call = fake.calls[0]
    assert call["url"] == "https://api.openai.com/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {KEY}"
    assert call["json"]["response_format"] == {"type": "json_object"}

    monkeypatch.setattr(ai_provider.httpx, "post", FakeHTTP({"error": "bad key"}, status=401))
    r = client.post(f"{URL}/test", headers=as_admin, json={"provider": "openai", "api_key": KEY, "model": "gpt-test"})
    assert r.json()["ok"] is False and "rejected the API key" in r.json()["message"]


def test_gemini_adapter_and_breakdown_via_admin_provider(client, as_admin, monkeypatch):
    client.put(f"{URL}/gemini", headers=as_admin,
               json={"api_key": "AIza-test-key-xyz9", "model": "gemini-test", "make_active": True})
    breakdown = {"episodes": [{"episode_number": 1, "title": "Ep", "scenes": [
        {"scene_number": 1, "heading": "INT. HOUSE - DAY", "title": "INT. HOUSE - DAY", "location": "House",
         "characters": ["RAMA"], "duration_sec": 90, "duration_source": "estimate", "summary": "Rama waits."}]}],
        "issues": []}
    fake = FakeHTTP(_gemini_reply("```json\n" + json.dumps(breakdown) + "\n```"))
    monkeypatch.setattr(ai_provider.httpx, "post", fake)
    data = client.post("/api/v1/screenplay/ai-breakdown-text", headers=as_admin,
                       json={"raw_text": "INT. HOUSE - DAY\nRAMA\nHello."}).json()
    assert data["ai_used"] is True and data["provider"] == "Google Gemini"
    assert data["episodes"][0]["scenes"][0]["script_text"] == "RAMA\nHello."
    call = fake.calls[0]
    assert call["url"].endswith("/models/gemini-test:generateContent")
    assert call["headers"]["x-goog-api-key"] == "AIza-test-key-xyz9"
    assert call["json"]["generationConfig"]["responseMimeType"] == "application/json"


@pytest.mark.parametrize("reply,status", [
    (_openai_reply("not json"), "error"),
    (_openai_reply("{}", finish="length"), "truncated"),
    (_openai_reply("", finish="content_filter"), "refused"),
])
def test_openai_compatible_bad_replies(monkeypatch, reply, status):
    monkeypatch.setattr(ai_provider.httpx, "post", FakeHTTP(reply))
    cfg = ai_provider.AIConfig("openrouter", KEY, "some/model", "https://openrouter.ai/api/v1", "admin")
    assert ai_provider.test_connection(cfg).status == status


def test_report_narrative_uses_admin_provider(client, as_admin, monkeypatch):
    client.put(f"{URL}/openai", headers=as_admin, json={"api_key": KEY, "model": "gpt-test", "make_active": True})
    fake = FakeHTTP(_openai_reply(json.dumps({"summary": "No scenes were submitted.", "highlights": [], "concerns": []})))
    monkeypatch.setattr(ai_provider.httpx, "post", fake)
    r = client.post("/api/v1/reports", headers=as_admin, json={})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["ai_status"] == "generated", body["ai_note"]
    assert "Narrative drafted by OpenAI (gpt-test)" in body["body"]
