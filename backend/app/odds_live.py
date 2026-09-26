"""Live price check for the "Bet this" sheet.

The scheduled props pull can be an hour old. When someone taps "Bet this",
this fetches that ONE market for that ONE game from The Odds API, so the
sheet shows the price that's actually up right now, plus the book's bet-slip
link.

COST: 1 credit per call (cost = unique markets returned x regions, and the
ten named books bill as one region). Results are cached for CACHE_SECONDS per
(game, market), shared by every user, so ten people tapping the same prop in
the same few minutes cost one credit. If the key is missing, the quota is
low, or the call fails, it falls back to the scheduled pull's price and says
so -- the sheet always works.
"""

from __future__ import annotations

import threading
import time
import unicodedata
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from app.config import settings
from app.data.loader import get_props_data
from app.props_config import (
    BOOKMAKERS, NO_SINGLE_BET_BOOKS, SHARP_BOOKS, SPORTS, UNBETTABLE_BOOKS,
)

API_BASE = "https://api.the-odds-api.com/v4"
CACHE_SECONDS = 180
MIN_REMAINING = 5000
TIMEOUT = 15

_cache: Dict[tuple, tuple] = {}
_lock = threading.Lock()
_remaining: Dict[str, Optional[int]] = {"value": None}


def _key(name: Any) -> str:
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower().replace(".", "").replace("'", "")
    return " ".join(p for p in s.split() if p not in {"jr", "sr", "ii", "iii", "iv", "v"})


def props_market(market: str) -> str:
    """Any spelling -> the props-file key: 'batter_hits' -> 'hits',
    'player_receptions' -> 'receptions'. Pitcher markets keep their prefix,
    matching get_props.py's strip_prefixes."""
    m = str(market or "")
    for pre in ("batter_", "player_"):
        if m.startswith(pre):
            return m[len(pre):]
    return m


def api_market(sport: str, market: str) -> str:
    """Props-file key -> The Odds API key."""
    m = props_market(market)
    if m.startswith("pitcher_"):
        return m
    return ("batter_" if sport == "mlb" else "player_") + m


def _fill_state(link: Optional[str], state: Optional[str]) -> Optional[str]:
    """Some books' links are state-specific. If a link carries a {state}
    placeholder, fill it with the user's state; otherwise leave it as is."""
    if not link or not isinstance(link, str):
        return None
    if "{state}" in link:
        return link.replace("{state}", (state or "").lower()) if state else None
    return link


