"""Pull game-level point spreads and totals from The Odds API, once a day.

    python backend/app/get_game_lines.py --sport mlb
    python backend/app/get_game_lines.py --sport nfl

WHY A SEPARATE SCRIPT FROM get_props.py
----------------------------------------
Player props need a per-event call (see get_props.py's docstring for the
whole tiered-refresh budget story) because that's how the Odds API exposes
them. Spreads and totals are different: they live on the bulk sport-level
odds endpoint, so ONE call per sport covers every upcoming game for the
day. That makes them cheap enough to run on their own daily schedule,
independent of the props pull's hourly cadence -- and a once-a-day line is
still a meaningfully fresher "projected points" number than the schedule
file's own baked-in line, which is refreshed once a day from a third-party
source (nflverse) that isn't tied to actual current sportsbook pricing.

    GET /v4/sports/{sport_key}/odds
        ?apiKey=...&bookmakers=<BOOKMAKERS>&markets=spreads,totals
        &oddsFormat=american&dateFormat=iso

Named books, not regions, for the same reason get_props.py uses
`bookmakers`: it overrides `regions` when both are sent, and bills ten
books as one region -- reusing props_config.BOOKMAKERS directly (rather
than inventing a second, possibly-diverging list) keeps this scoped to the
same books the props pull already pays for.

SIGN CONVENTION -- READ THIS BEFORE TOUCHING THE SPREAD MATH
--------------------------------------------------------------
The Odds API's own convention for the `spreads` market: the outcome whose
name matches a team carries that team's spread, and a NEGATIVE point means
that team is favored (e.g. home team point -3.5 means the home team is
favored by 3.5).

This app's own convention, already verified against real data in
app/data/nfl.py's get_game_script_projection() ("spread_line is the home
team's spread: POSITIVE = home favored by that many points -- confirmed
against real data -- LAC @ +10.5 home was actually a 10.5-point favorite,
the opposite of the initially assumed convention"), is the OPPOSITE:
POSITIVE = home favored.

So the raw Odds API home-team point is negated here, once, at the source,
rather than leaving every downstream reader to remember to flip it:

    spread_line = -raw_home_point

Worked example (hand-traced, matches this file's own module docstring
sample payload): New England (home) vs Pittsburgh (away), raw home-team
outcome is {"name": "New England Patriots", "point": -3.5} -- Odds API
says the Patriots (home) are favored by 3.5, so raw_home_point = -3.5.
This script's own spread_line = -(-3.5) = +3.5, i.e. "home favored by 3.5"
in THIS app's convention. Matches get_game_script_projection()'s own
documented sign. A positive get_game_lines.py spread_line always means the
home team is favored, same as the schedule file's spread_line it now sits
alongside in app/data/nfl.py.

MEDIAN, NOT BEST PRICE
-----------------------
The Hit Rate Sheet's best_odds is a genuinely "shop for the best price"
number -- a bettor can only take one price and wants the best one. A
game's spread/total isn't that: it's a "what is the market saying" number,
so one outlier book (a stale price, a fat-fingered line) shouldn't move
it. The median across every book that posted a price is cheap in pandas
and robust to exactly that one-outlier case -- a real, meaningful
distinction from best_odds worth keeping in mind if this script is ever
extended to price-shop.

SKIP, DON'T ERROR
------------------
Some far-out games have no lines posted yet on either market. Same quiet
tone as get_props.py's 422 handling: skip that event, keep going.

CARRY-FORWARD
--------------
Simple, because this is a full daily overwrite rather than an accumulating
log (unlike get_pitcher_logs.py's merge(), which replaces per pitcher
because it's INCREMENTAL): concat today's rows with any previous row whose
event_id didn't come back today (a transient miss), then drop duplicates
keeping the new one.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import requests

# Run as a plain script (`python backend/app/get_game_lines.py`), sys.path[0]
# is backend/app/ -- so `backend/` is not importable and `from
# app.props_config` fails with ModuleNotFoundError. Same bootstrap
# get_props.py already uses, so sibling imports work however this is invoked.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from props_config import BOOKMAKERS, SPORTS, SportConfig  # noqa: E402

API_BASE = "https://api.the-odds-api.com/v4"
DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
OUTPUT_FILENAME = "game_lines.parquet"
TIMEOUT = 30

OUT_COLS = ["event_id", "commence_time", "home_team", "away_team",
            "spread_line", "total_line", "book_count", "fetched_at"]


def _api_key() -> str:
    key = os.getenv("ODDS_API_KEY")
    if not key:
        sys.exit("ODDS_API_KEY is not set. Never hardcode it -- it is a billable credential.")
    return key


def _scope_params() -> dict:
    """Named books beat regions -- see the module docstring. Reuses
    props_config.BOOKMAKERS directly rather than an env-overridable copy:
    unlike get_props.py this script has no per-run budget to protect (one
    call a day, always the same cost), so there's nothing an override would
    be tuning."""
    return {"bookmakers": ",".join(BOOKMAKERS)}


def fetch_game_lines(api_key: str, cfg: SportConfig) -> list[dict]:
    """One call, whole sport: spreads/totals are on the bulk sport-level
    odds endpoint, unlike player props which need a per-event call."""
    r = requests.get(
        f"{API_BASE}/sports/{cfg.key}/odds",
        params={
            "apiKey": api_key,
            **_scope_params(),
            "markets": "spreads,totals",
            "oddsFormat": "american",
            "dateFormat": "iso",
        },
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        raise RuntimeError(f"odds call failed: HTTP {r.status_code} {r.text[:200]}")
    return r.json()


def _event_line(event: dict) -> dict | None:
    """One row for this event, or None if neither market has anything
    posted yet (skip, don't error -- see module docstring)."""
    home_team = event.get("home_team")
    away_team = event.get("away_team")
    spreads: list[float] = []
    totals: list[float] = []
    contributing_books: set[str] = set()

    for book in event.get("bookmakers", []):
        book_key = book.get("key")
        contributed = False
        for market in book.get("markets", []):
            if market.get("key") == "spreads":
                for outcome in market.get("outcomes", []):
                    if outcome.get("name") == home_team and outcome.get("point") is not None:
                        # See the module docstring's "SIGN CONVENTION"
                        # section -- this negation is the single most
                        # important line in this file.
                        spreads.append(-float(outcome["point"]))
                        contributed = True
            elif market.get("key") == "totals":
                for outcome in market.get("outcomes", []):
                    if outcome.get("name") == "Over" and outcome.get("point") is not None:
                        totals.append(float(outcome["point"]))
                        contributed = True
        if contributed:
            contributing_books.add(book_key)

    if not spreads and not totals:
        return None

    return {
        "event_id": event.get("id"),
        "commence_time": event.get("commence_time"),
        "home_team": home_team,
        "away_team": away_team,
        "spread_line": float(pd.Series(spreads).median()) if spreads else None,
        "total_line": float(pd.Series(totals).median()) if totals else None,
        # However many distinct books contributed a price to either median
        # above -- kept for later debugging/trust, not used in the median
        # itself.
        "book_count": len(contributing_books),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", required=True, choices=sorted(SPORTS))
    args = ap.parse_args()

    cfg = SPORTS[args.sport]
    out_path = DATA_ROOT / cfg.slug / OUTPUT_FILENAME
    api_key = _api_key()

    previous = pd.read_parquet(out_path) if out_path.exists() else pd.DataFrame()
    print(f"[{cfg.slug}] previous file: {len(previous)} rows")

    events = fetch_game_lines(api_key, cfg)
    print(f"{len(events)} events returned")

    rows = []
    for event in events:
        row = _event_line(event)
        label = f"{event.get('away_team')} @ {event.get('home_team')}"
        if row is None:
            print(f"  {label}: no spread/total posted yet, skipped")
            continue
        print(f"  {label}: spread {row['spread_line']}, total {row['total_line']} "
              f"({row['book_count']} book(s))")
        rows.append(row)

    now_iso = pd.Timestamp.now(tz="UTC").isoformat()
    fresh = pd.DataFrame(rows)
    if not fresh.empty:
        fresh["fetched_at"] = now_iso

    # Light carry-forward: keep any previous row whose event_id didn't come
    # back today (a transient miss) instead of dropping it. Simpler than
    # get_props.py's tiered carry-forward since this is a full daily
    # overwrite, not an accumulating log -- there's only one tier.
    keep = pd.DataFrame()
    if not previous.empty and "event_id" in previous.columns:
        fresh_ids = set(fresh["event_id"]) if not fresh.empty else set()
        keep = previous[~previous["event_id"].isin(fresh_ids)]

    out = pd.concat([f for f in (fresh, keep) if not f.empty], ignore_index=True)
    if out.empty:
        print("nothing to write; leaving the existing file alone")
        return 0

    # keep="first": fresh rows are concatenated before carried-forward ones,
    # so on any overlap (shouldn't happen -- keep already excludes fresh
    # event_ids above) the new row wins.
    out = out.drop_duplicates(subset=["event_id"], keep="first")

    for c in OUT_COLS:
        if c not in out.columns:
            out[c] = pd.NA
    out = out[OUT_COLS].sort_values("commence_time").reset_index(drop=True)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)

    print(f"\nwrote {len(out)} rows ({len(fresh)} fresh, {len(keep)} carried forward) -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
