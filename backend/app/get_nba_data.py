"""Daily NBA data pull: player box scores + the upcoming schedule.

SOURCES (free, no API key)
  Box scores  sportsdataverse / hoopR NBA data -- ESPN box scores republished
              as one parquet file per season on GitHub releases, refreshed
              daily during the season. File years are the year a season ENDS
              (player_box_2027 = the 2026-27 season).
  Schedule    ESPN's public scoreboard feed, one request per day for the next
              two weeks. hoopR's schedule files only cover finished seasons.

  Both are ESPN data: fine for the free beta, revisit before charging (same
  situation as the NHL pages).

INCREMENTAL BY SEASON
  Last season never changes, so its raw file is kept in the data-nba release
  (nba_box_raw_<year>.parquet) and only downloaded if missing. The current
  season's file is small and cumulative, so it is re-downloaded every run.

OUTPUTS (backend/data/nba/, published to the data-nba release)
  nba_player_stats.parquet   One row per player per game played, in the same
                             columns as the old NBA_Player_Stats.parquet so the
                             existing pages read it unchanged (plus a few
                             extras: SEASON TYPE, STARTER, PLAYER ID).
  nba_schedule.parquet       Games from yesterday through the next 14 days:
                             date, tip time, status, teams, scores.
  nba_box_raw_<year>.parquet Cached raw season files (see above).
  nba_game_odds.parquet      Pregame total + spread per game (ESPN), kept
                             forever -- the Vegas inputs for the projection model.
  nba_meta.json              When it ran and what it did.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "data" / "nba"
ET = ZoneInfo("America/New_York")

BOX_URL = ("https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"
           "espn_nba_player_boxscores/player_box_{year}.parquet")
SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
SCHEDULE_DAYS_AHEAD = 14

# ESPN season types: 1 preseason, 2 regular season, 3 playoffs, 5 play-in.
SEASON_TYPES = {2: "Regular", 3: "Playoffs", 5: "Play-In"}

# ESPN codes -> the NBA.com codes the app already uses everywhere (props,
# injuries, the old stats file). All-Star teams aren't in here, so they drop.
TEAM_CODES = {
    "ATL": "ATL", "BKN": "BKN", "BOS": "BOS", "CHA": "CHA", "CHI": "CHI", "CLE": "CLE",
    "DAL": "DAL", "DEN": "DEN", "DET": "DET", "GS": "GSW", "HOU": "HOU", "IND": "IND",
    "LAC": "LAC", "LAL": "LAL", "MEM": "MEM", "MIA": "MIA", "MIL": "MIL", "MIN": "MIN",
    "NO": "NOP", "NY": "NYK", "OKC": "OKC", "ORL": "ORL", "PHI": "PHI", "PHX": "PHX",
    "POR": "POR", "SA": "SAS", "SAC": "SAC", "TOR": "TOR", "UTAH": "UTA", "WSH": "WAS",
}

HEADERS = {"User-Agent": "Mozilla/5.0 (sports-analytics data pipeline)"}


# ── helpers ────────────────────────────────────────────────────────────────

def season_for(d: date) -> int:
    """ESPN/hoopR season year = the year the season ends (Oct 2026 -> 2027)."""
    return d.year + 1 if d.month >= 8 else d.year


def today_et() -> date:
    return datetime.now(ET).date()


def _get(url: str, params: Optional[dict] = None, tries: int = 3) -> requests.Response:
    last: Exception = RuntimeError("no attempts")
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=60)
            if r.status_code == 404:
                return r
            r.raise_for_status()
            return r
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 * (i + 1))
    raise last


def fetch_season_box(year: int) -> pd.DataFrame:
    """One hoopR season file, or an empty frame if it isn't published yet."""
    r = _get(BOX_URL.format(year=year))
    if r.status_code == 404:
        print(f"  player_box_{year}: not published yet")
        return pd.DataFrame()
    return pd.read_parquet(io.BytesIO(r.content))


# ── box scores -> the app's stats table ────────────────────────────────────

