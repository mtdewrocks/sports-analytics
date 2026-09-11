"""Per-player NFL season totals, across multiple seasons -- feeds the
Season Stat Screener page (e.g. "how many RBs had 1000+ rushing yards" or
"250+ carries AND 100+ targets" for a chosen season).

Pulled directly from nflverse's stats_player_week_{season}.csv, the same
source already used by get_nfl_weekly_stats.py -- NOT Player_Stats_Weekly
.parquet, which was checked directly and found to have zero rows for the
current in-progress season (2026), only completed prior seasons. A stat
screener that's supposed to cover "this season" needs a source that
actually has this season's in-progress data, even if partial.

Aggregates by summing each player's own weekly rows within a season --
correct for counting stats (yards, carries, targets, receptions,
touchdowns), which is what this page's filters are built around.

    python backend/app/get_nfl_season_totals.py

Reads:  stats_player_week_{season}.csv for each season in SEASONS below
Writes: backend/data/nfl/player_season_totals.parquet
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

WEEKLY_STATS_URL = "https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "nfl"
TIMEOUT = 60

# Extend this list as future seasons start -- each one just needs adding
# here, no other code changes required for a new season to show up.
SEASONS = [2025, 2026]

# Counting stats this page's filters are built around. Sums across a
# player's own weekly rows within one season -- correct for all of these
# (rate stats like yards-per-carry would need a different aggregation,
# not attempted here since the requested filters are all counting stats).
SUM_STATS = [
    "carries", "rushing_yards", "rushing_tds",
    "targets", "receptions", "receiving_yards", "receiving_tds",
    "attempts", "completions", "passing_yards", "passing_tds", "passing_interceptions",
    "def_sacks", "def_interceptions",
]


def fetch_weekly_stats(season: int) -> pd.DataFrame:
    url = WEEKLY_STATS_URL.format(season=season)
    r = requests.get(url, timeout=TIMEOUT)
    if r.status_code == 404:
        print(f"{season}: no data yet (404), skipping")
        return pd.DataFrame()
    r.raise_for_status()
    from io import StringIO
    return pd.read_csv(StringIO(r.text), low_memory=False)


def build_season(season: int) -> pd.DataFrame:
    weekly = fetch_weekly_stats(season)
    if weekly.empty:
        return pd.DataFrame()

    weekly.columns = [c.lower() for c in weekly.columns]
    name_col = "player_display_name" if "player_display_name" in weekly.columns else "player_name"
    group_cols = [name_col, "team", "position", "position_group"]
    group_cols = [c for c in group_cols if c in weekly.columns]

    agg = {stat: "sum" for stat in SUM_STATS if stat in weekly.columns}
    agg["week"] = "nunique"

    totals = weekly.groupby(group_cols, as_index=False).agg(agg)
    totals = totals.rename(columns={name_col: "player", "week": "games_played"})
    totals["season"] = season
    return totals


def main() -> None:
    frames = [build_season(s) for s in SEASONS]
    frames = [f for f in frames if not f.empty]

    if not frames:
        print("no data for any configured season -- nothing to save")
        return

    combined = pd.concat(frames, ignore_index=True)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "player_season_totals.parquet"
    combined.to_parquet(dest, index=False)

    for season in SEASONS:
        count = len(combined[combined["season"] == season])
        print(f"{season}: {count} players")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
