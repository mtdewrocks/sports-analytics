"""Admin-only endpoints -- not part of the API surface the frontend calls,
just a way to check on the app without opening a DB shell every time.

Gated by a single shared secret (ADMIN_API_KEY) rather than an is_admin
column on User: there's one admin -- whoever runs this app -- so a header
key checked before anything touches the database is simpler, and harder to
get wrong, than standing up a whole permission system for an audience of
one. Compare has_permanent_access on User (models.py), which is kept out of
the API entirely for the same reason in spirit: the fewer sensitive knobs
that exist as routes, the fewer ways they can be misused.

ADMIN_API_KEY unset means every route below refuses with 503, not 401 --
distinguishing "not set up yet" from "wrong key" without ever falling back
to "no key required". Fails closed on a fresh deploy that forgot to set it,
rather than leaving every user's email address world-readable behind an
undocumented but unauthenticated URL.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Subscription, User
from app.notifications import send_email

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_admin(x_admin_key: Optional[str] = Header(None)) -> None:
    if not settings.ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="Admin API not configured (ADMIN_API_KEY unset)")
    if not x_admin_key or x_admin_key != settings.ADMIN_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin key")


@router.get("/users/count")
def user_count(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """The number the whole endpoint exists for, plus enough of a breakdown
    to say what KIND of users they are without a follow-up query. Buckets
    aren't mutually exclusive with each other by construction (a permanent-
    access account's trial_ends_at is whatever it happened to be when it was
    granted) -- each is its own yes/no count, not a partition of `total`.
    """
    now = datetime.utcnow()
    total = db.query(func.count(User.id)).scalar() or 0
    trial_not_expired = db.query(func.count(User.id)).filter(
        User.trial_ends_at > now,
    ).scalar() or 0
    # Same definition of "paying" require_access() (auth/dependencies.py)
    # uses to decide access -- kept in sync with that rather than
    # reinvented here.
    paying_subscribers = db.query(func.count(func.distinct(Subscription.user_id))).filter(
        Subscription.status == "active",
    ).scalar() or 0
    permanent_access = db.query(func.count(User.id)).filter(
        User.has_permanent_access.is_(True),
    ).scalar() or 0
    return {
        "total": total,
        "trial_not_expired": trial_not_expired,
        "paying_subscribers": paying_subscribers,
        "permanent_access": permanent_access,
    }


@router.get("/users")
def list_users(limit: int = 100, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Newest signups first. Never returns hashed_password -- an admin view
    has no reason to touch it, so it never leaves the DB layer at all."""
    limit = max(1, min(limit, 500))
    now = datetime.utcnow()
    users = db.query(User).order_by(User.created_at.desc()).limit(limit).all()

    out = []
    for u in users:
        sub = (
            db.query(Subscription)
            .filter(Subscription.user_id == u.id)
            .order_by(Subscription.updated_at.desc())
            .first()
        )
        out.append({
            "id": u.id,
            "email": u.email,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "state": u.state,
            "favorite_sport": u.favorite_sport,
            "created_at": u.created_at,
            "is_active": u.is_active,
            "has_permanent_access": u.has_permanent_access,
            "trial_not_expired": u.trial_ends_at > now,
            "trial_ends_at": u.trial_ends_at,
            "subscription_status": sub.status if sub else None,
        })
    return out


@router.post("/test-email")
def test_email(_admin=Depends(require_admin)):
    """Confirms SMTP_* and ADMIN_NOTIFY_EMAIL actually work end to end,
    without needing to throw away a real signup to find out. Same
    send_email() the new-user ping uses, so a pass here means that ping
    will actually arrive."""
    if not settings.ADMIN_NOTIFY_EMAIL:
        raise HTTPException(status_code=400, detail="ADMIN_NOTIFY_EMAIL is not set")
    ok = send_email(
        settings.ADMIN_NOTIFY_EMAIL,
        "Sports Analytics: test email",
        "If this arrived, the admin API's SMTP settings are wired up correctly.",
    )
    if not ok:
        raise HTTPException(status_code=502, detail="Send failed -- check server logs for the SMTP error")
    return {"status": "sent", "to": settings.ADMIN_NOTIFY_EMAIL}
