"""Pure market math shared by the web app and the GitHub Actions scripts.

No loader, no settings, no network -- only pandas and the odds helpers -- so
build_flagged_plays.py can run it on a bare runner with the same results the
EV Finder shows. app/data/ev.py wraps compute_ev() with the live data;
app/bets/grading.py and build_flagged_plays.py share closing_for().

See app/data/ev.py's docstring for the EV method.
"""

from __future__ import annotations

import unicodedata
from typing import Any, Dict, List, Optional

import pandas as pd

try:  # imported as part of the app
    from app.odds_math import (
        devig_two_way, ev_per_unit, implied_prob, is_price, median,
        median_price, prob_to_american, to_decimal,
    )
    from app.props_config import NO_SINGLE_BET_BOOKS, SHARP_BOOKS, UNBETTABLE_BOOKS
except ImportError:  # run as a plain script with backend/app on sys.path
    from odds_math import (  # type: ignore
        devig_two_way, ev_per_unit, implied_prob, is_price, median,
        median_price, prob_to_american, to_decimal,
    )
    from props_config import NO_SINGLE_BET_BOOKS, SHARP_BOOKS, UNBETTABLE_BOOKS  # type: ignore

# An edge this large on a two-way prop is far more often a stale or
# mis-posted price than free money. Still shown, but labelled.
SUSPICIOUS_EV = 0.25


def is_live(commence_time: pd.Series) -> pd.Series:
    """True where the game has started (same rule as app/data/props.py)."""
    started = pd.to_datetime(commence_time, utc=True, errors="coerce")
    return started.notna() & (started <= pd.Timestamp.now(tz="UTC"))


def name_key(name: Any) -> str:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower().replace(".", "").replace("'", "")
    return " ".join(p for p in s.split() if p not in {"jr", "sr", "ii", "iii", "iv", "v"})


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


def compute_ev(
    df: pd.DataFrame,
    since: Optional[Dict[tuple, str]] = None,
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
    if df is None or df.empty or "Player" not in df.columns:
        return []

    df = df.copy()
    df["bookmakers"] = df["bookmakers"].astype(str).str.lower()
    df = df[~df["bookmakers"].isin(UNBETTABLE_BOOKS) & ~df["bookmakers"].isin(NO_SINGLE_BET_BOOKS)]
    if "commence_time" in df.columns:
        df = df[~is_live(df["commence_time"])]
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

    since = since or {}
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
                    # Bet-slip deep link for this book and side, when the
                    # book provides one (get_props.py includeLinks).
                    "link": _txt(raw.get("Over Link" if side == "over" else "Under Link")),
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


# ── closing line value ────────────────────────────────────────────────────

def closing_for(bet: Dict[str, Any], closes: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Closing price at the bet's book and the fair closing chance of the
    bet's side. Pure; `closes` is a closing-lines frame for the sport."""
    if closes.empty:
        return None
    base = str(bet["market"]).replace("_alternate", "")
    c = closes[(closes["event_id"].astype(str) == str(bet.get("event_id")))
               & closes["market"].astype(str).isin([base, f"{base}_alternate"])
               & (closes["Player"].map(name_key) == name_key(bet["player"]))]
    line = bet.get("line")
    if line is None:
        c = c[c["Line"].isna()]
    else:
        c = c[pd.to_numeric(c["Line"], errors="coerce").sub(float(line)).abs() < 1e-9]
    if c.empty:
        return None

    over_fair: Optional[float] = None
    sharp = c[c["bookmakers"].astype(str).str.lower() == "pinnacle"]
    for o, u in zip(sharp["Over Price"], sharp["Under Price"]):
        over_fair = devig_two_way(o, u)
        if over_fair is not None:
            break
    if over_fair is None:
        fair = [devig_two_way(o, u) for o, u in zip(c["Over Price"], c["Under Price"])]
        fair = [p for p in fair if p is not None]
        over_fair = median(fair) if fair else None

    col = "Over Price" if bet["side"] == "over" else "Under Price"
    at_book = c[c["bookmakers"].astype(str).str.lower() == str(bet["book"]).lower()]
    close_price = next((int(p) for p in at_book[col] if is_price(p)), None)

    if over_fair is not None:
        side_fair = over_fair if bet["side"] == "over" else 1 - over_fair
    elif close_price is not None:
        # One-sided market (e.g. anytime TD): the book's own close, vig and
        # all -- a conservative stand-in, since the vig works against you.
        side_fair = implied_prob(close_price)
    else:
        return None
    return {"close_price": close_price, "close_fair_pct": round(side_fair * 100, 2),
            "clv_pct": round((to_decimal(bet["price"]) * side_fair - 1) * 100, 2)}
