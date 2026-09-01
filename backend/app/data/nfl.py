"""NFL business logic layer."""
from typing import Optional, List, Dict, Any
import pandas as pd
from app.data.loader import get_nfl_stats, get_nfl_team_stats, get_nfl_schedule, get_nfl_player_week_usage

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


# Display order matches the user's original Quarto script's team_stats /
# team_ranks column selections exactly, including which stats it chose to
# show (e.g. Sacks Allowed / Defensive Sacks are computed and ranked
# upstream in get_nfl_weekly_stats.py but were never part of this specific
# display list in the source script, so they're left out here too).
# (display label, value column, rank column)
MATCHUP_STAT_ROWS = [
    ("Scoring Offense (PPG)", "score_offense", "Rank - Scoring Offense"),
    ("Scoring Defense (PPG Allowed)", "score_defense", "Rank - Scoring Defense"),
    ("Plays Per Game", "Plays Per Game", "Rank - Plays Per Game"),
    ("Pass Share", "pass_share", "Rank - pass_share"),
    ("Run Share", "run_share", "Rank - run_share"),
    ("Pass Yards Per Game", "Pass Yards Per Game", "Rank - Pass Yards Per Game"),
    ("Yards Per Pass Attempt", "Yards Per Pass Attempt", "Rank - Yards Per Pass Attempt"),
    ("Rush Yards Per Game", "Rush Yards Per Game", "Rank - Rush Yards Per Game"),
    ("Yards Per Carry", "Yards Per Carry", "Rank - Yards Per Carry"),
    ("Defense Plays Per Game", "Defense Plays Per Game", "Rank - Defense Plays Per Game"),
    ("Defense Pass Share", "Defense Pass Share", "Rank - Defense Pass Share"),
    ("Defense Rush Share", "Defense Rush Share", "Rank - Defense Rush Share"),
    ("Defense Pass Yards Per Game", "Defense Pass Yards Per Game", "Rank - Defense Pass Yards Per Game"),
    ("Defense Pass Yards Per Attempt", "Defense Pass Yards Per Attempt", "Rank - Defense Pass Yards Per Attempt"),
    ("Defense Rush Yards Per Game", "Defense Rush Yards Per Game", "Rank - Defense Rush Yards Per Game"),
    ("Defense Rush Yards Per Attempt", "Defense Rush Yards Per Attempt", "Rank - Defense Rush Yards Per Attempt"),
]


def _current_nfl_season() -> int:
    """Same rule as get_nfl_pbp.py / get_nfl_weekly_stats.py -- an NFL
    season is labeled by the year it starts in, and isn't labeled until
    Week 1 is actually played."""
    from datetime import date
    today = date.today()
    return today.year if today.month >= 9 else today.year - 1


def get_matchups() -> List[str]:
    """Upcoming week's matchups -- a pregame preview, not a recap of the
    week that just finished. Stats in get_matchup_detail are accumulated
    through the last COMPLETED week, then applied to the NEXT week's games.
    """
    schedule = get_nfl_schedule()
    if schedule.empty:
        return []

    season = _current_nfl_season()
    schedule = schedule[schedule["season"] == season]
    if schedule.empty:
        return []

    completed = schedule[schedule["home_score"].notna()]
    # No games played yet this season -- preview Week 1 itself. Team stats
    # for this case come from get_nfl_weekly_stats.py's fallback to last
    # season's regular season, so there's still something real to compare
    # against rather than nothing.
    upcoming_week = int(completed["week"].max()) + 1 if not completed.empty else 1
    upcoming = schedule[schedule["week"] == upcoming_week]

    return sorted(
        f"{row.away_team} @ {row.home_team}"
        for row in upcoming.itertuples()
        if pd.notna(row.away_team) and pd.notna(row.home_team)
    )


