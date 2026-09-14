"""Pull player props from The Odds API, on a budget.

    python backend/app/get_props.py --sport mlb
    python backend/app/get_props.py --sport nfl
    python backend/app/get_props.py --sport nfl --dry-run   # plan only, no spend

Output: backend/data/<slug>/<output>, long format -- one row per
player x market x line x bookmaker. app/data/mlb.py pivots it wide
(bookmakers become columns) and finds its columns BY NAME, so
Player / market / Line / bookmakers / Over Price are a contract. Rename one and
the Props page silently empties instead of erroring.

THE BUDGET PROBLEM
------------------
The event-odds endpoint is charged as:

    cost = (unique markets RETURNED) x (regions requested)

per event, per call. The original MLB script asked for 16 markets across 3
regions, so one event cost up to 48 credits; ~15 games a day run hourly came to
over 300,000 a month against a 100,000 quota. NFL is worse -- 60 documented
prop markets, and lines live for six days rather than one.

Listing events is FREE (`/events` does not count against the quota). That is
the whole lever: the schedule and every start time cost nothing, so the script
can be precise about the only thing it actually pays for.

Three mechanisms, in order of how much they save:

  1. TIERED REFRESH (props_config.py). A line six days out barely moves; one
     forty minutes out moves constantly. The refresh interval scales with time
     to kickoff, and a game that isn't due keeps its previous lines rather than
     being dropped.

  2. SPLIT MARKET TIERS. The `*_alternate` ladders are half the markets and
     move far more slowly than the main line, so they get their own, slower
     cadence. Because cost counts UNIQUE MARKETS RETURNED, asking for core and
     alt together in one call costs exactly what two separate calls would --
     so when both are due they are merged into a single request.

  3. HARD STOPS. x-requests-remaining is checked on every response and the run
     stops at MIN_REMAINING; a per-run ceiling bounds the damage from a bad
     config. These are the backstop, not the plan -- if you are relying on
     them, the tiers above are wrong.

ONLY UPCOMING GAMES, always: commenceTimeFrom=now on the free events call, so
a game in progress is never fetched.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

from app.props_config import SPORTS, SportConfig

API_BASE = "https://api.the-odds-api.com/v4"
DATA_ROOT = Path(__file__).resolve().parent.parent / "data"

# Each extra region MULTIPLIES the cost of every event fetch: "us,us2" doubles
# the bill, adding us_dfs triples it. Check the projection this script prints
# before leaving a second one on.
REGIONS = os.getenv("ODDS_REGIONS", "us")
MIN_REMAINING = int(os.getenv("ODDS_MIN_REMAINING", "5000"))
MAX_SPEND_PER_RUN = int(os.getenv("ODDS_MAX_SPEND_PER_RUN", "400"))

TIMEOUT = 30
RETRY_SLEEPS = (2, 6, 15)

OUT_COLS = ["Player", "market", "Line", "bookmakers", "Over Price", "Under Price",
            "commence_time", "home_team", "away_team", "event_id",
            "fetched_at", "alt_fetched_at"]


class QuotaExhausted(RuntimeError):
    pass


def _api_key() -> str:
    key = os.getenv("ODDS_API_KEY")
    if not key:
        sys.exit("ODDS_API_KEY is not set. Never hardcode it -- it is a billable credential.")
    return key


def _get(url: str, params: dict) -> requests.Response:
    """GET with backoff on 429 and 5xx. Any other 4xx is a definite answer
    (bad key, unknown market) and comes straight back -- retrying it would turn
    a clear failure into a slow one."""
    last = None
    for attempt, sleep_for in enumerate((*RETRY_SLEEPS, None), start=1):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT)
        except requests.RequestException as e:
            last = f"network error: {e}"
        else:
            if r.status_code < 400 or (400 <= r.status_code < 500 and r.status_code != 429):
                return r
            last = f"HTTP {r.status_code}: {r.text[:200]}"
        if sleep_for is None:
            break
        print(f"  attempt {attempt} failed ({last}); retrying in {sleep_for}s")
        time.sleep(sleep_for)
    raise RuntimeError(f"giving up: {last}")


def fetch_upcoming_events(api_key: str, cfg: SportConfig) -> list[dict]:
    """Events that have not started. Free -- does not touch the quota."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = _get(f"{API_BASE}/sports/{cfg.key}/events",
             {"api_key": api_key, "commenceTimeFrom": now, "dateFormat": "iso"})
    if r.status_code != 200:
        raise RuntimeError(f"events call failed: HTTP {r.status_code} {r.text[:200]}")
    return r.json()


def _hours_until(commence_time: str) -> float:
    return (pd.to_datetime(commence_time, utc=True)
            - pd.Timestamp.now(tz="UTC")).total_seconds() / 3600.0


def _interval(tiers: tuple, hours_out: float) -> float:
    for threshold, interval in tiers:
        if hours_out <= threshold:
            return interval
    return tiers[-1][1]


