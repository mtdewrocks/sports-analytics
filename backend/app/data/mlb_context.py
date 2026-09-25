"""Today's-matchup context for MLB Alt-Line Value ladders.

The ladder's "our chance" comes from the player's own game log, which knows
nothing about TODAY: who's pitching, which lineup he faces, where he bats.
This adds that context -- as information and a simple verdict, not as a
change to the number -- from daily_matchups.parquet (build_matchups.py),
the same file the Matchup Edge and Pitcher Daily Report pages read.

Verdicts are for the OVER, since every ladder rung is an Over:
  favorable   today's matchup points toward more of this stat than usual
  tough       it points toward less
  neutral     nothing stands out
  None        not enough to say (lineup not posted, market has no signal)

Thresholds are deliberately modest -- a verdict is a nudge to look closer,
not a projection.
"""

from __future__ import annotations

import unicodedata
from typing import Any, Dict, List, Optional

import pandas as pd

from app.data.loader import get_mlb_data, ttl_cache, MLB_TTL
from app.data.mlb import _matchup_edge_league_benchmarks, _matchup_edge_resolved_hand

# Batter markets graded on run production (wOBA), and the one graded on K%.
_BATTER_WOBA_MARKETS = {
    "batter_hits", "batter_total_bases", "batter_home_runs", "batter_rbis",
    "batter_runs_scored", "batter_hits_runs_rbis", "batter_singles", "batter_doubles",
}
_BATTER_K_MARKETS = {"batter_strikeouts"}

WOBA_EDGE = 0.020      # combined wOBA gap vs league (20 points) for a verdict
K_EDGE = 2.0           # K% points vs league for a verdict
GAME_WINDOW_HOURS = 4  # a matchup row counts only if its game is the prop's game


def _key(name: Any) -> str:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.lower().replace(".", "").split())


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 11 <= n % 100 <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _same_game(row_time: Any, prop_time: Any) -> bool:
    a = pd.to_datetime(row_time, utc=True, errors="coerce")
    b = pd.to_datetime(prop_time, utc=True, errors="coerce")
    if pd.isna(a) or pd.isna(b):
        return False
    return abs((a - b).total_seconds()) <= GAME_WINDOW_HOURS * 3600


def _w(x: float) -> str:
    """wOBA the way it's usually written: .342, not 0.342."""
    return f"{x:.3f}".lstrip("0")


def _verdict(gap: Optional[float], edge: float) -> Optional[str]:
    if gap is None:
        return None
    if gap >= edge:
        return "favorable"
    if gap <= -edge:
        return "tough"
    return "neutral"


@ttl_cache(MLB_TTL)
def _tables() -> Dict[str, Any]:
    data = get_mlb_data()
    m = data.get("matchups", pd.DataFrame())
    bench = _matchup_edge_league_benchmarks(data.get("pitcher_splits", pd.DataFrame()))
    if m.empty:
        return {"by_batter": {}, "by_pitcher": {}, "bench": bench}
    m = m.copy()
    m["_bkey"] = m["player"].map(_key)
    m["_pkey"] = m["pitcher"].map(_key)
    return {
        "by_batter": {k: g for k, g in m.groupby("_bkey")},
        "by_pitcher": {k: g for k, g in m.groupby("_pkey")},
        "bench": bench,
    }


def _league(bench: Dict[str, Dict[str, Optional[float]]], stat: str, hand: Optional[str]) -> Optional[float]:
    vals = bench.get(stat, {})
    if hand in ("L", "R") and vals.get(hand) is not None:
        return vals[hand]
    both = [v for v in vals.values() if v is not None]
    return sum(both) / len(both) if both else None


