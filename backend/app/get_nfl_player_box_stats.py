"""Pull nflverse's per-player weekly box-score stats (passing, rushing,
receiving) for the season.

player_week_usage.parquet (from get_nfl_pbp.py) already covers rushing and
receiving usage from play-by-play, but has no passing stats at all -- pbp
usage was built for target/carry share, not QB box scores. This script
pulls nflverse's separate "stats_player" release, which has passing yards,
TDs, completions, etc. alongside rushing/receiving, in one file per season.
Same source the season-total parlay pace feed (build_pace_feed.py) needs
for legs like "25+ passing TDs".

Same nflverse-data-direct approach as get_nfl_pbp.py, for the same reason:
no nfl_data_py (pandas/numpy version pins conflict with the rest of this
app). One row per player per week; season totals are a groupby downstream
(see build_pace_feed.py), consistent with player_week_usage.parquet's own
weekly grain rather than pre-aggregating here.

    python backend/app/get_nfl_player_box_stats.py                # current season
    python backend/app/get_nfl_player_box_stats.py --season 2024  # a specific season

Output: backend/data/nfl/player_box_stats.parquet
"""

from __future__ import annotations

import argparse
from datetime import date
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

NFLVERSE_STATS_URL = (
    "https://github.com/nflverse/nflverse-data/releases/download/"
    "stats_player/stats_player_week_{season}.csv"
)
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "nfl"
TIMEOUT = 60
REGULAR_SEASON_MAX_WEEK = 18  # matches get_nfl_weekly_stats.py / get_nfl_pbp.py

KEEP_COLUMNS = [
    "season", "week", "team", "player_id", "player_display_name", "position",
    "completions", "attempts", "passing_yards", "passing_tds", "interceptions",
    "carries", "rushing_yards", "rushing_tds",
    "receptions", "targets", "receiving_yards", "receiving_tds",
]


def fetch_stats(season: int) -> pd.DataFrame | None:
    """Returns None (not an exception) when the season's file doesn't exist
    yet -- e.g. before Week 1 -- so build() can fall back gracefully. Same
    reasoning as get_nfl_pbp.py's fetch_pbp(): a hard failure here would
    also block the later, unrelated steps in the same CI job."""
    url = NFLVERSE_STATS_URL.format(season=season)
    r = requests.get(url, timeout=TIMEOUT)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text), low_memory=False)

    # A few columns (e.g. fg_blocked_list) mix strings and NaN-as-float,
    # which pyarrow refuses to write to parquet. Only KEEP_COLUMNS survive
    # past this function anyway, but normalize defensively in case that
    # list grows to include one later.
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype(str).replace("nan", pd.NA)

    return df


def build(season: int) -> pd.DataFrame:
    df = fetch_stats(season)
    is_fallback = False

    if df is None:
        # Same fallback as get_nfl_pbp.py: no games yet this season, so use
        # last season's regular season instead of coming back empty.
        fallback_season = season - 1
        print(f"no player stats for {season} yet; falling back to {fallback_season} "
              f"regular season (weeks 1-{REGULAR_SEASON_MAX_WEEK})")
        df = fetch_stats(fallback_season)
        if df is None:
            raise RuntimeError(
                f"No player stats available for {season} OR its fallback {fallback_season}. "
                f"Something's genuinely wrong (not just \"season hasn't started\") -- check "
                f"https://github.com/nflverse/nflverse-data/releases/tag/stats_player directly."
            )
        df = df[df["week"] <= REGULAR_SEASON_MAX_WEEK]
        is_fallback = True

    print(f"{len(df)} player-week rows loaded" +
          (f" (fallback season {df['season'].iloc[0]})" if is_fallback else f" for {season}"))

    frame = df[[c for c in KEEP_COLUMNS if c in df.columns]].copy()
    frame["is_fallback"] = is_fallback
    return frame


def current_nfl_season() -> int:
    """Same rule as get_nfl_pbp.py's current_nfl_season() -- nflverse labels
    a season by the year it starts in, and the new one isn't labeled until
    games are actually played in September."""
    today = date.today()
    return today.year if today.month >= 9 else today.year - 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=current_nfl_season())
    args = parser.parse_args()

    frame = build(args.season)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "player_box_stats.parquet"
    frame.to_parquet(dest, index=False)

    print(f"{len(frame)} player-week rows across {frame['team'].nunique()} teams")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