def _last_seen(previous: pd.DataFrame, col: str) -> dict:
    if previous.empty or col not in previous.columns or "event_id" not in previous.columns:
        return {}
    seen = previous.dropna(subset=[col]).groupby("event_id")[col].max()
    return {k: pd.to_datetime(v, utc=True) for k, v in seen.items()}


def plan(events: list[dict], previous: pd.DataFrame, cfg: SportConfig) -> list[dict]:
    """Decide, per event, which market tiers are due.

    Returns the events needing a call, each carrying `_markets` (what to ask
    for) and `_why` (so the log explains a spend rather than just reporting it).
    """
    core_seen = _last_seen(previous, "fetched_at")
    alt_seen = _last_seen(previous, "alt_fetched_at")
    now = pd.Timestamp.now(tz="UTC")
    todo = []

    for ev in events:
        hours_out = _hours_until(ev["commence_time"])
        reasons, markets = [], []

        for label, seen, tiers, keys in (
            ("core", core_seen, cfg.core_tiers, cfg.core_markets),
            ("alt", alt_seen, cfg.alt_tiers, cfg.alt_markets),
        ):
            prev = seen.get(ev["id"])
            need = _interval(tiers, hours_out)
            if prev is None:
                markets += list(keys)
                reasons.append(f"{label}:new")
            else:
                age = (now - prev).total_seconds() / 3600.0
                if age >= need:
                    markets += list(keys)
                    reasons.append(f"{label}:{age:.1f}h>={need:g}h")

        if markets:
            ev["_markets"] = markets
            ev["_core"] = any(r.startswith("core") for r in reasons)
            ev["_alt"] = any(r.startswith("alt") for r in reasons)
            ev["_why"] = f"{', '.join(reasons)} (starts in {hours_out:.1f}h)"
            todo.append(ev)
    return todo


def fetch_event_odds(api_key: str, event: dict, cfg: SportConfig,
                     spent: list[int]) -> pd.DataFrame:
    r = _get(
        f"{API_BASE}/sports/{cfg.key}/events/{event['id']}/odds",
        {
            "api_key": api_key,
            "regions": REGIONS,
            "markets": ",".join(event["_markets"]),
            "oddsFormat": "american",
            "dateFormat": "iso",
        },
    )

    cost = r.headers.get("x-requests-last")
    remaining = r.headers.get("x-requests-remaining")
    if cost is not None:
        spent.append(int(float(cost)))

    label = f"{event['away_team']} @ {event['home_team']}"
    if r.status_code == 422:
        # No props posted for this game yet, or a market key this sport does not
        # serve. Normal, and free -- only markets that RETURN data are charged.
        print(f"  {label}: no props available")
        return pd.DataFrame()
    if r.status_code != 200:
        print(f"  {label}: HTTP {r.status_code}, skipped")
        return pd.DataFrame()
    if remaining is not None and int(float(remaining)) < MIN_REMAINING:
        raise QuotaExhausted(f"x-requests-remaining={remaining} < MIN_REMAINING={MIN_REMAINING}")

    payload = r.json()
    rows = []
    # .get() throughout: an event can come back with no bookmakers block, and
    # payload['bookmakers'] raised KeyError on those -- killing an entire run
    # over one quiet game.
    for book in payload.get("bookmakers", []):
        for market in book.get("markets", []):
            for outcome in market.get("outcomes", []):
                rows.append({
                    "description": outcome.get("description"),
                    "name": outcome.get("name"),
                    "price": outcome.get("price"),
                    "point": outcome.get("point"),
                    "market": market.get("key"),
                    "bookmakers": book.get("key"),
                })
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["event_id"] = payload.get("id")
    df["commence_time"] = payload.get("commence_time")
    df["home_team"] = payload.get("home_team")
    df["away_team"] = payload.get("away_team")

    got = sorted(df["market"].unique())
    missing = [m for m in event["_markets"] if m not in got]
    print(f"  {label}: {len(df)} outcomes, {len(got)} markets, cost {cost}")
    if missing:
        # Worth seeing: a key that never returns anything is either wrong or
        # not offered for this sport, and pruning it shortens every request.
        print(f"     no data for: {', '.join(missing[:6])}"
              + (f" (+{len(missing) - 6} more)" if len(missing) > 6 else ""))
    return df


