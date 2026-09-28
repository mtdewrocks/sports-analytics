"""Team efficiency stats for the NFL Matchup page and Matchup Deep Dive.

From nflverse play-by-play (CC-BY 4.0; credited on the pages as "Data:
nflverse"), every team's offense AND the same stats for its defense (what it
allowed), over two windows:

  season  every regular-season game this season
  last4   the team's last 4 games (the page offers it once every team has
          played 5 -- before that it equals the season)

Stats (per side; the defense row is what opponents did against it):
  overall    epa_per_play, success_rate, explosive_rate, yards_per_play
  passing    dropback_epa, dropback_success, cpoe, sack_rate,
             explosive_pass_rate, net_yards_per_dropback
  rushing    rush_success, yards_per_carry, explosive_run_rate, stuff_rate
  drives     points_per_drive, score_rate, td_rate, three_and_out_rate,
             plays_per_drive, start_yardline (own N), turnover_rate
  situations third_down_rate, third_down_distance, early_down_success,
             red_zone_td_rate, red_zone_trips_per_game
  pace       proe (pass rate over expected, neutral), neutral_pass_rate,
             seconds_per_play (neutral), plays_per_game, penalty_yards_per_game

Definitions:
  play        a pass or run (qb_dropback or rush_attempt), no kneels/spikes
  success     nflverse's `success` (EPA > 0)
  explosive   pass play gaining 20+ yards, run gaining 10+
  stuff       run for 0 yards or fewer
  3-and-out   a drive that ends in a punt with no first down
  neutral     1st-3rd quarter, win probability 20-80%
  points      the offense's score change over the drive (TDs include the
              extra point / two-point try)

Ranks aren't stored; the API ranks within each (window, side, stat) using
the direction in app/data/nfl_efficiency.py.

    python backend/app/get_nfl_team_efficiency.py
    python backend/app/get_nfl_team_efficiency.py --season 2025

Output: backend/data/nfl/team_efficiency.parquet
"""

from __future__ import annotations

import argparse
import io
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests

NFLVERSE_PBP_URL = "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{season}.parquet"
OUT = Path(__file__).resolve().parent.parent / "data" / "nfl" / "team_efficiency.parquet"
TIMEOUT = 120
LAST_N = 4

COLS = ["season", "season_type", "week", "game_id", "posteam", "defteam", "play_type", "qb_dropback",
        "rush_attempt", "pass_attempt", "sack", "qb_kneel", "qb_spike", "epa", "success", "yards_gained",
        "cpoe", "down", "ydstogo", "yardline_100", "qtr", "wp", "pass_oe", "pass", "game_seconds_remaining",
        "drive", "fixed_drive", "fixed_drive_result", "drive_first_downs", "drive_play_count",
        "posteam_score", "posteam_score_post", "third_down_converted", "third_down_failed",
        "penalty", "penalty_team", "penalty_yards"]


def fetch_pbp(season: int) -> pd.DataFrame | None:
    r = requests.get(NFLVERSE_PBP_URL.format(season=season), timeout=TIMEOUT)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    df = pd.read_parquet(io.BytesIO(r.content))
    return df[[c for c in COLS if c in df.columns]]


def _mean(s: pd.Series) -> float | None:
    s = pd.to_numeric(s, errors="coerce").dropna()
    return float(s.mean()) if len(s) else None


def _rate(num: float, den: float) -> float | None:
    return float(num) / float(den) if den else None


