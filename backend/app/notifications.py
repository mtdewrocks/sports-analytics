"""Outbound email -- currently just the "you got a new user" ping.

Plain smtplib rather than a provider SDK (Resend/SendGrid/Postmark/...) so
switching providers later is new env vars, not new code or a new dependency
-- most transactional email services expose an SMTP relay too. Defaults
point at Gmail (see config.py) so the fastest path to working is an
existing Gmail address plus an App Password, not signing up for anything.

Every call here is best-effort: a bad SMTP config, an expired app password,
or a flaky network must never turn an otherwise-successful signup into a
500 for the new user, or a broken deploy. Failures are logged and
swallowed, never raised -- see auth/router.py's register(), which calls
notify_new_user() from a BackgroundTask specifically so a slow or hanging
send can't even delay the response, let alone break it.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from typing import Any, Dict

from app.config import settings

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str) -> bool:
    """Best-effort send. Returns whether it went out; never raises."""
    if not (settings.SMTP_USER and settings.SMTP_PASSWORD and to):
        logger.info("send_email skipped (SMTP not configured or no recipient): %r", subject)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM or settings.SMTP_USER
    msg["To"] = to
    msg.set_content(body)

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception:
        logger.exception("Failed to send email %r to %s", subject, to)
        return False


def notify_new_user(info: Dict[str, Any]) -> None:
    """Fire-and-forget: let the admin know a new account signed up.

    Takes a plain dict of already-loaded fields rather than the SQLAlchemy
    User object itself -- this runs as a BackgroundTask, which fires AFTER
    the request's DB session has been closed by get_db()'s teardown, and a
    session's objects expire on commit. Reading a live ORM object here would
    risk a DetachedInstanceError depending on exactly what got touched and
    when; a dict captured right after the commit/refresh in register() has
    no such lifecycle to trip over.
    """
    if not settings.ADMIN_NOTIFY_EMAIL:
        return

    # Backslash escapes (the em dash below) aren't allowed inside an
    # f-string's {expression} part before Python 3.12 -- built as a plain
    # variable instead of inlining "—" in the f-strings below so this
    # doesn't become a SyntaxError on whatever Python version Render runs.
    dash = "—"
    name = " ".join(p for p in (info.get("first_name"), info.get("last_name")) if p) or "(no name given)"
    created_at = info.get("created_at")
    trial_ends_at = info.get("trial_ends_at")
    body = (
        "New signup on Sports Analytics:\n\n"
        f"  Name:  {name}\n"
        f"  Email: {info.get('email')}\n"
        f"  State: {info.get('state') or dash}\n"
        f"  Favorite sport: {info.get('favorite_sport') or dash}\n"
        f"  Signed up:  {created_at.isoformat() if created_at else dash} UTC\n"
        f"  Trial ends: {trial_ends_at.isoformat() if trial_ends_at else dash} UTC\n"
    )
    send_email(settings.ADMIN_NOTIFY_EMAIL, f"New user: {info.get('email')}", body)
