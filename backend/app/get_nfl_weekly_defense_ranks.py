"""Weekly defensive rank history, for context on a player's game log.

A raw stat line means little without knowing how good the opponent's defense
was AT THE TIME -- 45 rushing yards against the league's best run defense
reads very differently than 45 against its worst. team_stats.parquet only
ever holds one snapshot (the defense's rank as of the most recently
completed week), so it can't answer "what was this defense ranked entering
the game this player actually played." This script builds that history:
one row per team per week, with the defense's rank as of *entering* that
week (computed from strictly earlier weeks only -- never the week itself,
which would be lookahead bias).

Two variants of each stat, since which one is more informative depends on
what you're trying to see:
  - season-to-date: cumulative through the prior week (stable, less noisy)
  - last4: trailing 4 games only (reflects recent form / hot-cold streaks)
Early-season weeks naturally have fewer than 4 prior games available for
the last4 variant -- it just uses however many exist (1, 2, or 3), which
makes it identical to season-to-date until week 5 arrives.

Week 1 has no in-season games to compute from at all, so it falls back to
last season's full regular season (weeks 1-18) -- same convention as
get_nfl_weekly_stats.py's Matchup-page fallback.

Future/upcoming games don't need anything from this file -- they use
team_stats.parquet's current snapshot directly, since "the defense's rank
as of right now" is exactly what you want for a game that hasn't happened
yet.

    python backend/app/get_nfl_weekly_defense_ranks.py

Output: backend/data/nfl/weekly_defense_ranks.parquet
"""

from __future__ import annotations

import argparse
from datetime import date
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

WEEKLY_STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv"
SCHEDULE_URL = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "nfl"
TIMEOUT = 60
REGULAR_SEASON_MAX_WEEK = 18
TRAILING_WINDOW = 4


def current_nfl_season() -> int:
    today = date.today()
    return today.year if today.month >= 9 else today.year - 1


def fetch_weekly_stats(season: int) -> pd.DataFrame | None:
    """Returns None (not an exception) on a season with no file yet -- see
    get_nfl_weekly_stats.py for why this matters for CI resilience."""
    url = WEEKLY_STATS_URL.format(season=season)
    r = requests.get(url, timeout=TIMEOUT)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return pd.read_csv(StringIO(r.text), low_memory=False)


def fetch_schedule(season: int) -> pd.DataFrame:
    r = requests.get(SCHEDULE_URL, timeout=TIMEOUT)
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text), low_memory=False)
    return df[df["season"] == season]


def team_defense_for_window(weekly: pd.DataFrame) -> pd.DataFrame:
    """One row per team, defensive yards-allowed + rank, for whatever subset
    of weekly rows is passed in (a season-to-date slice, a trailing-4 slice,
    or a full prior season for the Week 1 fallback)."""
    return _add_ranks(_defense_stats_only(weekly))


def _defense_stats_only(weekly: pd.DataFrame) -> pd.DataFrame:
    """Raw defensive yards-allowed (no ranks yet) for whatever rows are
    passed in. Split out from ranking so the bye-safe last4 window below can
    compute each team's stats from ITS OWN window before ranking everyone
    together -- ranking per-team one at a time would be meaningless (a
    single row always "ranks" 1st against itself)."""
    d = weekly.copy()
    d["total_pass_plays"] = d["attempts"] + d["sacks_suffered"]

    g = d.groupby("opponent_team")
    games_played = g["week"].transform("nunique")
    pass_yards_allowed = g["passing_yards"].transform("sum")
    rush_yards_allowed = g["rushing_yards"].transform("sum")
    pass_attempts_allowed = g["total_pass_plays"].transform("sum")
    rush_attempts_allowed = g["carries"].transform("sum")

    d["def_pass_ypg"] = pass_yards_allowed / games_played
    d["def_rush_ypg"] = rush_yards_allowed / games_played
    d["def_pass_ypa"] = pass_yards_allowed / pass_attempts_allowed
    d["def_rush_ypa"] = rush_yards_allowed / rush_attempts_allowed

    return (
        d[["opponent_team", "def_pass_ypg", "def_rush_ypg", "def_pass_ypa", "def_rush_ypa"]]
        .drop_duplicates("opponent_team")
        .rename(columns={"opponent_team": "team"})
    )


