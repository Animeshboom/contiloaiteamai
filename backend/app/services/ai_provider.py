"""Which AI provider the app uses, and one way to ask any of them for structured JSON.

Providers: Anthropic (Claude, official SDK), OpenAI, Google Gemini, OpenRouter and any other
OpenAI-compatible endpoint ("custom"). The admin picks one on the Settings page; its key is stored
encrypted in `ai_providers`. With nothing active there, ANTHROPIC_API_KEY from the environment is used.

Callers (script breakdown, EOD report narrative) get back a validated Pydantic object or a clear
status (refused / truncated / error) so they can fall back to their non-AI path.
"""
import base64
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlparse

import httpx
from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationFailed

log = logging.getLogger("studiotrack.ai_provider")

ProviderName = Literal["anthropic", "openai", "gemini", "openrouter", "custom"]
PROVIDERS: dict[str, dict] = {
    "anthropic": {"label": "Anthropic (Claude)", "short": "Claude", "default_model": "claude-opus-5-5", "base_url": None},
    "openai": {"label": "OpenAI", "short": "OpenAI", "default_model": None, "base_url": "https://api.openai.com/v1"},
    "gemini": {"label": "Google Gemini", "short": "Gemini", "default_model": None,
               "base_url": "https://generativelanguage.googleapis.com/v1beta"},
    "openrouter": {"label": "OpenRouter", "short": "OpenRouter", "default_model": None, "base_url": "https://openrouter.ai/api/v1"},
    "custom": {"label": "Custom (OpenAI-compatible)", "short": "AI", "default_model": None, "base_url": None},
}


@dataclass
class AIConfig:
    provider: str
    api_key: str
    model: str
    base_url: str | None
    source: Literal["admin", "env"]

    @property
    def label(self) -> str:
        return PROVIDERS[self.provider]["label"]

    @property
    def short(self) -> str:
        return PROVIDERS[self.provider]["short"]


@dataclass
class AIResult:
    status: Literal["ok", "refused", "truncated", "error"]
    parsed: BaseModel | None = None
    model: str | None = None
    note: str | None = None


# ---------------- key storage ----------------

def _fernet() -> Fernet:
    key = hashlib.sha256(("ai-keys:" + get_settings().jwt_secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_key(key: str) -> str:
    return _fernet().encrypt(key.encode()).decode()


def decrypt_key(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        log.warning("Stored AI key can't be decrypted (JWT_SECRET_KEY changed?); ignoring it")
        return None


def validate_base_url(url: str | None) -> str | None:
    """https only, except plain http to this machine (e.g. a local model server)."""
    if not url:
        return None
    url = url.strip().rstrip("/")
    u = urlparse(url)
    local = u.hostname in ("localhost", "127.0.0.1", "::1")
    if u.scheme not in ("https", "http") or not u.hostname or (u.scheme == "http" and not local):
        raise ValidationFailed("Base URL must start with https:// (http:// is allowed only for localhost)")
    return url


def active_config(db: Session) -> AIConfig | None:
    from app.models import AIProviderSetting  # noqa: PLC0415

    try:
        row = db.scalar(select(AIProviderSetting).where(AIProviderSetting.is_active.is_(True)))
    except SQLAlchemyError:
        # e.g. the ai_providers migration hasn't run yet: never break the app, just use the env key.
        log.warning("Could not read ai_providers (migration not run?); falling back to ANTHROPIC_API_KEY")
        db.rollback()
        row = None
    if row is not None:
        key = decrypt_key(row.api_key_enc)
        meta = PROVIDERS.get(row.provider)
        model = row.model or (meta or {}).get("default_model")
        base_url = row.base_url or (meta or {}).get("base_url")
        if key and meta and model and (row.provider in ("anthropic",) or base_url):
            return AIConfig(row.provider, key, model, base_url, "admin")
    s = get_settings()
    if s.anthropic_api_key:
        return AIConfig("anthropic", s.anthropic_api_key, s.anthropic_model, None, "env")
    return None


# ---------------- calling a provider ----------------

def _json_instructions(schema: type[BaseModel]) -> str:
    return ("\n\nReply with ONLY a JSON object (no markdown, no commentary) that matches this JSON Schema:\n"
            + json.dumps(schema.model_json_schema(), ensure_ascii=False))


_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def _parse_json(text: str, schema: type[BaseModel]) -> BaseModel | None:
    text = _FENCE.sub("", text or "").strip()
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        text = text[start:end + 1] if start != -1 and end > start else text
    try:
        return schema.model_validate(json.loads(text))
    except (json.JSONDecodeError, ValidationError) as e:
        log.warning("AI reply was not valid JSON for %s: %s", schema.__name__, type(e).__name__)
        return None


def _anthropic_client(api_key: str, timeout: float):
    import anthropic  # noqa: PLC0415
    return anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=timeout)


def _call_anthropic(cfg: AIConfig, system: str, text: str | None, pdf: bytes | None, schema: type[BaseModel],
                    max_tokens: int, timeout: float, effort: str) -> AIResult:
    import anthropic  # noqa: PLC0415

    content: list[dict] = []
    if pdf:
        content.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                       "data": base64.standard_b64encode(pdf).decode()}})
    if text:
        content.append({"type": "text", "text": text})
    try:
        with _anthropic_client(cfg.api_key, timeout).beta.messages.stream(
            model=cfg.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_format=schema,
            output_config={"effort": effort},
            # Server-side refusal fallback: if the primary model declines, the API re-runs on a fallback model.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        ) as stream:
            response = stream.get_final_message()
    except anthropic.AuthenticationError:
        return AIResult("error", note="Anthropic rejected the API key")
    except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.APIStatusError) as e:
        log.warning("Anthropic call failed: %s", type(e).__name__)
        return AIResult("error", note=f"Anthropic API error ({type(e).__name__})")
    if response.stop_reason == "refusal":
        return AIResult("refused", model=response.model)
    if response.stop_reason == "max_tokens":
        return AIResult("truncated", model=response.model)
    if response.parsed_output is None:
        return AIResult("error", model=response.model, note="AI response could not be read")
    return AIResult("ok", response.parsed_output, response.model)


