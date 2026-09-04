"""Current active MLB roster for every team -- player_id -> team lookup.

Unlike a rolling game log, this doesn't depend on a player having appeared
in a recent game: it's a fresh snapshot of every team's active roster,
refreshed on every run, so a trade or call-up is correct within the hour
rather than lagging behind whenever the player next appears in a box score.

This replaces Hitter_Game_Logs_2026.parquet as the player -> team source for
get_hot_hitters() -- that file was a one-time import never wired into any
refresh pipeline, and by September was already four months stale (frozen at
its original March-May snapshot) with no way to close the gap going forward.

One row per active roster spot:

    player_id, player, team

Overwritten in full on every run -- a roster is a current snapshot, not
something to accumulate history for.

Reads:  nothing
Writes: backend/data/mlb/mlb_rosters.parquet
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

API = "https://statsapi.mlb.com/api/v1"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "mlb"
TIMEOUT = 60


def all_team_ids() -> dict[int, str]:
    r = requests.get(f"{API}/teams", params={"sportId": 1}, timeout=TIMEOUT)
    r.raise_for_status()
    return {t["id"]: t["name"] for t in r.json().get("teams", [])}


def roster_for(team_id: int) -> list[dict]:
    try:
        r = requests.get(
            f"{API}/teams/{team_id}/roster",
            params={"rosterType": "active"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
    except Exception as e:
        print(f"  team {team_id} failed: {e}")
        return []
    return [
        {"player_id": p["person"]["id"], "player": p["person"]["fullName"]}
        for p in r.json().get("roster", [])
    ]


def main() -> None:
    teams = all_team_ids()
    print(f"{len(teams)} team(s)")

    rows = []
    for team_id, team_name in teams.items():
        players = roster_for(team_id)
        for p in players:
            rows.append({**p, "team": team_name})
        print(f"  {team_name}: {len(players)} active roster spot(s)")

    if not rows:
        print("nothing fetched; leaving any existing file untouched")
        return

    frame = pd.DataFrame(rows)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "mlb_rosters.parquet"
    frame.to_parquet(dest, index=False)

    print(f"{len(frame)} active roster spot(s) across {frame['team'].nunique()} team(s)")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
