"""Thin client + parsers for the NHL's public (undocumented) web API.

    api-web.nhle.com/v1          schedule, boxscore, play-by-play, rosters
    api.nhle.com/stats/rest/en   shift charts

LICENSING: these endpoints are free but sit under NHL.com's terms, which do
not grant commercial rights. They are fine for building and a free beta; swap
the fetch_* functions for a licensed feed before NHL pages go behind a
paywall. Everything downstream only sees the parsed shapes returned here, so
that swap stays inside this file.

The API is unofficial, so every parser reads with .get() and skips what it
can't understand rather than failing the run -- the same stance as
get_injuries.py's ESPN parser.
"""

from __future__ import annotations

import time
from datetime import date
from typing import Any, Dict, List, Optional

import requests

WEB = "https://api-web.nhle.com/v1"
STATS = "https://api.nhle.com/stats/rest/en"
HEADERS = {"User-Agent": "Mozilla/5.0 (sports-analytics data pipeline)", "Accept": "application/json"}
PAUSE = 0.12      # seconds between requests -- be a polite client
TIMEOUT = 30

_session = requests.Session()
_session.headers.update(HEADERS)


def get_json(url: str, retries: int = 3) -> Optional[Any]:
    """GET a JSON document. None on 404 (a game with no shift chart, a team
    with no schedule yet); raises after `retries` on anything else."""
    last: Optional[Exception] = None
    for attempt in range(retries):
        try:
            r = _session.get(url, timeout=TIMEOUT)
            time.sleep(PAUSE)
            if r.status_code == 404:
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"{r.status_code} for {url}")
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001 -- retried, then re-raised
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed after {retries} tries: {url}: {last}")


# ── helpers ────────────────────────────────────────────────────────────────

def season_for(d: date) -> int:
    """20262027 for any date from September 2026 through August 2027."""
    y = d.year if d.month >= 9 else d.year - 1
    return y * 10000 + (y + 1)


