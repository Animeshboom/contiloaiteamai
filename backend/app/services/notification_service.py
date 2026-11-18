"""In-app notifications + email for important events.

Every notification has a deterministic ``dedupe_key`` (unique in the DB), and every email a
deterministic idempotency key, so replaying an event — a retried request, a re-run job —
never produces a duplicate. Notifications and queued emails commit atomically with the
change that caused them (the caller's transaction).

Events -> recipients:
  assignment_created      artist          in-app + email (send_artist_notification)
  submission_received     team lead(s)    in-app
  submission_approved     artist          in-app + email (send_artist_notification)
  submission_rejected     artist          in-app + email (send_task_revision_notification)
  deadline_approaching    artist          in-app + email (send_artist_notification)
  daily_report_generated  report author   in-app                  (Phase 5)
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.timeutils import ensure_utc, to_studio
from app.models import Assignment, AssignmentAssignee, Notification, RoleName, Submission, Team, User
from app.services import email_service


def notify(db: Session, *, user_id: int, event_type: str, title: str, message: str, dedupe_key: str,
           link: str | None = None, entity_type: str | None = None, entity_id: int | None = None) -> Notification | None:
    """Create an in-app notification once. Returns None if it already exists."""
    if db.scalar(select(Notification.id).where(Notification.dedupe_key == dedupe_key)):
        return None
    n = Notification(user_id=user_id, event_type=event_type, title=title[:200], message=message, link=link,
                     entity_type=entity_type, entity_id=entity_id, dedupe_key=dedupe_key[:200])
    try:
        with db.begin_nested():  # a concurrent duplicate loses on the unique constraint, not the whole request
            db.add(n)
    except IntegrityError:
        return None
    return n


def _url(path: str) -> str:
    return get_settings().app_base_url.rstrip("/") + path


def _ep(a: Assignment) -> str:
    return f"EP{a.episode.episode_number:02d} {a.episode.title}" if a.episode else ""


def _due(a: Assignment) -> str:
    return to_studio(a.deadline).strftime("%d %b %Y, %H:%M")


def _scene_labels(a: Assignment) -> str:
    labels = sorted(s.scene.label for s in a.scenes)
    return ", ".join(labels) if labels else "deliverable"


# ---------------- events ----------------

def assignment_created(db: Session, a: Assignment, artist: User) -> None:
    link = f"/artist/assignments?open={a.id}"
    msg = f"{a.project.title} · {_scene_labels(a)} · due {_due(a)}"
    notify(db, user_id=artist.id, event_type="assignment_created", title=f"New assignment: {a.title}", message=msg,
           link=link, entity_type="assignment", entity_id=a.id, dedupe_key=f"assignment:{a.id}:assigned:{artist.id}")
    body = (f"Hi {artist.full_name.split(' (')[0]},\n\nYou have a new assignment from {a.created_by.full_name}.\n\n"
            f"Project: {a.project.title}\nEpisode: {_ep(a) or '—'}\nScenes: {_scene_labels(a)}\n"
            f"Priority: {a.priority.value.title()}\nDeadline: {_due(a)} (studio time)\n")
    if a.description:
        body += f"\nTask:\n{a.description}\n"
    if a.expected_deliverables:
        body += f"\nExpected deliverables:\n{a.expected_deliverables}\n"
    body += f"\nOpen it in StudioTrack: {_url(link)}"
    subject = f"New assignment: {a.title}"
    email_service.enqueue(
        db, tool="send_artist_notification", idempotency_key=f"email:assignment:{a.id}:assigned:{artist.id}",
        args={"recipient_email": artist.email, "subject": subject, "message_body": body,
              "assignment_reference": f"Assignment #{a.id}"},
        recipients=[artist.email], subject=subject, preview=body, entity_type="assignment", entity_id=a.id,
        triggered_by_id=a.created_by_id,
    )


def _leads_for(db: Session, sub: Submission) -> set[int]:
    """Assignment creator (if a lead/admin) + the artist's team lead."""
    ids = set()
    creator = sub.assignment.created_by
    if creator and creator.role_name in (RoleName.TEAM_LEAD, RoleName.ADMIN) and creator.is_active:
        ids.add(creator.id)
    if sub.artist.team_id:
        lead_id = db.scalar(select(Team.lead_id).where(Team.id == sub.artist.team_id))
        if lead_id:
            ids.add(lead_id)
    return ids


def submission_received(db: Session, sub: Submission) -> None:
    a = sub.assignment
    what = ", ".join(d.label for d in sub.deliverables)
    kind = "Revised submission" if sub.previous_submission_id else "New submission"
    for lead_id in _leads_for(db, sub):
        notify(db, user_id=lead_id, event_type="submission_received",
               title=f"{kind} from {sub.artist.full_name.split(' (')[0]}",
               message=f"{a.project.code} · {a.title} · {what}", link=f"/lead/reviews?open={sub.id}",
               entity_type="submission", entity_id=sub.id, dedupe_key=f"submission:{sub.id}:received:{lead_id}")


