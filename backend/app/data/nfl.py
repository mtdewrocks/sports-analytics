"""NFL business logic layer."""
from typing import Optional, List, Dict, Any
import pandas as pd
from app.data.loader import get_nfl_stats, get_nfl_team_stats, get_nfl_schedule, get_nfl_player_week_usage, get_nfl_weekly_defense_ranks, get_nfl_team_game_script

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

# Which defensive context applies to a given selected stat. Passing AND
# receiving both map to pass defense, since receiving yards are the flip
# side of the same pass-coverage matchup. DEFENSE_STATS (a player's own
# defensive numbers, e.g. a linebacker's sacks/tackles) intentionally has no
# mapping -- "what defense did they face" isn't the relevant context for a
# defensive player's own stat line, and building the equivalent ("what
# offense did they face") is a different, out-of-scope feature.
PASS_CONTEXT_STATS = set(PASSING_STATS) | set(RECEIVING_STATS)
RUSH_CONTEXT_STATS = set(RUSHING_STATS)


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


def _current_nfl_season() -> int:
    from datetime import date
    today = date.today()
    return today.year if today.month >= 9 else today.year - 1


def _defense_context(stat: str, season, week, opponent: str, rank_history: pd.DataFrame) -> Dict[str, Any]:
    """Pass or rush defensive context for one played game, from the
    historical weekly-rank file -- entering-that-week ranks, not current
    ones. Returns an empty dict for a stat with no mapped category (a
    player's own defensive stats)."""
    if stat in PASS_CONTEXT_STATS:
        prefix = "def_pass"
    elif stat in RUSH_CONTEXT_STATS:
        prefix = "def_rush"
    else:
        return {}

    if rank_history.empty or pd.isna(season) or pd.isna(week):
        return {}

    match = rank_history[
        (rank_history["season"] == int(season))
        & (rank_history["week"] == int(week))
        & (rank_history["team"].str.upper() == str(opponent).upper())
    ]
    if match.empty:
        return {}
    row = match.iloc[0]

    def clean(v):
        return None if pd.isna(v) else round(float(v), 1)

    def clean_rank(v):
        return None if pd.isna(v) else int(v)

    return {
        "def_ypg_season": clean(row.get(f"{prefix}_ypg_season")),
        "def_ypg_rank_season": clean_rank(row.get(f"{prefix}_ypg_rank_season")),
        "def_ypa_season": clean(row.get(f"{prefix}_ypa_season")),
        "def_ypa_rank_season": clean_rank(row.get(f"{prefix}_ypa_rank_season")),
        "def_ypg_last4": clean(row.get(f"{prefix}_ypg_last4")),
        "def_ypg_rank_last4": clean_rank(row.get(f"{prefix}_ypg_rank_last4")),
        "def_ypa_last4": clean(row.get(f"{prefix}_ypa_last4")),
        "def_ypa_rank_last4": clean_rank(row.get(f"{prefix}_ypa_rank_last4")),
        "def_is_fallback": bool(row.get("is_fallback", False)),
    }


