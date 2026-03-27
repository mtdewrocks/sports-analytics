from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.models import User, Subscription
from app.schemas import BillingStatus
from app.auth.dependencies import get_current_user
from app.billing.stripe_service import create_checkout_session, create_portal_session, handle_webhook
from app.config import settings

router = APIRouter()

@router.get("/status", response_model=BillingStatus)
def billing_status(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    days_remaining = max(0, (user.trial_ends_at - now).days)
    sub = db.query(Subscription).filter(Subscription.user_id == user.id).first()
    if days_remaining > 0:
        status_str = "trialing"
    elif sub and sub.status == "active":
        status_str = "active"
    else:
        status_str = "expired"
    return BillingStatus(
        status=status_str,
        trial_ends_at=user.trial_ends_at,
        days_remaining=days_remaining,
        subscription_status=sub.status if sub else None,
        current_period_end=sub.current_period_end if sub else None,
    )

@router.post("/checkout")
def checkout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not settings.STRIPE_SECRET_KEY or not settings.STRIPE_PRICE_ID:
        raise HTTPException(status_code=503, detail="Billing not configured")
    url = create_checkout_session(user, db)
    return {"checkout_url": url}

@router.post("/portal")
def portal(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account found")
    url = create_portal_session(user.stripe_customer_id, f"{settings.FRONTEND_URL}/billing")
    return {"portal_url": url}

@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        result = handle_webhook(payload, sig_header, db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
