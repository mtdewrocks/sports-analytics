"""Pull nflverse weekly player stats + schedule, aggregate to team stats + ranks.

Ports the logic from the user's team_stats_and_weekly_matchup_quarto_reports
script, with three changes:

1. Auto-detects the latest completed week from the schedule (the most recent
   week with a non-null score) instead of relying on a `week` variable that
   was never actually defined in the source script -- the only place it was
   set was in two commented-out lines above it, which means the original
   only ever ran inside an interactive session where `week` had been set by
   hand in an earlier cell. A scheduled job has no such session, so this
   needs to be self-contained.

2. Fixes two rank-direction bugs found while porting:
   - Offense "Sacks Allowed" was ranked the same direction as the "more is
     better" offensive stats (ascending=False, i.e. most sacks allowed =
     rank 1). Getting sacked more is bad for an offense -- fixed to
     ascending=True (fewest sacks allowed = rank 1), matching every other
     "bad thing allowed" stat in that same table.
   - Defense "Defensive Sacks" was ranked the same direction as the
     yards-allowed stats (ascending=True, i.e. fewest sacks recorded =
     rank 1). Sacks recorded are good for a defense -- fixed to
     ascending=False (most sacks recorded = rank 1).

3. Reads weekly stats + schedule directly from nflverse's GitHub releases
   instead of nfl_data_py -- see get_nfl_pbp.py's docstring for why
   nfl_data_py is skipped (pandas<2.0/numpy<2.0 pin, conflicts with this
   app's pandas 3.x/numpy 2.x, and fails to build from source as-is).

    python backend/app/get_nfl_weekly_stats.py                # current season
    python backend/app/get_nfl_weekly_stats.py --season 2024  # a specific season

Output: backend/data/nfl/team_stats.parquet
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests

WEEKLY_STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv"
SCHEDULE_URL = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "nfl"
TIMEOUT = 60


def current_nfl_season() -> int:
    """Same logic as get_nfl_pbp.py -- see that file for the reasoning."""
    today = date.today()
    return today.year if today.month >= 9 else today.year - 1


def fetch_weekly_stats(season: int) -> pd.DataFrame:
    url = WEEKLY_STATS_URL.format(season=season)
    r = requests.get(url, timeout=TIMEOUT)
    if r.status_code == 404:
        raise RuntimeError(
            f"No weekly stats file for {season} yet ({url}). Same situation as "
            f"get_nfl_pbp.py -- try --season {season - 1} before Week 1."
        )
    r.raise_for_status()
    from io import StringIO
    return pd.read_csv(StringIO(r.text), low_memory=False)


def fetch_schedule(season: int) -> pd.DataFrame:
    r = requests.get(SCHEDULE_URL, timeout=TIMEOUT)
    r.raise_for_status()
    from io import StringIO
    df = pd.read_csv(StringIO(r.text), low_memory=False)
    return df[df["season"] == season]


def _rank(df: pd.DataFrame, new_col: str, col: str, ascending: bool) -> None:
    df[new_col] = df[col].rank(ascending=ascending, method="min")


REGULAR_SEASON_MAX_WEEK = 18  # weeks 19+ are playoffs


def build(season: int) -> pd.DataFrame:
    schedule = fetch_schedule(season)
    completed = schedule[schedule["home_score"].notna()]

    if completed.empty:
        # No games played yet this season (e.g. Week 1, before any results
        # exist) -- fall back to last season's full regular season as a
        # reasonable prior rather than having nothing to preview against.
        # Capped at week 18 to exclude the playoffs, which run on a
        # different, single-elimination dynamic than a season-long average
        # should represent.
        fallback_season = season - 1
        print(f"no completed games yet for {season}; falling back to {fallback_season} "
              f"regular season (weeks 1-{REGULAR_SEASON_MAX_WEEK})")
        schedule = fetch_schedule(fallback_season)
        schedule = schedule[schedule["week"] <= REGULAR_SEASON_MAX_WEEK]
        weekly = fetch_weekly_stats(fallback_season)
        weekly = weekly[weekly["week"] <= REGULAR_SEASON_MAX_WEEK]
        stats_season, week = fallback_season, REGULAR_SEASON_MAX_WEEK
        is_fallback = True
    else:
        week = int(completed["week"].max())
        print(f"season {season}, through week {week}")
        weekly = fetch_weekly_stats(season)
        weekly = weekly[weekly["week"] <= week]
        stats_season = season
        is_fallback = False

    team_stats = weekly.copy()

    # ---- Offense --------------------------------------------------------
    team_stats["total_plays"] = team_stats[["attempts", "carries", "sacks_suffered"]].sum(axis=1)
    team_stats["total_team_plays"] = team_stats.groupby("team")["total_plays"].transform("sum")

    def new_stat(new_column, column, transform):
        team_stats[new_column] = team_stats.groupby("team")[column].transform(transform)

    new_stat("team_rush_yards", "rushing_yards", "sum")
    new_stat("team_pass_yards", "passing_yards", "sum")
    new_stat("Pass Attempts", "attempts", "sum")
    new_stat("Sacks Allowed", "sacks_suffered", "sum")
    new_stat("Interceptions Thrown", "passing_interceptions", "sum")

    team_stats["games_count"] = team_stats.groupby("team")["week"].transform("nunique")
    team_stats["Plays Per Game"] = team_stats["total_team_plays"] / team_stats["games_count"]
    team_stats["Rush Yards Per Game"] = team_stats["team_rush_yards"] / team_stats["games_count"]
    team_stats["Pass Yards Per Game"] = team_stats["team_pass_yards"] / team_stats["games_count"]
    team_stats["Interceptions Thrown Per Game"] = team_stats["Interceptions Thrown"] / team_stats["games_count"]
    team_stats["rush_attempts"] = team_stats.groupby("team")["carries"].transform("sum")

    team_stats["total_pass_plays"] = team_stats[["attempts", "sacks_suffered"]].sum(axis=1)
    team_stats["pass_attempts"] = team_stats.groupby("team")["total_pass_plays"].transform("sum")
    team_stats["run_share"] = team_stats["rush_attempts"] / team_stats["total_team_plays"] * 100
    team_stats["pass_share"] = team_stats["pass_attempts"] / team_stats["total_team_plays"] * 100
    team_stats["Yards Per Carry"] = team_stats["team_rush_yards"] / team_stats["rush_attempts"]
    team_stats["Yards Per Pass Attempt"] = team_stats["team_pass_yards"] / team_stats["Pass Attempts"]

    offense = team_stats[[
        "team", "Plays Per Game", "run_share", "pass_share", "Yards Per Carry",
        "Yards Per Pass Attempt", "Rush Yards Per Game", "Pass Yards Per Game", "Sacks Allowed",
        "Interceptions Thrown Per Game",
    ]].drop_duplicates(subset="team", keep="first")

    # ---- Defense (== what opponents did against this team) --------------
    g_opp = team_stats.groupby("opponent_team")
    team_stats["Defense Plays Per Game"] = g_opp["total_plays"].transform("sum") / g_opp["week"].transform("nunique")
    team_stats[["Defense Total Plays", "Defense Rush Attempts", "Defense Pass Attempts"]] = (
        g_opp[["total_plays", "carries", "total_pass_plays"]].transform("sum")
    )
    team_stats["Defense Rush Share"] = team_stats["Defense Rush Attempts"] / team_stats["Defense Total Plays"] * 100
    team_stats["Defense Pass Share"] = team_stats["Defense Pass Attempts"] / team_stats["Defense Total Plays"] * 100
    team_stats["Defense Rush Yards Per Game"] = g_opp["rushing_yards"].transform("sum") / g_opp["week"].transform("nunique")
    team_stats["Defense Pass Yards Per Game"] = g_opp["passing_yards"].transform("sum") / g_opp["week"].transform("nunique")
    team_stats["Defense Rush Yards Per Attempt"] = g_opp["rushing_yards"].transform("sum") / team_stats["Defense Rush Attempts"]
    team_stats["Defense Pass Yards Per Attempt"] = g_opp["passing_yards"].transform("sum") / team_stats["Defense Pass Attempts"]
    team_stats["Defensive Sacks"] = g_opp["sacks_suffered"].transform("sum")
    team_stats["Defensive Interceptions Per Game"] = g_opp["passing_interceptions"].transform("sum") / g_opp["week"].transform("nunique")

    defense = team_stats[[
        "opponent_team", "Defense Plays Per Game", "Defense Rush Share", "Defense Pass Share",
        "Defense Rush Yards Per Attempt", "Defense Rush Yards Per Game",
        "Defense Pass Yards Per Attempt", "Defense Pass Yards Per Game", "Defensive Sacks",
        "Defensive Interceptions Per Game",
    ]].drop_duplicates(subset="opponent_team", keep="first")

    # ---- Ranks ------------------------------------------------------------
    # "More is better" offensive volume/efficiency stats.
    for col in ["Plays Per Game", "run_share", "pass_share", "Rush Yards Per Game",
                "Yards Per Carry", "Pass Yards Per Game", "Yards Per Pass Attempt"]:
        _rank(offense, f"Rank - {col}", col, ascending=False)
    # Getting sacked is bad -- fewest allowed ranks best. (Bug fix: the
    # source script ranked this the same direction as the stats above.)
    _rank(offense, "Rank - Sacks Allowed", "Sacks Allowed", ascending=True)
    # Throwing interceptions is bad for an offense -- fewest ranks best.
    _rank(offense, "Rank - Interceptions Thrown Per Game", "Interceptions Thrown Per Game", ascending=True)

    # "Fewest allowed is better" defensive stats.
    for col in ["Defense Plays Per Game", "Defense Rush Share", "Defense Pass Share",
                "Defense Rush Yards Per Game", "Defense Rush Yards Per Attempt",
                "Defense Pass Yards Per Game", "Defense Pass Yards Per Attempt"]:
        _rank(defense, f"Rank - {col}", col, ascending=True)
    # Recording sacks is good for a defense -- most recorded ranks best.
    # (Bug fix: the source script ranked this the same direction as the
    # yards-allowed stats above, which rewarded defenses for recording
    # FEWER sacks.)
    _rank(defense, "Rank - Defensive Sacks", "Defensive Sacks", ascending=False)
    # Taking interceptions is good for a defense -- most ranks best, same
    # "more is better for the defense" logic as sacks above.
    _rank(defense, "Rank - Defensive Interceptions Per Game", "Defensive Interceptions Per Game", ascending=False)

    combined = offense.merge(defense, left_on="team", right_on="opponent_team", how="inner")

    # ---- Scoring (points for / against, from the schedule) ----------------
    played = schedule[schedule["week"] <= week]
    home = played[["home_team", "home_score"]].rename(columns={"home_team": "team", "home_score": "score"})
    away = played[["away_team", "away_score"]].rename(columns={"away_team": "team", "away_score": "score"})
    offense_scores = pd.concat([home, away]).groupby("team", as_index=False)["score"].mean()
    _rank(offense_scores, "Rank - Scoring Offense", "score", ascending=False)

    def_home = played[["home_team", "away_score"]].rename(columns={"home_team": "team", "away_score": "score"})
    def_away = played[["away_team", "home_score"]].rename(columns={"away_team": "team", "home_score": "score"})
    defense_scores = pd.concat([def_home, def_away]).groupby("team", as_index=False)["score"].mean()
    _rank(defense_scores, "Rank - Scoring Defense", "score", ascending=True)

    scores = offense_scores.merge(defense_scores, on="team", suffixes=("_offense", "_defense"))

    final = combined.merge(scores, on="team", how="inner")
    final["season"] = stats_season
    final["through_week"] = week
    final["is_fallback"] = is_fallback
    return final


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=current_nfl_season())
    args = parser.parse_args()

    frame = build(args.season)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "team_stats.parquet"
    frame.to_parquet(dest, index=False)

    print(f"{len(frame)} teams")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
