"""
Sending email through Brevo's transactional API (free plan: 300 emails a day).

One HTTPS call (POST https://api.brevo.com/v3/smtp/email with an "api-key"
header), made with httpx, so there's no extra dependency. Settings in
backend/.env:
  BREVO_API_KEY   the API key (Brevo: SMTP & API -> API Keys)
  EMAIL_FROM      the sender address; it must be a sender verified in Brevo
  EMAIL_FROM_NAME the name shown as the sender (default "SecondBrain")

Without BREVO_API_KEY nothing is sent: the message is written to the backend
log instead (clearly marked), so the features that send email can be used
locally before an account is set up.
"""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
TIMEOUT_SECONDS = 15


def email_configured() -> bool:
    return bool(os.getenv("BREVO_API_KEY", "").strip())


def send_email(to: str, subject: str, text: str, html: Optional[str] = None, client: Optional[httpx.Client] = None) -> bool:
    """Send one email. Returns True if the provider accepted it (or it was logged
    because no provider is configured). Never raises: failures are logged, since
    callers (password reset) must answer the same way whatever happens here."""
    api_key = os.getenv("BREVO_API_KEY", "").strip()
    if not api_key:
        logger.warning(
            "BREVO_API_KEY is not set, so this email was NOT sent; it is shown here instead.\n"
            f"  To: {to}\n  Subject: {subject}\n\n{text}"
        )
        return True

    sender = os.getenv("EMAIL_FROM", "").strip()
    if not sender:
        logger.error("BREVO_API_KEY is set but EMAIL_FROM isn't; set it to a sender verified in Brevo. Email not sent.")
        return False

    payload = {
        "sender": {"email": sender, "name": os.getenv("EMAIL_FROM_NAME", "SecondBrain").strip() or "SecondBrain"},
        "to": [{"email": to}],
        "subject": subject,
        "textContent": text,
    }
    if html:
        payload["htmlContent"] = html

    try:
        own_client = client is None
        client = client or httpx.Client(timeout=TIMEOUT_SECONDS)
        try:
            response = client.post(BREVO_URL, json=payload, headers={"api-key": api_key, "accept": "application/json"})
        finally:
            if own_client:
                client.close()
    except httpx.HTTPError as e:
        logger.error(f"Could not reach Brevo to send '{subject}': {e}")
        return False

    if response.status_code in (200, 201, 202):
        return True
    # Brevo explains problems in the body (e.g. unverified sender, invalid key); the key is never logged.
    logger.error(f"Brevo refused '{subject}' (HTTP {response.status_code}): {response.text[:500]}")
    return False