def submission_approved(db: Session, sub: Submission) -> None:
    a = sub.assignment
    what = ", ".join(d.label for d in sub.deliverables)
    reviewer = sub.reviews[-1].reviewer if sub.reviews else None
    link = f"/artist/history?open={sub.id}"
    notify(db, user_id=sub.artist_id, event_type="submission_approved", title=f"Approved: {what}",
           message=f"{a.project.title} · {a.title}", link=link, entity_type="submission", entity_id=sub.id,
           dedupe_key=f"submission:{sub.id}:approved")
    body = (f"Your submission #{sub.id} was approved"
            f"{f' by {reviewer.full_name}' if reviewer else ''}.\n\nProject: {a.project.title}\n"
            f"Episode: {_ep(a) or '—'}\nApproved: {what}\n")
    if sub.reviews and sub.reviews[-1].feedback:
        body += f"\nComments:\n{sub.reviews[-1].feedback}\n"
    body += f"\nView it in StudioTrack: {_url(link)}"
    subject = f"Approved: {a.title}"
    email_service.enqueue(
        db, tool="send_artist_notification", idempotency_key=f"email:submission:{sub.id}:approved",
        args={"recipient_email": sub.artist.email, "subject": subject, "message_body": body,
              "assignment_reference": f"Assignment #{a.id} · Submission #{sub.id}"},
        recipients=[sub.artist.email], subject=subject, preview=body, entity_type="submission", entity_id=sub.id,
        triggered_by_id=reviewer.id if reviewer else None,
    )


def submission_rejected(db: Session, sub: Submission) -> None:
    """Covers full rejection and partial approval (some scenes sent back)."""
    a = sub.assignment
    review = sub.reviews[-1]
    revise = [d.label for d in sub.deliverables if d.status.value == "rejected"]
    approved = [d.label for d in sub.deliverables if d.status.value == "approved"]
    link = f"/artist/submit?assignment={a.id}"
    msg = f"Revise: {', '.join(revise)}" + (f" · Approved: {', '.join(approved)}" if approved else "")
    notify(db, user_id=sub.artist_id, event_type="revision_requested", title=f"Revision requested: {a.title}",
           message=f"{msg}. “{(review.feedback or '')[:140]}”", link=link, entity_type="submission",
           entity_id=sub.id, dedupe_key=f"submission:{sub.id}:rejected")
    feedback = review.feedback or ""
    if approved:
        feedback = f"(Approved in this submission: {', '.join(approved)})\n\n{feedback}"
    email_service.enqueue(
        db, tool="send_task_revision_notification", idempotency_key=f"email:submission:{sub.id}:revision",
        args={"artist_email": sub.artist.email, "project_title": a.project.title, "episode": _ep(a),
              "scene_references": revise, "team_lead_feedback": feedback, "assignment_link": _url(link)},
        recipients=[sub.artist.email], subject=f"Revision requested: {a.project.title}", preview=feedback,
        entity_type="submission", entity_id=sub.id, triggered_by_id=review.reviewer_id,
    )


def deadline_approaching(db: Session, x: AssignmentAssignee) -> bool:
    a = x.assignment
    stamp = int(ensure_utc(a.deadline).timestamp())  # a moved deadline gets its own reminder
    link = f"/artist/assignments?open={a.id}"
    created = notify(db, user_id=x.user_id, event_type="deadline_approaching", title=f"Due soon: {a.title}",
                     message=f"Due {_due(a)} (studio time) · {_scene_labels(a)}", link=link,
                     entity_type="assignment", entity_id=a.id, dedupe_key=f"deadline:{x.id}:{stamp}")
    if created is None:
        return False
    body = (f"Reminder: your assignment is due {_due(a)} (studio time).\n\nProject: {a.project.title}\n"
            f"Episode: {_ep(a) or '—'}\nScenes: {_scene_labels(a)}\n\nSubmit your work: {_url('/artist/submit?assignment=' + str(a.id))}")
    subject = f"Due soon: {a.title}"
    email_service.enqueue(
        db, tool="send_artist_notification", idempotency_key=f"email:deadline:{x.id}:{stamp}",
        args={"recipient_email": x.user.email, "subject": subject, "message_body": body,
              "assignment_reference": f"Assignment #{a.id}"},
        recipients=[x.user.email], subject=subject, preview=body, entity_type="assignment", entity_id=a.id,
    )
    return True


def daily_report_generated(db: Session, report_id: int, user_id: int, report_date: str) -> None:
    notify(db, user_id=user_id, event_type="daily_report_generated", title=f"Daily report ready: {report_date}",
           message="Review, edit and approve it before sending.", link=f"/lead/reports?open={report_id}",
           entity_type="daily_report", entity_id=report_id, dedupe_key=f"report:{report_id}:generated")

