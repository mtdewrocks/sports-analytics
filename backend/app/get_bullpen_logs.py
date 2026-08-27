"""Game-by-game pitching logs for every pitcher who appeared, not just starters.

Companion to get_pitcher_logs.py, which only re-fetches the pitcher who
started each game (element 0 of the boxscore's pitcher list). That is
correct for the starter-matchup page, but it means true relief appearances
are never captured anywhere -- this script exists to close that gap for the
bullpen usage/freshness page.

One row per appearance, with the columns the Bullpen page renders:

    date, team, opponent, is_starter, innings, hits, runs, earned_runs,
    walks, strikeouts, pitches

Only refetches pitchers who actually appeared yesterday (starters and
relievers both), same incremental approach as get_pitcher_logs.py.

First run (no existing parquet) does a full-season pull for every pitcher in
starters.parquet as a bootstrap, then relies on the daily incremental run to
backfill true relievers going forward -- there is no existing file to
bootstrap full bullpen history from, since it was never captured before.

No arguments:

    python backend/app/get_bullpen_logs.py

Reads:  backend/data/mlb/starters.parquet       (bootstrap only)
        backend/data/mlb/bullpen_logs.parquet   (previous run)
Writes: backend/data/mlb/bullpen_logs.parquet
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
ID_CHUNK = 25
TIMEOUT = 60
ROLLING_WINDOW_DAYS = 14  # trimmed on write -- the bullpen page only needs ~7-10 days


def games_on(day: str) -> list[int]:
    r = requests.get(
        f"{API}/schedule",
        params={"sportId": 1, "date": day},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return [g["gamePk"] for d in r.json().get("dates", []) for g in d["games"]]


def pitchers_in(game_pk: int) -> dict[int, dict]:
    """Every pitcher who appeared, keyed by id, with their team and starter flag.

    `pitchers` lists ids in order of appearance -- element 0 is the starter,
    everyone after is a relief appearance that day.
    """
    try:
        box = requests.get(f"{API}/game/{game_pk}/boxscore", timeout=TIMEOUT).json()
    except Exception as e:
        print(f"  boxscore {game_pk} failed: {e}")
        return {}

    out: dict[int, dict] = {}
    for side in ("home", "away"):
        team_block = box.get("teams", {}).get(side, {})
        team_name = team_block.get("team", {}).get("name", "")
        pitchers = team_block.get("pitchers", [])
        for i, pid in enumerate(pitchers):
            out[int(pid)] = {"team": team_name, "is_starter": i == 0}
    return out


def yesterdays_pitchers(day: str) -> dict[int, dict]:
    pks = games_on(day)
    print(f"{len(pks)} game(s) on {day}")

    ids: dict[int, dict] = {}
    for pk in pks:
        ids.update(pitchers_in(pk))
    return ids


def fetch_logs(person_ids: list[int], meta: dict[int, dict]) -> list[dict]:
    """Game logs for a batch of pitchers, flattened to one row per appearance.

    `meta` supplies team/is_starter for the appearance(s) just played; older
    rows for the same pitcher in this batch won't have a team tagged unless
    they also fall on the target date, which is fine -- the bullpen page only
    reads the trailing window this script keeps.
    """
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
        info = meta.get(pitcher_id, {})

        for stat_group in person.get("stats", []):
            for split in stat_group.get("splits", []):
                s = split.get("stat", {})
                game_date = split.get("date", "")
                rows.append(
                    {
                        "pitcher_id": pitcher_id,
                        "pitcher": pitcher,
                        "game_pk": split.get("game", {}).get("gamePk"),
                        "date": game_date,
                        "team": info.get("team", ""),
                        "opponent": split.get("opponent", {}).get("name", ""),
                        "is_starter": bool(int(s.get("gamesStarted", 0) or 0)),
                        "innings": s.get("inningsPitched", ""),
                        "hits": int(s.get("hits", 0) or 0),
                        "runs": int(s.get("runs", 0) or 0),
                        "earned_runs": int(s.get("earnedRuns", 0) or 0),
                        "home_runs": int(s.get("homeRuns", 0) or 0),
                        "walks": int(s.get("baseOnBalls", 0) or 0),
                        "strikeouts": int(s.get("strikeOuts", 0) or 0),
                        "batters_faced": int(s.get("battersFaced", 0) or 0),
                        "pitches": int(s.get("numberOfPitches", 0) or 0),
                    }
                )

    return rows


def fetch_many(pitcher_ids: list[int], meta: dict[int, dict]) -> pd.DataFrame:
    rows = []
    for i in range(0, len(pitcher_ids), ID_CHUNK):
        chunk = pitcher_ids[i : i + ID_CHUNK]
        try:
            batch = fetch_logs(chunk, meta)
        except Exception as e:
            print(f"  batch {i // ID_CHUNK + 1} failed ({e}); continuing")
            continue
        rows.extend(batch)
        print(f"  batch {i // ID_CHUNK + 1}: {len(batch)} appearance(s)")

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame

    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    return frame[frame["date"].notna()]


def merge(old: pd.DataFrame, new: pd.DataFrame, today: datetime) -> pd.DataFrame:
    """Add new appearances, keep a rolling window, drop exact duplicates."""
    if old.empty:
        combined = new
    else:
        combined = pd.concat([old, new], ignore_index=True)

    combined = combined.drop_duplicates(["pitcher_id", "game_pk"], keep="last")

    # Fill team forward within pitcher for rows that predate this script
    # (e.g. the bootstrap pull, which has no per-appearance team tagged).
    combined = combined.sort_values(["pitcher_id", "date"])
    combined["team"] = combined.groupby("pitcher_id")["team"].transform(
        lambda s: s.replace("", pd.NA).ffill().bfill()
    ).fillna("")

    cutoff = today - timedelta(days=ROLLING_WINDOW_DAYS)
    combined = combined[combined["date"] >= cutoff]

    return combined.sort_values(["team", "pitcher", "date"], ascending=[True, True, False]).reset_index(drop=True)


def main() -> None:
    dest = DATA_DIR / "bullpen_logs.parquet"
    now = datetime.now(BALLPARK_TZ)
    yesterday = (now.date() - timedelta(days=1)).isoformat()

    old = pd.read_parquet(dest) if dest.exists() else pd.DataFrame()

    if old.empty:
        starters_path = DATA_DIR / "starters.parquet"
        if not starters_path.exists():
            print("no starters.parquet -- run get_starters.py first")
            return
        starters_df = pd.read_parquet(starters_path)
        targets = starters_df["pitcher_id"].dropna().astype(int).tolist()
        # starters.parquet already has team per pitcher -- use it here so the
        # bootstrap pull isn't stuck with blank teams until a reliever happens
        # to pitch again (blank teams meant the bullpen page's team dropdown
        # was empty even though the appearance data itself pulled fine).
        meta: dict[int, dict] = {
            int(row.pitcher_id): {"team": row.team, "is_starter": True}
            for row in starters_df.itertuples()
            if pd.notna(row.pitcher_id)
        }
        print(f"no existing bullpen logs -- bootstrap pull for {len(targets)} pitcher(s) "
              f"(starters only; true relievers backfill from tomorrow)")
    else:
        meta = yesterdays_pitchers(yesterday)
        targets = list(meta.keys())
        print(f"{len(targets)} pitcher(s) appeared on {yesterday}")

    if not targets:
        print("nothing to update")
        return

    new = fetch_many(targets, meta)
    if new.empty:
        print("no game logs returned; leaving the existing file untouched")
        return

    combined = merge(old, new, pd.Timestamp(now.date()))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(dest, index=False)

    print(f"{len(combined)} appearances for {combined['pitcher_id'].nunique()} pitcher(s) "
          f"over trailing {ROLLING_WINDOW_DAYS} days")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
