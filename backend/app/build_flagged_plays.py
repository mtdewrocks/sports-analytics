"""Log every play the EV Finder flags, and grade it against the close.

    python backend/app/build_flagged_plays.py --sport nfl
    python backend/app/build_flagged_plays.py --sport mlb

Runs in update_props.yml right after build_odds_snapshots.py. FREE -- it only
reads files the earlier steps just wrote.

This is the site's report card, and it works whether or not anyone logs a
bet: each run, any (prop line, side, book) the EV Finder would show is
recorded the FIRST time it appears, at that price. Once the game starts and
its closing line is recorded, the play gets a CLV. "EV Finder plays beat the
closing line 64% of the time, +2.8% on average" is then a measured fact --
for tuning the tool, and for telling people why it's worth paying for.

Output: backend/data/<slug>/<slug>_flagged_plays.parquet, kept RETAIN_DAYS.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from market_core import closing_for, compute_ev  # noqa: E402
from props_config import SPORTS  # noqa: E402

DATA_ROOT = HERE.parent / "data"
RETAIN_DAYS = 120
KEY = ["event_id", "player", "market", "line", "side", "book"]
COLS = KEY + ["price", "fair_pct", "ev_pct", "source", "consensus_books", "commence_time",
              "home_team", "away_team", "flagged_at", "close_price", "close_fair_pct", "clv_pct"]


def new_flags(ev_rows: list, logged: pd.DataFrame, now_iso: str) -> pd.DataFrame:
    """EV rows not already in the log, first sighting only."""
    if not ev_rows:
        return pd.DataFrame(columns=COLS)
    df = pd.DataFrame(ev_rows)
    df["flagged_at"] = now_iso
    for c in ("close_price", "close_fair_pct", "clv_pct"):
        df[c] = float("nan")
    df = df[[c for c in COLS if c in df.columns]]
    if logged.empty:
        return df.reset_index(drop=True)

    def k(frame):
        # Fill blanks (e.g. HR props have no line) with "nan" explicitly, so keys
        # match rows logged under pandas 2 and the join never sees a float.
        keys = frame[KEY].astype(object)
        return keys.where(keys.notna(), "nan").astype(str).agg("|".join, axis=1)

    return df[~k(df).isin(set(k(logged)))].reset_index(drop=True)


def grade(log: pd.DataFrame, closes: pd.DataFrame, now: pd.Timestamp) -> pd.DataFrame:
    """Fill CLV for plays whose game has started and has a closing line."""
    if log.empty or closes.empty:
        return log
    log = log.copy()
    start = pd.to_datetime(log["commence_time"], utc=True, errors="coerce")
    todo = log.index[(start <= now) & log["clv_pct"].isna()]
    for i in todo:
        r = log.loc[i]
        line = None if pd.isna(r["line"]) else float(r["line"])
        c = closing_for({"event_id": r["event_id"], "player": r["player"], "market": r["market"],
                         "line": line, "side": r["side"], "book": r["book"], "price": int(r["price"])},
                        closes)
        if c:
            log.at[i, "close_price"] = c["close_price"]
            log.at[i, "close_fair_pct"] = c["close_fair_pct"]
            log.at[i, "clv_pct"] = c["clv_pct"]
    return log


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", required=True, choices=sorted(SPORTS))
    args = ap.parse_args()
    cfg = SPORTS[args.sport]
    folder = DATA_ROOT / cfg.slug
    props_path = folder / cfg.output
    close_path = folder / f"{cfg.slug}_closing_lines.parquet"
    log_path = folder / f"{cfg.slug}_flagged_plays.parquet"
    if not props_path.exists():
        print("no props file; nothing to do")
        return 0

    now = pd.Timestamp.now(tz="UTC")
    props = pd.read_parquet(props_path)
    log = pd.read_parquet(log_path) if log_path.exists() else pd.DataFrame(columns=COLS)
    closes = pd.read_parquet(close_path) if close_path.exists() else pd.DataFrame()

    added = new_flags(compute_ev(props), log, now.isoformat())
    log = pd.concat([f for f in (log, added) if not f.empty], ignore_index=True) \
        if not (log.empty and added.empty) else pd.DataFrame(columns=COLS)
    log = grade(log, closes, now)
    if not log.empty:
        start = pd.to_datetime(log["commence_time"], utc=True, errors="coerce")
        log = log[start.isna() | (start >= now - pd.Timedelta(days=RETAIN_DAYS))]

    folder.mkdir(parents=True, exist_ok=True)
    log.reset_index(drop=True).to_parquet(log_path, index=False)
    graded = int(log["clv_pct"].notna().sum()) if not log.empty else 0
    print(f"[{cfg.slug}] +{len(added)} flagged plays ({len(log)} logged, {graded} graded)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
