"""NBA business logic layer."""
import re
from typing import Optional, List
import pandas as pd
from app.data.loader import get_nba_data, get_nba_props

STAT_COMBOS = {
    "pra": ["pts", "reb", "ast"],
    "blk_stl": ["blk", "stl"],
    "reb_ast": ["reb", "ast"],
    "pts_ast": ["pts", "ast"],
    "pts_reb": ["pts", "reb"],
}


def _normalize(name: str) -> str:
    return name.strip().lower()


def _player_col(df: pd.DataFrame) -> str:
    """Return the player name column, trying common variants."""
    for c in ["player", "player_name", "name"]:
        if c in df.columns:
            return c
    raise KeyError("No player name column found in NBA data")


def get_players() -> List[str]:
    df = get_nba_data()
    col = _player_col(df)
    return sorted(df[col].dropna().unique().tolist())


# ---------------------------------------------------------------------------
# Column-detection helpers, pulled out of the inline "try these column names"
# blocks that get_teammates/get_game_log/get_in_out each duplicate -- the
# Team Usage and Team Matchup functions below need the same detection in a
# few more places, so it's worth naming once rather than re-copying the
# candidate lists a fourth and fifth time.
# ---------------------------------------------------------------------------

def _team_col(df: pd.DataFrame) -> Optional[str]:
    return next((c for c in ["team", "team_abbreviation", "tm"] if c in df.columns), None)


def _date_col(df: pd.DataFrame) -> Optional[str]:
    return next((c for c in ["game_date", "date", "gameid", "game_id"] if c in df.columns), None)


def _min_col(df: pd.DataFrame) -> Optional[str]:
    return next((c for c in ["min", "minutes", "min_played"] if c in df.columns), None)


def _played_col(df: pd.DataFrame) -> Optional[str]:
    return next((c for c in ["played", "game_played"] if c in df.columns), None)


def _opponent_col(df: pd.DataFrame) -> Optional[str]:
    return next((c for c in ["opponent", "matchup", "opp"] if c in df.columns), None)


def get_teammates(player: str) -> List[str]:
    """Return all players who shared at least one game with *player* on the same team."""
    df = get_nba_data()
    col = _player_col(df)

    # Identify the team column
    team_col = None
    for c in ["team", "team_abbreviation", "tm"]:
        if c in df.columns:
            team_col = c
            break

    game_col = None
    for c in ["game_id", "gameid", "game_date", "date"]:
        if c in df.columns:
            game_col = c
            break

    player_norm = _normalize(player)
    mask = df[col].str.lower().str.strip() == player_norm
    player_rows = df[mask]

    if player_rows.empty:
        return []

    if team_col and game_col:
        # Find (game, team) pairs for the target player
        game_team = player_rows[[game_col, team_col]].drop_duplicates()
        merged = df.merge(game_team, on=[game_col, team_col])
        teammates = merged[col].dropna().unique().tolist()
        teammates = [t for t in teammates if _normalize(t) != player_norm]
    elif team_col:
        teams = player_rows[team_col].unique()
        teammates = df[df[team_col].isin(teams)][col].dropna().unique().tolist()
        teammates = [t for t in teammates if _normalize(t) != player_norm]
    else:
        teammates = []

    return sorted(teammates)


def compute_stat(df: pd.DataFrame, stat: str) -> pd.Series:
    """Compute a (possibly composite) stat series from df columns."""
    cols = STAT_COMBOS.get(stat)
    if cols:
        available = [c for c in cols if c in df.columns]
        if not available:
            return pd.Series([0.0] * len(df), index=df.index)
        return df[available].fillna(0).sum(axis=1)
    if stat in df.columns:
        return pd.to_numeric(df[stat], errors="coerce").fillna(0)
    return pd.Series([0.0] * len(df), index=df.index)


