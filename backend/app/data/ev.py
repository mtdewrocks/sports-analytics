"""EV Finder: props where one sportsbook is paying more than the bet is worth.

No model involved. The "true" chance of each side comes from the market
itself, with the vig removed:

  SHARP      Pinnacle's two-way price on the same line, de-vigged. Used
             whenever Pinnacle hangs that exact line.
  CONSENSUS  Every OTHER sportsbook's two-way price on the same line,
             de-vigged book by book, then the median of those fair
             probabilities. Leave-one-out on purpose: the book being judged
             never votes on its own fair price, so a single outlier can't
             drag the consensus toward itself and hide its own edge.

Then every book's price on each side is compared with that fair chance, and
EV = p x payout - (1 - p). A price far from the pack that is only breakeven
once the vig comes out is NOT flagged -- that's the case the page explains.

What's never evaluated or used for consensus:
  * DFS / pick'em apps -- their "price" is a share of a multi-pick payout,
    not a bet you can place alone (see props_config.NO_SINGLE_BET_BOOKS).
  * UNBETTABLE_BOOKS.
  * Games that have started -- their lines are frozen pre-game snapshots.
Sharp books are used ONLY as the reference, never as a book to bet.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from app.data.loader import get_odds_snapshots_data, get_props_data
from app.data.props import _is_live_series
from app.odds_math import (
    devig_two_way, ev_per_unit, implied_prob, is_price, median,
    median_price, prob_to_american,
)
from app.props_config import NO_SINGLE_BET_BOOKS, SHARP_BOOKS, UNBETTABLE_BOOKS

GROUP = ["event_id", "Player", "market", "Line"]

# An edge this large on a two-way prop is far more often a stale or
# mis-posted price than free money. Still shown, but labelled, so a user
# checks the book before betting into it.
SUSPICIOUS_EV = 0.25


def _price_since(sport: str) -> Dict[tuple, str]:
    """(event_id, Player, market, Line, book) -> when the CURRENT price was
    first seen, from the snapshot history (it only records changes, so the
    last row per key is the moment the live price appeared). Empty until
    snapshots exist; the page then just omits the "posted X ago" note."""
    snaps = get_odds_snapshots_data(sport)
    if snaps.empty or "observed_at" not in snaps.columns:
        return {}
    s = snaps.sort_values("observed_at").drop_duplicates(
        subset=["event_id", "Player", "market", "Line", "bookmakers"], keep="last")
    line = pd.to_numeric(s["Line"], errors="coerce")
    return {
        (str(e), str(p), str(m), None if pd.isna(l) else float(l), str(b)): str(t)
        for e, p, m, l, b, t in zip(s["event_id"], s["Player"], s["market"],
                                   line, s["bookmakers"], s["observed_at"])
    }


def _fair_over(rows: List[dict], judged_book: Optional[str], source: str,
               min_books: int) -> Optional[Dict[str, Any]]:
    """Fair probability of the OVER for one prop line, excluding
    `judged_book` from the consensus. `rows` are that line's books, each a
    dict with book/over/under/fair (fair = that book's own de-vigged Over
    chance, or None if it isn't two-sided). Returns None if the requested
    source can't produce one."""
    if source in ("sharp", "auto"):
        for r in rows:
            if r["book"] in SHARP_BOOKS and r["fair"] is not None:
                return {"p": r["fair"], "source": "sharp", "books": 1,
                        "ref": f"{r['book']} {int(r['over']):+d}/{int(r['under']):+d}"}
        if source == "sharp":
            return None

    fair = [r["fair"] for r in rows
            if r["fair"] is not None and r["book"] not in SHARP_BOOKS and r["book"] != judged_book]
    if len(fair) < min_books:
        return None
    return {"p": median(fair), "source": "consensus", "books": len(fair), "ref": None}


def _txt(v) -> Optional[str]:
    """String, or None for any flavour of missing (None/NaN/NA/NaT) -- the
    JSON encoder can't serialize pandas' NA."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return str(v)


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def get_ev(
    sport: str,
    source: str = "auto",
    min_edge: float = 2.0,
    min_books: int = 2,
    market: Optional[str] = None,
    player: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Every (prop line, side, book) whose price beats the fair price by at
    least `min_edge` percent EV, best first.

    source     "auto" (sharp where available, else consensus), "sharp", or
               "consensus".
    min_books  Minimum number of OTHER books with a two-way price needed
               to form a consensus. 2 by default; 3+ is sturdier.

    Plain Python over records rather than pandas groupby/iterrows: a props
    file is ~10-15k rows split into thousands of tiny groups, where pandas'
    per-group overhead measured 15-27 seconds against well under one here.
    """
    df = get_props_data(sport)
    if df.empty or "Player" not in df.columns:
        return []

    df = df.copy()
    df["bookmakers"] = df["bookmakers"].astype(str).str.lower()
    df = df[~df["bookmakers"].isin(UNBETTABLE_BOOKS) & ~df["bookmakers"].isin(NO_SINGLE_BET_BOOKS)]
    if "commence_time" in df.columns:
        df = df[~_is_live_series(df["commence_time"])]
    if market:
        df = df[df["market"].astype(str).str.lower() == market.lower()]
    if player:
        df = df[df["Player"].astype(str).str.lower().str.contains(player.lower(), regex=False)]
    if df.empty:
        return []

    groups: Dict[tuple, List[dict]] = {}
    for r in df.to_dict(orient="records"):
        line = _num(r.get("Line"))
        over, under = _num(r.get("Over Price")), _num(r.get("Under Price"))
        rec = {
            "book": r["bookmakers"], "over": over, "under": under,
            "fair": devig_two_way(over, under), "line": line, "raw": r,
        }
        key = (str(r["event_id"]), str(r["Player"]), str(r["market"]), line)
        groups.setdefault(key, []).append(rec)

    since = _price_since(sport)
    out: List[Dict[str, Any]] = []

    for (event_id, player_name, mkt, line), rows in groups.items():
        bettable = [r for r in rows if r["book"] not in SHARP_BOOKS]
        if not bettable:
            continue
        # Cheap pre-check: with no sharp price and too few two-way books,
        # nothing in this group can get a fair price at all.
        two_way = sum(1 for r in bettable if r["fair"] is not None)
        has_sharp = any(r["book"] in SHARP_BOOKS and r["fair"] is not None for r in rows)
        if not (has_sharp and source != "consensus") and two_way < min_books:
            continue

        price_table = [
            {"book": r["book"],
             "over": int(r["over"]) if is_price(r["over"]) else None,
             "under": int(r["under"]) if is_price(r["under"]) else None}
            for r in sorted(rows, key=lambda x: x["book"])
        ]

        for r in bettable:
            fair = _fair_over(rows, r["book"], source, min_books)
            if fair is None:
                continue
            for side in ("over", "under"):
                price = r[side]
                if not is_price(price):
                    continue
                p = fair["p"] if side == "over" else 1.0 - fair["p"]
                ev = ev_per_unit(p, price)
                if ev * 100 < min_edge:
                    continue
                # Where the rest of the market sits on this side, for the
                # "-118 vs. median -135" comparison.
                peers = [x[side] for x in bettable if x["book"] != r["book"] and is_price(x[side])]
                med = median_price(peers) if peers else None
                raw = r["raw"]
                # Alt ladders are priced on their own, slower tier.
                fetched = _txt(raw.get("fetched_at"))
                if "_alternate" in mkt and _txt(raw.get("alt_fetched_at")):
                    fetched = _txt(raw.get("alt_fetched_at"))
                out.append({
                    "event_id": event_id,
                    "player": player_name,
                    "market": mkt,
                    "line": line,
                    "side": side,
                    "book": r["book"],
                    "price": int(price),
                    "implied_pct": round(implied_prob(price) * 100, 1),
                    "fair_pct": round(p * 100, 1),
                    "fair_price": prob_to_american(p),
                    "ev_pct": round(ev * 100, 1),
                    "source": fair["source"],
                    "consensus_books": fair["books"],
                    "sharp_ref": fair["ref"],
                    "median_price": med,
                    "gap_pp": (round((implied_prob(med) - implied_prob(price)) * 100, 1)
                               if med is not None else None),
                    "suspicious": ev >= SUSPICIOUS_EV,
                    "prices": price_table,
                    "price_since": since.get((event_id, player_name, mkt, line, r["book"])),
                    "commence_time": _txt(raw.get("commence_time")),
                    "home_team": _txt(raw.get("home_team")),
                    "away_team": _txt(raw.get("away_team")),
                    "fetched_at": fetched,
                })

    return best_book_only(out)


def best_book_only(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One row per bet (prop line + side): the book with the highest EV.
    Other books that also clear the bar are listed in `other_books` so the
    card can say "also +EV at ..." -- every book's price is still in
    `prices` for the expanded view."""
    best: Dict[tuple, Dict[str, Any]] = {}
    others: Dict[tuple, List[Dict[str, Any]]] = {}
    for r in rows:
        key = (r["event_id"], r["player"], r["market"], r["line"], r["side"])
        cur = best.get(key)
        if cur is None or (r["ev_pct"], r["price"]) > (cur["ev_pct"], cur["price"]):
            if cur is not None:
                others.setdefault(key, []).append(cur)
            best[key] = r
        else:
            others.setdefault(key, []).append(r)
    out = []
    for key, r in best.items():
        alt = sorted(others.get(key, []), key=lambda x: x["ev_pct"], reverse=True)
        out.append({**r, "other_books": [
            {"book": a["book"], "price": a["price"], "ev_pct": a["ev_pct"]} for a in alt]})
    out.sort(key=lambda x: x["ev_pct"], reverse=True)
    return out
