"""Password hashing, session tokens and brute-force damping.

Passwords are hashed with scrypt (memory-hard, in the standard library, no build
step on any platform) and compared in constant time.  Sessions are signed JWTs
carried in an httpOnly cookie, so page scripts cannot read them and EventSource
still authenticates -- which matters here, because the investigation stream is an
SSE connection and EventSource cannot send an Authorization header.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

import jwt

from app.config import settings

# scrypt parameters: ~16 MB and a few hundred ms per hash on a laptop.
_N, _R, _P, _DKLEN = 2 ** 14, 8, 1, 32
_ALGO = "HS256"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")
MIN_PASSWORD_LENGTH = 8
COMMON_PASSWORDS = {
    "password", "password1", "12345678", "123456789", "qwerty123", "letmein1",
    "iloveyou", "admin123", "welcome1", "abc12345", "passw0rd", "insightpilot",
}


class AuthError(ValueError):
    """Raised for anything a caller is allowed to see: bad input, bad credentials."""


# ------------------------------------------------------------------ passwords
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return f"scrypt${_N}${_R}${_P}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_hex, hash_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                            n=int(n), r=int(r), p=int(p), dklen=len(hash_hex) // 2)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), hash_hex)


def validate_credentials(email: str, password: str) -> tuple[str, str]:
    """Normalise and check sign-up input.  Returns (email, password)."""
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise AuthError("Enter a valid email address.")
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > 200:
        raise AuthError("Password is too long.")
    if password.lower() in COMMON_PASSWORDS:
        raise AuthError("That password is too common. Choose something less guessable.")
    if password.lower() == email.split("@")[0].lower():
        raise AuthError("Password must not be your email name.")
    return email, password


# --------------------------------------------------------------------- tokens
def _secret() -> str:
    return settings.jwt_secret or os.environ.get("JWT_SECRET") or settings.DEV_JWT_SECRET


def create_token(user_id: str, email: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id, "email": email, "role": role,
        "iat": now, "exp": now + timedelta(minutes=settings.session_minutes),
        "iss": "insightpilot",
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGO)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _secret(), algorithms=[_ALGO], issuer="insightpilot")
    except jwt.ExpiredSignatureError as e:
        raise AuthError("Session expired. Please sign in again.") from e
    except jwt.InvalidTokenError as e:
        raise AuthError("Invalid session.") from e


# ------------------------------------------------------- brute-force damping
_ATTEMPTS: dict[str, list[float]] = {}
_WINDOW_SECONDS = 300
_MAX_ATTEMPTS = 6


def record_failure(key: str) -> None:
    now = time.time()
    hits = [t for t in _ATTEMPTS.get(key, []) if now - t < _WINDOW_SECONDS]
    hits.append(now)
    _ATTEMPTS[key] = hits


def clear_failures(key: str) -> None:
    _ATTEMPTS.pop(key, None)


def seconds_locked_out(key: str) -> int:
    """0 when the caller may try again, otherwise how long to wait.

    In-process and per-worker: fine for a single-node POC, but a real deployment
    would keep this in Redis so it survives restarts and spans replicas.
    """
    now = time.time()
    hits = [t for t in _ATTEMPTS.get(key, []) if now - t < _WINDOW_SECONDS]
    _ATTEMPTS[key] = hits
    if len(hits) < _MAX_ATTEMPTS:
        return 0
    return int(_WINDOW_SECONDS - (now - hits[0])) + 1
