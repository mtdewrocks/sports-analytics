"""Player carry/target share, split by score situation.

Companion to get_nfl_game_script.py's team-level pass/run splits. The
eventual goal (not built yet -- this is the data layer only) is something
like: team X projects to a 65% rush share as a big favorite; running back Y
gets 60% of the team's carries; Y averages 4.0 YPC on the season; therefore
Y projects to ~28 carries and ~112 yards if that script plays out. This
script produces the piece that makes "60% of the team's carries" a real,
computed number instead of a guess -- and splits it by situation too, since
a bell-cow back's share of carries specifically in clock-killing situations
can differ meaningfully from his flat season share.

Same score-situation buckets as get_nfl_game_script.py (the standard
one-score-game 8-point cutoff):
    trailing_big   score_differential <= -9
    trailing       -8 to -1
    tied           0
    leading        1 to 8
    leading_big    >= 9

Efficiency (yards per carry, yards per target) is intentionally NOT split
by situation here -- just carries/targets and each player's share of his
team's total in that situation. Keeping efficiency at a simple season-long
number matches how the worked example above uses it, and splitting
efficiency by situation too would need a much larger sample size per
bucket to be reliable than a share split does.

    python backend/app/get_nfl_player_situational_usage.py

Output: backend/data/nfl/player_situational_usage.parquet
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

SITUATIONS = ["trailing_big", "trailing", "tied", "leading", "leading_big"]


def _bucket(d: float) -> str:
    if d <= -9:
        return "trailing_big"
    if d <= -1:
        return "trailing"
    if d == 0:
        return "tied"
    if d <= 8:
        return "leading"
    return "leading_big"


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


def _player_usage(
    plays: pd.DataFrame,
    attempt_col: str,
    player_id_col: str,
    player_name_col: str,
    volume_label: str,
) -> pd.DataFrame:
    """One row per (team, player): overall volume + share of team volume,
    plus the same two numbers within each situation bucket."""
    snaps = plays[plays[attempt_col] == 1].copy()
    snaps = snaps[snaps[player_id_col].notna()]

    team_totals = snaps.groupby("posteam").size().rename("_team_total")
    team_totals_by_situation = snaps.groupby(["posteam", "situation"]).size().unstack(fill_value=0)

    player_totals = (
        snaps.groupby(["posteam", player_id_col, player_name_col])
        .size()
        .reset_index(name=volume_label)
    )
    player_by_situation = (
        snaps.groupby(["posteam", player_id_col, player_name_col, "situation"])
        .size()
        .unstack(fill_value=0)
    )
    for s in SITUATIONS:
        if s not in player_by_situation.columns:
            player_by_situation[s] = 0
    player_by_situation = player_by_situation[SITUATIONS].reset_index()

    out = player_totals.merge(player_by_situation, on=["posteam", player_id_col, player_name_col])
    out = out.rename(columns={player_id_col: "player_id", player_name_col: "player", "posteam": "team"})

    out[f"{volume_label}_share"] = out.apply(
        lambda r: r[volume_label] / team_totals.get(r["team"], float("nan")), axis=1
    )
    for s in SITUATIONS:
        out[f"{s}_{volume_label}_share"] = out.apply(
            lambda r: (r[s] / team_totals_by_situation.loc[r["team"], s])
            if r["team"] in team_totals_by_situation.index and team_totals_by_situation.loc[r["team"], s] > 0
            else float("nan"),
            axis=1,
        )
        out = out.rename(columns={s: f"{s}_{volume_label}"})

    return out


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
    plays["situation"] = plays["score_differential"].apply(_bucket)
    print(f"{len(plays)} play-calling snaps loaded" + (" (fallback)" if is_fallback else ""))

    rushers = _player_usage(plays, "rush_attempt", "rusher_player_id", "rusher_player_name", "carries")
    receivers = _player_usage(plays, "pass_attempt", "receiver_player_id", "receiver_player_name", "targets")

    result = rushers.merge(receivers, on=["team", "player_id", "player"], how="outer")
    result["season"] = season if not is_fallback else season - 1
    result["is_fallback"] = is_fallback
    return result.sort_values(["team", "carries"], ascending=[True, False])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, default=current_nfl_season())
    args = parser.parse_args()

    frame = build(args.season)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "player_situational_usage.parquet"
    frame.to_parquet(dest, index=False)

    print(f"{len(frame)} player rows across {frame['team'].nunique()} teams")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
