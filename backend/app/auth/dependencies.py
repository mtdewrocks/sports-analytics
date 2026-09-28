from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.database import get_db
from app.models import User, Subscription
from app.auth.jwt import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    payload = decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user

def access_ends_at(user: User) -> datetime:
    """When this account's free access ends: its own trial, or the open beta
    (settings.BETA_ENDS_AT) if that runs longer."""
    from app.config import settings
    beta = settings.BETA_ENDS_AT
    if beta is not None:
        if beta.tzinfo is not None:
            beta = beta.astimezone(timezone.utc).replace(tzinfo=None)
        return max(user.trial_ends_at, beta)
    return user.trial_ends_at


def require_access(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    if user.has_permanent_access:
        return user
    trial_ok = access_ends_at(user) > datetime.utcnow()
    sub = db.query(Subscription).filter(Subscription.user_id == user.id, Subscription.status == "active").first()
    if not trial_ok and not sub:
        raise HTTPException(status_code=402, detail="trial_expired")
    return user
