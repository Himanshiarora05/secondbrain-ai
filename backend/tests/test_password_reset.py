"""Offline checks for "forgot password" and the Brevo email service (in-memory SQLite, TestClient,
Brevo faked with an httpx mock transport; no network).

Run from backend/:  .venv/Scripts/python.exe tests/test_password_reset.py
"""
import json
import os
import re
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Never touch the real database, vector store, model hub or email account.
os.environ["DATABASE_URL"] = "postgresql://offline:offline@127.0.0.1:1/offline"
os.environ["HF_HUB_OFFLINE"] = "1"
for key in ("BREVO_API_KEY", "EMAIL_FROM", "EMAIL_FROM_NAME", "APP_BASE_URL", "PASSWORD_RESET_MINUTES"):
    os.environ.pop(key, None)
warnings.filterwarnings("ignore", category=DeprecationWarning)

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.db import Base, get_db
from app.models import AuthSession, PasswordResetToken
from app.routes import auth as auth_routes
from app.services import email_service, password_reset

PASSWORD = "original password 1"
NEW_PASSWORD = "brand new password 2"
REPLY = "If an account exists for that email, we've sent a link to reset its password. It expires in 30 minutes."


def setup():
    """A client with one account (me@example.com), and a list collecting the emails that would be sent."""
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
    client = TestClient(app)
    assert client.post("/api/v1/auth/signup", json={"email": "me@example.com", "password": PASSWORD}).status_code == 201
    sent = []
    patch.object(password_reset, "send_email", side_effect=lambda to, subject, text, html=None: sent.append(
        {"to": to, "subject": subject, "text": text, "html": html}) or True).start()
    return client, Local, sent


def token_from(mail):
    return re.search(r"/reset-password\?token=([A-Za-z0-9_\-]+)", mail["text"]).group(1)


def ask(client, email="me@example.com"):
    return client.post("/api/v1/auth/password-reset/request", json={"email": email})


def test_known_and_unknown_emails_get_the_same_answer():
    client, _, sent = setup()
    known, unknown = ask(client, "  ME@example.com "), ask(client, "nobody@example.com")
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json() == {"message": REPLY}
    assert len(sent) == 1 and sent[0]["to"] == "me@example.com", "only the real account gets an email"
    assert ask(client, "not-an-email").status_code == 400


def test_the_email_has_a_working_link():
    client, Local, sent = setup()
    ask(client)
    mail = sent[0]
    assert mail["subject"] == "Reset your SecondBrain password"
    assert "http://localhost:5173/reset-password?token=" in mail["text"] and "30 minutes" in mail["text"]
    token = token_from(mail)
    assert f'href="http://localhost:5173/reset-password?token={token}"' in mail["html"]
    stored = Local().query(PasswordResetToken).one()
    assert stored.token_hash != token and len(stored.token_hash) == 64, "only the hash is stored"
    assert timedelta(minutes=29) < stored.expires_at - stored.created_at <= timedelta(minutes=30, seconds=1)
    assert client.post("/api/v1/auth/password-reset/check", json={"token": token}).json() == {"valid": True}
    assert client.post("/api/v1/auth/password-reset/check", json={"token": "made-up"}).json() == {"valid": False}


def test_reset_changes_the_password_and_ends_every_session():
    client, Local, sent = setup()
    other_device = TestClient(client.app)
    other_token = other_device.post("/api/v1/auth/login", json={"email": "me@example.com", "password": PASSWORD}).json()["token"]
    ask(client)
    token = token_from(sent[0])
    short = client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "password": "short"})
    assert short.status_code == 400 and "at least 8" in short.json()["detail"]
    ok = client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD})
    assert ok.status_code == 200 and ok.json()["message"].startswith("Password changed")
    assert Local().query(AuthSession).count() == 0, "every session ended"
    assert client.get("/api/v1/auth/me").status_code == 401
    assert other_device.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {other_token}"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "me@example.com", "password": PASSWORD}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "me@example.com", "password": NEW_PASSWORD}).status_code == 200


def test_a_link_works_once():
    client, _, sent = setup()
    ask(client)
    token = token_from(sent[0])
    assert client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "password": NEW_PASSWORD}).status_code == 200
    again = client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "password": "yet another pw 3"})
    assert again.status_code == 400 and again.json()["detail"] == password_reset.BAD_LINK
    assert client.post("/api/v1/auth/password-reset/check", json={"token": token}).json() == {"valid": False}


