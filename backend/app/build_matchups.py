"""Merge today's lineups with season-to-date Statcast splits into one table.

One row per batter in a posted lineup, with that batter's numbers against the
starter's throwing hand sitting next to the starter's numbers against that
batter's stance -- the shape Combined_Daily_Data.xlsx uses.

The join works because daily_components keys on (player_id, role, opp_hand)
where opp_hand is always the *opponent's* handedness:

    hitter  side ->  player_id = batter_id       opp_hand = opp_throws
    pitcher side ->  player_id = opp_starter_id  opp_hand = stand

Both split (vs that hand) and overall (vs everyone) columns are included, so
the dashboard can show either without a second file.

No arguments -- it reads the current day's lineups, so it can run unattended
in GitHub Actions:

    python backend/app/build_matchups.py

Reads:  backend/data/mlb/lineups_{date}.csv
        backend/data/mlb/daily_components_2026.parquet
Writes: backend/data/mlb/daily_matchups.parquet

The output filename is fixed, not date-stamped, so the dashboard can point at
one path forever. Each run overwrites it with the current slate; the `date`
column carries which day the rows belong to.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

SEASON = 2026
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "mlb"
BALLPARK_TZ = ZoneInfo("America/Chicago")


def season_totals(components: pd.DataFrame, role: str, by_hand: bool) -> pd.DataFrame:
    """Sum the daily components to season-to-date, with rates derived after.

    Rates have to be computed from summed numerators and denominators, never
    averaged from daily rates -- a 1-PA day would otherwise carry the same
    weight as a 5-PA day.
    """
    keys = ["player_id", "opp_hand"] if by_hand else ["player_id"]
    counts = (
        components[components["role"] == role]
        .groupby(keys, as_index=False)
        .sum(numeric_only=True)
        .drop(columns=["season"], errors="ignore")
    )

    pa, ab = counts["pa"], counts["ab"]
    tb = counts["singles"] + 2 * counts["doubles"] + 3 * counts["triples"] + 4 * counts["hr"]

    out = counts[keys].copy()
    out["pa"] = pa
    out["ab"] = ab
    out["h"] = counts["h"]
    out["hr"] = counts["hr"]
    out["avg"] = counts["h"] / ab.where(ab > 0)
    out["obp"] = (counts["h"] + counts["bb"] + counts["hbp"]) / pa.where(pa > 0)
    out["slg"] = tb / ab.where(ab > 0)
    out["ops"] = out["obp"] + out["slg"]
    out["iso"] = out["slg"] - out["avg"]
    out["woba"] = counts["woba_num"] / counts["woba_den"].where(counts["woba_den"] > 0)
    out["xwoba_con"] = counts["xwoba_con_sum"] / counts["xwoba_con_n"].where(
        counts["xwoba_con_n"] > 0
    )
    out["k_pct"] = 100 * counts["so"] / pa.where(pa > 0)
    out["bb_pct"] = 100 * counts["bb"] / pa.where(pa > 0)
    out["hr_pct"] = 100 * counts["hr"] / pa.where(pa > 0)
    out["pitches_per_pa"] = counts["pitches"] / pa.where(pa > 0)

    # No sample-size filtering -- every player who appeared gets their real
    # numbers. `pa` and `ab` travel alongside every rate so the dashboard can
    # judge reliability itself.
    return out


def last_week(components: pd.DataFrame, day: str, days: int = 7) -> pd.DataFrame:
    """Recent-form batting average, all pitchers, over a trailing window.

    Keyed on the slate date rather than the parquet's last game so the window
    stays honest on an off-day -- otherwise a Monday with no games would
    silently report the seven days before Sunday.
    """
    cutoff = pd.Timestamp(day) - pd.Timedelta(days=days)
    recent = components[
        (components["role"] == "batter") & (components["game_date"] >= cutoff)
    ]

    out = recent.groupby("player_id", as_index=False).agg(
        last_week_ab=("ab", "sum"), last_week_h=("h", "sum")
    )
    out["last_week_ba"] = out["last_week_h"] / out["last_week_ab"].where(
        out["last_week_ab"] > 0
    )
    return out[["player_id", "last_week_ab", "last_week_ba"]]


def attach(lineups: pd.DataFrame, totals: pd.DataFrame, left_id: str,
           left_hand: str | None, prefix: str) -> pd.DataFrame:
    """Left-join one side's season totals onto the lineup rows."""
    right = totals.rename(columns={"player_id": left_id})
    left_on = [left_id]

    if left_hand is not None:
        right = right.rename(columns={"opp_hand": left_hand})
        left_on.append(left_hand)

    right = right.rename(
        columns={c: prefix + c for c in right.columns if c not in left_on}
    )
    return lineups.merge(right, on=left_on, how="left")


