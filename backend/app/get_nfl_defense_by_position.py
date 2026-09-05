"""Weekly defensive rank history, split by the OPPONENT'S POSITION -- e.g.
"yards allowed to RBs" versus "yards allowed to QBs", not just one lumped
team-level pass/rush number. The existing weekly_defense_ranks.parquet
(get_nfl_weekly_defense_ranks.py) can't tell you a defense is bad against
running backs specifically versus just generally bad against the pass --
this file adds that split.

Scope, deliberately narrower than "every position x every stat type":
  - Rushing yards allowed to: RB, QB (mobile QBs are a real, relevant
    matchup factor; WR/TE rushing is rare enough to not be worth a column)
  - Receiving yards allowed to: RB, WR, TE (QBs essentially never catch
    passes, so a "receiving yards allowed to QBs" column would be
    meaningless noise)

Same season-to-date / last4 dual-window structure as
get_nfl_weekly_defense_ranks.py, for the same reason: season-to-date is
stable, last4 reflects recent form, and early-season weeks fall back to
however many prior games actually exist. Same Week-1-of-the-season and
whole-season-not-started-yet fallbacks too, for the same CI-resilience
reasons documented there.

    python backend/app/get_nfl_defense_by_position.py

Output: backend/data/nfl/weekly_defense_by_position.parquet
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

# (position_group to filter to, stat column to sum, output column prefix)
SPLITS = [
    ("RB", "rushing_yards", "def_rb_rush_ypg"),
    ("QB", "rushing_yards", "def_qb_rush_ypg"),
    ("RB", "receiving_yards", "def_rb_rec_ypg"),
    ("WR", "receiving_yards", "def_wr_rec_ypg"),
    ("TE", "receiving_yards", "def_te_rec_ypg"),
]


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


def position_defense_for_window(weekly: pd.DataFrame) -> pd.DataFrame:
    """One row per team, position-split yards-allowed + rank, for whatever
    subset of weekly rows is passed in (season-to-date slice, trailing-4
    slice, or a full prior season for the Week 1 fallback)."""
    return _add_ranks(_defense_stats_only(weekly))


def _defense_stats_only(weekly: pd.DataFrame) -> pd.DataFrame:
    """Raw position-split yards-allowed (no ranks yet). Split out from
    ranking for the same reason as get_nfl_weekly_defense_ranks.py: the
    bye-safe last4 window needs each team's stats from ITS OWN window
    before ranking everyone together."""
    all_teams = weekly[["opponent_team"]].drop_duplicates().rename(columns={"opponent_team": "team"})
    result = all_teams.copy()

    for position_group, stat_col, out_col in SPLITS:
        sub = weekly[weekly["position_group"] == position_group]
        g = sub.groupby("opponent_team")
        # Games played by THIS opponent overall (not just games where this
        # position group recorded a stat), so a defense that shut a
        # position group out entirely still gets a correct per-game rate
        # instead of dividing by zero or by an undercount.
        games_played = weekly[weekly["opponent_team"].isin(sub["opponent_team"].unique())].groupby("opponent_team")["week"].nunique()
        yards_allowed = g[stat_col].sum()
        per_game = (yards_allowed / games_played).rename(out_col)
        result = result.merge(per_game, left_on="team", right_index=True, how="left")

    return result


def _add_ranks(stats: pd.DataFrame) -> pd.DataFrame:
    stats = stats.copy()
    # Fewest yards allowed = best defense = rank 1, for all five splits.
    for _, _, out_col in SPLITS:
        if out_col in stats.columns:
            stats[f"{out_col}_rank"] = stats[out_col].rank(ascending=True, method="min")
    return stats


def position_defense_last4_bye_safe(weekly_prior: pd.DataFrame) -> pd.DataFrame:
    """Each team's own last 4 ACTUALLY PLAYED games, not a shared week-number
    range -- same bye-week reasoning as get_nfl_weekly_defense_ranks.py."""
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

    two_seasons_back = season - 1
    print(f"fetching {two_seasons_back} in case week 1 needs it too")
    prior_weekly = fetch_weekly_stats(two_seasons_back)
    prior_full_season = (
        position_defense_for_window(prior_weekly[prior_weekly["week"] <= REGULAR_SEASON_MAX_WEEK])
        if prior_weekly is not None else pd.DataFrame()
    )

    rows = []
    for week in range(1, latest_week + 1):
        prior_games = weekly[weekly["week"] < week]

        if prior_games.empty:
            if prior_full_season.empty:
                print(f"  week {week}: no fallback data available either -- skipping")
                continue
            season_to_date = prior_full_season.copy()
            last4 = prior_full_season.copy()
            is_fallback = True
        else:
            season_to_date = position_defense_for_window(prior_games)
            last4 = position_defense_last4_bye_safe(prior_games)
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
    dest = DATA_DIR / "weekly_defense_by_position.parquet"
    frame.to_parquet(dest, index=False)

    print(f"{len(frame)} team-week rows saved -> {dest}")


if __name__ == "__main__":
    main()
