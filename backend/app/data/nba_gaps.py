"""NBA Gap Bets: anti-middles priced against each player's own box scores.

An anti-middle is an Over on the HIGHER line at one book and an Under on the
LOWER line at another (Under 21.5 at +115, Over 22.5 at +110). Exactly one leg
wins on every result except the gap (22 here), where both lose.
build_prop_middles.py already finds and prices these and reports the
break-even: the most often the result can land in the gap before the pair
loses money. What it can't know is how often it actually DOES land there.

That's what this adds. For each pair, the player's last LOOKBACK games
(across last season and this one) give a landing rate for the gap, and from
that an estimated return:

    EV = (1 - p) x one_wins  +  p x (-100%)

Measured on 2025-26 box scores, a one-number gap at a player's average gets
hit ~6% of the time for points, ~4% for PRA, ~12% rebounds, ~14% assists and
~23% threes -- so the same +110/+110 pair is close to fair on points and a
clear loser on threes. Small samples are noisy, so rates on fewer than
MIN_GAMES games are left blank rather than guessed, and the rate shown is a
historical frequency, not a projection.
"""
from __future__ import annotations

import math
import unicodedata
from typing import Any, Dict, List, Optional

import pandas as pd

from app.data.loader import get_middles_data, get_nba_all_seasons

LOOKBACK = 30
MIN_GAMES = 10

# props market (after get_props.py strips "player_" and the middles builder
# folds "_alternate") -> box-score column(s) in nba_player_stats.parquet
MARKET_STATS = {
    "points": ["pts"],
    "rebounds": ["reb"],
    "assists": ["ast"],
    "threes": ["3pm"],
    "blocks": ["blk"],
    "steals": ["stl"],
    "turnovers": ["tov"],
    "blocks_steals": ["blk", "stl"],
    "points_rebounds_assists": ["pts", "reb", "ast"],
    "points_rebounds": ["pts", "reb"],
    "rebounds_assists": ["reb", "ast"],
    "points_assists": ["pts", "ast"],
}

MARKET_LABELS = {
    "points": "Points", "rebounds": "Rebounds", "assists": "Assists",
    "threes": "Threes made", "blocks": "Blocks", "steals": "Steals",
    "turnovers": "Turnovers", "blocks_steals": "Blocks + steals",
    "points_rebounds_assists": "Points + rebounds + assists",
    "points_rebounds": "Points + rebounds", "rebounds_assists": "Rebounds + assists",
    "points_assists": "Points + assists",
}


def name_key(name: str) -> str:
    """'Nikola Jokić' == 'Nikola Jokic', 'Jaren Jackson Jr.' == 'Jaren Jackson Jr'."""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.lower().replace(".", "").replace("'", "").split())


def gap_bounds(over_line: float, under_line: float) -> Optional[tuple]:
    """Integer results where both legs of an anti-middle lose -- the same
    span build_prop_middles.anti_middle_window() reports (ceil(under) to
    floor(over)), so a whole-number line's push counts as a loss here,
    which is the conservative reading."""
    lo, hi = math.ceil(under_line), math.floor(over_line)
    return (lo, hi) if hi >= lo else None


