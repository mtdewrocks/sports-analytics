"""Behind-the-scenes tracking for NBA Projections flags -- nothing here is
shown on the site yet.

Two experiments, logged every run and graded once games are final:

1. RULE VERSIONS. The live rule ("centered": chances read the projection as
   the typical result, Nov 13 2026) is logged as usual; the previous rule
   ("old": chances read it as the average, which leaned hard to unders) is
   re-run on the same lines and logged to a shadow file. Same games, same
   prices, same results -> a fair before/after.

2. STAR TIERS. Every live flag gets a 3/4/5-star rating from independent
   signals, plus the raw signals themselves so the rating can be redesigned
   later without waiting for new data:
     ev        expected return after the shrink + book blend
     hist_rate share of his last 10 games on the flagged side of this line
     books     books dealing this exact line (one stale outlier vs consensus)
     clean     no injury tag on the player
   (Every flag already passed the minutes check, so it isn't a signal here.)

   points: EV 8-12% = 1, 12%+ = 2; history 60%+ = 1; 3+ books = 1; clean = 1
   stars:  0-1 -> 3, 2-3 -> 4, 4-5 -> 5

Backtest that motivated it (Nov 10-12, centered rule, 356 flags): EV 5-8%
returned +0.3% (89 flags), 8-12% +15.9% (135), 12-20% +13.1% (102), 20%+
+23.4% (30). The report below grades stars, EV bands and sides per version.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

try:
    import nba_projection_edges as E      # run as a script from backend/app
except ImportError:
    from app import nba_projection_edges as E
_E = E

HIST_GAMES = 10
EV_BANDS = [0.05, 0.08, 0.12, 0.20, 10.0]
EV_LABELS = ["5-8%", "8-12%", "12-20%", "20%+"]


def recent_values(history: pd.DataFrame, n: int = HIST_GAMES) -> Dict[tuple, list]:
    """(match_key, market) -> the player's last n results, oldest first."""
    h = history.copy()
    if "Played" in h.columns:
        h = h[pd.to_numeric(h["Played"], errors="coerce") == 1]
    h["GAME DATE"] = pd.to_datetime(h["GAME DATE"])
    h = h.sort_values("GAME DATE").groupby("PLAYER").tail(n)
    out: Dict[tuple, list] = {}
    for p, g in h.groupby("PLAYER"):
        k = E.match_key(p)
        for m, parts in E.MARKETS.items():
            if all(c in g.columns for c in parts):
                out[(k, m)] = g[list(parts)].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1).tolist()
    return out


def hist_rate(vals: Optional[list], line: float, side: str) -> Optional[float]:
    if not vals:
        return None
    v = np.asarray(vals, float)
    hit = (v > line) if side == "over" else (v < line)
    return float(hit.mean())


def stars(ev: float, hrate: Optional[float], books: Optional[int], status: Optional[str]) -> int:
    pts = (2 if ev >= 0.12 else 1 if ev >= 0.08 else 0)
    pts += 1 if (hrate is not None and hrate >= 0.6) else 0
    pts += 1 if (books or 0) >= 3 else 0
    pts += 1 if not status or str(status) in ("nan", "None", "Probable") else 0
    return 5 if pts >= 4 else 4 if pts >= 2 else 3


