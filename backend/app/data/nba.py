"""NBA business logic layer."""
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
    if (with_player or without_player) and game_col and team_col:
        if with_player:
            wp_norm = _normalize(with_player)
            wp_mask = df[col].str.lower().str.strip() == wp_norm
            wp_games = df[wp_mask][game_col].unique()
            # Get games where both player and with_player played on the same team
            wp_team = df[wp_mask][[game_col, team_col]].drop_duplicates()
            player_df = player_df.merge(wp_team, on=[game_col, team_col])

        if without_player:
            wop_norm = _normalize(without_player)
            wop_mask = df[col].str.lower().str.strip() == wop_norm
            wop_games = set(df[wop_mask][game_col].unique())
            player_df = player_df[~player_df[game_col].isin(wop_games)]

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
        game_rows.append({
            "game_date": game_date,
            "opponent": opponent,
            "stat_value": stat_value,
            "min": minutes,
        })

    # Compute over/under counts for last 5, last 10, and full season
    def _over_count(values: list, n: int = None) -> dict:
        v = values[-n:] if n else values
        total = len(v)
        if total == 0:
            return {"over": 0, "total": 0, "pct": 0}
        over = int(sum(1 for x in v if x >= threshold))
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

    # "With" = keys where EVERY excluded player also played (same date + same team)
    with_keys = anchor_keys.copy()
    for exc_player in exclude:
        exc_norm = _normalize(exc_player)
        exc_df   = df_active[df_active[col].str.lower().str.strip() == exc_norm].copy()
        exc_keys = set(zip(exc_df["_date"], exc_df[team_col]))
        with_keys = with_keys & exc_keys

    # "Without" = anchor keys where at least one excluded player did NOT play
    without_keys = anchor_keys - with_keys

    anchor_df["_key"] = list(zip(anchor_df["_date"], anchor_df[team_col]))
    df_with    = anchor_df[anchor_df["_key"].isin(with_keys)]
    df_without = anchor_df[anchor_df["_key"].isin(without_keys)]

    stat_cols = [s for s in ["pts", "reb", "ast", "stl", "blk", "tov"] if s in anchor_df.columns]

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


def get_props(
    player: Optional[str] = None,
    market: Optional[str] = None,
    side: Optional[str] = None,
) -> List[dict]:
    """Return NBA props filtered by player, market, and/or side."""
    try:
        df = get_nba_props()
    except Exception as e:
        return [{"error": str(e)}]

    if df.empty:
        return []

    df.columns = [c.lower().replace(" ", "_") for c in df.columns]

    # Detect columns
    player_col = None
    for c in ["player", "player_name", "name"]:
        if c in df.columns:
            player_col = c
            break

    market_col = None
    for c in ["market", "stat", "prop_type", "bet_type"]:
        if c in df.columns:
            market_col = c
            break

    side_col = None
    for c in ["side", "over_under", "direction"]:
        if c in df.columns:
            side_col = c
            break

    if player and player_col:
        player_norm = _normalize(player)
        df = df[df[player_col].str.lower().str.strip() == player_norm]

    if market and market_col:
        market_norm = _normalize(market)
        df = df[df[market_col].str.lower().str.strip() == market_norm]

    if side and side_col:
        side_norm = _normalize(side)
        df = df[df[side_col].str.lower().str.strip() == side_norm]

    return df.fillna("").to_dict(orient="records")
