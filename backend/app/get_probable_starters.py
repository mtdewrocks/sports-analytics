"""Today's probable starting pitchers -- team, opponent, no lineup required.

get_lineups.py already fetches this exact information (schedule with
hydrate=probablePitcher) but only WRITES a row once a team's actual batting
lineup has posted, since its output shape is one row per batter. That means
the probable starter -- known well before the lineup, often hours earlier --
gets silently discarded on every early-day run.

This is the same schedule fetch, kept independent of lineup posting, so
get_pitcher_daily_report() can show every one of today's starters right
away, only leaving lineup-dependent columns (opposing lineup toughness)
blank until that data actually exists -- rather than the whole pitcher not
appearing at all until lineups post.

No arguments -- always the current day's slate:

    python backend/app/get_probable_starters.py

Output: backend/data/mlb/probable_starters.parquet (overwritten in full on
every run -- a probable-starters list is a snapshot, not something to
accumulate history for).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

API = "https://statsapi.mlb.com/api/v1"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "mlb"
TIMEOUT = 30

# Same reasoning as get_lineups.py: Actions runners are on UTC, so without
# an explicit zone a late-evening run would ask for tomorrow's slate.
BALLPARK_TZ = ZoneInfo("America/Chicago")


def get_schedule(day: str) -> list[dict]:
    r = requests.get(
        f"{API}/schedule",
        params={"sportId": 1, "date": day, "hydrate": "probablePitcher"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return [g for d in r.json().get("dates", []) for g in d["games"]]


def build(day: str) -> pd.DataFrame:
    rows = []
    for game in get_schedule(day):
        for side, opp in (("home", "away"), ("away", "home")):
            team = game["teams"][side]["team"]
            starter = game["teams"][side].get("probablePitcher") or {}
            if not starter:
                continue  # not announced yet -- not the same as "no game"
            rows.append({
                "date": day,
                "game_pk": game["gamePk"],
                "pitcher_id": starter.get("id"),
                "pitcher": starter.get("fullName", ""),
                "team": team["name"],
                "opponent": game["teams"][opp]["team"]["name"],
                "is_home": side == "home",
            })
    return pd.DataFrame(rows)


def main() -> None:
    day = datetime.now(BALLPARK_TZ).date().isoformat()

    frame = build(day)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / "probable_starters.parquet"

    if frame.empty:
        print(f"No probable starters announced yet for {day}; leaving any existing file untouched")
        return

    frame.to_parquet(dest, index=False)
    print(f"{len(frame)} probable starter(s) for {day}")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
