"""MLB business logic layer."""
from typing import Optional, List, Dict, Any
import pandas as pd
from app.data.loader import get_mlb_data


def _normalize(name: str) -> str:
    return name.strip().lower()


def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    cols_lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in cols_lower:
            return cols_lower[c.lower()]
    return None


def _pitcher_col(df: pd.DataFrame) -> Optional[str]:
    return _find_col(df, ["pitcher_name", "pitcher", "player_name", "player", "name"])


def _team_col(df: pd.DataFrame) -> Optional[str]:
    return _find_col(df, ["team", "team_name", "tm", "team_abbr"])


def _player_col(df: pd.DataFrame) -> Optional[str]:
    return _find_col(df, ["player_name", "player", "name", "hitter_name", "batter"])


def get_pitchers() -> List[str]:
    """Return sorted list of unique pitcher names."""
    data = get_mlb_data()
    df = data.get("pitcher_stats", pd.DataFrame())
    if df.empty:
        return []
    col = _pitcher_col(df)
    if not col:
        return []
    return sorted(df[col].dropna().unique().tolist())


def get_pitcher_matchup(pitcher_name: str) -> Dict[str, Any]:
    """
    Return comprehensive pitcher matchup data including:
    - pitcher career/season stats
    - game logs
    - percentile rankings
    - opposing hitter data
    """
    data = get_mlb_data()
    pitcher_norm = _normalize(pitcher_name)

    # --- Pitcher season stats ---
    pitcher_stats_df = data.get("pitcher_stats", pd.DataFrame())
    pitcher_stats = {}
    if not pitcher_stats_df.empty:
        col = _pitcher_col(pitcher_stats_df)
        if col:
            mask = pitcher_stats_df[col].str.lower().str.strip() == pitcher_norm
            rows = pitcher_stats_df[mask]
            if not rows.empty:
                pitcher_stats = rows.iloc[0].fillna("").to_dict()

    # --- Pitcher game logs ---
    game_log_df = data.get("pitcher_game_logs", pd.DataFrame())
    game_logs = []
    if not game_log_df.empty:
        col = _pitcher_col(game_log_df)
        if col:
            mask = game_log_df[col].str.lower().str.strip() == pitcher_norm
            sub = game_log_df[mask].copy()
            # Sort by date if possible
            for date_c in ["game_date", "date"]:
                if date_c in sub.columns:
                    sub = sub.sort_values(date_c, ascending=False)
                    break
            game_logs = sub.fillna("").to_dict(orient="records")

    # --- Pitcher percentile rankings ---
    pct_df = data.get("pitcher_percentiles", pd.DataFrame())
    percentiles = {}
    if not pct_df.empty:
        col = _pitcher_col(pct_df)
        if col:
            mask = pct_df[col].str.lower().str.strip() == pitcher_norm
            rows = pct_df[mask]
            if not rows.empty:
                percentiles = rows.iloc[0].fillna("").to_dict()

    # --- Opposing hitters (current day) ---
    # Attempt to identify the opponent team from the game log
    opponent_team = None
    if game_logs:
        latest = game_logs[0]
        for c in ["opponent", "opp", "away_team", "home_team", "opponent_team"]:
            if c in latest and latest[c]:
                opponent_team = str(latest[c]).strip()
                break

    # Current day hitters for the opponent team
    current_hitters_df = data.get("current_hitters", pd.DataFrame())
    opposing_hitters = []
    if not current_hitters_df.empty and opponent_team:
        t_col = _team_col(current_hitters_df)
        if t_col:
            mask = current_hitters_df[t_col].str.upper().str.strip() == opponent_team.upper()
            sub = current_hitters_df[mask]
            opposing_hitters = sub.fillna("").to_dict(orient="records")
        else:
            opposing_hitters = current_hitters_df.fillna("").to_dict(orient="records")

    # If no opponent identified, return all current hitters
    if not opposing_hitters and not current_hitters_df.empty:
        opposing_hitters = current_hitters_df.fillna("").head(30).to_dict(orient="records")

    return {
        "pitcher": pitcher_name,
        "stats": pitcher_stats,
        "game_logs": game_logs,
        "percentiles": percentiles,
        "opponent_team": opponent_team,
        "opposing_hitters": opposing_hitters,
    }


def get_hot_hitters() -> List[Dict[str, Any]]:
    """Return the list of hot/top hitter picks."""
    data = get_mlb_data()

    # Primary: dedicated hot hitters file
    hot_df = data.get("hot_hitters", pd.DataFrame())
    if not hot_df.empty:
        return hot_df.fillna("").to_dict(orient="records")

    # Fallback: use current_day_hitters if available
    current_df = data.get("current_hitters", pd.DataFrame())
    if not current_df.empty:
        return current_df.fillna("").to_dict(orient="records")

    # Last resort: top hitters from aggregated stats
    hitter_stats_df = data.get("hitter_stats", pd.DataFrame())
    if hitter_stats_df.empty:
        return []

    # Sort by a relevant metric if available
    sort_candidates = ["avg", "ops", "obp", "slg", "hr", "hits"]
    for s in sort_candidates:
        if s in hitter_stats_df.columns:
            hitter_stats_df = hitter_stats_df.sort_values(s, ascending=False)
            break

    return hitter_stats_df.head(25).fillna("").to_dict(orient="records")


def get_mlb_props(
    team: Optional[str] = None,
    player: Optional[str] = None,
    market: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return MLB props filtered by team, player, and/or market."""
    data = get_mlb_data()
    props_df = data.get("props", pd.DataFrame())

    if props_df.empty:
        return []

    props_df = props_df.copy()
    props_df.columns = [c.strip().lower().replace(" ", "_") for c in props_df.columns]

    player_col = _player_col(props_df)
    team_col = _team_col(props_df)
    market_col = _find_col(props_df, ["market", "prop_type", "stat", "bet_type", "category"])

    if team and team_col:
        team_norm = team.strip().upper()
        props_df = props_df[props_df[team_col].str.upper().str.strip() == team_norm]

    if player and player_col:
        player_norm = _normalize(player)
        props_df = props_df[props_df[player_col].str.lower().str.strip() == player_norm]

    if market and market_col:
        market_norm = _normalize(market)
        props_df = props_df[props_df[market_col].str.lower().str.strip() == market_norm]

    return props_df.fillna("").to_dict(orient="records")
