"""Grading logged bets: closing line value, and win/loss.

Both run lazily when a user opens My Bets -- only their own pending bets,
only once the game is far enough along -- so there's no separate job to
schedule and nothing runs for users who never look.

CLV
---
Needs the closing line (build_odds_snapshots.py's <slug>_closing_lines.parquet,
the last price each book hung before the game started).

    fair close  = the no-vig chance of this side at close: Pinnacle's
                  two-way price if it had this line, else the median of each
                  book's own de-vigged price
    CLV         = your decimal odds x fair close - 1

+3% CLV means you got a price 3% better than the market's final, sharpest
view of that bet. If no book closed at exactly your line (the line moved),
CLV stays empty rather than being guessed.

RESULTS
-------
From the same game logs the Hit Rate Sheet grades against, using the same
market -> stat definitions (MLB_MARKET_STAT_MAP, NFL_MARKET_STAT), so a bet
and the sheet can never disagree about what "over 1.5 hits" means. A bet the
data can't settle (doubleheader, missing box score, NBA until its props move
to this pipeline) stays pending, and the user can mark it themselves --
recorded as result_source="user".
"""

from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from app.market_core import closing_for  # noqa: F401  (re-exported for tests)
from app.odds_math import to_decimal

RESULT_DELAY_HOURS = 5      # box scores land after the game; don't grade too early


def _key(name: Any) -> str:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower().replace(".", "").replace("'", "")
    return " ".join(p for p in s.split() if p not in {"jr", "sr", "ii", "iii", "iv", "v"})


# ── CLV ──────────────────────────────────────────────────────────────────

# ── results ──────────────────────────────────────────────────────────────

def settle(value: Optional[float], line: Optional[float], side: str) -> Optional[str]:
    """win/loss/push for one stat value. Yes/No markets (line None) treat
    1+ as the Over/Yes."""
    if value is None:
        return None
    target = 0.5 if line is None else float(line)
    if value == target:
        return "push"
    over_wins = value > target
    return "win" if over_wins == (side == "over") else "loss"


def _et_date(ts) -> Optional[str]:
    t = pd.to_datetime(ts, utc=True, errors="coerce")
    if pd.isna(t):
        return None
    return t.tz_convert("America/New_York").strftime("%Y-%m-%d")


def _mlb_value(bet: Dict[str, Any]) -> Optional[float]:
    from app.data import mlb
    m = str(bet["market"]).replace("_alternate", "")
    key = m if m.startswith("pitcher_") else f"batter_{m}"
    date = _et_date(bet.get("commence_time"))
    if key not in mlb.MLB_MARKET_STAT_MAP or not date:
        return None
    logs = (mlb._pitcher_logs_for_market(key) if key.startswith("pitcher_")
            else mlb._batter_logs_for_market(key))
    lookup = (mlb._mlb_pitcher_name_lookup() if key.startswith("pitcher_")
              else mlb._mlb_batter_name_lookup())[0]
    pid = lookup.get(mlb._normalize(bet["player"]))
    if logs.empty or pid is None:
        return None
    rows = logs[(logs["player_id"] == pid)
                & (pd.to_datetime(logs["game_date"]).dt.strftime("%Y-%m-%d") == date)]
    if len(rows) != 1:          # not played yet / doubleheader: leave it to the user
        return None
    return float(rows["stat_value"].iloc[0])


def _nfl_value(bet: Dict[str, Any]) -> Optional[float]:
    from app.data import nfl
    from app.data.loader import get_nfl_schedule
    m = str(bet["market"]).replace("_alternate", "")
    spec = nfl.NFL_MARKET_STAT.get(m)
    date = _et_date(bet.get("commence_time"))
    if spec is None or not date:
        return None
    sched = get_nfl_schedule()
    if sched.empty:
        return None
    wk = sched[sched["gameday"].astype(str) == date]
    if wk.empty:
        return None
    season, week = int(wk["season"].iloc[0]), int(wk["week"].iloc[0])
    d, col, _ = nfl._nfl_current_season_frame()
    if d.empty:
        return None
    rows = d[(d["season"] == season) & (d["week"] == week)
             & (d[col].astype(str).map(nfl._normalize_loose) == nfl._normalize_loose(bet["player"]))]
    if rows.empty:
        return None
    return float(nfl._nfl_stat_value(rows.iloc[0], spec))


def result_for(bet: Dict[str, Any]) -> Optional[str]:
    try:
        value = {"mlb": _mlb_value, "nfl": _nfl_value}.get(bet["sport"], lambda b: None)(bet)
    except Exception as e:
        print(f"Warning: grading {bet.get('player')} failed: {e}")
        return None
    return settle(value, bet.get("line"), bet["side"])


# ── orchestration ────────────────────────────────────────────────────────

def grade_bets(bets: List[Any], db) -> int:
    """Grade what can be graded among these ORM rows; returns how many changed."""
    from app.data.loader import get_closing_lines_data
    now = datetime.utcnow()
    changed = 0
    closes_by_sport: Dict[str, pd.DataFrame] = {}
    for b in bets:
        if not b.commence_time or b.commence_time > now:
            continue
        d = {"sport": b.sport, "event_id": b.event_id, "player": b.player, "market": b.market,
             "line": b.line, "side": b.side, "book": b.book, "price": b.price,
             "commence_time": b.commence_time.isoformat() + "Z"}
        if b.clv_pct is None:
            if b.sport not in closes_by_sport:
                closes_by_sport[b.sport] = get_closing_lines_data(b.sport)
            c = closing_for(d, closes_by_sport[b.sport])
            if c:
                b.close_price, b.close_fair_pct, b.clv_pct = c["close_price"], c["close_fair_pct"], c["clv_pct"]
                changed += 1
        if b.result == "pending" and b.commence_time + timedelta(hours=RESULT_DELAY_HOURS) <= now:
            r = result_for(d)
            if r:
                b.result, b.result_source, b.graded_at = r, "auto", now
                changed += 1
    if changed:
        db.commit()
    return changed


def profit_units(price: int, result: str) -> float:
    """Profit per 1 unit staked."""
    if result == "win":
        return to_decimal(price) - 1
    if result == "loss":
        return -1.0
    return 0.0


def summarize(bets: List[Any]) -> Dict[str, Any]:
    """The My Bets tiles. ROI is per unit staked, so it works without stakes;
    'expected ROI' is what the average CLV implies."""
    settled = [b for b in bets if b.result in ("win", "loss", "push")]
    with_clv = [b for b in bets if b.clv_pct is not None]
    units = sum(profit_units(b.price, b.result) for b in settled)
    risked = sum(1 for b in settled if b.result != "push")
    avg_clv = round(sum(b.clv_pct for b in with_clv) / len(with_clv), 2) if with_clv else None
    return {
        "bets": len(bets),
        "settled": len(settled),
        "record": {r: sum(1 for b in settled if b.result == r) for r in ("win", "loss", "push")},
        "units": round(units, 2),
        "roi_pct": round(units / risked * 100, 1) if risked else None,
        "avg_clv_pct": avg_clv,
        "beat_close_pct": (round(sum(1 for b in with_clv if b.clv_pct > 0) / len(with_clv) * 100, 1)
                           if with_clv else None),
        "clv_bets": len(with_clv),
        "verified_share_pct": (round(sum(1 for b in bets if b.verification == "verified") / len(bets) * 100)
                               if bets else None),
    }
