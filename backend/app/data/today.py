"""Today: the strongest signals from every page, in one ranked feed.

Each item has the same shape so the page can render and filter them without
knowing where they came from:

    {id, type, sport, title, subtitle, notes: [..], badge, score, time,
     link, bet}

`type`  injury | ev | alt | weather | middle | hot
`score` ranks items across types (bigger = higher on the page). Injuries lead
        (they're the most time-sensitive), then edges by size.
`bet`   the fields the "Bet this" sheet needs, for items you can bet
        directly (EV plays and the best Alt-Line rung); None otherwise.

Every section is built independently and wrapped in try/except: one broken
source (a missing file, a schema change) drops that section, never the page.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from app.data.loader import ttl_cache

EV_PER_SPORT = 6

# ── long shots ───────────────────────────────────────────────────────────
# A +400 bet can be +EV and still lose 8 of 10 times; a feed that leads with
# those bleeds a bankroll before the edge shows up. So instead of banning
# them, Today holds long shots to a higher standard, caps how many appear,
# labels them, and sizes them smaller:
#
#   standard   -250 .. +250   normal rules
#   long shot  +251 .. +600   must ALSO pass the long-shot checks below
#   over +600                 not on Today (still on the EV Finder/Alt pages)
#   under -250                not on Today (too little payout to matter)
STANDARD_MIN_PRICE = -250
STANDARD_MAX_PRICE = 250
LONGSHOT_MAX_PRICE = 600
LONGSHOT_PER_SPORT = 2
# EV Finder long shots: the fair price must come from Pinnacle, or from at
# least 3 other books -- a thin consensus is too easy to be wrong on a long
# price -- and the edge must clear this bar.
LONGSHOT_EV_MIN_BOOKS = 3
LONGSHOT_MIN_EV = 6.0
# Alt-Line long shots: a real sample, AND both the season and last-10 hit
# rates above the implied chance by this margin (points) -- a hot streak alone
# doesn't qualify, and neither does a season number he isn't living up to now.
LONGSHOT_ALT_MIN_GAMES = 20
LONGSHOT_ALT_MARGIN = 5.0

# Suggested stake, as a % of bankroll: quarter-Kelly, capped. Kelly sizes a
# bet by edge relative to payout, so long shots come out small on their own;
# the caps keep one bad estimate from mattering much.
KELLY_FRACTION = 0.25
STAKE_CAP_STANDARD = 2.0
STAKE_CAP_LONGSHOT = 0.5

# Edges above this are ranked as if they were this big: a bigger number is
# more often a stale price than a better bet, so it shouldn't jump the queue.
EV_RANK_CAP = 12.0
ALT_PER_SPORT = 4
MIDDLES_PER_SPORT = 3
HOT_HITTERS = 3
WINDY_MPH = 12
WEATHER_ITEMS = 4


def _fmt_odds(p: Any) -> str:
    try:
        p = int(p)
    except (TypeError, ValueError):
        return "—"
    return f"+{p}" if p > 0 else str(p)


def _pretty_market(m: str) -> str:
    m = str(m or "")
    for pre in ("batter_", "player_"):
        if m.startswith(pre):
            m = m[len(pre):]
    return m.replace("_alternate", " (alt)").replace("_", " ")


def tier(price: int) -> Optional[str]:
    """standard | longshot | None (not shown on Today)."""
    if STANDARD_MIN_PRICE <= price <= STANDARD_MAX_PRICE:
        return "standard"
    if STANDARD_MAX_PRICE < price <= LONGSHOT_MAX_PRICE:
        return "longshot"
    return None


def stake_pct(p: float, price: int, kind: str) -> float:
    """Quarter-Kelly stake as % of bankroll for win chance `p` at `price`,
    capped by tier. 0 if there's no edge."""
    b = (100 / -price) if price < 0 else price / 100      # profit per unit
    k = (p * (b + 1) - 1) / b if b > 0 else 0.0
    cap = STAKE_CAP_LONGSHOT if kind == "longshot" else STAKE_CAP_STANDARD
    return round(max(0.0, min(k * KELLY_FRACTION * 100, cap)), 2)


