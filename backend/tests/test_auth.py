"""Offline checks for sign-up, login, logout and sessions (in-memory SQLite, FastAPI TestClient; no network).

Run from backend/:  .venv/Scripts/python.exe tests/test_auth.py
"""
import os
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database or model hub.
os.environ.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:1/offline")
os.environ["HF_HUB_OFFLINE"] = "1"
warnings.filterwarnings("ignore", category=DeprecationWarning)

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.db import Base, get_db
from app.models import AuthSession, User
from app.routes import auth as auth_routes
from app.services import auth_service as auth

PASSWORD = "correct horse battery"


def make_client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk_on(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    Local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def db_override():
        db = Local()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(auth_routes.router)
    app.dependency_overrides[get_db] = db_override
    return TestClient(app), Local


def test_passwords_are_hashed_and_checked():
    h = auth.hash_password(PASSWORD)
    assert h.startswith("$2b$") and PASSWORD not in h
    assert auth.verify_password(PASSWORD, h) and not auth.verify_password("wrong password", h)
    assert not auth.verify_password(PASSWORD, None), "unknown user"
    assert not auth.verify_password("x" * 80, h), "over 72 bytes never matches"


def test_signup_logs_in_with_an_httponly_cookie():
    client, Local = make_client()
    r = client.post("/api/v1/auth/signup", json={"email": "  Me@Example.COM ", "password": PASSWORD})
    assert r.status_code == 201, r.text
    assert r.json()["user"]["email"] == "me@example.com", "email is trimmed and lowercased"
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{auth.SESSION_COOKIE}=") and "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    assert "Max-Age=2592000" in cookie and "Secure" not in cookie
    assert client.get("/api/v1/auth/me").json()["user"]["email"] == "me@example.com"
    db = Local()
    stored = db.query(AuthSession).one()
    token = r.json()["token"]
    assert stored.token_hash != token and len(stored.token_hash) == 64, "only the token's hash is stored"
    assert db.query(User).one().password_hash.startswith("$2b$")


def test_signup_checks():
    client, _ = make_client()
    cases = [
        ({"email": "not-an-email", "password": PASSWORD}, 400, "valid email"),
        ({"email": "a@b.co", "password": "short"}, 400, "at least 8"),
        ({"email": "a@b.co", "password": "é" * 40}, 400, "too long"),  # 80 bytes
    ]
    for body, status, text in cases:
        r = client.post("/api/v1/auth/signup", json=body)
        assert r.status_code == status and text in r.json()["detail"], (body, r.status_code, r.text)
    assert client.post("/api/v1/auth/signup", json={"email": "a@b.co", "password": PASSWORD}).status_code == 201
    r = client.post("/api/v1/auth/signup", json={"email": "A@B.CO", "password": PASSWORD})
    assert r.status_code == 409 and "already exists" in r.json()["detail"]


def test_login_logout_and_generic_errors():
    client, _ = make_client()
    client.post("/api/v1/auth/signup", json={"email": "me@example.com", "password": PASSWORD})
    client.cookies.clear()
    assert client.get("/api/v1/auth/me").status_code == 401
    wrong = client.post("/api/v1/auth/login", json={"email": "me@example.com", "password": "wrong password"})
    unknown = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"] == "Email or password is incorrect."
    r = client.post("/api/v1/auth/login", json={"email": "ME@example.com ", "password": PASSWORD})
    assert r.status_code == 200 and client.get("/api/v1/auth/me").status_code == 200
    out = client.post("/api/v1/auth/logout")
    assert out.status_code == 200 and f"{auth.SESSION_COOKIE}=" in out.headers["set-cookie"]
    assert client.get("/api/v1/auth/me").status_code == 401, "logged out"
    # The old token is dead on the server too, not just forgotten by the browser.
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['token']}"}).status_code == 401


def test_bearer_token_works_for_scripts():
    client, _ = make_client()
    token = client.post("/api/v1/auth/signup", json={"email": "bot@example.com", "password": PASSWORD}).json()["token"]
    client.cookies.clear()
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["user"]["email"] == "bot@example.com"
    assert client.get("/api/v1/auth/me", headers={"Authorization": "Bearer made-up"}).status_code == 401


def test_expired_sessions_are_refused_and_removed():
    client, Local = make_client()
    client.post("/api/v1/auth/signup", json={"email": "me@example.com", "password": PASSWORD})
    db = Local()
    db.query(AuthSession).update({AuthSession.expires_at: datetime.utcnow() - timedelta(seconds=1)})
    db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401
    assert Local().query(AuthSession).count() == 0


def test_two_sessions_are_independent():
    client, Local = make_client()
    client.post("/api/v1/auth/signup", json={"email": "me@example.com", "password": PASSWORD})
    other, _ = TestClient(client.app), None
    t2 = other.post("/api/v1/auth/login", json={"email": "me@example.com", "password": PASSWORD}).json()["token"]
    client.post("/api/v1/auth/logout")
    assert other.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {t2}"}).status_code == 200, "logging out one device keeps the other"


def test_signup_can_be_closed():
    client, _ = make_client()
    client.post("/api/v1/auth/signup", json={"email": "owner@example.com", "password": PASSWORD})
    os.environ["ALLOW_SIGNUP"] = "false"
    try:
        r = client.post("/api/v1/auth/signup", json={"email": "new@example.com", "password": PASSWORD})
        assert r.status_code == 403 and "closed" in r.json()["detail"]
        assert client.post("/api/v1/auth/login", json={"email": "owner@example.com", "password": PASSWORD}).status_code == 200
        assert client.get("/api/v1/auth/me").json()["signup_allowed"] is False
    finally:
        del os.environ["ALLOW_SIGNUP"]


def test_secure_cookie_flag():
    client, _ = make_client()
    os.environ["SESSION_COOKIE_SECURE"] = "true"
    try:
        r = client.post("/api/v1/auth/signup", json={"email": "me@example.com", "password": PASSWORD})
        assert "Secure" in r.headers["set-cookie"]
    finally:
        del os.environ["SESSION_COOKIE_SECURE"]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