def add_flags(frame: pd.DataFrame) -> pd.DataFrame:
    """Binary tags, thresholded against today's slate rather than fixed cutoffs.

    Using the slate's own distribution means the flags stay meaningful as
    league offense drifts over the season.
    """
    out = frame.copy()

    def hi(col: str, q: float) -> pd.Series:
        values = out[col]
        if values.notna().sum() < 10:
            return pd.Series(0, index=out.index, dtype="int64")
        return (values >= values.quantile(q)).fillna(False).astype("int64")

    def lo(col: str, q: float) -> pd.Series:
        values = out[col]
        if values.notna().sum() < 10:
            return pd.Series(0, index=out.index, dtype="int64")
        return (values <= values.quantile(q)).fillna(False).astype("int64")

    out["high_k_hitter"] = hi("split_k_pct", 0.75)
    out["high_bb_hitter"] = hi("split_bb_pct", 0.75)
    out["high_avg_hitter"] = hi("split_avg", 0.75)
    out["low_avg_hitter"] = lo("split_avg", 0.25)
    out["high_iso_hitter"] = hi("split_iso", 0.75)
    out["high_woba_hitter"] = hi("split_woba", 0.75)
    return out


COLUMN_ORDER = [
    # identity
    "date", "game_pk", "game_time_utc", "team", "opponent", "home_away",
    "batting_order", "player", "batter_id", "bats", "hits_from",
    # hitter vs the starter's hand
    "split_hitter", "split_pa", "split_ab", "split_h", "split_hr",
    "split_avg", "split_obp", "split_slg", "split_ops", "split_iso",
    "split_woba", "split_xwoba_con", "split_k_pct", "split_bb_pct",
    "split_hr_pct", "split_pitches_per_pa",
    # recent form, all pitchers
    "last_week_ab", "last_week_ba",
    # hitter overall
    "all_pa", "all_avg", "all_obp", "all_slg", "all_ops", "all_iso",
    "all_woba", "all_k_pct", "all_bb_pct", "all_hr_pct",
    # opposing starter vs this batter's stance
    "pitcher", "pitcher_id", "throws", "split_pitcher",
    "p_split_pa", "p_split_h", "p_split_hr", "p_split_avg", "p_split_obp",
    "p_split_slg", "p_split_ops", "p_split_iso", "p_split_woba",
    "p_split_xwoba_con", "p_split_k_pct", "p_split_bb_pct", "p_split_hr_pct",
    "p_split_pitches_per_pa",
    # opposing starter overall
    "p_all_pa", "p_all_avg", "p_all_woba", "p_all_k_pct", "p_all_bb_pct",
    "p_all_hr_pct",
    # tags
    "high_k_hitter", "high_bb_hitter", "high_avg_hitter", "low_avg_hitter",
    "high_iso_hitter", "high_woba_hitter",
]


def main() -> None:
    day = datetime.now(BALLPARK_TZ).date().isoformat()

    lineups_path = DATA_DIR / f"lineups_{day}.csv"
    components_path = DATA_DIR / f"daily_components_{SEASON}.parquet"

    if not lineups_path.exists():
        print(f"no lineups file for {day} -- run get_lineups.py first")
        return

    lineups = pd.read_csv(lineups_path)
    if lineups.empty:
        print(f"lineups file for {day} is empty")
        return

    components = pd.read_parquet(components_path)

    bat_split = season_totals(components, "batter", by_hand=True)
    bat_all = season_totals(components, "batter", by_hand=False)
    pit_split = season_totals(components, "pitcher", by_hand=True)
    pit_all = season_totals(components, "pitcher", by_hand=False)

    # Hitter side: the batter vs the hand the starter throws.
    frame = attach(lineups, bat_split, "batter_id", "opp_throws", "split_")
    frame = attach(frame, bat_all, "batter_id", None, "all_")

    # Pitcher side: the starter vs the side this batter hits from. `stand` is
    # already resolved for switch hitters, so it is a real L/R key.
    frame = attach(frame, pit_split, "opp_starter_id", "stand", "p_split_")
    frame = attach(frame, pit_all, "opp_starter_id", None, "p_all_")

    # Recent form is not split by hand -- it answers "is he hot right now".
    frame = frame.merge(
        last_week(components, day).rename(columns={"player_id": "batter_id"}),
        on="batter_id",
        how="left",
    )

    frame = frame.rename(
        columns={
            "slot": "batting_order",
            "batter_name": "player",
            "stand": "hits_from",
            "opp_throws": "throws",
            "opp_starter_name": "pitcher",
            "opp_starter_id": "pitcher_id",
        }
    )

    # `bats` is how the player is listed (S survives for switch hitters);
    # `hits_from` is the side they bat from today, and is what every split
    # column above was actually matched on.
    frame["split_hitter"] = "vs " + frame["throws"]
    frame["split_pitcher"] = "vs " + frame["hits_from"]

    frame = add_flags(frame)
    frame = frame[[c for c in COLUMN_ORDER if c in frame.columns]]
    frame = frame.sort_values(["game_pk", "team", "batting_order"]).reset_index(drop=True)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "daily_matchups.parquet"
    frame.to_parquet(dest, index=False)

    unmatched = frame["split_pa"].isna().sum()
    print(f"{len(frame)} batters across {frame['game_pk'].nunique()} game(s)")
    if unmatched:
        print(f"{unmatched} with no prior PA vs that hand this season (blank stats)")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