def resolve_event(sport: str, player: str, market: str, event_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """The game this prop belongs to, from the props file: the soonest one
    that hasn't started, for this player and market."""
    df = get_props_data(sport)
    if df.empty:
        return None
    pm = props_market(market)
    base = pm.replace("_alternate", "")
    m = df[df["market"].astype(str).isin([base, f"{base}_alternate"])
           & (df["Player"].map(_key) == _key(player))]
    if event_id:
        m = m[m["event_id"].astype(str) == str(event_id)]
    if m.empty:
        return None
    start = pd.to_datetime(m["commence_time"], utc=True, errors="coerce")
    m = m.assign(_start=start).sort_values("_start")
    r = m.iloc[0]
    return {"event_id": str(r["event_id"]), "commence_time": str(r["commence_time"]),
            "home_team": r.get("home_team"), "away_team": r.get("away_team"),
            "started": bool(pd.notna(r["_start"]) and r["_start"] <= pd.Timestamp.now(tz="UTC"))}


def _fetch(sport: str, event_id: str, market_key: str) -> Optional[Dict[str, Any]]:
    """One live call, cached. None on any failure."""
    ck = (sport, event_id, market_key)
    now = time.time()
    with _lock:
        hit = _cache.get(ck)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    if not settings.ODDS_API_KEY:
        return None
    if _remaining["value"] is not None and _remaining["value"] < MIN_REMAINING:
        return None
    try:
        r = requests.get(
            f"{API_BASE}/sports/{SPORTS[sport].key}/events/{event_id}/odds",
            params={"apiKey": settings.ODDS_API_KEY, "bookmakers": ",".join(BOOKMAKERS),
                    "markets": market_key, "oddsFormat": "american", "dateFormat": "iso",
                    "includeLinks": "true"},
            timeout=TIMEOUT,
        )
        rem = r.headers.get("x-requests-remaining")
        if rem is not None:
            _remaining["value"] = int(float(rem))
        if r.status_code != 200:
            return None
        payload = r.json()
    except Exception as e:
        print(f"Warning: live odds fetch failed: {e}")
        return None
    data = {"payload": payload, "fetched_at": pd.Timestamp.now(tz="UTC").isoformat()}
    with _lock:
        _cache[ck] = (now, data)
    return data


def parse_offers(payload: Dict[str, Any], player: str, line: Optional[float], side: str) -> List[Dict[str, Any]]:
    """Every bettable book's price (and link) for one player/line/side."""
    want = {"over": ("Over", "Yes"), "under": ("Under", "No")}[side]
    pk = _key(player)
    out = []
    for book in payload.get("bookmakers", []) or []:
        bk = str(book.get("key", "")).lower()
        if bk in UNBETTABLE_BOOKS or bk in NO_SINGLE_BET_BOOKS or bk in SHARP_BOOKS:
            continue
        for market in book.get("markets", []) or []:
            for o in market.get("outcomes", []) or []:
                if o.get("name") not in want or _key(o.get("description")) != pk:
                    continue
                pt = o.get("point")
                if line is not None and (pt is None or abs(float(pt) - float(line)) > 1e-9):
                    continue
                out.append({"book": bk, "price": o.get("price"),
                            "link": o.get("link") or market.get("link") or book.get("link")})
    out.sort(key=lambda x: x["price"] if x["price"] is not None else -1e9, reverse=True)
    return out


def _scheduled_offers(sport: str, event_id: str, player: str, market: str,
                      line: Optional[float], side: str) -> List[Dict[str, Any]]:
    df = get_props_data(sport)
    if df.empty:
        return []
    pm = props_market(market).replace("_alternate", "")
    m = df[(df["event_id"].astype(str) == event_id)
           & df["market"].astype(str).isin([pm, f"{pm}_alternate"])
           & (df["Player"].map(_key) == _key(player))]
    if line is not None:
        m = m[pd.to_numeric(m["Line"], errors="coerce").sub(float(line)).abs() < 1e-9]
    col, link = ("Over Price", "Over Link") if side == "over" else ("Under Price", "Under Link")
    out = []
    for r in m.to_dict(orient="records"):
        bk = str(r["bookmakers"]).lower()
        if bk in UNBETTABLE_BOOKS or bk in NO_SINGLE_BET_BOOKS or bk in SHARP_BOOKS:
            continue
        p = pd.to_numeric(r.get(col), errors="coerce")
        if pd.isna(p):
            continue
        out.append({"book": bk, "price": int(p), "link": r.get(link) if isinstance(r.get(link), str) else None})
    best: Dict[str, Dict[str, Any]] = {}
    for o in out:
        if o["book"] not in best or o["price"] > best[o["book"]]["price"]:
            best[o["book"]] = o
    return sorted(best.values(), key=lambda x: x["price"], reverse=True)


def get_quote(sport: str, player: str, market: str, line: Optional[float], side: str,
              book: Optional[str] = None, event_id: Optional[str] = None,
              state: Optional[str] = None) -> Dict[str, Any]:
    """The current price for a bet, at `book` and at the best book."""
    ev = resolve_event(sport, player, market, event_id)
    if ev is None:
        return {"ok": False, "reason": "not_found"}
    if ev["started"]:
        return {"ok": False, "reason": "started", **ev}

    offers: List[Dict[str, Any]] = []
    source, fetched_at = "scheduled", None
    base_key = api_market(sport, props_market(market).replace("_alternate", ""))
    for mk in (base_key, f"{base_key}_alternate"):
        live = _fetch(sport, ev["event_id"], mk)
        if live is None:
            break
        offers = parse_offers(live["payload"], player, line, side)
        source, fetched_at = "live", live["fetched_at"]
        if offers:
            break
    if not offers:
        offers = _scheduled_offers(sport, ev["event_id"], player, market, line, side)
        source = "scheduled" if offers else source

    for o in offers:
        o["link"] = _fill_state(o.get("link"), state)
    at_book = next((o for o in offers if book and o["book"] == str(book).lower()), None)
    return {
        "ok": bool(offers), "reason": None if offers else "no_price",
        **ev, "source": source, "fetched_at": fetched_at,
        "at_book": at_book, "best": offers[0] if offers else None, "offers": offers,
    }
