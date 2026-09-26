"""Next-game context for the MLB Game Log page.

Two additions ride on the existing game-log responses (see
get_mlb_game_log() / get_mlb_pitcher_game_log() in mlb.py):

* Batter log -> `next_game`: the upcoming game, lineup status, the opposing
  starter's numbers against this batter's side, the batter's own record in
  games against that hand, and the best price on the selected stat's line.

* Pitcher log -> `next_start` plus a `lineup` block on every logged game:
  opposing-lineup AVERAGES only (never nine individual hitters) --
  strikeout %, batting average, wOBA, isolated power and walk % -- for
  tonight's lineup, the lineups he has faced this season, and the league
  against his throwing hand.

Where each number comes from:

* Tonight's lineup, once posted: daily_matchups.parquet's `split_*` columns
  (Statcast, already split against THIS pitcher's hand, switch hitters
  resolved) -- the same source the Pitcher Daily Report and Props page use.
  Before it posts: "projected" = the nine hitters with the most plate
  appearances in that team's most recent game, at their season rates.
* Lineups he faced in past games: the nine opposing hitters with the most
  plate appearances in that game (batter_logs.parquet has no batting order),
  each at his SEASON rates from batter_logs.parquet. wOBA there is an
  estimate from walks/singles/doubles/triples/homers per PA -- the logs
  carry no hit-by-pitch or sacrifice-fly counts -- so it runs a few points
  off Statcast's figure; fine for comparing lineups with each other.
* League vs his hand: pitcher_splits.parquet pooled over every pitcher of
  that hand, both batter sides, weighted by batters faced.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import pandas as pd

from app.data.loader import get_mlb_data, ttl_cache, MLB_TTL
from app.data.hit_rate import grade_over_under

LINEUP_METRICS = ["k_pct", "avg", "woba", "iso", "bb_pct"]
_DIGITS = {"k_pct": 1, "bb_pct": 1, "avg": 3, "woba": 3, "iso": 3}

# Standard linear weights (FanGraphs scale). No HBP/SF in the logs, so
# denominators are plate appearances -- see module docstring.
_WOBA_W = {"bb": 0.69, "1b": 0.88, "2b": 1.25, "3b": 1.59, "hr": 2.04}

# Which lineup number matters most for each pitcher market. Drives the
# "vs lineups like tonight's" row, and the frontend's column order.
PITCHER_KEY_METRIC = {
    "pitcher_strikeouts": "k_pct",
    "pitcher_hits_allowed": "avg",
    "pitcher_earned_runs": "woba",
    "pitcher_walks": "bb_pct",
    "pitcher_outs": "woba",
    "pitcher_record_a_win": "woba",
}

# Which standout-hitter count (HITTER_FLAG_THRESHOLDS in mlb.py) to show
# next to that metric.
PITCHER_KEY_FLAG = {
    "pitcher_strikeouts": "high_k_hitter",
    "pitcher_hits_allowed": "high_avg_hitter",
    "pitcher_earned_runs": "high_woba_hitter",
    "pitcher_walks": "high_bb_hitter",
    "pitcher_outs": "high_woba_hitter",
    "pitcher_record_a_win": "high_woba_hitter",
}


def _r(metric: str, v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return round(f, _DIGITS.get(metric, 3))


def prop_line_for_threshold(threshold: float) -> Optional[float]:
    """The sportsbook line matching the page's threshold. The page grades
    `value >= threshold` (see grade_over_under), so a threshold of 1 is the
    0.5 line, 2 is 1.5, and an already-half threshold is its own line."""
    if threshold is None or threshold <= 0:
        return None
    return math.ceil(threshold) - 0.5


def _props_df() -> pd.DataFrame:
    try:
        from app.data.props import bettable_props
        return bettable_props("mlb")
    except Exception as e:  # odds are a bonus, never a reason to fail the page
        print(f"game log context: props unavailable ({e})")
        return pd.DataFrame()


def _best_prices(player: str, props_market: Optional[str], line: Optional[float],
                 team: Optional[str], sides=("over",)) -> Dict[str, Any]:
    out: Dict[str, Any] = {s: None for s in sides}
    if not props_market or line is None:
        return out
    from app.data.props import best_price_at_line
    df = _props_df()
    if df.empty:
        return out
    markets = {props_market, f"{props_market}_alternate"}
    for side in sides:
        rung = best_price_at_line(df, player, markets, line, side=side, team=team or None)
        if rung:
            out[side] = {"line": rung["line"], "price": rung["price"], "books": rung["books"]}
    return out


# ---------------------------------------------------------------------------
# Hitter season rates and per-game lineups faced
# ---------------------------------------------------------------------------

def _rates_from_totals(t: pd.DataFrame) -> pd.DataFrame:
    pa = t["plate_appearances"].where(t["plate_appearances"] > 0)
    ab = t["at_bats"].where(t["at_bats"] > 0)
    singles = t["hits"] - t["doubles"] - t["triples"] - t["home_runs"]
    out = pd.DataFrame(index=t.index)
    out["pa"] = t["plate_appearances"]
    out["avg"] = t["hits"] / ab
    out["iso"] = (t["total_bases"] - t["hits"]) / ab
    out["k_pct"] = t["strikeouts"] / pa * 100
    out["bb_pct"] = t["walks"] / pa * 100
    out["woba"] = (
        _WOBA_W["bb"] * t["walks"] + _WOBA_W["1b"] * singles + _WOBA_W["2b"] * t["doubles"]
        + _WOBA_W["3b"] * t["triples"] + _WOBA_W["hr"] * t["home_runs"]
    ) / pa
    return out


_COUNT_COLS = ["plate_appearances", "at_bats", "hits", "doubles", "triples", "home_runs",
               "walks", "strikeouts", "total_bases"]


@ttl_cache(MLB_TTL)
def _hitter_season_rates() -> pd.DataFrame:
    """player_id -> season pa/avg/iso/k_pct/bb_pct/woba from batter_logs."""
    logs = get_mlb_data().get("batter_logs", pd.DataFrame())
    if logs.empty or not set(_COUNT_COLS) <= set(logs.columns):
        return pd.DataFrame(columns=["pa"] + LINEUP_METRICS)
    sub = logs[["player_id"] + _COUNT_COLS].copy()
    for c in _COUNT_COLS:
        sub[c] = pd.to_numeric(sub[c], errors="coerce").fillna(0)
    totals = sub.groupby("player_id")[_COUNT_COLS].sum()
    totals = totals[totals["plate_appearances"] > 0]
    return _rates_from_totals(totals)


def _top_nine(game_rows: pd.DataFrame) -> pd.DataFrame:
    rows = game_rows[pd.to_numeric(game_rows["plate_appearances"], errors="coerce").fillna(0) > 0]
    return rows.sort_values("plate_appearances", ascending=False).head(9)


@ttl_cache(MLB_TTL)
def _lineups_faced() -> pd.DataFrame:
    """One row per (game_pk, batting side is_home): straight average of the
    nine hitters with the most plate appearances that game, each at his
    season rates. Straight, not PA-weighted -- same convention as the
    Pitcher Daily Report's lineup averages."""
    logs = get_mlb_data().get("batter_logs", pd.DataFrame())
    rates = _hitter_season_rates()
    cols = ["game_pk", "is_home", "batters"] + LINEUP_METRICS
    if logs.empty or rates.empty or "plate_appearances" not in logs.columns:
        return pd.DataFrame(columns=cols)
    sub = logs[["game_pk", "is_home", "player_id", "plate_appearances"]].copy()
    sub["plate_appearances"] = pd.to_numeric(sub["plate_appearances"], errors="coerce").fillna(0)
    sub = sub[sub["plate_appearances"] > 0]
    sub = sub.sort_values(["game_pk", "is_home", "plate_appearances"], ascending=[True, True, False])
    sub = sub.groupby(["game_pk", "is_home"], sort=False).head(9)
    sub = sub.join(rates[LINEUP_METRICS], on="player_id", how="inner")
    agg = sub.groupby(["game_pk", "is_home"]).agg(
        batters=("player_id", "count"), **{m: (m, "mean") for m in LINEUP_METRICS}
    ).reset_index()
    return agg[cols]