def test_expired_links_and_older_links_stop_working():
    client, Local, sent = setup()
    ask(client)
    first = token_from(sent[0])
    ask(client)
    second = token_from(sent[1])
    assert client.post("/api/v1/auth/password-reset/check", json={"token": first}).json() == {"valid": False}, "a newer link cancels the older one"
    db = Local()
    db.query(PasswordResetToken).update({PasswordResetToken.expires_at: datetime.utcnow() - timedelta(seconds=1)})
    db.commit()
    r = client.post("/api/v1/auth/password-reset/confirm", json={"token": second, "password": NEW_PASSWORD})
    assert r.status_code == 400 and r.json()["detail"] == password_reset.BAD_LINK
    assert client.post("/api/v1/auth/login", json={"email": "me@example.com", "password": PASSWORD}).status_code == 200


def test_at_most_three_emails_an_hour_with_the_same_answer():
    client, _, sent = setup()
    replies = [ask(client).json() for _ in range(5)]
    assert all(r == {"message": REPLY} for r in replies)
    assert len(sent) == 3, len(sent)


def test_reset_minutes_and_base_url_come_from_env():
    os.environ["PASSWORD_RESET_MINUTES"] = "15"
    os.environ["APP_BASE_URL"] = "https://brain.example.org/"
    try:
        mail = password_reset.reset_email("me@example.com", "TOKEN123")
        assert "https://brain.example.org/reset-password?token=TOKEN123" in mail["text"] and "15 minutes" in mail["text"]
        assert "https://brain.example.org//" not in mail["text"]
    finally:
        del os.environ["PASSWORD_RESET_MINUTES"], os.environ["APP_BASE_URL"]


def test_email_address_is_escaped_in_the_html():
    mail = password_reset.reset_email('a<b>"@example.com', "T")
    assert "<b>" not in mail["html"].replace("<b>a&lt;", "") and "a&lt;b&gt;&quot;@example.com" in mail["html"]


# ─── email_service (Brevo) ───

def brevo(status=201, body=None, error=None):
    calls = []

    def handler(request):
        calls.append(request)
        if error:
            raise error
        return httpx.Response(status, json=body if body is not None else {"messageId": "<1@relay>"})

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def test_without_a_key_the_email_is_logged_not_sent():
    client, calls = brevo()
    with patch.object(email_service, "logger") as log:
        assert email_service.send_email("me@example.com", "Hi", "Link: http://x/reset-password?token=abc", client=client) is True
    assert calls == [], "nothing sent"
    logged = str(log.warning.call_args)
    assert "NOT sent" in logged and "token=abc" in logged and "me@example.com" in logged


def test_brevo_request_shape():
    os.environ.update({"BREVO_API_KEY": "xkeysib-secret", "EMAIL_FROM": "sender@gmail.com"})
    try:
        client, calls = brevo()
        assert email_service.send_email("me@example.com", "Subject", "Text body", "<p>Html</p>", client=client) is True
        req = calls[0]
        assert (req.method, str(req.url)) == ("POST", "https://api.brevo.com/v3/smtp/email")
        assert req.headers["api-key"] == "xkeysib-secret"
        assert json.loads(req.content) == {
            "sender": {"email": "sender@gmail.com", "name": "SecondBrain"},
            "to": [{"email": "me@example.com"}],
            "subject": "Subject", "textContent": "Text body", "htmlContent": "<p>Html</p>",
        }
    finally:
        del os.environ["BREVO_API_KEY"], os.environ["EMAIL_FROM"]


def test_brevo_failures_are_logged_never_raised_and_hide_the_key():
    os.environ.update({"BREVO_API_KEY": "xkeysib-secret", "EMAIL_FROM": "sender@gmail.com"})
    try:
        for client_calls in (brevo(status=400, body={"code": "invalid_parameter", "message": "sender not valid"}),
                             brevo(error=httpx.ConnectError("offline"))):
            client, _ = client_calls
            with patch.object(email_service, "logger") as log:
                assert email_service.send_email("me@example.com", "S", "T", client=client) is False
            assert "xkeysib-secret" not in str(log.mock_calls)
        del os.environ["EMAIL_FROM"]
        with patch.object(email_service, "logger") as log:
            assert email_service.send_email("me@example.com", "S", "T", client=brevo()[0]) is False
        assert "EMAIL_FROM" in str(log.error.call_args)
    finally:
        os.environ.pop("BREVO_API_KEY", None)
        os.environ.pop("EMAIL_FROM", None)


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} passed")
