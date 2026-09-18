"""Authentication: storage, session handling and the guard on the analytics API."""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.main import app
from app.auth.models import users
from app.auth.security import hash_password, verify_password
from app.db.session import rw_engine

PASSWORD = "correct-horse-battery-2026"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:      # lifespan startup creates the users table
        yield c
    # Keep the dev database tidy: remove only the accounts these tests created.
    from sqlalchemy import delete
    with rw_engine().begin() as conn:
        conn.execute(delete(users).where(users.c.email.like("user-%@example.com")))
        conn.execute(delete(users).where(users.c.email.in_(
            ["short@example.com", "common@example.com", "not-an-email"])))


def fresh_email() -> str:
    return f"user-{uuid.uuid4().hex[:10]}@example.com"


# ------------------------------------------------------------------ hashing
def test_password_hash_is_salted_and_verifiable():
    a, b = hash_password(PASSWORD), hash_password(PASSWORD)
    assert a != b, "identical hashes mean the salt is not random"
    assert a.startswith("scrypt$")
    assert PASSWORD not in a
    assert verify_password(PASSWORD, a)
    assert not verify_password("wrong-password", a)
    assert not verify_password(PASSWORD, "not-a-hash")


def test_stored_password_is_never_plaintext(client):
    email = fresh_email()
    client.post("/api/auth/signup", json={"email": email, "password": PASSWORD,
                                          "full_name": "Hash Check"})
    with rw_engine().connect() as c:
        row = c.execute(select(users).where(users.c.email == email)).one()
    assert PASSWORD not in row.password_hash
    assert verify_password(PASSWORD, row.password_hash)


# ------------------------------------------------------------------- signup
def test_signup_creates_account_and_session(client):
    email = fresh_email()
    r = client.post("/api/auth/signup", json={"email": email.upper(), "password": PASSWORD,
                                              "full_name": "  Ada Lovelace  ", "company": "Acme"})
    assert r.status_code == 201
    user = r.json()["user"]
    assert user["email"] == email          # normalised to lower case
    assert user["full_name"] == "Ada Lovelace"
    assert "password" not in str(user) and "password_hash" not in user
    assert client.cookies.get("insightpilot_session")
    client.cookies.clear()


@pytest.mark.parametrize("payload,fragment", [
    ({"email": "not-an-email", "password": PASSWORD}, "valid email"),
    ({"email": "short@example.com", "password": "abc123"}, "at least 8"),
    ({"email": "common@example.com", "password": "password"}, "too common"),
])
def test_signup_rejects_bad_input(client, payload, fragment):
    r = client.post("/api/auth/signup", json=payload)
    assert r.status_code == 400
    assert fragment in r.json()["detail"]


def test_duplicate_email_is_rejected(client):
    email = fresh_email()
    body = {"email": email, "password": PASSWORD, "full_name": "First"}
    assert client.post("/api/auth/signup", json=body).status_code == 201
    r = client.post("/api/auth/signup", json=body)
    assert r.status_code == 400 and "already exists" in r.json()["detail"]
    client.cookies.clear()


# -------------------------------------------------------------------- login
def test_login_and_me(client):
    email = fresh_email()
    client.post("/api/auth/signup", json={"email": email, "password": PASSWORD, "full_name": "Log In"})
    client.cookies.clear()

    assert client.post("/api/auth/login",
                       json={"email": email, "password": "not-the-password"}).status_code == 401

    r = client.post("/api/auth/login", json={"email": email.upper(), "password": PASSWORD})
    assert r.status_code == 200
    assert client.get("/api/auth/me").json()["user"]["email"] == email
    client.cookies.clear()


def test_repeated_failures_are_rate_limited(client):
    email = fresh_email()
    client.post("/api/auth/signup", json={"email": email, "password": PASSWORD, "full_name": "Locked"})
    client.cookies.clear()
    codes = [client.post("/api/auth/login", json={"email": email, "password": "nope"}).status_code
             for _ in range(8)]
    assert 429 in codes, f"expected a lockout, got {codes}"


def test_demo_account_needs_no_password(client):
    r = client.post("/api/auth/demo")
    assert r.status_code == 200
    assert r.json()["user"]["is_demo"] is True
    assert client.get("/api/auth/me").status_code == 200
    client.cookies.clear()


def test_logout_ends_the_session(client):
    client.post("/api/auth/demo")
    assert client.get("/api/auth/me").status_code == 200
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/auth/me").status_code == 401


# ------------------------------------------------------------------- guards
PROTECTED = [("get", "/api/meta"), ("get", "/api/dashboard"), ("get", "/api/policies"),
             ("post", "/api/sql"), ("post", "/api/investigate")]


@pytest.mark.parametrize("method,path", PROTECTED)
def test_analytics_routes_require_a_session(client, method, path):
    client.cookies.clear()
    call = getattr(client, method)
    r = (call(path, json={"sql": "SELECT 1 FROM sales", "question": "why did revenue fall?"})
         if method == "post" else call(path))
    assert r.status_code == 401


def test_health_stays_public(client):
    client.cookies.clear()
    assert client.get("/api/health").status_code == 200


def test_signed_in_user_can_reach_the_analytics_api(client):
    client.post("/api/auth/demo")
    assert client.get("/api/meta").status_code == 200
    assert client.get("/api/dashboard").status_code == 200
    client.cookies.clear()


def test_tampered_token_is_rejected(client):
    client.post("/api/auth/demo")
    token = client.cookies.get("insightpilot_session")
    client.cookies.clear()
    forged = token[:-4] + ("aaaa" if not token.endswith("aaaa") else "bbbb")
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401


def test_bearer_token_works_for_scripted_clients(client):
    r = client.post("/api/auth/demo")
    token = r.cookies.get("insightpilot_session") or client.cookies.get("insightpilot_session")
    client.cookies.clear()
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
