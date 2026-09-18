"""Game-by-game batting logs, updated incrementally.

Mirrors get_pitcher_logs.py exactly, but for hitters: one row per game
played, with the columns the Hit Rate Sheet's batter markets grade against:

    date, opponent, at_bats, plate_appearances, runs, hits, doubles,
    triples, home_runs, rbi, walks, strikeouts, stolen_bases, total_bases

Sourced from the MLB Stats API's own hitting game log (hydrate stats(
group=[hitting], type=[gameLog])) rather than derived from Statcast events --
runs, RBIs and stolen bases have no equivalent anywhere in the Statcast-based
daily_components file, and totalBases comes back as a real field here
instead of being reconstructed from extra-base hits.

Only refetches batters who actually appeared in yesterday's games. A
lineup regular plays most days, but re-pulling all ~750 rostered hitters
every run would be ~30 batched requests to rewrite data that mostly has
not changed. Yesterday's batters are however many games' worth of lineups,
usually 2-4 batches.

Actual participants come from each boxscore's batters list (every player
who came to the plate or was announced in the lineup), not a fixed
"starters" notion the way pitching has one -- a lineup is nine hitters
deep, all of whom belong on this sheet.

First run (no existing parquet) does a full pull for every player_id in
mlb_rosters.parquet -- that roster is every rostered player, pitchers
included, but a pure pitcher's hydrated hitting game log just comes back
empty, which costs a wasted call, not a wrong result.

No arguments:

    python backend/app/get_batter_logs.py

Reads:  backend/data/mlb/mlb_rosters.parquet   (bootstrap only)
        backend/data/mlb/batter_logs.parquet   (previous run)
Writes: backend/data/mlb/batter_logs.parquet
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


def batters_in(game_pk: int) -> list[int]:
    """Every player who batted (or was in the lineup) for each side.

    Unlike pitching, there is no single "starter" -- a full lineup is nine
    hitters, and the bench/pinch-hitters who entered belong here too.
    """
    try:
        box = requests.get(f"{API}/game/{game_pk}/boxscore", timeout=TIMEOUT).json()
    except Exception as e:
        print(f"  boxscore {game_pk} failed: {e}")
        return []

    out: list[int] = []
    for side in ("home", "away"):
        out.extend(int(pid) for pid in box.get("teams", {}).get(side, {}).get("batters", []))
    return out


def yesterdays_batters(day: str) -> list[int]:
    pks = games_on(day)
    print(f"{len(pks)} game(s) on {day}")

    ids: set[int] = set()
    for pk in pks:
        ids.update(batters_in(pk))
    return sorted(ids)


def fetch_logs(person_ids: list[int]) -> list[dict]:
    """Game logs for a batch of hitters, flattened to one row per game played."""
    r = requests.get(
        f"{API}/people",
        params={
            "personIds": ",".join(str(i) for i in person_ids),
            "hydrate": f"stats(group=[hitting],type=[gameLog],season={SEASON})",
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()

    rows = []
    for person in r.json().get("people", []):
        player_id = person.get("id")
        player = person.get("fullName", "")

        for stat_group in person.get("stats", []):
            for split in stat_group.get("splits", []):
                s = split.get("stat", {})
                rows.append(
                    {
                        "player_id": player_id,
                        "player": player,
                        "game_pk": split.get("game", {}).get("gamePk"),
                        "date": split.get("date", ""),
                        "opponent": split.get("opponent", {}).get("name", ""),
                        "is_home": bool(split.get("isHome", False)),
                        "at_bats": int(s.get("atBats", 0) or 0),
                        "plate_appearances": int(s.get("plateAppearances", 0) or 0),
                        "runs": int(s.get("runs", 0) or 0),
                        "hits": int(s.get("hits", 0) or 0),
                        "doubles": int(s.get("doubles", 0) or 0),
                        "triples": int(s.get("triples", 0) or 0),
                        "home_runs": int(s.get("homeRuns", 0) or 0),
                        "rbi": int(s.get("rbi", 0) or 0),
                        "walks": int(s.get("baseOnBalls", 0) or 0),
                        "strikeouts": int(s.get("strikeOuts", 0) or 0),
                        "stolen_bases": int(s.get("stolenBases", 0) or 0),
                        "total_bases": int(s.get("totalBases", 0) or 0),
                    }
                )

    return rows


def fetch_many(player_ids: list[int]) -> pd.DataFrame:
    rows = []

    for i in range(0, len(player_ids), ID_CHUNK):
        chunk = player_ids[i : i + ID_CHUNK]
        try:
            batch = fetch_logs(chunk)
        except Exception as e:
            # One bad batch should not lose the run.
            print(f"  batch {i // ID_CHUNK + 1} failed ({e}); continuing")
            continue

        rows.extend(batch)
        print(f"  batch {i // ID_CHUNK + 1}: {len(batch)} game(s)")

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame[frame["date"].notna()]


def merge(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Replace each refetched batter's rows wholesale, keep everyone else.

    Replacing per player rather than per game means a corrected box score --
    a scoring change days later -- flows through, since the fetch returns
    that player's whole season.
    """
    if old.empty:
        combined = new
    else:
        refreshed = set(new["player_id"])
        combined = pd.concat([old[~old["player_id"].isin(refreshed)], new], ignore_index=True)

    return (
        combined.drop_duplicates(["player_id", "game_pk"], keep="last")
        .sort_values(["player_id", "date"], ascending=[True, False])
        .reset_index(drop=True)
    )


def main() -> None:
    dest = DATA_DIR / "batter_logs.parquet"
    yesterday = (datetime.now(BALLPARK_TZ).date() - timedelta(days=1)).isoformat()

    old = pd.read_parquet(dest) if dest.exists() else pd.DataFrame()

    if old.empty:
        # Bootstrap: no prior file, so pull everyone once. mlb_rosters.parquet
        # is every active rostered player (pitchers included) -- a pure
        # pitcher's hydrated hitting log just comes back empty.
        rosters_path = DATA_DIR / "mlb_rosters.parquet"
        if not rosters_path.exists():
            print("no mlb_rosters.parquet -- run get_mlb_rosters.py first")
            return
        targets = pd.read_parquet(rosters_path)["player_id"].dropna().astype(int).unique().tolist()
        print(f"no existing logs -- full pull for {len(targets)} player(s)")
    else:
        targets = yesterdays_batters(yesterday)
        print(f"{len(targets)} batter(s) played on {yesterday}")

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

    print(f"{len(combined)} games for {combined['player_id'].nunique()} batter(s)")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
