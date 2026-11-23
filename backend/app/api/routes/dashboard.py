from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_any_user, require_artist, require_lead_or_admin
from app.core.timeutils import studio_today
from app.models import User
from app.services import ai_provider, dashboard_service

router = APIRouter(tags=["dashboard & meta"])


@router.get("/meta/config")
def config(_: User = Depends(get_any_user), db: Session = Depends(get_db)):
    """Non-secret settings the UI needs to render times correctly."""
    s = get_settings()
    ai = ai_provider.active_config(db)
    return {
        "studio_timezone": s.studio_timezone,
        "eod_deadline_hour": s.eod_deadline_hour,
        "studio_today": studio_today(),
        "email_provider": s.email_provider,
        "gmail_backend": s.gmail_backend,
        "ai_enabled": ai is not None,
        "ai_provider": ai.short if ai else None,
        "ai_model": ai.model if ai else None,
        "max_upload_mb": s.max_upload_mb,
        "email_enabled": s.email_enabled,
        "auth_provider": s.auth_provider,
        "low_attendance_pct": s.low_attendance_pct,
        "show_checkin_times": s.show_checkin_times,
    }


@router.get("/dashboard/overview")
def staff_overview(team_id: int | None = None, user: User = Depends(require_lead_or_admin),
                   db: Session = Depends(get_db)):
    return dashboard_service.staff_overview(db, user, team_id)


@router.get("/dashboard/me")
def artist_overview(user: User = Depends(require_artist), db: Session = Depends(get_db)):
    return dashboard_service.artist_overview(db, user)
