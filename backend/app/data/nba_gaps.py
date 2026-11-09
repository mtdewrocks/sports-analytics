"""NBA Gap Bets: anti-middles priced against each player's own box scores.

An anti-middle is an Over on the HIGHER line at one book and an Under on the
LOWER line at another (Under 21.5 at +115, Over 22.5 at +110). Exactly one leg
wins on every result except the gap (22 here), where both lose.
build_prop_middles.py already finds and prices these and reports the
break-even: the most often the result can land in the gap before the pair
loses money. What it can't know is how often it actually DOES land there.

That's what this adds. For each pair, the player's last LOOKBACK games
(across last season and this one) give a landing rate for the gap, and from
that an estimated return:

    EV = (1 - p) x one_wins  +  p x (-100%)

Measured on 2025-26 box scores, a one-number gap at a player's average gets
hit ~6% of the time for points, ~4% for PRA, ~12% rebounds, ~14% assists and
~23% threes -- so the same +110/+110 pair is close to fair on points and a
clear loser on threes. Small samples are noisy, so rates on fewer than
MIN_GAMES games are left blank rather than guessed, and the rate shown is a
historical frequency, not a projection.
"""
from __future__ import annotations

import math
import unicodedata
from typing import Any, Dict, List, Optional

import pandas as pd

from app.data.loader import get_middles_data, get_nba_all_seasons, get_nba_gap_log

LOOKBACK = 30
MIN_GAMES = 10

# props market (after get_props.py strips "player_" and the middles builder
# folds "_alternate") -> box-score column(s) in nba_player_stats.parquet
MARKET_STATS = {
    "points": ["pts"],
    "rebounds": ["reb"],
    "assists": ["ast"],
    "threes": ["3pm"],
    "blocks": ["blk"],
    "steals": ["stl"],
    "turnovers": ["tov"],
    "blocks_steals": ["blk", "stl"],
    "points_rebounds_assists": ["pts", "reb", "ast"],
    "points_rebounds": ["pts", "reb"],
    "rebounds_assists": ["reb", "ast"],
    "points_assists": ["pts", "ast"],
}

# Game-level markets have no player history to count, so the landing rate is
# modelled: final score ~ Normal(mean = the midpoint of the two lines, sd).
# sd is the typical miss of a final against its line. Measured on 2025-26:
# game totals vary by ~20 pts overall and team totals by ~12.7 around a
# team's own average; a closing line explains part of that, so 18 and 12.
# At sd 18 the chance of any single number near the line is ~2.2% -- the
# measured share was 2.3%.
MODELED_SD = {"totals": 18.0, "team_totals": 12.0}

MARKET_LABELS = {
    "totals": "Game total", "team_totals": "Team total",
    "points": "Points", "rebounds": "Rebounds", "assists": "Assists",
    "threes": "Threes made", "blocks": "Blocks", "steals": "Steals",
    "turnovers": "Turnovers", "blocks_steals": "Blocks + steals",
    "points_rebounds_assists": "Points + rebounds + assists",
    "points_rebounds": "Points + rebounds", "rebounds_assists": "Rebounds + assists",
    "points_assists": "Points + assists",
}


def name_key(name: str) -> str:
    """'Nikola Jokić' == 'Nikola Jokic', 'Jaren Jackson Jr.' == 'Jaren Jackson Jr'."""
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return " ".join(s.lower().replace(".", "").replace("'", "").split())


def gap_bounds(over_line: float, under_line: float) -> Optional[tuple]:
    """Integer results where both legs of an anti-middle lose -- the same
    span build_prop_middles.anti_middle_window() reports (ceil(under) to
    floor(over)), so a whole-number line's push counts as a loss here,
    which is the conservative reading."""
    lo, hi = math.ceil(under_line), math.floor(over_line)
    return (lo, hi) if hi >= lo else None


def _recent_values(stats: pd.DataFrame) -> Dict[tuple, List[float]]:
    """(name key, market) -> that player's last LOOKBACK results, newest last."""
    if stats.empty or "player" not in stats.columns:
        return {}
    df = stats.copy()
    if "played" in df.columns:
        df = df[pd.to_numeric(df["played"], errors="coerce") == 1]
    date_col = "date" if "date" in df.columns else "game_date"
    df["_d"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.sort_values("_d")
    df["_k"] = df["player"].map(name_key)
    recent = df.groupby("_k", sort=False).tail(LOOKBACK)
    out: Dict[tuple, List[float]] = {}
    for market, cols in MARKET_STATS.items():
        if not all(c in recent.columns for c in cols):
            continue
        vals = recent[cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
        for k, v in pd.DataFrame({"k": recent["_k"], "v": vals}).groupby("k", sort=False)["v"]:
            out[(k, market)] = v.tolist()
    return out


def _team_by_player(stats: pd.DataFrame) -> Dict[str, str]:
    if stats.empty or "team" not in stats.columns:
        return {}
    date_col = "date" if "date" in stats.columns else "game_date"
    last = stats.assign(_d=pd.to_datetime(stats[date_col], errors="coerce")).sort_values("_d")
    last = last.groupby(last["player"].map(name_key)).tail(1)
    return dict(zip(last["player"].map(name_key), last["team"]))


def _normal_window(lo: int, hi: int, mu: float, sd: float) -> float:
    """P(lo <= X <= hi) for an integer score X ~ Normal(mu, sd), with the
    usual +/-0.5 continuity correction."""
    cdf = lambda x: 0.5 * (1 + math.erf((x - mu) / (sd * math.sqrt(2))))  # noqa: E731
    return max(0.0, cdf(hi + 0.5) - cdf(lo - 0.5))


def _is_started(commence: Any) -> bool:
    ts = pd.to_datetime(commence, utc=True, errors="coerce")
    return bool(pd.notna(ts) and ts <= pd.Timestamp.now(tz="UTC"))


def get_gap_bets(include_negative: bool = False, market: Optional[str] = None) -> Dict[str, Any]:
    pairs = get_middles_data("nba")
    empty = {"lines_as_of": None, "oldest_line": None, "lookback": LOOKBACK, "rows": []}
    if pairs is None or pairs.empty or "kind" not in pairs.columns:
        return empty
    pairs = pairs[pairs["kind"] == "anti_middle"].copy()
    if "commence_time" in pairs.columns:
        pairs = pairs[~pairs["commence_time"].map(_is_started)]
    if market:
        pairs = pairs[pairs["market"] == market]
    if pairs.empty:
        return empty

    stats = get_nba_all_seasons()
    history = _recent_values(stats)
    teams = _team_by_player(stats)

    rows = []
    for r in pairs.to_dict("records"):
        bounds = gap_bounds(float(r["over_line"]), float(r["under_line"]))
        if not bounds:
            continue
        lo, hi = bounds
        key = name_key(r["Player"])
        modeled = r["market"] in MODELED_SD
        if modeled:
            vals, n = [], 0
            rate = _normal_window(lo, hi, (float(r["over_line"]) + float(r["under_line"])) / 2,
                                  MODELED_SD[r["market"]])
        else:
            vals = history.get((key, r["market"]), [])
            n = len(vals)
            rate = (sum(1 for v in vals if lo <= v <= hi) / n) if n >= MIN_GAMES else None
        one_wins = float(r["one_wins_pct"]) / 100.0          # return when exactly one leg wins
        ev = ((1 - rate) * one_wins - rate) if rate is not None else None
        avg = (sum(vals) / n) if n else None
        rows.append({
            "player": r["Player"],
            "team": None if modeled else teams.get(key),
            "market": r["market"],
            "market_label": MARKET_LABELS.get(r["market"], r["market"].replace("_", " ").title()),
            "game": f"{r.get('away_team') or ''} @ {r.get('home_team') or ''}".strip(" @"),
            "commence_time": r.get("commence_time"),
            "under_book": r["under_book"], "under_line": float(r["under_line"]),
            "under_price": float(r["under_price"]),
            "over_book": r["over_book"], "over_line": float(r["over_line"]),
            "over_price": float(r["over_price"]),
            "gap": str(lo) if lo == hi else f"{lo}-{hi}",
            "gap_width": hi - lo + 1,
            "stake_over_pct": float(r["stake_over_pct"]),
            "win_pct": round(100 * one_wins, 2),               # profit on total stake when one leg wins
            "breakeven_pct": float(r["breakeven_window_rate_pct"]),
            "games": n,
            "avg": round(avg, 1) if avg is not None else None,
            "landing_pct": round(100 * rate, 1) if rate is not None else None,
            "landing_basis": "model" if modeled else "history",
            "is_game_line": modeled,
            "ev_pct": round(100 * ev, 2) if ev is not None else None,
            "dfs_leg": r.get("dfs_leg") or "",
            "fetched_at": r.get("fetched_at"),
        })

    if not include_negative:
        rows = [x for x in rows if x["ev_pct"] is None or x["ev_pct"] > 0]
    # Priced rows by estimated return; un-priced (too little history) last.
    rows.sort(key=lambda x: (x["ev_pct"] is None, -(x["ev_pct"] or 0), -x["win_pct"]))
    stamps = sorted(str(x["fetched_at"]) for x in rows if x.get("fetched_at"))
    return {
        "lines_as_of": stamps[-1] if stamps else None,
        "oldest_line": stamps[0] if stamps else None,
        "lookback": LOOKBACK,
        "rows": rows,
    }


# ---------------------------------------------------------------------------
# Track record -- every logged gap bet, graded once its game is final.
# ---------------------------------------------------------------------------

from zoneinfo import ZoneInfo  # noqa: E402

ET = ZoneInfo("America/New_York")
GRADE_AFTER_HOURS = 4          # tip + 4h: the game is over and box scores are in

# Odds API full names -> app codes (kept here so this module has no import
# cycle with app.data.nba).
TEAM_CODES = {
    "Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN", "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI", "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN",
    "Detroit Pistons": "DET", "Golden State Warriors": "GSW", "Houston Rockets": "HOU", "Indiana Pacers": "IND",
    "Los Angeles Clippers": "LAC", "LA Clippers": "LAC", "Los Angeles Lakers": "LAL", "Memphis Grizzlies": "MEM",
    "Miami Heat": "MIA", "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NOP",
    "New York Knicks": "NYK", "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI",
    "Phoenix Suns": "PHX", "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC", "San Antonio Spurs": "SAS",
    "Toronto Raptors": "TOR", "Utah Jazz": "UTA", "Washington Wizards": "WAS",
}


def _game_date_et(commence: Any):
    ts = pd.to_datetime(commence, utc=True, errors="coerce")
    return ts.tz_convert(ET).date() if pd.notna(ts) else None


def _results_index(stats: pd.DataFrame):
    """(name key, date) -> row of stats; (team code, date) -> team points."""
    df = stats.copy()
    date_col = "date" if "date" in df.columns else "game_date"
    df["_d"] = pd.to_datetime(df[date_col], errors="coerce").dt.date
    df["_k"] = df["player"].map(name_key)
    by_player = {(k, d): r for k, d, r in zip(df["_k"], df["_d"], df.to_dict("records"))}
    team_pts = df.groupby(["team", "_d"])["pts"].sum().to_dict() if "pts" in df.columns else {}
    # history per player for flag-time landing rates, oldest first
    hist = {}
    df = df.sort_values("_d")
    for k, g in df.groupby("_k", sort=False):
        hist[k] = g
    return by_player, team_pts, hist


def _value_for(row: dict, game_date, by_player, team_pts) -> Optional[float]:
    m = row["market"]
    if m == "totals":
        away, _, home = str(row["Player"]).partition(" @ ")
        a, h = TEAM_CODES.get(away.strip()), TEAM_CODES.get(home.strip())
        if a and h and (a, game_date) in team_pts and (h, game_date) in team_pts:
            return float(team_pts[(a, game_date)] + team_pts[(h, game_date)])
        return None
    if m == "team_totals":
        t = TEAM_CODES.get(str(row["Player"]).strip())
        return float(team_pts[(t, game_date)]) if t and (t, game_date) in team_pts else None
    cols = MARKET_STATS.get(m)
    r = by_player.get((name_key(row["Player"]), game_date))
    if not cols or r is None:
        return None                       # didn't play -> books void the prop
    return float(sum(float(r.get(c) or 0) for c in cols))


def _flag_time_rate(row: dict, lo: int, hi: int, game_date, hist) -> Optional[float]:
    """Landing rate as the page would have shown it -- games BEFORE this one only."""
    m = row["market"]
    if m in MODELED_SD:
        return _normal_window(lo, hi, (float(row["over_line"]) + float(row["under_line"])) / 2, MODELED_SD[m])
    cols = MARKET_STATS.get(m)
    g = hist.get(name_key(row["Player"]))
    if not cols or g is None:
        return None
    prior = g[g["_d"] < game_date].tail(LOOKBACK)
    if len(prior) < MIN_GAMES:
        return None
    vals = prior[cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    return float(((vals >= lo) & (vals <= hi)).mean())


def _summary(graded: List[dict]) -> Dict[str, Any]:
    n = len(graded)
    if not n:
        return {"bets": 0, "one_leg_won": 0, "gap_hits": 0, "return_pct": None, "net_per_100": None}
    ret = sum(g["return"] for g in graded)
    hits = sum(1 for g in graded if g["landed_in_gap"])
    return {
        "bets": n,
        "one_leg_won": n - hits,
        "gap_hits": hits,
        "return_pct": round(100 * ret / n, 2),          # average return per $ staked
        "net_per_100": round(100 * ret, 2),             # total $ if every pair got $100
    }


def get_gap_record(recent: int = 25) -> Dict[str, Any]:
    log = get_nba_gap_log()
    empty = {"overall": _summary([]), "positive": _summary([]), "by_market": [], "recent": [],
             "since": None, "pending": 0}
    if log is None or log.empty:
        return empty
    now = pd.Timestamp.now(tz="UTC")
    start = pd.to_datetime(log["commence_time"], utc=True, errors="coerce")
    done = log[start <= now - pd.Timedelta(hours=GRADE_AFTER_HOURS)]
    pending = int((start > now - pd.Timedelta(hours=GRADE_AFTER_HOURS)).sum())
    if done.empty:
        return {**empty, "pending": pending}

    by_player, team_pts, hist = _results_index(get_nba_all_seasons())
    graded = []
    for r in done.to_dict("records"):
        b = gap_bounds(float(r["over_line"]), float(r["under_line"]))
        d = _game_date_et(r["commence_time"])
        if not b or d is None:
            continue
        lo, hi = b
        v = _value_for(r, d, by_player, team_pts)
        if v is None:
            continue
        in_gap = lo <= v <= hi
        one_wins = float(r["one_wins_pct"]) / 100.0
        rate = _flag_time_rate(r, lo, hi, d, hist)
        est = ((1 - rate) * one_wins - rate) if rate is not None else None
        graded.append({
            "date": d.isoformat(), "player": r["Player"], "market": r["market"],
            "market_label": MARKET_LABELS.get(r["market"], r["market"]),
            "gap": str(lo) if lo == hi else f"{lo}-{hi}",
            "under": f"U {r['under_line']:g} {int(r['under_price']):+d} {r['under_book']}",
            "over": f"O {r['over_line']:g} {int(r['over_price']):+d} {r['over_book']}",
            "result": v, "landed_in_gap": in_gap,
            "return": -1.0 if in_gap else one_wins,
            "est_ev_pct": round(100 * est, 2) if est is not None else None,
        })

    by_market = []
    for m in sorted({g["market"] for g in graded}):
        sub = [g for g in graded if g["market"] == m]
        by_market.append({"market": m, "market_label": MARKET_LABELS.get(m, m), **_summary(sub)})
    by_market.sort(key=lambda x: -x["bets"])
    recent_rows = sorted(graded, key=lambda g: g["date"], reverse=True)[:recent]
    return {
        "overall": _summary(graded),
        "positive": _summary([g for g in graded if (g["est_ev_pct"] or 0) > 0]),
        "by_market": by_market,
        "recent": [{k: v for k, v in g.items() if k != "return"} | {"return_pct": round(100 * g["return"], 2)}
                   for g in recent_rows],
        "since": min(g["date"] for g in graded) if graded else None,
        "pending": pending,
    }