def _upcoming_games(stat: str, player_team: str, season: int) -> List[Dict[str, Any]]:
    """Remaining schedule for the player's current team, with CURRENT
    defensive context (team_stats.parquet's latest snapshot) attached --
    there's no history to look up for a game that hasn't happened yet, so
    "as of right now" is exactly the right answer here, unlike past games.
    """
    if stat not in PASS_CONTEXT_STATS and stat not in RUSH_CONTEXT_STATS:
        return []

    schedule = get_nfl_schedule()
    if schedule.empty or not player_team:
        return []

    season_games = schedule[schedule["season"] == season]
    upcoming = season_games[
        season_games["home_score"].isna()
        & ((season_games["home_team"] == player_team) | (season_games["away_team"] == player_team))
    ].sort_values("week")

    team_stats = get_nfl_team_stats()
    prefix = "Defense Pass" if stat in PASS_CONTEXT_STATS else "Defense Rush"

    rows = []
    for g in upcoming.itertuples():
        opponent = g.home_team if g.away_team == player_team else g.away_team
        match = team_stats[team_stats["team"].str.upper() == str(opponent).upper()] if not team_stats.empty else pd.DataFrame()
        context = {}
        if not match.empty:
            row = match.iloc[0]
            context = {
                "def_ypg_current": round(float(row.get(f"{prefix} Yards Per Game")), 1) if pd.notna(row.get(f"{prefix} Yards Per Game")) else None,
                "def_ypg_rank_current": int(row.get(f"Rank - {prefix} Yards Per Game")) if pd.notna(row.get(f"Rank - {prefix} Yards Per Game")) else None,
                "def_ypa_current": round(float(row.get(f"{prefix} Yards Per Attempt")), 1) if pd.notna(row.get(f"{prefix} Yards Per Attempt")) else None,
                "def_ypa_rank_current": int(row.get(f"Rank - {prefix} Yards Per Attempt")) if pd.notna(row.get(f"Rank - {prefix} Yards Per Attempt")) else None,
            }
        rows.append({
            "week": int(g.week),
            "opponent": opponent,
            "is_upcoming": True,
            **context,
        })
    return rows


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
        return {"games": [], "upcoming": [], "over_counts": {"last5": {"over": 0, "total": 0, "pct": 0}, "last10": {"over": 0, "total": 0, "pct": 0}, "season": {"over": 0, "total": 0, "pct": 0}}}

    week_col = _week_col(df)
    season_col = _season_col(df)
    team_col = _team_col(df)

    # Compute stat values
    stat_values = pd.to_numeric(player_df.get(stat, pd.Series(dtype=float)), errors="coerce").fillna(0)
    player_df["_stat_value"] = stat_values

    # Sort by season then week
    sort_cols = [c for c in [season_col, week_col] if c and c in player_df.columns]
    if sort_cols:
        player_df = player_df.sort_values(sort_cols)
        stat_values = player_df["_stat_value"]

    rank_history = get_nfl_weekly_defense_ranks()

    # Build game rows matching NBA shape, plus defensive context
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
            "season": int(season) if pd.notna(season) else None,
            **_defense_context(stat, season, week, opponent, rank_history),
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

    # Upcoming games for the player's current team -- current-season, since
    # a player's future schedule beyond the season they've been logging in
    # isn't a thing yet.
    upcoming = []
    if team_col and not player_df.empty:
        current_team = player_df.iloc[-1].get(team_col)
        season_for_schedule = _current_nfl_season()
        if pd.notna(current_team):
            upcoming = _upcoming_games(stat, str(current_team), season_for_schedule)

    return {
        "games": game_rows,
        "upcoming": upcoming,
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


# Empirically derived from league-wide 2025 play-by-play: the spread in
# pass rate across score situations, by quarter (4.4 / 5.9 / 10.3 / 42.5
# points), normalized so Q4 = 1.0. No team is actually "leading big" before
# the game starts, so blending toward the situation-specific rate more
# heavily as the game progresses (rather than applying it flat across all
# four quarters) matches how game state actually diverges from the pregame
# expectation over time.
GAME_SCRIPT_QUARTER_WEIGHTS = {1: 0.104, 2: 0.140, 3: 0.243, 4: 1.000}


def _implied_situation(margin: float) -> str:
    """Same one-score-game (8-point) cutoff as get_nfl_game_script.py."""
    if margin <= -9:
        return "trailing_big"
    if margin <= -1:
        return "trailing"
    if margin == 0:
        return "tied"
    if margin <= 8:
        return "leading"
    return "leading_big"


def _projected_pass_pct(team_row: pd.Series, situation: str) -> Optional[float]:
    """Quarter-weighted blend between a team's neutral pass rate and its
    rate in the spread-implied situation -- see GAME_SCRIPT_QUARTER_WEIGHTS
    for why this isn't just a flat lookup.

    Uses pass_pct_neutral (close-game rate, within 7 points) rather than
    pass_pct_overall (plain season average) as the "as if the score didn't
    matter" baseline. Real 2025 data showed season average is measurably
    biased by team quality (r=-0.37 with point differential) -- winning
    teams look artificially run-heavy just from leading more often across
    the whole season, losing teams look artificially pass-heavy from
    trailing more. Restricting to close games removes most of that bias
    (r=0.14) while actually having MORE plays per team to estimate from.
    """
    neutral = team_row.get("pass_pct_neutral")
    situational = team_row.get(f"pass_pct_{situation}")
    if pd.isna(neutral) or pd.isna(situational):
        return None

    quarter_values = [
        (1 - weight) * neutral + weight * situational
        for weight in GAME_SCRIPT_QUARTER_WEIGHTS.values()
    ]
    return round(float(sum(quarter_values) / len(quarter_values)), 1)


def get_game_script_projection(matchup: str) -> Dict[str, Any]:
    """Spread-implied game script for one matchup: each team's projected
    pass/run mix, season-neutral (close-game rate) blended toward its own
    historical tendency in the situation the spread implies.

    Deliberately team-level only. A player-level version (projected
    carries/targets/yards per player) was built and then removed: every
    player-level source here is historical play-by-play, which can't know
    about a player who joined a team this offseason (e.g. a notable free
    agent signing) -- he simply has zero rows under his new team, while
    holdover backups who happen to have last-season tape keep showing up
    normally. That's not a rare edge case, it's a systematic blind spot for
    any real offseason addition, and it gets worse than just "incomplete":
    the projection looks confident and precise while quietly being wrong
    for exactly the situations people care most about. The team-level
    projection below doesn't have that problem -- it isn't tied to any one
    player's status, and it's built on a full prior season's real sample
    rather than a handful of early-season games.
    """
    parts = [p.strip().upper() for p in matchup.replace("@", " @ ").split("@")]
    if len(parts) != 2:
        return {"error": f"Could not parse matchup: {matchup}"}
    away_team, home_team = parts[0].strip(), parts[1].strip()

    schedule = get_nfl_schedule()
    game = schedule[
        (schedule["away_team"].str.upper() == away_team) & (schedule["home_team"].str.upper() == home_team)
    ]
    if game.empty:
        return {"error": f"No scheduled game found for {matchup}"}
    game_row = game.sort_values("season", ascending=False).iloc[0]
    spread_line = game_row.get("spread_line")
    total_line = game_row.get("total_line")

    if pd.isna(spread_line):
        return {"matchup": matchup, "away_team": away_team, "home_team": home_team, "error": "No line available for this game yet"}

    # spread_line is the home team's spread: negative = home favored by that
    # many points. Implied full-game margin is the mirror for each side.
    home_margin = -float(spread_line)
    away_margin = float(spread_line)

    game_script = get_nfl_team_game_script()

    def team_section(team: str, margin: float) -> Dict[str, Any]:
        situation = _implied_situation(margin)
        row = game_script[game_script["team"].str.upper() == team]
        if row.empty:
            return {"team": team, "implied_situation": situation, "error": "No game script data for this team"}
        row = row.iloc[0]

        projected_pass_pct = _projected_pass_pct(row, situation)
        baseline_pass_pct = row.get("pass_pct_neutral")

        return {
            "team": team,
            "implied_situation": situation,
            "baseline_pass_pct": None if pd.isna(baseline_pass_pct) else round(float(baseline_pass_pct), 1),
            "projected_pass_pct": projected_pass_pct,
        }

    return {
        "matchup": matchup,
        "away_team": away_team,
        "home_team": home_team,
        "spread_line": float(spread_line),
        "total_line": None if pd.isna(total_line) else float(total_line),
        "away": team_section(away_team, away_margin),
        "home": team_section(home_team, home_margin),
    }


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


# ---------------------------------------------------------------------------
# Weekly league-wide mismatch finder -- scans every game on a week's slate
# for the biggest statistical edges, instead of checking one matchup at a
# time on the Matchup page.
#
# All six categories share one scoring idea: for a given stat pairing (an
# offense stat and its comparable defense stat), a mismatch score is
# (33 - offense_rank) + defense_rank -- how strong this team's offense is,
# plus how weak the opponent's defense is, in that same stat. For passing,
# rushing, scoring, and sacks, "offense succeeding" and "defense failing"
# point the SAME direction (more passing yards is good for the offense and
# bad for the defense at once), so sorting this score descending always
# surfaces the biggest one-sided mismatch.
#
# Interceptions are the exception -- an offense succeeds by throwing FEW,
# a defense succeeds by taking MANY, which are opposite directions on the
# same event. That makes the same two numbers answer two different
# questions depending on sort direction: sorted one way, it surfaces "this
# defense should feast on a turnover-prone offense" (score low = bad
# offense + good takeaway defense); sorted the other way, it surfaces "ball
# security against a defense that rarely forces turnovers" (score high =
# both sides point toward a clean game). So interceptions appear as two
# separate categories below, sharing the same underlying columns but
# opposite sort directions, rather than one category with an ambiguous
# "mismatch" framing.
MISMATCH_CATEGORIES = {
    "passing": {
        "label": "Passing Offense vs. Pass Defense",
        "offense_col": "Pass Yards Per Game", "offense_rank_col": "Rank - Pass Yards Per Game",
        "defense_col": "Defense Pass Yards Per Game", "defense_rank_col": "Rank - Defense Pass Yards Per Game",
        "offense_label": "passing offense", "defense_label": "pass defense",
        "sort": "descending",
    },
    "rushing": {
        "label": "Rushing Offense vs. Run Defense",
        "offense_col": "Rush Yards Per Game", "offense_rank_col": "Rank - Rush Yards Per Game",
        "defense_col": "Defense Rush Yards Per Game", "defense_rank_col": "Rank - Defense Rush Yards Per Game",
        "offense_label": "rushing offense", "defense_label": "run defense",
        "sort": "descending",
    },
    "scoring": {
        "label": "Scoring Offense vs. Scoring Defense",
        "offense_col": "score_offense", "offense_rank_col": "Rank - Scoring Offense",
        "defense_col": "score_defense", "defense_rank_col": "Rank - Scoring Defense",
        "offense_label": "scoring offense", "defense_label": "scoring defense",
        "sort": "descending",
    },
    "sacks": {
        "label": "Pass Protection vs. Pass Rush",
        "offense_col": "Sacks Allowed", "offense_rank_col": "Rank - Sacks Allowed",
        "defense_col": "Defensive Sacks", "defense_rank_col": "Rank - Defensive Sacks",
        "offense_label": "pass protection", "defense_label": "pass rush",
        "sort": "descending",
    },
    "takeaways": {
        "label": "Takeaway Defense vs. Turnover-Prone Offense",
        "offense_col": "Interceptions Thrown Per Game", "offense_rank_col": "Rank - Interceptions Thrown Per Game",
        "defense_col": "Defensive Interceptions Per Game", "defense_rank_col": "Rank - Defensive Interceptions Per Game",
        "offense_label": "ball security", "defense_label": "takeaways",
        "sort": "ascending",  # low score = bad ball security + good takeaway defense
    },
    "ball_security": {
        "label": "Clean Game (Ball Security vs. Low-Takeaway Defense)",
        "offense_col": "Interceptions Thrown Per Game", "offense_rank_col": "Rank - Interceptions Thrown Per Game",
        "defense_col": "Defensive Interceptions Per Game", "defense_rank_col": "Rank - Defensive Interceptions Per Game",
        "offense_label": "ball security", "defense_label": "low takeaways",
        "sort": "descending",  # high score = good ball security + defense that rarely forces it anyway
    },
}


def get_mismatch_categories() -> List[Dict[str, str]]:
    """Category list for the frontend's dropdown/toggle."""
    return [{"key": key, "label": cfg["label"]} for key, cfg in MISMATCH_CATEGORIES.items()]


def get_weekly_mismatches(category: str, week: Optional[int] = None) -> Dict[str, Any]:
    """Every game on one week's slate, scored for the given mismatch
    category, sorted biggest mismatch first (or, for the two interception
    categories, in whichever direction that category's framing needs)."""
    config = MISMATCH_CATEGORIES.get(category)
    if config is None:
        return {"error": f"Unknown category: {category}"}

    schedule = get_nfl_schedule()
    if schedule.empty:
        return {"category": category, "label": config["label"], "week": week, "games": []}

    season = _current_nfl_season()
    season_games = schedule[schedule["season"] == season]
    if season_games.empty:
        return {"category": category, "label": config["label"], "week": week, "games": []}

    if week is None:
        completed = season_games[season_games["home_score"].notna()]
        week = int(completed["week"].max()) + 1 if not completed.empty else 1

    week_games = season_games[season_games["week"] == week]
    team_stats = get_nfl_team_stats()

    def team_row(team: str):
        match = team_stats[team_stats["team"].str.upper() == team.upper()]
        return match.iloc[0] if not match.empty else None

    def make_entry(matchup: str, off_team: str, off_row, def_team: str, def_row):
        off_rank = off_row.get(config["offense_rank_col"])
        def_rank = def_row.get(config["defense_rank_col"])
        if pd.isna(off_rank) or pd.isna(def_rank):
            return None
        off_value = off_row.get(config["offense_col"])
        def_value = def_row.get(config["defense_col"])
        return {
            "matchup": matchup,
            "offense_team": off_team,
            "defense_team": def_team,
            "offense_rank": int(off_rank),
            "defense_rank": int(def_rank),
            "offense_value": round(float(off_value), 1) if pd.notna(off_value) else None,
            "defense_value": round(float(def_value), 1) if pd.notna(def_value) else None,
            "score": round(float((33 - off_rank) + def_rank), 1),
        }

    entries = []
    for g in week_games.itertuples():
        home, away = str(g.home_team), str(g.away_team)
        home_row, away_row = team_row(home), team_row(away)
        if home_row is None or away_row is None:
            continue
        matchup = f"{away} @ {home}"
        for e in (
            make_entry(matchup, home, home_row, away, away_row),
            make_entry(matchup, away, away_row, home, home_row),
        ):
            if e:
                entries.append(e)

    entries.sort(key=lambda e: e["score"], reverse=(config["sort"] == "descending"))

    return {
        "category": category,
        "label": config["label"],
        "offense_label": config["offense_label"],
        "defense_label": config["defense_label"],
        "week": week,
        "games": entries,
    }
