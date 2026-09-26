import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Float, Integer
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


class Bet(Base):
    """One bet a user logged from a "Bet this" sheet (or entered by hand).

    placed_at is set by the server, never the client, and a bet can't be
    logged after its game starts -- that's what makes CLV and records
    trustworthy. `verification` says how much to trust the price:
      verified       the price the user took matches what we saw at that book
                     when they tapped (live check or scheduled pull)
      self_reported  the user entered a different price
    Only verified bets should ever count toward anything public.
    """
    __tablename__ = "bets"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    sport = Column(String(10), nullable=False)
    event_id = Column(String(64), nullable=True)
    player = Column(String(120), nullable=False)
    market = Column(String(80), nullable=False)          # props-file key, e.g. "receptions"
    line = Column(Float, nullable=True)                   # None for Yes/No markets
    side = Column(String(10), nullable=False)             # "over" | "under"
    book = Column(String(40), nullable=False)
    price = Column(Integer, nullable=False)               # American odds the user took
    quoted_price = Column(Integer, nullable=True)         # what we showed at that book
    stake = Column(Float, nullable=True)
    tool = Column(String(20), nullable=True)              # ev | alt | today | manual
    verification = Column(String(20), nullable=False, default="self_reported")
    commence_time = Column(DateTime, nullable=True)
    home_team = Column(String(80), nullable=True)
    away_team = Column(String(80), nullable=True)
    placed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    # Filled in after the game by app/bets/grading.py.
    close_price = Column(Integer, nullable=True)          # same book's closing price
    close_fair_pct = Column(Float, nullable=True)         # no-vig closing chance of this side
    clv_pct = Column(Float, nullable=True)                # (your decimal / fair close decimal - 1) x 100
    result = Column(String(10), nullable=False, default="pending")  # pending|win|loss|push|void
    result_source = Column(String(10), nullable=True)     # auto | user
    graded_at = Column(DateTime, nullable=True)
