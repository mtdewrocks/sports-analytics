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
from app.props_config import NO_SINGLE_BET_BOOKS, SHARP_BOOKS, UNBETTABLE_BOOKS

# Only the books you can't bet at. Deliberately NOT the middles screen's list:
# that one also drops prizepicks and pick6, which belong on this grid -- their
# lines are often the softest available. They just can't be PAIRED, because a
# single leg isn't placeable at the quoted price.
# SHARP_BOOKS too: Pinnacle is pulled only as the EV Finder's reference
# price and can't be bet from the US, so it must never read as a column you
# can shop, or win a "best price" anywhere downstream (Hit Rate Sheet,
# pitcher props card) -- all of which read through this list.
EXCLUDED_BOOKS = UNBETTABLE_BOOKS | SHARP_BOOKS


def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    return None


def _normalize(name: str) -> str:
    return str(name).lower().strip()


def _is_live_series(commence_time: pd.Series) -> pd.Series:
    """A game is "live" once its commence_time has passed -- at that point
    the book has stopped taking these lines, so whatever's still in the file
    is a frozen snapshot from just before kickoff, not a current price.

    Computed fresh against wall-clock time on every call, not stored in the
    parquet -- a boolean baked in at write time would be wrong the moment
    real time moved past it. get_props.py's RETENTION note covers why a
    started game's rows stick around in the file at all (~6h by default)
    instead of disappearing the instant kickoff passes; this is the "is it
    actually live right now" read of those rows once they're here. A
    missing/unparseable commence_time reads as NOT live (nothing to hide it
    for) rather than raising.
    """
    started = pd.to_datetime(commence_time, utc=True, errors="coerce")
    return started.notna() & (started <= pd.Timestamp.now(tz="UTC"))


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
        # Was `df.groupby(idx, as_index=False)[meta_cols].max()` -- correct,
        # but measured at 2-4s on a real props file (24k+ MLB rows, 27k+ NFL
        # rows) and the single biggest cost in every page that calls
        # get_props(), including a cold Hit Rate Sheet load. The cause is
        # pandas/pyarrow falling back to a slow pure-Python per-group
        # reduction for .max() on these Arrow-string-backed columns (see
        # pandas' groupby/ops.py:_agg_py_fallback) -- it is NOT the row
        # count itself, which a market/player filter wouldn't meaningfully
        # reduce (that filtering already happens above, before this line).
        #
        # These meta columns are effectively constant within a
        # (player, line, market) group EXCEPT fetched_at, where "latest
        # among however many books quoted this line" is the actual intent
        # (see the comment above meta_cols). Sorting by fetched_at and
        # keeping each group's LAST row after the sort reproduces
        # groupby(...).max() exactly for a sortable string timestamp --
        # verified row-for-row against the old .max() output on a live
        # props pull, same row count, zero value mismatches across all
        # four meta columns -- while actually vectorizing instead of
        # falling back to Python, cutting this step from ~2.3s to ~0.02s.
        # dropna(subset=idx) matches groupby's own default of dropping any
        # row whose group key is NaN, so a missing player/line/market still
        # can't sneak a meta row in that the old code would have excluded.
        meta = (
            df.dropna(subset=idx)
            .sort_values("fetched_at" if "fetched_at" in df.columns else idx)
            .drop_duplicates(subset=idx, keep="last")[idx + meta_cols]
        )
        pivot = pivot.merge(meta, on=idx, how="left")

    pivot["line_id"] = pivot[player_col].astype(str)
    if line_col and line_col in pivot.columns:
        pivot["line_id"] += " " + pivot[line_col].astype(str)
    if market_col and market_col in pivot.columns:
        pivot["line_id"] += " " + pivot[market_col].astype(str)

    lead = ["line_id"] + [c for c in idx if c in pivot.columns] + meta_cols
    # So the page can mark a row "LIVE -- frozen at kickoff" instead of
    # silently showing a pre-game price as if it were current. Unlike
    # Middles & Arbs (see get_middles() below), Props is a reference/browse
    # page rather than an actionable list, so a live game stays visible here
    # -- just labelled -- rather than disappearing.
    if "commence_time" in pivot.columns:
        pivot["is_live"] = _is_live_series(pivot["commence_time"])
        lead = lead + ["is_live"]
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
    # Middles & Arbs is a list of bets you can actually place -- once a game
    # is live its lines are frozen (see get_props.py's RETENTION note and
    # _is_live_series() above), so a pair sitting on a started game isn't an
    # opportunity anymore, just a stale price. Props (get_props() above)
    # keeps showing it, marked; this page just drops it, rather than
    # surfacing something that reads as live money on the table but can't
    # actually be bet.
    if "commence_time" in df.columns:
        df = df[~_is_live_series(df["commence_time"])]
    if df.empty:
        return []
    if kind:
        df = df[df["kind"].astype(str).str.lower() == _normalize(kind)]
    if player and "Player" in df.columns:
        df = df[df["Player"].astype(str).str.lower().str.strip() == _normalize(player)]
    if market and "market" in df.columns:
        df = df[df["market"].astype(str).str.lower().str.strip() == _normalize(market)]

    return df.fillna("").to_dict(orient="records")


