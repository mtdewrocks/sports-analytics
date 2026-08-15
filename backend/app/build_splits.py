"""Pitcher splits vs LHB / RHB, pooled across seasons.

Replaces Season_Aggregated_Pitcher_Statistics.xlsx.

Two seasons are combined by summing their components, which is a
plate-appearance weighted average -- a season with 200 batters faced counts
twice as much as one with 100. That is the right default: it needs no
arbitrary constant and it degrades gracefully for a pitcher who only appears
in one of the two years.

SEASON_WEIGHTS lets you tilt it toward recency if you decide the current year
should count for more. At the default 1.0/1.0 the pooled totals are the true
counts, so nothing is distorted.

No arguments:

    python backend/app/build_splits.py

Reads:  backend/data/mlb/daily_components_2025.parquet
        backend/data/mlb/daily_components_2026.parquet
Writes: backend/data/mlb/pitcher_splits.parquet
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "mlb"

#: Seasons to pool, and how much each counts. Equal weights = pure PA
#: weighting. Set 2025 to 0.5 to make the current season count double.
SEASON_WEIGHTS = {
    2025: 1.0,
    2026: 1.0,
}

#: FIP is scaled so league FIP equals league ERA. Earned runs are not in the
#: components, so the constant cannot be derived here -- it lands near 3.10-3.20
#: most years. Worth checking against FanGraphs' Guts page each spring.
FIP_CONSTANT = 3.15

#: A pitcher needs some batters faced before a split means anything. Rows below
#: this are dropped entirely rather than shown with noisy rates.
MIN_TBF = 20

BATTED_BALL_COLUMNS = ("bip", "gb", "ld", "fb", "pu", "hard_hit", "med_hit", "soft_hit", "ev_n")


def load_seasons() -> pd.DataFrame:
    """Pitcher rows from every available season, with the weight applied."""
    frames = []

    for season, weight in SEASON_WEIGHTS.items():
        path = DATA_DIR / f"daily_components_{season}.parquet"
        if not path.exists():
            print(f"{season}: no {path.name}, skipping")
            continue

        frame = pd.read_parquet(path)
        frame = frame[frame["role"] == "pitcher"].copy()
        frame["_weight"] = weight
        frames.append(frame)
        print(f"{season}: {len(frame):,} pitcher rows (weight {weight})")

    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)

    # Older parquets predate the batted-ball components. Fill them with zero so
    # the aggregation still runs -- the affected rates come out NaN, which is
    # honest, rather than silently wrong.
    missing = [c for c in BATTED_BALL_COLUMNS + ("ev_sum",) if c not in combined.columns]
    if missing:
        print(f"note: {missing} absent -- batted-ball rates will be blank. Re-pull to populate.")
        for column in missing:
            combined[column] = 0

    return combined


def pool(frame: pd.DataFrame) -> pd.DataFrame:
    """Sum weighted components to one row per (pitcher, opposing hand)."""
    counting = [
        "pa", "ab", "h", "singles", "doubles", "triples", "hr", "bb", "ibb",
        "hbp", "so", "sf", "sh", "pitches", "woba_num", "woba_den",
        "outs_batter_events", "baserunning_outs", "ev_sum", *BATTED_BALL_COLUMNS,
    ]
    counting = [c for c in counting if c in frame.columns]

    weighted = frame[counting].multiply(frame["_weight"], axis=0)
    weighted[["player_id", "opp_hand"]] = frame[["player_id", "opp_hand"]]

    return weighted.groupby(["player_id", "opp_hand"], as_index=False).sum()


def derive(totals: pd.DataFrame, league_hr_per_fb: float) -> pd.DataFrame:
    """Rates from pooled components. Never averaged from per-season rates."""
    def div(numerator, denominator):
        return numerator / denominator.where(denominator > 0)

    out = totals.copy()

    ab, pa, bip, ev_n = out["ab"], out["pa"], out["bip"], out["ev_n"]
    tb = out["singles"] + 2 * out["doubles"] + 3 * out["triples"] + 4 * out["hr"]
    ubb = out["bb"] - out["ibb"]

    # Innings pitched needs outs made on the bases too -- a caught stealing
    # ends an inning but carries no plate appearance. Older component files
    # predate that column, so fall back to batter outs alone.
    runner_outs = out["baserunning_outs"] if "baserunning_outs" in out.columns else 0
    total_outs = out["outs_batter_events"] + pd.Series(runner_outs, index=out.index).fillna(0)
    ip = total_outs / 3.0

    out["tbf"] = pa.round().astype("int64")
    out["hr_allowed"] = out["hr"].round().astype("int64")

    # IP displays in baseball notation, where the digit after the point is
    # thirds of an inning, not tenths: 643 outs is 214.1, meaning 214 innings
    # and one out. `ip` above stays decimal because FIP and the rates need
    # real division -- only the displayed value is converted.
    outs = total_outs.round().astype("int64")
    out["ip"] = (outs // 3) + (outs % 3) / 10

    out["avg"] = div(out["h"], ab)
    out["babip"] = div(out["h"] - out["hr"], ab - out["so"] - out["hr"] + out["sf"])
    out["woba"] = div(out["woba_num"], out["woba_den"])
    out["slg"] = div(tb, ab)
    out["iso"] = out["slg"] - out["avg"]
    out["hr_rate"] = 100 * div(out["hr"], pa)
    out["k_pct"] = 100 * div(out["so"], pa)
    out["bb_pct"] = 100 * div(out["bb"], pa)

    # FanGraphs counts infield flies inside FB%, while Statcast splits `popup`
    # out as its own bb_type. Using the narrow definition put league HR/FB at
    # 16.8% against their ~12%, purely because the denominator was smaller.
    # Fly balls here therefore mean fly_ball + popup, with the infield share
    # kept separately as IFFB%.
    fb_total = out["fb"] + out["pu"]

    out["gb_pct"] = 100 * div(out["gb"], bip)
    out["ld_pct"] = 100 * div(out["ld"], bip)
    out["fb_pct"] = 100 * div(fb_total, bip)
    out["iffb_pct"] = 100 * div(out["pu"], fb_total)
    out["hr_fb_pct"] = 100 * div(out["hr"], fb_total)

    # Exit-velocity buckets, denominated on batted balls that got a reading.
    # These approximate FanGraphs' Soft/Med/Hard, which use a different
    # (visual) classification -- close, not identical.
    out["soft_pct"] = 100 * div(out["soft_hit"], ev_n)
    out["med_pct"] = 100 * div(out["med_hit"], ev_n)
    out["hard_pct"] = 100 * div(out["hard_hit"], ev_n)
    out["avg_ev"] = div(out["ev_sum"], ev_n)

    # FIP strips out everything the defence touches. xFIP goes further and
    # replaces actual home runs with what a league-average HR/FB rate would
    # have produced on this pitcher's fly balls.
    out["fip"] = div(13 * out["hr"] + 3 * (ubb + out["hbp"]) - 2 * out["so"], ip) + FIP_CONSTANT
    # Same fly-ball definition as HR/FB above, so the league rate and the
    # pitcher's fly balls are measured on the same basis.
    expected_hr = league_hr_per_fb * fb_total
    out["xfip"] = div(13 * expected_hr + 3 * (ubb + out["hbp"]) - 2 * out["so"], ip) + FIP_CONSTANT

    return out


def main() -> None:
    frame = load_seasons()
    if frame.empty:
        print("no component files found")
        return

    totals = pool(frame)

    # League HR/FB from the pooled data itself, so xFIP is calibrated to the
    # same seasons rather than to a hardcoded figure.
    league_fb = (totals["fb"] + totals["pu"]).sum()
    league_hr_per_fb = totals["hr"].sum() / league_fb if league_fb > 0 else np.nan
    print(f"league HR/FB across the pooled seasons: {league_hr_per_fb:.3f}")

    splits = derive(totals, league_hr_per_fb)
    splits = splits[splits["tbf"] >= MIN_TBF].copy()

    splits["split"] = "vs " + splits["opp_hand"]
    splits["seasons"] = ", ".join(str(s) for s in sorted(SEASON_WEIGHTS))

    columns = [
        "player_id", "split", "seasons", "tbf", "ip",
        "avg", "babip", "woba", "slg", "iso", "hr_allowed", "hr_rate",
        "k_pct", "bb_pct", "gb_pct", "ld_pct", "fb_pct", "iffb_pct",
        "hr_fb_pct", "soft_pct", "med_pct", "hard_pct", "avg_ev",
        "fip", "xfip",
    ]
    splits = splits[[c for c in columns if c in splits.columns]]

    for column in ("avg", "babip", "woba", "slg", "iso"):
        splits[column] = splits[column].round(3)
    for column in ("hr_rate", "k_pct", "bb_pct", "gb_pct", "ld_pct", "fb_pct",
                   "iffb_pct", "hr_fb_pct", "soft_pct", "med_pct", "hard_pct"):
        splits[column] = splits[column].round(1)
    for column in ("fip", "xfip", "avg_ev"):
        splits[column] = splits[column].round(2)

    splits = splits.sort_values(["player_id", "split"]).reset_index(drop=True)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / "pitcher_splits.parquet"
    splits.to_parquet(dest, index=False)

    print(f"{len(splits)} split rows for {splits['player_id'].nunique()} pitchers "
          f"({MIN_TBF}+ TBF)")
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