def get_game_log(
    player: str,
    stat: str = "pts",
    threshold: float = 0,
    with_player: Optional[str] = None,
    without_player: Optional[str] = None,
    b2b: bool = False,
    three_in_four: bool = False,
    min_minutes: int = 0,
) -> dict:
    df = get_nba_data()
    col = _player_col(df)

    player_norm = _normalize(player)
    mask = df[col].str.lower().str.strip() == player_norm
    player_df = df[mask].copy()

    if player_df.empty:
        return {"rows": [], "hit_rate": None, "average": None, "games": 0}

    # Detect date/game columns
    date_col = None
    for c in ["game_date", "gameid", "date", "game_id"]:
        if c in df.columns:
            date_col = c
            break

    game_col = None
    for c in ["game_id", "gameid", "game_date", "date"]:
        if c in df.columns:
            game_col = c
            break

    team_col = None
    for c in ["team", "team_abbreviation", "tm"]:
        if c in df.columns:
            team_col = c
            break


    # Filter with_player / without_player
    # Use the same (normalized_date, team) key approach as get_in_out so that
    # played=0 inactive rows don't pollute the game lists.
    if (with_player or without_player) and date_col and team_col:
        # Normalize dates to plain date objects (strips timestamp differences)
        player_df = player_df.copy()
        player_df["_date"] = pd.to_datetime(player_df[date_col], errors="coerce").dt.date

        # Build a reference frame limited to rows where the player actually played
        played_col = next((c for c in ["played", "game_played"] if c in df.columns), None)
        df_ref = df.copy()
        df_ref["_date"] = pd.to_datetime(df_ref[date_col], errors="coerce").dt.date
        if played_col:
            df_ref = df_ref[pd.to_numeric(df_ref[played_col], errors="coerce") == 1]

        if with_player:
            wp_norm = _normalize(with_player)
            wp_rows = df_ref[df_ref[col].str.lower().str.strip() == wp_norm]
            # (date, team) pairs where with_player actually played
            wp_keys = set(zip(wp_rows["_date"], wp_rows[team_col]))
            player_df = player_df[
                player_df.apply(lambda r: (r["_date"], r[team_col]) in wp_keys, axis=1)
            ]

        if without_player:
            wop_norm = _normalize(without_player)
            wop_rows = df_ref[df_ref[col].str.lower().str.strip() == wop_norm]
            # (date, team) pairs where without_player actually played
            wop_keys = set(zip(wop_rows["_date"], wop_rows[team_col]))
            player_df = player_df[
                ~player_df.apply(lambda r: (r["_date"], r[team_col]) in wop_keys, axis=1)
            ]

    # Back-to-back filter
    if b2b and date_col:
        try:
            player_df = player_df.copy()
            player_df[date_col] = pd.to_datetime(player_df[date_col], errors="coerce")
            player_df = player_df.sort_values(date_col)
            prev_dates = player_df[date_col].shift(1)
            diff = (player_df[date_col] - prev_dates).dt.days
            player_df = player_df[diff == 1]
        except Exception:
            pass

    # Three-in-four filter
    if three_in_four and date_col:
        try:
            player_df = player_df.copy()
            player_df[date_col] = pd.to_datetime(player_df[date_col], errors="coerce")
            player_df = player_df.sort_values(date_col)
            mask_3in4 = []
            dates = player_df[date_col].reset_index(drop=True)
            for i in range(len(dates)):
                if i >= 2:
                    span = (dates[i] - dates[i - 2]).days
                    mask_3in4.append(span <= 3)
                else:
                    mask_3in4.append(False)
            player_df = player_df[mask_3in4]
        except Exception:
            pass

    # Minimum minutes filter
    if min_minutes > 0:
        min_col_early = next((c for c in ["min", "minutes", "min_played"] if c in player_df.columns), None)
        if min_col_early:
            player_df = player_df[
                pd.to_numeric(player_df[min_col_early], errors="coerce").fillna(0) >= min_minutes
            ]

    # Compute stat
    stat_values = compute_stat(player_df, stat)
    player_df = player_df.copy()
    player_df["_stat_value"] = stat_values

    # Detect minutes column
    min_col = None
    for c in ["min", "minutes", "min_played"]:
        if c in player_df.columns:
            min_col = c
            break

    # Build result rows
    keep_cols = ["_stat_value"]
    if date_col and date_col in player_df.columns:
        keep_cols.append(date_col)
    for c in ["opponent", "matchup", "opp", "wl", "result"]:
        if c in player_df.columns:
            keep_cols.append(c)
    if min_col:
        keep_cols.append(min_col)
    for c in ["fgm", "fga"]:
        if c in player_df.columns:
            keep_cols.append(c)

    rows = player_df[keep_cols].copy()
    rows = rows.rename(columns={"_stat_value": stat})
    if date_col and date_col in rows.columns:
        rows[date_col] = rows[date_col].astype(str)

    rows_list = rows.fillna("").to_dict(orient="records")

    # Build game rows in the shape the frontend expects
    game_rows = []
    for row_dict in rows_list:
        game_date = str(row_dict.get(date_col, "")) if date_col else ""
        opponent = str(
            row_dict.get("opponent") or row_dict.get("matchup") or row_dict.get("opp") or ""
        )
        stat_value = float(row_dict.get(stat, 0) or 0)
        minutes = row_dict.get(min_col) if min_col else None
        fgm = row_dict.get("fgm")
        fga = row_dict.get("fga")
        game_rows.append({
            "game_date": game_date,
            "opponent": opponent,
            "stat_value": stat_value,
            "min": minutes,
            "fgm": int(fgm) if fgm not in (None, "") else None,
            "fga": int(fga) if fga not in (None, "") else None,
        })

    # Sort ascending so chart displays oldest (left) → newest (right)
    # and values[-n:] correctly selects the most recent N games.
    # Must parse the date string (MM/DD/YYYY) — lexicographic sort is wrong.
    game_rows.sort(key=lambda r: pd.to_datetime(r["game_date"], errors="coerce") if r.get("game_date") else pd.Timestamp.min)

    # Compute over/under counts for last 5, last 10, and full season
    def _over_count(values: list, n: int = None) -> dict:
        v = values[-n:] if n else values
        total = len(v)
        if total == 0:
            return {"over": 0, "total": 0, "pct": 0}
        over = int(sum(1 for x in v if x > threshold))
        return {"over": over, "total": total, "pct": round(over / total, 4)}

    all_vals = [r["stat_value"] for r in game_rows]
    over_counts = {
        "last5": _over_count(all_vals, 5),
        "last10": _over_count(all_vals, 10),
        "season": _over_count(all_vals),
    }

    return {
        "games": game_rows,
        "over_counts": over_counts,
    }