def side_stats(pbp: pd.DataFrame, team_col: str, team: str, games: set) -> dict:
    """Every stat for one team on one side of the ball (`team_col` =
    "posteam" for its offense, "defteam" for its defense), over `games`.
    Pure, so it's tested directly."""
    d = pbp[(pbp[team_col] == team) & pbp["game_id"].isin(games)]
    plays = d[((d["qb_dropback"] == 1) | (d["rush_attempt"] == 1))
              & (d["qb_kneel"].fillna(0) == 0) & (d["qb_spike"].fillna(0) == 0)]
    drop = plays[plays["qb_dropback"] == 1]
    rush = plays[plays["rush_attempt"] == 1]
    ng = max(len(games), 1)
    out: dict = {}

    # overall
    out["epa_per_play"] = _mean(plays["epa"])
    out["success_rate"] = _mean(plays["success"])
    expl = ((plays["qb_dropback"] == 1) & (plays["yards_gained"] >= 20)) | \
           ((plays["rush_attempt"] == 1) & (plays["yards_gained"] >= 10))
    out["explosive_rate"] = _rate(expl.sum(), len(plays))
    out["yards_per_play"] = _mean(plays["yards_gained"])

    # passing
    out["dropback_epa"] = _mean(drop["epa"])
    out["dropback_success"] = _mean(drop["success"])
    out["cpoe"] = _mean(drop["cpoe"])
    out["sack_rate"] = _rate(drop["sack"].fillna(0).sum(), len(drop))
    out["explosive_pass_rate"] = _rate((drop["yards_gained"] >= 20).sum(), len(drop))
    out["net_yards_per_dropback"] = _mean(drop["yards_gained"])

    # rushing
    out["rush_success"] = _mean(rush["success"])
    out["yards_per_carry"] = _mean(rush["yards_gained"])
    out["explosive_run_rate"] = _rate((rush["yards_gained"] >= 10).sum(), len(rush))
    out["stuff_rate"] = _rate((rush["yards_gained"] <= 0).sum(), len(rush))

    # drives: one row per (game, drive) the offense had
    dv = d[d["fixed_drive"].notna()].sort_values(["game_id", "fixed_drive"])
    if len(dv):
        g = dv.groupby(["game_id", "fixed_drive"])
        drives = pd.DataFrame({
            "result": g["fixed_drive_result"].last(),
            "first_downs": g["drive_first_downs"].max(),
            "plays": g["drive_play_count"].max(),
            # first snap from scrimmage (down is set), not the kickoff
            "start": dv[dv["down"].notna()].groupby(["game_id", "fixed_drive"])["yardline_100"].first(),
            "pts": g["posteam_score_post"].max() - g["posteam_score"].first(),
            "reached_rz": g["yardline_100"].min() <= 20,
        })
        # Drives that are only the end-of-half clock running out aren't
        # possessions anyone judges an offense on.
        drives = drives[drives["result"] != "End of half"]
        n = len(drives)
        out["points_per_drive"] = _mean(drives["pts"].clip(lower=0))
        out["score_rate"] = _rate(drives["result"].isin(["Touchdown", "Field goal"]).sum(), n)
        out["td_rate"] = _rate((drives["result"] == "Touchdown").sum(), n)
        out["three_and_out_rate"] = _rate(((drives["result"] == "Punt") & (drives["first_downs"].fillna(0) == 0)).sum(), n)
        out["plays_per_drive"] = _mean(drives["plays"])
        out["start_yardline"] = (100 - _mean(drives["start"])) if _mean(drives["start"]) is not None else None
        out["turnover_rate"] = _rate(drives["result"].isin(["Turnover", "Opp touchdown"]).sum(), n)
        rz = drives[drives["reached_rz"]]
        out["red_zone_td_rate"] = _rate((rz["result"] == "Touchdown").sum(), len(rz))
        out["red_zone_trips_per_game"] = len(rz) / ng
    # situations
    third = plays[plays["down"] == 3]
    conv, fail = third["third_down_converted"].fillna(0).sum(), third["third_down_failed"].fillna(0).sum()
    out["third_down_rate"] = _rate(conv, conv + fail)
    out["third_down_distance"] = _mean(third["ydstogo"])
    out["early_down_success"] = _mean(plays[plays["down"].isin([1, 2])]["success"])

    # pace & tendencies (offense side is the meaningful one; defense rows
    # describe what opponents did against it)
    neutral = plays[(plays["qtr"] <= 3) & plays["wp"].between(0.2, 0.8)]
    out["proe"] = _mean(neutral["pass_oe"]) / 100 if _mean(neutral["pass_oe"]) is not None else None
    out["neutral_pass_rate"] = _mean(neutral["qb_dropback"])
    nd = neutral.sort_values(["game_id", "game_seconds_remaining"], ascending=[True, False])
    gaps = -nd.groupby(["game_id", "drive"])["game_seconds_remaining"].diff()
    gaps = gaps[(gaps > 0) & (gaps <= 60)]
    out["seconds_per_play"] = _mean(gaps)
    out["plays_per_game"] = len(plays) / ng
    pen = d[(d["penalty"] == 1) & (d["penalty_team"] == team)]
    out["penalty_yards_per_game"] = pen["penalty_yards"].fillna(0).sum() / ng
    return out


def build(pbp: pd.DataFrame) -> pd.DataFrame:
    """Long table: season, team, window, side, stat, value, games."""
    reg = pbp[pbp["season_type"] == "REG"] if "season_type" in pbp.columns else pbp
    season = int(reg["season"].max())
    reg = reg[reg["season"] == season]
    teams = sorted(t for t in reg["posteam"].dropna().unique() if t)
    rows = []
    for team in teams:
        # a team's games = games it appears in on either side
        gids = [g for g in reg[(reg["posteam"] == team) | (reg["defteam"] == team)]
                .drop_duplicates("game_id").sort_values("week")["game_id"]]
        for window, games in (("season", set(gids)), ("last4", set(gids[-LAST_N:]))):
            for side, col in (("off", "posteam"), ("def", "defteam")):
                for stat, val in side_stats(reg, col, team, games).items():
                    rows.append({"season": season, "team": team, "window": window, "side": side,
                                 "stat": stat, "value": None if val is None or pd.isna(val) else float(val),
                                 "games": len(games), "games_played": len(gids)})
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int)
    args = ap.parse_args()
    today = date.today()
    season = args.season or (today.year if today.month >= 9 else today.year - 1)
    pbp = fetch_pbp(season)
    if pbp is None or pbp.empty or not (pbp.get("season_type") == "REG").any():
        print(f"No {season} regular-season play-by-play yet; using {season - 1}")
        pbp = fetch_pbp(season - 1)
    if pbp is None or pbp.empty:
        print("No play-by-play available; nothing written")
        return
    out = build(pbp)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    print(f"{out['team'].nunique()} teams, {len(out)} rows -> {OUT}")


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
