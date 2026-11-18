from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import client_ip, get_current_user, require_artist, require_lead_or_admin
from app.core.errors import NotFound
from app.core.rate_limit import limiter
from app.models import SubmissionStatus, User
from app.schemas.assignments import AssignmentOut
from app.schemas.submissions import ProgressUpdate, ReviewCreate, SubmissionCreate, SubmissionOut
from app.services import assignment_service, email_service, files
from app.services import submission_service as svc

router = APIRouter(tags=["submissions & reviews"])


@router.put("/assignments/{assignment_id}/progress", response_model=AssignmentOut)
def update_progress(assignment_id: int, body: ProgressUpdate, request: Request, user: User = Depends(require_artist),
                    db: Session = Depends(get_db)):
    """Artist self-reported progress. Does not mark anything as complete or approved."""
    a = assignment_service.update_progress(db, user, assignment_id, body.reported_progress_pct, body.progress_note,
                                           client_ip(request))
    return assignment_service.to_out(db, a)


@router.post("/assignments/{assignment_id}/complete", response_model=AssignmentOut)
def complete_assignment(assignment_id: int, request: Request, user: User = Depends(require_lead_or_admin),
                        db: Session = Depends(get_db)):
    return assignment_service.to_out(db, assignment_service.complete(db, user, assignment_id, client_ip(request)))


@router.get("/submissions", response_model=list[SubmissionOut])
def list_submissions(
    status_: SubmissionStatus | None = Query(default=None, alias="status"),
    assignment_id: int | None = None,
    artist_id: int | None = None,
    project_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Artists: own submissions. Leads: their team's. Admins: all. Pending queue is oldest-first."""
    rows = svc.list_for(db, user, status=status_, assignment_id=assignment_id, artist_id=artist_id, project_id=project_id)
    return [svc.to_out(db, s) for s in rows]


@router.post("/submissions", response_model=SubmissionOut, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
def create_submission(request: Request, body: SubmissionCreate, background: BackgroundTasks,
                      user: User = Depends(require_artist), db: Session = Depends(get_db)):
    out = svc.to_out(db, svc.create(db, user, body, client_ip(request)))
    background.add_task(email_service.dispatch_pending)
    return out


@router.get("/submissions/{submission_id}", response_model=SubmissionOut)
def get_submission(submission_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.to_out(db, svc.get_for_view(db, user, submission_id))


@router.post("/submissions/{submission_id}/attachments", response_model=SubmissionOut,
             status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def upload_attachment(request: Request, submission_id: int, file: UploadFile = File(...),
                            user: User = Depends(require_artist), db: Session = Depends(get_db)):
    sub = await svc.add_attachment(db, user, submission_id, file, client_ip(request))
    return svc.to_out(db, sub)


@router.get("/submissions/{submission_id}/attachments/{attachment_id}")
def download_attachment(submission_id: int, attachment_id: int, user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    att = svc.get_attachment(db, user, submission_id, attachment_id)
    path = files.resolve(att.stored_filename)
    if not path.is_file():
        raise NotFound("File is missing from storage")
    return FileResponse(
        path, filename=att.original_filename, media_type="application/octet-stream",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )


@router.post("/submissions/{submission_id}/review", response_model=SubmissionOut)
def review_submission(submission_id: int, body: ReviewCreate, request: Request, background: BackgroundTasks,
                      user: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    """Approve (all or selected scenes) or reject with feedback. Each review is a new, permanent record."""
    out = svc.to_out(db, svc.review(db, user, submission_id, body, client_ip(request)))
    background.add_task(email_service.dispatch_pending)
    return out