def transform_box(raw: pd.DataFrame) -> pd.DataFrame:
    """hoopR rows -> the old NBA_Player_Stats.parquet columns (played games only)."""
    if raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    df = df[df["season_type"].isin(SEASON_TYPES)]
    df["TEAM"] = df["team_abbreviation"].map(TEAM_CODES)
    df["Opponent"] = df["opponent_team_abbreviation"].map(TEAM_CODES)
    df = df[df["TEAM"].notna() & df["Opponent"].notna()]          # drops All-Star teams

    mins = pd.to_numeric(df["minutes"], errors="coerce")
    dnp = df["did_not_play"].fillna(False).astype(bool)
    df = df[~dnp & mins.notna() & (mins > 0)].copy()
    if df.empty:
        return pd.DataFrame()

    num = lambda c: pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)  # noqa: E731
    gdate = pd.to_datetime(df["game_date"]).dt.normalize()
    home = df["home_away"].astype(str).str.lower().eq("home")

    out = pd.DataFrame({
        "PLAYER": df["athlete_display_name"].astype(str),
        "TEAM": df["TEAM"],
        "Opponent": df["Opponent"],
        "MATCH UP": np.where(home, df["TEAM"] + " vs. " + df["Opponent"], df["TEAM"] + " @ " + df["Opponent"]),
        "GAME DATE": gdate,
        "W/L": np.where(df["team_winner"].fillna(False).astype(bool), "W", "L"),
        "MIN": pd.to_numeric(df["minutes"], errors="coerce").round().astype(int),
        "PTS": num("points"),
        "FGM": num("field_goals_made"),
        "FGA": num("field_goals_attempted"),
        "3PM": num("three_point_field_goals_made"),
        "3PA": num("three_point_field_goals_attempted"),
        "FTM": num("free_throws_made"),
        "FTA": num("free_throws_attempted"),
        "OREB": num("offensive_rebounds"),
        "DREB": num("defensive_rebounds"),
        "REB": num("rebounds"),
        "AST": num("assists"),
        "STL": num("steals"),
        "BLK": num("blocks"),
        "TOV": num("turnovers"),
        "PF": num("fouls"),
        "+/-": num("plus_minus"),
    })
    for made, att, pct in (("FGM", "FGA", "FG%"), ("3PM", "3PA", "3P%"), ("FTM", "FTA", "FT%")):
        out[pct] = (out[made] / out[att].replace(0, np.nan)).round(3)

    # FanDuel scoring -- matches the old file's FP column
    out["FP"] = (out["PTS"] + 1.2 * out["REB"] + 1.5 * out["AST"] + 3 * out["STL"]
                 + 3 * out["BLK"] - out["TOV"]).round(1)
    out["Played"] = 1
    out["Date"] = gdate
    out["GameID"] = out["TEAM"] + "_" + gdate.dt.strftime("%Y-%m-%d")
    tens = (out[["PTS", "REB", "AST", "STL", "BLK"]] >= 10).sum(axis=1)
    out["DblDbl"] = (tens >= 2).astype(int)
    out["TrplDbl"] = (tens >= 3).astype(int)
    out["Location"] = np.where(home, "Home", "Away")
    out["Season"] = df["season"].astype(int).values
    out["BLK_STL"] = out["BLK"] + out["STL"]
    out["PRA"] = out["PTS"] + out["REB"] + out["AST"]
    out["REB_AST"] = out["REB"] + out["AST"]
    out["PTS_AST"] = out["PTS"] + out["AST"]
    out["PTS_REB"] = out["PTS"] + out["REB"]
    # extras the old file didn't have
    out["SEASON TYPE"] = df["season_type"].map(SEASON_TYPES).values
    out["STARTER"] = df["starter"].fillna(False).astype(bool).astype(int).values
    out["PLAYER ID"] = pd.to_numeric(df["athlete_id"], errors="coerce").astype("Int64").values
    out["ESPN GAME ID"] = df["game_id"].astype("int64").values
    return out.reset_index(drop=True)


