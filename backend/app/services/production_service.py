"""Projects, episodes and scenes."""
import re
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.timeutils import utcnow
from app.models import Episode, Project, ProjectCharacter, ProjectLocation, ProjectStatus, Scene, Team, User
from app.schemas.production import (
    EpisodeCreate, EpisodeOut, EpisodeUpdate, ProjectCreate, ProjectDetail, ProjectOut, ProjectUpdate,
    SceneCreate, SceneOut, SceneUpdate, ScreenplayImportRequest, ParsedSceneItem,
    BreakdownImportRequest, EpisodeImportResult,
)
from app.services import audit, scope


def _live_scenes(ep: Episode) -> list[Scene]:
    return [s for s in ep.scenes if s.deleted_at is None]


def _live_episodes(p: Project) -> list[Episode]:
    return [e for e in p.episodes if e.deleted_at is None]


def _project_out(db: Session, actor: User, p: Project, detail: bool = False) -> ProjectOut | ProjectDetail:
    eps = _live_episodes(p)
    team_name = db.scalar(select(Team.name).where(Team.id == p.team_id)) if p.team_id else None
    base = dict(
        id=p.id, code=p.code, title=p.title, description=p.description, project_type=p.project_type,
        status=p.status, start_date=p.start_date, expected_completion_date=p.expected_completion_date,
        team_id=p.team_id, team_name=team_name, created_at=p.created_at, episode_count=len(eps),
        scene_count=sum(len(_live_scenes(e)) for e in eps), can_manage=scope.can_manage_project(db, actor, p),
    )
    if not detail:
        return ProjectOut(**base)
    episodes = [
        EpisodeOut(id=e.id, project_id=e.project_id, episode_number=e.episode_number, title=e.title,
                   description=e.description, status=e.status,
                   scenes=[SceneOut.model_validate(s) for s in _live_scenes(e)])
        for e in eps
    ]
    return ProjectDetail(**base, episodes=episodes)


def list_projects(db: Session, actor: User, status: ProjectStatus | None = None) -> list[ProjectOut]:
    q = scope.project_query(db, actor)
    if status:
        q = q.where(Project.status == status)
    return [_project_out(db, actor, p) for p in db.scalars(q.order_by(Project.created_at.desc()))]


def get_project(db: Session, actor: User, project_id: int) -> ProjectDetail:
    return _project_out(db, actor, scope.get_project_for_view(db, actor, project_id), detail=True)


def _check_team(db: Session, actor: User, team_id: int | None) -> int | None:
    if team_id is None:
        if scope.is_lead(actor):  # leads' projects default to their own team
            teams = scope.lead_team_ids(db, actor)
            return actor.team_id if actor.team_id in teams else next(iter(teams), None)
        return None
    t = db.get(Team, team_id)
    if not t or t.deleted_at is not None:
        raise ValidationFailed("Team not found")
    if scope.is_lead(actor) and team_id not in scope.lead_team_ids(db, actor):
        raise ValidationFailed("You can only create projects for your own team")
    return team_id


def create_project(db: Session, actor: User, data: ProjectCreate, ip: str | None) -> ProjectDetail:
    code = data.code.upper()
    if db.scalar(select(Project.id).where(func.upper(Project.code) == code)):
        raise Conflict(f"Project code {code} is already in use")
    p = Project(
        code=code, title=data.title, description=data.description, project_type=data.project_type,
        status=data.status, start_date=data.start_date, expected_completion_date=data.expected_completion_date,
        team_id=_check_team(db, actor, data.team_id), created_by_id=actor.id,
    )
    db.add(p)
    db.flush()
    audit.record(db, actor_id=actor.id, action="project.create", entity_type="project", entity_id=p.id,
                 after=data.model_dump(), ip=ip)
    db.commit()
    db.refresh(p)
    return _project_out(db, actor, p, detail=True)


