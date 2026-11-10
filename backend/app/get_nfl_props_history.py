"""One-off backfill: historical NFL player-prop lines from The Odds API.

Why: the projections page blends our number with the betting line, and how
much weight the line gets was tuned on the closing lines the site has saved
itself -- only since late September 2026. The Odds API keeps player-prop
history back to May 2023, so a few seasons of lines can be bought once and
reused for every retune.

What it buys: ONE snapshot per game, SNAPSHOT_MIN minutes before kickoff
(close enough to the closing line), for the chosen markets. Cost is 10
credits x markets x regions per game, plus 1 credit per kickoff slot to look
up the event ids -- e.g. 5 markets for a 285-game season is ~14,300.

Safety:
  * --max-credits is a hard stop: before every paid call the script checks
    that the call can't push the run past it. The API's own remaining-credit
    count is checked too (MIN_REMAINING, same as get_props.py).
  * Resumable: games already in the output file are skipped, so a run that
    stops at the cap picks up where it left off next time.
  * --dry-run prints the cost estimate and spends nothing.

Usage:
  python backend/app/get_nfl_props_history.py --season 2025 --markets core --max-credits 14000
  python backend/app/get_nfl_props_history.py --season 2024 --dry-run
"""
from __future__ import annotations

import argparse
import io
import sys
import urllib.request
from datetime import timedelta
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from get_props import (API_BASE, MIN_REMAINING, _api_key, _get, _region_equivalents,  # noqa: E402
                       _scope_params, to_over_under)
from props_config import NFL  # noqa: E402

OUT = HERE.parent / "data" / "nfl" / "nfl_props_history.parquet"
GAMES_URL = "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv"
SNAPSHOT_MIN = 30

MARKET_SETS = {
    # the markets the projections page prices as bets or near-bets
    "core": ("player_receptions", "player_reception_yds", "player_rush_attempts", "player_rush_yds",
             "player_rush_reception_yds"),
    "qb": ("player_pass_yds", "player_pass_attempts", "player_pass_completions", "player_pass_tds"),
    "td": ("player_anytime_td",),
}
MARKET_SETS["all"] = MARKET_SETS["core"] + MARKET_SETS["qb"] + MARKET_SETS["td"]

TEAMS = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens", "BUF": "Buffalo Bills",
    "CAR": "Carolina Panthers", "CHI": "Chicago Bears", "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns",
    "DAL": "Dallas Cowboys", "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars", "KC": "Kansas City Chiefs",
    "LA": "Los Angeles Rams", "LAC": "Los Angeles Chargers", "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints", "NYG": "New York Giants",
    "NYJ": "New York Jets", "PHI": "Philadelphia Eagles", "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks",
    "SF": "San Francisco 49ers", "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}


class OverBudget(RuntimeError):
    pass


def games_for(season: int) -> pd.DataFrame:
    raw = urllib.request.urlopen(urllib.request.Request(GAMES_URL, headers={"User-Agent": "sports-analytics"}), timeout=120).read()
    G = pd.read_csv(io.BytesIO(raw))
    G = G[(G.season == season) & G.result.notna()].copy()
    G["kickoff"] = [pd.Timestamp(f"{g.gameday} {g.gametime or '13:00'}").tz_localize("America/New_York").tz_convert("UTC")
                    for g in G.itertuples()]
    G["home_name"] = G.home_team.map(TEAMS)
    G["away_name"] = G.away_team.map(TEAMS)
    return G.sort_values("kickoff").reset_index(drop=True)


def iso(t: pd.Timestamp) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


class Meter:
    def __init__(self, cap: int):
        self.cap, self.spent = cap, 0

    def check(self, next_cost: int):
        if self.spent + next_cost > self.cap:
            raise OverBudget(f"next call ({next_cost}) would pass --max-credits {self.cap} (spent {self.spent})")

    def charge(self, r):
        c = r.headers.get("x-requests-last")
        self.spent += int(float(c)) if c is not None else 0
        rem = r.headers.get("x-requests-remaining")
        if rem is not None and int(float(rem)) < MIN_REMAINING:
            raise OverBudget(f"account has {rem} credits left (< {MIN_REMAINING}); stopping")


