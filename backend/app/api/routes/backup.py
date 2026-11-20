"""Download a backup to keep on a local computer (team lead: their team; admin: everything)."""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import client_ip, require_lead_or_admin
from app.core.rate_limit import limiter
from app.models import User
from app.services import backup_service

router = APIRouter(tags=["backup"])


@router.get("/backup")
@limiter.limit("6/hour")
def download_backup(request: Request, actor: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    """ZIP of JSON files. No passwords or two-step secrets. Every download is recorded in the activity log."""
    filename, content = backup_service.build(db, actor, client_ip(request))
    return Response(content=content, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
