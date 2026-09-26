"""Current injury statuses for NFL, NBA and MLB, plus a log of every change.

    python backend/app/get_injuries.py --sport nfl
    python backend/app/get_injuries.py --sport nba
    python backend/app/get_injuries.py --sport mlb

Runs every 15 minutes from update_injuries.yml. Free: no paid APIs.

SOURCES
-------
ESPN's public injuries feed (site.api.espn.com/.../injuries) for all three
sports. It is unofficial and undocumented, so the parser below is defensive:
anything it can't read is skipped, never fatal, and an empty or failed pull
leaves the previous file alone rather than wiping it (which would otherwise
log every player as "cleared").

NFL also merges nflverse's weekly injury report (the official Wed-Fri
practice report, with practice participation). ESPN is fresher on game day;
nflverse is the official record and carries the gsis_id that joins to the
usage data. When both have a player, ESPN's status wins if it's newer.

OUTPUTS (backend/data/<slug>/)
-------
<slug>_injuries.parquet         One row per currently listed player.
<slug>_injury_changes.parquet   Append-only: every status change we've seen,
                                with when we first noticed it. This is what
                                the Today page's injury cards are built from,
                                and `detected_at` is what "has the line moved
                                since?" is measured against.

A player dropping off the list entirely is logged as a change to "Active"
(cleared), which matters as much as a downgrade.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
DATA_ROOT = HERE.parent / "data"

ESPN_PATHS = {
    "nfl": "football/nfl",
    "nba": "basketball/nba",
    "mlb": "baseball/mlb",
}
NFLVERSE_URL = "https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_{season}.csv"
TIMEOUT = 30
CHANGE_RETAIN_DAYS = 45

COLS = ["sport", "player", "player_key", "team", "position", "status", "detail",
        "practice", "source_updated", "source", "gsis_id"]
CHANGE_COLS = ["sport", "player", "player_key", "team", "position", "old_status",
               "new_status", "detail", "detected_at", "gsis_id"]

# Normalized statuses, most serious first. Anything unrecognized keeps its
# own text rather than being forced into a bucket.
STATUS_MAP = {
    "out": "Out", "o": "Out", "injured reserve": "IR", "ir": "IR",
    "injured reserve - designated for return": "IR", "physically unable to perform": "PUP",
    "pup": "PUP", "suspension": "Suspended", "suspended": "Suspended",
    "doubtful": "Doubtful", "d": "Doubtful", "questionable": "Questionable", "q": "Questionable",
    "probable": "Probable", "day-to-day": "Day-To-Day", "day to day": "Day-To-Day",
    "10-day-il": "IL-10", "10-day il": "IL-10", "15-day-il": "IL-15", "15-day il": "IL-15",
    "60-day-il": "IL-60", "60-day il": "IL-60", "7-day-il": "IL-7", "7-day il": "IL-7",
    "active": "Active",
}

# nflverse team abbreviations -> the full names The Odds API (and so every
# props file) uses. Kept here rather than imported so this script runs on a
# bare GitHub runner with only pandas + requests.
NFL_TEAMS = {
    "ARI": "Arizona Cardinals", "ATL": "Atlanta Falcons", "BAL": "Baltimore Ravens",
    "BUF": "Buffalo Bills", "CAR": "Carolina Panthers", "CHI": "Chicago Bears",
    "CIN": "Cincinnati Bengals", "CLE": "Cleveland Browns", "DAL": "Dallas Cowboys",
    "DEN": "Denver Broncos", "DET": "Detroit Lions", "GB": "Green Bay Packers",
    "HOU": "Houston Texans", "IND": "Indianapolis Colts", "JAX": "Jacksonville Jaguars",
    "KC": "Kansas City Chiefs", "LA": "Los Angeles Rams", "LAR": "Los Angeles Rams",
    "LAC": "Los Angeles Chargers", "LV": "Las Vegas Raiders", "MIA": "Miami Dolphins",
    "MIN": "Minnesota Vikings", "NE": "New England Patriots", "NO": "New Orleans Saints",
    "NYG": "New York Giants", "NYJ": "New York Jets", "PHI": "Philadelphia Eagles",
    "PIT": "Pittsburgh Steelers", "SEA": "Seattle Seahawks", "SF": "San Francisco 49ers",
    "TB": "Tampa Bay Buccaneers", "TEN": "Tennessee Titans", "WAS": "Washington Commanders",
}


def player_key(name: Any) -> str:
    """Accent/case/punctuation-insensitive, suffix-free: 'Kenneth Walker III'
    and 'Kenneth Walker' match, as do 'José Ramírez' and 'Jose Ramirez'."""
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower().replace(".", "").replace("'", "")
    parts = [p for p in s.split() if p not in {"jr", "sr", "ii", "iii", "iv", "v"}]
    return " ".join(parts)


def normalize_status(raw: Any) -> Optional[str]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    s = str(raw).strip()
    if not s:
        return None
    return STATUS_MAP.get(s.lower(), s)


def parse_espn(payload: Dict[str, Any], sport: str) -> List[Dict[str, Any]]:
    """ESPN groups injuries by team: {"injuries": [{"displayName": team,
    "injuries": [{"status", "date", "shortComment", "athlete": {...},
    "details": {...}}]}]}. Every field is read with .get() -- a missing one
    skips that player, never the run."""
    rows: List[Dict[str, Any]] = []
    for team_block in payload.get("injuries", []) or []:
        team = team_block.get("displayName") or (team_block.get("team") or {}).get("displayName")
        for inj in team_block.get("injuries", []) or []:
            athlete = inj.get("athlete") or {}
            name = athlete.get("displayName") or athlete.get("fullName")
            status = normalize_status(inj.get("status")
                                      or (inj.get("type") or {}).get("description"))
            if not name or not status:
                continue
            details = inj.get("details") or {}
            detail = " ".join(str(x) for x in (details.get("type"), details.get("detail"),
                                               details.get("side")) if x) or inj.get("shortComment")
            pos = (athlete.get("position") or {}).get("abbreviation")
            rows.append({
                "sport": sport, "player": name, "player_key": player_key(name),
                "team": team or (athlete.get("team") or {}).get("displayName"),
                "position": pos, "status": status, "detail": detail,
                "practice": None, "source_updated": inj.get("date"),
                "source": "espn", "gsis_id": None,
            })
    return rows


def fetch_espn(sport: str) -> List[Dict[str, Any]]:
    url = f"https://site.api.espn.com/apis/site/v2/sports/{ESPN_PATHS[sport]}/injuries"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        return parse_espn(r.json(), sport)
    except Exception as e:  # unofficial feed: a failure is a skipped source, not a failed run
        print(f"  espn {sport}: {e}")
        return []


def parse_nflverse(df: pd.DataFrame) -> List[Dict[str, Any]]:
    """The latest week's report only. Rows with no game status (a full
    practice, no designation) are not injuries for betting purposes."""
    if df.empty or "week" not in df.columns:
        return []
    df = df[df["week"] == df["week"].max()]
    rows = []
    for r in df.to_dict(orient="records"):
        status = normalize_status(r.get("report_status"))
        if not status:
            continue
        name = r.get("full_name") or f"{r.get('first_name', '')} {r.get('last_name', '')}".strip()
        detail = ", ".join(str(x) for x in (r.get("report_primary_injury"),
                                           r.get("report_secondary_injury"))
                           if isinstance(x, str) and x)
        rows.append({
            "sport": "nfl", "player": name, "player_key": player_key(name),
            "team": NFL_TEAMS.get(str(r.get("team")), r.get("team")),
            "position": r.get("position"), "status": status, "detail": detail or None,
            "practice": r.get("practice_status") if isinstance(r.get("practice_status"), str) else None,
            "source_updated": None, "source": "nflverse", "gsis_id": r.get("gsis_id"),
        })
    return rows


def fetch_nflverse(season: int) -> List[Dict[str, Any]]:
    try:
        df = pd.read_csv(NFLVERSE_URL.format(season=season))
        return parse_nflverse(df)
    except Exception as e:
        print(f"  nflverse {season}: {e}")
        return []


def merge_sources(espn: List[Dict[str, Any]], nflverse: List[Dict[str, Any]]) -> pd.DataFrame:
    """One row per (player_key, team). ESPN's status wins (fresher on game
    day); nflverse contributes the gsis_id and practice participation, and
    covers anyone ESPN doesn't list."""
    by_key: Dict[tuple, Dict[str, Any]] = {}
    for r in nflverse:
        by_key[(r["player_key"], r["team"])] = dict(r)
    for r in espn:
        k = (r["player_key"], r["team"])
        if k in by_key:
            base = by_key[k]
            base.update({kk: v for kk, v in r.items() if v is not None and kk not in ("gsis_id", "practice")})
            base["source"] = "espn+nflverse"
        else:
            by_key[k] = dict(r)
    df = pd.DataFrame(list(by_key.values()), columns=COLS)
    return df