def update_project(db: Session, actor: User, project_id: int, data: ProjectUpdate, ip: str | None) -> ProjectDetail:
    p = scope.get_project_for_edit(db, actor, project_id)
    changes = data.model_dump(exclude_unset=True)
    before = {k: getattr(p, k) for k in changes}
    if "team_id" in changes:
        changes["team_id"] = _check_team(db, actor, changes["team_id"])
    for k, v in changes.items():
        setattr(p, k, v)
    if p.start_date and p.expected_completion_date and p.expected_completion_date < p.start_date:
        raise ValidationFailed("Expected completion date cannot be before the start date")
    audit.record(db, actor_id=actor.id, action="project.update", entity_type="project", entity_id=p.id,
                 before=before, after=changes, ip=ip)
    db.commit()
    db.refresh(p)
    return _project_out(db, actor, p, detail=True)


def delete_project(db: Session, actor: User, project_id: int, ip: str | None) -> None:
    p = scope.get_project_for_edit(db, actor, project_id)
    p.deleted_at = utcnow()
    audit.record(db, actor_id=actor.id, action="project.delete", entity_type="project", entity_id=p.id, ip=ip)
    db.commit()


# ---------------- episodes ----------------

def _ensure_episode_number_free(db: Session, project_id: int, number: int, exclude_id: int | None = None) -> None:
    q = select(Episode.id).where(Episode.project_id == project_id, Episode.episode_number == number)
    if exclude_id:
        q = q.where(Episode.id != exclude_id)
    existing = db.scalar(q)
    if existing:
        raise Conflict(f"Episode {number} already exists in this project")


def create_episode(db: Session, actor: User, project_id: int, data: EpisodeCreate, ip: str | None) -> EpisodeOut:
    p = scope.get_project_for_edit(db, actor, project_id)
    _ensure_episode_number_free(db, p.id, data.episode_number)
    ep = Episode(project_id=p.id, episode_number=data.episode_number, title=data.title, description=data.description)
    db.add(ep)
    db.flush()
    for n in range(1, data.scene_count + 1):
        db.add(Scene(episode_id=ep.id, scene_number=n, title=f"Scene {n:02d}"))
    audit.record(db, actor_id=actor.id, action="episode.create", entity_type="episode", entity_id=ep.id,
                 after=data.model_dump(), ip=ip)
    db.commit()
    db.refresh(ep)
    return _episode_out(ep)


def _episode_out(ep: Episode) -> EpisodeOut:
    return EpisodeOut(id=ep.id, project_id=ep.project_id, episode_number=ep.episode_number, title=ep.title,
                      description=ep.description, status=ep.status,
                      scenes=[SceneOut.model_validate(s) for s in _live_scenes(ep)])


def update_episode(db: Session, actor: User, episode_id: int, data: EpisodeUpdate, ip: str | None) -> EpisodeOut:
    ep = scope.get_episode_for_edit(db, actor, episode_id)
    changes = data.model_dump(exclude_unset=True)
    if "episode_number" in changes:
        _ensure_episode_number_free(db, ep.project_id, changes["episode_number"], exclude_id=ep.id)
    before = {k: getattr(ep, k) for k in changes}
    for k, v in changes.items():
        setattr(ep, k, v)
    audit.record(db, actor_id=actor.id, action="episode.update", entity_type="episode", entity_id=ep.id,
                 before=before, after=changes, ip=ip)
    db.commit()
    db.refresh(ep)
    return _episode_out(ep)


def delete_episode(db: Session, actor: User, episode_id: int, ip: str | None) -> None:
    ep = scope.get_episode_for_edit(db, actor, episode_id)
    ep.deleted_at = utcnow()
    audit.record(db, actor_id=actor.id, action="episode.delete", entity_type="episode", entity_id=ep.id, ip=ip)
    db.commit()


# ---------------- scenes ----------------

