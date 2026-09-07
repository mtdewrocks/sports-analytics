import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    trial_ends_at = Column(DateTime, nullable=False)
    stripe_customer_id = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    # Profile fields
    first_name = Column(String(100), nullable=True)
    last_name = Column(String(100), nullable=True)
    state = Column(String(50), nullable=True)
    favorite_sport = Column(String(50), nullable=True)
    favorite_teams = Column(String(500), nullable=True)
    # Bypasses trial/subscription checks entirely when True. Deliberately
    # NOT settable through any API route or admin UI -- only ever flipped
    # by a direct database update, so there is nothing in the source code
    # (which may not stay private forever) that identifies which account
    # has it or how to grant it to a new one.
    has_permanent_access = Column(Boolean, default=False, nullable=False, server_default="false")
    subscriptions = relationship("Subscription", back_populates="user")

class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    stripe_sub_id = Column(String(255), unique=True, nullable=True)
    status = Column(String(50), default="trialing")
    current_period_end = Column(DateTime, nullable=True)
    plan_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    user = relationship("User", back_populates="subscriptions")
