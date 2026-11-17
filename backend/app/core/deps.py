"""FastAPI dependencies: DB session, current user, role guards.

Authorization is always evaluated against the database record, never the JWT's
role claim, so role changes and deactivations take effect immediately.
"""
from collections.abc import Callable

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import Forbidden, Unauthorized
from app.core.security import decode_access_token
from app.models import RoleName, User

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise Unauthorized("Not authenticated")
    try:
        payload = decode_access_token(creds.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise Unauthorized("Invalid or expired token")

    user = db.get(User, user_id)
    if not user or not user.is_active or user.deleted_at is not None:
        raise Unauthorized("Account is inactive")
    if payload.get("tv") != user.token_version:
        raise Unauthorized("Session has been revoked; please sign in again")
    return user


def require_roles(*roles: RoleName) -> Callable[..., User]:
    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role_name not in roles:
            raise Forbidden("You do not have permission to perform this action")
        return user

    return _guard


require_admin = require_roles(RoleName.ADMIN)
require_lead_or_admin = require_roles(RoleName.ADMIN, RoleName.TEAM_LEAD)
require_artist = require_roles(RoleName.ARTIST)


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
