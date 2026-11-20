from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import client_ip, get_current_user, require_lead_or_admin
from app.core.rate_limit import limiter
from app.core.timeutils import studio_today
from app.models import User
from app.schemas.attendance import (
    AttendanceCorrection, AttendanceOut, CheckOut, DailyCount, MonthStats, RosterRow, TodayStatus,
)
from app.services import attendance_service as svc

router = APIRouter(prefix="/attendance", tags=["attendance"])


@router.get("/today", response_model=TodayStatus)
def today(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.today_status(db, user)


@router.post("/check-in", response_model=AttendanceOut)
@limiter.limit("20/minute")
def check_in(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.check_in(db, user, client_ip(request))


@router.post("/check-out", response_model=AttendanceOut)
@limiter.limit("20/minute")
def check_out(request: Request, body: CheckOut | None = None, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    """Optional body {note}: what I did today / blockers (feeds the lead's evening report)."""
    return svc.check_out(db, user, client_ip(request), body.note if body else None)


@router.get("/me/month", response_model=MonthStats)
def my_month(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """This month's attendance so far (half days count 0.5; approved leave counts like an absence)."""
    return svc.month_stats(db, [user])[user.id]


@router.get("/me", response_model=list[AttendanceOut])
def my_history(start: date | None = None, end: date | None = None, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    end = end or studio_today()
    return svc.history(db, user, user.id, start or end - timedelta(days=30), end)


@router.get("/users/{user_id}", response_model=list[AttendanceOut])
def user_history(user_id: int, start: date | None = None, end: date | None = None,
                 actor: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    end = end or studio_today()
    return svc.history(db, actor, user_id, start or end - timedelta(days=30), end)


@router.get("/roster", response_model=list[RosterRow])
def roster(on: date | None = None, team_id: int | None = None, actor: User = Depends(require_lead_or_admin),
           db: Session = Depends(get_db)):
    """Everyone the caller oversees, with their status for the date (default: studio today)."""
    return svc.roster(db, actor, on or studio_today(), team_id)


@router.get("/summary", response_model=list[DailyCount])
def summary(start: date | None = None, end: date | None = None, team_id: int | None = None,
            actor: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    end = end or studio_today()
    start = start or end - timedelta(days=13)
    if (end - start).days > 92:
        start = end - timedelta(days=92)
    return svc.daily_counts(db, actor, start, end, team_id)


@router.put("/correct", response_model=AttendanceOut)
def correct(body: AttendanceCorrection, request: Request, actor: User = Depends(require_lead_or_admin),
            db: Session = Depends(get_db)):
    """Create or correct a record. The reason is stored and the change is written to the audit log."""
    return svc.correct(db, actor, body, client_ip(request))


@router.get("/export")
def export_month(month: str = Query(pattern=r"^\d{4}-\d{2}$"), team_id: int | None = None,
                 user: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    """Monthly staff sheet as CSV (P / H / L / A / - / off per day, totals, hours worked)."""
    filename, content = svc.export_month_csv(db, user, month, team_id)
    # The byte-order mark makes Excel open the UTF-8 file with the right encoding.
    return Response(content="\ufeff" + content, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