def mmss(s: Any) -> Optional[int]:
    """'19:42' -> 1182 seconds. Also accepts '1:02:03' and bare numbers."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return int(s)
    parts = str(s).strip().split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    total = 0
    for n in nums:
        total = total * 60 + n
    return total


def _txt(v: Any) -> Optional[str]:
    """The API wraps most strings as {"default": "..."}."""
    if isinstance(v, dict):
        return v.get("default")
    return v


# ── schedule ───────────────────────────────────────────────────────────────

def fetch_club_schedule(team: str, season: int) -> List[Dict[str, Any]]:
    data = get_json(f"{WEB}/club-schedule-season/{team}/{season}") or {}
    return [g for g in (parse_schedule_game(x) for x in data.get("games", []) or []) if g]


def parse_schedule_game(g: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        away, home = g.get("awayTeam") or {}, g.get("homeTeam") or {}
        out = g.get("gameOutcome") or {}
        return {
            "game_id": int(g["id"]),
            "season": int(g.get("season") or 0),
            "game_type": int(g.get("gameType") or 0),
            "date": g.get("gameDate") or (g.get("startTimeUTC") or "")[:10],
            "start_utc": g.get("startTimeUTC"),
            "away": away.get("abbrev"),
            "home": home.get("abbrev"),
            "away_score": away.get("score"),
            "home_score": home.get("score"),
            "state": g.get("gameState"),
            "last_period": out.get("lastPeriodType"),
            "venue": _txt(g.get("venue")),
            "neutral": bool(g.get("neutralSite", False)),
        }
    except (KeyError, TypeError, ValueError):
        return None


FINAL_STATES = {"OFF", "FINAL"}
STARTED_STATES = {"LIVE", "CRIT", "OFF", "FINAL"}


# ── game documents ─────────────────────────────────────────────────────────

def fetch_boxscore(game_id: int) -> Optional[Dict[str, Any]]:
    return get_json(f"{WEB}/gamecenter/{game_id}/boxscore")


def fetch_pbp(game_id: int) -> Optional[Dict[str, Any]]:
    return get_json(f"{WEB}/gamecenter/{game_id}/play-by-play")


def fetch_shifts(game_id: int) -> List[Dict[str, Any]]:
    data = get_json(f"{STATS}/shiftcharts?cayenneExp=gameId={game_id}") or {}
    return data.get("data", []) or []


def fetch_roster(team: str) -> Dict[str, Any]:
    return get_json(f"{WEB}/roster/{team}/current") or {}


def parse_roster(team: str, data: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = []
    for grp in ("forwards", "defensemen", "goalies"):
        for p in data.get(grp, []) or []:
            pid = p.get("id")
            if pid is None:
                continue
            name = f"{_txt(p.get('firstName')) or ''} {_txt(p.get('lastName')) or ''}".strip()
            rows.append({"player_id": int(pid), "player": name, "team": team,
                         "pos": p.get("positionCode") or ("G" if grp == "goalies" else "D" if grp == "defensemen" else "F")})
    return rows


def parse_boxscore(bx: Dict[str, Any]) -> Dict[str, Any]:
    """{"away": abbrev, "home": abbrev, "skaters": [...], "goalies": [...]}.

    Skater and goalie rows carry the team abbrev and the raw box numbers.
    Names here are abbreviated ("S. Reinhart"); the play-by-play roster has
    full names and is preferred by the caller.
    """
    away = (bx.get("awayTeam") or {}).get("abbrev")
    home = (bx.get("homeTeam") or {}).get("abbrev")
    pbg = bx.get("playerByGameStats") or {}
    skaters: List[Dict[str, Any]] = []
    goalies: List[Dict[str, Any]] = []
    for side, team in (("awayTeam", away), ("homeTeam", home)):
        grp = pbg.get(side) or {}
        for key in ("forwards", "defense"):
            for p in grp.get(key, []) or []:
                if p.get("playerId") is None:
                    continue
                skaters.append({
                    "player_id": int(p["playerId"]), "team": team,
                    "name_short": _txt(p.get("name")), "pos": p.get("position"),
                    "goals": int(p.get("goals") or 0), "assists": int(p.get("assists") or 0),
                    "pim": int(p.get("pim") or p.get("penaltyMinutes") or 0),
                    "hits": int(p.get("hits") or 0),
                    "blocks": int(p.get("blockedShots") or p.get("blocks") or 0),
                    "sog": int(p.get("sog") if p.get("sog") is not None else (p.get("shots") or 0)),
                    "pp_goals": int(p.get("powerPlayGoals") or 0),
                    "toi": mmss(p.get("toi")) or 0,
                    "shifts": int(p.get("shifts") or 0),
                    "plus_minus": int(p.get("plusMinus") or 0),
                })
        for p in grp.get("goalies", []) or []:
            if p.get("playerId") is None:
                continue
            toi = mmss(p.get("toi")) or 0
            sa, sv = p.get("shotsAgainst"), p.get("saves")
            if (sa is None or sv is None) and p.get("saveShotsAgainst"):
                try:
                    sv, sa = (int(x) for x in str(p["saveShotsAgainst"]).split("/"))
                except ValueError:
                    pass
            goalies.append({
                "player_id": int(p["playerId"]), "team": team,
                "name_short": _txt(p.get("name")), "toi": toi,
                "starter": bool(p.get("starter", False)),
                "decision": p.get("decision"),
                "shots_against": int(sa or 0), "saves": int(sv or 0),
                "goals_against": int(p.get("goalsAgainst") or 0),
            })
    return {"away": away, "home": home, "skaters": skaters, "goalies": goalies}


def parse_pbp(pbp: Dict[str, Any]) -> Dict[str, Any]:
    """Team ids/abbrevs, a player roster and a flat, time-ordered event list.

    Each event: type, period, period_type, sec (game seconds from opening
    faceoff), situation (4-char string or None), owner (team abbrev or None),
    defending_side (home team's side, 'left'/'right'/None) and the raw
    details dict. Shootout events are dropped: they aren't hockey for stats.
    """
    home_t, away_t = pbp.get("homeTeam") or {}, pbp.get("awayTeam") or {}
    team_by_id = {home_t.get("id"): home_t.get("abbrev"), away_t.get("id"): away_t.get("abbrev")}
    roster: Dict[int, Dict[str, Any]] = {}
    for r in pbp.get("rosterSpots", []) or []:
        pid = r.get("playerId")
        if pid is None:
            continue
        roster[int(pid)] = {
            "name": f"{_txt(r.get('firstName')) or ''} {_txt(r.get('lastName')) or ''}".strip(),
            "team": team_by_id.get(r.get("teamId")),
            "pos": r.get("positionCode"),
        }
    events = []
    for p in pbp.get("plays", []) or []:
        pd_ = p.get("periodDescriptor") or {}
        period = int(pd_.get("number") or p.get("period") or 0)
        ptype = pd_.get("periodType") or ("SO" if period >= 5 and pbp.get("gameType") == 2 else "REG")
        if ptype == "SO" or period <= 0:
            continue
        t = mmss(p.get("timeInPeriod"))
        if t is None:
            continue
        sit = p.get("situationCode")
        events.append({
            "type": p.get("typeDescKey"),
            "period": period,
            "period_type": ptype,
            "sec": (period - 1) * 1200 + t,
            "sort": p.get("sortOrder") or 0,
            "situation": str(sit).zfill(4) if sit not in (None, "") else None,
            "owner": team_by_id.get((p.get("details") or {}).get("eventOwnerTeamId")),
            "defending_side": p.get("homeTeamDefendingSide"),
            "details": p.get("details") or {},
        })
    events.sort(key=lambda e: (e["sec"], e["sort"]))
    return {
        "home": home_t.get("abbrev"), "away": away_t.get("abbrev"),
        "roster": roster, "events": events,
    }


def parse_shifts(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Real shifts only (the feed mixes in goal markers with no duration)."""
    out = []
    for r in rows:
        if r.get("duration") in (None, "") or r.get("playerId") is None:
            continue
        code = r.get("typeCode")
        if code not in (None, 517):
            continue
        period = int(r.get("period") or 0)
        s, e = mmss(r.get("startTime")), mmss(r.get("endTime"))
        if period <= 0 or s is None or e is None or e <= s or period > 7:
            continue
        base = (period - 1) * 1200
        out.append({"player_id": int(r["playerId"]), "team": r.get("teamAbbrev"),
                    "start": base + s, "end": base + e})
    return out
