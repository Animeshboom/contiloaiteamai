"""Projects, episodes and scenes."""
from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import client_ip, get_current_user, require_lead_or_admin
from app.models import ProjectStatus, User
from app.schemas.production import (
    EpisodeCreate, EpisodeOut, EpisodeUpdate, ProjectCreate, ProjectDetail, ProjectOut, ProjectUpdate, SceneBulkCreate,
    SceneCreate, SceneOut, SceneUpdate, ScreenplayImportRequest, ParsedSceneItem,
    BreakdownImportRequest, EpisodeImportResult, ScreenplayTextRequest,
)
from app.core.rate_limit import limiter
from app.services import production_service as svc
from app.services import screenplay_ai
from app.services.screenplay_ai import BreakdownResult

router = APIRouter(tags=["projects, episodes & scenes"])


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(status_: ProjectStatus | None = Query(default=None, alias="status"), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Leads/admins see all projects; artists see projects they are assigned to."""
    return svc.list_projects(db, user, status_)


@router.post("/projects", response_model=ProjectDetail, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, request: Request, user: User = Depends(require_lead_or_admin),
                   db: Session = Depends(get_db)):
    return svc.create_project(db, user, body, client_ip(request))


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(project_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.get_project(db, user, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectDetail)
def update_project(project_id: int, body: ProjectUpdate, request: Request, user: User = Depends(require_lead_or_admin),
                   db: Session = Depends(get_db)):
    return svc.update_project(db, user, project_id, body, client_ip(request))


@router.delete("/projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, request: Request, user: User = Depends(require_lead_or_admin),
                   db: Session = Depends(get_db)):
    svc.delete_project(db, user, project_id, client_ip(request))


@router.post("/projects/{project_id}/episodes", response_model=EpisodeOut, status_code=status.HTTP_201_CREATED)
def create_episode(project_id: int, body: EpisodeCreate, request: Request, user: User = Depends(require_lead_or_admin),
                   db: Session = Depends(get_db)):
    return svc.create_episode(db, user, project_id, body, client_ip(request))


@router.patch("/episodes/{episode_id}", response_model=EpisodeOut)
def update_episode(episode_id: int, body: EpisodeUpdate, request: Request, user: User = Depends(require_lead_or_admin),
                   db: Session = Depends(get_db)):
    return svc.update_episode(db, user, episode_id, body, client_ip(request))


@router.delete("/episodes/{episode_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_episode(episode_id: int, request: Request, user: User = Depends(require_lead_or_admin),
                   db: Session = Depends(get_db)):
    svc.delete_episode(db, user, episode_id, client_ip(request))


@router.post("/episodes/{episode_id}/scenes", response_model=SceneOut, status_code=status.HTTP_201_CREATED)
def create_scene(episode_id: int, body: SceneCreate, request: Request, user: User = Depends(require_lead_or_admin),
                 db: Session = Depends(get_db)):
    return svc.create_scene(db, user, episode_id, body, client_ip(request))


@router.post("/episodes/{episode_id}/scenes/bulk", response_model=list[SceneOut], status_code=status.HTTP_201_CREATED)
def bulk_create_scenes(episode_id: int, body: SceneBulkCreate, request: Request,
                       user: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    return svc.bulk_create_scenes(db, user, episode_id, body.count, client_ip(request))


@router.post("/episodes/{episode_id}/scenes/screenplay-import", response_model=list[SceneOut], status_code=status.HTTP_201_CREATED)
def import_screenplay(episode_id: int, body: ScreenplayImportRequest, request: Request,
                      user: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    """Parse and bulk import screenplay scenes directly into an episode."""
    return svc.import_screenplay_scenes(db, user, episode_id, body, client_ip(request))


@router.post("/projects/{project_id}/screenplay-import", response_model=list[SceneOut], status_code=status.HTTP_201_CREATED)
def import_screenplay_project(project_id: int, body: ScreenplayImportRequest, request: Request,
                              user: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    """Parse and bulk import screenplay scenes directly into a project (auto-creates Episode 1 if needed)."""
    return svc.import_screenplay_project(db, user, project_id, body, client_ip(request))


@router.post("/screenplay/upload-file")
async def upload_screenplay_file(file: UploadFile = File(...), user: User = Depends(require_lead_or_admin)):
    """Upload a script file (.docx, .txt, .fountain, .md), extract text, and return parsed scenes."""
    content = await file.read()
    raw_text = svc.extract_text_from_file(file.filename or "", content)
    parsed = svc.parse_screenplay_text(raw_text)
    return {
        "filename": file.filename,
        "raw_text": raw_text,
        "scenes": [ParsedSceneItem(**s) for s in parsed],
        "scene_count": len(parsed),
    }


# AI script breakdown. Plain `def` (not async): the Claude call blocks, so FastAPI runs it in a worker thread.
@router.post("/screenplay/ai-breakdown", response_model=BreakdownResult)
@limiter.limit("10/minute")
def ai_breakdown_file(request: Request, file: UploadFile = File(...), user: User = Depends(require_lead_or_admin),
                      db: Session = Depends(get_db)):
    """Upload a script (.docx, .pdf, .txt, .fountain, .md); the AI returns episodes, scenes, characters,
    locations, durations, artist notes and script issues. Falls back to the basic parser without AI."""
    content = file.file.read()
    name = file.filename or ""
    text = svc.extract_text_from_file(name, content)
    scanned_pdf = name.lower().endswith(".pdf") and not text.strip()
    return screenplay_ai.analyze(db, text, pdf_bytes=content if scanned_pdf else None, filename=name)


@router.post("/screenplay/ai-breakdown-text", response_model=BreakdownResult)
@limiter.limit("10/minute")
def ai_breakdown_text(request: Request, body: ScreenplayTextRequest, user: User = Depends(require_lead_or_admin),
                      db: Session = Depends(get_db)):
    """Same as /screenplay/ai-breakdown, for pasted script text."""
    return screenplay_ai.analyze(db, body.raw_text)


@router.post("/projects/{project_id}/screenplay-import-breakdown", response_model=list[EpisodeImportResult],
             status_code=status.HTTP_201_CREATED)
def import_breakdown(project_id: int, body: BreakdownImportRequest, request: Request,
                     user: User = Depends(require_lead_or_admin), db: Session = Depends(get_db)):
    """Import a reviewed breakdown: creates missing episodes, then their scenes, characters and locations."""
    return svc.import_breakdown(db, user, project_id, body, client_ip(request))


@router.post("/screenplay/parse", response_model=list[ParsedSceneItem])
def preview_screenplay_parse(body: ScreenplayImportRequest, user: User = Depends(require_lead_or_admin)):
    """Preview parsed scenes, durations, and characters from raw screenplay text."""
    if body.scenes:
        return body.scenes
    raw = body.raw_text or ""
    return [ParsedSceneItem(**s) for s in svc.parse_screenplay_text(raw)]


@router.patch("/scenes/{scene_id}", response_model=SceneOut)
def update_scene(scene_id: int, body: SceneUpdate, request: Request, user: User = Depends(require_lead_or_admin),
                 db: Session = Depends(get_db)):
    return svc.update_scene(db, user, scene_id, body, client_ip(request))


@router.delete("/scenes/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scene(scene_id: int, request: Request, user: User = Depends(require_lead_or_admin),
                 db: Session = Depends(get_db)):
    svc.delete_scene(db, user, scene_id, client_ip(request))