def ev_longshot_ok(r: Dict[str, Any]) -> bool:
    return (r["ev_pct"] >= LONGSHOT_MIN_EV
            and (r.get("source") == "sharp" or (r.get("consensus_books") or 0) >= LONGSHOT_EV_MIN_BOOKS))


def _pct(sample: Any) -> Optional[tuple]:
    try:
        h, n = str(sample).split("/")
        return int(h), int(n)
    except (ValueError, AttributeError):
        return None


def alt_longshot_ok(rung: Dict[str, Any]) -> bool:
    season, recent = _pct(rung.get("season_sample")), _pct(rung.get("recent_sample"))
    if not season or not recent or season[1] < LONGSHOT_ALT_MIN_GAMES or recent[1] == 0:
        return False
    bar = rung["implied_pct"] + LONGSHOT_ALT_MARGIN
    return season[0] / season[1] * 100 >= bar and recent[0] / recent[1] * 100 >= bar


def _risk(kind: str, p: float, price: int) -> Dict[str, Any]:
    return {"tier": kind, "stake_pct": stake_pct(p, price, kind)}


def _safe(label: str, fn: Callable[[], List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    try:
        return fn()
    except Exception as e:
        print(f"Warning: Today section '{label}' failed: {e}")
        return []


# ── sections ─────────────────────────────────────────────────────────────

def _injuries() -> List[Dict[str, Any]]:
    from app.data.injuries import get_injury_feed, SERIOUS
    out = []
    for sport in ("nfl", "nba", "mlb"):
        for c in get_injury_feed(sport):
            notes: List[str] = []
            for v in ((c.get("impact") or {}).get("volume") or []):
                label = "target share" if v["kind"] == "targets" else "carry share"
                for b in v["beneficiaries"]:
                    moved = [ln for ln in b.get("lines", []) if ln.get("moved") == 0]
                    tail = (f" · {_pretty_market(moved[0]['market'])} line still {moved[0]['now']:g}"
                            if moved else "")
                    notes.append(f"{b['player']}: {label} {b['share']:g}% → ~{b['est_share']:g}%{tail}")
            for b in ((c.get("impact") or {}).get("beneficiaries") or []):
                notes.append(f"{b['player']}: minutes {b['with']} → {b['without']} without him "
                             f"({b['games_without']} games)")
            serious = c["new_status"] in SERIOUS
            old = c.get("old_status") or "not listed"
            out.append({
                "id": f"inj|{sport}|{c['player']}|{c['detected_at']}",
                "type": "injury", "sport": sport,
                "title": f"{c['player']}: {old} → {c['new_status']}",
                "subtitle": " · ".join(x for x in (c.get("team"), c.get("position"), c.get("detail")) if x),
                "notes": notes,
                "badge": "Ruled out" if c["new_status"] == "Out" else c["new_status"],
                "score": 1000 + (100 if serious else 0) + (50 if notes else 0),
                "time": c["detected_at"],
                "link": f"/{sport}/in-out" if sport in ("nfl", "nba") else None,
                "bet": None,
            })
    return out


def _ev() -> List[Dict[str, Any]]:
    from app.data.ev import get_ev
    out = []
    for sport in ("nfl", "mlb"):
        picked, longshots = [], 0
        for r in get_ev(sport):
            if r.get("suspicious"):
                continue
            kind = tier(r["price"])
            if kind is None:
                continue
            if kind == "longshot":
                if longshots >= LONGSHOT_PER_SPORT or not ev_longshot_ok(r):
                    continue
                longshots += 1
            picked.append((r, kind))
            if len(picked) >= EV_PER_SPORT:
                break
        for r, kind in picked:
            side = ("Over" if r["side"] == "over" else "Under") if r["line"] is not None else \
                ("Yes" if r["side"] == "over" else "No")
            line = f" {r['line']:g}" if r["line"] is not None else ""
            risk = _risk(kind, r["fair_pct"] / 100, r["price"])
            out.append({
                "id": f"ev|{sport}|{r['event_id']}|{r['player']}|{r['market']}|{r['line']}|{r['side']}",
                "type": "ev", "sport": sport,
                "title": f"{r['player']} {side}{line} {_pretty_market(r['market'])} {_fmt_odds(r['price'])}",
                "subtitle": f"{r['book']} · fair {_fmt_odds(r['fair_price'])} ({r['fair_pct']:g}%) · edge +{r['ev_pct']:.1f}%",
                "notes": [f"Also +EV at {o['book']} {_fmt_odds(o['price'])}" for o in r.get("other_books", [])[:2]],
                "badge": f"+{r['ev_pct']:.1f}% EV",
                # Long shots rank below standard plays with the same edge.
                "score": 500 + min(r["ev_pct"], EV_RANK_CAP) * 10 - (40 if kind == "longshot" else 0),
                "time": r.get("fetched_at"),
                "link": f"/betting/ev?sport={sport}",
                "risk": risk,
                "bet": {"sport": sport, "event_id": r["event_id"], "player": r["player"],
                        "market": r["market"], "line": r["line"], "side": r["side"],
                        "book": r["book"], "price": r["price"], "tool": "ev",
                        "commence_time": r.get("commence_time")},
            })
    return out


def _alt() -> List[Dict[str, Any]]:
    from app.data import mlb, nfl
    from app.data.alt_value import get_alt_value
    out = []
    for sport, fn in (("mlb", mlb.get_mlb_hit_rate_sheet), ("nfl", nfl.get_nfl_hit_rate_sheet)):
        # For each ladder, the best standard-range rung; a long-shot rung only
        # if it passes the long-shot checks. Not simply the ladder's overall
        # best, which is often the longest shot on it.
        picks = []
        for lad in get_alt_value(sport, fn):
            cands = []
            for r in lad["rungs"]:
                kind = tier(r["best_price"]) if r.get("flagged") else None
                if kind == "standard" or (kind == "longshot" and alt_longshot_ok(r)):
                    cands.append((r, kind))
            if cands:
                std = [c for c in cands if c[1] == "standard"]
                best, kind = max(std or cands, key=lambda c: c[0]["ev_pct"])
                picks.append((lad, best, kind))
        # Favorable matchups first, then standard before long shots, then EV.
        picks.sort(key=lambda p: (((p[0].get("matchup") or {}).get("verdict") == "favorable"),
                                  p[2] == "standard", min(p[1]["ev_pct"], EV_RANK_CAP)), reverse=True)
        kept, longshots = [], 0
        for lad, best, kind in picks:
            if kind == "longshot":
                if longshots >= LONGSHOT_PER_SPORT:
                    continue
                longshots += 1
            kept.append((lad, best, kind))
            if len(kept) >= ALT_PER_SPORT:
                break
        for lad, best, kind in kept:
            m = lad.get("matchup") or {}
            notes = []
            if m.get("verdict"):
                notes.append(f"Matchup {m['verdict']}" + (": " + "; ".join(m.get("facts", [])[:2])
                                                        if m.get("facts") else ""))
            out.append({
                "id": f"alt|{sport}|{lad['player']}|{lad['market']}",
                "type": "alt", "sport": sport,
                "title": f"{lad['player']} Over {best['line']:g} {_pretty_market(lad['market'])} "
                         f"{_fmt_odds(best['best_price'])}",
                "subtitle": f"{best['best_book']} · hit {best['season_sample']} this season, "
                            f"{best['recent_sample']} last 10 · our chance {best['model_pct']:g}% "
                            f"vs {best['implied_pct']:g}% implied",
                "notes": notes,
                # Not headlined as "EV": this edge comes from his own history,
                # which runs optimistic next to the market-based EV Finder.
                "badge": "Alt value",
                # Sized on HALF the claimed edge: Alt-Line's chance comes from
                # his own history and runs optimistic next to the market.
                "risk": _risk(kind, (best["model_pct"] + best["implied_pct"]) / 200, best["best_price"]),
                # Below every EV play: the EV Finder's edge is measured against
                # the market itself, Alt-Line's against his own history, which
                # runs optimistic. Favorable matchups get a nudge.
                "score": (350 + min(best["ev_pct"], EV_RANK_CAP) * 4
                          + (30 if m.get("verdict") == "favorable" else 0)
                          - (30 if kind == "longshot" else 0)),
                "time": lad.get("fetched_at"),
                "link": f"/betting/alt-lines?sport={sport}",
                "bet": {"sport": sport, "event_id": None, "player": lad["player"],
                        "market": lad["market"], "line": best["line"], "side": "over",
                        "book": best["best_book"], "price": best["best_price"], "tool": "alt",
                        "commence_time": lad.get("commence_time")},
            })
    return out


def _weather() -> List[Dict[str, Any]]:
    from app.data import mlb, nfl
    out = []
    for sport, fn in (("mlb", mlb.get_mlb_weather), ("nfl", nfl.get_nfl_weather)):
        for g in (fn() or {}).get("games", []):
            wind = g.get("wind_mph") or 0
            rain = g.get("precip_pct") or 0
            if g.get("roof") not in (None, "outdoor", "open") or (wind < WINDY_MPH and rain < 50):
                continue
            eff = (g.get("wind_effect") or {}).get("label")
            out.append({
                "id": f"wx|{sport}|{g.get('home_team')}|{g.get('game_time_utc') or g.get('kickoff')}",
                "type": "weather", "sport": sport,
                "title": f"{g.get('away_team')} @ {g.get('home_team')}: wind {wind} mph"
                         + (f" {g.get('wind_dir')}" if g.get("wind_dir") else ""),
                "subtitle": " · ".join(x for x in (f"{g.get('temp_f')}°F" if g.get("temp_f") is not None else None,
                                                   f"{rain}% rain" if rain else None) if x),
                "notes": [eff] if eff else [],
                "badge": "Weather", "score": 200 + wind + rain / 5,
                "time": g.get("game_time_utc") or g.get("kickoff"),
                "link": f"/{sport}/weather", "bet": None,
            })
    out.sort(key=lambda i: i["score"], reverse=True)
    return out[:WEATHER_ITEMS]


def _middles() -> List[Dict[str, Any]]:
    from app.data.props import get_middles
    out = []
    for sport in ("nfl", "mlb"):
        rows = sorted(get_middles(sport), key=lambda r: float(r.get("one_wins_pct") or -99), reverse=True)
        for r in rows[:MIDDLES_PER_SPORT]:
            out.append({
                "id": f"mid|{sport}|{r['Player']}|{r['market']}|{r['over_book']}|{r['under_book']}",
                "type": "middle", "sport": sport,
                "title": f"{r['Player']} {_pretty_market(r['market'])}: O {r['over_line']:g} "
                         f"({r['over_book']}) / U {r['under_line']:g} ({r['under_book']})",
                "subtitle": f"{str(r.get('kind', '')).replace('_', '-')} · window {r.get('window') or 'none'}",
                "notes": [], "badge": "Middle" if "middle" in str(r.get("kind")) else "Arb",
                "score": 300 + float(r.get("one_wins_pct") or 0),
                "time": r.get("fetched_at"), "link": f"/betting/middles?sport={sport}", "bet": None,
            })
    return out


def _hot() -> List[Dict[str, Any]]:
    from app.data import mlb
    out = []
    rows = [h for h in mlb.get_hot_hitters() if (h.get("today") or {}).get("pitcher")]
    rows.sort(key=lambda h: h.get("wOBA") or 0, reverse=True)
    for h in rows[:HOT_HITTERS]:
        t = h["today"]
        out.append({
            "id": f"hot|{h['Player']}", "type": "hot", "sport": "mlb",
            "title": f"{h['Player']}: {h.get('H')}-for-{h.get('AB')}, {h.get('HR')} HR over the last 7 days",
            "subtitle": f"{h.get('Team')} · faces {t.get('pitcher')} ({t.get('throws')}HP) today",
            "notes": [], "badge": "Hot", "score": 150 + (h.get("wOBA") or 0) * 100,
            "time": None, "link": "/mlb/hot-hitters", "bet": None,
        })
    return out


@ttl_cache(300)
def get_today() -> Dict[str, Any]:
    items: List[Dict[str, Any]] = []
    for label, fn in (("injuries", _injuries), ("ev", _ev), ("alt", _alt),
                      ("weather", _weather), ("middles", _middles), ("hot", _hot)):
        items += _safe(label, fn)
    items.sort(key=lambda i: i["score"], reverse=True)
    return {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "items": items}
