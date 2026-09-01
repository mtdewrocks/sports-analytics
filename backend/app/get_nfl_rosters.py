"""Current team rosters, to keep player-level projections honest about who
actually plays for a team right now.

player_situational_usage.parquet and player_week_usage.parquet are built
from PLAY-BY-PLAY, which only ever reflects who played for a team DURING
the season that data covers. When that data is itself a fallback to last
season (see get_nfl_pbp.py etc. -- true whenever the current season hasn't
started yet), a player's team in that data can be stale: someone who's
since left via free agency or a trade (e.g. Mike Evans: Tampa Bay in 2025,
San Francisco as of this roster pull) would incorrectly still show up
under their old team without this check.

This does NOT fix the reverse problem -- a player who JOINED a team this
offseason has no situational history under that team at all, since no
snapshot of play-by-play can have him wearing a jersey he didn't wear yet.
There's no way to backfill that from historical data; the correct handling
is to exclude departed players (this script) and separately flag, rather
than silently omit, that new arrivals aren't represented yet.

    python backend/app/get_nfl_rosters.py

Output: backend/data/nfl/rosters.parquet
"""

from __future__ import annotations

import argparse
from datetime import date
from io import StringIO
from pathlib import Path

import pandas as pd
import requests

ROSTER_URL = "https://github.com/nflverse/nflverse-data/releases/download/rosters/roster_{season}.csv"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "nfl"
TIMEOUT = 60


def current_nfl_season() -> int:
    today = date.today()
    return today.year if today.month >= 9 else today.year - 1


def fetch_roster(season: int) -> pd.DataFrame | None:
    url = ROSTER_URL.format(season=season)
    r = requests.get(url, timeout=TIMEOUT)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return pd.read_csv(StringIO(r.text), low_memory=False)


def build(season: int) -> pd.DataFrame:
    roster = fetch_roster(season)
    if roster is None:
        # Unlike weekly stats/play-by-play, roster data doesn't depend on
        # games having been played -- it should exist for any season
        # that's been announced. If this 404s, something's actually wrong
        # rather than "season hasn't started yet."
        raise RuntimeError(f"No roster file for {season} at {ROSTER_URL.format(season=season)}")

    roster = roster[roster["gsis_id"].notna()]
    # Keep only each player's most recent snapshot, in case multiple weekly
    # snapshots exist (there's only one right now, before the season
    # starts, but this stays correct once the season is underway and the
    # file accumulates one row per player per week).
    roster = roster.sort_values("week").drop_duplicates("gsis_id", keep="last")

    return roster[["gsis_id", "full_name", "team", "position", "status"]].rename(
        columns={"gsis_id": "player_id"}
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=current_nfl_season())
    args = parser.parse_args()

    frame = build(args.season)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "rosters.parquet"
    frame.to_parquet(dest, index=False)

    print(f"{len(frame)} players across {frame['team'].nunique()} teams")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
