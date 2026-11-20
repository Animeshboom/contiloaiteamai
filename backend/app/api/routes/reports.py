from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import client_ip, require_admin, require_lead_or_admin
from app.core.rate_limit import limiter
from app.core.timeutils import studio_today
from app.models import ReportStatus, User
from app.schemas.reports import (
    ReportApprove, ReportComment, ReportGenerate, ReportListItem, ReportOut, ReportSubmit, ReportUpdate,
)
from app.services import report_metrics, scope
from app.services import report_service as svc

router = APIRouter(prefix="/reports", tags=["EOD reports"])


@router.get("/metrics")
def preview_metrics(report_date: date | None = None, project_id: int | None = None, episode_id: int | None = None,
                    artist_id: int | None = None, team_id: int | None = None,
                    user: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    """Live deterministic metrics (no AI, nothing saved) for the EOD dashboard."""
    return report_metrics.compute(db, user, report_date or studio_today(), project_id=project_id,
                                  episode_id=episode_id, artist_id=artist_id,
                                  team_id=team_id if scope.is_admin(user) else None)


@router.get("", response_model=list[ReportListItem])
def list_reports(status: ReportStatus | None = None, user: User = Depends(require_lead_or_admin),
                 db: Session = Depends(get_db)):
    return [svc.to_list_item(db, r) for r in svc.list_for(db, user, status)]


@router.post("", response_model=ReportOut, status_code=201)
@limiter.limit("10/minute")
def generate_report(request: Request, body: ReportGenerate, user: User = Depends(require_lead_or_admin),
                    db: Session = Depends(get_db)):
    """Compute metrics, draft the narrative (Claude, or template fallback) and save a DRAFT report."""
    return svc.to_out(db, svc.generate(db, user, body, client_ip(request)))


@router.get("/team-status")
def team_status(report_date: date | None = None, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Admin: each team lead's report for the day and whether it has been sent."""
    return svc.team_status(db, report_date or studio_today())


@router.post("/{report_id}/submit", response_model=ReportOut)
def submit_report(report_id: int, body: ReportSubmit, request: Request, user: User = Depends(require_lead_or_admin),
                  db: Session = Depends(get_db)):
    """Send the day report to the admin in the app, with the lead's issues / remarks."""
    return svc.to_out(db, svc.submit_to_admin(db, user, report_id, body.issues, client_ip(request)))


@router.post("/{report_id}/comment", response_model=ReportOut)
def comment_report(report_id: int, body: ReportComment, request: Request, user: User = Depends(require_admin),
                   db: Session = Depends(get_db)):
    """Admin reply on a lead's report; the lead is notified."""
    return svc.to_out(db, svc.comment(db, user, report_id, body.comment, client_ip(request)))


@router.get("/{report_id}", response_model=ReportOut)
def get_report(report_id: int, user: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    return svc.to_out(db, svc.get(db, user, report_id))


@router.patch("/{report_id}", response_model=ReportOut)
def update_report(report_id: int, body: ReportUpdate, request: Request, user: User = Depends(require_lead_or_admin),
                  db: Session = Depends(get_db)):
    return svc.to_out(db, svc.update(db, user, report_id, body, client_ip(request)))


@router.post("/{report_id}/approve", response_model=ReportOut)
def approve_report(report_id: int, body: ReportApprove, request: Request, user: User = Depends(require_lead_or_admin),
                   db: Session = Depends(get_db)):
    return svc.to_out(db, svc.approve(db, user, report_id, [str(e) for e in body.recipients], client_ip(request)))


@router.post("/{report_id}/revoke", response_model=ReportOut)
def revoke_approval(report_id: int, request: Request, user: User = Depends(require_lead_or_admin),
                    db: Session = Depends(get_db)):
    return svc.to_out(db, svc.revoke(db, user, report_id, client_ip(request)))


@router.post("/{report_id}/send", response_model=ReportOut)
@limiter.limit("10/minute")
async def send_report(request: Request, report_id: int, user: User = Depends(require_lead_or_admin),
                      db: Session = Depends(get_db)):
    """Send an APPROVED report through the Gmail MCP server. Requires a separate approve step."""
    r = await svc.send(db, user, report_id, client_ip(request))
    return svc.to_out(db, r)


@router.post("/{report_id}/gmail-draft", response_model=ReportOut)
@limiter.limit("10/minute")
async def gmail_draft(request: Request, report_id: int, user: User = Depends(require_lead_or_admin),
                      db: Session = Depends(get_db)):
    """Optional: save the current report text as a Gmail draft (never sends)."""
    return svc.to_out(db, await svc.create_gmail_draft(db, user, report_id, client_ip(request)))

