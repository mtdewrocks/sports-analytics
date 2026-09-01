"""Pull nflverse play-by-play and aggregate to player-week usage.

nflverse (the community project behind nfl_data_py) publishes full-season
play-by-play directly as a GitHub release -- no auth, no package needed.
nfl_data_py itself is skipped here on purpose: it hard-pins pandas<2.0 and
numpy<2.0, which conflicts with the rest of this app (pandas 3.x / numpy
2.x), and it currently fails to even build from source in a clean
environment. It's a thin wrapper around this exact same file, so pulling it
directly avoids the dependency conflict entirely.

Unlike the MLB bullpen script, there's no bootstrap/incremental split here:
nflverse republishes the *entire* season's play-by-play as one file each
time (not a growing daily log), so every run just re-downloads and
re-aggregates the whole thing.

This script does NOT save the raw play-by-play (372 columns x ~50k+ rows by
season's end is too much to ship to the frontend or reload on every
request). Instead it pre-aggregates to a much smaller player-week usage
table -- targets, air yards, carries, rushing yards, both overall and
red-zone-only (yardline_100 <= 20) -- which is the foundation for the
target-share and rushing-yards dashboards. Team-level rollups (e.g. total
rushing yards by team) are a simple groupby of this same table, so one
output file covers both the player-level (treemap-style) and team-level
views without needing separate pulls.

Further slices (play distribution, success rate, QB hits, drive-level
stats -- the rest of the 14-page Power BI workbook) are intentionally left
for follow-up scripts once this first slice is confirmed working, rather
than building all of them blind in one pass.

    python backend/app/get_nfl_pbp.py                # current season
    python backend/app/get_nfl_pbp.py --season 2024  # a specific season

Output: backend/data/nfl/player_week_usage.parquet
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd
import requests

NFLVERSE_PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "nfl"
TIMEOUT = 120
RED_ZONE_YARDLINE = 20  # yardline_100 <= this counts as a red-zone play


def fetch_pbp(season: int) -> pd.DataFrame:
    url = NFLVERSE_PBP_URL.format(season=season)
    r = requests.get(url, timeout=TIMEOUT)
    if r.status_code == 404:
        raise RuntimeError(
            f"No play-by-play file for {season} yet ({url}). nflverse doesn't "
            f"publish a season's file until its first games have been played "
            f"and processed -- if this is before Week 1, pass --season "
            f"{season - 1} to work against last season's complete data instead."
        )
    r.raise_for_status()
    import io
    return pd.read_parquet(io.BytesIO(r.content))


def _usage_slice(df: pd.DataFrame, red_zone_only: bool) -> pd.DataFrame:
    """One row per player-week-role (receiver or rusher), for either all
    plays or red-zone plays only, depending on `red_zone_only`."""
    frame = df
    if red_zone_only:
        frame = frame[frame["yardline_100"] <= RED_ZONE_YARDLINE]

    targets = (
        frame[frame["pass_attempt"] == 1]
        .groupby(["season", "week", "posteam", "receiver_player_id", "receiver_player_name"], dropna=True)
        .agg(
            targets=("pass_attempt", "size"),
            receptions=("complete_pass", "sum"),
            receiving_yards=("receiving_yards", "sum"),
            air_yards=("air_yards", "sum"),
            receiving_tds=("pass_touchdown", "sum"),
        )
        .reset_index()
        .rename(columns={"receiver_player_id": "player_id", "receiver_player_name": "player"})
    )

    carries = (
        frame[frame["rush_attempt"] == 1]
        .groupby(["season", "week", "posteam", "rusher_player_id", "rusher_player_name"], dropna=True)
        .agg(
            carries=("rush_attempt", "size"),
            rushing_yards=("rushing_yards", "sum"),
            rushing_tds=("rush_touchdown", "sum"),
        )
        .reset_index()
        .rename(columns={"rusher_player_id": "player_id", "rusher_player_name": "player"})
    )

    merged = targets.merge(
        carries, on=["season", "week", "posteam", "player_id", "player"], how="outer"
    )
    numeric_cols = [
        "targets", "receptions", "receiving_yards", "air_yards", "receiving_tds",
        "carries", "rushing_yards", "rushing_tds",
    ]
    for c in numeric_cols:
        merged[c] = merged[c].fillna(0)

    prefix = "rz_" if red_zone_only else ""
    merged = merged.rename(columns={c: f"{prefix}{c}" for c in numeric_cols})
    return merged


def build(season: int) -> pd.DataFrame:
    df = fetch_pbp(season)
    print(f"{len(df)} plays loaded for {season}")

    overall = _usage_slice(df, red_zone_only=False)
    red_zone = _usage_slice(df, red_zone_only=True)

    merged = overall.merge(
        red_zone, on=["season", "week", "posteam", "player_id", "player"], how="left"
    )
    rz_cols = [c for c in merged.columns if c.startswith("rz_")]
    for c in rz_cols:
        merged[c] = merged[c].fillna(0)

    # Team-week totals, for target_share / air_yards_share / rush_share --
    # computed here rather than left to the API layer, since it's the same
    # groupby every consumer would otherwise repeat.
    team_week_targets = merged.groupby(["season", "week", "posteam"])["targets"].transform("sum")
    team_week_air_yards = merged.groupby(["season", "week", "posteam"])["air_yards"].transform("sum")
    team_week_carries = merged.groupby(["season", "week", "posteam"])["carries"].transform("sum")

    merged["target_share"] = (merged["targets"] / team_week_targets).where(team_week_targets > 0)
    merged["air_yards_share"] = (merged["air_yards"] / team_week_air_yards).where(team_week_air_yards > 0)
    merged["rush_share"] = (merged["carries"] / team_week_carries).where(team_week_carries > 0)

    return merged.sort_values(["season", "week", "posteam", "targets"], ascending=[True, True, True, False])


def current_nfl_season() -> int:
    """nflverse labels a season by the year it starts in (the 2025 season
    ran Sept 2025 - Feb 2026). During the offseason and preseason (through
    August), the most recently completed/relevant season is still last
    year's -- the new one isn't labeled until games are actually played in
    September.
    """
    today = date.today()
    return today.year if today.month >= 9 else today.year - 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=current_nfl_season())
    args = parser.parse_args()

    frame = build(args.season)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "player_week_usage.parquet"
    frame.to_parquet(dest, index=False)

    print(f"{len(frame)} player-week rows across {frame['posteam'].nunique()} teams")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