def _add_ranks(stats: pd.DataFrame) -> pd.DataFrame:
    stats = stats.copy()
    # Fewest yards allowed = best defense = rank 1, for all four stats.
    for col in ["def_pass_ypg", "def_rush_ypg", "def_pass_ypa", "def_rush_ypa"]:
        stats[f"{col}_rank"] = stats[col].rank(ascending=True, method="min")
    return stats


def team_defense_last4_bye_safe(weekly_prior: pd.DataFrame) -> pd.DataFrame:
    """Each team's own last 4 ACTUALLY PLAYED games, not a shared week-number
    range -- a bye week means a team's window needs to reach one week
    further back than a team without a bye in that span, so this can't be a
    single filter shared across all teams the way season-to-date can be.
    """
    per_team = []
    for _, group in weekly_prior.groupby("opponent_team"):
        played_weeks = sorted(group["week"].unique())
        last4_weeks = set(played_weeks[-TRAILING_WINDOW:])
        per_team.append(_defense_stats_only(group[group["week"].isin(last4_weeks)]))

    if not per_team:
        return pd.DataFrame()
    return _add_ranks(pd.concat(per_team, ignore_index=True))


def build(season: int) -> pd.DataFrame:
    weekly = fetch_weekly_stats(season)
    outer_fallback = False

    if weekly is None:
        # Whole season doesn't exist yet (e.g. before Week 1) -- fall back
        # entirely to last season's regular season, same as
        # get_nfl_pbp.py / get_nfl_weekly_stats.py already do. This script
        # previously only had the narrower per-row Week 1 fallback below,
        # which assumes the CURRENT season's file exists at all -- it does
        # nothing if the season hasn't started, unlike its siblings.
        prior_season = season - 1
        print(f"no weekly stats for {season} yet; falling back entirely to {prior_season} "
              f"regular season (weeks 1-{REGULAR_SEASON_MAX_WEEK})")
        weekly = fetch_weekly_stats(prior_season)
        if weekly is None:
            raise RuntimeError(f"No weekly stats available for {season} or {prior_season}.")
        weekly = weekly[weekly["week"] <= REGULAR_SEASON_MAX_WEEK]
        season = prior_season
        outer_fallback = True

    schedule = fetch_schedule(season)
    completed = schedule[schedule["home_score"].notna()]
    if outer_fallback:
        completed = completed[completed["week"] <= REGULAR_SEASON_MAX_WEEK]
    if completed.empty:
        print(f"no completed games yet for {season} -- nothing to build")
        return pd.DataFrame()
    latest_week = int(completed["week"].max())

    # For a week with no prior games in ITS OWN season (Week 1 of a real
    # season, or -- when outer_fallback already kicked in -- Week 1 of last
    # year too), borrow the year before that one's full season as context.
    two_seasons_back = season - 1
    print(f"fetching {two_seasons_back} in case week 1 needs it too")
    prior_weekly = fetch_weekly_stats(two_seasons_back)
    prior_full_season = (
        team_defense_for_window(prior_weekly[prior_weekly["week"] <= REGULAR_SEASON_MAX_WEEK])
        if prior_weekly is not None else pd.DataFrame()
    )

    rows = []
    for week in range(1, latest_week + 1):
        prior_games = weekly[weekly["week"] < week]

        if prior_games.empty:
            # Week 1 -- no in-season games exist yet at all.
            if prior_full_season.empty:
                print(f"  week {week}: no fallback data available either -- skipping")
                continue
            season_to_date = prior_full_season.copy()
            last4 = prior_full_season.copy()
            is_fallback = True
        else:
            season_to_date = team_defense_for_window(prior_games)
            last4 = team_defense_last4_bye_safe(prior_games)
            # If the whole season we're using is itself a fallback (outer),
            # every row reflects borrowed data, not just Week 1.
            is_fallback = outer_fallback

        merged = season_to_date.merge(last4, on="team", suffixes=("_season", "_last4"))
        merged["season"] = season
        merged["week"] = week
        merged["is_fallback"] = is_fallback
        rows.append(merged)
        print(f"  week {week}: {'fallback' if is_fallback else 'computed'}")

    if not rows:
        return pd.DataFrame()

    return pd.concat(rows, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=current_nfl_season())
    args = parser.parse_args()

    frame = build(args.season)
    if frame.empty:
        print("nothing to save")
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "weekly_defense_ranks.parquet"
    frame.to_parquet(dest, index=False)

    print(f"{len(frame)} team-week rows saved -> {dest}")


if __name__ == "__main__":
    main()