def to_over_under(df: pd.DataFrame, cfg: SportConfig) -> pd.DataFrame:
    """Collapse Over/Under pairs onto one row.

    OUTER join, not the original's left join: a book posting only an Under
    still carries a real line, and dropping it quietly shrinks the comparison
    grid the Props page exists to show -- and removes exactly the legs the
    middles screen pairs against.
    """
    if df.empty:
        return pd.DataFrame(columns=[c for c in OUT_COLS if c != "alt_fetched_at"])

    keys = ["description", "point", "market", "bookmakers",
            "event_id", "commence_time", "home_team", "away_team"]
    df = df.drop_duplicates(subset=keys + ["name"])

    # Yes/No markets -- anytime TD, first TD, pitcher to record a win -- come
    # back with outcome names "Yes"/"No" and no point. Matching only on
    # Over/Under dropped every one of their rows on the floor AFTER paying for
    # them: cost counts markets that RETURN data, and these return plenty.
    #
    # "Yes" IS the over side (anytime TD = over 0.5 touchdowns), so mapping
    # them keeps the line-shopping pivot working unchanged -- the row just has
    # no Line, which is correct: there is no number to beat.
    df = df.copy()
    df["name"] = df["name"].replace({"Yes": "Over", "No": "Under"})

    over = df[df["name"] == "Over"].drop(columns=["name"]).rename(columns={"price": "Over Price"})
    under = df[df["name"] == "Under"].drop(columns=["name"]).rename(columns={"price": "Under Price"})
    merged = over.merge(under, on=keys, how="outer")
    merged = merged.rename(columns={"description": "Player", "point": "Line"})

    for prefix in cfg.strip_prefixes:
        merged["market"] = merged["market"].str.replace(prefix, "", regex=False)
    return merged


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", required=True, choices=sorted(SPORTS))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = SPORTS[args.sport]
    out_path = DATA_ROOT / cfg.slug / cfg.output
    api_key = _api_key()
    n_regions = len(REGIONS.split(","))

    previous = pd.read_parquet(out_path) if out_path.exists() else pd.DataFrame()
    print(f"[{cfg.slug}] previous file: {len(previous)} rows")

    events = fetch_upcoming_events(api_key, cfg)
    print(f"{len(events)} upcoming events (this call is free)")
    if not events:
        print("nothing upcoming; leaving the existing file alone")
        return 0

    todo = plan(events, previous, cfg)
    worst = sum(len(ev["_markets"]) for ev in todo) * n_regions
    print(f"\n{len(todo)} of {len(events)} events due; "
          f"worst-case {worst} credits ({n_regions} region(s))")
    print("actual will be lower -- only markets that RETURN data are charged")

    if args.dry_run:
        for ev in todo:
            print(f"  would fetch {ev['away_team']} @ {ev['home_team']}: "
                  f"{len(ev['_markets'])} markets -- {ev['_why']}")
        return 0

    spent: list[int] = []
    frames, core_ids, alt_ids = [], set(), set()
    for ev in todo:
        if sum(spent) >= MAX_SPEND_PER_RUN:
            print(f"\nper-run ceiling of {MAX_SPEND_PER_RUN} reached; stopping")
            break
        try:
            frame = fetch_event_odds(api_key, ev, cfg, spent)
        except QuotaExhausted as e:
            print(f"\nSTOPPING: {e}")
            break
        if not frame.empty:
            frames.append(frame)
            if ev["_core"]:
                core_ids.add(ev["id"])
            if ev["_alt"]:
                alt_ids.add(ev["id"])

    fresh = to_over_under(pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(), cfg)
    now_iso = pd.Timestamp.now(tz="UTC").isoformat()
    if not fresh.empty:
        # Timestamped per TIER, because that is the granularity the next run's
        # plan() reasons about: a core-only refresh must not make the ladders
        # look freshly fetched.
        fresh["fetched_at"] = fresh["event_id"].map(
            lambda e: now_iso if e in core_ids else pd.NA)
        fresh["alt_fetched_at"] = fresh["event_id"].map(
            lambda e: now_iso if e in alt_ids else pd.NA)

    # Carry forward every upcoming event we didn't refresh, plus the tier
    # timestamps we didn't touch. Without this, being frugal and losing the
    # data would look identical from the outside.
    refreshed = set(fresh["event_id"]) if not fresh.empty else set()
    upcoming = {ev["id"] for ev in events}
    keep = pd.DataFrame()
    if not previous.empty and "event_id" in previous.columns:
        keep = previous[previous["event_id"].isin(upcoming - refreshed)]
        if not fresh.empty:
            prior_alt = _last_seen(previous, "alt_fetched_at")
            prior_core = _last_seen(previous, "fetched_at")
            fresh["alt_fetched_at"] = fresh.apply(
                lambda r: r["alt_fetched_at"] if pd.notna(r["alt_fetched_at"])
                else prior_alt.get(r["event_id"], pd.NA), axis=1)
            fresh["fetched_at"] = fresh.apply(
                lambda r: r["fetched_at"] if pd.notna(r["fetched_at"])
                else prior_core.get(r["event_id"], pd.NA), axis=1)

    out = pd.concat([f for f in (fresh, keep) if not f.empty], ignore_index=True)
    if out.empty:
        print("\nnothing to write; leaving the existing file alone")
        return 0

    for c in OUT_COLS:
        if c not in out.columns:
            out[c] = pd.NA
    out = out[OUT_COLS].sort_values(["Player", "market", "bookmakers", "Line"])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)

    used = sum(spent)
    print(f"\nspent {used} credits ({len(fresh)} fresh rows, {len(keep)} carried forward)")
    print(f"wrote {len(out)} rows -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
