"""Full-season MLB schedule and completed game scores, for all 30 teams in
one pull -- feeds three features on the new MLB Matchup page from a single
source rather than three separate ones:

  - Team season record (aggregate wins/losses across all completed games)
  - Recent form (last 10 games record + run differential per team)
  - Head-to-head this season (filter for games between two specific teams)

Same request pattern already proven in get_probable_starters.py, extended
to a date range instead of a single day, and reading each game's own score
fields directly rather than needing a separate boxscore call per game.

    python backend/app/get_mlb_schedule_results.py

Output: backend/data/mlb/schedule_results.parquet (one row per completed
regular-season game), overwritten in full on every run.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import requests

API = "https://statsapi.mlb.com/api/v1"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "mlb"
TIMEOUT = 60
# Regular season never starts before this in a given year -- a wide-enough
# floor that a single call covers the whole season without guessing the
# exact opening day.
SEASON_START_MONTH_DAY = "03-15"


def get_schedule_range(start_date: str, end_date: str) -> list[dict]:
    r = requests.get(
        f"{API}/schedule",
        params={"sportId": 1, "startDate": start_date, "endDate": end_date, "gameType": "R"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return [g for d in r.json().get("dates", []) for g in d["games"]]


def build(season: int) -> pd.DataFrame:
    today = date.today().isoformat()
    start = f"{season}-{SEASON_START_MONTH_DAY}"
    games = get_schedule_range(start, today)

    rows = []
    for g in games:
        status = g.get("status", {}).get("abstractGameState")
        if status != "Final":
            continue  # only completed games -- an in-progress or postponed
            # game has no final score to aggregate, and would silently
            # skew both a record and a run-differential average if left in
        home = g["teams"]["home"]
        away = g["teams"]["away"]
        home_score, away_score = home.get("score"), away.get("score")
        if home_score is None or away_score is None:
            continue
        rows.append({
            "date": g.get("officialDate"),
            "game_pk": g["gamePk"],
            "home_team": home["team"]["name"],
            "away_team": away["team"]["name"],
            "home_score": int(home_score),
            "away_score": int(away_score),
        })

    return pd.DataFrame(rows)


def main() -> None:
    season = date.today().year
    frame = build(season)

    if frame.empty:
        print(f"no completed games found for {season} -- nothing to save")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / "schedule_results.parquet"
    frame.to_parquet(dest, index=False)

    print(f"{len(frame)} completed game(s) for {season}")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
