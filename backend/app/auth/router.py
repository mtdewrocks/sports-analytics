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
import hashlib
import logging

logger = logging.getLogger(__name__)

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _prepare_password(password: str) -> str:
    """
    SHA-256 pre-hash the password before bcrypt.
    bcrypt has a hard 72-byte limit — pre-hashing produces a fixed-length
    64-character hex string so any password length works safely.
    """
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    return pwd_context.hash(_prepare_password(password))


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(_prepare_password(plain), hashed)


@router.post("/register", response_model=TokenWithUser)
def register(data: UserRegister, db: Session = Depends(get_db)):
    try:
        if db.query(User).filter(User.email == data.email).first():
            raise HTTPException(status_code=400, detail="Email already registered")
        user = User(
            id=str(uuid.uuid4()),
            email=data.email,
            hashed_password=hash_password(data.password),
            trial_ends_at=datetime.utcnow() + timedelta(days=settings.TRIAL_DAYS),
        )
        db.add(user)
        sub = Subscription(id=str(uuid.uuid4()), user_id=user.id, status="trialing")
        db.add(sub)
        db.commit()
        db.refresh(user)
        token = create_access_token({"sub": user.id})
        return TokenWithUser(access_token=token, user=UserOut.model_validate(user))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Registration failed for %s: %s", data.email, e)
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@router.post("/login", response_model=TokenWithUser)
def login(data: UserLogin, db: Session = Depends(get_db)):
    try:
        user = db.query(User).filter(User.email == data.email).first()
        if not user or not verify_password(data.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        token = create_access_token({"sub": user.id})
        return TokenWithUser(access_token=token, user=UserOut.model_validate(user))
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Login failed for %s: %s", data.email, e)
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)