def _ensure_scene_number_free(db: Session, episode_id: int, number: int, exclude_id: int | None = None) -> None:
    q = select(Scene.id).where(Scene.episode_id == episode_id, Scene.scene_number == number)
    if exclude_id:
        q = q.where(Scene.id != exclude_id)
    if db.scalar(q):
        raise Conflict(f"Scene {number} already exists in this episode")


def create_scene(db: Session, actor: User, episode_id: int, data: SceneCreate, ip: str | None) -> SceneOut:
    ep = scope.get_episode_for_edit(db, actor, episode_id)
    _ensure_scene_number_free(db, ep.id, data.scene_number)
    sc = Scene(episode_id=ep.id, **data.model_dump())
    db.add(sc)
    db.flush()
    audit.record(db, actor_id=actor.id, action="scene.create", entity_type="scene", entity_id=sc.id,
                 after=data.model_dump(), ip=ip)
    db.commit()
    return SceneOut.model_validate(sc)


def bulk_create_scenes(db: Session, actor: User, episode_id: int, count: int, ip: str | None) -> list[SceneOut]:
    """Append `count` scenes after the highest existing scene number."""
    ep = scope.get_episode_for_edit(db, actor, episode_id)
    start = (db.scalar(select(func.max(Scene.scene_number)).where(Scene.episode_id == ep.id)) or 0) + 1
    created = []
    for n in range(start, start + count):
        sc = Scene(episode_id=ep.id, scene_number=n, title=f"Scene {n:02d}")
        db.add(sc)
        created.append(sc)
    db.flush()
    audit.record(db, actor_id=actor.id, action="scene.bulk_create", entity_type="episode", entity_id=ep.id,
                 after={"from": start, "count": count}, ip=ip)
    db.commit()
    return [SceneOut.model_validate(s) for s in created]


def update_scene(db: Session, actor: User, scene_id: int, data: SceneUpdate, ip: str | None) -> SceneOut:
    sc = scope.get_scene_for_edit(db, actor, scene_id)
    changes = data.model_dump(exclude_unset=True)
    if "scene_number" in changes:
        _ensure_scene_number_free(db, sc.episode_id, changes["scene_number"], exclude_id=sc.id)
    before = {k: getattr(sc, k) for k in changes}
    for k, v in changes.items():
        setattr(sc, k, v)
    audit.record(db, actor_id=actor.id, action="scene.update", entity_type="scene", entity_id=sc.id,
                 before=before, after=changes, ip=ip)
    db.commit()
    return SceneOut.model_validate(sc)


def delete_scene(db: Session, actor: User, scene_id: int, ip: str | None) -> None:
    sc = scope.get_scene_for_edit(db, actor, scene_id)
    sc.deleted_at = utcnow()
    audit.record(db, actor_id=actor.id, action="scene.delete", entity_type="scene", entity_id=sc.id, ip=ip)
    db.commit()


