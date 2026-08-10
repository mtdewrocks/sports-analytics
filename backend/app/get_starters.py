"""Every pitcher who has started a game this season, for the dropdown.

Season-long, not just today's probables -- users can pull up any starter's
stats at any time. The matchup table will simply be empty for a pitcher who
isn't starting today, which is expected.

Keyed on `pitcher_id` (MLBAM). That is the same id used by:
  * daily_matchups.parquet         -> pitcher_id
  * Pitcher_Percentile_Rankings.csv -> player_id
  * Baseball Savant player URLs

so percentiles join on the id rather than on a name. `savant_name` is carried
for display and for the older Savant-named Excel files, but joining on it is
fragile -- accents, suffixes ("Leiter Jr., Mark") and initials ("Ginn, J.T.")
all vary between sources.

Deliberately not pybaseball: this uses the MLB Stats API, the same source as
get_lineups.py, so names and ids line up exactly. pybaseball routes through
FanGraphs, which is currently returning 403.

No arguments:

    python backend/app/get_starters.py

Output: backend/data/mlb/starters.parquet
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
ID_CHUNK = 100          # keep the /people query string to a sane length
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
    """Handedness and name parts, in chunks so no URL gets too long."""
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
                # Savant renders "lastName, useName" -- useName is the name the
                # player goes by, which is not always firstName.
                "last": p.get("lastName", ""),
                "first": p.get("useName") or p.get("firstName", ""),
                # Roster team as of right now. The season stats endpoint returns
                # one row per team for a traded pitcher and has no dates, so it
                # cannot answer "who does he play for today" -- Skubal would
                # still read Tigers on games-started alone.
                "team": p.get("currentTeam", {}).get("name", ""),
            }

    return people


def outs(innings: str | float | None) -> int:
    """Innings-pitched notation -> outs.

    IP is base-3 in disguise: "100.1" is 100 innings and one out, not 100.1.
    Adding those as decimals drifts, so convert to outs, sum, convert back.
    """
    try:
        whole, _, frac = str(innings or "0").partition(".")
        return int(whole or 0) * 3 + int((frac or "0")[:1])
    except ValueError:
        return 0


def build() -> pd.DataFrame:
    rows = []

    for split in season_pitchers():
        stat = split.get("stat", {})
        games_started = int(stat.get("gamesStarted", 0) or 0)
        if games_started < 1:
            continue  # relievers only -- not dropdown material

        player = split.get("player", {})
        rows.append(
            {
                "pitcher_id": player.get("id"),
                "pitcher": player.get("fullName", ""),
                "games_started": games_started,
                "_outs": outs(stat.get("inningsPitched")),
                "_er": int(stat.get("earnedRuns", 0) or 0),
                "strikeouts": int(stat.get("strikeOuts", 0) or 0),
            }
        )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    # A traded pitcher gets one row per team. Sum the counting stats so the
    # season totals are whole, then recompute ERA from the combined figures --
    # averaging two ERAs would be wrong, and picking one team's row would throw
    # away half the season.
    frame = (
        frame.groupby(["pitcher_id", "pitcher"], as_index=False)
        .agg({"games_started": "sum", "_outs": "sum", "_er": "sum", "strikeouts": "sum"})
    )

    people = get_people(frame["pitcher_id"].astype(int).tolist())
    frame["throws"] = frame["pitcher_id"].map(lambda i: people.get(i, {}).get("throws", ""))
    frame["savant_name"] = frame["pitcher_id"].map(
        lambda i: f"{people.get(i, {}).get('last', '')}, {people.get(i, {}).get('first', '')}".strip(", ")
    )
    # Current roster team, so a traded pitcher reads as his new club.
    frame["team"] = frame["pitcher_id"].map(lambda i: people.get(i, {}).get("team", ""))

    frame["innings"] = (frame["_outs"] // 3) + (frame["_outs"] % 3) / 10
    frame["era"] = (9 * frame["_er"] / (frame["_outs"] / 3).where(frame["_outs"] > 0)).round(2)

    frame["season"] = SEASON
    frame = frame[
        ["pitcher_id", "pitcher", "savant_name", "throws", "team",
         "games_started", "innings", "era", "strikeouts", "season"]
    ]
    return frame.sort_values("pitcher").reset_index(drop=True)


def main() -> None:
    frame = build()
    if frame.empty:
        print(f"No {SEASON} starters returned")
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "starters.parquet"
    frame.to_parquet(dest, index=False)

    stamp = datetime.now(BALLPARK_TZ).date().isoformat()
    print(f"{len(frame)} pitchers with a {SEASON} start (as of {stamp})")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
