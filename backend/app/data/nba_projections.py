"""NBA Projections page: Shawn's stat model with editable minutes.

The daily pipeline (get_nba_projections.py) publishes tonight's players with
every feature EXCEPT minutes, plus the seven trained models (2.6 MB). Here we
fill in minutes -- the default, or whatever the user typed -- and run the
models, so an edit costs one prediction call per team, not a rebuild.

The injury report is re-read at request time (it refreshes every 15 min,
the slate twice a day): anyone newly ruled out drops to 0 and default
minutes are recomputed by the same minutes model. Teammates' usage is
recomputed from whoever has minutes > 0, so zeroing a player out shifts
his usage to the others -- learned, not a fixed scale-up.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Dict, List, Optional

import pandas as pd

from app import nba_projection_edges as E
from app import nba_projection_features as F
from app.data.loader import _fetch_bytes, _load, get_injuries_data, get_props_data, ttl_cache
from app.config import settings
from app.props_config import DFS_BOOKS, SHARP_BOOKS, UNBETTABLE_BOOKS

STAT_ORDER = ["PTS", "REB", "AST", "3PM", "STL", "BLK", "TOV"]
EXCLUDE_BOOKS = set(UNBETTABLE_BOOKS | SHARP_BOOKS | DFS_BOOKS)


@ttl_cache(600)
def get_projection_slate() -> pd.DataFrame:
    return _load(f"{settings.NBA_BASE_URL}/nba_projection_slate.parquet", pd.read_parquet, "nba projection slate")


@ttl_cache(600)
def get_projection_log() -> pd.DataFrame:
    return _load(f"{settings.NBA_BASE_URL}/nba_projection_log.parquet", pd.read_parquet, "nba projection log")


@ttl_cache(600)
def get_projection_plays() -> pd.DataFrame:
    return _load(f"{settings.NBA_BASE_URL}/nba_projection_plays.parquet", pd.read_parquet, "nba projection plays")


_models_lock = threading.Lock()
_models: Dict[str, Any] = {"trained_at": None, "models": None, "minutes": None, "meta": None, "calibration": {}}


def _boosters():
    """Stat models + minutes model, rebuilt only when the published file changes."""
    import lightgbm as lgb
    raw = json.loads(_fetch_bytes(f"{settings.NBA_BASE_URL}/nba_projection_model.json"))
    with _models_lock:
        if _models["trained_at"] != raw.get("trained_at"):
            _models["models"] = {s: (lgb.Booster(model_str=v["model"]), v["features"], bool(v.get("per_minute")))
                                 for s, v in raw["models"].items()}
            mm = raw.get("minutes_model")
            _models["minutes"] = lgb.Booster(model_str=mm["model"]) if mm else None
            _models["meta"] = {k: raw.get(k) for k in ("trained_at", "trained_through", "rows", "holdout_mae",
                                                       "holdout_days", "calibration_days", "uses_vegas",
                                                       "minutes_holdout_mae")}
            _models["calibration"] = raw.get("calibration") or {}
            _models["trained_at"] = raw.get("trained_at")
        return _models["models"], _models["meta"]


@ttl_cache(600)
def _cached_boosters():
    return _boosters()


def _live_status(slate: pd.DataFrame) -> pd.DataFrame:
    """Re-apply the injury report (refreshed every 15 min) and recompute
    default minutes with the same model the pipeline used."""
    s = slate.copy()
    try:
        inj = get_injuries_data("nba")
    except Exception:
        inj = None
    if inj is not None and not inj.empty:
        st = {E.match_key(r.player): (r.status, getattr(r, "detail", None)) for r in inj.itertuples()}
        live = s["PLAYER"].map(lambda p: st.get(E.match_key(p), (None, None)))
        s["status"] = [x[0] for x in live]
        s["injury"] = [x[1] for x in live]
        s["out"] = s["status"] == "Out"
    _cached_boosters()
    mb = _models.get("minutes")
    if mb is not None and all(c in s.columns for c in ("ew", "last", "l3")):
        s["default_min"] = F.model_minutes(s, mb)
    else:
        s["default_min"] = F.default_minutes(s)
    return s


def _predict(slate: pd.DataFrame, minutes: pd.Series) -> pd.DataFrame:
    models, _ = _cached_boosters()
    return F.predict_stats(models, slate, minutes)


@ttl_cache(600)
def default_projections() -> Dict[str, Any]:
    """Tonight's projections at default minutes, keyed by match_key(player):
    {"stats": {PTS: .., REB: .., ...}, "min": ..}, plus the calibration the
    chances come from. For other pages (Gap Bets) that want the model's view
    without running the whole projections response."""
    slate = get_projection_slate()
    if slate is None or slate.empty:
        return {"players": {}, "calibration": {}}
    slate = _live_status(slate).reset_index(drop=True)
    proj = _predict(slate, slate["default_min"])
    players = {}
    for i, r in slate.iterrows():
        players[E.match_key(r["PLAYER"])] = {
            "min": float(r["default_min"]),
            "out": bool(r.get("out")),
            "stats": {s: float(proj.loc[i, s]) for s in F.TARGETS},
        }
    return {"players": players, "calibration": _models.get("calibration") or {}}


def _scaled(p, minutes, used) -> Optional[Dict[str, float]]:
    if minutes is None or pd.isna(minutes) or not used or used <= 0:
        return None
    return {s: float(p[s]) * float(minutes) / float(used) for s in F.TARGETS}


def get_projections(game_id: Optional[int] = None, minutes: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    slate = get_projection_slate()
    empty = {"date": None, "model": None, "lines_as_of": None, "games": []}
    if slate is None or slate.empty:
        return empty
    slate = _live_status(slate)
    if game_id is not None:
        slate = slate[slate["espn_game_id"] == int(game_id)]
        if slate.empty:
            return empty
    slate = slate.reset_index(drop=True)

    overrides = {E.match_key(k): float(v) for k, v in (minutes or {}).items() if v is not None}
    used = slate.apply(lambda r: max(0.0, min(48.0, overrides.get(E.match_key(r["PLAYER"]), r["default_min"]))), axis=1)
    proj = _predict(slate, used)

    try:
        lines = E.main_lines(get_props_data("nba"), EXCLUDE_BOOKS)
    except Exception:
        lines = {}
    _, meta = _cached_boosters()

    games = []
    for gid, g in slate.groupby("espn_game_id", sort=False):
        first = g.iloc[0]
        teams = []
        for team in (first["away"], first["home"]):
            rows = []
            tg = g[g["TEAM"] == team]
            for i, r in tg.iterrows():
                p = proj.loc[i]
                stats = {s: round(float(p[s]), 1) for s in STAT_ORDER}
                stats["PRA"] = round(stats["PTS"] + stats["REB"] + stats["AST"], 1)
                rows.append({
                    "player": r["PLAYER"],
                    "status": r["status"], "injury": r["injury"],
                    "default_min": float(r["default_min"]), "minutes": round(float(used[i]), 1),
                    "edited": E.match_key(r["PLAYER"]) in overrides,
                    "projection": stats,
                    # unedited players: a flag must also hold at his recent minutes
                    "lines": E.edges_for(r["PLAYER"], {s: float(p[s]) for s in F.TARGETS}, lines,
                                         _models.get("calibration"),
                                         None if E.match_key(r["PLAYER"]) in overrides
                                         else _scaled(p, r.get("ew"), used[i])),
                })
            rows.sort(key=lambda x: (-x["minutes"], x["player"]))
            teams.append({"team": team, "home": team == first["home"],
                          "minutes_total": round(sum(x["minutes"] for x in rows), 1), "players": rows})
        games.append({"game_id": int(gid), "start_utc": first["start_utc"],
                      "away": first["away"], "home": first["home"], "teams": teams})
    games.sort(key=lambda x: x["start_utc"] or "")
    stamps = [e.get("fetched_at") for g in games for t in g["teams"] for p in t["players"]
              for e in p["lines"].values() if e.get("fetched_at")]
    return {
        "date": str(pd.Timestamp(slate["GAME DATE"].iloc[0]).date()),
        "model": meta,
        "lines_as_of": max(stamps) if stamps else None,
        "thresholds": E.THRESHOLDS,
        "min_ev": E.MIN_EV,
        "games": games,
    }


# ---------------------------------------------------------------------------
# Track record
# ---------------------------------------------------------------------------

def _american_profit(price: float) -> float:
    return price / 100.0 if price > 0 else 100.0 / abs(price)


def get_projection_record() -> Dict[str, Any]:
    """Default-minutes projections and threshold plays, graded against box scores."""
    from app.data.loader import get_nba_all_seasons
    log, plays = get_projection_log(), get_projection_plays()
    stats = get_nba_all_seasons()
    out: Dict[str, Any] = {"accuracy": None, "plays": None, "by_market": [], "recent": []}
    if stats is None or stats.empty:
        return out
    st = stats.copy()
    st["_d"] = pd.to_datetime(st["date"] if "date" in st.columns else st["game_date"]).dt.normalize()
    st["_k"] = st["player"].map(E.match_key)
    col = {"PTS": "pts", "REB": "reb", "AST": "ast", "3PM": "3pm", "STL": "stl", "BLK": "blk", "TOV": "tov"}
    actual = st.set_index(["_k", "_d"])

    if log is not None and not log.empty:
        lg = log.copy()
        lg["_k"] = lg["PLAYER"].map(E.match_key)
        lg["_d"] = pd.to_datetime(lg["GAME DATE"]).dt.normalize()
        j = lg.join(actual[[c for c in col.values() if c in actual.columns] + ["min"]], on=["_k", "_d"], how="inner")
        if not j.empty:
            out["accuracy"] = {
                "games": int(len(j)), "since": str(j["_d"].min().date()),
                "minutes_mae": round(float((j["default_min"] - j["min"]).abs().mean()), 2),
                "mae": {s: round(float((j[s] - j[c]).abs().mean()), 2) for s, c in col.items() if c in j.columns},
            }

    if plays is not None and not plays.empty:
        pl = plays.copy()
        pl["_k"] = pl["PLAYER"].map(E.match_key)
        pl["_d"] = pd.to_datetime(pl["GAME DATE"]).dt.normalize()
        j = pl.join(actual[[c for c in col.values() if c in actual.columns]], on=["_k", "_d"], how="inner")
        graded = []
        for r in j.to_dict("records"):
            v = float(sum(r[col[s]] for s in E.MARKETS[r["market"]]))
            if v == r["line"]:
                res, ret = "push", 0.0
            else:
                won = (v > r["line"]) == (r["side"] == "over")
                res, ret = ("win", _american_profit(r["price"])) if won else ("loss", -1.0)
            graded.append({"date": str(r["_d"].date()), "player": r["PLAYER"], "market": r["market"],
                           "label": E.LABELS[r["market"]], "side": r["side"], "line": r["line"],
                           "price": r["price"], "book": r["book"], "projection": r["projection"],
                           "result": v, "outcome": res, "units": round(ret, 3)})

        def summ(rows):
            dec = [g for g in rows if g["outcome"] != "push"]
            if not rows:
                return None
            return {"plays": len(rows), "wins": sum(g["outcome"] == "win" for g in rows),
                    "losses": sum(g["outcome"] == "loss" for g in rows),
                    "win_pct": round(100 * sum(g["outcome"] == "win" for g in dec) / len(dec), 1) if dec else None,
                    "units": round(sum(g["units"] for g in rows), 2),
                    "roi_pct": round(100 * sum(g["units"] for g in rows) / len(rows), 1)}

        out["plays"] = summ(graded)
        out["by_market"] = [{"market": m, "label": E.LABELS[m], **summ([g for g in graded if g["market"] == m])}
                            for m in sorted({g["market"] for g in graded})]
        out["recent"] = sorted(graded, key=lambda g: g["date"], reverse=True)[:25]
    return out
