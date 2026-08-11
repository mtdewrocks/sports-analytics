"""Batters who are hot over the last seven days.

Replaces Last_Week_Stats.xlsx. Recency is the point, so this is a strict
trailing 7-day window rather than each batter's last 7 games -- a "last 7
games" view reaches back months for part-time players, which is a season
summary, not a hot streak.

The PA floor does the sample-size work instead. At 18+ PA a pinch hitter who
went 1-for-1 cannot appear, while a regular who sat two games still can.

Rates are computed from summed components, never averaged from daily rates.

No arguments:

    python backend/app/build_hot_hitters.py

Reads:  backend/data/mlb/daily_components_2026.parquet
        backend/data/mlb/starters.parquet          (optional, for names)
Writes: backend/data/mlb/hot_hitters.parquet
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

SEASON = 2026
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "mlb"
BALLPARK_TZ = ZoneInfo("America/Chicago")

WINDOW_DAYS = 7
MIN_PA = 18
MIN_BA = 0.350


def player_names() -> pd.DataFrame:
    """MLBAM id -> name, from the Chadwick register pybaseball ships.

    daily_components stores ids only. Falling back to an empty frame keeps
    this usable offline -- the table just shows ids instead of names.
    """
    try:
        from pybaseball import chadwick_register

        reg = chadwick_register()
        reg = reg[reg["key_mlbam"].notna()].copy()
        reg["player_id"] = pd.to_numeric(reg["key_mlbam"], errors="coerce")
        reg = reg[reg["player_id"].notna()]
        reg["player_id"] = reg["player_id"].astype("int64")
        reg["player"] = (
            reg["name_first"].fillna("").str.strip()
            + " "
            + reg["name_last"].fillna("").str.strip()
        ).str.strip()
        return reg[["player_id", "player"]].drop_duplicates("player_id", keep="last")
    except Exception as e:
        print(f"could not load player names ({e}); ids only")
        return pd.DataFrame(columns=["player_id", "player"])


def build(components: pd.DataFrame, day: str) -> pd.DataFrame:
    cutoff = pd.Timestamp(day) - pd.Timedelta(days=WINDOW_DAYS)

    window = components[
        (components["role"] == "batter") & (components["game_date"] >= cutoff)
    ]
    if window.empty:
        return pd.DataFrame()

    totals = window.groupby("player_id", as_index=False).agg(
        games=("game_date", "nunique"),
        pa=("pa", "sum"),
        ab=("ab", "sum"),
        h=("h", "sum"),
        singles=("singles", "sum"),
        doubles=("doubles", "sum"),
        triples=("triples", "sum"),
        hr=("hr", "sum"),
        bb=("bb", "sum"),
        hbp=("hbp", "sum"),
        so=("so", "sum"),
        sf=("sf", "sum"),
        woba_num=("woba_num", "sum"),
        woba_den=("woba_den", "sum"),
    )

    ab = totals["ab"]
    pa = totals["pa"]
    tb = totals["singles"] + 2 * totals["doubles"] + 3 * totals["triples"] + 4 * totals["hr"]

    totals["ba"] = totals["h"] / ab.where(ab > 0)
    totals["obp"] = (totals["h"] + totals["bb"] + totals["hbp"]) / pa.where(pa > 0)
    totals["slg"] = tb / ab.where(ab > 0)
    totals["ops"] = totals["obp"] + totals["slg"]
    totals["woba"] = totals["woba_num"] / totals["woba_den"].where(totals["woba_den"] > 0)
    totals["k_pct"] = 100 * totals["so"] / pa.where(pa > 0)
    totals["bb_pct"] = 100 * totals["bb"] / pa.where(pa > 0)

    hot = totals[(totals["pa"] >= MIN_PA) & (totals["ba"] >= MIN_BA)].copy()
    if hot.empty:
        return hot

    hot = hot.merge(player_names(), on="player_id", how="left")
    hot["player"] = hot["player"].fillna(hot["player_id"].astype(str))
    hot["date"] = day
    hot["window_days"] = WINDOW_DAYS

    columns = [
        "date", "player", "player_id", "window_days", "games",
        "pa", "ab", "h", "hr", "bb", "so",
        "ba", "obp", "slg", "ops", "woba", "k_pct", "bb_pct",
    ]
    hot = hot[columns].sort_values("ba", ascending=False).reset_index(drop=True)

    for col in ("ba", "obp", "slg", "ops", "woba"):
        hot[col] = hot[col].round(3)
    for col in ("k_pct", "bb_pct"):
        hot[col] = hot[col].round(1)

    return hot


def main() -> None:
    day = datetime.now(BALLPARK_TZ).date().isoformat()
    components_path = DATA_DIR / f"daily_components_{SEASON}.parquet"

    if not components_path.exists():
        print(f"no {components_path.name} -- run update_stats_refactored.py first")
        return

    components = pd.read_parquet(components_path)
    hot = build(components, day)

    if hot.empty:
        print(f"no batters met {MIN_PA}+ PA and .{int(MIN_BA*1000)} BA in the last {WINDOW_DAYS} days")
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "hot_hitters.parquet"
    hot.to_parquet(dest, index=False)

    print(f"{len(hot)} hot hitter(s) over the last {WINDOW_DAYS} days "
          f"({MIN_PA}+ PA, {MIN_BA:.3f}+ BA)")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
