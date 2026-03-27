from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import datetime
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

def require_access(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> User:
    trial_ok = user.trial_ends_at > datetime.utcnow()
    sub = db.query(Subscription).filter(Subscription.user_id == user.id, Subscription.status == "active").first()
    if not trial_ok and not sub:
        raise HTTPException(status_code=402, detail="trial_expired")
    return user