def _batter_context(market: str, rows: pd.DataFrame, bench) -> Dict[str, Any]:
    r = rows.iloc[0]
    hand = _matchup_edge_resolved_hand(r.get("bats"), r.get("throws"))
    order = _num(r.get("batting_order"))
    ctx: Dict[str, Any] = {
        "kind": "batter",
        "pitcher": r.get("pitcher"),
        "throws": r.get("throws"),
        "batting_order": int(order) if order else None,
        "facts": [],
        "verdict": None,
    }
    facts: List[str] = []
    if order:
        facts.append(f"Batting {_ordinal(int(order))}")

    if market in _BATTER_K_MARKETS:
        lk = _league(bench, "k", hand)
        bk, pk = _num(r.get("split_k_pct")), _num(r.get("p_split_k_pct"))
        if bk is not None:
            facts.append(f"Strikes out {bk:.0f}% vs {r.get('throws')}HP")
        if pk is not None:
            facts.append(f"{r.get('pitcher')} K rate vs his side: {pk:.0f}%"
                         + (f" (league {lk:.0f}%)" if lk is not None else ""))
        if lk is not None and bk is not None and pk is not None:
            ctx["verdict"] = _verdict(0.5 * (bk - lk) + 0.5 * (pk - lk), K_EDGE)
    elif market in _BATTER_WOBA_MARKETS:
        lw = _league(bench, "woba", hand)
        bw, pw = _num(r.get("split_woba")), _num(r.get("p_split_woba"))
        if bw is not None:
            facts.append(f"His wOBA vs {r.get('throws')}HP: {_w(bw)}")
        if pw is not None:
            facts.append(f"{r.get('pitcher')} allows {_w(pw)} to his side"
                         + (f" (league {_w(lw)})" if lw is not None else ""))
        if lw is not None and bw is not None and pw is not None:
            ctx["verdict"] = _verdict(0.5 * (bw - lw) + 0.5 * (pw - lw), WOBA_EDGE)
    ctx["facts"] = facts
    return ctx


def _pitcher_context(market: str, rows: pd.DataFrame, bench) -> Dict[str, Any]:
    """`rows` = the opposing lineup, one row per hitter, each already split
    against this pitcher's throwing hand."""
    throws = rows.iloc[0].get("throws")
    k = pd.to_numeric(rows["split_k_pct"], errors="coerce").dropna()
    w = pd.to_numeric(rows["split_woba"], errors="coerce").dropna()
    lk = _league(bench, "k", None)
    lw = _league(bench, "woba", None)
    own_k = _num(rows.iloc[0].get("p_all_k_pct"))
    ctx: Dict[str, Any] = {
        "kind": "pitcher", "opponent": rows.iloc[0].get("team"), "throws": throws,
        "facts": [], "verdict": None,
    }
    facts: List[str] = []
    lineup_k = float(k.mean()) if not k.empty else None
    lineup_w = float(w.mean()) if not w.empty else None
    if lineup_k is not None:
        facts.append(f"Opposing lineup strikes out {lineup_k:.1f}% vs {throws}HP"
                     + (f" (league {lk:.1f}%)" if lk is not None else ""))
    if lineup_w is not None:
        facts.append(f"Lineup wOBA vs {throws}HP: {_w(lineup_w)}"
                     + (f" (league {_w(lw)})" if lw is not None else ""))
    if own_k is not None:
        facts.append(f"His season K rate: {own_k:.1f}%")
    ctx["facts"] = facts

    if market == "pitcher_strikeouts" and lineup_k is not None and lk is not None:
        ctx["verdict"] = _verdict(lineup_k - lk, K_EDGE)
    elif market in ("pitcher_hits_allowed", "pitcher_earned_runs") and lineup_w is not None and lw is not None:
        ctx["verdict"] = _verdict(lineup_w - lw, WOBA_EDGE)
    elif market == "pitcher_outs" and lineup_w is not None and lw is not None:
        # A weaker lineup means a longer outing: the Over likes a LOW wOBA.
        ctx["verdict"] = _verdict(lw - lineup_w, WOBA_EDGE)
    return ctx


def mlb_ladder_context(ladder: Dict[str, Any]) -> Dict[str, Any]:
    """Context for one ladder. Always returns a dict; `status` says whether
    today's lineup was found."""
    t = _tables()
    market = str(ladder.get("market", ""))
    key = _key(ladder.get("player"))
    when = ladder.get("commence_time")

    if market.startswith("pitcher_"):
        rows = t["by_pitcher"].get(key)
    else:
        rows = t["by_batter"].get(key)
    if rows is not None:
        rows = rows[rows["game_time_utc"].map(lambda x: _same_game(x, when))]
    if rows is None or rows.empty:
        return {"status": "no_lineup", "verdict": None, "facts": []}

    ctx = (_pitcher_context(market, rows, t["bench"]) if market.startswith("pitcher_")
           else _batter_context(market, rows, t["bench"]))
    ctx["status"] = "ok"
    return ctx
