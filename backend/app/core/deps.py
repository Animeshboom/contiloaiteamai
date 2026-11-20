"""FastAPI dependencies: DB session, current user, role guards.

Authorization is always evaluated against the database record, never the JWT's
role claim, so role changes and deactivations take effect immediately.
"""
from collections.abc import Callable

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_access_token
from app.models import RoleName, User
from app.services import identity

bearer = HTTPBearer(auto_error=False)


def signed_in_at(claims: dict) -> int:
    """When this Supabase session was created by a sign-in (the ``amr`` timestamps survive refreshes)."""
    stamps = [a.get("timestamp", 0) for a in claims.get("amr") or [] if isinstance(a, dict)]
    return int(max(stamps, default=0))


def claim_artist_session(db: Session, user: User, claims: dict) -> None:
    """One device per artist: the most recent sign-in owns the session; older ones are refused."""
    sid, at = claims.get("session_id"), signed_in_at(claims)
    if not sid:
        return
    if user.active_session_id is None or (sid != user.active_session_id and at >= (user.active_session_at or 0)):
        user.active_session_id, user.active_session_at = sid, at
        db.commit()


def _user_from_token(token: str, db: Session) -> User:
    if get_settings().uses_supabase:
        try:
            claims = identity.verify_supabase_token(token)
        except jwt.PyJWTError:
            raise Unauthorized("Invalid or expired token")
        user = db.scalar(select(User).where(User.auth_user_id == claims["sub"]))
        if user is None:
            raise Unauthorized("No StudioTrack account is linked to this sign-in. Ask your administrator.")
        aal = claims.get("aal", "aal1")
        if user.role_name == RoleName.ARTIST and user.is_active:
            claim_artist_session(db, user, claims)  # a newer sign-in always takes over
            if claims.get("session_id") and claims.get("session_id") != user.active_session_id:
                raise Unauthorized("You signed in on another device. Sign in again to use this one.")
    else:
        try:
            payload = decode_access_token(token)
            user_id = int(payload["sub"])
        except (jwt.PyJWTError, KeyError, ValueError):
            raise Unauthorized("Invalid or expired token")
        user = db.get(User, user_id)
        if user is not None and payload.get("tv") != user.token_version:
            raise Unauthorized("Session has been revoked; please sign in again")
        aal = payload.get("aal", "aal1")
    if not user or not user.is_active or user.deleted_at is not None:
        raise Unauthorized("Account is inactive")
    user.token_aal = aal  # not a column: how this request's token was obtained
    return user


def get_any_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """Any signed-in, active account."""
    if creds is None or creds.scheme.lower() != "bearer":
        raise Unauthorized("Not authenticated")
    return _user_from_token(creds.credentials, db)


def get_user_claiming_session(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    """Explicit hand-over after a Supabase sign-in (every request already lets the newest sign-in win)."""
    if creds is None or creds.scheme.lower() != "bearer":
        raise Unauthorized("Not authenticated")
    return _user_from_token(creds.credentials, db)


def get_current_user(user: User = Depends(get_any_user)) -> User:
    """Every normal route. Admins must have signed in with their two-step code (ADMIN_MFA_REQUIRED);
    only /auth/me, the two-step setup routes, notifications and /meta/config work without it."""
    if (user.role_name == RoleName.ADMIN and get_settings().admin_mfa_required
            and getattr(user, "token_aal", "aal1") != "aal2"):
        raise Forbidden("Two-step login is required for the admin account", code="mfa_required")
    return user


def require_roles(*roles: RoleName) -> Callable[..., User]:
    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role_name not in roles:
            raise Forbidden("You do not have permission to perform this action")
        return user

    return _guard


require_admin = require_roles(RoleName.ADMIN)


def require_admin_any_aal(user: User = Depends(get_any_user)) -> User:
    """Admin routes that must work before two-step login is set up (the setup itself)."""
    if user.role_name != RoleName.ADMIN:
        raise Forbidden("You do not have permission to perform this action")
    return user
require_lead_or_admin = require_roles(RoleName.ADMIN, RoleName.TEAM_LEAD)
require_artist = require_roles(RoleName.ARTIST)


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


