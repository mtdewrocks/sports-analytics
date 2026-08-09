"""Pull today's starting pitchers and lineups.

One row per batter, carrying the opposing starter alongside. That shape is what
makes the matchup join trivial later:

    statcast_hitters_2026.xlsx   key = player_id|opp_hand
        -> merge on  batter_id + opp_throws

    statcast_pitchers_2026.xlsx  key = player_id|opp_hand
        -> merge on  opp_starter_id + stand

`opp_hand` in the Statcast splits is always the *opponent's* handedness, so a
batter row needs the pitcher's throwing hand and a pitcher row needs the
batter's stance. Both are included here.

No arguments -- it always pulls the current day's slate, so it can run
unattended in GitHub Actions:

    python backend/app/get_lineups.py

Output: backend/data/mlb/lineups_{date}.csv

Lineups only exist once a team posts them, usually 1-4 hours before first
pitch. An early run gets starters with no lineups; later runs fill them in.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

API = "https://statsapi.mlb.com/api/v1"
OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "mlb"

# Actions runners are on UTC. Without an explicit zone, a 9 PM Central run
# (02:00 UTC) would ask for tomorrow's slate and come back empty.
BALLPARK_TZ = ZoneInfo("America/Chicago")

TIMEOUT = 30


def get_schedule(day: str) -> list[dict]:
    """Games for a date, with the probable starter attached to each side."""
    r = requests.get(
        f"{API}/schedule",
        params={"sportId": 1, "date": day, "hydrate": "probablePitcher"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return [g for d in r.json().get("dates", []) for g in d["games"]]


def get_lineup(game_pk: int, team_id: int) -> list[tuple[int, int, str]]:
    """(slot, batter_id, name) for the nine starters, or [] if not posted yet.

    battingOrder encodes the slot, not a row position: "300" is whoever
    started in the 3rd spot, "301"/"302" are substitutes who later occupied
    it. So slot = value // 100, and the starter is the one ending in 00.

    Both matter. Counting rows instead of parsing the value misnumbers every
    slot below a substitution -- a pinch runner in the 2nd spot would push a
    3rd-spot pinch hitter to slot 4. And keeping only the "00" entries means a
    game already in progress still reports the lineup as posted, rather than
    drifting as substitutes enter.
    """
    try:
        box = requests.get(f"{API}/game/{game_pk}/boxscore", timeout=TIMEOUT).json()
    except Exception:
        return []

    for side in ("home", "away"):
        team = box["teams"][side]
        if team["team"]["id"] != team_id:
            continue
        starters = []
        for p in team["players"].values():
            raw = p.get("battingOrder")
            if not raw:
                continue
            order = int(raw)
            if order % 100 == 0:  # skip substitutes
                starters.append((order // 100, p["person"]["id"], p["person"]["fullName"]))
        return sorted(starters)
    return []


def get_hands(person_ids: set[int]) -> dict[int, dict[str, str]]:
    """{id: {"bats": L/R/S, "throws": L/R}} for every player, in one call."""
    if not person_ids:
        return {}
    r = requests.get(
        f"{API}/people",
        params={"personIds": ",".join(str(i) for i in person_ids)},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return {
        p["id"]: {
            "bats": p.get("batSide", {}).get("code", "R"),
            "throws": p.get("pitchHand", {}).get("code", "R"),
        }
        for p in r.json().get("people", [])
    }


def build(day: str) -> pd.DataFrame:
    rows = []

    for game in get_schedule(day):
        for side, opp in (("home", "away"), ("away", "home")):
            team = game["teams"][side]["team"]
            starter = game["teams"][opp].get("probablePitcher") or {}

            for slot, batter_id, batter_name in get_lineup(game["gamePk"], team["id"]):
                rows.append(
                    {
                        "date": day,
                        "game_pk": game["gamePk"],
                        "game_time_utc": game.get("gameDate", ""),
                        "team": team["name"],
                        "opponent": game["teams"][opp]["team"]["name"],
                        "home_away": side,
                        "slot": slot,
                        "batter_id": batter_id,
                        "batter_name": batter_name,
                        "opp_starter_id": starter.get("id"),
                        "opp_starter_name": starter.get("fullName", ""),
                    }
                )

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    # One batched lookup for every batter and starter on the slate.
    ids = set(frame["batter_id"]) | set(frame["opp_starter_id"].dropna().astype(int))
    hands = get_hands(ids)

    frame["bats"] = frame["batter_id"].map(lambda i: hands.get(i, {}).get("bats", "R"))
    frame["opp_throws"] = frame["opp_starter_id"].map(
        lambda i: hands.get(i, {}).get("throws", "") if pd.notna(i) else ""
    )

    # Two columns on purpose:
    #   bats  -- as listed, so a switch hitter still reads "S" for display
    #   stand -- the side they will actually hit from today, which is the only
    #            thing that joins to a vs-LHP / vs-RHP split
    frame["stand"] = frame["bats"]
    switch = frame["bats"].eq("S") & frame["opp_throws"].isin(["L", "R"])
    frame.loc[switch, "stand"] = frame.loc[switch, "opp_throws"].map({"L": "R", "R": "L"})

    return frame


def main() -> None:
    day = datetime.now(BALLPARK_TZ).date().isoformat()

    frame = build(day)
    if frame.empty:
        print(f"No lineups posted yet for {day}.")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dest = OUT_DIR / f"lineups_{day}.csv"
    frame.to_csv(dest, index=False)

    games = frame["game_pk"].nunique()
    missing = frame["opp_starter_id"].isna().sum()
    print(f"{len(frame)} batters across {games} game(s)")
    if missing:
        print(f"note: {missing} row(s) have no probable starter announced yet")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