def events_at(key: str, when: pd.Timestamp, meter: Meter) -> list:
    meter.check(1)
    r = _get(f"{API_BASE}/historical/sports/{NFL.key}/events", {"api_key": key, "date": iso(when), "dateFormat": "iso"})
    meter.charge(r)
    if r.status_code != 200:
        print(f"  events {iso(when)}: HTTP {r.status_code} {r.text[:150]}")
        return []
    return r.json().get("data") or []


def odds_at(key: str, event_id: str, when: pd.Timestamp, markets: tuple, meter: Meter) -> tuple:
    meter.check(10 * len(markets) * _region_equivalents())
    r = _get(f"{API_BASE}/historical/sports/{NFL.key}/events/{event_id}/odds",
             {"api_key": key, **_scope_params(), "markets": ",".join(markets), "oddsFormat": "american",
              "dateFormat": "iso", "date": iso(when)})
    meter.charge(r)
    if r.status_code != 200:
        return None, r.status_code
    return r.json(), 200


def flatten(payload: dict) -> pd.DataFrame:
    ev = payload.get("data") or {}
    rows = [{"description": o.get("description"), "name": o.get("name"), "price": o.get("price"),
             "point": o.get("point"), "market": m.get("key"), "bookmakers": b.get("key")}
            for b in ev.get("bookmakers", []) for m in b.get("markets", []) for o in m.get("outcomes", [])]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["event_id"], df["commence_time"] = ev.get("id"), ev.get("commence_time")
    df["home_team"], df["away_team"] = ev.get("home_team"), ev.get("away_team")
    df = to_over_under(df, NFL)
    df["observed_at"] = payload.get("timestamp")
    return df


def save(new: list, old: pd.DataFrame):
    if not new:
        return old
    df = pd.concat([old] + new, ignore_index=True) if len(old) else pd.concat(new, ignore_index=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    return df


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--markets", default="core", choices=sorted(MARKET_SETS))
    ap.add_argument("--max-credits", type=int, default=14000)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.season < 2023:
        sys.exit("The Odds API keeps player-prop history from May 2023 -- 2023 is the earliest season.")
    markets = MARKET_SETS[a.markets]

    G = games_for(a.season)
    old = pd.read_parquet(OUT) if OUT.exists() else pd.DataFrame()
    done = set(old.game_id.dropna()) if "game_id" in old.columns else set()
    todo = G[~G.game_id.isin(done)]
    slots = todo.kickoff.nunique()
    per_game = 10 * len(markets) * _region_equivalents()
    est = len(todo) * per_game + slots
    print(f"{a.season}: {len(G)} games, {len(done & set(G.game_id))} already saved, {len(todo)} to fetch")
    print(f"markets ({a.markets}): {', '.join(m.replace('player_', '') for m in markets)}")
    print(f"estimate: {len(todo)} games x {per_game} + {slots} event lookups = ~{est:,} credits (cap {a.max_credits:,})")
    if a.dry_run or todo.empty:
        return 0

    key = _api_key()
    meter = Meter(a.max_credits)
    batch, saved, missing = [], 0, []
    try:
        for kick, slot in todo.groupby("kickoff", sort=True):
            snap = kick - timedelta(minutes=SNAPSHOT_MIN)
            evs = events_at(key, snap, meter)
            by_home = {(e.get("home_team"), e.get("away_team")): e for e in evs}
            for g in slot.itertuples():
                e = by_home.get((g.home_name, g.away_name)) or by_home.get((g.away_name, g.home_name))
                if not e:
                    missing.append(g.game_id)
                    print(f"  {g.game_id}: no matching event")
                    continue
                payload, code = odds_at(key, e["id"], snap, markets, meter)
                if payload is None:
                    print(f"  {g.game_id}: HTTP {code}")
                    continue
                df = flatten(payload)
                if df.empty:
                    df = pd.DataFrame([{"event_id": e["id"]}])     # remember it, so it's not bought twice
                df["game_id"], df["season"], df["week"] = g.game_id, g.season, g.week
                df["minutes_before_start"] = SNAPSHOT_MIN
                batch.append(df)
                saved += 1
                print(f"  {g.game_id}: {len(df)} lines (spent {meter.spent:,})")
                if len(batch) >= 15:                # save as we go: a stop loses nothing paid for
                    old = save(batch, old)
                    batch = []
    except OverBudget as e:
        print(f"stopped: {e}")
    old = save(batch, old)
    print(f"done: {saved} games saved this run, {meter.spent:,} credits spent"
          + (f"; {len(missing)} games had no event match" if missing else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
