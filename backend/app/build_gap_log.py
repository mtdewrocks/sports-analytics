"""Log every NBA gap bet (anti-middle) the first time it appears.

    python backend/app/build_gap_log.py --sport nba

Runs in update_props.yml right after build_prop_middles.py. FREE -- it only
reads the middles file that step just wrote.

Each run, any anti-middle pair on a game that hasn't started is recorded the
FIRST time it shows up, at those prices; later sightings only bump last_seen.
The site grades the log against box scores once games finish
(app/data/nba_gaps.py::get_gap_record), so "gap bets on game totals are
+3.1% over 214 pairs" becomes a measured fact rather than an estimate --
the job Analyzing_Middle_Bets.py used to do by hand.

Output: backend/data/<slug>/<slug>_gap_log.parquet, kept RETAIN_DAYS.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from props_config import SPORTS  # noqa: E402

DATA_ROOT = HERE.parent / "data"
RETAIN_DAYS = 400          # a full season plus, so the record can span one
KEY = ["Player", "market", "commence_time", "over_book", "over_line", "under_book", "under_line"]
COLS = KEY + ["over_price", "under_price", "one_wins_pct", "breakeven_window_rate_pct",
              "stake_over_pct", "window", "dfs_leg", "home_team", "away_team",
              "first_seen", "last_seen"]


def update_log(pairs: pd.DataFrame, logged: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    now_iso = now.isoformat()
    if pairs is None or pairs.empty or "kind" not in pairs.columns:
        return logged
    gaps = pairs[pairs["kind"] == "anti_middle"].copy()
    if gaps.empty:
        return logged
    start = pd.to_datetime(gaps["commence_time"], utc=True, errors="coerce")
    gaps = gaps[start > now]                          # only bets you could still place
    # Even-money legs are left off the page, so they're not logged either; and
    # of the hundreds of alt-line pairs a player can have, keep the best payout
    # at each gap width -- the page picks its one pair per game from these.
    gaps = gaps[(pd.to_numeric(gaps["over_price"], errors="coerce") != 100)
                & (pd.to_numeric(gaps["under_price"], errors="coerce") != 100)
                & (gaps["over_line"].astype(float) - gaps["under_line"].astype(float)
                   <= gaps["market"].isin(["totals", "team_totals"]).map({True: 5.0, False: 2.0}))]   # page's max gap
    if gaps.empty:
        return logged
    width = (gaps["over_line"].astype(float).apply(math.floor) - gaps["under_line"].astype(float).apply(math.ceil))
    gaps = (gaps.assign(_w=width, _p=-gaps["one_wins_pct"].astype(float))
                .sort_values("_p").drop_duplicates(subset=["Player", "market", "commence_time", "_w"])
                .drop(columns=["_w", "_p"]))
    gaps["commence_time"] = gaps["commence_time"].astype(str)
    for c in COLS:
        if c not in gaps.columns:
            gaps[c] = pd.NA
    gaps["first_seen"] = now_iso
    gaps["last_seen"] = now_iso
    gaps = gaps[COLS].drop_duplicates(subset=KEY)

    if logged is None or logged.empty:
        out = gaps
    else:
        logged = logged.copy()
        logged["commence_time"] = logged["commence_time"].astype(str)
        k = lambda df: df[KEY].astype(str).agg("|".join, axis=1)  # noqa: E731
        seen_now = set(k(gaps))
        logged.loc[k(logged).isin(seen_now), "last_seen"] = now_iso
        fresh = gaps[~k(gaps).isin(set(k(logged)))]
        out = pd.concat([logged, fresh], ignore_index=True)

    cutoff = now - pd.Timedelta(days=RETAIN_DAYS)
    keep = pd.to_datetime(out["commence_time"], utc=True, errors="coerce") >= cutoff
    return out[keep].reset_index(drop=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", required=True, choices=sorted(SPORTS))
    args = ap.parse_args()
    cfg = SPORTS[args.sport]
    folder = DATA_ROOT / cfg.slug
    src = folder / f"{cfg.slug}_prop_middles.parquet"
    out_path = folder / f"{cfg.slug}_gap_log.parquet"

    pairs = pd.read_parquet(src) if src.exists() else pd.DataFrame()
    logged = pd.read_parquet(out_path) if out_path.exists() else pd.DataFrame()
    before = len(logged)
    out = update_log(pairs, logged, pd.Timestamp.now(tz="UTC"))
    if out is None or out.empty:
        print("no gap bets logged yet")
        return 0
    folder.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)
    print(f"gap log: {before} -> {len(out)} rows ({len(out) - before} new) -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
