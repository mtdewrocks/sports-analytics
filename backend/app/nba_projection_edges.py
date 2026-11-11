"""Projection vs sportsbook line -- the step merge_predictions_and_lines.py did.

Same idea as Shawn's script, with three changes:

  * every bettable book, not just FanDuel. The "main line" is the number the
    most books are dealing (ties -> the lower one), and the price shown on
    each side is the best available AT that line.
  * PRA added, since the model projects all three parts.
  * plays are flagged by EXPECTED VALUE, not a raw gap. "Projects 26 vs a
    20.5 line" becomes "goes over ~72% of the time; at -115 that's +11%",
    using how actual results have spread around projections of that size
    recently (calibration from get_nba_projections.py). A 5-point gap on a
    20.5 line and on a 35.5 line aren't the same bet, and price matters.

Pure pandas, no app imports: get_nba_projections.py logs edges with it and
the API serves them with it.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Dict, Optional

import numpy as np
import pandas as pd

# props market -> how to build it from projected stats
MARKETS = {
    "points": ["PTS"], "rebounds": ["REB"], "assists": ["AST"], "threes": ["3PM"],
    "points_rebounds_assists": ["PTS", "REB", "AST"],
    "blocks": ["BLK"], "steals": ["STL"], "turnovers": ["TOV"],
}
LABELS = {"points": "Points", "rebounds": "Rebounds", "assists": "Assists", "threes": "Threes",
          "points_rebounds_assists": "PRA", "blocks": "Blocks", "steals": "Steals", "turnovers": "Turnovers"}
# Shawn's cut-offs (merge_predictions_and_lines.py), PRA added. Kept for
# reference on each line; what flags a play now is expected value (below).
THRESHOLDS = {"points": 1.5, "assists": 1.0, "rebounds": 1.25, "threes": 0.75, "points_rebounds_assists": 2.5}

# Calibration key for each market (get_nba_projections.calibrate)
CAL_KEY = {"points": "PTS", "rebounds": "REB", "assists": "AST", "threes": "3PM",
           "points_rebounds_assists": "PRA", "blocks": "BLK", "steals": "STL", "turnovers": "TOV"}

# A play is flagged when the model's chance beats the price by this much:
# expected return per $1 at the best available price.
MIN_EV = 0.05
# ...AND the model has to disagree with the book's own no-vig chance by this
# much. Otherwise a whole-number market (threes, assists) whose fair line
# can't sit at exactly 50% looks like value whenever a book deals it at
# -110/-110 -- which real books mostly don't, so this is mostly a guard
# against one-sided juice we'd misread as an edge.
MIN_PROB_EDGE = 0.05
# Past this, the gap usually means the model is missing news (a role change,
# a minutes cap) rather than the books being wrong -- still shown, but marked.
SUSPECT_EV = 0.35

# Tested Nov 2026 (models as of Oct 31, graded on Nov 1-9 games): the
# chances were right in the middle but too sure at the ends -- 65% calls hit
# 60%, 88% calls hit 80% -- so they're pulled 15% back toward a coin flip.
PROB_SHRINK = 0.85
# And on Nov 10 the model disagreed with the books' no-vig price by 5%+ on
# 64% of all lines (266 flags in 6 games) even though its projections sat on
# the lines on average. Books aren't wrong two times in three; the model is
# noisy line to line. So its chance is averaged 50/50 with the book's before
# a play is judged -- the same lean-on-the-market blend the NFL page uses.
# Re-tune once a few weeks of closing lines can be graded.
MARKET_WEIGHT = 0.5


def american_to_decimal(price: Optional[float]) -> Optional[float]:
    if price is None or pd.isna(price) or price == 0:
        return None
    return 1 + (price / 100.0 if price > 0 else 100.0 / abs(price))


def prob_over(stat: str, projection: float, line: float, calibration: dict) -> Optional[float]:
    """Chance the result beats `line`, from how actual results have spread
    around projections of this size recently (ratio quantiles)."""
    c = (calibration or {}).get(stat)
    if not c or projection is None or projection <= 0:
        return None
    b = int(np.searchsorted(np.asarray(c["edges"]), projection, side="left"))
    vals = np.asarray(c["ratios"][min(b, len(c["ratios"]) - 1)]) * projection
    cut = line if line % 1 else line + 0.5      # whole-number line: a push isn't a win
    return float((vals > cut).mean())


def match_key(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r"[.'’]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return " ".join(s.split())


def main_lines(props: pd.DataFrame, exclude_books: set, markets=None) -> Dict[tuple, dict]:
    """(player key, market) -> {line, over_price, over_book, under_price, under_book, books}.
    `markets`: which props markets to read (default: the NBA ones above)."""
    if props is None or props.empty:
        return {}
    df = props[props["market"].isin(MARKETS if markets is None else markets)].copy()   # main lines, not *_alternate
    df = df[~df["bookmakers"].str.lower().isin(exclude_books)]
    df = df.dropna(subset=["Line"])
    if df.empty:
        return {}
    df["_k"] = df["Player"].map(match_key)
    out = {}
    for (k, m), g in df.groupby(["_k", "market"]):
        two_way = g.dropna(subset=["Over Price", "Under Price"])
        pool = two_way if not two_way.empty else g
        counts = pool.groupby("Line")["bookmakers"].nunique()
        line = float(counts[counts == counts.max()].index.min())
        at = g[g["Line"] == line]
        o = at.dropna(subset=["Over Price"]).sort_values("Over Price", ascending=False).head(1)
        u = at.dropna(subset=["Under Price"]).sort_values("Under Price", ascending=False).head(1)
        out[(k, m)] = {
            "line": line,
            "over_price": float(o["Over Price"].iloc[0]) if len(o) else None,
            "over_book": o["bookmakers"].iloc[0] if len(o) else None,
            "under_price": float(u["Under Price"].iloc[0]) if len(u) else None,
            "under_book": u["bookmakers"].iloc[0] if len(u) else None,
            "books": int(at["bookmakers"].nunique()),
            "fetched_at": str(at["fetched_at"].max()) if "fetched_at" in at.columns else None,
        }
    return out


def edges_for(player: str, proj: dict, lines: Dict[tuple, dict], calibration: Optional[dict] = None) -> Dict[str, dict]:
    """Every market with a line for this player: projection, line, the model's
    chance of each side, expected return at the best price, and -- when that
    return clears MIN_EV -- the side to play."""
    k = match_key(player)
    out = {}
    for m, parts in MARKETS.items():
        ln = lines.get((k, m))
        if not ln:
            continue
        p = float(sum(proj.get(s, 0.0) or 0.0 for s in parts))
        diff = p - ln["line"]
        po = prob_over(CAL_KEY[m], p, ln["line"], calibration)
        pu = None
        if po is not None:
            pu = 1 - po if ln["line"] % 1 else float(1 - prob_over(CAL_KEY[m], p, ln["line"] - 1, calibration))
        # no-vig market chance of the over, when both sides are priced
        mkt = None
        do, du = american_to_decimal(ln["over_price"]), american_to_decimal(ln["under_price"])
        if do and du:
            mkt = (1 / do) / (1 / do + 1 / du)
        raw_po, raw_pu = po, pu
        if po is not None:
            po = 0.5 + PROB_SHRINK * (po - 0.5)
            pu = 0.5 + PROB_SHRINK * (pu - 0.5)
            if mkt is not None:
                po = (1 - MARKET_WEIGHT) * po + MARKET_WEIGHT * mkt
                pu = (1 - MARKET_WEIGHT) * pu + MARKET_WEIGHT * (1 - mkt)
        ev = {}
        for side, prob, price in (("over", po, ln["over_price"]), ("under", pu, ln["under_price"])):
            dec = american_to_decimal(price)
            if prob is not None and dec:
                ev[side] = prob * dec - 1
        side = max(ev, key=ev.get) if ev else None
        if side and ev[side] < MIN_EV:
            side = None
        if side and mkt is not None:
            model_p = po if side == "over" else pu
            book_p = mkt if side == "over" else 1 - mkt
            if model_p - book_p < MIN_PROB_EDGE:
                side = None
        out[m] = {**ln, "label": LABELS[m], "projection": round(p, 2), "diff": round(diff, 2),
                  "threshold": THRESHOLDS.get(m),
                  "prob_over": round(po, 3) if po is not None else None,
                  "prob_under": round(pu, 3) if pu is not None else None,
                  # the model alone, before the shrink and the blend with the book
                  "model_prob_over": round(raw_po, 3) if raw_po is not None else None,
                  "model_prob_under": round(raw_pu, 3) if raw_pu is not None else None,
                  "market_prob_over": round(mkt, 3) if mkt is not None else None,
                  "ev_over": round(ev["over"], 3) if "over" in ev else None,
                  "ev_under": round(ev["under"], 3) if "under" in ev else None,
                  "side": side,
                  "ev": round(ev[side], 3) if side else None,
                  "suspect": bool(side and ev[side] >= SUSPECT_EV),
                  "price": ln["over_price"] if side == "over" else ln["under_price"] if side == "under" else None,
                  "book": ln["over_book"] if side == "over" else ln["under_book"] if side == "under" else None}
    return out
