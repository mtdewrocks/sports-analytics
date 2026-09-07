"""Team-level hitting wOBA vs LHP / RHP -- season pooled AND last 30 days.

Mirrors build_splits.py's exact approach (same source file, same
sum-the-components-then-divide method, same two-season pooling for the
season window) but aggregates by team instead of by individual pitcher,
using role == "batter" instead of "pitcher".

wOBA specifically because it's the one metric this can build reliably for
free: real wRC+ needs park/league adjustment data this app doesn't have a
confirmed free source for (checked directly against statsapi.mlb.com's
documented stat types, which don't include a sabermetrics group), while
wOBA is directly summable from the same components file already used
elsewhere in this pipeline.

Team assignment comes from mlb_rosters.parquet (current roster), not the
components file itself (which has no team column) -- a small inaccuracy
for a batter traded mid-season whose earlier-season plate appearances get
attributed to their CURRENT team, but the same tradeoff already accepted
elsewhere in this app for the same reason (a lineup-independent team
lookup that's simple and current beats a fully historically-accurate one
that needs a second data source).

No arguments:

    python backend/app/build_team_hitting_splits.py

Reads:  backend/data/mlb/daily_components_2025.parquet
        backend/data/mlb/daily_components_2026.parquet
        backend/data/mlb/mlb_rosters.parquet
Writes: backend/data/mlb/team_hitting_splits.parquet
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "mlb"

# Same pooling convention as build_splits.py -- equal weights means the
# pooled totals are the true plate-appearance counts, nothing distorted.
SEASON_WEIGHTS = {2025: 1.0, 2026: 1.0}
LAST_N_DAYS = 30

# A team needs some real plate appearances against a given hand before a
# split means anything -- rows below this are dropped rather than shown
# with a noisy rate built from a handful of PAs.
MIN_PA = 30


def load_batter_components(seasons: dict) -> pd.DataFrame:
    frames = []
    for season, weight in seasons.items():
        path = DATA_DIR / f"daily_components_{season}.parquet"
        if not path.exists():
            print(f"{season}: no {path.name}, skipping")
            continue
        frame = pd.read_parquet(path)
        frame = frame[frame["role"] == "batter"].copy()
        frame["_weight"] = weight
        frames.append(frame)
        print(f"{season}: {len(frame):,} batter rows (weight {weight})")

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def team_lookup() -> dict:
    path = DATA_DIR / "mlb_rosters.parquet"
    if not path.exists():
        print(f"no {path.name} -- cannot map players to teams")
        return {}
    rosters = pd.read_parquet(path)
    return dict(zip(rosters["player_id"], rosters["team"]))


def pool_to_team(frame: pd.DataFrame, team_by_player: dict, window: str) -> pd.DataFrame:
    """Sum weighted PA/wOBA components to one row per (team, opposing hand)."""
    frame = frame.copy()
    frame["team"] = frame["player_id"].map(team_by_player)
    frame = frame[frame["team"].notna()]
    if frame.empty:
        return frame

    frame["weighted_pa"] = frame["pa"] * frame["_weight"]
    frame["weighted_woba_num"] = frame["woba_num"] * frame["_weight"]
    frame["weighted_woba_den"] = frame["woba_den"] * frame["_weight"]

    grouped = frame.groupby(["team", "opp_hand"], as_index=False).agg(
        pa=("weighted_pa", "sum"),
        woba_num=("weighted_woba_num", "sum"),
        woba_den=("weighted_woba_den", "sum"),
    )
    grouped["woba"] = (grouped["woba_num"] / grouped["woba_den"].where(grouped["woba_den"] > 0)).round(3)
    grouped["window"] = window
    grouped["split"] = "vs " + grouped["opp_hand"]
    return grouped[grouped["pa"] >= MIN_PA][["team", "split", "window", "pa", "woba"]]


def main() -> None:
    team_by_player = team_lookup()
    if not team_by_player:
        print("no roster data -- nothing to build")
        return

    # ---- Season-pooled window (2025 + 2026, same as build_splits.py) -----
    season_frame = load_batter_components(SEASON_WEIGHTS)
    season_splits = pool_to_team(season_frame, team_by_player, "season") if not season_frame.empty else pd.DataFrame()

    # ---- Last-30-days window (current season only) ------------------------
    current_season = date.today().year
    cutoff = date.today() - timedelta(days=LAST_N_DAYS)
    recent_frame = load_batter_components({current_season: 1.0})
    if not recent_frame.empty:
        recent_frame["game_date"] = pd.to_datetime(recent_frame["game_date"], errors="coerce")
        recent_frame = recent_frame[recent_frame["game_date"] >= pd.Timestamp(cutoff)]
    recent_splits = pool_to_team(recent_frame, team_by_player, "last_30_days") if not recent_frame.empty else pd.DataFrame()

    combined = pd.concat([season_splits, recent_splits], ignore_index=True)
    if combined.empty:
        print("nothing to save")
        return

    combined["pa"] = combined["pa"].round().astype("int64")
    combined = combined.sort_values(["team", "window", "split"]).reset_index(drop=True)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "team_hitting_splits.parquet"
    combined.to_parquet(dest, index=False)

    print(f"{len(combined)} team-split rows ({combined['team'].nunique()} teams, {MIN_PA}+ PA)")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
