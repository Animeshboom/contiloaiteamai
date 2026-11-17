from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Unauthorized, ValidationFailed
from app.core.security import create_access_token, hash_password, verify_password
from app.core.timeutils import utcnow
from app.models import User
from app.services import audit

# Constant-time-ish: verify against a dummy hash when the user doesn't exist,
# so response timing doesn't reveal which emails are registered.
_DUMMY_HASH = hash_password("not-a-real-password")


def authenticate(db: Session, email: str, password: str, ip: str | None) -> tuple[User, str]:
    user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    if user is None:
        verify_password(password, _DUMMY_HASH)
        raise Unauthorized("Invalid email or password")
    if not verify_password(password, user.password_hash):
        audit.record(db, actor_id=user.id, action="auth.login_failed", entity_type="user", entity_id=user.id, ip=ip)
        db.commit()
        raise Unauthorized("Invalid email or password")
    if not user.is_active or user.deleted_at is not None:
        raise Unauthorized("Account is inactive. Contact your administrator.")

    user.last_login_at = utcnow()
    audit.record(db, actor_id=user.id, action="auth.login", entity_type="user", entity_id=user.id, ip=ip)
    db.commit()
    token = create_access_token(user.id, user.role_name.value, user.token_version)
    return user, token


def change_password(db: Session, user: User, current: str, new: str, ip: str | None) -> str:
    if not verify_password(current, user.password_hash):
        raise ValidationFailed("Current password is incorrect")
    user.password_hash = hash_password(new)
    user.token_version += 1  # revoke other sessions
    audit.record(db, actor_id=user.id, action="auth.password_changed", entity_type="user", entity_id=user.id, ip=ip)
    db.commit()
    return create_access_token(user.id, user.role_name.value, user.token_version)
