"""NBA Injury Impact: who's ruled out, and which teammates it helps.

For every player on the current NBA injury report (get_injuries.py, ESPN,
refreshed every 15 min) who actually plays a role, compare each teammate's
games WITH him against games WITHOUT him -- the same (date, team) matching
the In/Out page uses -- and surface the teammates whose minutes, points,
rebounds, assists or shots move the most.

SEASON BASIS. This season first. A player who has missed only a game or two
(or none) this season doesn't give a usable "without" sample yet, so those
fall back to this season + last season combined, ON THE SAME TEAM only (the
date+team key means a traded player's old games never count). Every card says
which basis it used and how many games are on each side, because two
"without" games is a hint, not a finding.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, Optional

import pandas as pd

from datetime import datetime
from zoneinfo import ZoneInfo

from app.data.loader import get_injuries_data, get_nba_all_seasons, get_nba_schedule, nba_current_season

ET = ZoneInfo("America/New_York")

STATS = ["min", "pts", "reb", "ast", "fga", "pra"]
STAT_LABELS = {"min": "Minutes", "pts": "Points", "reb": "Rebounds", "ast": "Assists",
               "fga": "Shot attempts", "pra": "Pts+Reb+Ast"}

MIN_ROLE_MINUTES = 18      # injured player's average when he plays -- below this, his absence barely moves anyone
MIN_WITH = 3               # teammate games alongside him
MIN_WITHOUT = 2            # teammate games without him
TOP_N = 5

# A move worth flagging, per stat (teammate average, without minus with)
FLAG_AT = {"min": 4.0, "pts": 4.0, "reb": 2.5, "ast": 2.0, "fga": 3.0, "pra": 5.0}

TEAM_CODES = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN", "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET", "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "LA Clippers": "LAC", "Los Angeles Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA", "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR", "Utah Jazz": "UTA", "Washington Wizards": "WAS",
}

STATUS_ORDER = {"Out": 0, "Doubtful": 1, "Questionable": 2, "Day-To-Day": 3, "Probable": 4}


def match_key(name: str) -> str:
    """Accent/punctuation/suffix-insensitive: 'Mikel Brown Jr.' == 'Mikel Brown'."""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r"[.'’]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return " ".join(s.split())


def _season_label(season: int) -> str:
    return f"{season - 1}-{str(season)[-2:]}"


def _prep(stats: pd.DataFrame) -> pd.DataFrame:
    df = stats.copy()
    if "played" in df.columns:
        df = df[pd.to_numeric(df["played"], errors="coerce") == 1]
    date_col = "date" if "date" in df.columns else "game_date"
    df["_date"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
    df["_k"] = df["player"].map(match_key)
    for c in STATS:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["_date"])


def _impact_for(df: pd.DataFrame, inj_key: str, team: str) -> Optional[Dict[str, Any]]:
    """With/without for every teammate of one injured player, on one team."""
    team_df = df[df["team"] == team]
    mine = team_df[team_df["_k"] == inj_key]
    if mine.empty:
        return None
    his_games = set(mine["_date"])
    role = {"games": int(len(mine)),
            "min": round(float(mine["min"].mean()), 1) if "min" in mine else None,
            "pts": round(float(mine["pts"].mean()), 1) if "pts" in mine else None}

    mates = team_df[team_df["_k"] != inj_key].copy()
    mates["_with"] = mates["_date"].isin(his_games)
    rows = []
    stat_cols = [c for c in STATS if c in mates.columns]
    for name, g in mates.groupby("player"):
        w, wo = g[g["_with"]], g[~g["_with"]]
        if len(w) < MIN_WITH or len(wo) < MIN_WITHOUT:
            continue
        mw, mwo = w[stat_cols].mean(), wo[stat_cols].mean()
        deltas = {c: round(float(mwo[c] - mw[c]), 1) for c in stat_cols}
        rows.append({
            "player": name,
            "games_with": int(len(w)), "games_without": int(len(wo)),
            "with": {c: round(float(mw[c]), 1) for c in stat_cols},
            "without": {c: round(float(mwo[c]), 1) for c in stat_cols},
            "delta": deltas,
            "flags": [c for c in stat_cols if deltas[c] >= FLAG_AT.get(c, 99)],
        })
    return {"role": role, "teammates": rows}


def get_injury_impact(team: Optional[str] = None, include_day_to_day: bool = True) -> Dict[str, Any]:
    inj = get_injuries_data("nba")
    empty = {"season": None, "updated_at": None, "players": []}
    if inj is None or inj.empty:
        return empty
    stats = get_nba_all_seasons()
    if stats.empty:
        return empty
    cur = nba_current_season(stats)
    df = _prep(stats)
    df_cur = df[df["season"] == cur] if cur else df

    inj = inj.copy()
    inj["code"] = inj["team"].map(TEAM_CODES).fillna(inj["team"])
    if team:
        inj = inj[inj["code"] == team.upper()]
    if not include_day_to_day:
        inj = inj[inj["status"].isin(["Out", "Doubtful"])]

    # each team's next game (today or later), so cards can say "tonight vs BOS"
    next_game: Dict[str, Dict[str, Any]] = {}
    try:
        sched = get_nba_schedule()
        today = datetime.now(ET).date().isoformat()
        if sched is not None and not sched.empty:
            up = sched[(sched["date"] >= today) & (sched["state"] != "post")].sort_values("start_utc")
            for g in up.itertuples():
                for me, opp, home in ((g.home, g.away, True), (g.away, g.home, False)):
                    next_game.setdefault(me, {"date": g.date, "opponent": opp, "home": home,
                                              "start_utc": g.start_utc, "today": g.date == today})
    except Exception:
        pass

    cards = []
    for r in inj.to_dict("records"):
        k = match_key(r["player"])
        basis = "current"
        imp = _impact_for(df_cur, k, r["code"])
        # Not enough "without" games this season for anyone -> widen to both seasons
        if imp is None or not imp["teammates"]:
            wide = _impact_for(df, k, r["code"])
            if wide and wide["teammates"]:
                imp, basis = wide, "both"
        if imp is None or not imp["teammates"]:
            continue
        if (imp["role"]["min"] or 0) < MIN_ROLE_MINUTES:
            continue

        mates = imp["teammates"]
        top_pts = sorted(mates, key=lambda m: -m["delta"].get("pts", 0))[:TOP_N]
        top_min = sorted(mates, key=lambda m: -m["delta"].get("min", 0))[:TOP_N]
        seen, beneficiaries = set(), []
        for m in top_pts + top_min:
            if m["player"] not in seen and (m["delta"].get("pts", 0) > 0 or m["delta"].get("min", 0) > 0):
                seen.add(m["player"])
                beneficiaries.append(m)
        beneficiaries.sort(key=lambda m: (-len(m["flags"]), -m["delta"].get("pts", 0)))
        cards.append({
            "player": r["player"],
            "team": r["code"],
            "status": r.get("status"),
            "detail": r.get("detail"),
            "updated": r.get("source_updated"),
            "role": imp["role"],
            "next_game": next_game.get(r["code"]),
            # Others out on the same team: their absences overlap with his, so
            # the "without" games partly measure them too.
            "also_out": sorted(p for p in inj[(inj["code"] == r["code"]) & (inj["status"] == "Out")]["player"]
                               if p != r["player"]),
            "basis": basis,
            "basis_label": (_season_label(cur) if basis == "current" and cur
                            else f"{_season_label(cur - 1)} + {_season_label(cur)}" if cur else None),
            "flag_count": sum(len(m["flags"]) for m in beneficiaries),
            "beneficiaries": beneficiaries[:6],
        })

    # Out before day-to-day, then the players whose absence matters most
    # Teams playing today first, then Out before day-to-day, then the players
    # whose absence matters most
    cards.sort(key=lambda c: (not (c["next_game"] or {}).get("today", False),
                              STATUS_ORDER.get(c["status"], 5), -(c["role"]["min"] or 0)))
    upd = inj["source_updated"].dropna().astype(str).max() if "source_updated" in inj.columns and inj["source_updated"].notna().any() else None
    return {"season": _season_label(cur) if cur else None, "updated_at": upd,
            "stat_labels": STAT_LABELS, "players": cards}