def get_in_out(player_a: str, exclude: List[str] = None) -> dict:
    """
    Compare player_a's stats when specific teammates are in vs out of the lineup.

    Logic: use (normalized game_date, team) as the key so two teammates on the
    same team on the same date are matched correctly, regardless of timestamp
    format differences in the raw data.
      - anchor AND excluded player both have played=1, same date, same team → "with"
      - anchor played but excluded player did not → "without"
    """
    df = get_nba_data()
    col = _player_col(df)
    exclude = [e for e in (exclude or []) if e]

    date_col = next((c for c in ["game_date", "date"] if c in df.columns), None)
    team_col = next((c for c in ["team", "team_abbreviation", "tm"] if c in df.columns), None)

    if not date_col or not team_col:
        return {"player": player_a, "exclude": exclude,
                "games_with": 0, "games_without": 0, "with": {}, "without": {}}

    # Filter to played=1 rows only
    played_col = next((c for c in ["played", "game_played"] if c in df.columns), None)
    df_active = df[pd.to_numeric(df[played_col], errors="coerce") == 1].copy() if played_col else df.copy()

    # Normalise date to remove timestamp component so dates compare cleanly
    df_active["_date"] = pd.to_datetime(df_active[date_col], errors="coerce").dt.date

    player_norm = _normalize(player_a)
    anchor_df = df_active[df_active[col].str.lower().str.strip() == player_norm].copy()

    if anchor_df.empty:
        return {"player": player_a, "exclude": exclude,
                "games_with": 0, "games_without": 0, "with": {}, "without": {}}

    # Key = (date, team) — two teammates always share the same team on the same date
    anchor_keys = set(zip(anchor_df["_date"], anchor_df[team_col]))

    # Pre-compute (date, team) key sets for each excluded player
    exc_key_sets = []
    for exc_player in exclude:
        exc_norm = _normalize(exc_player)
        exc_df   = df_active[df_active[col].str.lower().str.strip() == exc_norm].copy()
        exc_key_sets.append(set(zip(exc_df["_date"], exc_df[team_col])))

    # "With" = anchor games where ALL excluded players played
    with_keys = anchor_keys.copy()
    for eks in exc_key_sets:
        with_keys = with_keys & eks

    # "Without" = anchor games where ALL excluded players were absent
    without_keys = anchor_keys.copy()
    for eks in exc_key_sets:
        without_keys = without_keys - eks

    anchor_df["_key"] = list(zip(anchor_df["_date"], anchor_df[team_col]))
    df_with    = anchor_df[anchor_df["_key"].isin(with_keys)]
    df_without = anchor_df[anchor_df["_key"].isin(without_keys)]

    stat_cols = [s for s in ["min", "pts", "reb", "ast", "pts_ast", "pts_reb", "pra"] if s in anchor_df.columns]

    def avg_stats(sub_df: pd.DataFrame) -> dict:
        result = {}
        for s in stat_cols:
            vals = pd.to_numeric(sub_df[s], errors="coerce").dropna()
            result[s] = round(float(vals.mean()), 2) if len(vals) > 0 else None
        return result

    return {
        "player": player_a,
        "exclude": exclude,
        "games_with": len(with_keys),
        "games_without": len(without_keys),
        "with": avg_stats(df_with),
        "without": avg_stats(df_without),
    }