# Scene header formats, tried in order (first format that matches anything wins):
#   1. "01 | EXT. VILLAGE — MORNING | 01:15"   (extra "| notes" columns allowed)
#   2. "SCENE 1: Title"
#   3. Standard sluglines "INT. HOUSE - DAY" / "12. EXT. STREET - NIGHT" (auto-numbered when unnumbered)
_HEADER_RE = re.compile(
    r"^[ \t]*(\d+)[ \t]*\|[ \t]*([^|\n]+?)[ \t]*\|[ \t]*(\d{1,2}:\d{2})[ \t]*(?:\|[^\n]*)?$",
    re.MULTILINE
)
_SCENE_WORD_RE = re.compile(
    r"^[ \t]*SCENE[ \t]+(\d+)[ \t]*[:.\-–—][ \t]*([^\n]+)",
    re.MULTILINE | re.IGNORECASE
)
_SLUGLINE_RE = re.compile(
    r"^[ \t]*(?:(\d+)[A-Z]?[ \t]*[.):\-]?[ \t]*)?"
    r"((?:INT\.?[ \t]*/[ \t]*EXT|EXT\.?[ \t]*/[ \t]*INT|I/E|INT|EXT)\.?[ \t][^\n]*\S)[ \t]*$",
    re.MULTILINE
)
# A character cue: an ALL-CAPS name on its own line, or followed by ":" / "(V.O.)" / non-Latin dialogue.
_CHAR_RE = re.compile(r"^[ \t]*([A-Z][A-Z'\-]{2,19})(?=[ \t]*(?:$|[:(]|[^\x00-\x7F]))")
_IGNORE_CUES = {
    'CUT', 'EXT', 'INT', 'FADE', 'WIDE', 'BEAT', 'HALF', 'TITLE',
    'INSERT', 'LOW', 'AUDIENCE', 'CONTINUOUS', 'AERIAL', 'WHIP', 'PAN',
    'SOUND', 'EDIT', 'SHOT', 'ANGLE', 'POV', 'DISSOLVE',
    'DAY', 'NIGHT', 'MORNING', 'NOON', 'AFTERNOON', 'EVENING', 'SUNSET', 'SUNRISE', 'DAWN', 'DUSK',
    'LATER', 'LATE', 'THE', 'END', 'CAMERA', 'FREEZE', 'MONTAGE', 'CLOSE', 'MUSIC', 'SFX', 'VFX',
    'SUPER', 'INTERCUT', 'FLASHBACK', 'SMASH', 'MATCH', 'TRANSITION', 'BACK', 'ESTABLISHING',
    'CONT', 'MORE', 'TRACKING', 'ZOOM', 'TILT', 'OVERHEAD', 'MEDIUM', 'SERIES', 'SHOTS',
}
_TITLE_MAX = 200
_SCENE_MAX = 9999


def _duration(value: str | None) -> float | None:
    if not value:
        return None
    mins, _, secs = value.strip().partition(":")
    try:
        return float(int(mins) * 60 + int(secs))
    except ValueError:
        return None


def parse_screenplay_text(text: str) -> list[dict]:
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    matches: list[re.Match] = []
    for rx in (_HEADER_RE, _SCENE_WORD_RE, _SLUGLINE_RE):
        matches = list(rx.finditer(text))
        if matches:
            break
    if not matches:
        return []

    parsed = []
    used: set[int] = set()
    for i, m in enumerate(matches):
        # Every scene needs a unique number in 1..9999 (DB constraint). Missing, out-of-range or
        # repeated numbers get the next free number so nothing is dropped and the import can't crash.
        num = int(m.group(1)) if m.group(1) else None
        if num is None or not (1 <= num <= _SCENE_MAX) or num in used:
            num = max(used, default=0) + 1
        used.add(num)

        title = m.group(2).strip()[:_TITLE_MAX] or None
        dur_sec = _duration(m.group(3)) if m.re is _HEADER_RE else None

        end_idx = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end_idx].strip()

        chars = []
        for line in body.splitlines():
            cm = _CHAR_RE.match(line)
            if cm:
                name = cm.group(1).strip("'-")
                if len(name) >= 3 and name not in _IGNORE_CUES and name not in chars:
                    chars.append(name)

        parsed.append({
            "scene_number": num,
            "title": title,
            "description": body,
            "duration_sec": dur_sec,
            "characters": chars,
        })
    return parsed


def _get_or_create(db: Session, model, project_id: int, name: str):
    obj = db.scalar(select(model).where(model.project_id == project_id, model.name == name))
    if obj is None:
        obj = model(project_id=project_id, name=name)
        db.add(obj)
        db.flush()
    return obj


