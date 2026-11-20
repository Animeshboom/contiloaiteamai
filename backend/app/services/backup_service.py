"""Download a backup (ZIP of JSON files) to keep on a local computer.

- Team lead: their team's people, attendance, leave, assignments, submissions (with reviews) and their reports.
- Admin: everything, plus teams, projects, holidays, announcements and the activity log.
Never included: password hashes, two-step secrets, Supabase ids, session data. Uploaded files are listed
(name, size) but not included; they stay in file storage.
"""
import io
import json
import zipfile
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutils import utcnow
from app.models import (
    Announcement, Assignment, AssignmentAssignee, Attendance, AuditLog, DailyReport, Episode, Holiday, LeaveRequest,
    Project, Scene, Submission, Team, User,
)
from app.services import audit, scope


def _json(rows) -> str:
    def default(o):
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        if hasattr(o, "value"):
            return o.value
        return str(o)
    return json.dumps(rows, default=default, ensure_ascii=False, indent=1)


def _person(u: User) -> dict:
    return {"id": u.id, "name": u.full_name, "email": u.email, "employee_code": u.employee_code,
            "role": u.role_name, "team": u.team.name if u.team else None, "job_title": u.job_title,
            "phone": u.phone, "is_active": u.is_active, "created_at": u.created_at}


def build(db: Session, actor: User, ip: str | None) -> tuple[str, bytes]:
    admin = scope.is_admin(actor)
    ids = scope.visible_user_ids(db, actor)  # None = everyone
    people = list(db.scalars(select(User).where(User.deleted_at.is_(None)) if ids is None
                             else select(User).where(User.id.in_(ids or {-1}))))
    pids = [u.id for u in people]

    attendance = db.scalars(select(Attendance).where(Attendance.user_id.in_(pids or [-1])).order_by(Attendance.work_date))
    leave = db.scalars(select(LeaveRequest).where(LeaveRequest.user_id.in_(pids or [-1])))
    assignments = list(db.scalars(scope.assignment_query(db, actor)))
    slot_ids = [x.id for a in assignments for x in a.assignees]
    submissions = db.scalars(select(Submission).where(Submission.assignee_id.in_(slot_ids or [-1])))
    reports = db.scalars(select(DailyReport) if admin else select(DailyReport).where(
        (DailyReport.created_by_id == actor.id) | DailyReport.team_id.in_(scope.lead_team_ids(db, actor) or {-1})))

    files = {
        "people.json": [_person(u) for u in people],
        "attendance.json": [{"person_id": r.user_id, "date": r.work_date, "status": r.status, "check_in": r.check_in_at,
                             "check_out": r.check_out_at, "notes": r.notes, "work_note": r.work_note} for r in attendance],
        "leave.json": [{"person_id": r.user_id, "start": r.start_day, "end": r.end_day, "reason": r.reason,
                        "status": r.status, "decision_note": r.decision_note} for r in leave],
        "assignments.json": [{
            "id": a.id, "title": a.title, "project_id": a.project_id, "episode_id": a.episode_id,
            "description": a.description, "deadline": a.deadline, "priority": a.priority, "status": a.status,
            "created_by_id": a.created_by_id, "scene_ids": [s.scene_id for s in a.scenes],
            "assignees": [{"person_id": x.user_id, "status": x.status, "progress_pct": x.reported_progress_pct}
                          for x in a.assignees]} for a in assignments],
        "submissions.json": [{
            "id": s.id, "assignment_id": s.assignment_id, "person_id": s.artist_id, "status": s.status,
            "submitted_at": s.submitted_at, "description": s.work_description, "output_links": s.output_links,
            "attachments": [{"name": f.original_filename, "size": f.size_bytes} for f in s.attachments],
            "reviews": [{"decision": r.decision, "feedback": r.feedback, "rating": r.rating, "at": r.created_at}
                        for r in s.reviews]} for s in submissions],
        "day_reports.json": [{"id": r.id, "date": r.report_date, "subject": r.subject, "body": r.body,
                              "issues": r.issues, "submitted_at": r.submitted_at, "admin_comment": r.admin_comment}
                             for r in reports],
    }
    if admin:
        files["teams.json"] = [{"id": t.id, "name": t.name, "lead_id": t.lead_id}
                               for t in db.scalars(select(Team).where(Team.deleted_at.is_(None)))]
        files["projects.json"] = [{
            "id": p.id, "code": p.code, "title": p.title, "status": p.status,
            "episodes": [{"id": e.id, "number": e.episode_number, "title": e.title,
                          "scenes": [{"id": s.id, "number": s.scene_number, "status": s.status}
                                     for s in db.scalars(select(Scene).where(Scene.episode_id == e.id))]}
                         for e in db.scalars(select(Episode).where(Episode.project_id == p.id))]}
            for p in db.scalars(select(Project).where(Project.deleted_at.is_(None)))]
        files["holidays.json"] = [{"date": h.day, "name": h.name, "teams": [t.name for t in h.teams]}
                                  for h in db.scalars(select(Holiday))]
        files["announcements.json"] = [{"title": a.title, "body": a.body, "teams": [t.name for t in a.teams],
                                        "show_until": a.show_until, "created_at": a.created_at}
                                       for a in db.scalars(select(Announcement))]
        files["activity_log.json"] = [{"at": r.created_at, "actor_id": r.actor_id, "action": r.action,
                                       "entity": f"{r.entity_type}:{r.entity_id}", "details": r.after}
                                      for r in db.scalars(select(AuditLog).order_by(AuditLog.id))]

    stamp = utcnow().strftime("%Y-%m-%d_%H%M")
    who = "studio" if admin else "team"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("README.txt", f"StudioTrack backup ({who}) made {stamp} UTC by {actor.full_name}.\n"
                                 "JSON files, one per kind of record. Passwords and two-step secrets are never included.\n"
                                 "Uploaded files are listed in submissions.json but not included.\n")
        for name, rows in files.items():
            z.writestr(name, _json(rows))
    audit.record(db, actor_id=actor.id, action="backup.download", entity_type="user", entity_id=actor.id,
                 after={"scope": who, "files": list(files)}, ip=ip)
    db.commit()
    return f"studiotrack-{who}-backup-{stamp}.zip", buf.getvalue()
