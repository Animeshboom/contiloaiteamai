"""Password hashing and JWT helpers."""
from datetime import timedelta

import bcrypt
import jwt

from app.core.config import get_settings
from app.core.timeutils import utcnow


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=get_settings().bcrypt_rounds)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, role: str, token_version: int) -> str:
    s = get_settings()
    now = utcnow()
    payload = {
        "sub": str(user_id),
        "role": role,  # informational only; the server always re-reads role from DB
        "tv": token_version,
        "iat": now,
        "exp": now + timedelta(minutes=s.access_token_expire_minutes),
        "type": "access",
    }
    return jwt.encode(payload, s.jwt_secret_key, algorithm=s.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    s = get_settings()
    return jwt.decode(token, s.jwt_secret_key, algorithms=[s.jwt_algorithm], options={"require": ["sub", "exp"]})