def _apply_scene_items(db: Session, ep: Episode, items: list[dict], replace_existing: bool) -> list[Scene]:
    """Create/update the given scenes in one episode (no commit). Raises on empty or duplicate numbers."""
    if not items:
        raise ValidationFailed(f"No scenes to import into episode {ep.episode_number}")
    seen: set[int] = set()
    dupes = sorted({it["scene_number"] for it in items if it["scene_number"] in seen or seen.add(it["scene_number"])})
    if dupes:
        raise ValidationFailed(f"Scene number(s) used more than once: {', '.join(map(str, dupes))}")

    existing_map = {s.scene_number: s for s in db.scalars(select(Scene).where(Scene.episode_id == ep.id))}
    imported_nums = {item["scene_number"] for item in items}

    if replace_existing:
        for s_num, s_obj in existing_map.items():
            if s_num not in imported_nums and s_obj.deleted_at is None:
                s_obj.deleted_at = utcnow()

    out = []
    for item in items:
        num = item["scene_number"]
        ref_links = []
        if item.get("drive_link"):
            ref_links.append({"label": "Google Drive", "url": item["drive_link"]})

        sc = existing_map.get(num)
        if sc is not None:
            sc.title = item.get("title") or sc.title or f"Scene {num:02d}"
            sc.description = item.get("description")
            sc.duration_sec = item.get("duration_sec")
            if ref_links:
                sc.reference_links = ref_links
            sc.deleted_at = None
        else:
            sc = Scene(
                episode_id=ep.id,
                scene_number=num,
                title=item.get("title") or f"Scene {num:02d}",
                description=item.get("description"),
                duration_sec=item.get("duration_sec"),
                reference_links=ref_links,
            )
            db.add(sc)

        loc_name = (item.get("location") or "").strip()[:120]
        if loc_name:
            sc.location_id = _get_or_create(db, ProjectLocation, ep.project_id, loc_name).id

        for c_name in item.get("characters") or []:
            c_name = c_name.strip()[:120]
            if not c_name:
                continue
            pc = _get_or_create(db, ProjectCharacter, ep.project_id, c_name)
            if pc not in sc.characters:
                sc.characters.append(pc)

        out.append(sc)
    db.flush()
    return out


def import_screenplay_scenes(db: Session, actor: User, episode_id: int, data: ScreenplayImportRequest,
                            ip: str | None) -> list[SceneOut]:
    ep = scope.get_episode_for_edit(db, actor, episode_id)
    items = []
    if data.scenes:
        items = [s.model_dump() for s in data.scenes]
    elif data.raw_text:
        items = parse_screenplay_text(data.raw_text)

    if not items:
        raise ValidationFailed("No scenes could be parsed from the screenplay text")

    created_or_updated = _apply_scene_items(db, ep, items, data.replace_existing)
    audit.record(db, actor_id=actor.id, action="scene.import_screenplay", entity_type="episode", entity_id=ep.id,
                 after={"scenes_count": len(created_or_updated)}, ip=ip)
    db.commit()
    return [SceneOut.model_validate(s) for s in created_or_updated]


def import_breakdown(db: Session, actor: User, project_id: int, data: BreakdownImportRequest,
                     ip: str | None) -> list[EpisodeImportResult]:
    """Import a reviewed (AI) breakdown: creates missing episodes by number, then their scenes."""
    p = scope.get_project_for_edit(db, actor, project_id)
    if not data.episodes:
        raise ValidationFailed("No episodes to import")
    nums = [e.episode_number for e in data.episodes]
    if len(nums) != len(set(nums)):
        raise ValidationFailed("Episode numbers must be unique")

    by_num = {e.episode_number: e for e in p.episodes}
    results = []
    for item in data.episodes:
        ep = by_num.get(item.episode_number)
        created = ep is None or ep.deleted_at is not None
        if ep is None:
            ep = Episode(project_id=p.id, episode_number=item.episode_number,
                         title=item.title or f"Episode {item.episode_number:02d}")
            db.add(ep)
            db.flush()
        elif ep.deleted_at is not None:
            ep.deleted_at = None
            ep.title = item.title or ep.title
        scenes = _apply_scene_items(db, ep, [s.model_dump() for s in item.scenes], data.replace_existing)
        results.append(EpisodeImportResult(episode_id=ep.id, episode_number=ep.episode_number, created=created,
                                           scenes=[SceneOut.model_validate(s) for s in scenes]))
    audit.record(db, actor_id=actor.id, action="scene.import_breakdown", entity_type="project", entity_id=p.id,
                 after={"episodes": len(results), "scenes_count": sum(len(r.scenes) for r in results)}, ip=ip)
    db.commit()
    return results