def diff_statuses(previous: pd.DataFrame, current: pd.DataFrame, now_iso: str) -> pd.DataFrame:
    """Status changes between two snapshots, including players who appeared
    (old_status None) and players who dropped off (new_status 'Active')."""
    def index(df):
        if df.empty:
            return {}
        return {(r["player_key"], r["team"]): r for r in df.to_dict(orient="records")}

    prev, cur = index(previous), index(current)
    out = []
    for k, r in cur.items():
        old = prev.get(k, {}).get("status")
        if old != r["status"]:
            out.append({"sport": r["sport"], "player": r["player"], "player_key": r["player_key"],
                        "team": r["team"], "position": r.get("position"), "old_status": old,
                        "new_status": r["status"], "detail": r.get("detail"),
                        "detected_at": now_iso, "gsis_id": r.get("gsis_id")})
    for k, r in prev.items():
        if k not in cur:
            out.append({"sport": r["sport"], "player": r["player"], "player_key": r["player_key"],
                        "team": r["team"], "position": r.get("position"), "old_status": r["status"],
                        "new_status": "Active", "detail": None,
                        "detected_at": now_iso, "gsis_id": r.get("gsis_id")})
    return pd.DataFrame(out, columns=CHANGE_COLS)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", required=True, choices=sorted(ESPN_PATHS))
    args = ap.parse_args()
    sport = args.sport

    folder = DATA_ROOT / sport
    cur_path = folder / f"{sport}_injuries.parquet"
    log_path = folder / f"{sport}_injury_changes.parquet"
    now = pd.Timestamp.now(tz="UTC")

    espn = fetch_espn(sport)
    nflv = fetch_nflverse(now.year if now.month >= 3 else now.year - 1) if sport == "nfl" else []
    print(f"[{sport}] espn {len(espn)} rows, nflverse {len(nflv)} rows")
    if not espn and not nflv:
        print("nothing fetched; leaving the existing files alone")
        return 0

    current = merge_sources(espn, nflv) if sport == "nfl" else pd.DataFrame(espn, columns=COLS)
    current = current.drop_duplicates(subset=["player_key", "team"], keep="last")
    previous = pd.read_parquet(cur_path) if cur_path.exists() else pd.DataFrame(columns=COLS)
    log = pd.read_parquet(log_path) if log_path.exists() else pd.DataFrame(columns=CHANGE_COLS)

    # First run ever: record the baseline without logging hundreds of
    # "changes" that are really just the list we started from.
    changes = diff_statuses(previous, current, now.isoformat()) if not previous.empty \
        else pd.DataFrame(columns=CHANGE_COLS)

    # A source that silently dropped most of its rows would read as a mass
    # "cleared" event. Don't trust a pull that lost more than half the list.
    if not previous.empty and len(current) < 0.5 * len(previous):
        print(f"current list ({len(current)}) is under half the previous ({len(previous)}); "
              "treating as a partial pull and not logging clearances")
        changes = changes[changes["new_status"] != "Active"]
        current = pd.concat([current, previous[~previous.set_index(["player_key", "team"]).index
                                               .isin(current.set_index(["player_key", "team"]).index)]],
                            ignore_index=True)

    if not changes.empty:
        log = pd.concat([log, changes], ignore_index=True)
    cutoff = now - pd.Timedelta(days=CHANGE_RETAIN_DAYS)
    if not log.empty:
        log = log[pd.to_datetime(log["detected_at"], utc=True, errors="coerce") >= cutoff]

    folder.mkdir(parents=True, exist_ok=True)
    current.reset_index(drop=True).to_parquet(cur_path, index=False)
    log.reset_index(drop=True).to_parquet(log_path, index=False)
    print(f"[{sport}] {len(current)} listed, {len(changes)} changes this run, {len(log)} in log")
    return 0


if __name__ == "__main__":
    sys.exit(main())