def get_biggest_beneficiary(excluded_player: str, stat: str = "min", min_games: int = 3) -> dict:
    """Given one player who is OUT, find which teammate's stat increases the
    most -- rather than requiring the user to manually check each teammate
    one at a time via get_in_out(). Reuses get_in_out() and get_teammates()
    directly instead of duplicating the with/without logic.

    min_games: both the "with" and "without" sample need at least this many
    games, or a teammate is skipped entirely -- a "without" average built
    from a single game is too noisy to call someone a genuine beneficiary,
    and would be exactly the kind of result most likely to misleadingly
    top this ranking if left in.
    """
    teammates = get_teammates(excluded_player)
    results = []
    for teammate in teammates:
        cmp = get_in_out(teammate, [excluded_player])
        with_val = cmp.get("with", {}).get(stat)
        without_val = cmp.get("without", {}).get(stat)
        if with_val is None or without_val is None:
            continue
        if cmp["games_with"] < min_games or cmp["games_without"] < min_games:
            continue
        results.append({
            "player": teammate,
            "with": with_val,
            "without": without_val,
            "delta": round(without_val - with_val, 2),
            "games_with": cmp["games_with"],
            "games_without": cmp["games_without"],
        })

    results.sort(key=lambda r: r["delta"], reverse=True)
    return {"excluded_player": excluded_player, "stat": stat, "results": results}


ALLOWED_BOOKS = {
    "betmgm", "draftkings", "espnbet", "fanatics", "fanduel",
    "fliff", "hardrockbet", "prizepicks", "underdog", "williamhill_us",
}

# Maps frontend-friendly market names to the data's player_ prefix keys
MARKET_MAP = {
    "points":    "player_points",
    "rebounds":  "player_rebounds",
    "assists":   "player_assists",
    "steals":    "player_steals",
    "blocks":    "player_blocks",
    "3-pointers": "player_threes",
    "pts+reb+ast": "player_points_rebounds_assists",
    "pts+reb":   "player_points_rebounds",
    "pts+ast":   "player_points_assists",
    "reb+ast":   "player_rebounds_assists",
    "blk+stl":   "player_blocks_steals",
}


