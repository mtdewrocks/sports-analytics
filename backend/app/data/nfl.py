"""NFL business logic layer."""
from typing import Optional, List, Dict, Any
import pandas as pd
from app.data.loader import get_nfl_stats, get_nfl_team_stats, get_nfl_schedule

# Stat groups for reference / display
PASSING_STATS = [
    "passing_yards", "passing_tds", "interceptions", "completions",
    "attempts", "completion_pct", "passer_rating", "sacks",
]
RUSHING_STATS = [
    "rushing_yards", "rushing_tds", "carries", "yards_per_carry",
]
RECEIVING_STATS = [
    "receiving_yards", "receiving_tds", "receptions", "targets",
    "yards_per_reception", "air_yards",
]
DEFENSE_STATS = [
    "sacks", "tackles", "interceptions", "fumbles_recovered",
    "passes_defended", "defensive_tds",
]

ALL_STAT_GROUPS = {
    "passing": PASSING_STATS,
    "rushing": RUSHING_STATS,
    "receiving": RECEIVING_STATS,
    "defense": DEFENSE_STATS,
}


def _normalize(name: str) -> str:
    return name.strip().lower()


def _player_col(df: pd.DataFrame) -> str:
    for c in ["player_display_name", "player_name", "player", "name"]:
        if c in df.columns:
            return c
    raise KeyError("No player name column found in NFL data")


def _team_col(df: pd.DataFrame) -> Optional[str]:
    for c in ["recent_team", "team", "posteam", "team_abbr"]:
        if c in df.columns:
            return c
    return None


def _week_col(df: pd.DataFrame) -> Optional[str]:
    for c in ["week", "game_week", "week_num"]:
        if c in df.columns:
            return c
    return None


def _season_col(df: pd.DataFrame) -> Optional[str]:
    for c in ["season", "year", "season_year"]:
        if c in df.columns:
            return c
    return None


def get_players() -> List[str]:
    df = get_nfl_stats()
    col = _player_col(df)
    return sorted(df[col].dropna().unique().tolist())


def get_available_stats() -> Dict[str, Any]:
    """Return available stat columns grouped by category."""
    df = get_nfl_stats()
    actual_cols = set(df.columns.tolist())

    result = {}
    for group, stats in ALL_STAT_GROUPS.items():
        available = [s for s in stats if s in actual_cols]
        result[group] = available

    # Also return all numeric columns not already categorized
    categorized = set(s for stats in ALL_STAT_GROUPS.values() for s in stats)
    extra = [c for c in actual_cols if c not in categorized and pd.api.types.is_numeric_dtype(df[c])]
    result["other"] = sorted(extra)

    return result


def get_game_log(
    player: str,
    stat: str = "passing_yards",
    threshold: float = 0,
) -> dict:
    df = get_nfl_stats()
    col = _player_col(df)

    player_norm = _normalize(player)
    mask = df[col].str.lower().str.strip() == player_norm
    player_df = df[mask].copy()

    if player_df.empty:
        return {"rows": [], "hit_rate": None, "average": None, "games": 0}

    week_col = _week_col(df)
    season_col = _season_col(df)
    team_col = _team_col(df)

    # Compute stat values
    if stat in player_df.columns:
        stat_values = pd.to_numeric(player_df[stat], errors="coerce").fillna(0)
    else:
        stat_values = pd.Series([0.0] * len(player_df), index=player_df.index)

    player_df = player_df.copy()
    player_df["_stat_value"] = stat_values

    # Build output rows with useful context columns
    keep_cols = ["_stat_value"]
    for c in [week_col, season_col, team_col, "opponent_team", "home_team", "away_team", "result"]:
        if c and c in player_df.columns:
            keep_cols.append(c)

    rows = player_df[keep_cols].copy()
    rows = rows.rename(columns={"_stat_value": stat})

    # Sort by season then week if available
    sort_cols = []
    if season_col and season_col in rows.columns:
        sort_cols.append(season_col)
    if week_col and week_col in rows.columns:
        sort_cols.append(week_col)
    if sort_cols:
        rows = rows.sort_values(sort_cols)

    rows_list = rows.fillna("").to_dict(orient="records")

    total = len(rows_list)
    hits = int((stat_values >= threshold).sum()) if threshold > 0 else None
    hit_rate = round(hits / total, 4) if (hits is not None and total > 0) else None
    average = round(float(stat_values.mean()), 2) if total > 0 else None

    return {
        "player": player,
        "stat": stat,
        "threshold": threshold,
        "games": total,
        "hit_rate": hit_rate,
        "average": average,
        "rows": rows_list,
    }