def flag_rows(rule: str, today_rows: pd.DataFrame, lines: dict, calibration: dict, alt_for, hist: dict,
              center: bool, edges=None) -> List[dict]:
    """Every flag one rule makes on tonight's lines, with tier signals.
    `edges` is the caller's nba_projection_edges module (the rule switch must
    flip the same module object the caller uses)."""
    E = edges or _E
    was = E.CENTER_ON_TYPICAL
    E.CENTER_ON_TYPICAL = center
    try:
        out = []
        for r in today_rows.to_dict("records"):
            for m, e in E.edges_for(r["PLAYER"], r, lines, calibration, alt_for(r)).items():
                if not e["side"] or e["price"] is None:
                    continue
                hr = hist_rate(hist.get((E.match_key(r["PLAYER"]), m)), e["line"], e["side"])
                out.append({
                    "rule": rule, "PLAYER": r["PLAYER"], "TEAM": r["TEAM"], "GAME DATE": r["GAME DATE"],
                    "start_utc": r.get("start_utc"), "market": m, "side": e["side"], "line": e["line"],
                    "price": e["price"], "book": e["book"], "projection": e["projection"], "diff": e["diff"], "ev": e["ev"],
                    "prob": e["prob_over"] if e["side"] == "over" else e["prob_under"],
                    "hist_rate": hr, "books": e.get("books"), "status": r.get("status"),
                    "stars": stars(e["ev"], hr, e.get("books"), r.get("status")),
                    "minutes": r.get("default_min"), "logged_at": r.get("logged_at"),
                })
        return out
    finally:
        E.CENTER_ON_TYPICAL = was


def _profit(price: float) -> float:
    return price / 100.0 if price > 0 else 100.0 / abs(price)


def grade(plays: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """Each logged flag with its result; ungraded (not final / didn't play) dropped."""
    if plays is None or plays.empty:
        return pd.DataFrame()
    h = history.copy()
    if "Played" in h.columns:
        h = h[pd.to_numeric(h["Played"], errors="coerce") == 1]
    h["_d"] = pd.to_datetime(h["GAME DATE"]).dt.normalize()
    h["_k"] = h["PLAYER"].map(E.match_key)
    act = h.drop_duplicates(["_k", "_d"]).set_index(["_k", "_d"])
    rows = []
    for r in plays.to_dict("records"):
        key = (E.match_key(r["PLAYER"]), pd.Timestamp(r["GAME DATE"]).normalize())
        if key not in act.index:
            continue
        a = act.loc[key]
        v = float(sum(float(a[c]) for c in E.MARKETS[r["market"]]))
        if v == r["line"]:
            u, res = 0.0, "push"
        else:
            won = (v > r["line"]) == (r["side"] == "over")
            u, res = (_profit(r["price"]), "win") if won else (-1.0, "loss")
        rows.append({**r, "result": v, "outcome": res, "units": u})
    return pd.DataFrame(rows)


def _summ(g: pd.DataFrame) -> dict:
    dec = g[g["outcome"] != "push"]
    return {"plays": int(len(g)), "wins": int((g["outcome"] == "win").sum()),
            "losses": int((g["outcome"] == "loss").sum()),
            "win_pct": round(100 * float((dec["outcome"] == "win").mean()), 1) if len(dec) else None,
            "units": round(float(g["units"].sum()), 2), "roi_pct": round(100 * float(g["units"].mean()), 1)}


def report(graded: pd.DataFrame) -> dict:
    """Per rule: overall, by side, by stars, by EV band, by night."""
    out = {}
    if graded is None or graded.empty:
        return out
    g = graded.copy()
    g["ev_band"] = pd.cut(g["ev"], EV_BANDS, labels=EV_LABELS, right=False).astype(str)
    g["night"] = pd.to_datetime(g["GAME DATE"]).dt.date.astype(str)
    for rule, rg in g.groupby("rule"):
        rep = {"overall": _summ(rg)}
        for col in ("side", "ev_band", "night") + (("stars",) if "stars" in rg.columns else ()):
            rep[f"by_{col}"] = {str(k): _summ(x) for k, x in rg.groupby(col) if len(x)}
        out[rule] = rep
    return out


def update_log(path, new_rows: Iterable[dict], day) -> pd.DataFrame:
    """Replace today's rows (the last run before tip wins), keep the rest."""
    new = pd.DataFrame(list(new_rows))
    if path.exists():
        old = pd.read_parquet(path)
        old = old[pd.to_datetime(old["GAME DATE"]) != pd.Timestamp(day)]
        new = pd.concat([old, new], ignore_index=True)
    if not new.empty:
        new.to_parquet(path, index=False)
    return new