def lineup_faced_for(game_pk: Any, pitcher_is_home: Any) -> Optional[Dict[str, Any]]:
    """Averages of the lineup a pitcher faced in one game, or None."""
    faced = _lineups_faced()
    if faced.empty or pd.isna(game_pk):
        return None
    hit = faced[(faced["game_pk"] == game_pk) & (faced["is_home"] != bool(pitcher_is_home))]
    if hit.empty:
        return None
    r = hit.iloc[0]
    return {m: _r(m, r[m]) for m in LINEUP_METRICS}


# ---------------------------------------------------------------------------
# League vs a throwing hand
# ---------------------------------------------------------------------------

@ttl_cache(MLB_TTL)
def _league_vs_hand() -> Dict[str, Dict[str, Optional[float]]]:
    from app.data.mlb import _pitcher_throws_lookup
    data = get_mlb_data()
    splits = data.get("pitcher_splits", pd.DataFrame())
    out: Dict[str, Dict[str, Optional[float]]] = {}
    if splits.empty or "tbf" not in splits.columns:
        return out
    throws = _pitcher_throws_lookup(data)
    s = splits.copy()
    s["throws"] = s["player_id"].map(lambda p: throws.get(int(p)) if pd.notna(p) else None)
    for hand in ("L", "R"):
        h = s[(s["throws"] == hand) & (pd.to_numeric(s["tbf"], errors="coerce") > 0)]
        entry: Dict[str, Optional[float]] = {}
        for m in LINEUP_METRICS:
            if m not in h.columns:
                entry[m] = None
                continue
            w = h.dropna(subset=[m])
            entry[m] = _r(m, (w["tbf"] * w[m]).sum() / w["tbf"].sum()) if not w.empty else None
        out[hand] = entry
    return out


