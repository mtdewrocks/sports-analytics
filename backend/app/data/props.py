"""Props and middles, shared by MLB and NFL.

get_props.py writes the identical long-format schema for both sports, so the
pivot and the middles reader are one implementation each rather than two that
drift. `app/data/mlb.py::get_mlb_props` stays as the MLB entry point and now
delegates here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from app.data.loader import get_middles_data, get_props_data
from app.props_config import UNBETTABLE_BOOKS

# Only the books you can't bet at. Deliberately NOT the middles screen's list:
# that one also drops prizepicks and pick6, which belong on this grid -- their
# lines are often the softest available. They just can't be PAIRED, because a
# single leg isn't placeable at the quoted price.
EXCLUDED_BOOKS = UNBETTABLE_BOOKS


def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def _normalize(name: str) -> str:
    return str(name).lower().strip()


def get_props(
    sport: str,
    team: Optional[str] = None,
    player: Optional[str] = None,
    market: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Props pivoted wide: one row per player/line/market, sportsbooks as columns."""
    df = get_props_data(sport)
    if df.empty:
        return []

    df = df.copy()
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    player_col = _find_col(df, ["player", "player_name", "name"])
    market_col = _find_col(df, ["market", "prop_type", "stat"])
    book_col = _find_col(df, ["bookmakers", "bookmaker", "sportsbook"])
    price_col = _find_col(df, ["over_price", "price", "over"])
    line_col = _find_col(df, ["line", "line_value"])
    if not (book_col and price_col and player_col):
        return []

    df = df[~df[book_col].astype(str).str.lower().isin(EXCLUDED_BOOKS)]
    if player and player_col:
        df = df[df[player_col].astype(str).str.lower().str.strip() == _normalize(player)]
    if market and market_col:
        df = df[df[market_col].astype(str).str.lower().str.strip() == _normalize(market)]
    if team:
        for c in ("home_team", "away_team"):
            if c not in df.columns:
                break
        else:
            t = _normalize(team)
            df = df[(df["home_team"].astype(str).str.lower() == t)
                    | (df["away_team"].astype(str).str.lower() == t)]
    if df.empty:
        return []

    idx = [c for c in [player_col, line_col, market_col] if c]
    # Carried through the pivot so the page can say how stale what's on screen
    # actually is. A tiered refresh means the FILE can be minutes old while the
    # game you're looking at was last priced six hours ago -- reporting the
    # file's age would be quietly wrong in exactly the cases that matter.
    meta_cols = [c for c in ("fetched_at", "commence_time", "home_team", "away_team")
                 if c in df.columns]
    try:
        pivot = df.pivot_table(index=idx, columns=book_col, values=price_col,
                               aggfunc="first").reset_index()
        pivot.columns.name = None
    except Exception as e:
        print(f"Warning: {sport} props pivot failed: {e}")
        return []

    if meta_cols:
        meta = df.groupby(idx, as_index=False)[meta_cols].max()
        pivot = pivot.merge(meta, on=idx, how="left")

    pivot["line_id"] = pivot[player_col].astype(str)
    if line_col and line_col in pivot.columns:
        pivot["line_id"] += " " + pivot[line_col].astype(str)
    if market_col and market_col in pivot.columns:
        pivot["line_id"] += " " + pivot[market_col].astype(str)

    lead = ["line_id"] + [c for c in idx if c in pivot.columns] + meta_cols
    books = [c for c in pivot.columns if c not in lead]
    return pivot[lead + books].fillna("").to_dict(orient="records")


def get_middles(
    sport: str,
    kind: Optional[str] = None,
    player: Optional[str] = None,
    market: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Middles and arbs from build_prop_middles.py, already priced and ranked."""
    df = get_middles_data(sport)
    if df.empty:
        return []

    df = df.copy()
    if kind:
        df = df[df["kind"].astype(str).str.lower() == _normalize(kind)]
    if player and "Player" in df.columns:
        df = df[df["Player"].astype(str).str.lower().str.strip() == _normalize(player)]
    if market and "market" in df.columns:
        df = df[df["market"].astype(str).str.lower().str.strip() == _normalize(market)]

    return df.fillna("").to_dict(orient="records")
