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


def get_available_stats() -> List[str]:
    """Return a flat list of available stat columns in preferred display order."""
    df = get_nfl_stats()
    actual_cols = set(df.columns.tolist())
    ordered = []
    for group_stats in ALL_STAT_GROUPS.values():
        for s in group_stats:
            if s in actual_cols:
                ordered.append(s)
    return ordered


def get_game_log(
    player: str,
    stat: str = "passing_yards",
    threshold: float = 0,
) -> dict:
    df = get_nfl_stats()
    col = _player_col(df)

    player_norm = _normalize(player)
    player_df = df[df[col].str.lower().str.strip() == player_norm].copy()

    if player_df.empty:
        return {"games": [], "over_counts": {"last5": {"over": 0, "total": 0, "pct": 0}, "last10": {"over": 0, "total": 0, "pct": 0}, "season": {"over": 0, "total": 0, "pct": 0}}}

    week_col = _week_col(df)
    season_col = _season_col(df)

    # Compute stat values
    stat_values = pd.to_numeric(player_df.get(stat, pd.Series(dtype=float)), errors="coerce").fillna(0)
    player_df["_stat_value"] = stat_values

    # Sort by season then week
    sort_cols = [c for c in [season_col, week_col] if c and c in player_df.columns]
    if sort_cols:
        player_df = player_df.sort_values(sort_cols)
        stat_values = player_df["_stat_value"]

    # Build game rows matching NBA shape
    game_rows = []
    for _, row in player_df.iterrows():
        week = row.get(week_col) if week_col else None
        season = row.get(season_col) if season_col else None
        opponent = row.get("opponent_team") or row.get("home_team") or ""
        label = f"W{int(week)}" if pd.notna(week) else ""
        game_date = f"{int(season)} {label}" if season and label else label or str(season or "")
        game_rows.append({
            "game_date": game_date,
            "opponent": str(opponent),
            "stat_value": float(row["_stat_value"]),
            "week": int(week) if pd.notna(week) else None,
        })

    # Compute over/under counts matching NBA shape
    all_vals = [g["stat_value"] for g in game_rows]

    def _over_count(values: list, n: int = None) -> dict:
        v = values[-n:] if n else values
        total = len(v)
        if total == 0:
            return {"over": 0, "total": 0, "pct": 0}
        over = int(sum(1 for x in v if x >= threshold))
        return {"over": over, "total": total, "pct": round(over / total, 4)}

    return {
        "games": game_rows,
        "over_counts": {
            "last5": _over_count(all_vals, 5),
            "last10": _over_count(all_vals, 10),
            "season": _over_count(all_vals),
        },
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
