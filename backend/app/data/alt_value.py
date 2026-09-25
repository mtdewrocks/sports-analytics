"""Alt-Line Value: which rung of a player's alt ladder is the best bet.

Built on the Hit Rate Sheet, which already grades every priced line --
standard and alternate -- against the player's game log. This groups those
rows into one ladder per (player, market) and, for each rung, compares how
often the player has cleared it with what the best available price implies.

HOW A RUNG IS SCORED
--------------------
1. Best price: the highest Over price across real sportsbooks. Pick'em apps
   are left out -- their "price" isn't a bet you can place on its own.
2. Hit rate: the season rate blended with the recent-window rate
   (RECENT_WEIGHT), so form counts without letting a ten-game streak run
   the show. The SAMPLE SIZE
   is the season game count only -- recent games are already inside it, and
   counting them twice would overstate how much evidence there is.
3. Shrinkage: that hit rate is pulled toward the market's own view (the
   median implied probability across books for that rung). The prior is
   worth PRIOR_GAMES games, or more for rare outcomes: it always carries at
   least PRIOR_EXPECTED_HITS expected hits, so a rung the market prices at
   1% needs hundreds of games of evidence to move far -- one lucky 3-hit
   night in 84 games does not make a +2500 rung a bet. A 3-for-4 run on a +300 rung reads as a modest edge,
   not a 75% lock. This is deliberately conservative: the prior still carries
   the vig, so a rung has to beat the market by a real margin to show up.
4. EV = p x payout - (1 - p), per unit staked.

A ladder needs at least MIN_GAMES[sport] games of history before any rung
is flagged. Early in a season (NFL week 2 = two games) nothing qualifies,
which is correct: two games say almost nothing about a 79.5-yard rung.

Rungs priced above MAX_FLAG_PRICE are shown but never flagged.
Long shots need more: a rung priced above LONGSHOT_PRICE is only flagged if
the season sample is at least LONGSHOT_MIN_GAMES and its EV clears twice the
normal bar. Small samples on long odds are exactly where hit rates lie.

Over-only, like the Hit Rate Sheet itself: alt ladders are posted as Over
rungs. Yes/No markets (anytime TD, to record a win) aren't ladders and are
skipped.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from app.odds_math import ev_per_unit, implied_prob, is_price, median, shrink_toward
from app.props_config import NO_SINGLE_BET_BOOKS

PRIOR_GAMES = 15.0
PRIOR_EXPECTED_HITS = 3.0
RECENT_WEIGHT = 0.2
MAX_FLAG_PRICE = 600
MIN_GAMES = {"mlb": 10, "nfl": 4}
DEFAULT_MIN_GAMES = 6
LONGSHOT_PRICE = 300
LONGSHOT_MIN_GAMES = 10


def _sample(s: Any) -> Tuple[int, int]:
    """'11/20' -> (11, 20). Anything unparseable -> (0, 0)."""
    try:
        h, n = str(s).split("/")
        return int(h), int(n)
    except (ValueError, AttributeError):
        return 0, 0


def score_rung(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """One Hit Rate Sheet row -> a scored rung, or None if it has no
    bettable price."""
    offers = {b: o for b, o in (row.get("odds_by_book") or {}).items()
              if b.lower() not in NO_SINGLE_BET_BOOKS and is_price(o)}
    if not offers:
        return None
    best_book, best_price = max(offers.items(), key=lambda kv: kv[1])
    market_p = median([implied_prob(o) for o in offers.values()])

    s_hits, s_n = _sample(row.get("season_sample"))
    r_hits, r_n = _sample(row.get("recent_sample"))
    if s_n == 0:
        return None
    rate = s_hits / s_n
    if r_n:
        rate = (1 - RECENT_WEIGHT) * rate + RECENT_WEIGHT * (r_hits / r_n)
    prior_n = max(PRIOR_GAMES, PRIOR_EXPECTED_HITS / market_p) if market_p > 0 else PRIOR_GAMES
    model_p = shrink_toward(rate * s_n, s_n, market_p, prior_n)
    ev = ev_per_unit(model_p, best_price)
    imp = implied_prob(best_price)

    return {
        "line": row.get("line"),
        "best_price": int(best_price),
        "best_book": best_book,
        "book_count": len(offers),
        "implied_pct": round(imp * 100, 1),
        "season_pct": row.get("season_pct"),
        "season_sample": row.get("season_sample"),
        "recent_pct": row.get("recent_pct"),
        "recent_sample": row.get("recent_sample"),
        "model_pct": round(model_p * 100, 1),
        "edge_pp": round((model_p - imp) * 100, 1),
        "ev_pct": round(ev * 100, 1),
        "_season_n": s_n,
    }


def _qualifies(rung: Dict[str, Any], min_ev: float, min_games: int) -> bool:
    if rung["_season_n"] < min_games or rung["best_price"] > MAX_FLAG_PRICE:
        return False
    if rung["best_price"] > LONGSHOT_PRICE:
        return rung["_season_n"] >= LONGSHOT_MIN_GAMES and rung["ev_pct"] >= 2 * min_ev
    return rung["ev_pct"] >= min_ev


def build_ladders(rows: List[Dict[str, Any]], min_ev: float = 3.0, min_rungs: int = 2,
                  flagged_only: bool = True, min_games: int = DEFAULT_MIN_GAMES) -> List[Dict[str, Any]]:
    """Group Hit Rate Sheet rows into ladders and pick each ladder's best
    rung. Pure function of its input, so it's tested directly."""
    ladders: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        if row.get("is_live") or isinstance(row.get("line"), str):
            continue
        rung = score_rung(row)
        if rung is None:
            continue
        key = (str(row.get("player")), str(row.get("market")))
        lad = ladders.setdefault(key, {
            "player": row.get("player"),
            "team": row.get("team"),
            "opponent": row.get("opponent"),
            "market": row.get("market"),
            "commence_time": row.get("commence_time"),
            "fetched_at": row.get("fetched_at"),
            "rungs": [],
        })
        if row.get("fetched_at") and str(row.get("fetched_at")) > str(lad["fetched_at"] or ""):
            lad["fetched_at"] = row.get("fetched_at")
        lad["rungs"].append(rung)

    out = []
    for lad in ladders.values():
        # One rung per line: the standard market and its alt ladder can
        # both quote the same number (the sheet already de-dupes most of
        # these); keep the better price.
        by_line: Dict[float, Dict[str, Any]] = {}
        for r in lad["rungs"]:
            cur = by_line.get(r["line"])
            if cur is None or r["best_price"] > cur["best_price"]:
                by_line[r["line"]] = r
        rungs = sorted(by_line.values(), key=lambda r: r["line"])
        if len(rungs) < min_rungs:
            continue
        for r in rungs:
            r["flagged"] = _qualifies(r, min_ev, min_games)
        candidates = [r for r in rungs if r["flagged"]]
        best = max(candidates, key=lambda r: r["ev_pct"]) if candidates else None
        if flagged_only and best is None:
            continue
        lad["games"] = max(r["_season_n"] for r in rungs)
        lad["enough_games"] = lad["games"] >= min_games
        for r in rungs:
            r["is_best"] = best is not None and r is best
            r.pop("_season_n", None)
        lad["rungs"] = rungs
        lad["best_line"] = best["line"] if best else None
        lad["best_ev_pct"] = best["ev_pct"] if best else None
        out.append(lad)

    out.sort(key=lambda l: (l["best_ev_pct"] is not None, l["best_ev_pct"] or 0), reverse=True)
    return out


def get_alt_value(sport: str, sheet_fn: Callable[..., List[Dict[str, Any]]],
                  market: Optional[str] = None, player: Optional[str] = None,
                  min_ev: float = 3.0, flagged_only: bool = True) -> List[Dict[str, Any]]:
    """`sheet_fn` is get_mlb_hit_rate_sheet or get_nfl_hit_rate_sheet."""
    rows = sheet_fn(market=market, min_pct=0, min_odds=None, period="season",
                    player=player, books=None)
    return build_ladders(rows, min_ev=min_ev, flagged_only=flagged_only,
                         min_games=MIN_GAMES.get(sport, DEFAULT_MIN_GAMES))
