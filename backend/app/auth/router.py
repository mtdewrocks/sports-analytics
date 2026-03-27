from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from passlib.context import CryptContext
from app.database import get_db
from app.models import User, Subscription
from app.schemas import UserRegister, UserLogin, TokenWithUser, UserOut
from app.auth.jwt import create_access_token
from app.auth.dependencies import get_current_user
from app.config import settings
import uuid

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@router.post("/register", response_model=TokenWithUser)
def register(data: UserRegister, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        id=str(uuid.uuid4()),
        email=data.email,
        hashed_password=pwd_context.hash(data.password),
        trial_ends_at=datetime.utcnow() + timedelta(days=settings.TRIAL_DAYS),
    )
    db.add(user)
    sub = Subscription(id=str(uuid.uuid4()), user_id=user.id, status="trialing")
    db.add(sub)
    db.commit()
    db.refresh(user)
    token = create_access_token({"sub": user.id})
    return TokenWithUser(access_token=token, user=UserOut.model_validate(user))

@router.post("/login", response_model=TokenWithUser)
def login(data: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not pwd_context.verify(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({"sub": user.id})
    return TokenWithUser(access_token=token, user=UserOut.model_validate(user))

@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)