# ── Pitcher props card (MLB Matchup page) ───────────────────────────────────

# Main markets only. The alternate ladders are Over-only rungs running from
# 2.5 K at -2500 upward, so "lowest line" across them would always be the
# bottom rung -- a number nobody means by "best line".
PITCHER_MARKETS = [
    ("pitcher_strikeouts", "Strikeouts"),
    ("pitcher_outs", "Outs"),
    ("pitcher_hits_allowed", "Hits allowed"),
    ("pitcher_earned_runs", "Earned runs"),
    ("pitcher_walks", "Walks"),
    ("pitcher_record_a_win", "To record a win"),
]


def _name_key(name: str) -> str:
    """Accent-, case- and punctuation-insensitive, so 'José Berríos' on the
    matchup page finds 'Jose Berrios' in The Odds API feed."""
    import unicodedata
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.lower().replace(".", "").split())


def _best_side(df: pd.DataFrame, price_col: str, prefer_low_line: bool) -> Optional[Dict[str, Any]]:
    """Most favorable line first (lowest for Over, highest for Under), then
    the best price among the books at that line. Every book tied at that
    line and price is returned, so the page can say 'FanDuel +2'."""
    side = df.dropna(subset=[price_col])
    if side.empty:
        return None
    has_line = side["Line"].notna().any()
    if has_line:
        side = side.dropna(subset=["Line"])
        target = side["Line"].min() if prefer_low_line else side["Line"].max()
        side = side[side["Line"] == target]
    best = side[price_col].max()
    books = sorted(side.loc[side[price_col] == best, "bookmakers"].astype(str).unique())
    return {
        "line": float(target) if has_line else None,
        "price": int(best),
        "books": books,
    }


def get_pitcher_props(pitcher: str) -> Dict[str, Any]:
    """Best Over and Under for each main pitcher market, for the pitcher's
    next (or in-progress) game."""
    empty = {"markets": [], "commence_time": None, "is_live": False, "fetched_at": None}
    df = get_props_data("mlb")
    if df.empty or "Player" not in df.columns:
        return empty

    keys = {m for m, _ in PITCHER_MARKETS}
    df = df[df["market"].isin(keys)]
    # Pick'em apps are left out as well as the unbettable books: their
    # "price" is a notional multiplier share, not odds a single bet is paid
    # at (see NO_SINGLE_BET_BOOKS), so letting Dabble's +103 beat a real
    # book's -110 would make "best price" mean something it doesn't.
    books = df["bookmakers"].astype(str).str.lower()
    df = df[~books.isin(EXCLUDED_BOOKS) & ~books.isin(NO_SINGLE_BET_BOOKS)]
    df = df[df["Player"].map(_name_key) == _name_key(pitcher)]
    if df.empty:
        return empty

    # A pitcher can carry lines for today AND a start later in the week
    # (books post tomorrow's probables tonight), so pin one game: the
    # earliest one that hasn't been over for long. Rows for a started game
    # stay in the file ~6h (see get_props.py RETENTION); those are frozen
    # pre-game prices, flagged live rather than hidden.
    if "commence_time" in df.columns:
        start = pd.to_datetime(df["commence_time"], utc=True, errors="coerce")
        cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=5)
        upcoming = start[start >= cutoff]
        if upcoming.empty:
            return empty
        game_start = upcoming.min()
        df = df[start == game_start]
    else:
        game_start = None

    markets = []
    for key, label in PITCHER_MARKETS:
        m = df[df["market"] == key]
        if m.empty:
            continue
        # The consensus line -- what most books hang -- for context next to
        # the best-of lines, and as the number the L10 hit rate is graded at.
        lines = m["Line"].dropna()
        consensus = float(lines.mode().min()) if not lines.empty else None
        markets.append({
            "market": key,
            "label": label,
            "consensus_line": consensus,
            "book_count": int(m["bookmakers"].nunique()),
            "over": _best_side(m, "Over Price", prefer_low_line=True),
            "under": _best_side(m, "Under Price", prefer_low_line=False),
        })

    fetched = df["fetched_at"].max() if "fetched_at" in df.columns else None
    return {
        "markets": markets,
        "commence_time": game_start.isoformat() if game_start is not None else None,
        "is_live": bool(game_start is not None and game_start <= pd.Timestamp.now(tz="UTC")),
        "fetched_at": str(fetched) if fetched is not None else None,
    }