def get_scene(db: Session, scene_id: int) -> Scene:
    sc = db.get(Scene, scene_id)
    if not sc or sc.deleted_at is not None:
        raise NotFound("Scene not found")
    return sc


_SCRIPT_EXTS = (".docx", ".pdf", ".txt", ".fountain", ".md")
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _docx_paragraph_text(p) -> str:
    out = []
    for el in p.iter():
        if el.tag == _W + "t" and el.text:
            out.append(el.text)
        elif el.tag == _W + "tab":
            out.append("\t")
        elif el.tag in (_W + "br", _W + "cr"):
            out.append("\n")
    return "".join(out)


def _docx_to_text(content: bytes) -> str:
    import io, zipfile, xml.etree.ElementTree as ET
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as z:
            tree = ET.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ET.ParseError):
        raise ValidationFailed("Could not read this Word file. Save it as .docx (not .doc) and try again.")
    body = tree.find(_W + "body")
    lines: list[str] = []
    for child in (body if body is not None else []):
        if child.tag == _W + "tbl":
            # One line per table row, cells joined with " | " so "01 | HEADING | 01:15" tables parse.
            for tr in child.findall(_W + "tr"):
                cells = [" ".join(_docx_paragraph_text(p) for p in tc.iter(_W + "p")).strip()
                         for tc in tr.findall(_W + "tc")]
                cells = [c for c in cells if c]
                if cells:
                    lines.append(" | ".join(cells))
        else:
            for p in ([child] if child.tag == _W + "p" else child.iter(_W + "p")):
                t = _docx_paragraph_text(p)
                if t.strip():
                    lines.append(t)
    return "\n\n".join(lines)


def _pdf_to_text(content: bytes) -> str:
    """Text layer of a PDF ("" for scanned/image-only PDFs — the AI breakdown can still read those)."""
    import io
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
    if not content.startswith(b"%PDF"):
        raise ValidationFailed("This doesn't look like a PDF file.")
    try:
        reader = PdfReader(io.BytesIO(content))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except (PdfReadError, ValueError, KeyError) as e:
        raise ValidationFailed("Could not read this PDF file.") from e


def extract_text_from_file(filename: str, content: bytes) -> str:
    """Extract plain text from uploaded screenplay file (.docx, .pdf, .txt, .fountain, .md)."""
    from app.core.config import get_settings
    name_lower = (filename or "").lower()
    if not name_lower.endswith(_SCRIPT_EXTS):
        raise ValidationFailed("Unsupported file type. Upload a .docx, .pdf, .txt, .fountain or .md script.")
    limit_mb = get_settings().max_upload_mb
    if len(content) > limit_mb * 1024 * 1024:
        raise ValidationFailed(f"File exceeds the {limit_mb} MB limit")
    if not content.strip():
        raise ValidationFailed("The file is empty.")
    if name_lower.endswith(".docx"):
        return _docx_to_text(content)
    if name_lower.endswith(".pdf"):
        return _pdf_to_text(content)
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return content.decode("utf-16")
    if b"\x00" in content or content.startswith(b"PK\x03\x04"):
        raise ValidationFailed("This doesn't look like a text file. Save the script as .txt or .docx.")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="replace")


def import_screenplay_project(db: Session, actor: User, project_id: int, data: ScreenplayImportRequest,
                              ip: str | None) -> list[SceneOut]:
    p = scope.get_project_for_edit(db, actor, project_id)
    episodes = _live_episodes(p)
    if not episodes:
        ep = Episode(project_id=p.id, episode_number=1, title="Episode 01")
        db.add(ep)
        db.flush()
    else:
        ep = episodes[0]
    return import_screenplay_scenes(db, actor, ep.id, data, ip)
