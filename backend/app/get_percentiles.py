"""Download Baseball Savant percentile rankings for pitchers and hitters.

Replaces the manual export of Pitcher_Percentile_Rankings.csv and
Hitter_Percentile_Rankings.csv. Savant serves the same table the leaderboard
page shows as a CSV, so this is the identical data you have now -- just
fetched on a schedule instead of by hand.

No other source publishes these: the percentiles are Savant's own computation
against their league-wide Statcast distribution.

Written as parquet rather than CSV so the dashboard reads them the same way as
everything else, and so player_id keeps its integer type instead of arriving
as a quoted string.

No arguments:

    python backend/app/get_percentiles.py

Writes: backend/data/mlb/pitcher_percentiles.parquet
        backend/data/mlb/hitter_percentiles.parquet
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "mlb"

SEASON = 2026
URL = (
    "https://baseballsavant.mlb.com/leaderboard/percentile-rankings"
    "?type={kind}&year={year}&csv=true"
)

# Savant rejects requests without a browser-like User-Agent.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/csv,*/*",
}

TIMEOUT = 60
MIN_ROWS = 50  # a real leaderboard has hundreds; fewer means something is wrong


def fetch(kind: str, year: int = SEASON) -> pd.DataFrame:
    """One leaderboard: kind is "pitcher" or "batter"."""
    url = URL.format(kind=kind, year=year)
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()

    # utf-8-sig strips the BOM Savant prefixes, which would otherwise turn the
    # first column into "﻿player_name" and break every lookup.
    frame = pd.read_csv(io.BytesIO(r.content), encoding="utf-8-sig")
    frame.columns = [c.strip().strip('"') for c in frame.columns]

    if "player_id" in frame.columns:
        frame["player_id"] = pd.to_numeric(frame["player_id"], errors="coerce").astype("Int64")

    return frame


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Savant calls the hitter leaderboard "batter"; the dashboard calls the
    # file "hitter". Map between the two here rather than renaming downstream.
    for kind, label in (("pitcher", "pitcher"), ("batter", "hitter")):
        try:
            frame = fetch(kind)
        except Exception as e:
            print(f"{label}: fetch failed ({e}); leaving any existing file alone")
            continue

        if len(frame) < MIN_ROWS:
            print(f"{label}: only {len(frame)} row(s) returned; refusing to overwrite")
            continue

        dest = DATA_DIR / f"{label}_percentiles.parquet"
        frame.to_parquet(dest, index=False)
        print(f"{label}: {len(frame)} players, {len(frame.columns)} columns -> {dest.name}")


if __name__ == "__main__":
    main()
