"""Admin: choose the AI provider (Anthropic, OpenAI, Gemini, OpenRouter, custom) and manage its API key.

Keys are write-only: they are stored encrypted and only the last 4 characters are ever returned.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import client_ip, require_admin
from app.core.errors import NotFound, ValidationFailed
from app.core.rate_limit import limiter
from app.models import AIProviderSetting, User
from app.services import ai_provider, audit
from app.services.ai_provider import PROVIDERS, ProviderName

router = APIRouter(prefix="/admin/ai-settings", tags=["admin: AI provider"])


class ProviderOut(BaseModel):
    provider: str
    label: str
    has_key: bool
    key_hint: str | None
    model: str | None
    default_model: str | None
    base_url: str | None
    default_base_url: str | None
    is_active: bool
    updated_at: datetime | None


class AISettingsOut(BaseModel):
    providers: list[ProviderOut]
    active_provider: str | None
    active_source: str | None  # admin | env | None
    env_key_present: bool


class ProviderUpdate(BaseModel):
    api_key: str | None = Field(default=None, max_length=500, description="Omit to keep the saved key")
    model: str | None = Field(default=None, max_length=120)
    base_url: str | None = Field(default=None, max_length=300)
    make_active: bool = False


class TestRequest(BaseModel):
    provider: ProviderName
    api_key: str | None = Field(default=None, max_length=500, description="Omit to test the saved key")
    model: str | None = Field(default=None, max_length=120)
    base_url: str | None = Field(default=None, max_length=300)


class TestResult(BaseModel):
    ok: bool
    message: str
    model: str | None = None


def _rows(db: Session) -> dict[str, AIProviderSetting]:
    return {r.provider: r for r in db.scalars(select(AIProviderSetting))}


def _out(db: Session) -> AISettingsOut:
    rows = _rows(db)
    providers = []
    for name, meta in PROVIDERS.items():
        r = rows.get(name)
        providers.append(ProviderOut(
            provider=name, label=meta["label"], has_key=bool(r and r.api_key_enc), key_hint=r.key_hint if r else None,
            model=r.model if r else None, default_model=meta["default_model"],
            base_url=r.base_url if r else None, default_base_url=meta["base_url"],
            is_active=bool(r and r.is_active), updated_at=r.updated_at if r else None,
        ))
    cfg = ai_provider.active_config(db)
    return AISettingsOut(providers=providers, active_provider=cfg.provider if cfg else None,
                         active_source=cfg.source if cfg else None,
                         env_key_present=bool(get_settings().anthropic_api_key))


def _check_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise NotFound("Unknown AI provider")


def _clean_key(key: str | None) -> str | None:
    key = (key or "").strip()
    if key and (len(key) < 8 or any(c.isspace() for c in key)):
        raise ValidationFailed("That doesn't look like an API key")
    return key or None


@router.get("", response_model=AISettingsOut)
def get_ai_settings(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _out(db)


@router.put("/{provider}", response_model=AISettingsOut)
def update_provider(provider: str, body: ProviderUpdate, request: Request, actor: User = Depends(require_admin),
                    db: Session = Depends(get_db)):
    _check_provider(provider)
    meta = PROVIDERS[provider]
    row = db.get(AIProviderSetting, provider) or AIProviderSetting(provider=provider)
    if row not in db:
        db.add(row)
    key = _clean_key(body.api_key)
    if key:
        row.api_key_enc = ai_provider.encrypt_key(key)
        row.key_hint = key[-4:]
    row.model = (body.model or "").strip() or None
    row.base_url = ai_provider.validate_base_url(body.base_url)
    row.updated_by_id = actor.id

    if body.make_active:
        if not row.api_key_enc:
            raise ValidationFailed(f"Add an API key for {meta['label']} before making it active")
        if not (row.model or meta["default_model"]):
            raise ValidationFailed(f"Enter a model name for {meta['label']}")
        if not (row.base_url or meta["base_url"]) and provider != "anthropic":
            raise ValidationFailed("Enter the base URL for the custom provider")
        for other in db.scalars(select(AIProviderSetting).where(AIProviderSetting.provider != provider)):
            other.is_active = False
        row.is_active = True
    audit.record(db, actor_id=actor.id, action="settings.ai_provider", entity_type="ai_provider", entity_id=None,
                 after={"provider": provider, "key_changed": bool(key), "model": row.model,
                        "base_url": row.base_url, "active": row.is_active},
                 ip=client_ip(request))
    db.commit()
    return _out(db)


@router.post("/{provider}/deactivate", response_model=AISettingsOut)
def deactivate(provider: str, request: Request, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Stop using this provider (the app falls back to ANTHROPIC_API_KEY from the server, if set)."""
    _check_provider(provider)
    row = db.get(AIProviderSetting, provider)
    if row and row.is_active:
        row.is_active = False
        audit.record(db, actor_id=actor.id, action="settings.ai_provider", entity_type="ai_provider", entity_id=None,
                     after={"provider": provider, "active": False}, ip=client_ip(request))
        db.commit()
    return _out(db)


@router.delete("/{provider}/key", response_model=AISettingsOut)
def delete_key(provider: str, request: Request, actor: User = Depends(require_admin), db: Session = Depends(get_db)):
    _check_provider(provider)
    row = db.get(AIProviderSetting, provider)
    if row:
        row.api_key_enc = None
        row.key_hint = None
        row.is_active = False
        row.updated_by_id = actor.id
        audit.record(db, actor_id=actor.id, action="settings.ai_provider", entity_type="ai_provider", entity_id=None,
                     after={"provider": provider, "key_removed": True}, ip=client_ip(request))
        db.commit()
    return _out(db)


@router.post("/test", response_model=TestResult, status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
def test_provider(request: Request, body: TestRequest, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Send a tiny request with the given (or saved) key so the admin knows it works before saving."""
    meta = PROVIDERS[body.provider]
    row = db.get(AIProviderSetting, body.provider)
    key = _clean_key(body.api_key) or (ai_provider.decrypt_key(row.api_key_enc) if row else None)
    if not key and body.provider == "anthropic":
        key = get_settings().anthropic_api_key
    if not key:
        return TestResult(ok=False, message="Enter an API key first")
    model = (body.model or "").strip() or (row.model if row else None) or meta["default_model"]
    if not model:
        return TestResult(ok=False, message="Enter a model name first")
    base_url = ai_provider.validate_base_url(body.base_url) or (row.base_url if row else None) or meta["base_url"]
    if body.provider != "anthropic" and not base_url:
        return TestResult(ok=False, message="Enter the base URL first")
    res = ai_provider.test_connection(ai_provider.AIConfig(body.provider, key, model, base_url, "admin"))
    if res.status == "ok":
        return TestResult(ok=True, message=f"Connected to {meta['label']}", model=res.model)
    if res.status == "refused":
        return TestResult(ok=True, message=f"Connected to {meta['label']} (the test prompt was declined, but the key works)",
                          model=res.model)
    return TestResult(ok=False, message=res.note or "The test request failed", model=res.model)