def _http_error(provider: str, e: Exception) -> AIResult:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code in (401, 403):
            return AIResult("error", note=f"{PROVIDERS[provider]['label']} rejected the API key")
        if code == 404:
            return AIResult("error", note=f"{PROVIDERS[provider]['label']}: model or URL not found")
        return AIResult("error", note=f"{PROVIDERS[provider]['label']} API error (HTTP {code})")
    return AIResult("error", note=f"Could not reach {PROVIDERS[provider]['label']} ({type(e).__name__})")


def _call_openai_compatible(cfg: AIConfig, system: str, text: str | None, pdf: bytes | None,
                            schema: type[BaseModel], max_tokens: int, timeout: float) -> AIResult:
    parts: list[dict] = []
    if pdf:
        parts.append({"type": "file", "file": {
            "filename": "script.pdf", "file_data": "data:application/pdf;base64," + base64.b64encode(pdf).decode()}})
    parts.append({"type": "text", "text": text or "See the attached file."})
    body = {
        "model": cfg.model,
        "messages": [{"role": "system", "content": system + _json_instructions(schema)},
                     {"role": "user", "content": parts}],
        "response_format": {"type": "json_object"},
        "max_completion_tokens" if cfg.provider == "openai" else "max_tokens": max_tokens,
    }
    headers = {"Authorization": f"Bearer {cfg.api_key}"}
    try:
        r = httpx.post(f"{cfg.base_url}/chat/completions", json=body, headers=headers, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("%s call failed: %s", cfg.provider, type(e).__name__)
        return _http_error(cfg.provider, e)
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    model = data.get("model") or cfg.model
    if msg.get("refusal") or choice.get("finish_reason") == "content_filter":
        return AIResult("refused", model=model)
    if choice.get("finish_reason") == "length":
        return AIResult("truncated", model=model)
    parsed = _parse_json(msg.get("content") or "", schema)
    return AIResult("ok", parsed, model) if parsed else AIResult("error", model=model, note="AI reply was not valid JSON")


def _call_gemini(cfg: AIConfig, system: str, text: str | None, pdf: bytes | None, schema: type[BaseModel],
                 max_tokens: int, timeout: float) -> AIResult:
    parts: list[dict] = []
    if pdf:
        parts.append({"inline_data": {"mime_type": "application/pdf", "data": base64.b64encode(pdf).decode()}})
    parts.append({"text": text or "See the attached file."})
    body = {
        "systemInstruction": {"parts": [{"text": system + _json_instructions(schema)}]},
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": max_tokens},
    }
    try:
        r = httpx.post(f"{cfg.base_url}/models/{cfg.model}:generateContent", json=body,
                       headers={"x-goog-api-key": cfg.api_key}, timeout=timeout)
        r.raise_for_status()
        data = r.json()
    except (httpx.HTTPError, ValueError) as e:
        log.warning("gemini call failed: %s", type(e).__name__)
        return _http_error("gemini", e)
    if (data.get("promptFeedback") or {}).get("blockReason"):
        return AIResult("refused", model=cfg.model)
    cand = (data.get("candidates") or [{}])[0]
    reason = cand.get("finishReason")
    if reason in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "RECITATION"):
        return AIResult("refused", model=cfg.model)
    if reason == "MAX_TOKENS":
        return AIResult("truncated", model=cfg.model)
    reply = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    parsed = _parse_json(reply, schema)
    return AIResult("ok", parsed, cfg.model) if parsed else AIResult("error", model=cfg.model, note="AI reply was not valid JSON")


def structured(cfg: AIConfig, *, system: str, schema: type[BaseModel], text: str | None = None,
               pdf: bytes | None = None, max_tokens: int = 16000, timeout: float = 600.0,
               effort: str = "medium") -> AIResult:
    """Ask the configured provider for a JSON object matching `schema`. Never raises for API problems."""
    if cfg.provider == "anthropic":
        return _call_anthropic(cfg, system, text, pdf, schema, max_tokens, timeout, effort)
    if cfg.provider == "gemini":
        return _call_gemini(cfg, system, text, pdf, schema, max_tokens, timeout)
    return _call_openai_compatible(cfg, system, text, pdf, schema, max_tokens, timeout)


class _Ping(BaseModel):
    ok: bool


def test_connection(cfg: AIConfig) -> AIResult:
    """Tiny request to check the key, model and URL work."""
    return structured(cfg, system="You are a connectivity check.", schema=_Ping,
                      text='Reply with {"ok": true}.', max_tokens=2000, timeout=60.0, effort="low")