def add_schedule_flags(stats: pd.DataFrame) -> pd.DataFrame:
    """back_to_back / third_in_four, from each TEAM's game dates (all seasons
    kept separate so opening night is never a back-to-back)."""
    if stats.empty:
        stats["back_to_back"] = []
        stats["third_in_four"] = []
        return stats
    tg = stats[["TEAM", "Season", "Date"]].drop_duplicates().sort_values(["TEAM", "Season", "Date"])
    prev1 = tg.groupby(["TEAM", "Season"])["Date"].shift(1)
    prev2 = tg.groupby(["TEAM", "Season"])["Date"].shift(2)
    tg["back_to_back"] = ((tg["Date"] - prev1).dt.days == 1).astype(int)
    tg["third_in_four"] = ((tg["Date"] - prev2).dt.days <= 3).astype(int)
    return stats.merge(tg, on=["TEAM", "Season", "Date"], how="left")


# ── schedule ───────────────────────────────────────────────────────────────

def parse_scoreboard(doc: dict) -> List[dict]:
    rows = []
    for ev in doc.get("events", []) or []:
        comp = (ev.get("competitions") or [{}])[0]
        teams = {c.get("homeAway"): c for c in comp.get("competitors", []) or []}
        h, a = teams.get("home", {}), teams.get("away", {})
        hc = TEAM_CODES.get((h.get("team") or {}).get("abbreviation"))
        ac = TEAM_CODES.get((a.get("team") or {}).get("abbreviation"))
        if not hc or not ac:
            continue                                               # All-Star etc.
        status = (comp.get("status") or ev.get("status") or {}).get("type") or {}
        start = pd.to_datetime(ev.get("date"), utc=True, errors="coerce")
        stype = (ev.get("season") or {}).get("type")
        broadcasts = [n for b in comp.get("broadcasts", []) or [] for n in (b.get("names") or [])]

        def score(c):
            s = pd.to_numeric(c.get("score"), errors="coerce")
            return None if pd.isna(s) or status.get("state") == "pre" else int(s)

        total, home_spread = parse_odds(comp, h, a)
        rows.append({
            "espn_game_id": int(ev["id"]),
            "date": start.tz_convert(ET).date().isoformat() if pd.notna(start) else None,
            "start_utc": start.isoformat() if pd.notna(start) else None,
            "season": (ev.get("season") or {}).get("year"),
            "season_type": SEASON_TYPES.get(stype, str(stype) if stype is not None else None),
            "state": status.get("state"),                          # pre / in / post
            "status": status.get("shortDetail") or status.get("description"),
            "home": hc, "away": ac,
            "home_score": score(h), "away_score": score(a),
            "venue": (comp.get("venue") or {}).get("fullName"),
            "broadcast": ", ".join(broadcasts) or None,
            # ESPN's pregame line (provider varies): game total, and the HOME
            # team's spread (negative = home favored)
            "total": total, "home_spread": home_spread,
        })
    return rows


def parse_odds(comp: dict, home: dict, away: dict) -> tuple:
    """(total, home_spread) from a scoreboard competition's odds block, or
    (None, None). ESPN gives `overUnder` and a `details` string like
    "NYK -4.5" (or "EVEN"); the favourite is named, so the sign is read from
    which team that is rather than trusting a bare `spread` field whose sign
    convention has varied."""
    odds = (comp.get("odds") or [None])[0] or {}
    total = pd.to_numeric(odds.get("overUnder"), errors="coerce")
    total = float(total) if pd.notna(total) and total > 150 else None
    details = str(odds.get("details") or "").strip()
    home_spread = None
    if details.upper() in ("EVEN", "PK", "PICK"):
        home_spread = 0.0
    else:
        m = re.match(r"^([A-Za-z]+)\s*([-+]?\d+(?:\.\d+)?)$", details)
        if m:
            fav = TEAM_CODES.get(m.group(1).upper(), m.group(1).upper())
            pts = abs(float(m.group(2)))
            hc = TEAM_CODES.get((home.get("team") or {}).get("abbreviation"))
            ac = TEAM_CODES.get((away.get("team") or {}).get("abbreviation"))
            if fav == hc:
                home_spread = -pts
            elif fav == ac:
                home_spread = pts
    return total, home_spread