def _recent_values(stats: pd.DataFrame) -> Dict[tuple, List[float]]:
    """(name key, market) -> that player's last LOOKBACK results, newest last."""
    if stats.empty or "player" not in stats.columns:
        return {}
    df = stats.copy()
    if "played" in df.columns:
        df = df[pd.to_numeric(df["played"], errors="coerce") == 1]
    date_col = "date" if "date" in df.columns else "game_date"
    df["_d"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.sort_values("_d")
    df["_k"] = df["player"].map(name_key)
    recent = df.groupby("_k", sort=False).tail(LOOKBACK)
    out: Dict[tuple, List[float]] = {}
    for market, cols in MARKET_STATS.items():
        if not all(c in recent.columns for c in cols):
            continue
        vals = recent[cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
        for k, v in pd.DataFrame({"k": recent["_k"], "v": vals}).groupby("k", sort=False)["v"]:
            out[(k, market)] = v.tolist()
    return out


def _team_by_player(stats: pd.DataFrame) -> Dict[str, str]:
    if stats.empty or "team" not in stats.columns:
        return {}
    date_col = "date" if "date" in stats.columns else "game_date"
    last = stats.assign(_d=pd.to_datetime(stats[date_col], errors="coerce")).sort_values("_d")
    last = last.groupby(last["player"].map(name_key)).tail(1)
    return dict(zip(last["player"].map(name_key), last["team"]))


def _is_started(commence: Any) -> bool:
    ts = pd.to_datetime(commence, utc=True, errors="coerce")
    return bool(pd.notna(ts) and ts <= pd.Timestamp.now(tz="UTC"))


def get_gap_bets(include_negative: bool = False, market: Optional[str] = None) -> Dict[str, Any]:
    pairs = get_middles_data("nba")
    empty = {"lines_as_of": None, "oldest_line": None, "lookback": LOOKBACK, "rows": []}
    if pairs is None or pairs.empty or "kind" not in pairs.columns:
        return empty
    pairs = pairs[pairs["kind"] == "anti_middle"].copy()
    if "commence_time" in pairs.columns:
        pairs = pairs[~pairs["commence_time"].map(_is_started)]
    if market:
        pairs = pairs[pairs["market"] == market]
    if pairs.empty:
        return empty

    stats = get_nba_all_seasons()
    history = _recent_values(stats)
    teams = _team_by_player(stats)

    rows = []
    for r in pairs.to_dict("records"):
        bounds = gap_bounds(float(r["over_line"]), float(r["under_line"]))
        if not bounds:
            continue
        lo, hi = bounds
        key = name_key(r["Player"])
        vals = history.get((key, r["market"]), [])
        n = len(vals)
        rate = (sum(1 for v in vals if lo <= v <= hi) / n) if n >= MIN_GAMES else None
        one_wins = float(r["one_wins_pct"]) / 100.0          # return when exactly one leg wins
        ev = ((1 - rate) * one_wins - rate) if rate is not None else None
        avg = (sum(vals) / n) if n else None
        rows.append({
            "player": r["Player"],
            "team": teams.get(key),
            "market": r["market"],
            "market_label": MARKET_LABELS.get(r["market"], r["market"].replace("_", " ").title()),
            "game": f"{r.get('away_team') or ''} @ {r.get('home_team') or ''}".strip(" @"),
            "commence_time": r.get("commence_time"),
            "under_book": r["under_book"], "under_line": float(r["under_line"]),
            "under_price": float(r["under_price"]),
            "over_book": r["over_book"], "over_line": float(r["over_line"]),
            "over_price": float(r["over_price"]),
            "gap": str(lo) if lo == hi else f"{lo}-{hi}",
            "gap_width": hi - lo + 1,
            "stake_over_pct": float(r["stake_over_pct"]),
            "win_pct": round(100 * one_wins, 2),               # profit on total stake when one leg wins
            "breakeven_pct": float(r["breakeven_window_rate_pct"]),
            "games": n,
            "avg": round(avg, 1) if avg is not None else None,
            "landing_pct": round(100 * rate, 1) if rate is not None else None,
            "ev_pct": round(100 * ev, 2) if ev is not None else None,
            "dfs_leg": r.get("dfs_leg") or "",
            "fetched_at": r.get("fetched_at"),
        })

    if not include_negative:
        rows = [x for x in rows if x["ev_pct"] is None or x["ev_pct"] > 0]
    # Priced rows by estimated return; un-priced (too little history) last.
    rows.sort(key=lambda x: (x["ev_pct"] is None, -(x["ev_pct"] or 0), -x["win_pct"]))
    stamps = sorted(str(x["fetched_at"]) for x in rows if x.get("fetched_at"))
    return {
        "lines_as_of": stamps[-1] if stamps else None,
        "oldest_line": stamps[0] if stamps else None,
        "lookback": LOOKBACK,
        "rows": rows,
    }