def get_props(
    player: Optional[str] = None,
    market: Optional[str] = None,
    side: Optional[str] = None,
    bookmaker: Optional[str] = None,
) -> List[dict]:
    """Return NBA props filtered by player, market, side, and/or bookmaker."""
    try:
        df = get_nba_props()
    except Exception as e:
        return [{"error": str(e)}]

    if df.empty:
        return []

    df.columns = [c.lower().replace(" ", "_") for c in df.columns]

    # Restrict to allowed sportsbooks
    df = df[df["bookmakers"].isin(ALLOWED_BOOKS)]

    if player:
        df = df[df["player"].str.lower().str.strip() == _normalize(player)]

    if market:
        market_key = MARKET_MAP.get(_normalize(market), _normalize(market))
        df = df[df["market"].str.lower() == market_key]

    if bookmaker:
        df = df[df["bookmakers"].str.lower() == _normalize(bookmaker)]

    # The data has over_price / under_price as separate columns — melt into rows
    over_df = df[["player", "market", "line", "bookmakers", "over_price"]].copy()
    over_df["side"] = "over"
    over_df = over_df.rename(columns={"over_price": "odds", "bookmakers": "bookmaker"})
    over_df = over_df.dropna(subset=["odds"])

    under_df = df[["player", "market", "line", "bookmakers", "under_price"]].copy()
    under_df["side"] = "under"
    under_df = under_df.rename(columns={"under_price": "odds", "bookmakers": "bookmaker"})
    under_df = under_df.dropna(subset=["odds"])

    melted = pd.concat([over_df, under_df], ignore_index=True)

    if side:
        melted = melted[melted["side"] == _normalize(side)]

    melted["odds"] = melted["odds"].astype(int)
    melted["line"] = melted["line"].astype(float)

    return melted.fillna("").to_dict(orient="records")


# ---------------------------------------------------------------------------
# Team Usage / Team Matchup -- both aggregated straight from the same
# per-game box-score file everything above reads, same way the NFL/MLB
# Team Usage and Team Matchup pages work. No separate team-stats or
# play-by-play pipeline exists for NBA yet (see USAGE note below), so this
# leans harder on the multi-candidate column detection already used
# throughout this file, and degrades to empty/None results rather than
# raising when a column it hoped for isn't there.
#
# IMPORTANT CAVEAT: unlike every other recent change in this codebase, this
# section could NOT be verified against the live NBA_STATS_URL file -- this
# session had no network access to fetch it. Every column name is a
# best-effort guess based on the candidate lists get_teammates/get_game_log/
# get_in_out already use elsewhere in this file. If the real file's team,
# date, or opponent columns don't match one of the candidates tried below,
# get_teams()/get_team_usage() will come back empty and get_team_matchup()'s
# defense/record/head-to-head fields will come back None rather than wrong --
# but this needs a real check against production data before being trusted.
# ---------------------------------------------------------------------------

TEAM_USAGE_METRICS = {"fga", "pts", "min"}


def get_teams() -> List[str]:
    """Distinct team abbreviations, for a team selector -- reads the same
    box-score file get_players() does, no new pipeline."""
    df = get_nba_data()
    team_col = _team_col(df)
    if not team_col:
        return []
    teams = df[team_col].dropna().astype(str).str.upper().str.strip()
    return sorted(t for t in teams.unique().tolist() if t)


