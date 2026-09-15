"""Pull nflverse's per-player weekly box-score stats (passing, rushing,
receiving) for the current season AND the season before it, combined into
one file.

Same source and same both-seasons-combined approach as
get_nfl_season_totals.py, and for the same reason: the NFL Game Log page
used to read Player_Stats_Weekly.parquet (a legacy file from the separate
sports_analysis repo), which was checked directly and found to sit frozen
on last season -- it never picked up the current season's games at all, no
matter how often this repo's own workflows ran. This script gives Game Log
its own live source, and keeping both seasons in the same file (rather than
one replacing the other, which is what this script used to do) is what
lets the page offer a season toggle instead of just whichever one season
happened to be "current" at pull time.

Column names are kept exactly as nflverse publishes them (passing_
interceptions, sacks_suffered, etc.) rather than renamed to match the old
legacy file's naming -- matching get_nfl_season_totals.py's convention,
since both scripts read the same source file and there's no reason for two
different mental models of the same columns. backend/app/data/nfl.py's
Game-Log-specific stat lists (PASSING_STATS etc.) were updated to match.

Not carried over from the legacy source: derived ratios (completion
percentage, yards per carry/reception, passer rating) and defensive box
stats (sacks recorded, tackles, passes defended). Neither nflverse's classic
weekly file nor -- as far as could be checked -- the legacy one actually
populated these, so this isn't believed to be a real loss of function; flag
it if a stat you used regularly goes missing from the dropdown.

    python backend/app/get_nfl_player_box_stats.py

Reads:  stats_player_week_{season}.csv for each season in SEASONS below
Writes: backend/data/nfl/player_box_stats.parquet
"""

from __future__ import annotations

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

# Extend this list as future seasons start -- see get_nfl_season_totals.py,
# which uses this identical pattern against this identical source file.
SEASONS = [2025, 2026]

KEEP_COLUMNS = [
    "season", "week", "season_type",
    "team", "opponent_team",
    "player_id", "player_display_name", "position",
    "completions", "attempts", "passing_yards", "passing_tds",
    "passing_interceptions", "sacks_suffered",
    "carries", "rushing_yards", "rushing_tds",
    "receptions", "targets", "receiving_yards", "receiving_tds",
    "receiving_air_yards",
]


def fetch_stats(season: int) -> pd.DataFrame:
    """Empty DataFrame (not an exception) when the season's file doesn't
    exist yet -- e.g. a season before its Week 1 -- so build() can just
    skip it instead of the whole run failing."""
    url = NFLVERSE_STATS_URL.format(season=season)
    r = requests.get(url, timeout=TIMEOUT)
    if r.status_code == 404:
        print(f"{season}: no data yet (404), skipping")
        return pd.DataFrame()
    r.raise_for_status()
    df = pd.read_csv(StringIO(r.text), low_memory=False)
    df.columns = [c.lower() for c in df.columns]
    return df


def build_season(season: int) -> pd.DataFrame:
    df = fetch_stats(season)
    if df.empty:
        return df
    # Regular season only, matching the rest of this app's NFL scripts
    # (get_nfl_pbp.py, get_nfl_weekly_stats.py). season_type is nflverse's
    # own field for this -- more reliable than a week-number cutoff once
    # this file also carries playoff weeks, which restart week numbering.
    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    return df[[c for c in KEEP_COLUMNS if c in df.columns]].copy()


def main() -> None:
    frames = [build_season(s) for s in SEASONS]
    frames = [f for f in frames if not f.empty]

    if not frames:
        raise RuntimeError(
            f"No player stats available for any of {SEASONS}. Something's "
            f"genuinely wrong (not just \"season hasn't started\") -- check "
            f"https://github.com/nflverse/nflverse-data/releases/tag/stats_player directly."
        )

    frame = pd.concat(frames, ignore_index=True)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "player_box_stats.parquet"
    frame.to_parquet(dest, index=False)

    for season in SEASONS:
        count = len(frame[frame["season"] == season])
        print(f"{season}: {count} player-week rows")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
