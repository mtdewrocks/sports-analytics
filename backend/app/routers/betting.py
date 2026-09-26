"""Cross-sport betting endpoints: Today feed, live quotes, bet log, report card."""

from datetime import datetime
from typing import Literal, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import require_access
from app.database import get_db
from app.models import Bet, User

router = APIRouter(prefix="/api/betting", tags=["betting"])

Sport = Literal["mlb", "nfl", "nba"]


@router.get("/briefing")
def briefing(_=Depends(require_access)):
    """Daily Briefing -- see app/data/briefing.py."""
    from app.data.briefing import get_briefing
    return get_briefing()


@router.get("/today")
def today(_=Depends(require_access)):
    from app.data.today import get_today
    return get_today()


@router.get("/quote")
def quote(
    sport: Sport, player: str, market: str, side: Literal["over", "under"],
    line: Optional[float] = Query(None), book: Optional[str] = Query(None),
    event_id: Optional[str] = Query(None), user: User = Depends(require_access),
):
    """Current price for one bet (live when possible) plus bet-slip links."""
    from app.odds_live import get_quote
    return get_quote(sport, player, market, line, side, book, event_id, user.state)


class BetIn(BaseModel):
    sport: Sport
    player: str = Field(..., max_length=120)
    market: str = Field(..., max_length=80)
    line: Optional[float] = None
    side: Literal["over", "under"]
    book: str = Field(..., max_length=40)
    price: int
    stake: Optional[float] = Field(None, ge=0, le=1_000_000)
    tool: Optional[str] = Field(None, max_length=20)
    event_id: Optional[str] = Field(None, max_length=64)


def _bet_out(b: Bet) -> dict:
    return {c.name: (getattr(b, c.name).isoformat() + "Z" if isinstance(getattr(b, c.name), datetime)
                     else getattr(b, c.name))
            for c in Bet.__table__.columns if c.name != "user_id"}


@router.post("/bets")
def log_bet(body: BetIn, user: User = Depends(require_access), db: Session = Depends(get_db)):
    """Log a bet. The server stamps the time, refuses games that have
    started, and marks the bet verified only if the price taken is no better
    than what we saw at that book when the sheet opened."""
    from app.odds_live import get_quote, props_market
    if not (body.price >= 100 or body.price <= -100):
        raise HTTPException(400, "Price must be American odds, e.g. -110 or +150.")
    market = props_market(body.market)
    q = get_quote(body.sport, body.player, market, body.line, body.side, body.book,
                  body.event_id, user.state)
    if q.get("reason") == "started":
        raise HTTPException(409, "This game has already started; bets can only be logged before it begins.")
    if q.get("reason") == "not_found":
        raise HTTPException(404, "Couldn't find this prop in today's lines.")
    quoted = (q.get("at_book") or {}).get("price")
    verified = quoted is not None and body.price <= quoted
    start = pd.to_datetime(q.get("commence_time"), utc=True, errors="coerce")
    bet = Bet(
        user_id=user.id, sport=body.sport, event_id=q.get("event_id"), player=body.player,
        market=market, line=body.line, side=body.side, book=body.book.lower(), price=body.price,
        quoted_price=quoted, stake=body.stake, tool=body.tool or "manual",
        verification="verified" if verified else "self_reported",
        commence_time=None if pd.isna(start) else start.tz_convert(None).to_pydatetime(),
        home_team=q.get("home_team"), away_team=q.get("away_team"),
    )
    db.add(bet)
    db.commit()
    db.refresh(bet)
    return _bet_out(bet)


@router.get("/bets")
def my_bets(user: User = Depends(require_access), db: Session = Depends(get_db)):
    """Your bets (newest first) and the summary tiles. Grades anything that
    has become gradeable since the last look."""
    from app.bets.grading import grade_bets, summarize
    bets = db.query(Bet).filter(Bet.user_id == user.id).order_by(Bet.placed_at.desc()).all()
    grade_bets([b for b in bets if b.result == "pending" or b.clv_pct is None], db)
    return {"summary": summarize(bets), "bets": [_bet_out(b) for b in bets]}


class ResultIn(BaseModel):
    result: Literal["win", "loss", "push", "void"]


@router.patch("/bets/{bet_id}")
def set_result(bet_id: str, body: ResultIn, user: User = Depends(require_access),
               db: Session = Depends(get_db)):
    """Settle a bet by hand -- only once its game has started."""
    b = db.query(Bet).filter(Bet.id == bet_id, Bet.user_id == user.id).first()
    if not b:
        raise HTTPException(404, "Bet not found.")
    if b.commence_time and b.commence_time > datetime.utcnow():
        raise HTTPException(409, "This game hasn't started yet.")
    b.result, b.result_source, b.graded_at = body.result, "user", datetime.utcnow()
    db.commit()
    return _bet_out(b)


@router.delete("/bets/{bet_id}")
def delete_bet(bet_id: str, user: User = Depends(require_access), db: Session = Depends(get_db)):
    """Remove a bet -- only before its game starts, so a record can't be
    cleaned up after the fact."""
    b = db.query(Bet).filter(Bet.id == bet_id, Bet.user_id == user.id).first()
    if not b:
        raise HTTPException(404, "Bet not found.")
    if b.commence_time and b.commence_time <= datetime.utcnow():
        raise HTTPException(409, "Bets can't be deleted once the game has started.")
    db.delete(b)
    db.commit()
    return {"deleted": bet_id}


@router.get("/report-card")
def report_card(_=Depends(require_access)):
    """How the EV Finder's flagged plays have done against the close."""
    from app.data.report_card import get_report_card
    return get_report_card()
