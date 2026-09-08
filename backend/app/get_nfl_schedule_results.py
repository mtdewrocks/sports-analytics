"""Full NFL schedule and completed game scores across every season
nflverse has, for all 32 teams in one pull -- the box-score analog of
get_mlb_schedule_results.py. Feeds team win/loss records for the parlay
pace feed (build_pace_feed.py), and is generally reusable for anything
else that needs a team's record or remaining-games count (recent form,
head-to-head, playoff odds, etc.).

Unlike the MLB version, this keeps every season in one file rather than
filtering to just the current one: the single nflverse request already
returns full history for free, and get_nfl_player_box_stats.py falls back
to last season's data before Week 1 -- filtering this file to only the
current season would leave that fallback season's games missing here,
silently zeroing out every team's record in build_pace_feed.py right when
the fallback is doing its job. Downstream consumers filter by season
themselves.

Same nflverse-data-direct approach as get_nfl_pbp.py and
get_nfl_player_box_stats.py: nflverse publishes the full schedule
(including this season's, with scores filled in as games finish) as a
public CSV, no package or auth needed.

One row per game -- including ones that haven't been played yet (with null
scores). Downstream consumers filter to completed games themselves (see
build_pace_feed.py), same division of responsibility as
get_mlb_schedule_results.py's per-game rows.

    python backend/app/get_nfl_schedule_results.py

Output: backend/data/nfl/schedule_results.parquet
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path

import pandas as pd
import requests

NFLVERSE_GAMES_URL = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "nfl"
TIMEOUT = 60

KEEP_COLUMNS = [
    "season", "game_type", "week", "gameday",
    "home_team", "away_team", "home_score", "away_score",
]


def fetch_games() -> pd.DataFrame:
    r = requests.get(NFLVERSE_GAMES_URL, timeout=TIMEOUT)
    r.raise_for_status()
    return pd.read_csv(io.BytesIO(r.content), low_memory=False)


def build() -> pd.DataFrame:
    df = fetch_games()
    frame = df[[c for c in KEEP_COLUMNS if c in df.columns]].copy()

    current = current_nfl_season()
    completed_current = frame[(frame["season"] == current) & frame["home_score"].notna()]
    print(f"{len(frame)} scheduled game(s) across {frame['season'].nunique()} seasons "
          f"({len(completed_current)} completed so far for {current})")
    return frame


def current_nfl_season() -> int:
    """Same rule as get_nfl_pbp.py's current_nfl_season()."""
    today = date.today()
    return today.year if today.month >= 9 else today.year - 1


def main() -> None:
    frame = build()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "schedule_results.parquet"
    frame.to_parquet(dest, index=False)

    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
