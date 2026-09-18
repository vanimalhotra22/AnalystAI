"""Account storage and the FastAPI dependency that guards the analytics API."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import insert, select, update

from app.auth.models import auth_metadata, users
from app.auth.security import (
    AuthError, clear_failures, create_token, decode_token, hash_password,
    record_failure, seconds_locked_out, validate_credentials, verify_password,
)
from app.config import settings
from app.db.session import rw_engine

PUBLIC_FIELDS = ("user_id", "email", "full_name", "company", "role", "created_at",
                 "last_login_at", "is_demo")


def init_auth_storage() -> None:
    """Create the users table if it is missing.  Safe to call on every startup."""
    auth_metadata.create_all(rw_engine())


def _public(row) -> dict:
    d = dict(row._mapping)
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in d.items() if k in PUBLIC_FIELDS}


def get_user_by_email(email: str):
    with rw_engine().connect() as c:
        return c.execute(select(users).where(users.c.email == email.strip().lower())).first()


def get_user_by_id(user_id: str):
    with rw_engine().connect() as c:
        return c.execute(select(users).where(users.c.user_id == user_id)).first()


def create_user(email: str, password: str, full_name: str, company: str | None = None,
                role: str = "analyst", is_demo: bool = False) -> dict:
    email, password = validate_credentials(email, password)
    full_name = (full_name or "").strip() or email.split("@")[0]
    if len(full_name) > 120:
        raise AuthError("Name is too long.")
    if get_user_by_email(email):
        # Sign-up is the one place we do reveal that an address is taken -- the
        # alternative (silent success) is worse UX and users can discover it
        # anyway by attempting a password reset.
        raise AuthError("An account with that email already exists. Sign in instead.")

    row = {
        "user_id": uuid.uuid4().hex, "email": email, "full_name": full_name,
        "company": (company or "").strip()[:120] or None, "role": role,
        "password_hash": hash_password(password),
        "created_at": datetime.now(timezone.utc), "last_login_at": None,
        "is_demo": is_demo,
    }
    with rw_engine().begin() as c:
        c.execute(insert(users), row)
    return {k: (v.isoformat() if hasattr(v, "isoformat") else v)
            for k, v in row.items() if k in PUBLIC_FIELDS}


def authenticate(email: str, password: str, client_key: str = "") -> dict:
    email = (email or "").strip().lower()
    lock_key = f"{client_key}|{email}"
    wait = seconds_locked_out(lock_key)
    if wait:
        raise AuthError(f"Too many failed attempts. Try again in {wait} seconds.")

    row = get_user_by_email(email)
    # Always run a verification so a missing account and a wrong password take a
    # similar amount of time.
    stored = row.password_hash if row else hash_password("timing-equaliser")
    if not row or not verify_password(password or "", stored):
        record_failure(lock_key)
        raise AuthError("Email or password is incorrect.")

    clear_failures(lock_key)
    with rw_engine().begin() as c:
        c.execute(update(users).where(users.c.user_id == row.user_id)
                  .values(last_login_at=datetime.now(timezone.utc)))
    return _public(row)


def ensure_demo_account() -> dict | None:
    """The demo account exists so an interview walkthrough never has to type a
    password on stage.  Disable it with DEMO_ACCOUNT_ENABLED=false."""
    if not settings.demo_account_enabled:
        return None
    row = get_user_by_email(settings.demo_email)
    if row:
        return _public(row)
    return create_user(settings.demo_email, settings.demo_password,
                       "Demo Analyst", "SmartHealth Consumer Analytics",
                       role="demo", is_demo=True)


def issue_token(user: dict) -> str:
    return create_token(user["user_id"], user["email"], user.get("role", "analyst"))


# ---------------------------------------------------------------- dependency
def _token_from(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(settings.cookie_name)


def current_user(request: Request) -> dict:
    """Guards every analytics route.  Cookie for the browser (including SSE),
    bearer token for scripted clients."""
    token = _token_from(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in.")
    try:
        claims = decode_token(token)
    except AuthError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e)) from e
    row = get_user_by_id(claims.get("sub", ""))
    if not row:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account no longer exists.")
    return _public(row)


CurrentUser = Depends(current_user)