# ---------------------------------------------------------------------------
# Pitcher: next start
# ---------------------------------------------------------------------------

def _flag_counts_from_rates(rates: pd.DataFrame) -> Dict[str, int]:
    from app.data.mlb import _lineup_flag_counts
    as_split = rates.rename(columns={m: f"split_{m}" for m in LINEUP_METRICS})
    return _lineup_flag_counts(as_split)


def _projected_lineup(team: str) -> Optional[pd.DataFrame]:
    """Season rates for the nine hitters with the most plate appearances in
    `team`'s most recent logged game (team via the current roster file)."""
    data = get_mlb_data()
    rosters = data.get("mlb_rosters", pd.DataFrame())
    logs = data.get("batter_logs", pd.DataFrame())
    if rosters.empty or logs.empty or not team:
        return None
    ids = set(rosters.loc[rosters["team"] == team, "player_id"].dropna().astype(int))
    rows = logs[logs["player_id"].isin(ids)].copy()
    if rows.empty:
        return None
    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    last_pk = rows.sort_values("date").iloc[-1]["game_pk"]
    nine = _top_nine(rows[rows["game_pk"] == last_pk])
    rates = _hitter_season_rates()
    nine = nine.join(rates[LINEUP_METRICS], on="player_id", how="inner")
    return nine if not nine.empty else None


def _mean(df: pd.DataFrame, col: str, metric: str) -> Optional[float]:
    if col not in df.columns:
        return None
    vals = pd.to_numeric(df[col], errors="coerce").dropna()
    return _r(metric, vals.mean()) if len(vals) else None


