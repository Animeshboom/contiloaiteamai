import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import Forbidden, Locked, Unauthorized, ValidationFailed
from app.core.rate_limit import login_throttle
from app.core.security import create_access_token, create_mfa_token, decode_mfa_token, hash_password, verify_password
from app.core.timeutils import utcnow
from app.models import RoleName, User
from app.services import audit, identity, security_service

# Constant-time-ish: verify against a dummy hash when the user doesn't exist,
# so response timing doesn't reveal which emails are registered.
_DUMMY_HASH = hash_password("not-a-real-password")


def authenticate(db: Session, email: str, password: str, ip: str | None,
                 user_agent: str | None = None) -> tuple[User, str | None, str | None]:
    """Local sign-in. ``email`` may also be an Employee ID (e.g. EMP001).

    Returns (user, access_token, mfa_token): an admin with two-step login turned on gets only an
    ``mfa_token`` and must finish with ``complete_mfa``. 5 wrong passwords lock the account for 15 minutes."""
    if get_settings().uses_supabase:
        raise ValidationFailed("Sign-in is handled by Supabase Auth")
    identifier = email.strip()
    email = identity.login_email(identifier)
    login_throttle.check(email)  # per-account backstop (in memory); the DB lockout below is the main one
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None and "@" not in identifier:  # an Employee ID
        user = db.scalar(select(User).where(func.upper(User.employee_code) == identifier.upper()))
    if user is None:
        verify_password(password, _DUMMY_HASH)
        login_throttle.record_failure(email)
        raise Unauthorized("Invalid email or password")
    locked = security_service.lock_message(user)
    if locked:
        raise Locked(locked)
    if not verify_password(password, user.password_hash):
        login_throttle.record_failure(email)
        audit.record(db, actor_id=user.id, action="auth.login_failed", entity_type="user", entity_id=user.id, ip=ip)
        security_service.record_failed_login(db, user)
        db.commit()
        locked = security_service.lock_message(user)
        if locked:
            raise Locked(locked)
        raise Unauthorized("Invalid email or password")
    login_throttle.reset(email)
    if not user.is_active or user.deleted_at is not None:
        raise Unauthorized("Account is inactive. Contact your administrator.")

    security_service.record_successful_login(user)
    if user.role_name == RoleName.ADMIN and user.totp_enabled:
        db.commit()
        return user, None, create_mfa_token(user.id, user.token_version)
    return user, _finish_login(db, user, ip, user_agent, aal="aal1"), None


def _finish_login(db: Session, user: User, ip: str | None, user_agent: str | None, aal: str) -> str:
    user.last_login_at = utcnow()
    if user.role_name == RoleName.ARTIST:
        user.token_version += 1  # one device: signing in here signs the artist out everywhere else
    security_service.check_device(db, user, ip, user_agent)
    audit.record(db, actor_id=user.id, action="auth.login", entity_type="user", entity_id=user.id, ip=ip)
    db.commit()
    return create_access_token(user.id, user.role_name.value, user.token_version, aal=aal)


def complete_mfa(db: Session, mfa_token: str, code: str, ip: str | None, user_agent: str | None) -> tuple[User, str]:
    """Second step of an admin sign-in: the 6-digit code from the authenticator app."""
    try:
        payload = decode_mfa_token(mfa_token)
    except jwt.PyJWTError:
        raise Unauthorized("The sign-in took too long. Start again.")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active or payload.get("tv") != user.token_version or not user.totp_enabled:
        raise Unauthorized("Start the sign-in again")
    locked = security_service.lock_message(user)
    if locked:
        raise Locked(locked)
    if not security_service.verify_totp(security_service.decrypt_secret(user.totp_secret), code):
        security_service.record_failed_login(db, user)
        audit.record(db, actor_id=user.id, action="auth.mfa_failed", entity_type="user", entity_id=user.id, ip=ip)
        db.commit()
        raise Unauthorized("Wrong code. Check the time on your phone and try again.")
    security_service.record_successful_login(user)
    return user, _finish_login(db, user, ip, user_agent, aal="aal2")


def start_mfa_setup(db: Session, user: User) -> dict:
    """Admin: create a new secret (not active until confirmed with a code)."""
    if get_settings().uses_supabase:
        raise ValidationFailed("With Supabase Auth, set up two-step login in the app's Supabase flow")
    secret = security_service.new_totp_secret()
    user.totp_secret = security_service.encrypt_secret(secret)
    user.totp_enabled = False
    db.commit()
    return {"secret": secret, "otpauth_uri": security_service.otpauth_uri(user, secret)}


def confirm_mfa_setup(db: Session, user: User, code: str, ip: str | None) -> str:
    """Admin: confirm with the first code; returns a fresh token that counts as two-step (aal2)."""
    if not user.totp_secret:
        raise ValidationFailed("Start the setup first")
    if not security_service.verify_totp(security_service.decrypt_secret(user.totp_secret), code):
        raise ValidationFailed("That code didn't match. Check the time on your phone and try again.")
    user.totp_enabled = True
    user.token_version += 1  # older (password-only) sessions end
    audit.record(db, actor_id=user.id, action="auth.mfa_enabled", entity_type="user", entity_id=user.id, ip=ip)
    db.commit()
    return create_access_token(user.id, user.role_name.value, user.token_version, aal="aal2")


def change_password(db: Session, user: User, current: str, new: str, ip: str | None) -> str | None:
    """Returns a fresh local token, or None with Supabase (the existing Supabase session stays valid)."""
    if user.role_name == RoleName.ARTIST:
        raise Forbidden("Ask your team lead or administrator to reset your password")
    if get_settings().uses_supabase:
        if not identity.password_is_correct(user.email, current):
            raise ValidationFailed("Current password is incorrect")
        identity.set_password(user, new)
        audit.record(db, actor_id=user.id, action="auth.password_changed", entity_type="user", entity_id=user.id,
                     ip=ip)
        db.commit()
        return None
    if not verify_password(current, user.password_hash):
        raise ValidationFailed("Current password is incorrect")
    user.password_hash = hash_password(new)
    user.token_version += 1  # revoke other sessions
    audit.record(db, actor_id=user.id, action="auth.password_changed", entity_type="user", entity_id=user.id, ip=ip)
    db.commit()
    return create_access_token(user.id, user.role_name.value, user.token_version)
