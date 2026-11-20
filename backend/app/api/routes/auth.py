from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import client_ip, get_any_user, get_user_claiming_session, require_admin_any_aal
from app.core.rate_limit import limiter
from app.models import User
from app.schemas.auth import ChangePasswordRequest, LoginRequest, MfaCode, MfaLogin, TokenResponse, UserOut
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit(get_settings().login_rate_limit)
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    user, token, mfa_token = auth_service.authenticate(db, body.email, body.password, client_ip(request),
                                                       request.headers.get("user-agent"))
    return TokenResponse(
        access_token=token, mfa_required=mfa_token is not None, mfa_token=mfa_token,
        expires_in=get_settings().access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/login/mfa", response_model=TokenResponse)
@limiter.limit(get_settings().login_rate_limit)
def login_mfa(request: Request, body: MfaLogin, db: Session = Depends(get_db)):
    """Second step for admins with two-step login: the 6-digit code from the authenticator app."""
    user, token = auth_service.complete_mfa(db, body.mfa_token, body.code, client_ip(request),
                                            request.headers.get("user-agent"))
    return TokenResponse(access_token=token, expires_in=get_settings().access_token_expire_minutes * 60,
                         user=UserOut.model_validate(user))


@router.post("/mfa/setup")
def mfa_setup(user: User = Depends(require_admin_any_aal), db: Session = Depends(get_db)):
    """Admin: start two-step login setup. Scan the otpauth link (as a QR code) in an authenticator app."""
    return auth_service.start_mfa_setup(db, user)


@router.post("/mfa/enable", response_model=TokenResponse)
def mfa_enable(request: Request, body: MfaCode, user: User = Depends(require_admin_any_aal),
               db: Session = Depends(get_db)):
    """Admin: confirm setup with the first code. Returns a new token (older sessions end)."""
    token = auth_service.confirm_mfa_setup(db, user, body.code, client_ip(request))
    return TokenResponse(access_token=token, expires_in=get_settings().access_token_expire_minutes * 60,
                         user=UserOut.model_validate(user))


@router.post("/session", response_model=UserOut)
def start_session(request: Request, user: User = Depends(get_user_claiming_session),
                  db: Session = Depends(get_db)):
    """Called by the web app right after a Supabase sign-in. For artists this makes this device the
    only signed-in one (older devices get 401 on their next request). Admins: a new device raises an alert."""
    from app.services import security_service  # noqa: PLC0415
    security_service.check_device(db, user, client_ip(request), request.headers.get("user-agent"))
    db.commit()
    return user


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_any_user)):
    return user


@router.post("/change-password", response_model=TokenResponse)
@limiter.limit("5/minute")
def change_password(
    request: Request,
    body: ChangePasswordRequest,
    user: User = Depends(get_any_user),
    db: Session = Depends(get_db),
):
    token = auth_service.change_password(db, user, body.current_password, body.new_password, client_ip(request))
    return TokenResponse(
        access_token=token,
        expires_in=get_settings().access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )
