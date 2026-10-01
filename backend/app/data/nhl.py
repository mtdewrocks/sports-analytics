"""NHL page payloads, built from the get_nhl_data.py parquet files.

Every public function here backs one route in routers/nhl.py and returns
plain JSON-able dicts. The heavy lifting (shift charts -> lines, xG, strength
states) already happened in the pipeline; this module only filters,
aggregates and ranks small tables.

Season choice: early in a season, numbers from 3-4 games are noise, so each
page falls back to LAST season until the current one has enough games
(MIN_GAMES) and says so (`fallback: true`) -- the same idea as the NFL
pages' "showing last season" banner.

Starting goalies are PROJECTED from each team's rotation (who has been
starting, back-to-backs) and only CONFIRMED once a game has started: the
free data has no morning-skate confirmations.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from app import nhl_teams
from app.data.loader import (
    get_injuries_data, get_nhl_games, get_nhl_goalie_games, get_nhl_meta, get_nhl_rosters,
    get_nhl_skater_games, get_nhl_team_games, get_nhl_unit_matchups, get_nhl_units, get_nhl_zones,
    ttl_cache,
)

MIN_GAMES = 5            # per team, before the current season is trusted
FINAL = {"OFF", "FINAL"}
STARTED = {"LIVE", "CRIT", "OFF", "FINAL"}

ZONE_LABELS = {
    "net_front": "Net front", "slot": "Slot", "high_slot": "High slot",
    "left_circle": "Left circle", "right_circle": "Right circle",
    "left_point": "Left point", "right_point": "Right point", "wide": "Wide / behind net",
}


# ── basics ─────────────────────────────────────────────────────────────────

def today_ct() -> date:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("America/Chicago")).date()
    except Exception:  # noqa: BLE001
        return (datetime.now(timezone.utc) - timedelta(hours=5)).date()


def season_for(d: date) -> int:
    y = d.year if d.month >= 9 else d.year - 1
    return y * 10000 + (y + 1)


def prior(season: int) -> int:
    y = season // 10000 - 1
    return y * 10000 + y + 1


def season_label(season: int) -> str:
    return f"{season // 10000}-{str(season % 10000)[2:]}"


def ordinal(n: Optional[int]) -> Optional[str]:
    if n is None or (isinstance(n, float) and np.isnan(n)):
        return None
    n = int(n)
    suf = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def mmss(sec: Any) -> Optional[str]:
    if sec is None or (isinstance(sec, float) and np.isnan(sec)):
        return None
    sec = int(sec)
    return f"{sec // 60}:{sec % 60:02d}"


def _f(x: Any, nd: int = 2) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(v) else round(v, nd)


def _plain(df: pd.DataFrame) -> pd.DataFrame:
    """Categories -> plain values, dates parsed. Done once per cache fill."""
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    for c in df.select_dtypes("category").columns:
        df[c] = df[c].astype(object)
    if "date" in df.columns:
        df["d"] = pd.to_datetime(df["date"], errors="coerce")
    return df


@ttl_cache(1800)
def _data() -> Dict[str, pd.DataFrame]:
    return {
        "games": _plain(get_nhl_games()),
        "teams": _plain(get_nhl_team_games()),
        "skaters": _plain(get_nhl_skater_games()),
        "goalies": _plain(get_nhl_goalie_games()),
        "units": _plain(get_nhl_units()),
        "matchups": _plain(get_nhl_unit_matchups()),
        "zones": _plain(get_nhl_zones()),
        "rosters": _plain(get_nhl_rosters()),
    }


def clear_cache() -> None:
    _data.cache_clear()
    _schedule_context.cache_clear()


def _clean(x: Any) -> Any:
    """NaN -> None and numpy scalars -> Python, recursively. Starlette's JSON
    encoder refuses NaN (allow_nan=False), and one stray NaN in a nested dict
    would otherwise 500 the whole page."""
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, np.generic):
        x = x.item()
    if isinstance(x, float) and (np.isnan(x) or np.isinf(x)):
        return None
    if x is pd.NaT:
        return None
    return x


def _public(fn):
    """Every route-backing function returns _clean()ed output."""
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **k):
        return _clean(fn(*a, **k))
    return wrapper


def _empty(msg: str = "NHL data isn't available yet -- the daily NHL update hasn't run.") -> dict:
    return {"error": msg}


def stats_season(tg: pd.DataFrame, on: Optional[date] = None) -> Tuple[int, bool]:
    """(season to use for team stats, whether that's a fallback to last season)."""
    cur = season_for(on or today_ct())
    reg = tg[(tg["season"] == cur) & (tg["game_type"] == 2)] if not tg.empty else tg
    if not reg.empty and reg.groupby("team").size().median() >= MIN_GAMES:
        return cur, False
    return prior(cur), True


# ── team tables ────────────────────────────────────────────────────────────

# key, label, higher-is-better, graded (colour the rank), format
METRICS = [
    ("Scoring", [
        ("gf_pg", "Goals per game", True, True, "2"),
        ("ga_pg", "Goals allowed per game", False, True, "2"),
    ]),
    ("Shot volume", [
        ("sf_pg", "Shots per game", True, True, "1"),
        ("sa_pg", "Shots allowed per game", False, True, "1"),
        ("cf5_pct", "5-on-5 shot attempt share", True, True, "%"),
        ("xgf5_pct", "5-on-5 expected goals share", True, True, "%"),
        ("hd_pg", "High-danger chances per game", True, True, "1"),
        ("hda_pg", "High-danger chances allowed per game", False, True, "1"),
    ]),
    ("Special teams", [
        ("pp_pct", "Power-play %", True, True, "%"),
        ("pk_pct", "Penalty-kill %", True, True, "%"),
        ("pp_opps_pg", "Power-play chances per game", True, True, "2"),
        ("times_sh_pg", "Times shorthanded per game", False, True, "2"),
    ]),
    ("First period", [
        ("p1_gf_pg", "First-period goals per game", True, True, "2"),
        ("p1_ga_pg", "First-period goals allowed", False, True, "2"),
    ]),
    ("Other", [
        ("fo_pct", "Faceoff win %", True, True, "%"),
        ("hits_pg", "Hits per game", True, False, "1"),
        ("blocks_pg", "Blocked shots per game", True, False, "1"),
    ]),
]
RANKED = {k: (hib, graded) for _, rows in METRICS for (k, _, hib, graded, _) in rows}
RANKED.update({"cf5_p60": (True, True), "sf_pg": (True, True)})


def team_table(season: int, last_n: Optional[int] = None) -> pd.DataFrame:
    tg = _data()["teams"]
    if tg.empty:
        return pd.DataFrame()
    df = tg[(tg["season"] == season) & (tg["game_type"] == 2)].sort_values("d")
    if df.empty:
        return pd.DataFrame()
    if last_n:
        df = df.groupby("team").tail(last_n)
    g = df.groupby("team")
    s = g.sum(numeric_only=True)
    n = g.size()
    out = pd.DataFrame(index=s.index)
    out["gp"] = n
    out["w"] = df[df["result"] == "W"].groupby("team").size().reindex(s.index, fill_value=0)
    out["l"] = df[df["result"] == "L"].groupby("team").size().reindex(s.index, fill_value=0)
    out["otl"] = df[df["result"] == "OTL"].groupby("team").size().reindex(s.index, fill_value=0)
    out["gf_pg"] = s["goals_for"] / n
    out["ga_pg"] = s["goals_against"] / n
    out["sf_pg"] = s["shots_for"] / n
    out["sa_pg"] = s["shots_against"] / n
    out["cf5_pct"] = 100 * s["cf5"] / (s["cf5"] + s["ca5"]).replace(0, np.nan)
    out["cf5_p60"] = 3600 * s["cf5"] / s["sec_5v5"].replace(0, np.nan)
    if "xgf5" in s and "xga5" in s:
        out["xgf5_pct"] = 100 * s["xgf5"] / (s["xgf5"] + s["xga5"]).replace(0, np.nan)
    else:
        out["xgf5_pct"] = np.nan
    out["hd_pg"] = s["hd_for"] / n
    out["hda_pg"] = s["hd_against"] / n
    out["pp_pct"] = 100 * s["pp_goals"] / s["pp_opps"].replace(0, np.nan)
    out["pk_pct"] = 100 * (1 - s["pk_goals_against"] / s["times_shorthanded"].replace(0, np.nan))
    out["pp_opps_pg"] = s["pp_opps"] / n
    out["times_sh_pg"] = s["times_shorthanded"] / n
    out["p1_gf_pg"] = s["p1_gf"] / n
    out["p1_ga_pg"] = s["p1_ga"] / n
    out["fo_pct"] = 100 * s["fo_wins"] / s["fo_total"].replace(0, np.nan)
    out["hits_pg"] = s["hits"] / n
    out["blocks_pg"] = s["blocks"] / n
    tot = df["goals_for"] + df["goals_against"]
    out["avg_total"] = tot.groupby(df["team"]).mean()
    out["over55_pct"] = 100 * (tot >= 6).groupby(df["team"]).mean()
    out["p1_over15_pct"] = 100 * ((df["p1_gf"] + df["p1_ga"]) >= 2).groupby(df["team"]).mean()
    out["first10_pct"] = 100 * df["goal_first10"].astype(bool).groupby(df["team"]).mean()
    out["ot_pct"] = 100 * df["last_period"].isin(["OT", "SO"]).groupby(df["team"]).mean()
    for k, (hib, _) in RANKED.items():
        if k in out:
            out[f"{k}_rank"] = out[k].rank(ascending=not hib, method="min")
    return out


def _last10(team: str) -> str:
    tg = _data()["teams"]
    df = tg[(tg["team"] == team) & (tg["game_type"] == 2)].sort_values("d").tail(10)
    if df.empty:
        return "—"
    c = df["result"].value_counts()
    return f"{c.get('W', 0)}-{c.get('L', 0)}-{c.get('OTL', 0)}"


def _record(tt: pd.DataFrame, team: str) -> Optional[str]:
    if tt.empty or team not in tt.index:
        return None
    r = tt.loc[team]
    return f"{int(r['w'])}-{int(r['l'])}-{int(r['otl'])}"


# ── schedule context (rest, travel, trips) ─────────────────────────────────

@ttl_cache(1800)
def _schedule_context() -> pd.DataFrame:
    """One row per team per scheduled game (past and future) with rest, recent
    load, travel and road-trip position. The basis of Schedule Spots and every
    'back-to-back' flag outside the game logs."""
    g = _data()["games"]
    if g.empty:
        return pd.DataFrame()
    base = g[["game_id", "season", "game_type", "date", "d", "home", "away", "state", "start_utc"]]
    home = base.assign(team=base["home"], opp=base["away"], is_home=True)
    away = base.assign(team=base["away"], opp=base["home"], is_home=False)
    # grouped by team AND season: the first game of a season has no "rest"
    # (it's an opener, not a 5-month break) and no carried-over road trip
    df = pd.concat([home, away], ignore_index=True).sort_values(["team", "season", "d", "game_id"])
    df["key"] = df["team"] + "_" + df["season"].astype(str)
    df["prev_d"] = df.groupby("key")["d"].shift()
    df["rest_days"] = (df["d"] - df["prev_d"]).dt.days - 1
    df["b2b"] = df["rest_days"] == 0

    def recent_games(days: int) -> np.ndarray:
        """Games each team played in the `days` days before each game."""
        out = np.zeros(len(df), dtype=int)
        pos = 0
        for _, grp in df.groupby("key", sort=False):
            ds = grp["d"].values
            lo = np.searchsorted(ds, ds - np.timedelta64(days, "D"), side="left")
            hi = np.searchsorted(ds, ds, side="left")
            out[pos:pos + len(ds)] = hi - lo
            pos += len(ds)
        return out
    df = df.reset_index(drop=True)
    df["games_last3"] = recent_games(3)
    df["games_last6"] = recent_games(6)

    df["venue_team"] = np.where(df["is_home"], df["team"], df["opp"])
    df["prev_venue"] = df.groupby("key")["venue_team"].shift()
    df["travel"] = [nhl_teams.travel_miles(a, b) if isinstance(a, str) else None
                    for a, b in zip(df["prev_venue"], df["venue_team"])]
    df["tz_shift"] = [nhl_teams.tz_shift(a, b) if isinstance(a, str) else None
                      for a, b in zip(df["prev_venue"], df["venue_team"])]
    # road trip: position in the current run of away games, and its length
    trip_idx, trip_len = [], []
    for _, grp in df.groupby("key", sort=False):
        away_flags = (~grp["is_home"]).tolist()
        runs, i = [], 0
        while i < len(away_flags):
            j = i
            while j < len(away_flags) and away_flags[j] == away_flags[i]:
                j += 1
            runs.append((i, j, away_flags[i]))
            i = j
        idx = [0] * len(away_flags); ln = [0] * len(away_flags)
        for a, b, is_away in runs:
            for k in range(a, b):
                idx[k] = (k - a + 1) if is_away else 0
                ln[k] = (b - a) if is_away else 0
        trip_idx += idx; trip_len += ln
    df["trip_game"] = trip_idx
    df["trip_len"] = trip_len
    df["spot"], df["tone"] = zip(*[_spot(r) for r in df.itertuples()])
    return df


def _spot(r: Any) -> Tuple[str, str]:
    if pd.isna(r.rest_days):
        return "Season opener", "neutral"
    if r.rest_days == 0:
        return "Back-to-back, 2nd night", "tired"
    if r.games_last3 >= 2:
        return "3 games in 4 nights", "tired"
    if r.trip_game >= 4:
        return "Long road trip", "tired"
    if r.rest_days is not None and not pd.isna(r.rest_days) and r.rest_days >= 2:
        return "Rested", "rested"
    return "Normal", "neutral"


# ── slate ──────────────────────────────────────────────────────────────────

@_public
def slate(on: Optional[str] = None) -> dict:
    g = _data()["games"]
    if g.empty:
        return _empty()
    d0 = pd.Timestamp(on) if on else pd.Timestamp(today_ct())
    day = g[g["d"] == d0]
    if day.empty and not on:
        future = g[g["d"] > d0].sort_values("d")
        if not future.empty:
            d0 = future["d"].iloc[0]
            day = g[g["d"] == d0]
    day = day.sort_values(["start_utc", "game_id"])
    return {
        "date": d0.strftime("%Y-%m-%d"),
        "is_today": d0.date() == today_ct(),
        "games": [{"game_id": int(r.game_id), "label": f"{r.away} @ {r.home}", "away": r.away, "home": r.home,
                   "start_utc": r.start_utc, "state": r.state} for r in day.itertuples()],
    }


def _game(game_id: int) -> Optional[pd.Series]:
    g = _data()["games"]
    row = g[g["game_id"] == int(game_id)] if not g.empty else g
    return None if row.empty else row.iloc[0]


# ── goalies ────────────────────────────────────────────────────────────────

def project_goalie(team: str, on: pd.Timestamp, game_id: Optional[int] = None) -> dict:
    """Who starts for `team` on date `on`: Confirmed once the game has a box
    score, otherwise Projected from the rotation."""
    D = _data()
    gg, rosters, games = D["goalies"], D["rosters"], D["games"]
    if game_id is not None and not gg.empty:
        actual = gg[(gg["game_id"] == int(game_id)) & (gg["team"] == team) & (gg["starter"])]
        if not actual.empty:
            r = actual.iloc[0]
            return {"player_id": int(r["player_id"]), "name": r["player"], "status": "Confirmed",
                    "reason": "Started this game"}
    starts = gg[(gg["team"] == team) & (gg["starter"]) & (gg["d"] < on)].sort_values("d", ascending=False) \
        if not gg.empty else gg
    cur = season_for(on.date())
    if not starts.empty and (starts["season"] == cur).sum() >= 3:
        starts = starts[starts["season"] == cur]
    cands = rosters[(rosters["team"] == team) & (rosters["pos"] == "G")] if not rosters.empty else rosters
    cand_ids = set(cands["player_id"].astype(int)) if not cands.empty else set(starts["player_id"].astype(int)) \
        if not starts.empty else set()
    names = {}
    if not cands.empty:
        names.update(dict(zip(cands["player_id"].astype(int), cands["player"])))
    if not starts.empty:
        for pid, nm in zip(starts["player_id"].astype(int), starts["player"]):
            names.setdefault(pid, nm)
    recent = starts[starts["player_id"].astype(int).isin(cand_ids)].head(10) if not starts.empty else starts
    if recent.empty:
        if not cand_ids:
            return {"player_id": None, "name": None, "status": "Unknown", "reason": "No goalie data yet"}
        pid = sorted(cand_ids)[0]
        return {"player_id": pid, "name": names.get(pid), "status": "Projected",
                "reason": "No starts with this team yet"}
    counts = recent.groupby("player_id").agg(n=("game_id", "size"), last=("d", "max")).sort_values(
        ["n", "last"], ascending=False)
    no1 = int(counts.index[0])
    n1 = int(counts.iloc[0]["n"])
    total = len(recent)
    # back-to-back: did the team play yesterday, and who started?
    y = on - pd.Timedelta(days=1)
    b2b = False
    if not games.empty:
        b2b = bool(((games["d"] == y) & ((games["home"] == team) | (games["away"] == team))).any())
    if b2b:
        yday = gg[(gg["team"] == team) & (gg["d"] == y) & (gg["starter"])] if not gg.empty else gg
        started_yday = int(yday.iloc[0]["player_id"]) if not yday.empty else no1
        if started_yday == no1:
            others = [int(p) for p in counts.index[1:]] or [p for p in cand_ids if p != no1]
            if others:
                pid = others[0]
                return {"player_id": pid, "name": names.get(pid), "status": "Projected",
                        "reason": "Back-to-back: the No. 1 started last night", "is_backup": True}
    return {"player_id": no1, "name": names.get(no1), "status": "Projected",
            "reason": f"Started {n1} of the last {total}", "is_backup": False}


def goalie_form(pid: Optional[int], before: pd.Timestamp, opp: Optional[str] = None) -> dict:
    gg = _data()["goalies"]
    if pid is None or gg.empty:
        return {}
    mine = gg[(gg["player_id"] == pid) & (gg["d"] < before)].sort_values("d")
    starts = mine[mine["starter"]]
    last5 = starts.tail(5)
    cur = season_for(before.date())
    season = starts[starts["season"] == cur]
    if len(season) < 3:
        season = starts[starts["season"] == prior(cur)]

    def sv(df: pd.DataFrame) -> Optional[float]:
        sa = df["shots_against"].sum()
        return round(df["saves"].sum() / sa, 3) if sa else None

    out = {
        "last5_sv": sv(last5), "last5_gsax": _f(last5["gsax"].sum(), 1) if "gsax" in last5 and len(last5) else None,
        "last5_faced": _f(last5["shots_against"].mean(), 1) if len(last5) else None,
        "last5_saves": [int(x) for x in last5["saves"].tolist()],
        "season_sv": sv(season), "season_gsax": _f(season["gsax"].sum(), 1) if "gsax" in season and len(season) else None,
        "season_starts": int(len(season)),
        "season_label": season_label(int(season["season"].iloc[0])) if len(season) else None,
    }
    if opp:
        vs = starts[starts["opp"] == opp]
        out["vs_opp_sv"] = sv(vs)
        out["vs_opp_starts"] = int(len(vs))
    return out


def _team_ranks(tt: pd.DataFrame, team: str) -> dict:
    if tt.empty or team not in tt.index:
        return {}
    r = tt.loc[team]
    return {
        "shots_pg": _f(r["sf_pg"], 1), "shots_pg_rank": ordinal(r.get("sf_pg_rank")),
        "cf5_p60": _f(r["cf5_p60"], 1), "cf5_p60_rank": ordinal(r.get("cf5_p60_rank")),
        "pp_opps_pg": _f(r["pp_opps_pg"], 2),
        "shots_allowed_pg": _f(r["sa_pg"], 1),
        "shots_allowed_rank": int(tt["sa_pg"].rank(method="min").loc[team]),
    }


@_public
def goalie_report(on: Optional[str] = None) -> dict:
    sl = slate(on)
    if "error" in sl:
        return sl
    D = _data()
    season, fallback = stats_season(D["teams"])
    tt = team_table(season)
    d0 = pd.Timestamp(sl["date"])
    games = []
    counts = {"Confirmed": 0, "Projected": 0, "Unknown": 0}
    for gm in sl["games"]:
        cards = []
        for team, opp, is_home in ((gm["away"], gm["home"], False), (gm["home"], gm["away"], True)):
            proj = project_goalie(team, d0, gm["game_id"])
            counts[proj["status"]] = counts.get(proj["status"], 0) + 1
            cards.append({
                "team": team, "opp": opp, "is_home": is_home, **proj,
                "form": goalie_form(proj["player_id"], d0, opp),
                "opponent": _team_ranks(tt, opp),
            })
        games.append({**gm, "goalies": cards})
    return {"date": sl["date"], "is_today": sl["is_today"], "season": season_label(season),
            "fallback": fallback, "counts": counts, "games": games}


# ── players / game log ─────────────────────────────────────────────────────

SKATER_STATS = {
    "sog": "Shots on goal", "points": "Points", "goals": "Goals", "assists": "Assists",
    "pp_points": "Power-play points", "attempts": "Shot attempts", "blocks": "Blocked shots",
    "hits": "Hits", "toi_min": "Time on ice (minutes)",
}
GOALIE_STATS = {"saves": "Saves", "shots_against": "Shots faced", "goals_against": "Goals against",
                "save_pct": "Save %"}


@_public
def players() -> List[dict]:
    D = _data()
    frames = []
    for key, is_g in (("skaters", False), ("goalies", True)):
        df = D[key]
        if not df.empty:
            last = df.sort_values("d").groupby("player_id").tail(1)
            frames.append(pd.DataFrame({"id": last["player_id"].astype(int), "player": last["player"],
                                        "team": last["team"],
                                        "pos": last["pos"] if "pos" in last else "G", "is_goalie": is_g}))
    ro = D["rosters"]
    if not ro.empty:
        frames.append(pd.DataFrame({"id": ro["player_id"].astype(int), "player": ro["player"], "team": ro["team"],
                                    "pos": ro["pos"], "is_goalie": ro["pos"] == "G"}))
    if not frames:
        return []
    allp = pd.concat(frames, ignore_index=True)
    # roster (listed last) wins for the current team
    allp = allp.drop_duplicates("id", keep="last")
    return [{"id": int(r.id), "label": f"{r.player} · {r.team}", "player": r.player, "team": r.team,
             "pos": r.pos, "is_goalie": bool(r.is_goalie)} for r in allp.sort_values("player").itertuples()]


def _opp_rank_maps(season: int) -> Tuple[Dict[str, int], Dict[str, int]]:
    tt = team_table(season)
    if tt.empty:
        return {}, {}
    sa = tt["sa_pg"].rank(method="min").astype(int).to_dict()           # 1 = fewest shots allowed
    sf = tt["sf_pg"].rank(ascending=False, method="min").astype(int).to_dict()  # 1 = most shots
    return sa, sf


def _rank_words(rank: Optional[int], words: str) -> Optional[str]:
    """3 -> '3rd fewest allowed'; 1 -> 'Fewest allowed'."""
    if not rank:
        return None
    return words[0].upper() + words[1:] if rank == 1 else f"{ordinal(rank)} {words}"


def _pos_group(p: Any) -> str:
    return "D" if p == "D" else "F"


def shots_allowed_by_position(season: int) -> pd.DataFrame:
    """Opponent shots on goal per game, split by the shooter's position group."""
    sk = _data()["skaters"]
    if sk.empty:
        return pd.DataFrame()
    df = sk[(sk["season"] == season) & (sk["game_type"] == 2)].copy()
    if df.empty:
        return pd.DataFrame()
    df["grp"] = df["pos"].map(_pos_group)
    per_game = df.groupby(["opp", "game_id", "grp"])["sog"].sum().reset_index()
    out = per_game.groupby(["opp", "grp"])["sog"].mean().unstack()
    for g in ("F", "D"):
        if g in out:
            out[f"{g}_rank"] = out[g].rank(method="min")   # 1 = fewest allowed
    return out


def _over(values: List[float], line: float, n: Optional[int] = None) -> dict:
    vals = values[-n:] if n else values
    over = sum(1 for v in vals if v is not None and v > line)
    tot = len(vals)
    return {"over": over, "total": tot, "pct": round(over / tot, 3) if tot else 0}


@_public
def game_log(player_id: int, stat: str = "sog", threshold: float = 0.5, season: Optional[int] = None,
             home_away: str = "all", pp_role: str = "all", min_toi: Optional[float] = None,
             opp_goalie: str = "all", rest: str = "all", starts_only: bool = True) -> dict:
    D = _data()
    sk, gg = D["skaters"], D["goalies"]
    if sk.empty and gg.empty:
        return _empty()
    is_goalie = not gg.empty and (gg["player_id"] == player_id).any() and \
        (sk.empty or not (sk["player_id"] == player_id).any())
    src = gg if is_goalie else sk
    rows = src[src["player_id"] == player_id].sort_values("d")
    if rows.empty:
        return {"error": "No games found for that player yet."}
    stats = GOALIE_STATS if is_goalie else SKATER_STATS
    if stat not in stats:
        stat = "saves" if is_goalie else "sog"

    cur = season_for(today_ct())
    fallback = False
    if season is None:
        season = cur if (rows["season"] == cur).sum() >= MIN_GAMES else prior(cur)
        fallback = season != cur
    seasons_available = sorted({int(s) for s in rows["season"].unique()}, reverse=True)
    df = rows[rows["season"] == season].copy()
    if is_goalie and starts_only:
        df = df[df["starter"]]
    if df.empty:
        return {"error": f"No {season_label(season)} games for that player.",
                "seasons_available": seasons_available}

    if stat == "toi_min":
        df["val"] = (df["toi"] / 60).round(1)
    elif stat == "save_pct":
        df["val"] = df["save_pct"].astype(float).round(3)
    else:
        df["val"] = df[stat].astype(float)

    sa_rank, sf_rank = _opp_rank_maps(season)
    base = df.copy()   # splits use the season before filters

    # filters
    if home_away in ("home", "away"):
        df = df[df["is_home"] == (home_away == "home")]
    if rest == "b2b" and "b2b" in df:
        df = df[df["b2b"] == True]  # noqa: E712
    elif rest == "rested" and "b2b" in df:
        df = df[df["b2b"] != True]  # noqa: E712
    if not is_goalie:
        if pp_role == "pp1":
            df = df[df["pp_unit"] == "PP1"]
        elif pp_role == "not_pp1":
            df = df[df["pp_unit"] != "PP1"]
        if min_toi:
            df = df[df["toi"] >= float(min_toi) * 60]
        if opp_goalie in ("starter", "backup") and "opp_goalie_backup" in df:
            df = df[df["opp_goalie_backup"] == (opp_goalie == "backup")]

    def game_row(r: Any) -> dict:
        opp = r.opp
        res = r.team_result
        out = {
            "game_id": int(r.game_id), "date": r.date, "game_date": r.d.strftime("%b %d"),
            "opponent": f"{'vs' if r.is_home else '@'} {opp}", "opp": opp,
            "stat_value": None if pd.isna(r.val) else float(r.val),
            "result": "W" if res == "W" else "L", "team_result": res, "score": r.score,
            "tooltip": {"score": r.score},
            "toi": mmss(r.toi), "b2b": bool(getattr(r, "b2b", False) is True),
            "playoffs": int(r.game_type) == 3,
        }
        if is_goalie:
            out.update({"shots_against": int(r.shots_against), "saves": int(r.saves),
                        "goals_against": int(r.goals_against), "save_pct": _f(r.save_pct, 3),
                        "decision": r.decision, "starter": bool(r.starter),
                        "xga": _f(getattr(r, "xga", None), 2), "gsax": _f(getattr(r, "gsax", None), 2),
                        "opp_rank": sf_rank.get(opp), "opp_rank_label":
                            _rank_words(sf_rank.get(opp), "most shots")})
        else:
            out.update({"sog": int(r.sog), "attempts": int(r.attempts), "goals": int(r.goals),
                        "assists": int(r.assists), "pp_points": int(r.pp_points),
                        "pp_toi": mmss(r.pp_toi), "pp_unit": r.pp_unit, "line": r.line,
                        "linemates": r.linemates, "opp_goalie": r.opp_goalie,
                        "opp_goalie_backup": bool(getattr(r, "opp_goalie_backup", False) is True),
                        "ixg": _f(getattr(r, "ixg", None), 2),
                        "opp_rank": sa_rank.get(opp), "opp_rank_label":
                            _rank_words(sa_rank.get(opp), "fewest allowed")})
        return out

    games = [game_row(r) for r in df.itertuples()]
    vals = [g["stat_value"] for g in games]
    over_counts = {"last5": _over(vals, threshold, 5), "last10": _over(vals, threshold, 10),
                   "last20": _over(vals, threshold, 20), "season": _over(vals, threshold)}
    if not is_goalie:
        pp1_vals = [g["stat_value"] for g in games if g.get("pp_unit") == "PP1"]
        over_counts["pp1"] = _over(pp1_vals, threshold)

    # splits on the unfiltered season
    def split(label: str, sub: pd.DataFrame) -> Optional[dict]:
        if sub.empty:
            return None
        v = sub["val"].astype(float)
        over = int((v > threshold).sum())
        return {"label": label, "n": int(len(sub)), "avg": _f(v.mean(), 2), "over": over,
                "pct": round(over / len(sub), 3)}
    sp = [split("Home", base[base["is_home"] == True]),  # noqa: E712
          split("Away", base[base["is_home"] == False])]  # noqa: E712
    if "b2b" in base:
        sp += [split("Second night of a back-to-back", base[base["b2b"] == True]),  # noqa: E712
               split("Not a back-to-back", base[base["b2b"] != True])]  # noqa: E712
    if is_goalie:
        top = {t for t, r in sf_rank.items() if r <= 10}
        sp += [split("vs top-10 shot teams", base[base["opp"].isin(top)]),
               split("vs everyone else", base[~base["opp"].isin(top)])]
    else:
        sp += [split("On the first power-play unit", base[base["pp_unit"] == "PP1"]),
               split("Not on the first unit", base[base["pp_unit"] != "PP1"])]
        if "opp_goalie_backup" in base:
            sp += [split("vs starting goalie", base[base["opp_goalie_backup"] == False]),  # noqa: E712
                   split("vs backup goalie", base[base["opp_goalie_backup"] == True])]  # noqa: E712
    splits = [s for s in sp if s]

    last = rows.iloc[-1]
    ro = D["rosters"]
    cur_team = last["team"]
    if not ro.empty and (ro["player_id"] == player_id).any():
        cur_team = ro[ro["player_id"] == player_id].iloc[0]["team"]

    return {
        "player": {"id": int(player_id), "name": last["player"], "team": cur_team,
                   "pos": "G" if is_goalie else last.get("pos"), "is_goalie": bool(is_goalie)},
        "stat": stat, "stat_label": stats[stat], "stats": [{"key": k, "label": v} for k, v in stats.items()],
        "season": int(season), "season_label": season_label(season), "fallback": fallback,
        "seasons_available": seasons_available, "threshold": threshold,
        "games": games, "over_counts": over_counts, "splits": splits,
        "next_game": _next_game(player_id, cur_team, is_goalie, rows),
    }


def _next_game(player_id: int, team: str, is_goalie: bool, rows: pd.DataFrame) -> Optional[dict]:
    D = _data()
    g = D["games"]
    if g.empty:
        return None
    t0 = pd.Timestamp(today_ct())
    up = g[((g["home"] == team) | (g["away"] == team)) & (g["d"] >= t0) & (~g["state"].isin(FINAL))]
    if up.empty:
        return None
    nxt = up.sort_values(["d", "start_utc"]).iloc[0]
    is_home = nxt["home"] == team
    opp = nxt["away"] if is_home else nxt["home"]
    season, fallback = stats_season(D["teams"])
    tt = team_table(season)
    out = {"game_id": int(nxt["game_id"]), "date": nxt["date"], "start_utc": nxt["start_utc"],
           "label": f"{nxt['away']} @ {nxt['home']}", "opp": opp, "is_home": bool(is_home),
           "stats_season": season_label(season), "fallback": fallback}
    if is_goalie:
        proj = project_goalie(team, nxt["d"], int(nxt["game_id"]))
        out["projection"] = proj
        out["projected_to_start"] = proj.get("player_id") == player_id
        out["opponent"] = _team_ranks(tt, opp)
    else:
        out["opp_goalie"] = project_goalie(opp, nxt["d"], int(nxt["game_id"]))
        out["opponent"] = _team_ranks(tt, opp)
        bypos = shots_allowed_by_position(season)
        grp = _pos_group(rows.iloc[-1].get("pos"))
        if not bypos.empty and opp in bypos.index and grp in bypos:
            out["pos_group"] = "defensemen" if grp == "D" else "forwards"
            out["shots_allowed_to_pos"] = _f(bypos.loc[opp, grp], 1)
            out["shots_allowed_to_pos_rank"] = ordinal(bypos.loc[opp, f"{grp}_rank"])
        last = rows.iloc[-1]
        out["role"] = {"line": last.get("line"), "pp_unit": last.get("pp_unit"),
                       "linemates": last.get("linemates"), "as_of": last["date"]}
    return out


# ── team matchup ───────────────────────────────────────────────────────────

def _fmt(v: Any, f: str) -> Optional[str]:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    if f == "%":
        return f"{v:.1f}%"
    return f"{v:.{int(f)}f}"


def _injuries(team: str) -> List[dict]:
    inj = get_injuries_data("nhl")
    if inj is None or inj.empty:
        return []
    ab = inj["team"].map(nhl_teams.abbrev_for_name)
    rows = inj[ab == team]
    return [{"player": r.player, "position": r.position, "status": r.status, "detail": r.detail}
            for r in rows.itertuples()]


def _context_row(team: str, game_id: int) -> Optional[pd.Series]:
    ctx = _schedule_context()
    if ctx.empty:
        return None
    r = ctx[(ctx["team"] == team) & (ctx["game_id"] == game_id)]
    return None if r.empty else r.iloc[0]


def _ctx_dict(r: Optional[pd.Series]) -> dict:
    if r is None:
        return {}
    rest = None if pd.isna(r["rest_days"]) else max(0, int(r["rest_days"]))
    return {"rest_days": rest, "b2b": bool(r["b2b"]), "spot": r["spot"], "tone": r["tone"],
            "games_last6": int(r["games_last6"]), "travel": _f(r["travel"], 0),
            "tz_shift": None if pd.isna(r["tz_shift"]) else int(r["tz_shift"]),
            "trip_game": int(r["trip_game"]), "trip_len": int(r["trip_len"]),
            "first_game": rest is None}


@_public
def matchup(game_id: int) -> dict:
    D = _data()
    gm = _game(game_id)
    if gm is None:
        return {"error": "Game not found."}
    away, home = gm["away"], gm["home"]
    season, fallback = stats_season(D["teams"], gm["d"].date())
    tt = team_table(season)
    if tt.empty:
        return _empty()
    sections = []
    for title, rows in METRICS:
        out_rows = []
        for key, label, hib, graded, f in rows:
            if key not in tt:
                continue
            a = tt[key].get(away) if away in tt.index else None
            h = tt[key].get(home) if home in tt.index else None
            ar = tt[f"{key}_rank"].get(away) if away in tt.index else None
            hr = tt[f"{key}_rank"].get(home) if home in tt.index else None
            edge = None
            if graded and ar is not None and hr is not None and not (pd.isna(ar) or pd.isna(hr)):
                edge = "Even" if abs(ar - hr) <= 3 else (away if ar < hr else home)
            out_rows.append({"key": key, "label": label, "graded": graded,
                             "away": _fmt(a, f), "away_rank": None if ar is None or pd.isna(ar) else int(ar),
                             "home": _fmt(h, f), "home_rank": None if hr is None or pd.isna(hr) else int(hr),
                             "edge": edge})
        sections.append({"title": title, "rows": out_rows})

    def st(team: str, opp: str) -> dict:
        pp = tt.loc[team] if team in tt.index else None
        pk = tt.loc[opp] if opp in tt.index else None
        if pp is None or pk is None:
            return {}
        diff = int(pp["pp_pct_rank"]) - int(pk["pk_pct_rank"])
        edge = "Even" if abs(diff) < 8 else (f"{team} power play" if diff < 0 else f"{opp} penalty kill")
        return {"team": team, "opp": opp, "pp_pct": _f(pp["pp_pct"], 1), "pp_rank": ordinal(pp["pp_pct_rank"]),
                "pk_pct": _f(pk["pk_pct"], 1), "pk_rank": ordinal(pk["pk_pct_rank"]), "edge": edge,
                "expected_pp": _f((pp["pp_opps_pg"] + pk["times_sh_pg"]) / 2, 1)}

    totals = []
    for key, label in (("avg_total", "Average total goals"), ("over55_pct", "Went over 5.5 goals"),
                       ("p1_over15_pct", "Over 1.5 first-period goals"),
                       ("first10_pct", "Goal in the first 10 minutes"), ("ot_pct", "Went to overtime")):
        f = "2" if key == "avg_total" else "%"
        totals.append({"label": label,
                       "away": _fmt(tt[key].get(away), f) if away in tt.index else None,
                       "home": _fmt(tt[key].get(home), f) if home in tt.index else None})

    tg = D["teams"]
    h2h = tg[(tg["team"] == home) & (tg["opp"] == away)].sort_values("d", ascending=False).head(6)
    h2h_rows = [{"date": r.date, "season": season_label(int(r.season)),
                 "venue": home if r.is_home else away,
                 "winner": home if r.result == "W" else away,
                 "score": f"{max(r.goals_for, r.goals_against)}-{min(r.goals_for, r.goals_against)}"
                          + (f" {r.last_period}" if r.last_period in ("OT", "SO") else "")}
                for r in h2h.itertuples()]

    d0 = gm["d"]
    team_blocks = {}
    for team, opp in ((away, home), (home, away)):
        proj = project_goalie(team, d0, int(game_id))
        team_blocks[team] = {
            "team": team, "name": nhl_teams.full_name(team), "record": _record(tt, team),
            "last10": _last10(team),
            "goalie": {**proj, "form": goalie_form(proj.get("player_id"), d0, opp)},
            "schedule": _ctx_dict(_context_row(team, int(game_id))),
            "injuries": _injuries(team),
        }
    return {
        "game": {"game_id": int(game_id), "away": away, "home": home, "date": gm["date"],
                 "start_utc": gm["start_utc"], "venue": gm.get("venue"), "state": gm["state"]},
        "season": season_label(season), "fallback": fallback,
        "away": team_blocks[away], "home": team_blocks[home],
        "sections": sections, "special_teams": [st(away, home), st(home, away)],
        "totals": totals, "head_to_head": h2h_rows,
    }


# ── schedule spots ─────────────────────────────────────────────────────────

@_public
def schedule_spots(on: Optional[str] = None) -> dict:
    sl = slate(on)
    if "error" in sl:
        return sl
    ctx = _schedule_context()
    D = _data()
    tg = D["teams"]
    d0 = pd.Timestamp(sl["date"])
    cur = season_for(d0.date())
    hist_season = prior(cur)
    hist = ctx[(ctx["season"] == hist_season) & (ctx["game_type"] == 2)].merge(
        tg[["game_id", "team", "result", "goals_against", "goals_for", "starter_goalie_id"]],
        on=["game_id", "team"], how="inner") if not tg.empty else pd.DataFrame()

    def in_spot(team: str, spot: str) -> Optional[str]:
        if hist.empty:
            return None
        h = hist[(hist["team"] == team) & (hist["spot"] == spot)]
        if h.empty:
            return None
        c = h["result"].value_counts()
        return f"{c.get('W', 0)}-{c.get('L', 0)}-{c.get('OTL', 0)} · {h['goals_against'].mean():.1f} goals allowed"

    rows, edges = [], []
    for gm in sl["games"]:
        pair = []
        for team, opp in ((gm["away"], gm["home"]), (gm["home"], gm["away"])):
            c = _ctx_dict(_context_row(team, gm["game_id"]))
            proj = project_goalie(team, d0, gm["game_id"])
            row = {"game_id": gm["game_id"], "game": gm["label"], "team": team, "opp": opp, **c,
                   "goalie": proj.get("name"), "goalie_status": proj.get("status"),
                   "goalie_backup": bool(proj.get("is_backup")),
                   "history": in_spot(team, c.get("spot", "Normal"))}
            rows.append(row)
            pair.append(row)
        a, h = pair
        tones = (a.get("tone"), h.get("tone"))
        if tones[0] == "tired" and tones[1] == "tired":
            edges.append({"game": gm["label"], "tag": "Both tired", "tone": "tired",
                          "head": "Both teams in a tough spot",
                          "body": f"{a['team']}: {a['spot'].lower()}. {h['team']}: {h['spot'].lower()}."})
        elif "tired" in tones and tones != ("tired", "tired"):
            tired, fresh = (a, h) if tones[0] == "tired" else (h, a)
            edges.append({"game": gm["label"], "tag": f"Rest edge: {fresh['team']}", "tone": "rested",
                          "head": f"{fresh['team']} ({_rest_words(fresh)}) vs {tired['team']} ({tired['spot'].lower()})",
                          "body": _tired_body(tired)})

    # league trend: 2nd night of a back-to-back vs a rested opponent
    trend = None
    if not hist.empty:
        opp_ctx = hist[["game_id", "team", "rest_days"]].rename(columns={"team": "opp", "rest_days": "opp_rest"})
        h2 = hist.merge(opp_ctx, on=["game_id", "opp"], how="left")
        spot = h2[(h2["b2b"]) & (h2["opp_rest"] >= 1)]
        if len(spot) >= 20:
            season_ga = hist.groupby("team")["goals_against"].mean()
            no1 = D["goalies"]
            no1 = no1[(no1["season"] == hist_season) & (no1["starter"])].groupby(["team", "player_id"]).size() \
                .reset_index(name="n").sort_values("n").groupby("team").tail(1).set_index("team")["player_id"] \
                if not no1.empty else pd.Series(dtype=float)
            backup = (spot["starter_goalie_id"] != spot["team"].map(no1)).mean() if len(no1) else None
            trend = {
                "season": season_label(hist_season), "games": int(len(spot)),
                "win_pct": _f(100 * (spot["result"] == "W").mean(), 0),
                "ga_vs_avg": _f((spot["goals_against"] - spot["team"].map(season_ga)).mean(), 2),
                "backup_pct": _f(100 * backup, 0) if backup is not None else None,
                "six_plus_pct": _f(100 * ((spot["goals_for"] + spot["goals_against"]) >= 6).mean(), 0),
            }
    return {"date": sl["date"], "is_today": sl["is_today"], "rows": rows, "edges": edges, "trend": trend,
            "history_season": season_label(hist_season)}


def _rest_words(r: dict) -> str:
    if r.get("first_game"):
        return "first game"
    d = r.get("rest_days")
    return f"{d} day{'s' if d != 1 else ''} of rest" if d is not None else "rest unknown"


def _tired_body(r: dict) -> str:
    bits = [r["spot"]]
    if r.get("travel"):
        bits.append(f"{int(r['travel'])} miles of travel")
    if r.get("goalie_backup"):
        bits.append(f"backup {r.get('goalie')} projected in goal")
    return ", ".join(bits) + "."


# ── lines & power play ─────────────────────────────────────────────────────

def _unit_sort(label: str) -> Tuple[int, int]:
    kind = {"L": 0, "D": 1, "P": 2}[label[0]]
    return kind, int(label[-1])


@_public
def lines(game_id: int, mode: str = "last") -> dict:
    D = _data()
    gm = _game(game_id)
    if gm is None:
        return {"error": "Game not found."}
    units = D["units"]
    if units.empty:
        return _empty()
    d0 = gm["d"]
    teams = []
    for team in (gm["away"], gm["home"]):
        tu = units[(units["team"] == team) & (units["d"] <= d0) & (units["game_id"] != int(game_id))
                   if gm["state"] not in STARTED else (units["team"] == team) & (units["d"] <= d0)]
        game_ids = tu.drop_duplicates("game_id").sort_values("d")["game_id"].tolist()
        if not game_ids:
            teams.append({"team": team, "units": [], "note": "No games with shift data yet."})
            continue
        latest, prev = game_ids[-1], (game_ids[-2] if len(game_ids) > 1 else None)
        last10 = tu[tu["game_id"].isin(game_ids[-10:])]
        if mode == "common":
            last5 = tu[tu["game_id"].isin(game_ids[-5:])]
            chosen = (last5.groupby(["unit", "players_key"]).agg(n=("game_id", "size"), last=("d", "max"))
                      .reset_index().sort_values(["n", "last"], ascending=False).drop_duplicates("unit"))
            picked = [(r.unit, r.players_key) for r in chosen.itertuples()]
        else:
            lg = tu[tu["game_id"] == latest]
            picked = [(r.unit, r.players_key) for r in lg.itertuples()]
        name_by_key = tu.drop_duplicates("players_key", keep="last").set_index("players_key")["players"]

        # player -> unit label, latest vs previous game
        def labels(gid: Optional[int]) -> Dict[str, Dict[int, str]]:
            out: Dict[str, Dict[int, str]] = {"line": {}, "pp": {}}
            if gid is None:
                return out
            for r in tu[tu["game_id"] == gid].itertuples():
                for p in str(r.player_ids).split(","):
                    out["pp" if r.unit.startswith("PP") else "line"][int(p)] = r.unit
            return out
        now_l, prev_l = labels(latest), labels(prev)
        sk = D["skaters"]
        names = {}
        if not sk.empty:
            recent_sk = sk[(sk["team"] == team) & (sk["game_id"].isin(game_ids[-2:]))]
            names = dict(zip(recent_sk["player_id"].astype(int), recent_sk["player"]))

        out_units = []
        for label, key in sorted(picked, key=lambda x: _unit_sort(x[0])):
            hist = last10[last10["players_key"] == key]
            toi, cf, ca = hist["toi_together"].sum(), hist["cf"].sum(), hist["ca"].sum()
            ids = [int(p) for p in key.split("-")]
            member_ids = [int(p) for p in str(tu[tu["players_key"] == key]["player_ids"].iloc[-1]).split(",")]
            kind = "pp" if label.startswith("PP") else "line"
            notes = []
            if prev is not None:
                for p in member_ids:
                    before = prev_l[kind].get(p)
                    nm = (names.get(p) or "").split(" ")[-1] or str(p)
                    if before is None:
                        notes.append(f"{nm} new to the {'power play' if kind == 'pp' else 'lineup'}"
                                     if p not in prev_l["line"] else f"{nm} new to {label}")
                    elif before != label:
                        up = _unit_sort(label)[1] < _unit_sort(before)[1]
                        notes.append(f"{nm} moved {'up' if up else 'down'} from {before}")
            out_units.append({
                "unit": label, "players": name_by_key.get(key, ""), "player_ids": member_ids,
                "games_together": int(hist["game_id"].nunique()),
                "minutes_together": _f(toi / 60, 0), "gf": int(hist["gf"].sum()), "ga": int(hist["ga"].sum()),
                "shot_share": _f(100 * cf / (cf + ca), 0) if (cf + ca) else None,
                "notes": notes, "changed": bool(notes),
            })
        # players who played the previous game but not the latest
        dropped = []
        if prev is not None:
            prev_players = set(prev_l["line"]) | set(prev_l["pp"])
            now_players = set(now_l["line"]) | set(now_l["pp"])
            for p in sorted(prev_players - now_players):
                dropped.append({"player": names.get(p, str(p)), "was": prev_l["line"].get(p) or prev_l["pp"].get(p)})
        latest_row = tu[tu["game_id"] == latest].iloc[0]
        teams.append({"team": team, "as_of": latest_row["date"], "units": out_units, "out_since_last": dropped,
                      "prior_season": int(latest_row["season"]) != season_for(d0.date()),
                      "goalie": project_goalie(team, d0, int(game_id))})

    return {"game": {"game_id": int(game_id), "away": gm["away"], "home": gm["home"], "date": gm["date"]},
            "mode": mode, "teams": teams, "matchups": _line_matchups(gm["away"], gm["home"], d0)}


def _line_matchups(a: str, b: str, before: pd.Timestamp) -> Optional[dict]:
    D = _data()
    um, units = D["matchups"], D["units"]
    if um.empty:
        return None
    meet = um[(((um["team"] == a) & (um["opp"] == b)) | ((um["team"] == b) & (um["opp"] == a)))
              & (um["d"] <= before)]
    if meet.empty:
        return None
    gid = int(meet.sort_values("d").iloc[-1]["game_id"])
    m = meet[meet["game_id"] == gid]
    names = units[units["game_id"] == gid].set_index(["team", "unit"])["players"].to_dict()
    gm = _game(gid)
    rows = []
    for r in m.itertuples():
        if r.unit not in ("L1", "L2", "D1"):
            continue
        rows.append({"team": r.team, "unit": r.unit, "players": names.get((r.team, r.unit)),
                     "opp": r.opp, "opp_unit": r.opp_unit, "opp_players": names.get((r.opp, r.opp_unit)),
                     "share": _f(100 * r.seconds / r.unit_toi, 0) if r.unit_toi else None})
    rows.sort(key=lambda x: (x["team"] != a, _unit_sort(x["unit"]), x["opp_unit"]))
    return {"game_id": gid, "date": m.iloc[0]["date"],
            "home": gm["home"] if gm is not None else None, "rows": rows}


# ── deep dive ──────────────────────────────────────────────────────────────

@_public
def deep_dive(game_id: int, attacking: str = "away", strength: str = "5v5", window: int = 20) -> dict:
    D = _data()
    gm = _game(game_id)
    if gm is None:
        return {"error": "Game not found."}
    zones, tg = D["zones"], D["teams"]
    if zones.empty or tg.empty:
        return _empty()
    x_team = gm["away"] if attacking == "away" else gm["home"]
    y_team = gm["home"] if attacking == "away" else gm["away"]
    d0 = gm["d"]
    strength = strength if strength in ("5v5", "pp", "all") else "5v5"
    season, fallback = stats_season(tg, d0.date())

    def last_ids(team: str) -> List[int]:
        t = tg[(tg["team"] == team) & (tg["d"] < d0) & (tg["game_type"] == 2)].sort_values("d")
        cur = t[t["season"] == season]
        use = cur if len(cur) >= MIN_GAMES else t
        return use["game_id"].tail(window).astype(int).tolist()

    x_ids, y_ids = last_ids(x_team), last_ids(y_team)
    z = zones[zones["strength"] == strength]
    zcols = [c for c in ZONE_LABELS if c in z.columns]
    x_for = z[(z["team"] == x_team) & (z["game_id"].isin(x_ids))][zcols]
    y_against = z[(z["opp"] == y_team) & (z["game_id"].isin(y_ids))][zcols]
    league = z[(z["season"] == season) & (z["game_type"] == 2)][zcols]
    if league.empty:
        league = z[zcols]
    lg = league.mean()
    xf, ya = x_for.mean(), y_against.mean()

    def pct(v: float, base: float) -> Optional[float]:
        return _f(100 * (v - base) / base, 0) if base and not np.isnan(v) else None
    zone_rows = [{"zone": k, "label": ZONE_LABELS[k], "for": _f(xf.get(k), 2), "against": _f(ya.get(k), 2),
                  "league": _f(lg.get(k), 2), "for_diff": pct(xf.get(k, np.nan), lg.get(k, 0)),
                  "against_diff": pct(ya.get(k, np.nan), lg.get(k, 0))} for k in zcols]

    def quality(df: pd.DataFrame) -> dict:
        ub = df["ub_for"].sum()
        return {"hd_share": _f(100 * df["hd_for"].sum() / ub, 0) if ub else None,
                "avg_distance": _f(df["dist_sum_for"].sum() / ub, 0) if ub else None,
                "rebounds_pg": _f(df["rebounds_for"].mean(), 1), "rush_pg": _f(df["rush_for"].mean(), 1)}
    x_q = quality(tg[(tg["team"] == x_team) & (tg["game_id"].isin(x_ids))])
    y_q = quality(tg[(tg["opp"] == y_team) & (tg["game_id"].isin(y_ids))])

    def periods(team: str, ids: List[int]) -> dict:
        t = tg[(tg["team"] == team) & (tg["game_id"].isin(ids))]
        return {p: {"for": _f(t[f"{p}_gf"].mean(), 2), "against": _f(t[f"{p}_ga"].mean(), 2)}
                for p in ("p1", "p2", "p3", "ot")}

    def score_state(team: str, ids: List[int]) -> dict:
        t = tg[(tg["team"] == team) & (tg["game_id"].isin(ids))]
        out = {}
        for s in ("lead", "tied", "trail"):
            sec = t[f"sec_{s}"].sum()
            out[s] = _f(3600 * t[f"sog_{s}"].sum() / sec, 1) if sec else None
        tot = t[["sec_lead", "sec_tied", "sec_trail"]].sum().sum()
        out["share_leading"] = _f(100 * t["sec_lead"].sum() / tot, 0) if tot else None
        return out

    return {
        "game": {"game_id": int(game_id), "away": gm["away"], "home": gm["home"], "date": gm["date"]},
        "attacking": x_team, "defending": y_team, "strength": strength,
        "window": window, "games_for": len(x_ids), "games_against": len(y_ids),
        "season": season_label(season), "fallback": fallback,
        "zones": zone_rows,
        "per_game": {"for": _f(xf.sum(), 1), "against": _f(ya.sum(), 1), "league": _f(lg.sum(), 1)},
        "quality": {"for": x_q, "against": y_q},
        "periods": {x_team: periods(x_team, x_ids), y_team: periods(y_team, y_ids)},
        "score_state": {x_team: score_state(x_team, x_ids), y_team: score_state(y_team, y_ids)},
    }


@_public
def meta() -> dict:
    m = get_nhl_meta()
    return m if isinstance(m, dict) else {}
