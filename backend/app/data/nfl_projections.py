"""NFL Projections page.

Everything heavy (the 4,000-run simulation of each game, the direct models)
happens in get_nfl_projections.py once a day. Here we only re-price: player
projections are compared with the CURRENT props board (refreshed through the
day by get_props.py) and the injury report, so a line move or a late
scratch shows up without waiting for the next pipeline run.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from app import nfl_projection_edges as E
from app.config import settings
from app.data.loader import _fetch_bytes, get_injuries_data, get_props_data, ttl_cache
from app.props_config import DFS_BOOKS, SHARP_BOOKS, UNBETTABLE_BOOKS

EXCLUDE_BOOKS = set(UNBETTABLE_BOOKS | SHARP_BOOKS | DFS_BOOKS)
RULED_OUT = {"Out", "Doubtful", "IR", "Injured Reserve", "PUP", "Suspended"}


def _json(name: str) -> Optional[dict]:
    try:
        return json.loads(_fetch_bytes(f"{settings.NFL_BASE_URL}/{name}"))
    except Exception:          # noqa: BLE001 -- not published yet
        return None


@ttl_cache(600)
def get_projection_bundle() -> Optional[dict]:
    return _json("nfl_projections.json")


@ttl_cache(600)
def get_projection_record() -> Dict[str, Any]:
    return _json("nfl_projection_record.json") or {"accuracy": None, "plays": None, "watch": None,
                                                    "by_market": [], "recent": []}


def _live_status() -> Dict[str, tuple]:
    try:
        inj = get_injuries_data("nfl")
    except Exception:          # noqa: BLE001
        return {}
    if inj is None or inj.empty or "gsis_id" not in inj.columns:
        return {}
    return {r.gsis_id: (r.status, getattr(r, "detail", None)) for r in inj.itertuples() if r.gsis_id}


def get_projections(game_id: Optional[str] = None) -> Dict[str, Any]:
    b = get_projection_bundle()
    if not b:
        return {"season": None, "week": None, "games": [], "players": [], "best_bets": [], "watch": []}
    cal = b.get("calibration") or {}
    try:
        props = get_props_data("nfl")
    except Exception:          # noqa: BLE001
        props = None
    lines = E.main_lines(props, EXCLUDE_BOOKS, E.MARKETS) if props is not None and not props.empty else {}
    tds = E.td_prices(props, EXCLUDE_BOOKS) if props is not None and not props.empty else {}
    status = _live_status()

    players = []
    for p in b["players"]:
        if game_id and p["game_id"] != game_id:
            continue
        p = dict(p)
        if p["player_id"] in status:
            p["status"], p["injury"] = status[p["player_id"]]
        p["ruled_out"] = p.get("status") in RULED_OUT
        p["lines"] = {} if p["ruled_out"] else E.edges_for(p["player"], p["projection"], lines, tds, cal, p["position"])
        players.append(p)
    games = [g for g in b["games"] if not game_id or g["game_id"] == game_id]
    stamps = [e.get("fetched_at") for p in players for e in p["lines"].values() if e.get("fetched_at")]
    return {
        "season": b["season"], "week": b["week"], "generated_at": b["generated_at"],
        "lines_as_of": max(stamps) if stamps else None,
        "games": games, "players": players,
        "best_bets": E.best_bets(players, "bet"), "watch": E.best_bets(players, "watch"),
        "accuracy": cal.get("accuracy"), "fit_on": cal.get("fit_on"),
        "min_ev": E.MIN_EV, "min_prob_edge": E.MIN_PROB_EDGE,
    }
