import stripe
from sqlalchemy.orm import Session
from datetime import datetime
from app.config import settings
from app.models import User, Subscription
import uuid

stripe.api_key = settings.STRIPE_SECRET_KEY

def get_or_create_customer(user: User, db: Session) -> str:
    if user.stripe_customer_id:
        return user.stripe_customer_id
    customer = stripe.Customer.create(email=user.email, metadata={"user_id": user.id})
    user.stripe_customer_id = customer.id
    db.commit()
    return customer.id

def create_checkout_session(user: User, db: Session) -> str:
    customer_id = get_or_create_customer(user, db)
    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": settings.STRIPE_PRICE_ID, "quantity": 1}],
        success_url=f"{settings.FRONTEND_URL}/billing?success=true",
        cancel_url=f"{settings.FRONTEND_URL}/billing?canceled=true",
        metadata={"user_id": user.id},
    )
    return session.url

def create_portal_session(customer_id: str, return_url: str) -> str:
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return session.url

def handle_webhook(payload: bytes, sig_header: str, db: Session) -> dict:
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise ValueError("Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id")
        stripe_sub_id = session.get("subscription")
        if user_id and stripe_sub_id:
            sub = db.query(Subscription).filter(Subscription.user_id == user_id).first()
            if sub:
                sub.stripe_sub_id = stripe_sub_id
                sub.status = "active"
            else:
                db.add(Subscription(id=str(uuid.uuid4()), user_id=user_id, stripe_sub_id=stripe_sub_id, status="active"))
            db.commit()

    elif event["type"] in ("customer.subscription.updated", "customer.subscription.created"):
        stripe_sub = event["data"]["object"]
        sub = db.query(Subscription).filter(Subscription.stripe_sub_id == stripe_sub["id"]).first()
        if sub:
            sub.status = stripe_sub["status"]
            period_end = stripe_sub.get("current_period_end")
            if period_end:
                sub.current_period_end = datetime.utcfromtimestamp(period_end)
            db.commit()

    elif event["type"] == "customer.subscription.deleted":
        stripe_sub = event["data"]["object"]
        sub = db.query(Subscription).filter(Subscription.stripe_sub_id == stripe_sub["id"]).first()
        if sub:
            sub.status = "canceled"
            db.commit()

    return {"received": True}
