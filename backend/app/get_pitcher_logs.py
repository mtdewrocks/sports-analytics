"""Game-by-game pitching logs, updated incrementally.

Replaces 2026_Pitching_Logs.xlsx. One row per appearance with the columns the
Recent Game Logs table renders:

    date, opponent, wins, losses, innings, hits, runs, earned_runs,
    home_runs, walks, strikeouts, pitches

Only refetches pitchers who actually started yesterday. A starter works every
fifth day, so re-pulling all ~350 every run would be ~14 batched requests to
rewrite data that has not changed. Yesterday's starters are ~30 pitchers, or
two batches.

Actual starters come from each boxscore's pitcher list, not from the
schedule's probablePitcher -- a late scratch means the probable never threw a
pitch, and his log would be fetched while the real starter's went stale.

First run (no existing parquet) does a full pull from starters.parquet.

No arguments:

    python backend/app/get_pitcher_logs.py

Reads:  backend/data/mlb/starters.parquet        (bootstrap only)
        backend/data/mlb/pitcher_logs.parquet    (previous run)
Writes: backend/data/mlb/pitcher_logs.parquet
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

API = "https://statsapi.mlb.com/api/v1"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "mlb"
BALLPARK_TZ = ZoneInfo("America/Chicago")

SEASON = 2026
ID_CHUNK = 25     # hydrated stats make responses large; keep batches modest
TIMEOUT = 60


def games_on(day: str) -> list[int]:
    """gamePks for a date."""
    r = requests.get(
        f"{API}/schedule",
        params={"sportId": 1, "date": day},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return [g["gamePk"] for d in r.json().get("dates", []) for g in d["games"]]


def starters_in(game_pk: int) -> list[int]:
    """The pitcher who actually started for each side.

    `pitchers` lists ids in order of appearance, so element 0 is the starter.
    """
    try:
        box = requests.get(f"{API}/game/{game_pk}/boxscore", timeout=TIMEOUT).json()
    except Exception as e:
        print(f"  boxscore {game_pk} failed: {e}")
        return []

    out = []
    for side in ("home", "away"):
        pitchers = box.get("teams", {}).get(side, {}).get("pitchers", [])
        if pitchers:
            out.append(int(pitchers[0]))
    return out


def yesterdays_starters(day: str) -> list[int]:
    pks = games_on(day)
    print(f"{len(pks)} game(s) on {day}")

    ids: set[int] = set()
    for pk in pks:
        ids.update(starters_in(pk))
    return sorted(ids)


def fetch_logs(person_ids: list[int]) -> list[dict]:
    """Game logs for a batch of pitchers, flattened to one row per appearance."""
    r = requests.get(
        f"{API}/people",
        params={
            "personIds": ",".join(str(i) for i in person_ids),
            "hydrate": f"stats(group=[pitching],type=[gameLog],season={SEASON})",
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()

    rows = []
    for person in r.json().get("people", []):
        pitcher_id = person.get("id")
        pitcher = person.get("fullName", "")

        for stat_group in person.get("stats", []):
            for split in stat_group.get("splits", []):
                s = split.get("stat", {})
                rows.append(
                    {
                        "pitcher_id": pitcher_id,
                        "pitcher": pitcher,
                        "game_pk": split.get("game", {}).get("gamePk"),
                        "date": split.get("date", ""),
                        "opponent": split.get("opponent", {}).get("name", ""),
                        "is_home": bool(split.get("isHome", False)),
                        "wins": int(s.get("wins", 0) or 0),
                        "losses": int(s.get("losses", 0) or 0),
                        "innings": s.get("inningsPitched", ""),
                        "hits": int(s.get("hits", 0) or 0),
                        "runs": int(s.get("runs", 0) or 0),
                        "earned_runs": int(s.get("earnedRuns", 0) or 0),
                        "home_runs": int(s.get("homeRuns", 0) or 0),
                        "walks": int(s.get("baseOnBalls", 0) or 0),
                        "strikeouts": int(s.get("strikeOuts", 0) or 0),
                        "pitches": int(s.get("numberOfPitches", 0) or 0),
                        "games_started": int(s.get("gamesStarted", 0) or 0),
                    }
                )

    return rows


def fetch_many(pitcher_ids: list[int]) -> pd.DataFrame:
    rows = []

    for i in range(0, len(pitcher_ids), ID_CHUNK):
        chunk = pitcher_ids[i : i + ID_CHUNK]
        try:
            batch = fetch_logs(chunk)
        except Exception as e:
            # One bad batch should not lose the run.
            print(f"  batch {i // ID_CHUNK + 1} failed ({e}); continuing")
            continue

        rows.extend(batch)
        print(f"  batch {i // ID_CHUNK + 1}: {len(batch)} appearance(s)")

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame[frame["date"].notna()]


def merge(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Replace each refetched pitcher's rows wholesale, keep everyone else.

    Replacing per pitcher rather than per game means a corrected box score --
    a scoring change days later -- flows through, since the fetch returns that
    pitcher's whole season.
    """
    if old.empty:
        combined = new
    else:
        refreshed = set(new["pitcher_id"])
        combined = pd.concat([old[~old["pitcher_id"].isin(refreshed)], new], ignore_index=True)

    return (
        combined.drop_duplicates(["pitcher_id", "game_pk"], keep="last")
        .sort_values(["pitcher_id", "date"], ascending=[True, False])
        .reset_index(drop=True)
    )


def main() -> None:
    dest = DATA_DIR / "pitcher_logs.parquet"
    yesterday = (datetime.now(BALLPARK_TZ).date() - timedelta(days=1)).isoformat()

    old = pd.read_parquet(dest) if dest.exists() else pd.DataFrame()

    if old.empty:
        # Bootstrap: no prior file, so pull everyone once.
        starters_path = DATA_DIR / "starters.parquet"
        if not starters_path.exists():
            print("no starters.parquet -- run get_starters.py first")
            return
        targets = pd.read_parquet(starters_path)["pitcher_id"].dropna().astype(int).tolist()
        print(f"no existing logs -- full pull for {len(targets)} pitcher(s)")
    else:
        targets = yesterdays_starters(yesterday)
        print(f"{len(targets)} pitcher(s) started on {yesterday}")

    if not targets:
        print("nothing to update")
        return

    new = fetch_many(targets)
    if new.empty:
        print("no game logs returned; leaving the existing file untouched")
        return

    combined = merge(old, new)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(dest, index=False)

    print(f"{len(combined)} appearances for {combined['pitcher_id'].nunique()} pitcher(s)")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