# ── Per-player price lookups (Hot Hitters, Matchup Edge) ────────────────────
#
# The same "best bettable price" rules get_pitcher_props() applies above --
# no unbettable books, no sharp reference books, no pick'em apps -- but for
# pages that need one or two specific lines for many players at once. The
# frame is filtered and name-keyed ONCE per request (bettable_props()) and
# then sliced per player, rather than re-mapping _name_key over ~13k rows
# for every card.


def bettable_props(sport: str = "mlb") -> pd.DataFrame:
    """Props rows from books a single bet can actually be placed at, with a
    `_key` column holding the accent/case/punctuation-insensitive name."""
    df = get_props_data(sport)
    if df.empty or "Player" not in df.columns or "bookmakers" not in df.columns:
        return pd.DataFrame()
    books = df["bookmakers"].astype(str).str.lower()
    df = df[~books.isin(EXCLUDED_BOOKS) & ~books.isin(NO_SINGLE_BET_BOOKS)].copy()
    df["_key"] = df["Player"].map(_name_key)
    return df


def _pin_next_game(df: pd.DataFrame) -> "tuple[pd.DataFrame, Optional[pd.Timestamp]]":
    """Same rule as get_pitcher_props(): the earliest game that hasn't been
    over for long, so tomorrow's early-posted lines never stand in for
    today's, and a game in progress still shows its frozen pre-game price."""
    if df.empty or "commence_time" not in df.columns:
        return df, None
    start = pd.to_datetime(df["commence_time"], utc=True, errors="coerce")
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=5)
    upcoming = start[start >= cutoff]
    if upcoming.empty:
        return df.iloc[0:0], None
    game_start = upcoming.min()
    return df[start == game_start], game_start


def player_ladder(
    df: pd.DataFrame,
    player: str,
    markets: "set[str] | list[str]",
    side: str = "over",
    team: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Best price and book(s) at every line one player has in the given
    markets (a base market plus its _alternate ladder), for his next game.
    One entry per line, sorted low to high. `team` narrows to games that
    team is in -- two players can share a name ("Will Smith")."""
    if df is None or df.empty:
        return []
    price_col = "Over Price" if side == "over" else "Under Price"
    sub = df[(df["_key"] == _name_key(player)) & df["market"].isin(list(markets))]
    if team and {"home_team", "away_team"} <= set(sub.columns):
        sub = sub[(sub["home_team"] == team) | (sub["away_team"] == team)]
    sub, game_start = _pin_next_game(sub)
    sub = sub.dropna(subset=[price_col, "Line"])
    if sub.empty:
        return []
    is_live = bool(game_start is not None and game_start <= pd.Timestamp.now(tz="UTC"))
    out = []
    for line, g in sub.groupby("Line"):
        best = g[price_col].max()
        out.append({
            "line": float(line),
            "price": int(best),
            "books": sorted(g.loc[g[price_col] == best, "bookmakers"].astype(str).unique()),
            "is_live": is_live,
        })
    return sorted(out, key=lambda x: x["line"])


def best_price_at_line(
    df: pd.DataFrame,
    player: str,
    markets: "set[str] | list[str]",
    line: float,
    side: str = "over",
    team: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Just the one rung of player_ladder() -- e.g. hits over 0.5."""
    for rung in player_ladder(df, player, markets, side, team):
        if abs(rung["line"] - line) < 1e-9:
            return rung
    return None
