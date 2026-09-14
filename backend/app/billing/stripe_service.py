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

PLAN_PRICE_IDS = {
    "monthly": lambda: settings.STRIPE_PRICE_ID_MONTHLY,
    "yearly": lambda: settings.STRIPE_PRICE_ID_YEARLY,
}


def create_checkout_session(user: User, db: Session, plan: str) -> str:
    customer_id = get_or_create_customer(user, db)
    price_id = PLAN_PRICE_IDS[plan]()
    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.FRONTEND_URL}/billing?success=true",
        cancel_url=f"{settings.FRONTEND_URL}/billing?canceled=true",
        metadata={"user_id": user.id, "plan": plan},
    )
    return session.url

def create_portal_session(customer_id: str, return_url: str) -> str:
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return session.url

def _period_end(stripe_sub: dict) -> datetime | None:
    """Renewal date for a subscription.

    Stripe removed `current_period_end` from the Subscription object in API
    version 2025-03-31 (Basil) and moved it onto each subscription ITEM, so
    reading it off the subscription now silently yields None -- no error, the
    renewal date just never gets stored. We read the item, and fall back to the
    old location so this keeps working on pre-Basil API versions.

    Single-price subscriptions have exactly one item; if that ever changes, the
    latest period end across items is the one the customer is paid through.
    """
    items = (stripe_sub.get("items") or {}).get("data") or []
    ends = [i.get("current_period_end") for i in items if i.get("current_period_end")]
    ts = max(ends) if ends else stripe_sub.get("current_period_end")
    return datetime.utcfromtimestamp(ts) if ts else None


def handle_webhook(payload: bytes, sig_header: str, db: Session) -> dict:
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except stripe.error.SignatureVerificationError:
        raise ValueError("Invalid signature")

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        user_id = session.get("metadata", {}).get("user_id")
        stripe_sub_id = session.get("subscription")
        plan = session.get("metadata", {}).get("plan")
        if user_id and stripe_sub_id:
            # Fetch the subscription so the renewal date is stored immediately.
            # Waiting for customer.subscription.updated would leave it NULL
            # until the first renewal -- and that event can also arrive BEFORE
            # this one, in which case its handler finds no row yet and drops it.
            period_end = None
            try:
                period_end = _period_end(stripe.Subscription.retrieve(stripe_sub_id))
            except Exception:
                pass  # a missing renewal date is not worth failing the webhook

            sub = db.query(Subscription).filter(Subscription.user_id == user_id).first()
            if sub:
                sub.stripe_sub_id = stripe_sub_id
                sub.status = "active"
                if period_end:
                    sub.current_period_end = period_end
                if plan:
                    sub.plan_id = plan
            else:
                db.add(Subscription(
                    id=str(uuid.uuid4()), user_id=user_id, stripe_sub_id=stripe_sub_id,
                    status="active", current_period_end=period_end, plan_id=plan,
                ))
            db.commit()

    elif event["type"] in ("customer.subscription.updated", "customer.subscription.created"):
        stripe_sub = event["data"]["object"]
        sub = db.query(Subscription).filter(Subscription.stripe_sub_id == stripe_sub["id"]).first()
        if sub:
            sub.status = stripe_sub["status"]
            period_end = _period_end(stripe_sub)
            if period_end:
                sub.current_period_end = period_end
            db.commit()

    elif event["type"] == "customer.subscription.deleted":
        stripe_sub = event["data"]["object"]
        sub = db.query(Subscription).filter(Subscription.stripe_sub_id == stripe_sub["id"]).first()
        if sub:
            sub.status = "canceled"
            db.commit()

    return {"received": True}
