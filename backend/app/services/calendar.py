"""Working days and holidays.

A day is a *work day* when its weekday is in WORK_DAYS, it is not in the HOLIDAYS setting, and no holiday is
recorded for everyone or for the person's team. Holidays are cached for a minute (and dropped immediately
when one changes here).
"""
import time as _time
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.errors import NotFound, ValidationFailed
from app.core.timeutils import is_work_day as _weekday_rule
from app.models import Holiday, Team, User
from app.services import audit

TTL_SECONDS = 60


@dataclass(frozen=True)
class _Entry:
    name: str
    applies_to_all: bool
    team_ids: frozenset[int]


_cache: dict = {"at": None, "days": {}}


def invalidate() -> None:
    _cache["at"] = None


def _entries(d: date) -> list[_Entry]:
    now = _time.monotonic()
    if _cache["at"] is None or now - _cache["at"] > TTL_SECONDS:
        days: dict[date, list[_Entry]] = {}
        with SessionLocal() as db:
            for h in db.scalars(select(Holiday)):
                days.setdefault(h.day, []).append(
                    _Entry(h.name, h.applies_to_all, frozenset(t.id for t in h.teams)))
        _cache["days"], _cache["at"] = days, now
    return _cache["days"].get(d, [])


def holiday_name(d: date, team_id: int | None = None) -> str | None:
    for e in _entries(d):
        if e.applies_to_all or (team_id is not None and team_id in e.team_ids):
            return e.name
    return None


def is_work_day(d: date, team_id: int | None = None) -> bool:
    """Weekday rule, settings holidays, holidays for everyone, and (with ``team_id``) that team's holidays."""
    return _weekday_rule(d) and holiday_name(d, team_id) is None


# ---------------- admin management ----------------

def list_holidays(db: Session, year: int | None = None) -> list[Holiday]:
    q = select(Holiday)
    if year:
        q = q.where(Holiday.day >= date(year, 1, 1), Holiday.day <= date(year, 12, 31))
    return list(db.scalars(q.order_by(Holiday.day, Holiday.id)))


def create_holiday(db: Session, actor: User, day: date, name: str, team_ids: list[int], ip: str | None) -> Holiday:
    teams = []
    for tid in dict.fromkeys(team_ids):
        t = db.get(Team, tid)
        if not t or t.deleted_at is not None:
            raise ValidationFailed(f"Team {tid} not found")
        teams.append(t)
    h = Holiday(day=day, name=name.strip(), applies_to_all=not teams, teams=teams)
    db.add(h)
    db.flush()
    audit.record(db, actor_id=actor.id, action="holiday.create", entity_type="holiday", entity_id=h.id,
                 after={"day": day, "name": h.name, "team_ids": [t.id for t in teams]}, ip=ip)
    db.commit()
    invalidate()
    db.refresh(h)
    return h


def delete_holiday(db: Session, actor: User, holiday_id: int, ip: str | None) -> None:
    h = db.get(Holiday, holiday_id)
    if not h:
        raise NotFound("Holiday not found")
    audit.record(db, actor_id=actor.id, action="holiday.delete", entity_type="holiday", entity_id=h.id,
                 before={"day": h.day, "name": h.name}, ip=ip)
    db.delete(h)
    db.commit()
    invalidate()
