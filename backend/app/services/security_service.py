"""Account protection: lockout after wrong passwords, admin two-step login (TOTP), and admin alerts
(account locked, admin sign-in from a new device, bulk account changes)."""
import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import timedelta
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.core.timeutils import ensure_utc, utcnow
from app.models import AuditLog, KnownDevice, Role, RoleName, User
from app.services import notification_service

BULK_THRESHOLD = 5  # this many account imports / password resets by one person within an hour triggers an alert


def _admin_ids(db: Session) -> list[int]:
    return list(db.scalars(select(User.id).join(Role).where(
        Role.name == RoleName.ADMIN, User.is_active.is_(True), User.deleted_at.is_(None))))


def alert_admins(db: Session, *, title: str, message: str, dedupe_key: str, link: str | None = "/admin/activity") -> None:
    for admin_id in _admin_ids(db):
        notification_service.notify(db, user_id=admin_id, event_type="security_alert", title=title, message=message,
                                    link=link, dedupe_key=f"{dedupe_key}:{admin_id}")


# ---------------- lockout ----------------

def lock_message(user: User) -> str | None:
    """Why this account cannot sign in right now, or None."""
    if user.locked_until and ensure_utc(user.locked_until) > utcnow():
        minutes = max(1, int((ensure_utc(user.locked_until) - utcnow()).total_seconds() // 60) + 1)
        return f"Too many wrong passwords. Try again in {minutes} minute(s) or ask your administrator."
    return None


def record_failed_login(db: Session, user: User) -> None:
    s = get_settings()
    user.failed_logins = (user.failed_logins or 0) + 1
    if user.failed_logins >= s.login_max_attempts:
        user.failed_logins = 0
        user.locked_until = utcnow() + timedelta(minutes=s.login_lock_minutes)
        alert_admins(db, title=f"Account locked: {user.full_name}",
                     message=f"{s.login_max_attempts} wrong passwords in a row; locked for {s.login_lock_minutes} minutes.",
                     dedupe_key=f"locked:{user.id}:{int(user.locked_until.timestamp())}")


def record_successful_login(user: User) -> None:
    user.failed_logins = 0
    user.locked_until = None


def unlock(user: User) -> None:
    user.failed_logins = 0
    user.locked_until = None


# ---------------- admin sign-in from a new device ----------------

def check_device(db: Session, user: User, ip: str | None, user_agent: str | None) -> None:
    """Admins: remember each browser + network; alert the admins the first time a new one signs in."""
    if user.role_name != RoleName.ADMIN:
        return
    agent = (user_agent or "unknown")[:300]
    network = ".".join((ip or "").split(".")[:3]) or (ip or "unknown")  # same /24 network counts as the same place
    fingerprint = hashlib.sha256(f"{agent}|{network}".encode()).hexdigest()
    if db.scalar(select(KnownDevice.id).where(KnownDevice.user_id == user.id, KnownDevice.fingerprint == fingerprint)):
        return
    first_ever = not db.scalar(select(func.count(KnownDevice.id)).where(KnownDevice.user_id == user.id))
    db.add(KnownDevice(user_id=user.id, fingerprint=fingerprint, user_agent=agent, ip=ip))
    if not first_ever:
        alert_admins(db, title=f"New sign-in to admin account: {user.full_name}",
                     message=f"From {ip or 'unknown address'} · {agent[:120]}. If this wasn't them, reset the password.",
                     dedupe_key=f"device:{user.id}:{fingerprint[:16]}")


# ---------------- bulk changes ----------------

def check_bulk(db: Session, actor: User, action: str, count: int = 1) -> None:
    """Alert when one person creates or resets many accounts within an hour."""
    since = utcnow() - timedelta(hours=1)
    recent = db.scalar(select(func.count(AuditLog.id)).where(
        AuditLog.actor_id == actor.id, AuditLog.action == action, AuditLog.created_at >= since)) or 0
    total = max(recent, count)
    if total >= BULK_THRESHOLD:
        what = {"user.create": "created", "user.password_reset": "reset passwords for"}.get(action, action)
        alert_admins(db, title=f"Bulk change by {actor.full_name}",
                     message=f"{actor.full_name} {what} {total} accounts in the last hour.",
                     dedupe_key=f"bulk:{actor.id}:{action}:{utcnow():%Y%m%d%H}")


# ---------------- two-step login (TOTP, RFC 6238) ----------------

def _fernet() -> Fernet:
    key = hashlib.sha256(("totp:" + get_settings().jwt_secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def new_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValidationFailed("Two-step login must be set up again (the server key changed)") from e


def totp_code(secret: str, at: float | None = None, step: int = 30) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    counter = int((at if at is not None else time.time()) // step)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def verify_totp(secret: str, code: str) -> bool:
    code = (code or "").strip().replace(" ", "")
    if len(code) != 6 or not code.isdigit():
        return False
    now = time.time()
    return any(hmac.compare_digest(totp_code(secret, now + drift), code) for drift in (-30, 0, 30))


def otpauth_uri(user: User, secret: str) -> str:
    issuer = get_settings().app_name
    return (f"otpauth://totp/{quote(issuer)}:{quote(user.email)}?secret={secret}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits=6&period=30")