def get_team_usage(team: str, metric: str = "fga", scope: str = "season") -> dict:
    """Per-player share of a team's shot attempts, points, or minutes.

    scope="season" averages every game loaded so far this season;
    scope="l10" averages only the team's 10 most recent game dates (not
    each player's own last 10 games individually -- a bench player who
    missed two of those games is still being compared over the same
    10-game window as everyone else on the roster).

    Starter/bench is inferred from minutes-per-game rank (top 5 by minutes
    = starter) rather than a roster pull, since this box-score file carries
    no position/depth-chart data the way NFL's newer pipeline does.
    """
    metric = metric if metric in TEAM_USAGE_METRICS else "fga"
    empty = {
        "team": team.upper().strip(), "metric": metric, "scope": scope,
        "team_total": 0.0, "starter_share": 0.0, "players": [],
    }

    df = get_nba_data()
    if df.empty:
        return empty

    col = _player_col(df)
    team_col = _team_col(df)
    if not team_col:
        return empty

    team_norm = team.upper().strip()
    sub = df[df[team_col].astype(str).str.upper().str.strip() == team_norm].copy()
    if sub.empty:
        return empty

    played_col = _played_col(df)
    if played_col:
        sub = sub[pd.to_numeric(sub[played_col], errors="coerce") == 1]

    date_col = _date_col(df)
    if scope == "l10" and date_col:
        sub["_date"] = pd.to_datetime(sub[date_col], errors="coerce")
        recent_dates = sorted(sub["_date"].dropna().unique())[-10:]
        if recent_dates:
            sub = sub[sub["_date"].isin(recent_dates)]

    if sub.empty:
        return empty

    # "min" is handled separately from compute_stat() below: compute_stat only
    # checks for the literal column name "min", but the minutes column can
    # also show up as "minutes" or "min_played" (see _min_col) -- going
    # through compute_stat for the Minutes toggle would silently return all
    # zeroes on a file using either of those alternate names.
    min_col = _min_col(df)
    sub["_min_value"] = pd.to_numeric(sub[min_col], errors="coerce").fillna(0) if min_col else 0.0
    sub["_stat_value"] = sub["_min_value"] if metric == "min" else compute_stat(sub, metric)

    agg = (
        sub.groupby(col)
        .agg(value=("_stat_value", "mean"), min=("_min_value", "mean"), games=("_stat_value", "count"))
        .reset_index()
    )
    if agg.empty:
        return empty

    agg = agg.sort_values("min", ascending=False).reset_index(drop=True)
    agg["role"] = ["starter" if i < 5 else "bench" for i in range(len(agg))]

    team_total = float(agg["value"].sum())
    agg["share"] = agg["value"] / team_total if team_total > 0 else 0.0
    starter_share = float(agg.loc[agg["role"] == "starter", "share"].sum())

    agg = agg.sort_values("value", ascending=False).reset_index(drop=True)

    players = [
        {
            "player": row[col],
            "role": row["role"],
            "value": round(float(row["value"]), 1),
            "share": round(float(row["share"]), 4),
            "games": int(row["games"]),
        }
        for _, row in agg.iterrows()
    ]

    return {
        "team": team_norm,
        "metric": metric,
        "scope": scope,
        "team_total": round(team_total, 1),
        "starter_share": round(starter_share, 4),
        "players": players,
    }


def _resolve_opponent(value, self_team: str, known_teams: set) -> Optional[str]:
    """Best-effort extraction of the OTHER team's abbreviation out of
    whatever the opponent/matchup/opp column holds -- a plain abbreviation
    ("DEN"), or a "BOS @ DEN" / "DEN vs. BOS" style matchup string. Returns
    None rather than guessing wrong when it can't tell."""
    if not isinstance(value, str):
        return None
    v = value.strip().upper()
    if not v:
        return None
    if v in known_teams and v != self_team:
        return v
    tokens = [t for t in re.split(r"[^A-Z0-9]+", v) if t]
    candidates = [t for t in tokens if t in known_teams and t != self_team]
    return candidates[0] if candidates else None


def _extract_win(value) -> Optional[float]:
    if not isinstance(value, str):
        return None
    v = value.strip().upper()
    if v.startswith("W"):
        return 1.0
    if v.startswith("L"):
        return 0.0
    return None


_MATCHUP_STAT_COLS = ["pts", "reb", "ast", "fgm", "fga"]


