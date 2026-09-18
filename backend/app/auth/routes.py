"""Authentication endpoints: /api/auth/*"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from app.auth import service
from app.auth.security import AuthError
from app.config import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)
    full_name: str = Field(default="", max_length=120)
    company: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=200)


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.cookie_name, token,
        max_age=settings.session_minutes * 60,
        httponly=True,          # not readable from page scripts
        samesite=settings.cookie_samesite,
        secure=settings.cookie_secure,   # set true behind HTTPS
        path="/",
    )


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, response: Response):
    try:
        user = service.create_user(body.email, body.password, body.full_name, body.company)
    except AuthError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e)) from e
    _set_cookie(response, service.issue_token(user))
    return {"user": user}


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response):
    try:
        user = service.authenticate(body.email, body.password, _client_key(request))
    except AuthError as e:
        # 429 for the lockout so the UI can say "wait", 401 for bad credentials.
        code = (status.HTTP_429_TOO_MANY_REQUESTS if "Too many" in str(e)
                else status.HTTP_401_UNAUTHORIZED)
        raise HTTPException(code, str(e)) from e
    _set_cookie(response, service.issue_token(user))
    return {"user": user}


@router.post("/demo")
def demo_login(response: Response):
    """One-click sign-in to the read-only demo account, so a live walkthrough
    never involves typing a password."""
    user = service.ensure_demo_account()
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The demo account is disabled.")
    _set_cookie(response, service.issue_token(user))
    return {"user": user}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(settings.cookie_name, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(service.current_user)):
    return {"user": user}