def get_matchup_detail(matchup: str) -> Dict[str, Any]:
    """Stats + ranks for both sides of a matchup, in the same Stat/Value/Rank
    long format as the user's original Quarto HTML tables -- one row per
    stat, so the frontend can render it as a straightforward two-column
    comparison table without reshaping anything itself.
    """
    parts = [p.strip().upper() for p in matchup.replace("@", " @ ").split("@")]
    if len(parts) != 2:
        return {"error": f"Could not parse matchup: {matchup}"}
    away_team, home_team = parts[0].strip(), parts[1].strip()

    team_df = get_nfl_team_stats()

    def stat_rows(team_abbr: str) -> List[Dict[str, Any]]:
        if team_df.empty or "team" not in team_df.columns:
            return []
        match = team_df[team_df["team"].str.upper().str.strip() == team_abbr]
        if match.empty:
            return []
        row = match.iloc[0]

        rows = []
        for label, value_col, rank_col in MATCHUP_STAT_ROWS:
            value = row.get(value_col)
            rank = row.get(rank_col)
            rows.append({
                "stat": label,
                "value": round(float(value), 1) if pd.notna(value) else None,
                "rank": int(rank) if pd.notna(rank) else None,
            })
        return rows

    # Player stats for player summaries -- unchanged from before, still
    # reads the weekly player-stats file, a separate concern from team
    # offense/defense stats above.
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
        numeric_cols = sub.select_dtypes(include="number").columns.tolist()
        agg = sub.groupby(p_col)[numeric_cols].mean().reset_index()
        for sort_stat in ["passing_yards", "rushing_yards", "receiving_yards"]:
            if sort_stat in agg.columns:
                agg = agg.sort_values(sort_stat, ascending=False)
                break
        top = agg.head(n)
        return top.fillna("").to_dict(orient="records")

    stats_season = None
    through_week = None
    is_fallback = False
    if not team_df.empty and "team" in team_df.columns:
        any_row = team_df[team_df["team"].str.upper().str.strip() == home_team]
        if not any_row.empty:
            stats_season = int(any_row.iloc[0].get("season"))
            through_week = int(any_row.iloc[0].get("through_week"))
            is_fallback = bool(any_row.iloc[0].get("is_fallback", False))

    return {
        "matchup": matchup,
        "home_team": home_team,
        "away_team": away_team,
        "home_stats": stat_rows(home_team),
        "away_stats": stat_rows(away_team),
        "home_top_players": get_top_players(home_team),
        "away_top_players": get_top_players(away_team),
        "stats_season": stats_season,
        "stats_through_week": through_week,
        "is_fallback": is_fallback,
    }


# ---------------------------------------------------------------------------
# Play-by-play-derived usage (target share / rush share), from get_nfl_pbp.py.
# First piece of NFL data built on the new pipeline rather than the legacy
# manually-run Excel process -- see get_nfl_stats/get_nfl_team_stats above
# for the still-in-place old path.
# ---------------------------------------------------------------------------

def get_nfl_teams() -> List[str]:
    """Distinct team abbreviations available, for a team selector."""
    df = get_nfl_player_week_usage()
    if df.empty or "posteam" not in df.columns:
        return []
    return sorted(t for t in df["posteam"].dropna().unique().tolist() if t)


def get_team_usage(team: str, week: Optional[int] = None) -> Dict[str, Any]:
    """Team-level target share / rush share leaderboard, optionally for one
    week -- otherwise summed across all weeks loaded so far this season.

    Player rows are sorted by targets, since that's the more commonly
    referenced share stat; the same rows carry rushing numbers too, so a
    single call covers both the target-share and rushing-yards dashboards
    rather than needing two separate endpoints.
    """
    df = get_nfl_player_week_usage()
    if df.empty:
        return {"team": team, "week": week, "players": []}

    sub = df[df["posteam"].str.lower() == team.lower().strip()]
    if week is not None:
        sub = sub[sub["week"] == week]
        players = sub.sort_values("targets", ascending=False)
    else:
        # Season-to-date: sum counting stats, recompute shares from the
        # summed totals rather than averaging each week's already-computed
        # share (averaging shares across weeks of different pass volume
        # would over-weight a low-volume week).
        numeric_cols = [
            "targets", "receptions", "receiving_yards", "air_yards", "receiving_tds",
            "carries", "rushing_yards", "rushing_tds",
            "rz_targets", "rz_receptions", "rz_receiving_yards", "rz_air_yards", "rz_receiving_tds",
            "rz_carries", "rz_rushing_yards", "rz_rushing_tds",
        ]
        players = sub.groupby(["player_id", "player"], as_index=False)[numeric_cols].sum()
        team_targets = players["targets"].sum()
        team_air_yards = players["air_yards"].sum()
        team_carries = players["carries"].sum()
        players["target_share"] = (players["targets"] / team_targets) if team_targets else 0
        players["air_yards_share"] = (players["air_yards"] / team_air_yards) if team_air_yards else 0
        players["rush_share"] = (players["carries"] / team_carries) if team_carries else 0
        players = players.sort_values("targets", ascending=False)

    return {
        "team": team,
        "week": week,
        "players": players.fillna(0).to_dict(orient="records"),
    }
