"""All timestamps are stored in UTC; 'work dates' are computed in the studio timezone."""
from datetime import date, datetime, time, timezone

from app.core.config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    """Treat naive datetimes (e.g. from SQLite) as UTC."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def studio_today() -> date:
    return utcnow().astimezone(get_settings().tz).date()


def to_studio(dt: datetime) -> datetime:
    return ensure_utc(dt).astimezone(get_settings().tz)


def studio_day_bounds_utc(d: date) -> tuple[datetime, datetime]:
    """UTC [start, end) of a studio-local calendar day."""
    tz = get_settings().tz
    start = datetime.combine(d, time.min, tzinfo=tz)
    end = datetime.combine(d, time.max, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def studio_eod(d: date) -> datetime:
    """Default end-of-day deadline for a studio date, as UTC."""
    s = get_settings()
    return datetime.combine(d, time(hour=s.eod_deadline_hour), tzinfo=s.tz).astimezone(timezone.utc)