def update_odds_history(sched: pd.DataFrame, path: Path) -> pd.DataFrame:
    """Keep every game's pregame line: ESPN shows it until tip, so the last
    capture while state == 'pre' wins; games already final keep whatever was
    stored (or what ESPN still shows, for a backfill)."""
    cols = ["espn_game_id", "date", "home", "away", "total", "home_spread", "captured_at", "state"]
    new = sched.dropna(subset=["total"]).copy() if "total" in sched.columns else pd.DataFrame(columns=cols)
    if new.empty and path.exists():
        return pd.read_parquet(path)
    new["captured_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new = new[[c for c in cols if c in new.columns]]
    if path.exists():
        old = pd.read_parquet(path)
        # a pre-game capture replaces anything older; a post-game one only fills gaps
        pre = new[new["state"] == "pre"]
        post = new[(new["state"] != "pre") & ~new["espn_game_id"].isin(old["espn_game_id"])]
        new = pd.concat([old[~old["espn_game_id"].isin(pre["espn_game_id"])], pre, post], ignore_index=True)
    new = new.drop_duplicates("espn_game_id", keep="last").sort_values("date").reset_index(drop=True)
    new.to_parquet(path, index=False)
    return new


def fetch_schedule(start: date, days: int) -> pd.DataFrame:
    rows: List[dict] = []
    for i in range(days + 1):
        d = start + timedelta(days=i)
        try:
            r = _get(SCOREBOARD_URL, params={"dates": d.strftime("%Y%m%d"), "limit": 50})
            rows.extend(parse_scoreboard(r.json()))
        except Exception as e:  # noqa: BLE001
            print(f"  schedule {d}: {e}")
    df = pd.DataFrame(rows)
    return df.drop_duplicates("espn_game_id").sort_values(["date", "start_utc"]).reset_index(drop=True) if not df.empty else df


# ── main ───────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-prior", action="store_true",
                    help="re-download last season even if it's already cached")
    ap.add_argument("--backfill-odds", action="store_true",
                    help="also fetch ESPN's pregame lines for every past game day (one-off)")
    args = ap.parse_args()

    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    today = today_et()
    cur = season_for(today)
    seasons = [cur - 1, cur]
    print(f"NBA update {today} -- seasons {seasons}")

    frames = []
    for year in seasons:
        cache = OUT / f"nba_box_raw_{year}.parquet"
        if year < cur and cache.exists() and not args.refresh_prior:
            raw = pd.read_parquet(cache)
            print(f"  {year}: cached ({len(raw):,} rows)")
        else:
            raw = fetch_season_box(year)
            if not raw.empty:
                raw.to_parquet(cache, index=False)
            print(f"  {year}: downloaded ({len(raw):,} rows)")
        frames.append(transform_box(raw))

    stats = pd.concat([f for f in frames if not f.empty], ignore_index=True) if any(not f.empty for f in frames) else pd.DataFrame()
    if stats.empty:
        print("ERROR: no box score rows -- leaving the published file alone")
        return 1
    stats = add_schedule_flags(stats).sort_values(["Date", "TEAM", "PLAYER"], ascending=[False, True, True])
    stats.to_parquet(OUT / "nba_player_stats.parquet", index=False)
    latest = stats["Date"].max().date().isoformat()
    print(f"  stats: {len(stats):,} player-games, latest {latest}")

    sched = fetch_schedule(today - timedelta(days=1), SCHEDULE_DAYS_AHEAD + 1)
    if args.backfill_odds:
        # one-off: every game day since last season's opener, for the model's
        # Vegas features. ~260 small requests.
        first = date(cur - 2, 10, 1)
        hist = fetch_schedule(first, (today - first).days)
        o = update_odds_history(hist, OUT / "nba_game_odds.parquet")
        print(f"  odds backfill: {int(hist['total'].notna().sum()) if 'total' in hist else 0} of {len(hist)} past games had a line")
    if not sched.empty:
        odds = update_odds_history(sched, OUT / "nba_game_odds.parquet")
        print(f"  odds history: {len(odds)} games with a pregame line")
        sched.to_parquet(OUT / "nba_schedule.parquet", index=False)
        print(f"  schedule: {len(sched)} games, {sched['date'].min()} to {sched['date'].max()}")
    else:
        print("  schedule: nothing fetched -- keeping the previous file")

    (OUT / "nba_meta.json").write_text(json.dumps({
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "seasons": seasons,
        "player_games": int(len(stats)),
        "latest_game_date": latest,
        "schedule_games": int(len(sched)),
    }, indent=1))
    print(f"done in {time.time() - started:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
