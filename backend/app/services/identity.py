"""Sign-in identities: local passwords or Supabase Auth (AUTH_PROVIDER).

With ``supabase``:
- The web app signs people in with supabase-js; this API only *verifies* the access token
  (JWKS for projects with signing keys, or SUPABASE_JWT_SECRET for legacy HS256 projects).
- Accounts are created here (admin screens, CSV import, bootstrap) through the Supabase Admin API
  using the secret service-role key, and linked by ``User.auth_user_id``.
- A Supabase user with no linked StudioTrack account is rejected, so public sign-ups grant nothing.

With ``local`` (tests, offline development) passwords are bcrypt hashes in our own database.
"""
import logging
import secrets
from functools import lru_cache

import httpx
import jwt

from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.core.security import hash_password

log = logging.getLogger("studiotrack.identity")

# Stored as password_hash for Supabase-managed accounts: never matches any bcrypt check.
EXTERNAL_PASSWORD = "!supabase"
_PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"  # no 0/O, 1/l/I


class IdentityError(Exception):
    pass


def generate_password(length: int = 12) -> str:
    return "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))


def id_email(code: str) -> str:
    """The login email for an account that signs in with an Employee ID."""
    return f"{code.strip().lower()}@{get_settings().login_id_email_domain}"


def login_email(identifier: str) -> str:
    """People sign in with an email, or with an Employee ID: 'EMP001' -> 'emp001@<login id domain>'."""
    identifier = identifier.strip()
    return identifier.lower() if "@" in identifier else id_email(identifier)


# ---------------- Supabase Admin API ----------------

def _admin_headers() -> dict:
    key = get_settings().supabase_service_role_key
    if not key:
        raise IdentityError("SUPABASE_SERVICE_ROLE_KEY is not set")
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def _auth_url(path: str) -> str:
    base = get_settings().supabase_url
    if not base:
        raise IdentityError("SUPABASE_URL is not set")
    return f"{base.rstrip('/')}/auth/v1{path}"


def _request(method: str, path: str, **kw) -> dict:
    try:
        r = httpx.request(method, _auth_url(path), headers=_admin_headers(), timeout=15, **kw)
    except httpx.HTTPError as e:
        raise IdentityError(f"Could not reach Supabase Auth: {e}") from e
    if r.status_code >= 400:
        try:
            body = r.json()
            msg = body.get("msg") or body.get("message") or body.get("error_description") or r.text
        except ValueError:
            msg = r.text
        raise IdentityError(f"Supabase Auth refused ({r.status_code}): {msg}")
    return r.json() if r.content else {}


def _find_supabase_user(email: str) -> str | None:
    page = 1
    while True:
        users = _request("GET", "/admin/users", params={"page": page, "per_page": 1000}).get("users", [])
        for u in users:
            if (u.get("email") or "").lower() == email.lower():
                return u["id"]
        if len(users) < 1000:
            return None
        page += 1


def create_login(email: str, password: str, *, link_existing: bool = False) -> tuple[str, str | None]:
    """Returns (password_hash, auth_user_id) for a new account."""
    if not get_settings().uses_supabase:
        return hash_password(password), None
    try:
        user = _request("POST", "/admin/users", json={"email": email, "password": password, "email_confirm": True})
        return EXTERNAL_PASSWORD, user["id"]
    except IdentityError as e:
        if link_existing and "already" in str(e).lower():
            existing = _find_supabase_user(email)
            if existing:
                _request("PUT", f"/admin/users/{existing}", json={"password": password})
                return EXTERNAL_PASSWORD, existing
        raise ValidationFailed(f"Could not create the login: {e}") from e


def set_password(user, password: str) -> None:
    if not get_settings().uses_supabase:
        user.password_hash = hash_password(password)
        return
    if not user.auth_user_id:
        raise ValidationFailed("This account is not linked to Supabase Auth")
    try:
        _request("PUT", f"/admin/users/{user.auth_user_id}", json={"password": password})
    except IdentityError as e:
        raise ValidationFailed(f"Could not change the password: {e}") from e


def set_login_enabled(user, enabled: bool) -> None:
    """Deactivated accounts are refused by this API anyway; banning also stops new Supabase sessions."""
    if not get_settings().uses_supabase or not user.auth_user_id:
        return
    try:
        _request("PUT", f"/admin/users/{user.auth_user_id}",
                 json={"ban_duration": "none" if enabled else "876000h"})
    except IdentityError:
        log.exception("could not %s Supabase login for user %s", "unban" if enabled else "ban", user.id)


def password_is_correct(email: str, password: str) -> bool:
    """Supabase mode: check a password by attempting a sign-in (used before a password change)."""
    s = get_settings()
    try:
        r = httpx.post(_auth_url("/token"), params={"grant_type": "password"},
                       headers={"apikey": s.supabase_publishable_key or ""},
                       json={"email": email, "password": password}, timeout=15)
    except httpx.HTTPError as e:
        raise ValidationFailed(f"Could not reach Supabase Auth: {e}") from e
    return r.status_code == 200


# ---------------- token verification ----------------

@lru_cache
def _jwks_client(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{url.rstrip('/')}/auth/v1/.well-known/jwks.json", cache_keys=True, lifespan=3600)


def verify_supabase_token(token: str) -> dict:
    """Validate a Supabase access token and return its claims. Raises jwt.PyJWTError."""
    s = get_settings()
    opts = {"require": ["sub", "exp"]}
    if s.supabase_jwt_secret:
        return jwt.decode(token, s.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated", options=opts)
    if not s.supabase_url:
        raise jwt.InvalidTokenError("SUPABASE_URL is not set")
    key = _jwks_client(s.supabase_url).get_signing_key_from_jwt(token)
    return jwt.decode(token, key.key, algorithms=["ES256", "RS256", "EdDSA"], audience="authenticated",
                      issuer=f"{s.supabase_url.rstrip('/')}/auth/v1", options=opts)


def set_email(user, email: str) -> None:
    """Change the sign-in email (Supabase mode updates the Auth user too; the password is unchanged)."""
    if get_settings().uses_supabase and user.auth_user_id:
        try:
            _request("PUT", f"/admin/users/{user.auth_user_id}", json={"email": email, "email_confirm": True})
        except IdentityError as e:
            raise ValidationFailed(f"Could not change the sign-in email: {e}") from e
    user.email = email
