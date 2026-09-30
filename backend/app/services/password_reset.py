"""
"Forgot password": reset links sent by email.

- A link carries a random token (secrets.token_urlsafe(32)); only its SHA-256
  is stored. It works once and expires after PASSWORD_RESET_MINUTES (30).
  Asking for a new link cancels any earlier unused one.
- Asking for a link always gets the same answer, whether or not the email has
  an account, and the email is sent in the background so the answer's timing
  doesn't tell either. At most MAX_REQUESTS_PER_HOUR links per account per
  hour; extra requests get the same answer and send nothing.
- Setting the new password marks the link used and ends every session of
  that account, so anyone who knew the old password is logged out.
"""

import hashlib
import html
import os
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import AuthSession, PasswordResetToken, User
from app.services import auth_service as auth
from app.services.email_service import send_email

MAX_REQUESTS_PER_HOUR = 3
REQUEST_REPLY = "If an account exists for that email, we've sent a link to reset its password. It expires in {minutes} minutes."
BAD_LINK = "This reset link is invalid, has expired or was already used. Ask for a new one."


def reset_minutes() -> int:
    try:
        return max(5, int(os.getenv("PASSWORD_RESET_MINUTES", "30")))
    except ValueError:
        return 30


def app_base_url() -> str:
    """Where the frontend runs, for the link in the email (APP_BASE_URL in .env)."""
    return os.getenv("APP_BASE_URL", "http://localhost:5173").strip().rstrip("/")


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_reset(db: Session, user: User) -> Optional[str]:
    """A new reset token for `user`, or None when the hourly limit is reached."""
    now = datetime.utcnow()
    recent = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.user_id == user.id, PasswordResetToken.created_at > now - timedelta(hours=1))
        .count()
    )
    if recent >= MAX_REQUESTS_PER_HOUR:
        return None
    # Only the newest link works.
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)
    ).update({PasswordResetToken.expires_at: now}, synchronize_session=False)
    token = secrets.token_urlsafe(32)
    db.add(PasswordResetToken(user_id=user.id, token_hash=_hash(token), expires_at=now + timedelta(minutes=reset_minutes())))
    db.commit()
    return token


def reset_email(email: str, token: str) -> dict:
    """Subject, plain text and HTML for a reset link."""
    link = f"{app_base_url()}/reset-password?token={token}"
    minutes = reset_minutes()
    text = (
        f"Someone (hopefully you) asked to reset the password for the SecondBrain account {email}.\n\n"
        f"Set a new password here. The link works once and expires in {minutes} minutes:\n{link}\n\n"
        "If you didn't ask for this, ignore this email; your password won't change."
    )
    safe_email, safe_link = html.escape(email), html.escape(link, quote=True)
    body = f"""<div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.5;color:#111;max-width:520px">
<p>Someone (hopefully you) asked to reset the password for the SecondBrain account <b>{safe_email}</b>.</p>
<p><a href="{safe_link}" style="display:inline-block;padding:10px 18px;background:#2563eb;color:#fff;border-radius:8px;text-decoration:none;font-weight:bold">Set a new password</a></p>
<p style="font-size:13px;color:#555">The link works once and expires in {minutes} minutes. If the button doesn't work, copy this address into your browser:<br><span style="word-break:break-all">{safe_link}</span></p>
<p style="font-size:13px;color:#555">If you didn't ask for this, ignore this email; your password won't change.</p>
</div>"""
    return {"subject": "Reset your SecondBrain password", "text": text, "html": body}


def send_reset_email(email: str, token: str) -> None:
    """Runs in the background after the request has been answered."""
    message = reset_email(email, token)
    send_email(email, message["subject"], message["text"], message["html"])


def valid_token(db: Session, token: Optional[str], lock: bool = False) -> Optional[PasswordResetToken]:
    if not token:
        return None
    query = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == _hash(token),
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.expires_at > datetime.utcnow(),
    )
    if lock:
        query = query.with_for_update()
    return query.first()


def reset_password(db: Session, token: str, new_password: str) -> Optional[User]:
    """Set the new password with a valid token; returns the user, or None for a bad link.

    The token row is locked so two submissions of the same link can't both succeed.
    """
    row = valid_token(db, token, lock=True)
    if row is None:
        db.rollback()
        return None
    user = db.get(User, row.user_id)
    now = datetime.utcnow()
    user.password_hash = auth.hash_password(new_password)
    row.used_at = now
    db.query(AuthSession).filter(AuthSession.user_id == user.id).delete(synchronize_session=False)
    db.commit()
    return user