def get_matchups() -> List[Dict[str, Any]]:
    """Return upcoming matchups from the schedule file."""
    try:
        schedule_df = get_nfl_schedule()
    except Exception as e:
        return [{"error": str(e)}]

    if schedule_df.empty:
        return []

    schedule_df.columns = [c.strip().lower().replace(" ", "_") for c in schedule_df.columns]

    # Try to find home/away/week columns
    home_col = None
    away_col = None
    for h in ["home_team", "home", "home_abbr"]:
        if h in schedule_df.columns:
            home_col = h
            break
    for a in ["away_team", "away", "away_abbr", "visitor_team", "visitor"]:
        if a in schedule_df.columns:
            away_col = a
            break

    if not home_col or not away_col:
        # Just return raw rows
        return schedule_df.fillna("").to_dict(orient="records")

    matchups = []
    for _, row in schedule_df.iterrows():
        home = str(row.get(home_col, ""))
        away = str(row.get(away_col, ""))
        if not home or not away:
            continue
        entry = {
            "matchup": f"{away} @ {home}",
            "home_team": home,
            "away_team": away,
        }
        for c in schedule_df.columns:
            if c not in [home_col, away_col] and c not in entry:
                val = row.get(c, "")
                entry[c] = str(val) if pd.notna(val) else ""
        matchups.append(entry)

    # Frontend expects a flat list of matchup strings like ["DAL @ PHI", ...]
    return [entry["matchup"] for entry in matchups]


def get_matchup_detail(matchup: str) -> Dict[str, Any]:
    """
    Return detailed stats for a matchup string like 'DAL @ PHI'.
    Pulls team stats for both teams and top players from each side.
    """
    parts = [p.strip().upper() for p in matchup.replace("@", " @ ").split("@")]
    if len(parts) != 2:
        return {"error": f"Could not parse matchup: {matchup}"}

    away_team, home_team = parts[0].strip(), parts[1].strip()

    # Load team stats
    try:
        team_df = get_nfl_team_stats()
        team_df.columns = [c.strip().lower().replace(" ", "_") for c in team_df.columns]
    except Exception:
        team_df = pd.DataFrame()

    team_col_name = None
    for c in ["team", "team_name", "team_abbr", "abbreviation"]:
        if c in team_df.columns:
            team_col_name = c
            break

    def get_team_stats_row(team_abbr: str) -> dict:
        if team_df.empty or not team_col_name:
            return {}
        mask = team_df[team_col_name].str.upper().str.strip() == team_abbr
        rows = team_df[mask]
        if rows.empty:
            return {}
        return rows.iloc[0].fillna("").to_dict()

    # Load player stats for player summaries
    try:
        player_df = get_nfl_stats()
        p_col = _player_col(player_df)
        t_col = _team_col(player_df)
    except Exception:
        player_df = pd.DataFrame()
        p_col = None
        t_col = None

    def get_top_players(team_abbr: str, n: int = 5) -> List[dict]:
        if player_df.empty or not p_col or not t_col:
            return []
        mask = player_df[t_col].str.upper().str.strip() == team_abbr
        sub = player_df[mask]
        if sub.empty:
            return []
        # Aggregate per player
        numeric_cols = sub.select_dtypes(include="number").columns.tolist()
        agg = sub.groupby(p_col)[numeric_cols].mean().reset_index()
        # Sort by a representative offensive stat if available
        for sort_stat in ["passing_yards", "rushing_yards", "receiving_yards"]:
            if sort_stat in agg.columns:
                agg = agg.sort_values(sort_stat, ascending=False)
                break
        top = agg.head(n)
        return top.fillna("").to_dict(orient="records")

    return {
        "matchup": matchup,
        "home_team": home_team,
        "away_team": away_team,
        "home_stats": get_team_stats_row(home_team),
        "away_stats": get_team_stats_row(away_team),
        "home_top_players": get_top_players(home_team),
        "away_top_players": get_top_players(away_team),
    }
