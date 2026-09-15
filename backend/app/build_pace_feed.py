"""
build_pace_feed.py
-------------------
Aggregates backend/data/nfl/player_box_stats.parquet (from
get_nfl_player_box_stats.py) and backend/data/nfl/schedule_results.parquet
(from get_nfl_schedule_results.py) into a small JSON feed that the "On Pace"
parlay tracker fetches directly from raw.githubusercontent.com -- same
no-server, fetch-a-public-file pattern the rest of this repo's frontend
already uses for its data.

Run this after the two scripts above (see update_nfl.yml, which already
does this on every scheduled run).

    python build_pace_feed.py                # current season
    python build_pace_feed.py --season 2024  # a specific season

Output: backend/data/nfl/on_pace_feed.json
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "nfl"
PLAYER_STATS_FILE = DATA_DIR / "player_box_stats.parquet"
SCHEDULE_FILE = DATA_DIR / "schedule_results.parquet"
OUTPUT_FILE = DATA_DIR / "on_pace_feed.json"

GAMES_TOTAL = 17  # NFL regular-season length

# Stat columns a leg can reference, keyed by the same stat_type values
# used in the tracker's "Add Parlay" form.
STAT_COLUMNS = [
    "passing_yards", "passing_tds",
    "rushing_yards", "rushing_tds",
    "receiving_yards", "receiving_tds",
    "receptions",
]


def current_nfl_season() -> int:
    """Same rule used across the other NFL scripts in this repo."""
    today = date.today()
    return today.year if today.month >= 9 else today.year - 1


def build_player_feed(df: pd.DataFrame, season: int) -> dict:
    reg = df[df["season"] == season]

    grouped = reg.groupby(["player_display_name", "team", "position"])
    games_played = grouped["week"].nunique()
    totals = grouped[STAT_COLUMNS].sum()

    players = {}
    for (name, team, position), gp in games_played.items():
        row = totals.loc[(name, team, position)]
        players[name] = {
            "team": team,
            "position": position,
            "games_played": int(gp),
            **{stat: float(row[stat]) for stat in STAT_COLUMNS},
        }
    return players


def build_team_feed(schedule: pd.DataFrame, season: int) -> dict:
    sched = schedule[
        (schedule["season"] == season)
        & (schedule["game_type"] == "REG")
        & schedule["home_score"].notna()
    ]

    teams = {}
    all_teams = pd.unique(sched[["home_team", "away_team"]].values.ravel())
    for team in all_teams:
        home = sched[sched["home_team"] == team]
        away = sched[sched["away_team"] == team]
        wins = (home["home_score"] > home["away_score"]).sum() + (
            away["away_score"] > away["home_score"]
        ).sum()
        losses = (home["home_score"] < home["away_score"]).sum() + (
            away["away_score"] < away["home_score"]
        ).sum()
        games_played = len(home) + len(away)
        teams[team] = {
            "games_played": int(games_played),
            "wins": int(wins),
            "losses": int(losses),
        }
    return teams


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=current_nfl_season())
    args = parser.parse_args()
    season = args.season

    player_stats = pd.read_parquet(PLAYER_STATS_FILE)
    schedule = pd.read_parquet(SCHEDULE_FILE)

    # player_box_stats.parquet now holds the current season AND the one
    # before it in the same file (get_nfl_player_box_stats.py keeps both so
    # the Game Log page can offer a season toggle). Picking the season with
    # more ROWS (the old `.mode()` approach) is wrong here: last season has a
    # full year of rows and this season only has a few weeks, so `.mode()`
    # would keep resolving to last season for most of the year. What we
    # actually want is "prefer the current season; only fall back to last
    # season if the current one has no rows at all yet" -- a membership
    # check, not a majority vote.
    seasons_present = (
        set(player_stats["season"].dropna().unique()) if not player_stats.empty else set()
    )
    if season in seasons_present:
        effective_season = season
    elif (season - 1) in seasons_present:
        effective_season = season - 1
        print(f"no {season} data yet; using {effective_season} instead")
    else:
        effective_season = season

    max_week = int(player_stats[player_stats["season"] == effective_season]["week"].max())

    feed = {
        "season": effective_season,
        "as_of_week": max_week,
        "games_total": GAMES_TOTAL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "players": build_player_feed(player_stats, effective_season),
        "teams": build_team_feed(schedule, effective_season),
    }

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(feed, f, indent=2)

    print(f"Wrote {OUTPUT_FILE}: {len(feed['players'])} players, "
          f"{len(feed['teams'])} teams, season {effective_season} through week {max_week}")


if __name__ == "__main__":
    main()
