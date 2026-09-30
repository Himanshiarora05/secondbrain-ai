"""
Accounts and sign-in sessions.

Passwords are stored only as bcrypt hashes. A session is a random token held
by the browser in an HttpOnly cookie (or sent as a Bearer token); only its
SHA-256 hash is stored, so a copy of the database doesn't expose live
sessions. Logging out deletes the session row.
"""

from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.database.db import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    # Stored lowercased and trimmed (see auth_service.normalize_email).
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    sessions = relationship("AuthSession", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)


class AuthSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # SHA-256 of the token, hex. The token itself is never stored.
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)

    user = relationship("User", back_populates="sessions")


class PasswordResetToken(Base):
    """A "forgot password" link: single use, short-lived; only its SHA-256 is stored."""

    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    # Set when the link is used to change the password; a used link never works again.
    used_at = Column(DateTime, nullable=True)