def _team_game_totals(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (team, game): that team's summed box-score totals for the
    game, the resolved opponent abbreviation (best-effort -- see
    _resolve_opponent), and a win flag when derivable. Feeds both offense
    (read the row directly) and defense (read the opponent's row for the
    same date) in get_team_matchup(), without needing a separate schedule
    or team-stats file -- the same per-game player rows already carry
    everything needed, just keyed by player instead of by team.
    """
    team_col = _team_col(df)
    date_col = _date_col(df)
    if not team_col or not date_col:
        return pd.DataFrame()

    sub = df.copy()
    played_col = _played_col(df)
    if played_col:
        sub = sub[pd.to_numeric(sub[played_col], errors="coerce") == 1]

    sub["_date"] = pd.to_datetime(sub[date_col], errors="coerce")
    sub = sub.dropna(subset=["_date"])
    if sub.empty:
        return pd.DataFrame()

    sub[team_col] = sub[team_col].astype(str).str.upper().str.strip()
    known_teams = set(sub[team_col].unique())

    stat_cols = [c for c in _MATCHUP_STAT_COLS if c in sub.columns]
    for c in stat_cols:
        sub[c] = pd.to_numeric(sub[c], errors="coerce").fillna(0)

    opp_col = _opponent_col(sub)
    result_col = next((c for c in ["wl", "result"] if c in sub.columns), None)

    rows = []
    for (gdate, team), g in sub.groupby(["_date", team_col]):
        row: dict = {"date": gdate, "team": team}
        for c in stat_cols:
            row[c] = float(g[c].sum())

        opp = None
        if opp_col:
            resolved = [
                _resolve_opponent(v, team, known_teams)
                for v in g[opp_col].dropna().astype(str)
            ]
            resolved = [r for r in resolved if r]
            if resolved:
                opp = pd.Series(resolved).mode().iloc[0]
        row["opponent"] = opp

        win = None
        if result_col:
            wins = [w for w in (_extract_win(v) for v in g[result_col].dropna().astype(str)) if w is not None]
            if wins:
                win = pd.Series(wins).mode().iloc[0]
        row["win"] = win

        rows.append(row)

    tgt = pd.DataFrame(rows)
    if tgt.empty or "pts" not in tgt.columns:
        return tgt

    # Fall back to a points comparison for any game where a direct W/L
    # column wasn't available (or didn't parse) but the opponent WAS
    # resolved -- better than leaving every record blank on a file that
    # simply doesn't carry an explicit result column.
    opp_pts = tgt[["date", "team", "pts"]].rename(columns={"team": "opponent", "pts": "_opp_pts"})
    tgt = tgt.merge(opp_pts, on=["date", "opponent"], how="left")
    derived = (tgt["pts"] > tgt["_opp_pts"]).astype(float)
    derived[tgt["_opp_pts"].isna()] = float("nan")
    tgt["win"] = tgt["win"].where(tgt["win"].notna(), derived)
    tgt = tgt.drop(columns=["_opp_pts"])

    return tgt


def _team_offense(tgt: pd.DataFrame, team: str) -> dict:
    sub = tgt[tgt["team"] == team]
    if sub.empty:
        return {}
    out = {}
    for c in ["pts", "reb", "ast"]:
        if c in sub.columns:
            out[c] = float(sub[c].mean())
    if "fgm" in sub.columns and "fga" in sub.columns and sub["fga"].sum() > 0:
        out["fg_pct"] = float(sub["fgm"].sum() / sub["fga"].sum())
    return out


def _team_defense(tgt: pd.DataFrame, team: str) -> Optional[float]:
    """Points allowed/gm -- the same box-score file read the other way: for
    each game this team played, the points its resolved opponent put up.
    Needs the opponent to have resolved for that game; returns None rather
    than a wrong number where it couldn't."""
    if "pts" not in tgt.columns:
        return None
    sub = tgt[(tgt["team"] == team) & tgt["opponent"].notna()]
    if sub.empty:
        return None
    opp_pts = tgt[["date", "team", "pts"]].rename(columns={"team": "opponent", "pts": "_opp_pts"})
    merged = sub.merge(opp_pts, on=["date", "opponent"], how="left")
    vals = merged["_opp_pts"].dropna()
    return float(vals.mean()) if not vals.empty else None


def _team_record(tgt: pd.DataFrame, team: str) -> Optional[dict]:
    sub = tgt[tgt["team"] == team]
    if sub.empty or "win" not in sub.columns:
        return None
    decided = sub.dropna(subset=["win"])
    if decided.empty:
        return None
    wins = int(decided["win"].sum())
    losses = int(len(decided) - wins)
    recent = decided.sort_values("date").tail(5)
    r_wins = int(recent["win"].sum())
    r_losses = int(len(recent) - r_wins)
    return {"wins": wins, "losses": losses, "last5": f"{r_wins}-{r_losses}"}


# label/direction for each Team Matchup row -- "direction" says which way is
# better, since Points Allowed is the one stat here where lower wins.
MATCHUP_STATS = [
    {"key": "pts", "label": "Points/gm", "direction": "high", "kind": "num"},
    {"key": "pts_allowed", "label": "Points allowed/gm", "direction": "low", "kind": "num"},
    {"key": "reb", "label": "Rebounds/gm", "direction": "high", "kind": "num"},
    {"key": "ast", "label": "Assists/gm", "direction": "high", "kind": "num"},
    {"key": "fg_pct", "label": "FG%", "direction": "high", "kind": "pct"},
]


def _league_team_stats(tgt: pd.DataFrame) -> pd.DataFrame:
    teams = sorted(tgt["team"].dropna().unique().tolist())
    rows = []
    for team in teams:
        row = {"team": team, **_team_offense(tgt, team)}
        d = _team_defense(tgt, team)
        if d is not None:
            row["pts_allowed"] = d
        rows.append(row)
    return pd.DataFrame(rows)


def _rank_of(league: pd.DataFrame, key: str, team: str, ascending: bool) -> Optional[int]:
    """1-based league rank for `team` on `key` -- ascending=True means the
    smallest value is rank 1 (used for Points Allowed), else the largest is."""
    if league.empty or key not in league.columns:
        return None
    ranked = league.dropna(subset=[key]).sort_values(key, ascending=ascending).reset_index(drop=True)
    match = ranked.index[ranked["team"] == team]
    return int(match[0]) + 1 if len(match) else None


def _head_to_head(tgt: pd.DataFrame, a: str, b: str) -> Optional[dict]:
    sub = tgt[(tgt["team"] == a) & (tgt["opponent"] == b)].sort_values("date")
    if sub.empty:
        return None
    games = len(sub)
    decided = sub.dropna(subset=["win"]) if "win" in sub.columns else sub.iloc[0:0]
    a_wins = int(decided["win"].sum()) if len(decided) == games and games > 0 else None
    b_wins = (games - a_wins) if a_wins is not None else None
    last = sub.iloc[-1]
    last_b = tgt[(tgt["team"] == b) & (tgt["date"] == last["date"])]
    return {
        "games": games,
        "a_wins": a_wins,
        "b_wins": b_wins,
        "last_meeting": {
            "date": str(last["date"].date()) if pd.notna(last["date"]) else None,
            "a_pts": float(last["pts"]) if "pts" in sub.columns and pd.notna(last["pts"]) else None,
            "b_pts": float(last_b.iloc[0]["pts"]) if not last_b.empty and "pts" in last_b.columns else None,
        },
    }


def get_team_matchup(team_a: str, team_b: str) -> dict:
    """Season-to-date offense/defense for both teams, league rank per stat,
    and head-to-head record -- all derived from the same per-game box-score
    file get_players()/get_game_log() already read. Mirrors the NFL/MLB
    Team Matchup pages' value+rank shape.

    Defense isn't a column in the raw file -- "points allowed" for team A in
    a given game is just team B's own point total from that same game, so
    it's the same file read the other way once the opponent is resolved
    (see _resolve_opponent / _team_game_totals). Where that resolution
    fails, the affected numbers come back as None rather than a guess.
    """
    a = team_a.upper().strip()
    b = team_b.upper().strip()
    empty = {
        "team_a": a, "team_b": b, "record_a": None, "record_b": None,
        "stats_a": [], "stats_b": [], "head_to_head": None,
    }

    df = get_nba_data()
    if df.empty:
        return empty

    tgt = _team_game_totals(df)
    if tgt.empty:
        return empty

    league = _league_team_stats(tgt)

    def stat_rows(team: str) -> List[dict]:
        values = {**_team_offense(tgt, team), "pts_allowed": _team_defense(tgt, team)}
        rows = []
        for spec in MATCHUP_STATS:
            val = values.get(spec["key"])
            ascending = spec["direction"] == "low"
            rank = _rank_of(league, spec["key"], team, ascending) if val is not None else None
            rows.append({
                "key": spec["key"],
                "label": spec["label"],
                "direction": spec["direction"],
                "kind": spec["kind"],
                "value": round(val, 4 if spec["kind"] == "pct" else 1) if val is not None else None,
                "rank": rank,
            })
        return rows

    return {
        "team_a": a,
        "team_b": b,
        "record_a": _team_record(tgt, a),
        "record_b": _team_record(tgt, b),
        "stats_a": stat_rows(a),
        "stats_b": stat_rows(b),
        "head_to_head": _head_to_head(tgt, a, b) if a != b else None,
    }
