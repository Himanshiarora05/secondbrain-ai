"""
Password hashing, sign-in sessions and the current-user dependency.

- Passwords: bcrypt (at least 8 characters; bcrypt reads only 72 bytes, so
  longer ones are refused rather than silently cut).
- Sessions: secrets.token_urlsafe(32), valid for SESSION_DAYS; only the
  SHA-256 hash is stored. The browser keeps the token in an HttpOnly,
  SameSite=Lax cookie (page scripts can't read it); scripts and tests can
  send it as "Authorization: Bearer <token>" instead.
- get_current_user: FastAPI dependency for every protected endpoint; 401
  without a valid, unexpired session.
"""

import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.user import AuthSession, User

SESSION_COOKIE = "sb_session"
SESSION_DAYS = 30
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_BYTES = 72  # bcrypt ignores anything after this
MAX_EMAIL_LENGTH = 254
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Compared against when the email is unknown, so a login for a missing
# account takes as long as one with a wrong password.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt())


def signup_allowed() -> bool:
    """ALLOW_SIGNUP=false in .env closes sign-up (existing accounts still log in)."""
    return os.getenv("ALLOW_SIGNUP", "true").strip().lower() not in ("false", "0", "no", "off")


def cookie_secure() -> bool:
    """Send the cookie over HTTPS only. Off by default: the dev servers use plain http://localhost."""
    return os.getenv("SESSION_COOKIE_SECURE", "false").strip().lower() in ("true", "1", "yes", "on")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def check_email(email: str) -> Optional[str]:
    """A plain message if the email can't be used, else None."""
    if not email or len(email) > MAX_EMAIL_LENGTH or not _EMAIL_RE.match(email):
        return "Please enter a valid email address."
    return None


def check_password(password: str) -> Optional[str]:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Use at least {MIN_PASSWORD_LENGTH} characters for your password."
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        return f"That password is too long; use at most {MAX_PASSWORD_BYTES} bytes (about {MAX_PASSWORD_BYTES} plain characters)."
    return None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: Optional[str]) -> bool:
    data = password.encode("utf-8")
    if len(data) > MAX_PASSWORD_BYTES:
        bcrypt.checkpw(b"x", _DUMMY_HASH)  # same cost as a real check
        return False
    if not password_hash:
        bcrypt.checkpw(data, _DUMMY_HASH)
        return False
    return bcrypt.checkpw(data, password_hash.encode("ascii"))


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: User) -> str:
    """Start a session for `user` and return its token (shown to the client once)."""
    token = secrets.token_urlsafe(32)
    db.add(AuthSession(
        user_id=user.id,
        token_hash=_token_hash(token),
        expires_at=datetime.utcnow() + timedelta(days=SESSION_DAYS),
    ))
    db.commit()
    return token


def user_for_token(db: Session, token: Optional[str]) -> Optional[User]:
    """The user a valid, unexpired session token belongs to; expired sessions are removed."""
    if not token:
        return None
    session = db.query(AuthSession).filter(AuthSession.token_hash == _token_hash(token)).first()
    if session is None:
        return None
    if session.expires_at <= datetime.utcnow():
        db.delete(session)
        db.commit()
        return None
    return db.get(User, session.user_id)


def end_session(db: Session, token: Optional[str]) -> None:
    if token:
        db.query(AuthSession).filter(AuthSession.token_hash == _token_hash(token)).delete()
        db.commit()


def token_from_request(request: Request) -> Optional[str]:
    """The session token from the cookie, or from "Authorization: Bearer <token>"."""
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return request.cookies.get(SESSION_COOKIE)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = user_for_token(db, token_from_request(request))
    if user is None:
        raise HTTPException(status_code=401, detail="Please log in to continue.")
    return user
