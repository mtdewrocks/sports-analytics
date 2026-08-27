"""Season pitching stats for every pitcher who has thrown a pitch this season.

get_starters.py hits the same MLB Stats API endpoint (`stats=season,
group=pitching, playerPool=All`) but throws away every row with
games_started < 1 -- fine for a starter dropdown, but it means true
relievers have no season ERA/WHIP/K%/BB% anywhere in the data. This script
keeps everyone, so the Bullpen page can show real season rates instead of
a rolling window computed from ~14 days of appearance logs.

Also captures battersFaced (for K%/BB%, which need a PA denominator that
raw innings can't give you) and throwing hand -- closing the handedness
gap noted in get_bullpen_status().

No arguments:

    python backend/app/get_season_pitching_stats.py

Output: backend/data/mlb/season_pitching_stats.parquet
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

API = "https://statsapi.mlb.com/api/v1"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "mlb"
BALLPARK_TZ = ZoneInfo("America/Chicago")

SEASON = 2026
PAGE_SIZE = 500
ID_CHUNK = 100
TIMEOUT = 30


def season_pitchers() -> list[dict]:
    """Every pitcher with season stats, paged until the API stops returning."""
    out, offset = [], 0

    while True:
        r = requests.get(
            f"{API}/stats",
            params={
                "stats": "season",
                "group": "pitching",
                "season": SEASON,
                "sportId": 1,
                "playerPool": "All",
                "limit": PAGE_SIZE,
                "offset": offset,
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()

        splits = [s for stat in r.json().get("stats", []) for s in stat.get("splits", [])]
        if not splits:
            break

        out.extend(splits)
        if len(splits) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    return out


def get_people(person_ids: list[int]) -> dict[int, dict]:
    people = {}
    for i in range(0, len(person_ids), ID_CHUNK):
        chunk = person_ids[i : i + ID_CHUNK]
        r = requests.get(
            f"{API}/people",
            params={
                "personIds": ",".join(str(p) for p in chunk),
                "hydrate": "currentTeam",
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()

        for p in r.json().get("people", []):
            people[p["id"]] = {
                "throws": p.get("pitchHand", {}).get("code", ""),
                "team": p.get("currentTeam", {}).get("name", ""),
            }
    return people


def outs(innings: str | float | None) -> int:
    try:
        whole, _, frac = str(innings or "0").partition(".")
        return int(whole or 0) * 3 + int((frac or "0")[:1])
    except ValueError:
        return 0


def build() -> pd.DataFrame:
    rows = []

    for split in season_pitchers():
        stat = split.get("stat", {})
        player = split.get("player", {})
        rows.append(
            {
                "pitcher_id": player.get("id"),
                "pitcher": player.get("fullName", ""),
                "games_started": int(stat.get("gamesStarted", 0) or 0),
                "games_played": int(stat.get("gamesPlayed", 0) or 0),
                "_outs": outs(stat.get("inningsPitched")),
                "_er": int(stat.get("earnedRuns", 0) or 0),
                "_hits": int(stat.get("hits", 0) or 0),
                "_walks": int(stat.get("baseOnBalls", 0) or 0),
                "strikeouts": int(stat.get("strikeOuts", 0) or 0),
                "batters_faced": int(stat.get("battersFaced", 0) or 0),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    # A traded pitcher gets one row per team -- sum, then recompute rates
    # from the combined components rather than averaging two partial ERAs.
    frame = frame.groupby(["pitcher_id", "pitcher"], as_index=False).agg(
        {
            "games_started": "sum",
            "games_played": "sum",
            "_outs": "sum",
            "_er": "sum",
            "_hits": "sum",
            "_walks": "sum",
            "strikeouts": "sum",
            "batters_faced": "sum",
        }
    )

    people = get_people(frame["pitcher_id"].astype(int).tolist())
    frame["throws"] = frame["pitcher_id"].map(lambda i: people.get(i, {}).get("throws", ""))
    frame["team"] = frame["pitcher_id"].map(lambda i: people.get(i, {}).get("team", ""))

    frame["role"] = frame["games_started"].apply(lambda gs: "SP" if gs >= 1 else "RP")

    ip_exact = (frame["_outs"] / 3).where(frame["_outs"] > 0)
    bf = frame["batters_faced"].where(frame["batters_faced"] > 0)

    frame["innings"] = (frame["_outs"] // 3) + (frame["_outs"] % 3) / 10
    frame["era"] = (9 * frame["_er"] / ip_exact).round(2)
    frame["whip"] = ((frame["_hits"] + frame["_walks"]) / ip_exact).round(3)
    frame["k_pct"] = (100 * frame["strikeouts"] / bf).round(1)
    frame["bb_pct"] = (100 * frame["_walks"] / bf).round(1)

    frame["season"] = SEASON
    frame = frame[
        ["pitcher_id", "pitcher", "throws", "team", "role", "games_started",
         "games_played", "innings", "era", "whip", "k_pct", "bb_pct", "season"]
    ]
    return frame.sort_values("pitcher").reset_index(drop=True)


def main() -> None:
    frame = build()
    if frame.empty:
        print(f"No {SEASON} pitching stats returned")
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "season_pitching_stats.parquet"
    frame.to_parquet(dest, index=False)

    stamp = datetime.now(BALLPARK_TZ).date().isoformat()
    sp = int((frame["role"] == "SP").sum())
    rp = int((frame["role"] == "RP").sum())
    print(f"{len(frame)} pitchers ({sp} SP, {rp} RP) with {SEASON} stats (as of {stamp})")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
