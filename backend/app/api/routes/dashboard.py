from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_artist, require_lead_or_admin
from app.core.timeutils import studio_today
from app.models import User
from app.services import dashboard_service

router = APIRouter(tags=["dashboard & meta"])


@router.get("/meta/config")
def config(_: User = Depends(get_current_user)):
    """Non-secret settings the UI needs to render times correctly."""
    s = get_settings()
    return {
        "studio_timezone": s.studio_timezone,
        "eod_deadline_hour": s.eod_deadline_hour,
        "studio_today": studio_today(),
        "email_provider": s.email_provider,
        "ai_enabled": bool(s.anthropic_api_key),
        "max_upload_mb": s.max_upload_mb,
    }


@router.get("/dashboard/overview")
def staff_overview(team_id: int | None = None, user: User = Depends(require_lead_or_admin),
                   db: Session = Depends(get_db)):
    return dashboard_service.staff_overview(db, user, team_id)


@router.get("/dashboard/me")
def artist_overview(user: User = Depends(require_artist), db: Session = Depends(get_db)):
    return dashboard_service.artist_overview(db, user)
