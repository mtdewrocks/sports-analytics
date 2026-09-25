"""Keep a price history of every prop, and record each game's closing line.

    python backend/app/build_odds_snapshots.py --sport mlb
    python backend/app/build_odds_snapshots.py --sport nfl

Runs right after get_props.py in update_props.yml. FREE -- no API calls; it
only reads the props file get_props.py just wrote.

WHY
---
get_props.py keeps the LATEST price per prop and overwrites the rest, so the
file can't tell you where a line opened, how far it has moved, or where it
closed. Those three answers are what line movement, steam alerts and CLV
(closing line value) are built on, and the only way to have them later is to
start keeping them now -- history can't be backfilled from a file that never
stored it.

TWO OUTPUTS
-----------
<slug>_odds_snapshots.parquet   Append-only price history, pruned to
                                SNAPSHOT_RETAIN_DAYS. A row is added only when
                                a prop is NEW or its price CHANGED since the
                                last row for the same key -- not on every run.
                                Carried-forward rows (a game get_props chose
                                not to refresh this run) are unchanged by
                                definition and so add nothing. That keeps the
                                file a list of real moves, and small.

<slug>_closing_lines.parquet    One row per prop per book: the last price seen
                                BEFORE the game started. Permanent (never
                                pruned) and tiny, because it's what every
                                future bet gets graded against.

Key = (event_id, Player, market, Line, bookmakers). A book moving its main
line from 6.5 to 7.5 therefore shows up as a NEW key at 7.5 -- which is right:
those are different bets. The old 6.5 key simply stops getting rows.

HOW FRESH IS "CLOSING"?
-----------------------
Only as fresh as get_props.py's refresh tiers make it. MLB core markets refresh
hourly inside three hours of first pitch, so the close is at most ~1h old.
NFL core markets refresh every 6h inside three days of kickoff, so an NFL
"close" can be several hours stale. Each closing row carries
`minutes_before_start` so anything built on it can say how good the close is,
and a tighter pre-game pull can be added to props_config later without
touching this file.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from props_config import SPORTS  # noqa: E402

DATA_ROOT = HERE.parent / "data"

SNAPSHOT_RETAIN_DAYS = float(os.getenv("SNAPSHOT_RETAIN_DAYS", "21"))

KEY = ["event_id", "Player", "market", "Line", "bookmakers"]
PRICE_COLS = ["Over Price", "Under Price"]
SNAP_COLS = KEY + PRICE_COLS + ["commence_time", "home_team", "away_team", "observed_at"]
CLOSE_COLS = KEY + PRICE_COLS + ["commence_time", "home_team", "away_team",
                                 "observed_at", "minutes_before_start"]


def _key_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize the key columns so equality works across runs: Line as a
    float (a Yes/No market's missing Line stays NaN and is filled with a
    sentinel for matching only), everything else as string."""
    out = df.copy()
    out["Line"] = pd.to_numeric(out["Line"], errors="coerce")
    for c in ("event_id", "Player", "market", "bookmakers"):
        out[c] = out[c].astype(str)
    for c in PRICE_COLS:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def _match_key(df: pd.DataFrame) -> pd.Series:
    line = df["Line"].fillna(-9999.0).map(lambda v: f"{v:g}")
    return (df["event_id"] + "|" + df["Player"] + "|" + df["market"]
            + "|" + line + "|" + df["bookmakers"])


def observed_at(props: pd.DataFrame, run_time: str) -> pd.Series:
    """When THIS row's price was actually fetched. get_props.py stamps the
    core and alternate tiers separately; a market whose name contains
    `_alternate` (or that only has alt_fetched_at) was priced at the alt
    time. Falls back to the run time if neither stamp is set."""
    is_alt = props["market"].astype(str).str.contains("_alternate", regex=False)
    core = props.get("fetched_at", pd.Series(pd.NA, index=props.index))
    alt = props.get("alt_fetched_at", pd.Series(pd.NA, index=props.index))
    ts = core.where(~is_alt, alt)
    ts = ts.where(ts.notna(), alt.where(alt.notna(), core))
    return ts.fillna(run_time).astype(str)


def new_snapshot_rows(props: pd.DataFrame, previous: pd.DataFrame, run_time: str) -> pd.DataFrame:
    """Rows of `props` that are new, or whose Over/Under price differs from
    the most recent snapshot of the same key."""
    if props.empty:
        return pd.DataFrame(columns=SNAP_COLS)

    cur = _key_frame(props)
    cur["observed_at"] = observed_at(props, run_time).values
    for c in ("commence_time", "home_team", "away_team"):
        if c not in cur.columns:
            cur[c] = pd.NA
    cur = cur[SNAP_COLS].drop_duplicates(subset=KEY, keep="last")
    cur["_k"] = _match_key(cur)

    if previous.empty:
        return cur.drop(columns="_k")

    prev = _key_frame(previous)
    prev = prev.sort_values("observed_at").drop_duplicates(subset=KEY, keep="last")
    prev["_k"] = _match_key(prev)
    last = prev.set_index("_k")[PRICE_COLS]

    joined = cur.join(last, on="_k", rsuffix="_prev")
    unseen = joined["Over Price_prev"].isna() & joined["Under Price_prev"].isna() \
        & ~joined["_k"].isin(last.index)

    def _differs(a: pd.Series, b: pd.Series) -> pd.Series:
        return ~((a == b) | (a.isna() & b.isna()))

    changed = _differs(joined["Over Price"], joined["Over Price_prev"]) \
        | _differs(joined["Under Price"], joined["Under Price_prev"])
    out = joined[unseen | changed]
    return out[SNAP_COLS]


