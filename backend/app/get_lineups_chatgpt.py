```python
"""Pull today's MLB starting pitchers and posted lineups.

The script creates one row per starting batter and includes the opposing
probable starting pitcher. The resulting file is used later to join today's
matchups to the Statcast hitter/pitcher data.

Expected repository structure:

    backend/
    ├── app/
    │   └── get_lineups.py
    └── data/
        └── mlb/
            └── lineups_YYYY-MM-DD.csv

The script takes no command-line arguments. It always uses today's date in
Central Time so it can run unattended from GitHub Actions.

Example:

    python backend/app/get_lineups.py

Important:
    MLB lineups are not necessarily available early in the day. If the script
    runs before lineups are posted, it may produce no rows. Running it again
    later will pick up the posted lineups.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
# Keep the settings that you may want to change in one place.

API_BASE = "https://statsapi.mlb.com/api/v1"
TIMEOUT = 30

# GitHub Actions runs on UTC, but MLB games and lineup announcements should
# be interpreted using Central Time for this project.
MLB_TIMEZONE = ZoneInfo("America/Chicago")

# This file lives in:
#
#     backend/app/get_lineups.py
#
# parent      = backend/app
# parent.parent = backend
#
# Therefore this resolves to:
#
#     backend/data/mlb
#
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "mlb"


# ---------------------------------------------------------------------------
# HTTP HELPERS
# ---------------------------------------------------------------------------

def get_json(
    session: requests.Session,
    endpoint: str,
    *,
    params: dict | None = None,
) -> dict:
    """Request an MLB Stats API endpoint and return its JSON response.

    Keeping API requests in one helper gives us consistent timeout and error
    handling. If MLB returns an HTTP error, raise_for_status() makes the
    GitHub Action fail instead of quietly producing incomplete data.
    """
    response = session.get(
        f"{API_BASE}/{endpoint.lstrip('/')}",
        params=params,
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# MLB API FUNCTIONS
# ---------------------------------------------------------------------------

def get_schedule(
    session: requests.Session,
    day: str,
) -> list[dict]:
    """Return MLB games scheduled for ``day``.

    The probablePitcher hydration tells MLB Stats API to include the probable
    starting pitcher directly in each team's game information, which saves us
    from making a separate API request for every pitcher.
    """
    data = get_json(
        session,
        "schedule",
        params={
            "sportId": 1,
            "date": day,
            "hydrate": "probablePitcher",
        },
    )

    return [
        game
        for schedule_day in data.get("dates", [])
        for game in schedule_day.get("games", [])
    ]


def get_lineup(
    session: requests.Session,
    game_pk: int,
    team_id: int,
) -> list[tuple[int, str]]:
    """Return the nine starting batters for a team in batting-order sequence.

    MLB's ``battingOrder`` field is a string such as ``"300"`` for the third
    batting slot. Values such as ``"301"`` represent a replacement batting in
    that same slot.

    Sorting the values and taking the first nine gives us the currently posted
    starting lineup rather than every player who appears in the box score.

    Returns:
        A list of ``(player_id, player_name)`` tuples.
        Returns an empty list if the lineup has not been posted yet.
    """
    data = get_json(session, f"game/{game_pk}/boxscore")

    for side in ("home", "away"):
        team = data.get("teams", {}).get(side, {})

        if team.get("team", {}).get("id") != team_id:
            continue

        players = team.get("players", {}).values()

        ordered = [
            (
                player["battingOrder"],
                player["person"]["id"],
                player["person"]["fullName"],
            )
            for player in players
            if player.get("battingOrder")
        ]

        ordered.sort(key=lambda row: row[0])

        return [
            (player_id, player_name)
            for _, player_id, player_name in ordered[:9]
        ]

    return []


def get_hands(
    session: requests.Session,
    player_ids: set[int],
) -> dict[int, dict[str, str]]:
    """Return batting and throwing handedness for all supplied players.

    MLB's /people endpoint accepts multiple player IDs in a single request,
    so we intentionally batch all batter and probable-starter lookups into
    one API call instead of making a request for every player.
    """
    if not player_ids:
        return {}

    data = get_json(
        session,
        "people",
        params={
            "personIds": ",".join(str(player_id) for player_id in sorted(player_ids))
        },
    )

    return {
        player["id"]: {
            "bats": player.get("batSide", {}).get("code", "R"),
            "throws": player.get("pitchHand", {}).get("code", "R"),
        }
        for player in data.get("people", [])
    }


# ---------------------------------------------------------------------------
# DATA BUILDING
# ---------------------------------------------------------------------------

def build_lineups(
    session: requests.Session,
    day: str,
) -> pd.DataFrame:
    """Build today's batter-level matchup table.

    Each row represents one starting batter and contains:

    - game information
    - team/opponent
    - batting-order slot
    - batter ID/name
    - opposing probable starter ID/name
    - batter stance
    - opposing pitcher's throwing hand

    Switch hitters are resolved here. If a batter is listed as ``S`` and the
    opposing starter throws left-handed, the batter's effective stance is
    right-handed, and vice versa. This gives us the actual handedness needed
    for the Statcast split lookup.
    """
    rows: list[dict] = []

    for game in get_schedule(session, day):
        game_pk = game["gamePk"]

        for side, opponent_side in (
            ("home", "away"),
            ("away", "home"),
        ):
            team_info = game["teams"][side]["team"]
            opponent_info = game["teams"][opponent_side]["team"]

            lineup = get_lineup(
                session,
                game_pk,
                team_info["id"],
            )

            # A game can exist on the schedule before either team has posted
            # its starting lineup. Just skip that team for this run.
            if not lineup:
                continue

            starter = (
                game["teams"][opponent_side].get("probablePitcher")
                or {}
            )

            for slot, (batter_id, batter_name) in enumerate(lineup, start=1):
                rows.append(
                    {
                        "date": day,
                        "game_pk": game_pk,
                        "game_time_utc": game.get("gameDate", ""),
                        "team": team_info["name"],
                        "opponent": opponent_info["name"],
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

    # We now know every batter and every probable starter appearing in the
    # slate. Look up all handedness information in one API request.
    player_ids = set(frame["batter_id"].astype(int))

    starter_ids = (
        frame["opp_starter_id"]
        .dropna()
        .astype(int)
    )

    player_ids.update(starter_ids)

    hands = get_hands(session, player_ids)

    frame["stand"] = frame["batter_id"].map(
        lambda player_id: hands.get(player_id, {}).get("bats", "R")
    )

    frame["opp_throws"] = frame["opp_starter_id"].map(
        lambda player_id: (
            hands.get(int(player_id), {}).get("throws", "")
            if pd.notna(player_id)
            else ""
        )
    )

    # Switch hitters do not have one fixed matchup side. Resolve their
    # effective stance based on the opposing starter:
    #
    #     vs LHP -> R
    #     vs RHP -> L
    #
    switch_hitter = (
        frame["stand"].eq("S")
        & frame["opp_throws"].isin(("L", "R"))
    )

    frame.loc[switch_hitter, "stand"] = (
        frame.loc[switch_hitter, "opp_throws"]
        .map({"L": "R", "R": "L"})
    )

    return frame


# ---------------------------------------------------------------------------
# OUTPUT
# ---------------------------------------------------------------------------

def save_lineups(
    frame: pd.DataFrame,
    day: str,
) -> Path:
    """Save today's lineup data and return the output path."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    destination = DATA_DIR / f"lineups_{day}.csv"
    frame.to_csv(destination, index=False)

    return destination


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the daily MLB lineup update.

    The date is calculated in Central Time, the MLB schedule and posted
    lineups are retrieved, handedness is resolved, and the finished CSV is
    written to backend/data/mlb.
    """
    day = datetime.now(MLB_TIMEZONE).date().isoformat()

    print(f"Checking MLB lineups for {day}...")

    # Reuse one HTTP session for all requests made during this run.
    with requests.Session() as session:
        frame = build_lineups(session, day)

    if frame.empty:
        print(f"No lineups posted yet for {day}.")
        return

    destination = save_lineups(frame, day)

    games = frame["game_pk"].nunique()
    missing_starters = frame["opp_starter_id"].isna().sum()

    print(f"{len(frame)} batters across {games} game(s)")

    if missing_starters:
        print(
            f"Note: {missing_starters} row(s) have no probable "
            "starter announced yet."
        )

    print(f"Saved -> {destination}")


if __name__ == "__main__":
    main()
```
