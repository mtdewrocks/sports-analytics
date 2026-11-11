"""One-off backfill: pregame NBA spreads and totals from The Odds API.

Why: ESPN's scoreboard only shows a game's line until tip, so the ESPN
"backfill odds" option comes back empty for finished games (tested Nov 2026:
0 lines). The projection models need past lines to learn what a Vegas
total and spread mean for a player's minutes and stats.

What it buys: ONE snapshot per game day at SNAPSHOT_UTC (11 AM Eastern,
before any normal tip), with spreads and totals for every game on the board
in a single call. Cost: 10 credits x 2 markets = 20 per game day, so a full
season (~165 game days) is ~3,300 credits.

Writes into backend/data/nba/nba_game_odds.parquet in the same shape ESPN's
captures use; a line already captured pregame from ESPN is kept as is.

Usage:
  python backend/app/get_nba_odds_history.py --start 2025-10-21 --max-credits 5000
  python backend/app/get_nba_odds_history.py --start 2025-10-21 --dry-run
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from get_props import API_BASE, MIN_REMAINING, _api_key, _get  # noqa: E402

OUT = HERE.parent / "data" / "nba"
ODDS = OUT / "nba_game_odds.parquet"
STATS = OUT / "nba_player_stats.parquet"
SPORT = "basketball_nba"
SNAPSHOT_UTC = "16:00:00"
COST = 20                     # 10 x (spreads, totals) x 1 region

TEAMS = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN", "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET", "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC", "LA Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA", "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR", "Utah Jazz": "UTA", "Washington Wizards": "WAS",
}


def game_days(start: date, end: date) -> list:
    """Days that had games, from the box scores (so off days cost nothing)."""
    s = pd.read_parquet(STATS, columns=["GAME DATE"])
    d = pd.to_datetime(s["GAME DATE"]).dt.date
    return sorted(x for x in d.unique() if start <= x <= end)


def consensus(event: dict) -> dict:
    """Median spread and total across books for one game."""
    home = event.get("home_team")
    spreads, totals = [], []
    for b in event.get("bookmakers", []):
        for m in b.get("markets", []):
            for o in m.get("outcomes", []):
                if m.get("key") == "spreads" and o.get("name") == home and o.get("point") is not None:
                    spreads.append(float(o["point"]))
                if m.get("key") == "totals" and o.get("name") == "Over" and o.get("point") is not None:
                    totals.append(float(o["point"]))
    med = lambda xs: float(pd.Series(xs).median()) if xs else None  # noqa: E731
    return {"home_spread": med(spreads), "total": med(totals)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-10-21")
    ap.add_argument("--end", default=None, help="default: yesterday")
    ap.add_argument("--max-credits", type=int, default=5000)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    start = date.fromisoformat(a.start)
    end = date.fromisoformat(a.end) if a.end else date.today() - timedelta(days=1)

    old = pd.read_parquet(ODDS) if ODDS.exists() else pd.DataFrame()
    have = set()
    if len(old):
        have = set(pd.to_datetime(old["date"]).dt.date[old["total"].notna()])
    days = [d for d in game_days(start, end) if d not in have]
    print(f"{len(days)} game days without lines between {start} and {end}; ~{len(days) * COST:,} credits "
          f"(cap {a.max_credits:,})")
    if a.dry_run or not days:
        return 0

    key = _api_key()
    spent, rows = 0, []
    for d in days:
        if spent + COST > a.max_credits:
            print(f"stopped at the {a.max_credits:,}-credit cap")
            break
        r = _get(f"{API_BASE}/historical/sports/{SPORT}/odds",
                 {"api_key": key, "regions": "us", "markets": "spreads,totals", "oddsFormat": "american",
                  "dateFormat": "iso", "date": f"{d.isoformat()}T{SNAPSHOT_UTC}Z"})
        spent += int(float(r.headers.get("x-requests-last", COST) or COST))
        rem = r.headers.get("x-requests-remaining")
        if r.status_code != 200:
            print(f"  {d}: HTTP {r.status_code} {r.text[:120]}")
            continue
        n = 0
        for ev in r.json().get("data") or []:
            tip = pd.Timestamp(ev.get("commence_time"))
            if tip.tz_convert("America/New_York").date() != d:
                continue                                  # tomorrow's games show up too
            h, aw = TEAMS.get(ev.get("home_team")), TEAMS.get(ev.get("away_team"))
            if not h or not aw:
                continue
            c = consensus(ev)
            if c["total"] is None or c["home_spread"] is None:
                continue
            rows.append({"espn_game_id": None, "date": d.isoformat(), "home": h, "away": aw, **c,
                         "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         "state": "odds_api_history"})
            n += 1
        print(f"  {d}: {n} games (spent {spent:,})")
        if rem is not None and int(float(rem)) < MIN_REMAINING:
            print(f"account down to {rem} credits; stopping")
            break

    if rows:
        new = pd.DataFrame(rows)
        if len(old):
            # never overwrite a line ESPN captured before tip
            k = lambda df: df["date"].astype(str) + df["home"] + df["away"]  # noqa: E731
            new = new[~k(new).isin(set(k(old[old["total"].notna()])))]
            new = pd.concat([old, new], ignore_index=True)
        new.sort_values("date").to_parquet(ODDS, index=False)
        print(f"saved {len(rows)} games; file now has {len(new)}")
    print(f"done: {spent:,} credits")
    return 0


if __name__ == "__main__":
    sys.exit(main())