def prune(snapshots: pd.DataFrame, now: pd.Timestamp, days: float) -> pd.DataFrame:
    """Drop history for games that started more than `days` ago. Pruned by
    GAME start rather than by row time, so a game's history is always
    whole -- never half a line chart."""
    if snapshots.empty:
        return snapshots
    start = pd.to_datetime(snapshots["commence_time"], utc=True, errors="coerce")
    keep = start.isna() | (start >= now - pd.Timedelta(days=days))
    return snapshots[keep]


def closing_lines(props: pd.DataFrame, snapshots: pd.DataFrame, existing: pd.DataFrame,
                  now: pd.Timestamp, run_time: str) -> pd.DataFrame:
    """For every game that has STARTED and isn't closed out yet, the last
    price per key fetched before its start.

    Read from the PROPS file first, not the snapshots: get_props.py stops
    fetching a game at its start time and keeps its last rows for
    RETAIN_LIVE_HOURS, so the props row IS the final pre-game price -- and its
    fetched_at says exactly when that price was last confirmed. (Snapshots
    only record CHANGES, so their timestamp is when the price last moved,
    which would overstate how old a stable close is.) If a game has already
    aged out of the props file -- a workflow gap longer than RETAIN_LIVE_HOURS
    -- the snapshot history is the fallback.

    Games already in `existing` are left exactly as recorded: a close, once
    final, never changes.
    """
    done = set(existing["event_id"].astype(str)) if not existing.empty else set()
    frames = []

    if not props.empty:
        p = _key_frame(props)
        p["observed_at"] = observed_at(props, run_time).values
        frames.append(p)
    if not snapshots.empty:
        s = _key_frame(snapshots)
        in_props = set(frames[0]["event_id"]) if frames else set()
        frames.append(s[~s["event_id"].isin(in_props)])
    if not frames:
        return existing if not existing.empty else pd.DataFrame(columns=CLOSE_COLS)

    cand = pd.concat(frames, ignore_index=True)
    for c in ("commence_time", "home_team", "away_team"):
        if c not in cand.columns:
            cand[c] = pd.NA
    cand["_start"] = pd.to_datetime(cand["commence_time"], utc=True, errors="coerce")
    cand["_obs"] = pd.to_datetime(cand["observed_at"], utc=True, errors="coerce", format="mixed")
    cand = cand[cand["_start"].notna() & (cand["_start"] <= now)
                & cand["_obs"].notna() & (cand["_obs"] <= cand["_start"])
                & ~cand["event_id"].isin(done)]
    if cand.empty:
        return existing if not existing.empty else pd.DataFrame(columns=CLOSE_COLS)

    last = cand.sort_values("_obs").drop_duplicates(subset=KEY, keep="last").copy()
    last["minutes_before_start"] = ((last["_start"] - last["_obs"]).dt.total_seconds() / 60).round(0)
    last = last[CLOSE_COLS].reset_index(drop=True)
    if existing.empty:
        return last
    return pd.concat([existing, last], ignore_index=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", required=True, choices=sorted(SPORTS))
    args = ap.parse_args()
    cfg = SPORTS[args.sport]

    folder = DATA_ROOT / cfg.slug
    props_path = folder / cfg.output
    snap_path = folder / f"{cfg.slug}_odds_snapshots.parquet"
    close_path = folder / f"{cfg.slug}_closing_lines.parquet"

    if not props_path.exists():
        print(f"no props file at {props_path}; nothing to snapshot")
        return 0

    now = pd.Timestamp.now(tz="UTC")
    run_time = now.isoformat()
    props = pd.read_parquet(props_path)
    previous = pd.read_parquet(snap_path) if snap_path.exists() else pd.DataFrame(columns=SNAP_COLS)
    closes = pd.read_parquet(close_path) if close_path.exists() else pd.DataFrame(columns=CLOSE_COLS)

    added = new_snapshot_rows(props, previous, run_time)
    snaps = pd.concat([f for f in (previous, added) if not f.empty], ignore_index=True) \
        if not (previous.empty and added.empty) else pd.DataFrame(columns=SNAP_COLS)

    # Closing lines BEFORE pruning, so a game is always closed out while its
    # history still exists.
    closes_out = closing_lines(props, snaps, closes, now, run_time)
    snaps = prune(snaps, now, SNAPSHOT_RETAIN_DAYS)

    folder.mkdir(parents=True, exist_ok=True)
    snaps.reset_index(drop=True).to_parquet(snap_path, index=False)
    closes_out.reset_index(drop=True).to_parquet(close_path, index=False)

    new_games = len(closes_out) - len(closes)
    print(f"[{cfg.slug}] +{len(added)} snapshot rows ({len(snaps)} kept, "
          f"{SNAPSHOT_RETAIN_DAYS:g}-day window); +{new_games} closing rows "
          f"({len(closes_out)} total)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