def pitcher_next_start(pitcher_id: int, pitcher: str, stat: str, threshold: float,
                       graded_games: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """`graded_games`: this pitcher's filtered log rows with `stat_value`
    and per-game lineup metric columns (lineup_k_pct, ...) already attached."""
    from app.data.mlb import (HITTER_FLAG_THRESHOLDS, _lineup_flag_counts, _pitcher_throws_lookup,
                              _MLB_PROPS_MARKET_KEY, _ip_to_outs)
    data = get_mlb_data()
    probable = data.get("probable_starters", pd.DataFrame())
    if probable.empty or "pitcher_id" not in probable.columns:
        return None
    match = probable[probable["pitcher_id"] == pitcher_id]
    if match.empty:
        return None
    p = match.iloc[0]
    throws = _pitcher_throws_lookup(data).get(int(pitcher_id))
    opponent = p.get("opponent")

    matchups = data.get("matchups", pd.DataFrame())
    lineup = pd.DataFrame()
    if not matchups.empty and "pitcher_id" in matchups.columns:
        lineup = matchups[matchups["pitcher_id"] == pitcher_id]

    tonight: Dict[str, Optional[float]] = {m: None for m in LINEUP_METRICS}
    overall: Dict[str, Optional[float]] = {m: None for m in LINEUP_METRICS}
    counts: Optional[Dict[str, int]] = None
    game_time = None
    if not lineup.empty:
        status = "posted"
        for m in LINEUP_METRICS:
            tonight[m] = _mean(lineup, f"split_{m}", m)
            overall[m] = _mean(lineup, f"all_{m}", m)
        counts = _lineup_flag_counts(lineup)
        gt = lineup["game_time_utc"].dropna() if "game_time_utc" in lineup.columns else pd.Series(dtype=object)
        game_time = str(gt.iloc[0]) if len(gt) else None
        if throws is None and "throws" in lineup.columns:
            t = lineup["throws"].dropna()
            throws = t.iloc[0] if len(t) else None
    else:
        proj = _projected_lineup(opponent) if isinstance(opponent, str) else None
        status = "projected" if proj is not None else "unknown"
        if proj is not None:
            for m in LINEUP_METRICS:
                tonight[m] = _mean(proj, m, m)
                overall[m] = tonight[m]
            counts = _flag_counts_from_rates(proj[LINEUP_METRICS])

    # Average of the lineups he's actually faced (games with lineup data).
    faced_avg: Dict[str, Optional[float]] = {}
    for m in LINEUP_METRICS:
        col = f"lineup_{m}"
        faced_avg[m] = _mean(graded_games, col, m) if col in graded_games.columns else None

    # "vs lineups like tonight's": the games on the same side of his own
    # faced-average as tonight's lineup, on the stat's key metric. Uses the
    # lineup's OVERALL rates for tonight so it's measured on the same scale
    # as the past games (season rates, not a one-hand split).
    key = PITCHER_KEY_METRIC.get(stat, "woba")
    similar = None
    kcol = f"lineup_{key}"
    if overall.get(key) is not None and faced_avg.get(key) is not None and kcol in graded_games.columns:
        above = overall[key] >= faced_avg[key]
        g = graded_games.dropna(subset=[kcol])
        g = g[g[kcol] >= faced_avg[key]] if above else g[g[kcol] < faced_avg[key]]
        similar = {"side": "above" if above else "below", "metric": key,
                   **grade_over_under(g["stat_value"].tolist(), threshold)}

    # Walk rate, per nine, from his logged innings.
    walks_per_9 = None
    logs = data.get("pitcher_logs", pd.DataFrame())
    if not logs.empty:
        mine = logs[logs["pitcher_id"] == pitcher_id]
        outs = sum(_ip_to_outs(x) for x in mine["innings"])
        if outs > 0:
            walks_per_9 = round(pd.to_numeric(mine["walks"], errors="coerce").fillna(0).sum() * 27 / outs, 1)

    line = prop_line_for_threshold(threshold)
    team = p.get("team") if isinstance(p.get("team"), str) else None
    prices = _best_prices(pitcher, _MLB_PROPS_MARKET_KEY.get(stat), line, team, sides=("over", "under"))

    flag_key = PITCHER_KEY_FLAG.get(stat)
    flag_rule = HITTER_FLAG_THRESHOLDS.get(flag_key) if flag_key else None
    date = p.get("date")
    return {
        "date": str(pd.to_datetime(date).date()) if date is not None and pd.notna(date) else None,
        "game_time_utc": game_time,
        "opponent": opponent,
        "is_home": bool(p.get("is_home")) if pd.notna(p.get("is_home")) else None,
        "throws": throws,
        "lineup_status": status,          # posted | projected | unknown
        "batters": int(len(lineup)) if not lineup.empty else None,
        "tonight": tonight,               # split vs his hand when posted; season rates when projected
        "faced_avg": faced_avg,
        "league": _league_vs_hand().get(throws) if throws else None,
        "key_metric": key,
        "flag": ({"key": flag_key, "count": (counts or {}).get(flag_key),
                  "faced_avg": _mean(graded_games, "lineup_flag", "k_pct") if "lineup_flag" in graded_games.columns else None,
                  "op": flag_rule[1], "threshold": flag_rule[2]} if flag_rule else None),
        "similar": similar,
        "walks_per_9": walks_per_9,
        "line": line,
        "prices": prices,
    }


def attach_lineups_faced(rows: pd.DataFrame, stat: str) -> pd.DataFrame:
    """Add lineup_<metric> columns (and lineup_flag, the standout-hitter
    count for this stat's key flag) to a pitcher's log rows."""
    from app.data.mlb import HITTER_FLAG_THRESHOLDS
    faced = _lineups_faced()
    out = rows.copy()
    if faced.empty or "game_pk" not in out.columns:
        for m in LINEUP_METRICS:
            out[f"lineup_{m}"] = float("nan")
        return out
    opp = faced.rename(columns={m: f"lineup_{m}" for m in LINEUP_METRICS}).copy()
    opp["pitcher_is_home"] = ~opp["is_home"].astype(bool)
    opp = opp.drop(columns=["is_home", "batters"])
    out["_pih"] = out["is_home"].astype(bool)
    out = out.merge(opp, left_on=["game_pk", "_pih"], right_on=["game_pk", "pitcher_is_home"], how="left")
    out = out.drop(columns=["_pih", "pitcher_is_home"])

    # Per-game standout-hitter count for the stat's key flag.
    flag_key = PITCHER_KEY_FLAG.get(stat)
    rule = HITTER_FLAG_THRESHOLDS.get(flag_key) if flag_key else None
    if rule:
        metric = rule[0].replace("split_", "")
        counts = _flag_counts_by_game(metric, rule[1], rule[2])
        out = out.merge(counts, on=["game_pk", "is_home"], how="left") if not counts.empty else out.assign(lineup_flag=float("nan"))
    return out


@ttl_cache(MLB_TTL)
def _flag_counts_by_game(metric: str, op: str, threshold: float) -> pd.DataFrame:
    """(game_pk, PITCHER's is_home) -> how many of the nine hitters he
    faced clear one standout-hitter cutoff, at season rates."""
    logs = get_mlb_data().get("batter_logs", pd.DataFrame())
    rates = _hitter_season_rates()
    if logs.empty or rates.empty or metric not in rates.columns:
        return pd.DataFrame(columns=["game_pk", "is_home", "lineup_flag"])
    sub = logs[["game_pk", "is_home", "player_id", "plate_appearances"]].copy()
    sub["plate_appearances"] = pd.to_numeric(sub["plate_appearances"], errors="coerce").fillna(0)
    sub = sub[sub["plate_appearances"] > 0]
    sub = sub.sort_values(["game_pk", "is_home", "plate_appearances"], ascending=[True, True, False])
    sub = sub.groupby(["game_pk", "is_home"], sort=False).head(9)
    sub = sub.join(rates[[metric]], on="player_id", how="inner")
    sub["hit"] = (sub[metric] >= threshold) if op == "ge" else (sub[metric] <= threshold)
    agg = sub.groupby(["game_pk", "is_home"])["hit"].sum().reset_index(name="lineup_flag")
    agg["is_home"] = ~agg["is_home"].astype(bool)  # batting side -> pitcher side
    return agg


# ---------------------------------------------------------------------------
# Batter: next game
# ---------------------------------------------------------------------------

def batter_next_game(player_id: int, player: str, stat: str, threshold: float) -> Dict[str, Any]:
    """Upcoming game for one batter. status: in_lineup | pending (team
    plays, lineup not out) | out (lineup posted without him) | no_game."""
    from app.data.mlb import (_pitcher_throws_lookup, _mlb_batter_bats_index, _pitcher_split_stats,
                              _matchup_edge_resolved_hand, _MLB_PROPS_MARKET_KEY)
    data = get_mlb_data()
    matchups = data.get("matchups", pd.DataFrame())
    probable = data.get("probable_starters", pd.DataFrame())
    rosters = data.get("mlb_rosters", pd.DataFrame())
    starters = data.get("starters", pd.DataFrame())
    splits = data.get("pitcher_splits", pd.DataFrame())

    team = None
    bats = None
    if not rosters.empty and "player_id" in rosters.columns:
        r = rosters[rosters["player_id"] == player_id]
        if not r.empty:
            team = r.iloc[0].get("team")
            bats = r.iloc[0].get("bats") if "bats" in rosters.columns else None
    bats = _mlb_batter_bats_index().get(player_id, bats)

    out: Dict[str, Any] = {
        "status": "no_game", "team": team, "opponent": None, "is_home": None, "date": None,
        "game_time_utc": None, "batting_order": None, "pitcher": None, "pitcher_id": None,
        "throws": None, "vs_side": None, "pitcher_split": None, "pitcher_season": None,
        "line": None, "price": None,
    }

    row = None
    team_posted = False
    if not matchups.empty and "batter_id" in matchups.columns:
        hit = matchups[matchups["batter_id"] == player_id]
        row = hit.iloc[0] if not hit.empty else None
        if team and "team" in matchups.columns:
            team_posted = bool((matchups["team"] == team).any())

    pitcher_id = None
    if row is not None:
        out["status"] = "in_lineup"
        out["team"] = row.get("team") or team
        out["opponent"] = row.get("opponent")
        out["is_home"] = row.get("home_away") == "home" if row.get("home_away") in ("home", "away") else None
        out["date"] = str(row.get("date")) if pd.notna(row.get("date")) else None
        out["game_time_utc"] = str(row.get("game_time_utc")) if pd.notna(row.get("game_time_utc")) else None
        bo = row.get("batting_order")
        out["batting_order"] = int(bo) if pd.notna(bo) else None
        out["pitcher"] = row.get("pitcher")
        pitcher_id = int(row["pitcher_id"]) if pd.notna(row.get("pitcher_id")) else None
        out["throws"] = row.get("throws") if row.get("throws") in ("L", "R") else None
        side = row.get("hits_from")
        out["vs_side"] = side if side in ("L", "R") else None
    elif team and not probable.empty:
        opp = probable[probable["opponent"] == team]
        own = probable[probable["team"] == team]
        if opp.empty and own.empty:
            return out
        out["status"] = "out" if team_posted else "pending"
        src = opp.iloc[0] if not opp.empty else None
        if src is not None:
            out["opponent"] = src.get("team")
            out["is_home"] = (not bool(src.get("is_home"))) if pd.notna(src.get("is_home")) else None
            out["date"] = str(pd.to_datetime(src.get("date")).date()) if pd.notna(src.get("date")) else None
            out["pitcher"] = src.get("pitcher")
            pitcher_id = int(src["pitcher_id"]) if pd.notna(src.get("pitcher_id")) else None
            out["throws"] = _pitcher_throws_lookup(data).get(pitcher_id) if pitcher_id is not None else None
        else:
            o = own.iloc[0]
            out["opponent"] = o.get("opponent")
            out["is_home"] = bool(o.get("is_home")) if pd.notna(o.get("is_home")) else None
            out["date"] = str(pd.to_datetime(o.get("date")).date()) if pd.notna(o.get("date")) else None
        out["vs_side"] = _matchup_edge_resolved_hand(bats, out["throws"])
    else:
        return out

    out["pitcher_id"] = pitcher_id
    if pitcher_id is not None:
        if out["vs_side"]:
            out["pitcher_split"] = _pitcher_split_stats(splits, pitcher_id, out["vs_side"]) or None
        if not starters.empty and "pitcher_id" in starters.columns:
            s = starters[starters["pitcher_id"] == pitcher_id]
            if not s.empty:
                s = s.iloc[0]
                gs = s.get("games_started")
                ip = s.get("innings")
                season = {"games_started": int(gs) if pd.notna(gs) else None,
                          "era": float(s["era"]) if pd.notna(s.get("era")) else None}
                try:
                    from app.data.mlb import _ip_to_outs
                    outs = _ip_to_outs(ip)
                    season["ip_per_start"] = round(outs / 3 / gs, 1) if gs and outs else None
                except Exception:
                    season["ip_per_start"] = None
                out["pitcher_season"] = season

    line = prop_line_for_threshold(threshold)
    out["line"] = line
    out["price"] = _best_prices(player, _MLB_PROPS_MARKET_KEY.get(stat), line, out["team"])["over"]
    return out


def batter_vs_hand(rows: pd.DataFrame, hand: Optional[str], threshold: float) -> Optional[Dict[str, Any]]:
    """This batter's record in games against starters of `hand`: hit rate
    against the current threshold plus AVG / OBP / SLG / K% from the box
    scores. OBP here is (H + BB) / PA -- no HBP in the logs."""
    if hand not in ("L", "R") or rows.empty or "throws" not in rows.columns:
        return None
    g = rows[rows["throws"] == hand]
    if g.empty:
        return {"hand": hand, "games": 0, **grade_over_under([], threshold)}
    def tot(c):
        return float(pd.to_numeric(g[c], errors="coerce").fillna(0).sum()) if c in g.columns else 0.0
    ab, pa, h, bb, so, tb = tot("at_bats"), tot("plate_appearances"), tot("hits"), tot("walks"), tot("strikeouts"), tot("total_bases")
    return {
        "hand": hand,
        "games": int(len(g)),
        **grade_over_under(g["stat_value"].tolist(), threshold),
        "avg": round(h / ab, 3) if ab else None,
        "obp": round((h + bb) / pa, 3) if pa else None,
        "slg": round(tb / ab, 3) if ab else None,
        "k_pct": round(so / pa * 100, 1) if pa else None,
    }
