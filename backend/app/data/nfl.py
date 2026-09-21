"""NFL business logic layer."""
from typing import Optional, List, Dict, Any
import math
import pandas as pd
from app.data.loader import get_nfl_stats, get_nfl_team_stats, get_nfl_schedule, get_nfl_player_week_usage, get_nfl_weekly_defense_ranks, get_nfl_team_game_script, get_nfl_defense_by_position, get_nfl_snap_counts, get_nfl_rosters, get_nfl_season_totals, get_nfl_player_box_stats, get_nfl_game_lines, ttl_cache, OTHER_TTL
from app.data.hit_rate import grade_over_under, split_season_recent, RECENT_WINDOW

# Stat groups for reference / display -- Game Log only (Fantasy Matchup,
# In/Out, and the usage trend page each have their own separate stat
# definitions and don't read these).
#
# Names here match get_nfl_player_box_stats.py's raw nflverse column names
# (passing_interceptions, sacks_suffered) rather than the shorter names the
# old legacy source used, since that script deliberately kept nflverse's own
# naming -- see its docstring. completion_pct, passer_rating,
# yards_per_carry, yards_per_reception and defensive box stats (tackles,
# passes defended, etc.) are dropped: neither the new source nor -- as far
# as could be checked -- the old one actually populated them.
PASSING_STATS = [
    "passing_yards", "passing_tds", "passing_interceptions", "completions",
    "attempts", "sacks_suffered",
]
RUSHING_STATS = [
    "rushing_yards", "rushing_tds", "carries",
]
RECEIVING_STATS = [
    "receiving_yards", "receiving_tds", "receptions", "targets",
    "receiving_air_yards",
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

# Supplementary raw stats shown in a tooltip alongside the main selected
# stat -- e.g. hovering a passing_yards row also shows that game's
# completions/attempts, without a second API call. Only stats the user
# actually asked for; everything else gets no tooltip.
STAT_TOOLTIP_FIELDS = {
    "passing_yards": ["completions", "attempts"],
    "rushing_yards": ["carries"],
    "receiving_yards": ["targets", "receptions"],
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


def get_game_log_players() -> List[str]:
    """Player list for the Game Log page specifically -- kept separate from
    get_players() above (used by Fantasy Matchup, In/Out, and the usage
    trend page) so that Game Log's move to a different data source can't
    put a name in its dropdown that those other three pages, still reading
    the legacy source, don't recognize.
    """
    df = get_nfl_player_box_stats()
    if df.empty:
        return []
    col = _player_col(df)
    return sorted(df[col].dropna().unique().tolist())


def get_available_stats() -> List[str]:
    """Return a flat list of available stat columns in preferred display
    order. Game Log only -- see PASSING_STATS etc. above."""
    df = get_nfl_player_box_stats()
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


# Noise rules for "Position vs. Defense" -- landed on with Shawn by looking
# at real data together (Ashton Jeanty vs. the Saints, 2026). Two different
# shapes depending on position:
#   - RB: a flat workload floor. A carries-only cutoff would hide a real
#     game from a pass-catching back (e.g. 3 carries, 70 receiving yards),
#     so it's an OR: carries >= 5 OR targets >= 4.
#   - WR/TE: a flat floor either lets 5+ names through a pass-heavy
#     shootout or none through a run-heavy blowout, so instead it's a
#     top-N cap PER GAME (top 3 WRs / top 2 TEs), ranked by receiving
#     yards (Shawn's call over targets -- means a lower-target,
#     higher-yardage game can outrank a higher-target, lower-yardage one;
#     surfaced in `excluded`, not hidden). Only players with >=1 target
#     that game are even in the running, so the cap never gets padded out
#     with a zero-target scrub just to hit the count -- a game with only 2
#     real options shows 2 rows, not 3.
_PVD_RB_MIN_CARRIES = 5
_PVD_RB_MIN_TARGETS = 4
_PVD_TOP_N = {"WR": 3, "TE": 2}

# Maps a raw roster/game-log position onto the coarse RB/WR/TE grouping the
# "Position vs. Defense" filters above are written for -- a roster can say
# "FB" or "HB" for a back, or "QB" isn't supported by this feature at all
# (no defense-by-QB-vs-QB comparison makes sense the same way), so this is
# also where an unsupported position quietly becomes None rather than
# something get_nfl_position_vs_defense() would reject.
_POSITION_GROUP_MAP = {
    "RB": "RB", "HB": "RB", "FB": "RB",
    "WR": "WR",
    "TE": "TE",
}


def _normalize_position_group(raw_position: Optional[str]) -> Optional[str]:
    if not raw_position:
        return None
    return _POSITION_GROUP_MAP.get(str(raw_position).upper())


def _pvd_num(v) -> int:
    return int(v) if pd.notna(v) else 0


def _pvd_row(row, week: int) -> Dict[str, Any]:
    return {
        "week": week,
        "player": str(row.player_display_name),
        "team": str(row.team),
        "carries": _pvd_num(row.carries),
        "rushing_yards": _pvd_num(row.rushing_yards),
        "rushing_tds": _pvd_num(row.rushing_tds),
        "targets": _pvd_num(row.targets),
        "receptions": _pvd_num(row.receptions),
        "receiving_yards": _pvd_num(row.receiving_yards),
        "receiving_tds": _pvd_num(row.receiving_tds),
    }


def _pvd_matchup_label(season: int, week: int, team: str) -> str:
    """'NO at DET' style label for a week's divider -- away team first, at
    the home team -- looked up from the real schedule rather than assumed,
    since box_stats itself doesn't say which side was home. Falls back to
    just the team name if the schedule row can't be matched."""
    schedule = get_nfl_schedule()
    if schedule.empty:
        return team
    match = schedule[
        (schedule["season"] == season) & (schedule["week"] == week)
        & ((schedule["home_team"] == team) | (schedule["away_team"] == team))
    ]
    if match.empty:
        return team
    g = match.iloc[0]
    return f"{g['away_team']} at {g['home_team']}"


def get_nfl_position_vs_defense(opponent: str, position: str, exclude_player: Optional[str] = None) -> Dict[str, Any]:
    """Weekly log of what a defense has allowed to one position this
    season -- e.g. every RB who has faced the Saints in 2026, most recent
    week first. Feeds the Game Log page's "Position vs. Defense" section,
    which sits directly under the Upcoming schedule's header, scoped to
    the next opponent on that schedule (not a general-purpose position
    browser -- there's no user-facing toggle for it).

    `exclude_player` drops the selected player's own row for `opponent`,
    for the rare case a team faces the same opponent twice in a season
    (a divisional rematch) and the player's own earlier game would
    otherwise show up looking like "someone else's" data point.

    Returns `rows` (already filtered) and `excluded` (everyone who didn't
    clear the filter, with why) -- the frontend shows `excluded` behind a
    "Show N filtered out" disclosure rather than dropping it silently, so
    the filtering stays auditable instead of a black box.
    """
    position = (position or "").upper()
    if position not in ("RB", "WR", "TE"):
        return {"rows": [], "excluded": []}

    box = get_nfl_player_box_stats()
    if box.empty or "opponent_team" not in box.columns:
        return {"rows": [], "excluded": []}

    season = _current_nfl_season()
    rows = box[
        (box["season"] == season)
        & (box["opponent_team"].str.upper() == str(opponent).upper())
        & (box["position"] == position)
    ].copy()
    if exclude_player:
        rows = rows[rows["player_display_name"] != exclude_player]
    if rows.empty:
        return {"rows": [], "excluded": []}

    included: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []

    for week_val, week_rows in rows.groupby("week"):
        week = int(week_val)
        team = str(week_rows["team"].iloc[0])
        matchup = _pvd_matchup_label(season, week, team)

        if position == "RB":
            for r in week_rows.itertuples():
                item = {**_pvd_row(r, week), "matchup": matchup}
                carries, targets = _pvd_num(r.carries), _pvd_num(r.targets)
                if carries >= _PVD_RB_MIN_CARRIES or targets >= _PVD_RB_MIN_TARGETS:
                    included.append(item)
                elif carries == 0 and targets == 0:
                    excluded.append({**item, "reason": "no involvement"})
                else:
                    excluded.append({**item, "reason": f"below thresholds (carries < {_PVD_RB_MIN_CARRIES}, targets < {_PVD_RB_MIN_TARGETS})"})
        else:
            top_n = _PVD_TOP_N[position]
            involved = [r for r in week_rows.itertuples() if _pvd_num(r.targets) >= 1]
            involved.sort(key=lambda r: _pvd_num(r.receiving_yards), reverse=True)
            for r in involved[:top_n]:
                included.append({**_pvd_row(r, week), "matchup": matchup})
            for r in involved[top_n:]:
                excluded.append({
                    **_pvd_row(r, week), "matchup": matchup,
                    "reason": f"cut by the {position} top-{top_n} cap (ranked below by receiving yards)",
                })
            for r in week_rows.itertuples():
                if _pvd_num(r.targets) == 0:
                    excluded.append({**_pvd_row(r, week), "matchup": matchup, "reason": "no involvement"})

    included.sort(key=lambda x: x["week"], reverse=True)
    excluded.sort(key=lambda x: x["week"], reverse=True)
    return {"rows": included, "excluded": excluded}


def get_game_log(
    player: str,
    stat: str = "passing_yards",
    threshold: float = 0,
    win_loss: Optional[str] = None,
    margin_operator: Optional[str] = None,
    margin_value: Optional[float] = None,
    season: Optional[int] = None,
) -> dict:
    df = get_nfl_player_box_stats()
    col = _player_col(df)
    season_col = _season_col(df)

    player_norm = _normalize(player)
    player_df = df[df[col].str.lower().str.strip() == player_norm].copy()

    # Defaults to the current season -- the whole point of adding a season
    # column here was so a game log doesn't silently mix two years of games
    # together, the way the single-season legacy source never had to worry
    # about. An explicit season (the page's toggle) narrows it further, or
    # to the OTHER season instead.
    effective_season = season if season is not None else _current_nfl_season()
    if season_col:
        player_df = player_df[player_df[season_col] == effective_season]

    if player_df.empty:
        empty_summary = {"games": 0, "avg": None, "hit": 0, "total": 0, "pct": 0}
        return {
            "games": [], "upcoming": [],
            "over_counts": {"last5": {"over": 0, "total": 0, "pct": 0}, "last10": {"over": 0, "total": 0, "pct": 0}, "season": {"over": 0, "total": 0, "pct": 0}},
            "win_loss_breakdown": {"W": empty_summary, "L": empty_summary},
            "player_position": None,
        }
    team_col = _team_col(df)
    week_col = _week_col(df)

    # Position drives the "Position vs. Defense" section on the frontend --
    # resolved from the full (pre win_loss/margin filter) player_df so a
    # narrow filter that empties the table doesn't also blank out the
    # position, and the same trade-aware lookup used for team elsewhere
    # (current roster preferred over the game log's own last row),
    # normalized to the coarse RB/WR/TE group get_nfl_position_vs_defense()
    # actually filters on (a raw roster position of "FB" or "HB" should
    # still mean "RB" here).
    _, _raw_position = _player_team_and_position(player_df, team_col, player)
    player_position = _normalize_position_group(_raw_position)

    # Result (W/L/T), signed margin, and the actual score, computed before
    # any filtering so "all games" view can still show them, then filtered
    # on if requested -- filtering here, before stat_values/windowing
    # below, means "last 5" correctly means "last 5 [filtered] games"
    # rather than a window picked first and then thinned out afterward.
    #
    # Win/Loss and margin are deliberately independent filters (not one
    # refining the other): a team can lose a close game and still see
    # similar volume/usage patterns to a close win, so margin needs to be
    # checkable on its own, not only as a subfilter of a chosen result.
    game_results = _game_results_for(player_df, team_col, season_col, week_col)
    player_df["_result"] = game_results["result"]
    player_df["_margin"] = game_results["margin"]
    player_df["_team_score"] = game_results["team_score"]
    player_df["_opp_score"] = game_results["opp_score"]

    # Wins-vs-losses breakdown, always the full season regardless of
    # whatever win_loss/margin filters get applied below for the rest of
    # this response -- the whole point of this table is comparing the two
    # groups against each other, so filtering either side down separately
    # would undercut the comparison rather than refine it.
    full_stat_values = pd.to_numeric(player_df.get(stat, pd.Series(dtype=float)), errors="coerce").fillna(0)

    def _result_summary(result_filter: str) -> Dict[str, Any]:
        mask = player_df["_result"] == result_filter
        vals = full_stat_values[mask]
        if len(vals) == 0:
            return {"games": 0, "avg": None, "hit": 0, "total": 0, "pct": 0}
        hit = int((vals >= threshold).sum())
        return {
            "games": len(vals),
            "avg": round(float(vals.mean()), 1),
            "hit": hit,
            "total": len(vals),
            "pct": round(hit / len(vals), 4),
        }

    win_loss_breakdown = {"W": _result_summary("W"), "L": _result_summary("L")}

    if win_loss in ("W", "L"):
        player_df = player_df[player_df["_result"] == win_loss]

    if margin_operator in ("<", ">") and margin_value is not None:
        # Margin filtering uses the ABSOLUTE point differential, not the
        # signed one: "margin < 7" should mean "any game decided by fewer
        # than 7 points" (a close win OR a close loss), not just "team
        # won/lost by fewer than 7" in one specific direction -- the
        # signed value is still returned per-game for the tooltip/score
        # display, but filtering itself is direction-agnostic by design.
        abs_margin = player_df["_margin"].abs()
        if margin_operator == "<":
            player_df = player_df[abs_margin < margin_value]
        else:
            player_df = player_df[abs_margin > margin_value]

    if player_df.empty:
        return {
            "games": [], "upcoming": [],
            "over_counts": {"last5": {"over": 0, "total": 0, "pct": 0}, "last10": {"over": 0, "total": 0, "pct": 0}, "season": {"over": 0, "total": 0, "pct": 0}},
            "win_loss_breakdown": win_loss_breakdown,
            "player_position": player_position,
        }
    stat_values = pd.to_numeric(player_df.get(stat, pd.Series(dtype=float)), errors="coerce").fillna(0)
    player_df["_stat_value"] = stat_values

    # Sort by season then week
    sort_cols = [c for c in [season_col, week_col] if c and c in player_df.columns]
    if sort_cols:
        player_df = player_df.sort_values(sort_cols)
        stat_values = player_df["_stat_value"]

    rank_history = get_nfl_weekly_defense_ranks()
    tooltip_fields = STAT_TOOLTIP_FIELDS.get(stat, [])

    # Build game rows matching NBA shape, plus defensive context
    game_rows = []
    for _, row in player_df.iterrows():
        week = row.get(week_col) if week_col else None
        season = row.get(season_col) if season_col else None
        opponent = row.get("opponent_team") or row.get("home_team") or ""
        label = f"W{int(week)}" if pd.notna(week) else ""
        game_date = f"{int(season)} {label}" if season and label else label or str(season or "")

        tooltip = {}
        for field in tooltip_fields:
            val = row.get(field)
            tooltip[field] = None if val is None or pd.isna(val) else float(val)
        # Score shown via tooltip rather than its own column, per request --
        # keeps the table clean while still making it available on hover.
        team_score, opp_score = row.get("_team_score"), row.get("_opp_score")
        if pd.notna(team_score) and pd.notna(opp_score):
            tooltip["score"] = f"{int(team_score)}-{int(opp_score)}"

        game_rows.append({
            "game_date": game_date,
            "opponent": str(opponent),
            "stat_value": float(row["_stat_value"]),
            "week": int(week) if pd.notna(week) else None,
            "season": int(season) if pd.notna(season) else None,
            "result": row.get("_result"),
            "tooltip": tooltip,
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

    # Upcoming games for the player's current team -- only when viewing the
    # actual current season. Every game in a PAST season is already played,
    # so "what's next" doesn't mean anything while the toggle is on last
    # season -- it would otherwise show the real upcoming schedule stapled
    # onto a historical game log, which reads as if last season is still in
    # progress.
    upcoming = []
    if team_col and not player_df.empty and effective_season == _current_nfl_season():
        current_team = player_df.iloc[-1].get(team_col)
        if pd.notna(current_team):
            upcoming = _upcoming_games(stat, str(current_team), effective_season)

    return {
        "games": game_rows,
        "upcoming": upcoming,
        "over_counts": {
            "last5": _over_count(all_vals, 5),
            "last10": _over_count(all_vals, 10),
            "season": _over_count(all_vals),
        },
        "win_loss_breakdown": win_loss_breakdown,
        "player_position": player_position,
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
    ("Sacks + QB Hits Allowed (Per Game)", "Sacks + QB Hits Allowed Per Game", "Rank - Sacks + QB Hits Allowed"),
    ("Defensive Sacks + QB Hits (Per Game)", "Defensive Sacks + QB Hits Per Game", "Rank - Defensive Sacks + QB Hits"),
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

    # A week only counts as "done" once EVERY one of its games has a score
    # -- see get_weekly_mismatches for the same fix and the reasoning
    # (checking for ANY completed game flipped this the moment a single
    # early game finished, well before the rest of that week, including
    # Monday Night Football, had been played).
    week_totals = schedule.groupby("week").size()
    week_completed = schedule[schedule["home_score"].notna()].groupby("week").size()
    fully_completed_weeks = [w for w in week_totals.index if week_completed.get(w, 0) == week_totals[w]]
    # No games played yet this season -- preview Week 1 itself. Team stats
    # for this case come from get_nfl_weekly_stats.py's fallback to last
    # season's regular season, so there's still something real to compare
    # against rather than nothing.
    upcoming_week = int(max(fully_completed_weeks)) + 1 if fully_completed_weeks else 1
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


# ── Fantasy Matchup: compare 2-4 players side by side ──────────────────────
#
# Position-specific stat sets -- a QB and a WR have nothing useful to
# compare on a shared stat grid, so each player gets their own
# position-appropriate rows instead. Two "kind"s:
#   - "avg": a counting stat, averaged per game (e.g. targets/game)
#   - "ratio": numerator/denominator computed from SEASON TOTALS, not an
#     average of each game's own ratio (yards-per-carry needs total yards
#     over total carries, not the mean of each game's YPC, which would let
#     a single small-sample game distort the season number)
#
# Each stat's "def" tag says which defensive category applies:
#   - "pass": always the team-level pass defense (only QBs pass, so the
#     existing team-level number IS the position-specific one already)
#   - "rush": position-specific for RB/QB (the only two scoped for rushing
#     splits -- see get_nfl_defense_by_position.py's own scope note),
#     team-level rush defense as the fallback for any other position
#   - "rec": position-specific for RB/WR/TE, team-level PASS defense as
#     the fallback (receiving yards move with a defense's overall pass
#     defense as a rough proxy when there's no position split for it)
POSITION_STAT_SETS: Dict[str, List[Dict[str, Any]]] = {
    "QB": [
        {"label": "Completions/G", "col": "completions", "kind": "avg", "def": "pass"},
        {"label": "Pass Att/G", "col": "attempts", "kind": "avg", "def": "pass"},
        {"label": "Pass Yds/G", "col": "passing_yards", "kind": "avg", "def": "pass"},
        {"label": "Pass TD/G", "col": "passing_tds", "kind": "avg", "def": "pass"},
        {"label": "INT/G", "col": "passing_interceptions", "kind": "avg", "def": "pass"},
        {"label": "Rush Att/G", "col": "carries", "kind": "avg", "def": "rush"},
        {"label": "Rush Yds/G", "col": "rushing_yards", "kind": "avg", "def": "rush"},
    ],
    "RB": [
        {"label": "Carries/G", "col": "carries", "kind": "avg", "def": "rush"},
        {"label": "Yds/Carry", "num": "rushing_yards", "den": "carries", "kind": "ratio", "def": "rush"},
        {"label": "Rush Yds/G", "col": "rushing_yards", "kind": "avg", "def": "rush"},
        {"label": "Targets/G", "col": "targets", "kind": "avg", "def": "rec"},
        {"label": "Receptions/G", "col": "receptions", "kind": "avg", "def": "rec"},
        {"label": "Rec Yds/G", "col": "receiving_yards", "kind": "avg", "def": "rec"},
    ],
    "WR": [
        {"label": "Targets/G", "col": "targets", "kind": "avg", "def": "rec"},
        {"label": "Receptions/G", "col": "receptions", "kind": "avg", "def": "rec"},
        {"label": "Rec Yds/G", "col": "receiving_yards", "kind": "avg", "def": "rec"},
        {"label": "Yds/Reception", "num": "receiving_yards", "den": "receptions", "kind": "ratio", "def": "rec"},
        {"label": "Rec TD/G", "col": "receiving_tds", "kind": "avg", "def": "rec"},
    ],
    "TE": [
        {"label": "Targets/G", "col": "targets", "kind": "avg", "def": "rec"},
        {"label": "Receptions/G", "col": "receptions", "kind": "avg", "def": "rec"},
        {"label": "Rec Yds/G", "col": "receiving_yards", "kind": "avg", "def": "rec"},
        {"label": "Rec TD/G", "col": "receiving_tds", "kind": "avg", "def": "rec"},
    ],
}

# Position-specific defense column, keyed by (category, position). Only the
# combinations get_nfl_defense_by_position.py actually computes -- anything
# else falls back to team-level via _team_level_defense below.
_POSITION_DEFENSE_COL = {
    ("rush", "RB"): "def_rb_rush_ypg",
    ("rush", "QB"): "def_qb_rush_ypg",
    ("rec", "RB"): "def_rb_rec_ypg",
    ("rec", "WR"): "def_wr_rec_ypg",
    ("rec", "TE"): "def_te_rec_ypg",
}


def _matchup_rank(raw_rank: Optional[float], low_rank_is_favorable: bool, total_teams: int = 32) -> Optional[int]:
    """Reframes a raw stat-based rank into a matchup-oriented rank where 1
    ALWAYS means the easiest matchup for the offense/player, regardless of
    which direction the underlying stat's own natural ranking runs.
    Without this, "32nd fewest yards allowed" -- correct, but requires
    realizing rank 32-of-32 fewest actually means the MOST allowed, i.e.
    the best matchup -- reads as confusing or backwards, which is exactly
    what a real user reported. Same low_rank_is_favorable parameter as
    _favorable_from_rank, for the same reason: which direction is
    favorable genuinely differs per stat, so it's never left implicit."""
    if raw_rank is None:
        return None
    return int(raw_rank) if low_rank_is_favorable else int(total_teams + 1 - raw_rank)


def _favorable_from_rank(rank: Optional[float], low_rank_is_favorable: bool, total_teams: int = 32) -> Optional[bool]:
    """True = favorable for the offense/player, False = tough, None =
    roughly average. Same top-10/bottom-10 threshold already used for
    color elsewhere in this file, just returned as an explicit boolean
    instead of a rank number the frontend would have to re-interpret.

    low_rank_is_favorable matters because "rank 1" means opposite things
    depending on the stat: for yards allowed or pressure generated, rank 1
    is the TOUGHEST for the offense (unfavorable). For a team's OWN sacks
    allowed, rank 1 is the BEST protection (favorable) -- the same
    generic "low rank = tough" assumption doesn't hold for both, and
    getting this backwards for one specific case already happened once
    reasoning about it by hand, hence making the direction an explicit
    parameter instead of leaving it implicit."""
    if rank is None:
        return None
    top_10, bottom_10 = (rank <= 10), (rank >= total_teams - 9)
    if low_rank_is_favorable:
        return True if top_10 else (False if bottom_10 else None)
    return False if top_10 else (True if bottom_10 else None)


def _player_team_and_position(player_df: pd.DataFrame, team_col: Optional[str], player_name: Optional[str] = None) -> tuple:
    """Current team and position_group for a player -- prefers the current
    roster (get_nfl_rosters.py) over the game log's own team/position
    columns, since a recent trade or signing means the game log's last
    row still shows wherever they last actually played, not where they
    are now (confirmed real: Kenneth Walker III's game log still showed
    Seattle after he signed with Kansas City). Falls back to the game
    log's own team/position if the player isn't found on a current
    roster (e.g. game log has data but the roster pull is stale/missing).
    """
    if player_name:
        rosters = get_nfl_rosters()
        if not rosters.empty and "full_name" in rosters.columns:
            name_norm = _normalize_loose(player_name)
            match = rosters[rosters["full_name"].apply(_normalize_loose) == name_norm]
            if not match.empty:
                row = match.iloc[0]
                team = row.get("team")
                position = row.get("position")
                if pd.notna(team):
                    return str(team), (str(position) if pd.notna(position) else None)

    if player_df.empty:
        return None, None
    last_row = player_df.iloc[-1]
    team = last_row.get(team_col) if team_col else None
    position = last_row.get("position_group") or last_row.get("position")
    return (str(team) if pd.notna(team) else None), (str(position) if pd.notna(position) else None)


def _game_results_for(player_df: pd.DataFrame, team_col: Optional[str], season_col: Optional[str], week_col: Optional[str]) -> pd.DataFrame:
    """W/L/T, signed point margin, and the actual final score for each row
    in player_df, based on that row's team, season, and week matched
    against the real schedule. Margin is always from the player's own
    team's perspective -- positive for a win by that many points, negative
    for a loss by that many, zero for a tie -- so a single number/operator
    filter (e.g. "margin < 7") naturally covers both a close win and a
    close loss without needing separate win/loss-specific thresholds.
    """
    empty = pd.DataFrame({
        "result": [None] * len(player_df), "margin": [None] * len(player_df),
        "team_score": [None] * len(player_df), "opp_score": [None] * len(player_df),
    }, index=player_df.index)

    if not team_col or not season_col or not week_col:
        return empty

    schedule = get_nfl_schedule()
    if schedule.empty:
        return empty

    results, margins, team_scores, opp_scores = [], [], [], []
    for _, row in player_df.iterrows():
        team, season, week = row.get(team_col), row.get(season_col), row.get(week_col)
        if pd.isna(team) or pd.isna(season) or pd.isna(week):
            results.append(None); margins.append(None); team_scores.append(None); opp_scores.append(None)
            continue
        game = schedule[
            (schedule["season"] == season) & (schedule["week"] == week)
            & ((schedule["home_team"] == team) | (schedule["away_team"] == team))
            & schedule["home_score"].notna()
        ]
        if game.empty:
            results.append(None); margins.append(None); team_scores.append(None); opp_scores.append(None)
            continue
        g = game.iloc[0]
        is_home = g["home_team"] == team
        team_score = g["home_score"] if is_home else g["away_score"]
        opp_score = g["away_score"] if is_home else g["home_score"]
        team_scores.append(float(team_score))
        opp_scores.append(float(opp_score))
        margins.append(float(team_score) - float(opp_score))
        if team_score > opp_score:
            results.append("W")
        elif team_score < opp_score:
            results.append("L")
        else:
            results.append("T")

    return pd.DataFrame(
        {"result": results, "margin": margins, "team_score": team_scores, "opp_score": opp_scores},
        index=player_df.index,
    )


def _team_record(team: str, season: int) -> Optional[Dict[str, int]]:
    """Season win-loss-tie record for one team, from completed games in the
    real schedule data. Ties are real and possible in the NFL (unlike MLB),
    so tracked as their own count rather than dropped or folded into losses."""
    schedule = get_nfl_schedule()
    if schedule.empty or not team:
        return None
    season_games = schedule[schedule["season"] == season]
    team_games = season_games[
        season_games["home_score"].notna()
        & ((season_games["home_team"] == team) | (season_games["away_team"] == team))
    ]

    wins = losses = ties = 0
    for _, g in team_games.iterrows():
        is_home = g["home_team"] == team
        team_score = g["home_score"] if is_home else g["away_score"]
        opp_score = g["away_score"] if is_home else g["home_score"]
        if team_score > opp_score:
            wins += 1
        elif team_score < opp_score:
            losses += 1
        else:
            ties += 1
    return {"wins": wins, "losses": losses, "ties": ties}


def _next_game_for_team(team: str, season: int) -> Optional[Dict[str, Any]]:
    """The single soonest unplayed game for a team, or None if their season
    is over / hasn't been scheduled."""
    schedule = get_nfl_schedule()
    if schedule.empty or not team:
        return None
    season_games = schedule[schedule["season"] == season]
    upcoming = season_games[
        season_games["home_score"].isna()
        & ((season_games["home_team"] == team) | (season_games["away_team"] == team))
    ].sort_values("week")
    if upcoming.empty:
        return None
    g = upcoming.iloc[0]
    is_home = g["home_team"] == team
    opponent = g["away_team"] if is_home else g["home_team"]
    return {"week": int(g["week"]), "opponent": str(opponent), "is_home": bool(is_home)}


def _position_specific_defense(category: str, position: Optional[str], opponent: str) -> Optional[Dict[str, Any]]:
    """Position-specific rank, only when get_nfl_defense_by_position.py
    actually covers this (category, position) combination -- returns None
    otherwise rather than falling back, since the caller now shows the
    team-level number as its own separate line rather than a substitute."""
    position_col = _POSITION_DEFENSE_COL.get((category, position))
    if not position_col:
        return None
    by_pos = get_nfl_defense_by_position()
    if by_pos.empty:
        return None
    latest_week = by_pos["week"].max()
    match = by_pos[(by_pos["week"] == latest_week) & (by_pos["team"].str.upper() == opponent.upper())]
    col = f"{position_col}_season"
    rank_col = f"{position_col}_rank_season"
    if match.empty or rank_col not in match.columns or pd.isna(match.iloc[0][rank_col]):
        return None
    row = match.iloc[0]
    return {
        "def_ypg": round(float(row[col]), 1) if pd.notna(row[col]) else None,
        "def_rank": int(row[rank_col]),
    }


def _team_level_defense(category: str, opponent: str) -> Optional[Dict[str, Any]]:
    """Team-level rank (team_stats.parquet, same source _upcoming_games()
    uses for 'as of right now') -- shown as its own line now, not just a
    fallback for when the position-specific split is missing. Verified
    against real data to use the identical rank-1-equals-fewest-yards
    convention as the position-specific file, so the same matchup-rank
    transform applies safely to both."""
    team_stats = get_nfl_team_stats()
    if team_stats.empty:
        return None
    prefix = "Defense Pass" if category in ("pass", "rec") else "Defense Rush"
    match = team_stats[team_stats["team"].str.upper() == opponent.upper()]
    if match.empty:
        return None
    row = match.iloc[0]
    ypg = row.get(f"{prefix} Yards Per Game")
    rank = row.get(f"Rank - {prefix} Yards Per Game")
    if pd.isna(ypg) or pd.isna(rank):
        return None
    return {"def_ypg": round(float(ypg), 1), "def_rank": int(rank)}


def get_fantasy_matchup_current_week(players: List[str]) -> Dict[str, Any]:
    """Side-by-side current-week comparison for 2-4 players: position-
    specific season stat averages, a single consolidated matchup-context
    block (not repeated per stat row -- every pass-catching stat shares
    the same underlying defensive category, so showing it five times was
    pure redundancy), plus the same projected game script shown on the
    Matchup page, reused directly rather than recomputed."""
    df = get_nfl_stats()
    col = _player_col(df)
    team_col = _team_col(df)
    season = _current_nfl_season()
    team_stats_df = get_nfl_team_stats()

    results = []
    for player in players:
        player_norm = _normalize(player)
        player_df = df[df[col].str.lower().str.strip() == player_norm].copy()
        if player_df.empty:
            results.append({"player": player, "error": "No stats found for this player"})
            continue

        team, position = _player_team_and_position(player_df, team_col, player)
        stat_set = POSITION_STAT_SETS.get(position or "", [])
        games_played = max(int(len(player_df)), 1)

        stats = []
        categories_seen = []
        for spec in stat_set:
            if spec["kind"] == "avg":
                total = pd.to_numeric(player_df.get(spec["col"]), errors="coerce").fillna(0).sum()
                value = round(float(total) / games_played, 1)
            else:
                num = pd.to_numeric(player_df.get(spec["num"]), errors="coerce").fillna(0).sum()
                den = pd.to_numeric(player_df.get(spec["den"]), errors="coerce").fillna(0).sum()
                value = round(float(num) / den, 1) if den else None
            stats.append({"label": spec["label"], "value": value})
            if spec["def"] not in categories_seen:
                categories_seen.append(spec["def"])

        next_game = _next_game_for_team(team, season) if team else None
        game_script = None
        matchup_context = None
        if next_game:
            opponent = next_game["opponent"]

            # One opponent-defense line per UNIQUE category in this
            # player's stat set (usually just one), not one per stat row.
            opp_defense = []
            for category in categories_seen:
                is_rush = category == "rush"
                stat_word = "Rush Yds" if is_rush else "Rec Yds"
                team_stat_word = "Rush D" if is_rush else "Pass D"

                pos_info = _position_specific_defense(category, position, opponent)
                if pos_info:
                    opp_defense.append({
                        "label": f"{stat_word} Allowed to {position}s",
                        "value": pos_info["def_ypg"],
                        "rank": _matchup_rank(pos_info["def_rank"], low_rank_is_favorable=False),
                        "rank_word": "easiest",
                        "granularity": position,
                        "favorable": _favorable_from_rank(pos_info["def_rank"], low_rank_is_favorable=False),
                    })

                team_info = _team_level_defense(category, opponent)
                if team_info:
                    opp_defense.append({
                        "label": f"Total Team {team_stat_word}",
                        "value": team_info["def_ypg"],
                        "rank": _matchup_rank(team_info["def_rank"], low_rank_is_favorable=False),
                        "rank_word": "easiest",
                        "granularity": "team",
                        "favorable": _favorable_from_rank(team_info["def_rank"], low_rank_is_favorable=False),
                    })

            opp_pass_rush = None
            if not team_stats_df.empty:
                match = team_stats_df[team_stats_df["opponent_team"].str.upper() == opponent.upper()]
                if not match.empty:
                    row = match.iloc[0]
                    value = row.get("Defensive Sacks + QB Hits Per Game")
                    rank = row.get("Rank - Defensive Sacks + QB Hits")
                    if pd.notna(value) and pd.notna(rank):
                        opp_pass_rush = {
                            "label": "Opp Sacks + QB Hits",
                            "value": round(float(value), 1),
                            "rank": _matchup_rank(int(rank), low_rank_is_favorable=False),
                            "rank_word": "easiest",
                            "favorable": _favorable_from_rank(int(rank), low_rank_is_favorable=False),  # rank 1 = most pressure = unfavorable
                        }

            own_pass_block = None
            if team and not team_stats_df.empty:
                match = team_stats_df[team_stats_df["team"].str.upper() == team.upper()]
                if not match.empty:
                    row = match.iloc[0]
                    value = row.get("Sacks + QB Hits Allowed Per Game")
                    rank = row.get("Rank - Sacks + QB Hits Allowed")
                    if pd.notna(value) and pd.notna(rank):
                        own_pass_block = {
                            "label": "Own Sacks + QB Hits Allowed",
                            "value": round(float(value), 1),
                            "rank": _matchup_rank(int(rank), low_rank_is_favorable=True),
                            "rank_word": "easiest",
                            "favorable": _favorable_from_rank(int(rank), low_rank_is_favorable=True),  # rank 1 = fewest sacks+hits allowed = best protection = favorable
                        }

            matchup_context = {
                "opp_defense": opp_defense,
                "opp_pass_rush": opp_pass_rush,
                "own_pass_block": own_pass_block,
            }

            away, home = (team, opponent) if not next_game["is_home"] else (opponent, team)
            projection = get_game_script_projection(f"{away} @ {home}")
            if "error" not in projection:
                game_script = projection["home"] if next_game["is_home"] else projection["away"]

        results.append({
            "player": player,
            "team": team,
            "position": position,
            "team_record": _team_record(team, season) if team else None,
            "opponent": next_game["opponent"] if next_game else None,
            "opponent_record": _team_record(next_game["opponent"], season) if next_game else None,
            "is_home": next_game["is_home"] if next_game else None,
            "week": next_game["week"] if next_game else None,
            "stats": stats,
            "matchup_context": matchup_context,
            "game_script": game_script,
        })

    return {"mode": "current_week", "players": results}


def get_fantasy_matchup_season(players: List[str]) -> Dict[str, Any]:
    """Remaining-schedule comparison for 2-4 players: every remaining week
    for each player's team, with the opponent's defensive rank (position-
    specific where covered) and an explicit row for a bye week rather than
    silently skipping that week number, which reads as a data gap."""
    df = get_nfl_stats()
    col = _player_col(df)
    team_col = _team_col(df)
    season = _current_nfl_season()
    schedule = get_nfl_schedule()

    results = []
    for player in players:
        player_norm = _normalize(player)
        player_df = df[df[col].str.lower().str.strip() == player_norm].copy()
        if player_df.empty:
            results.append({"player": player, "error": "No stats found for this player"})
            continue

        team, position = _player_team_and_position(player_df, team_col, player)
        rem_schedule = []
        if team and not schedule.empty:
            season_games = schedule[schedule["season"] == season]
            team_games = season_games[
                season_games["home_score"].isna()
                & ((season_games["home_team"] == team) | (season_games["away_team"] == team))
            ].sort_values("week")

            if not team_games.empty:
                played_weeks = set(team_games["week"].astype(int))
                full_range = range(int(team_games["week"].min()), int(team_games["week"].max()) + 1)
                primary_category = "rush" if position in ("RB", "QB") else "rec" if position in ("WR", "TE") else "pass"

                for week in full_range:
                    if week not in played_weeks:
                        rem_schedule.append({"week": week, "is_bye": True})
                        continue
                    g = team_games[team_games["week"] == week].iloc[0]
                    is_home = g["home_team"] == team
                    opponent = str(g["away_team"] if is_home else g["home_team"])
                    rank_info = _position_specific_defense(primary_category, position, opponent)
                    granularity = position
                    if not rank_info:
                        rank_info = _team_level_defense(primary_category, opponent)
                        granularity = "team"
                    rem_schedule.append({
                        "week": week,
                        "is_bye": False,
                        "opponent": opponent,
                        "is_home": bool(is_home),
                        "def_rank": rank_info["def_rank"] if rank_info else None,
                        "def_granularity": granularity,
                    })

        results.append({
            "player": player,
            "team": team,
            "position": position,
            "schedule": rem_schedule,
        })

    return {"mode": "season", "players": results}


# ── NFL In/Out: who picks up more volume when a teammate is out ───────────
#
# NFL's box-score stats file has no way to distinguish "played and recorded
# a zero" from "wasn't active that week" -- unlike NBA's data, which has an
# explicit played/game_played column. get_nfl_snap_counts() (real snap
# participation, sourced from Pro Football Reference via nflverse) fills
# that gap: presence in that file for a given player-week is treated as
# "played," matching real data (~5.8% of games for a normally-regular
# player show up at under half their usual snap share while still
# technically playing -- checked directly rather than assumed -- but that's
# infrequent enough that a simple played/did-not-play split is fine for
# this rather than adding a third "limited" category).
IN_OUT_STATS = ["carries", "rushing_yards", "targets", "receptions", "receiving_yards"]


def _normalize_loose(name: str) -> str:
    """Like _normalize(), but also strips common generational suffixes
    (Jr./Sr./II/III/IV). Used only for matching names BETWEEN the box-score
    stats file and get_nfl_snap_counts() -- two independent sources with no
    shared player ID, confirmed to spell suffixes inconsistently with each
    other (e.g. "Brian Robinson" vs. "Brian Robinson Jr."). Kept separate
    from _normalize() since being this aggressive isn't necessary or safe
    for every other name-matching call site in this file.
    """
    name = name.strip().lower().replace(".", "")
    tokens = name.split()
    suffixes = {"jr", "sr", "ii", "iii", "iv"}
    while tokens and tokens[-1] in suffixes:
        tokens.pop()
    return " ".join(tokens)


def get_nfl_season_screener(season: int, position: Optional[str], filters: List[str]) -> List[Dict[str, Any]]:
    """Season-long stat screener: which players meet ALL of a set of
    stat thresholds for one season (e.g. "1000+ rushing yards AND 250+
    carries"). Each filter is a simple string like "carries>=250" or
    "targets<=50" -- parsed here rather than requiring a JSON body, since
    this is a read-only query that fits the same GET-with-query-params
    convention already used everywhere else in this file.
    """
    df = get_nfl_season_totals()
    if df.empty:
        return []

    season_df = df[df["season"] == season].copy()
    if position and "position_group" in season_df.columns:
        season_df = season_df[season_df["position_group"].str.upper() == position.upper()]

    parsed_filters = []
    for f in filters:
        for op in (">=", "<="):
            if op in f:
                stat, _, value_str = f.partition(op)
                stat = stat.strip()
                try:
                    value = float(value_str.strip())
                except ValueError:
                    continue
                if stat in season_df.columns:
                    parsed_filters.append((stat, op, value))
                break

    for stat, op, value in parsed_filters:
        col = pd.to_numeric(season_df[stat], errors="coerce").fillna(0)
        season_df = season_df[col >= value] if op == ">=" else season_df[col <= value]

    if season_df.empty:
        return []

    # Always include every stat involved in an active filter, plus the
    # small set of identifying columns, rather than every possible stat
    # column -- keeps the response focused on what was actually asked for.
    filter_stats = [stat for stat, _, _ in parsed_filters]
    id_cols = [c for c in ("player", "team", "position", "position_group", "games_played") if c in season_df.columns]
    display_cols = id_cols + [s for s in filter_stats if s not in id_cols]

    sort_col = filter_stats[0] if filter_stats else (id_cols[0] if id_cols else None)
    if sort_col and sort_col in season_df.columns:
        season_df = season_df.sort_values(sort_col, ascending=False)

    out = []
    for _, row in season_df.iterrows():
        entry = {}
        for col in display_cols:
            val = row.get(col)
            if pd.isna(val):
                entry[col] = None
            elif isinstance(val, (int, float)) and col not in ("player", "team", "position", "position_group"):
                entry[col] = round(float(val), 1)
            else:
                entry[col] = str(val)
        out.append(entry)
    return out


def get_nfl_teammates(player: str) -> List[str]:
    """Every player who has shared a team with *player* in a game, per
    get_nfl_snap_counts() -- mirrors get_teammates() in data/nba.py."""
    snaps = get_nfl_snap_counts()
    if snaps.empty:
        return []
    player_norm = _normalize_loose(player)
    player_rows = snaps[snaps["player"].apply(_normalize_loose) == player_norm]
    if player_rows.empty:
        return []
    team_games = player_rows[["game_id", "team"]].drop_duplicates()
    merged = snaps.merge(team_games, on=["game_id", "team"])
    teammates = merged["player"].dropna().unique().tolist()
    return sorted(t for t in teammates if _normalize_loose(t) != player_norm)


def get_nfl_in_out(player_a: str, exclude: List[str]) -> Dict[str, Any]:
    """Compare player_a's volume stats (carries/targets/receptions/yards)
    for weeks a specific teammate (or teammates) played versus weeks they
    didn't -- same with/without logic as data/nba.py's get_in_out(), keyed
    on (season, week) instead of (date, team) to match NFL's weekly rather
    than nightly schedule.
    """
    exclude = [e for e in (exclude or []) if e]
    stats_df = get_nfl_stats()
    snaps = get_nfl_snap_counts()
    col = _player_col(stats_df)
    season_col = _season_col(stats_df)
    week_col = _week_col(stats_df)

    if snaps.empty or not season_col or not week_col:
        return {"player": player_a, "exclude": exclude, "games_with": 0, "games_without": 0, "with": {}, "without": {}}

    player_norm = _normalize(player_a)
    anchor_df = stats_df[stats_df[col].str.lower().str.strip() == player_norm].copy()
    if anchor_df.empty:
        return {"player": player_a, "exclude": exclude, "games_with": 0, "games_without": 0, "with": {}, "without": {}}

    # (season, week) pairs where a given player actually played, from real
    # snap participation -- not just "recorded a stat."
    def played_weeks(name: str) -> set:
        norm = _normalize_loose(name)
        rows = snaps[snaps["player"].apply(_normalize_loose) == norm]
        return set(zip(rows["season"], rows["week"]))

    anchor_df["_key"] = list(zip(anchor_df[season_col], anchor_df[week_col]))
    exc_key_sets = [played_weeks(e) for e in exclude]

    anchor_keys = set(anchor_df["_key"])
    with_keys = anchor_keys.copy()
    for eks in exc_key_sets:
        with_keys = with_keys & eks
    without_keys = anchor_keys.copy()
    for eks in exc_key_sets:
        without_keys = without_keys - eks

    df_with = anchor_df[anchor_df["_key"].isin(with_keys)]
    df_without = anchor_df[anchor_df["_key"].isin(without_keys)]

    def avg_stats(sub_df: pd.DataFrame) -> Dict[str, Optional[float]]:
        result = {}
        for s in IN_OUT_STATS:
            if s not in sub_df.columns:
                continue
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


def _weekly_scoring_ranks(season: int, week: int) -> Dict[str, int]:
    """Rank every team's implied point total for one specific week (not a
    season-long average -- how this week's projection compares to this
    week's other 31 teams). Reuses the exact same spread+total formula as
    team_section() below. Rank 1 = highest projected total that week."""
    schedule = get_nfl_schedule()
    week_games = schedule[(schedule["season"] == season) & (schedule["week"] == week)]

    implied: Dict[str, float] = {}
    for _, g in week_games.iterrows():
        spread_line, total_line = g.get("spread_line"), g.get("total_line")
        if pd.isna(spread_line) or pd.isna(total_line):
            continue
        home_team, away_team = str(g["home_team"]).upper(), str(g["away_team"]).upper()
        implied[home_team] = float(total_line) / 2 + float(spread_line) / 2
        implied[away_team] = float(total_line) / 2 - float(spread_line) / 2

    ranked = sorted(implied.items(), key=lambda x: x[1], reverse=True)
    return {team: i + 1 for i, (team, _) in enumerate(ranked)}


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

    # Prefer the daily-refreshed game_lines.parquet (get_game_lines.py) over
    # the schedule's own baked-in spread_line/total_line when today's
    # pipeline has a line for this matchup: same game, a fresher number,
    # tied to actual current sportsbook pricing rather than nflverse's own
    # once-a-day sync from a third-party source. Falls back to the
    # schedule's line when there's no match yet (a game too far out for
    # lines to be posted, or the daily game-lines pipeline hasn't run) so
    # nothing regresses for games the new source doesn't cover.
    #
    # get_nfl_game_lines() is keyed by full Odds-API team names ("Kansas
    # City Chiefs"), while the schedule (and this function's own
    # home_team/away_team, parsed from the matchup string) use nflverse
    # abbreviations ("KC") -- confirmed by direct inspection of both
    # nfl_schedule.parquet (abbreviations) and NFL_Props.parquet (full
    # names, from the same Odds API get_game_lines.py reads). See
    # _nfl_game_lines_by_abbr()'s own comment for the NFL_TEAM_ABBR bridge
    # that resolves this mismatch.
    game_line_row = _nfl_game_lines_by_abbr().get((home_team, away_team))
    if game_line_row is not None and pd.notna(game_line_row.get("spread_line")):
        # Already stored in THIS app's own spread_line convention (positive
        # = home favored) by get_game_lines.py -- no sign flip needed here.
        spread_line = game_line_row.get("spread_line")
        total_line = game_line_row.get("total_line")
    else:
        spread_line = game_row.get("spread_line")
        total_line = game_row.get("total_line")

    if pd.isna(spread_line):
        return {"matchup": matchup, "away_team": away_team, "home_team": home_team, "error": "No line available for this game yet"}

    # spread_line is the home team's spread: POSITIVE = home favored by that
    # many points (confirmed against real data -- LAC @ +10.5 home was
    # actually a 10.5-point favorite, the opposite of the initially assumed
    # convention). Implied full-game margin is the mirror for each side.
    home_margin = float(spread_line)
    away_margin = -float(spread_line)

    game_script = get_nfl_team_game_script()
    weekly_ranks = _weekly_scoring_ranks(int(game_row["season"]), int(game_row["week"])) if pd.notna(game_row.get("week")) else {}

    def team_section(team: str, margin: float) -> Dict[str, Any]:
        situation = _implied_situation(margin)

        # Verified formula: this team's implied point total is half the
        # game total, shifted by half their margin -- confirmed against a
        # real example (PHI home, spread 8.5, total 47.5 -> PHI implied
        # 28.0, DAL implied 19.5, sums back to the full 47.5). Works
        # uniformly for both home and away since `margin` passed in here
        # is already correctly signed for whichever side is being built.
        implied_total = None if pd.isna(total_line) else round(float(total_line) / 2 + margin / 2, 1)

        # Weekly (not season-long) scoring rank -- rank 1 = most points
        # generally means MORE fantasy production for that team's players,
        # the opposite direction from a yards-allowed rank where rank 1 is
        # tough for the offense. Explicit low_rank_is_favorable=True here
        # for the same reason it's explicit everywhere else in this file:
        # getting this backwards for one specific stat already happened
        # once, so the direction is never left implicit.
        weekly_rank = weekly_ranks.get(team.upper())
        weekly_rank_favorable = _favorable_from_rank(weekly_rank, low_rank_is_favorable=True) if weekly_rank else None

        row = game_script[game_script["team"].str.upper() == team]
        if row.empty:
            return {
                "team": team, "implied_situation": situation, "implied_total": implied_total,
                "weekly_scoring_rank": weekly_rank, "weekly_scoring_favorable": weekly_rank_favorable,
                "error": "No game script data for this team",
            }
        row = row.iloc[0]

        projected_pass_pct = _projected_pass_pct(row, situation)
        baseline_pass_pct = row.get("pass_pct_neutral")

        return {
            "team": team,
            "implied_situation": situation,
            "implied_total": implied_total,
            "weekly_scoring_rank": weekly_rank,
            "weekly_scoring_favorable": weekly_rank_favorable,
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


def get_nfl_usage_players() -> List[str]:
    """Player list for the Usage Trend page specifically -- reads directly
    from get_nfl_player_week_usage(), the SAME source get_player_usage_trend()
    below actually queries. get_players() (used by Fantasy Matchup/In-Out)
    reads the legacy Player_Stats_Weekly file, whose full display names
    ("Trey McBride") don't match this pipeline's abbreviated ones
    ("T.McBride") under any normalization -- so a name picked from that
    dropdown never matched a row here, and the trend page came back empty
    for every player, no matter who was selected. Same fix already applied
    to Game Log via get_game_log_players(), for the identical reason.
    """
    df = get_nfl_player_week_usage()
    if df.empty or "player" not in df.columns:
        return []
    return sorted(df["player"].dropna().unique().tolist())


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
        # Counting stats for every situational slice the pbp pipeline
        # produces -- discovered from the frame rather than hardcoded, so
        # adding a split in get_nfl_pbp.py (fourth down, two-minute) shows up
        # here without a second edit in a file nobody would think to open.
        numeric_cols = [
            f"{prefix}{stat}"
            for prefix in USAGE_PREFIXES
            for stat in USAGE_COUNT_STATS
            if f"{prefix}{stat}" in sub.columns
        ]
        players = sub.groupby(["player_id", "player"], as_index=False)[numeric_cols].sum()
        # Recompute shares from the summed totals rather than averaging each
        # week's already-computed share -- averaging shares across weeks of
        # different pass volume would over-weight a low-volume week.
        for prefix in USAGE_PREFIXES:
            for share_col, source_col in (
                (f"{prefix}target_share", f"{prefix}targets"),
                (f"{prefix}air_yards_share", f"{prefix}air_yards"),
                (f"{prefix}rush_share", f"{prefix}carries"),
            ):
                if source_col not in players.columns:
                    continue
                total = players[source_col].sum()
                players[share_col] = (players[source_col] / total) if total else 0
        players = players.sort_values("targets", ascending=False)

    players = _attach_position(players)

    return {
        "team": team,
        "week": week,
        "weeks_available": _weeks_for_team(df, team),
        # Which situational toggles the UI may offer. The third-down columns
        # only exist in files written after that split was added to
        # get_nfl_pbp.py, so between deploying the code and the next workflow
        # run this list is short by one -- and the page has to hide the toggle
        # rather than show one that silently returns zeroes.
        "splits_available": [p or "all" for p in USAGE_PREFIXES
                             if f"{p}targets" in players.columns],
        "totals": _usage_totals(players),
        # fillna only on the numbers. A blanket fillna(0) turned a player the
        # roster pull hasn't got into position "0", which then renders as a
        # position chip reading 0.
        "players": _fill_numeric(players).to_dict(orient="records"),
    }


def _fill_numeric(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    num = out.select_dtypes(include="number").columns
    out[num] = out[num].fillna(0)
    return out.astype(object).where(pd.notna(out), None)


# Situational slices produced by get_nfl_pbp.py. "" is all plays; the rest are
# strict subsets of it.
USAGE_PREFIXES = ("", "rz_", "third_")
USAGE_COUNT_STATS = (
    "targets", "receptions", "receiving_yards", "air_yards", "receiving_tds",
    "carries", "rushing_yards", "rushing_tds",
)


def _attach_position(players: pd.DataFrame) -> pd.DataFrame:
    """Position from the current roster, joined on player_id.

    On id, not name: the play-by-play abbreviates ("A.St. Brown"), so name
    matching against a roster's "Amon-Ra St. Brown" needs fuzzy logic that
    the shared id makes unnecessary.
    """
    if players.empty or "player_id" not in players.columns:
        return players
    rosters = get_nfl_rosters()
    if rosters.empty or "player_id" not in rosters.columns or "position" not in rosters.columns:
        players["position"] = None
        return players
    lookup = rosters.drop_duplicates(subset=["player_id"])[["player_id", "position"]]
    return players.merge(lookup, on="player_id", how="left")


def _weeks_for_team(df: pd.DataFrame, team: str) -> List[int]:
    sub = df[df["posteam"].str.lower() == team.lower().strip()]
    if sub.empty or "week" not in sub.columns:
        return []
    return sorted(int(w) for w in sub["week"].dropna().unique())


def _usage_totals(players: pd.DataFrame) -> Dict[str, Any]:
    """Team touch totals per slice, for the page header.

    Deliberately "touches" and not "plays": these are targets plus carries by
    skill-position players, which excludes sacks, scrambles credited
    elsewhere, kneels and spikes. Calling it plays would be wrong by a few
    every week, and the label is what makes the number trustworthy.
    """
    out: Dict[str, Any] = {}
    for prefix in USAGE_PREFIXES:
        t_col, c_col = f"{prefix}targets", f"{prefix}carries"
        targets = float(players[t_col].sum()) if t_col in players.columns else 0.0
        carries = float(players[c_col].sum()) if c_col in players.columns else 0.0
        touches = targets + carries
        out[prefix or "all"] = {
            "targets": targets,
            "carries": carries,
            "touches": touches,
            "pass_pct": round(targets / touches * 100, 1) if touches else None,
        }
    return out


def get_player_usage_trend(player: str, stat: str = "targets") -> Dict[str, Any]:
    """One player's week-by-week share of his team's usage, plus every
    teammate's line and the team's own weekly volume.

    All three are needed together and that is the whole point of the page.
    Share is zero-sum, so a rising line means nothing until you can see whose
    share it came from -- hence the teammates. And a share is a share OF
    something, so 25% of 30 targets and 25% of 45 are different weeks -- hence
    the team volume.
    """
    valid = {"targets": "target_share", "carries": "rush_share", "air_yards": "air_yards_share"}
    if stat not in valid:
        raise ValueError(f"stat must be one of {sorted(valid)}")
    share_col = valid[stat]

    df = get_nfl_player_week_usage()
    empty = {"player": player, "stat": stat, "team": None, "position": None,
             "weeks": [], "series": [], "teammates": []}
    if df.empty:
        return empty

    name_norm = _normalize_loose(player)
    rows = df[df["player"].apply(_normalize_loose) == name_norm]
    if rows.empty:
        return empty

    team = rows.sort_values("week")["posteam"].iloc[-1]
    team_rows = df[df["posteam"] == team]
    weeks = sorted(int(w) for w in team_rows["week"].dropna().unique())

    by_week = rows.set_index("week")
    team_totals = team_rows.groupby("week")[stat].sum()

    series = []
    for w in weeks:
        r = by_week.loc[w] if w in by_week.index else None
        if r is not None and isinstance(r, pd.DataFrame):  # duplicate week rows
            r = r.iloc[0]
        series.append({
            "week": w,
            "value": float(r[stat]) if r is not None else 0.0,
            "share": float(r[share_col]) if r is not None and pd.notna(r[share_col]) else 0.0,
            "team_total": float(team_totals.get(w, 0.0)),
        })

    # Teammates, drawn in grey behind the subject. Capped at the ones who
    # actually matter: anyone averaging under 5% of the team's usage is a line
    # sitting on the axis adding noise, not context.
    teammates = []
    for (pid, name), grp in team_rows.groupby(["player_id", "player"]):
        if _normalize_loose(name) == name_norm:
            continue
        mean_share = grp[share_col].fillna(0).mean()
        if not mean_share or mean_share < 0.05:
            continue
        g = grp.set_index("week")
        teammates.append({
            "player": name,
            "series": [
                {"week": w, "share": float(g.loc[w, share_col]) if w in g.index and pd.notna(g.loc[w, share_col]) else 0.0}
                for w in weeks
            ],
        })
    teammates.sort(key=lambda t: -sum(p["share"] for p in t["series"]))

    positions = _attach_position(rows.head(1).copy())
    position = positions["position"].iloc[0] if "position" in positions.columns and not positions.empty else None

    return {
        "player": rows["player"].iloc[0],
        "stat": stat,
        "team": team,
        "position": position if isinstance(position, str) else None,
        "weeks": weeks,
        "series": series,
        "teammates": teammates,
    }


# ---------------------------------------------------------------------------
# Weekly league-wide mismatch finder -- scans every game on a week's slate
# for the biggest statistical edges, instead of checking one matchup at a
# time on the Matchup page.
#
# All six categories share one scoring idea: for a given stat pairing (an
# offense stat and its comparable defense stat), a mismatch score is
# defense_rank - offense_rank -- zero means the two are equally ranked (a
# neutral matchup), positive means the offense has the edge (its rank number
# is better than the defense's), negative means the defense has the edge.
# For passing, rushing, scoring, and sacks, "offense succeeding" and
# "defense failing" point the SAME direction (more passing yards is good for
# the offense and bad for the defense at once), so sorting this score
# descending always surfaces the biggest one-sided mismatch.
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
        # A week only counts as "done" once EVERY one of its games has a
        # score -- checking for ANY completed game (the old logic) meant
        # the page flipped to next week as soon as a single early game
        # (e.g. Thursday night) finished, well before the rest of that
        # week's games, including Monday Night Football, had been played.
        week_totals = season_games.groupby("week").size()
        week_completed = season_games[season_games["home_score"].notna()].groupby("week").size()
        fully_completed_weeks = [w for w in week_totals.index if week_completed.get(w, 0) == week_totals[w]]
        week = int(max(fully_completed_weeks)) + 1 if fully_completed_weeks else 1

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
            "score": round(float(def_rank - off_rank), 1),
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


# ---------------------------------------------------------------------------
# Hit Rate Sheet -- bulk per-market scan across every NFL player currently
# priced on a market, generalizing get_game_log()'s per-player-per-week
# grouping/sorting pattern to scan every player at once instead of one at a
# time. See app/data/hit_rate.py for the shared, sport-agnostic
# grading/window-splitting helpers this reuses.
# ---------------------------------------------------------------------------

NFL_RECENT_GAMES = RECENT_WINDOW["nfl"]

# Hit-rate-sheet market key -> player_box_stats.parquet column, or a
# derivation function taking one game's row and returning a float. Keys
# match get_props.py's own NFL market keys exactly (no prefix stripping
# needed here, unlike MLB's `batter_*` markets -- see app/data/mlb.py).
#
# Longest-play markets, 1st/last TD scorer, defensive stats and kicking
# markets are deliberately left out -- none of that data exists anywhere in
# this pipeline (confirmed by direct inspection of player_box_stats.parquet).
NFL_MARKET_STAT: Dict[str, Any] = {
    "pass_yds": "passing_yards",
    "pass_tds": "passing_tds",
    "pass_attempts": "attempts",
    "pass_completions": "completions",
    "pass_interceptions": "passing_interceptions",
    "rush_yds": "rushing_yards",
    "rush_attempts": "carries",
    "rush_tds": "rushing_tds",
    "receptions": "receptions",
    "reception_yds": "receiving_yards",
    "reception_tds": "receiving_tds",
    "pass_rush_reception_yds": lambda r: (r.get("passing_yards") or 0) + (r.get("rushing_yards") or 0) + (r.get("receiving_yards") or 0),
    "rush_reception_yds": lambda r: (r.get("rushing_yards") or 0) + (r.get("receiving_yards") or 0),
    "pass_rush_yds": lambda r: (r.get("passing_yards") or 0) + (r.get("rushing_yards") or 0),
    # Yes/No market -- graded against a fixed effective line of 1 (see
    # get_nfl_hit_rate_sheet), same treatment as MLB's pitcher_record_a_win.
    "anytime_td": lambda r: 1.0 if ((r.get("rushing_tds") or 0) + (r.get("receiving_tds") or 0)) >= 1 else 0.0,
}

_NFL_YES_NO_MARKETS = {"anytime_td"}

_NFL_PROPS_META_COLS = {"line_id", "player", "market", "line", "fetched_at", "commence_time", "home_team", "away_team", "is_live"}

# player_box_stats.parquet/get_nfl_schedule() key every team by its
# nflverse abbreviation ("KC"), but get_props.py's home_team/away_team
# columns spell the full name ("Kansas City Chiefs") -- confirmed by direct
# inspection of both files, and there's no existing bridge between the two
# conventions anywhere else in this file, so building the current-season
# name is needed just for matching a player's own team against the props
# row's home_team/away_team to resolve an opponent.
NFL_TEAM_ABBR: Dict[str, str] = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LA", "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN",
    "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
}


def _nfl_stat_value(row, spec) -> float:
    try:
        val = spec(row) if callable(spec) else row.get(spec)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return 0.0
        return float(val)
    except Exception:
        return 0.0


def _nfl_is_number(v) -> bool:
    try:
        f = float(v)
        return not math.isnan(f)
    except (TypeError, ValueError):
        return False


# Same problem get_mlb_hit_rate_sheet() has, and the same fix -- see that
# function's cached helpers for the full explanation. Without this, the
# default "All Markets" view (and every keystroke in the player search box,
# which doesn't narrow the per-market work at all) re-filters, re-sorts and
# -- for derived markets -- re-runs a row-wise .apply() over the ENTIRE
# season's player_box_stats for every one of ~14 markets, on every request.
# get_nfl_player_box_stats() itself is already cached (OTHER_TTL), but the
# season-filter/sort and per-market grouping done on top of it were not.
@ttl_cache(OTHER_TTL)
def _nfl_current_season_frame() -> "tuple[pd.DataFrame, str, Optional[str]]":
    df = get_nfl_player_box_stats()
    if df.empty:
        return df, "", None
    col = _player_col(df)
    season_col = _season_col(df)
    week_col = _week_col(df)
    team_col = _team_col(df)

    season = _current_nfl_season()
    d = df.copy()
    if season_col:
        d = d[d[season_col] == season]

    sort_cols = [c for c in [season_col, week_col] if c and c in d.columns]
    if sort_cols:
        d = d.sort_values(sort_cols)

    return d, col, team_col


@ttl_cache(OTHER_TTL)
def _nfl_latest_team_by_player() -> Dict[str, str]:
    d, col, team_col = _nfl_current_season_frame()
    if d.empty or not team_col:
        return {}
    latest = d.groupby(col, as_index=False).tail(1)
    return dict(zip(latest[col].astype(str).apply(_normalize_loose), latest[team_col]))


@ttl_cache(OTHER_TTL)
def _nfl_values_by_player(market: str) -> Dict[str, List[float]]:
    d, col, _team_col_name = _nfl_current_season_frame()
    if d.empty:
        return {}
    spec = NFL_MARKET_STAT[market]
    if callable(spec):
        stat_values = d.apply(lambda r: _nfl_stat_value(r, spec), axis=1)
    else:
        stat_values = pd.to_numeric(d[spec], errors="coerce").fillna(0.0)
    series = pd.DataFrame({"_player": d[col].astype(str), "stat_value": stat_values})
    return {_normalize_loose(name): g["stat_value"].tolist() for name, g in series.groupby("_player")}


@ttl_cache(OTHER_TTL)
def _nfl_game_lines_lookup() -> Dict[tuple, dict]:
    """(home_team, away_team) -> that game's game_lines.parquet row, for
    the Hit Rate Sheet's Game Line / Total columns. Built once per
    OTHER_TTL window, not once per output row -- same discipline as the
    cached helpers above.

    Keyed by the full Odds-API team names get_props("nfl") itself already
    carries as home_team/away_team (confirmed by direct inspection of
    NFL_Props.parquet: "Kansas City Chiefs", not "KC") -- get_game_lines.py
    is sourced from the same API, so this join needs no abbreviation
    bridging, unlike get_game_script_projection()'s join against the
    nflverse schedule below.
    """
    lines = get_nfl_game_lines()
    if lines.empty or "home_team" not in lines.columns or "away_team" not in lines.columns:
        return {}
    return {(r["home_team"], r["away_team"]): r for r in lines.to_dict(orient="records")}


@ttl_cache(OTHER_TTL)
def _nfl_game_lines_by_abbr() -> Dict[tuple, dict]:
    """Same game_lines.parquet rows as _nfl_game_lines_lookup() above, but
    keyed by (home_abbr, away_abbr) instead of the raw Odds-API full team
    names -- for get_game_script_projection()'s join against
    get_nfl_schedule(), which (confirmed by direct inspection of
    nfl_schedule.parquet) keys every team by its nflverse abbreviation
    ("KC"), not the full name ("Kansas City Chiefs") get_game_lines.py
    writes. NFL_TEAM_ABBR is the existing full-name -> abbreviation bridge,
    reused here rather than duplicated.
    """
    lines = get_nfl_game_lines()
    if lines.empty or "home_team" not in lines.columns or "away_team" not in lines.columns:
        return {}
    out: Dict[tuple, dict] = {}
    for r in lines.to_dict(orient="records"):
        home_abbr = NFL_TEAM_ABBR.get(r.get("home_team"))
        away_abbr = NFL_TEAM_ABBR.get(r.get("away_team"))
        if home_abbr and away_abbr:
            out[(home_abbr, away_abbr)] = r
    return out


def get_nfl_hit_rate_sheet_players() -> List[str]:
    """Distinct player names with at least one live prop right now -- see
    get_mlb_hit_rate_sheet_players()'s identical docstring in
    app/data/mlb.py. Sourced from get_props("nfl"), the same call
    get_nfl_hit_rate_sheet() itself makes."""
    from app.data.props import get_props
    props_rows = get_props("nfl")
    if not props_rows:
        return []
    names = {str(r.get("player", "")).strip() for r in props_rows if r.get("player")}
    return sorted(names)


def get_nfl_hit_rate_sheet(
    market: Optional[str] = None,
    min_pct: float = 0,
    min_odds: Optional[float] = None,
    period: str = "season",
    player: Optional[str] = None,
    books: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Hit Rate Sheet: one row per (player, market, line) NFL currently has
    a live sportsbook price for -- same current-lines-driven shape as
    get_mlb_hit_rate_sheet(), sourced from get_props("nfl") for the line and
    best-odds/book, and player_box_stats.parquet (get_game_log()'s own
    source) for the season/recent grading.

    `books`: optional CSV of sportsbook column names -- see
    get_mlb_hit_rate_sheet()'s docstring for why this narrows best_odds/
    best_book instead of just being a display filter.
    """
    from app.data.props import get_props

    markets = (
        [market] if market and market != "all" and market in NFL_MARKET_STAT
        else list(NFL_MARKET_STAT.keys())
    )

    props_rows = get_props("nfl")
    if not props_rows:
        return []
    # See get_mlb_hit_rate_sheet()'s identical comment: all_book_cols always
    # goes into each row's odds_by_book so the frontend's Books toggle can
    # recompute best-odds/hidden-count for any checked subset locally.
    all_book_cols = [c for c in props_rows[0].keys() if c not in _NFL_PROPS_META_COLS]
    book_cols = all_book_cols
    if books:
        wanted = {b.strip().lower() for b in books.split(",") if b.strip()}
        book_cols = [c for c in all_book_cols if c.lower() in wanted]

    d, _col, _team_col_name = _nfl_current_season_frame()
    if d.empty:
        return []
    latest_team = _nfl_latest_team_by_player()
    game_lines_by_matchup = _nfl_game_lines_lookup()

    # Grouped once instead of re-scanning the full props feed once per
    # market below -- see get_mlb_hit_rate_sheet()'s identical comment.
    rows_by_market: Dict[str, List[dict]] = {}
    for row in props_rows:
        rows_by_market.setdefault(str(row.get("market", "")).lower(), []).append(row)

    out: List[Dict[str, Any]] = []
    for mkt in markets:
        # See get_mlb_hit_rate_sheet()'s identical comment: alternate lines
        # ("reception_yds_alternate") are a separate market in the raw feed
        # from the standard one ("reception_yds") even though they're the
        # same stat, and the two commonly re-quote the same player+line --
        # so alt rows are only added for a (player, line) the standard
        # market doesn't already cover, rather than duplicating it.
        primary_rows = rows_by_market.get(mkt, [])
        alt_rows = rows_by_market.get(f"{mkt}_alternate", [])
        if alt_rows:
            covered = {(r.get("player"), r.get("line")) for r in primary_rows}
            candidate_rows = primary_rows + [
                r for r in alt_rows if (r.get("player"), r.get("line")) not in covered
            ]
        else:
            candidate_rows = primary_rows
        if not candidate_rows:
            continue
        by_player = _nfl_values_by_player(mkt)
        if not by_player:
            continue

        for row in candidate_rows:
            player_name = str(row.get("player", "") or "")
            if not player_name:
                continue
            if player and player.lower() not in player_name.lower():
                continue

            key = _normalize_loose(player_name)
            values = by_player.get(key)
            if not values:
                continue

            windows = split_season_recent(values, NFL_RECENT_GAMES)

            if mkt in _NFL_YES_NO_MARKETS:
                line_f = 1.0
            else:
                line_raw = row.get("line")
                if not _nfl_is_number(line_raw):
                    continue
                line_f = float(line_raw)

            season_grade = grade_over_under(windows["season"], line_f)
            recent_grade = grade_over_under(windows["recent"], line_f)
            selected_pct = season_grade["pct"] if period == "season" else recent_grade["pct"]
            if selected_pct * 100 < min_pct:
                continue

            offers = [(b, row.get(b)) for b in book_cols]
            offers = [(b, float(o)) for b, o in offers if _nfl_is_number(o)]
            if not offers:
                continue
            best_book, best_odds = max(offers, key=lambda x: x[1])
            if min_odds is not None and best_odds < min_odds:
                continue

            odds_by_book = {
                b: int(round(float(row.get(b))))
                for b in all_book_cols if _nfl_is_number(row.get(b))
            }

            team = latest_team.get(key)
            home_team_full, away_team_full = row.get("home_team"), row.get("away_team")
            home_abbr, away_abbr = NFL_TEAM_ABBR.get(home_team_full), NFL_TEAM_ABBR.get(away_team_full)
            opponent = None
            if team and home_abbr and away_abbr:
                if team == home_abbr:
                    opponent = f"vs {away_abbr}"
                elif team == away_abbr:
                    opponent = f"@ {home_abbr}"

            # Daily game-level spread/total from get_game_lines.py -- one
            # dict lookup plus a couple of ternaries (game_lines_by_matchup
            # is built once above), not a new pandas scan per row. Keyed by
            # the same full team-name strings as home_team_full/
            # away_team_full above, both from the same Odds API.
            game_line_row = game_lines_by_matchup.get((home_team_full, away_team_full)) if home_team_full and away_team_full else None
            total = None
            game_line = None
            if game_line_row is not None:
                raw_total = game_line_row.get("total_line")
                if pd.notna(raw_total):
                    total = float(raw_total)
                raw_spread = game_line_row.get("spread_line")
                if pd.notna(raw_spread) and team and home_abbr and away_abbr:
                    # spread_line is stored positive-means-home-favored (see
                    # get_game_lines.py's own sign-conversion comment).
                    # Converted here to the standard bettor-facing sign for
                    # THIS ROW'S OWN team, comparing abbreviations since
                    # `team` here is nflverse-style ("KC"), not the full
                    # Odds-API name.
                    if team == home_abbr:
                        game_line = round(-float(raw_spread), 1)
                    elif team == away_abbr:
                        game_line = round(float(raw_spread), 1)

            out.append({
                "player": player_name,
                "team": team,
                "opponent": opponent,
                "market": mkt,
                "line": "Yes" if mkt in _NFL_YES_NO_MARKETS else line_f,
                "season_pct": round(season_grade["pct"] * 100, 1),
                "season_sample": f"{season_grade['over']}/{season_grade['total']}",
                "recent_pct": round(recent_grade["pct"] * 100, 1),
                "recent_sample": f"{recent_grade['over']}/{recent_grade['total']}",
                "best_odds": int(round(best_odds)),
                "best_book": best_book,
                "odds_by_book": odds_by_book,
                "estimated_line": False,
                # See get_mlb_hit_rate_sheet()'s identical field for why this
                # is carried through.
                "fetched_at": row.get("fetched_at"),
                # See get_mlb_hit_rate_sheet()'s identical fields.
                "game_line": game_line,
                "total": total,
            })

    return out
