"""Team pass/run tendency, split by score situation and by quarter.

"Game script" is a season-long tendency profile, not a single-week
snapshot -- does this team keep passing even with a big lead, or does it
lean run-heavy to protect one? Does it abandon the run plan the moment
it's trailing? This is season-to-date, same convention as team_stats.parquet.

Score-situation buckets use the standard "one-score game" cutoff of 8
points (a touchdown + 2-point conversion) as the threshold between a
close game and a blowout:
    trailing_big   score_differential <= -9
    trailing       -8 to -1
    tied           0
    leading        1 to 8
    leading_big    >= 9

Only actual play-calling snaps count (play_type in pass/run) -- kneels,
spikes, punts, kicks, and no-plays are excluded so they don't dilute the
pass/run mix.

    python backend/app/get_nfl_game_script.py

Output: backend/data/nfl/team_game_script.parquet
"""

from __future__ import annotations

import argparse
import io
from datetime import date
from pathlib import Path

import pandas as pd
import requests

NFLVERSE_PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "nfl"
TIMEOUT = 120
REGULAR_SEASON_MAX_WEEK = 18
NEUTRAL_MARGIN = 7  # within this many points either way counts as "close"

SITUATION_BUCKETS = [
    ("trailing_big", lambda d: d <= -9),
    ("trailing", lambda d: (d >= -8) & (d <= -1)),
    ("tied", lambda d: d == 0),
    ("leading", lambda d: (d >= 1) & (d <= 8)),
    ("leading_big", lambda d: d >= 9),
]
QUARTER_BUCKETS = [("q1", 1), ("q2", 2), ("q3", 3), ("q4", 4), ("ot", 5)]


def current_nfl_season() -> int:
    today = date.today()
    return today.year if today.month >= 9 else today.year - 1


def fetch_pbp(season: int) -> pd.DataFrame | None:
    url = NFLVERSE_PBP_URL.format(season=season)
    r = requests.get(url, timeout=TIMEOUT)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return pd.read_parquet(io.BytesIO(r.content))


def _pass_pct_and_plays(plays: pd.DataFrame) -> pd.DataFrame:
    """One row per team: play count and pass rate, for whatever subset of
    play-calling snaps is passed in."""
    g = plays.groupby("posteam")
    total = g["play_type"].transform("count")
    passes = g["pass_attempt"].transform("sum")
    out = plays.assign(_total=total, _passes=passes)[["posteam", "_total", "_passes"]].drop_duplicates("posteam")
    out = out.rename(columns={"posteam": "team"})
    out["plays"] = out["_total"].astype(int)
    out["pass_pct"] = (out["_passes"] / out["_total"] * 100).round(1)
    return out[["team", "plays", "pass_pct"]]


def build(season: int) -> pd.DataFrame:
    df = fetch_pbp(season)
    is_fallback = False

    if df is None:
        fallback_season = season - 1
        print(f"no play-by-play for {season} yet; falling back to {fallback_season} "
              f"regular season (weeks 1-{REGULAR_SEASON_MAX_WEEK})")
        df = fetch_pbp(fallback_season)
        if df is None:
            raise RuntimeError(f"No play-by-play available for {season} or {fallback_season}.")
        df = df[df["week"] <= REGULAR_SEASON_MAX_WEEK]
        is_fallback = True

    plays = df[df["play_type"].isin(["pass", "run"])].copy()
    print(f"{len(plays)} play-calling snaps loaded" + (" (fallback)" if is_fallback else ""))

    overall = _pass_pct_and_plays(plays).rename(columns={"plays": "plays_overall", "pass_pct": "pass_pct_overall"})
    result = overall

    # "Neutral" close-game baseline -- see NEUTRAL_MARGIN's comment above.
    # Kept separate from pass_pct_overall (plain season average) rather than
    # replacing it, so the biased season number is still available if ever
    # needed for something else, while this becomes the actual baseline the
    # projection blend uses.
    neutral_plays = plays[plays["score_differential"].abs() <= NEUTRAL_MARGIN]
    neutral = _pass_pct_and_plays(neutral_plays).rename(columns={"plays": "plays_neutral", "pass_pct": "pass_pct_neutral"})
    result = result.merge(neutral, on="team", how="left")

    for label, condition in SITUATION_BUCKETS:
        sub = plays[condition(plays["score_differential"])]
        stats = _pass_pct_and_plays(sub).rename(columns={"plays": f"plays_{label}", "pass_pct": f"pass_pct_{label}"})
        result = result.merge(stats, on="team", how="left")

    for label, qtr_num in QUARTER_BUCKETS:
        sub = plays[plays["qtr"] == qtr_num]
        stats = _pass_pct_and_plays(sub).rename(columns={"plays": f"plays_{label}", "pass_pct": f"pass_pct_{label}"})
        result = result.merge(stats, on="team", how="left")

    result["season"] = season if not is_fallback else season - 1
    result["is_fallback"] = is_fallback
    return result.sort_values("team")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=current_nfl_season())
    args = parser.parse_args()

    frame = build(args.season)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "team_game_script.parquet"
    frame.to_parquet(dest, index=False)

    print(f"{len(frame)} teams")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
