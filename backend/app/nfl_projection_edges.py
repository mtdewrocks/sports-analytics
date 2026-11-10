"""NFL projection vs sportsbook line.

Same rules as the NBA page (nba_projection_edges.py): the main line is the
number most bettable books deal, the price is the best one at that line, and
a play is flagged on EXPECTED VALUE -- the model's chance of the side times
the payout -- not on a raw gap. Chances come from how actual results landed
around projections of the same size in 2025-26 (out of sample), shipped in
nfl_projection_calibration.json.

Interceptions, longest-play and kicking markets aren't projected.

Pure pandas, no app imports: the pipeline logs plays with it and the API
serves them with it.
"""
from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

try:                                    # imported by the API (package) or run by the pipeline (script dir on path)
    from app.nba_projection_edges import american_to_decimal, main_lines, match_key  # noqa: F401
    from app.nfl_projection_model import prob_over
except ImportError:                     # pragma: no cover
    from nba_projection_edges import american_to_decimal, main_lines, match_key  # noqa: F401
    from nfl_projection_model import prob_over

# props market -> projected stat
MARKETS = {
    "receptions": "rec", "reception_yds": "rec_yds", "rush_attempts": "rush_att", "rush_yds": "rush_yds",
    "rush_reception_yds": "rush_rec_yds", "pass_yds": "pass_yds", "pass_attempts": "pass_att",
    "pass_completions": "pass_cmp", "pass_tds": "pass_tds",
}
LABELS = {"receptions": "Receptions", "reception_yds": "Receiving yds", "rush_attempts": "Rush attempts",
          "rush_yds": "Rushing yds", "rush_reception_yds": "Rush + rec yds", "pass_yds": "Passing yds",
          "pass_attempts": "Pass attempts", "pass_completions": "Completions", "pass_tds": "Passing TDs",
          "anytime_td": "Anytime TD"}

MIN_EV = 0.05
MIN_PROB_EDGE = 0.08      # vs the book's no-vig chance, when both sides are priced
MIN_TD_EDGE = 0.03        # anytime TD is one-sided: vs the price's own implied chance
MAX_TD_PRICE = 500        # longer shots are mostly fringe players who may not even dress
SUSPECT_EV = 0.35

# Backtest at 2026 weeks 4-9 closing lines (models trained through 2024,
# chances calibrated on 2025 only): receptions and receiving yards made
# money on both sides; rushing and QB markets didn't. Only the first are
# "bets"; the rest are flagged as "watch" -- shown and graded separately,
# so the track record can promote them if they earn it.
BET_MARKETS = {"receptions", "reception_yds"}
# chances for rushing markets were calibrated on running backs only
RB_ONLY = {"rush_attempts", "rush_yds"}


def td_prices(props: pd.DataFrame, exclude_books: set) -> Dict[str, dict]:
    """player key -> best anytime-TD 'yes' price."""
    if props is None or props.empty:
        return {}
    df = props[(props["market"] == "anytime_td") & props["Over Price"].notna()]
    df = df[~df["bookmakers"].str.lower().isin(exclude_books)]
    out = {}
    for k, g in df.assign(_k=df["Player"].map(match_key)).groupby("_k"):
        b = g.sort_values("Over Price", ascending=False).iloc[0]
        out[k] = {"price": float(b["Over Price"]), "book": b["bookmakers"], "books": int(g["bookmakers"].nunique()),
                  "fetched_at": str(g["fetched_at"].max()) if "fetched_at" in g.columns else None}
    return out


def edges_for(player: str, proj: dict, lines: Dict[tuple, dict], tds: Dict[str, dict], cal: dict,
              position: Optional[str] = None) -> Dict[str, dict]:
    k = match_key(player)
    out = {}
    for m, st in MARKETS.items():
        ln = lines.get((k, m))
        p = proj.get(st)
        if not ln or p is None:
            continue
        line = ln["line"]
        model = p
        # Pull toward the market before pricing. On 2026 closing lines the
        # line alone beat our number for QB and rushing stats, and a 50/50
        # mix beat either for receiving -- so the line is information, not
        # just a target. Weights per stat in nfl_projection_calibration.json.
        w = (cal.get("market_weight") or {}).get(st, 0.0)
        p = (1 - w) * model + w * line
        po = prob_over(st, p, line, cal)
        pu = None
        if po is not None:
            pu = 1 - po if line % 1 else 1 - prob_over(st, p, line - 1, cal)
        ev = {}
        for side, prob, price in (("over", po, ln["over_price"]), ("under", pu, ln["under_price"])):
            dec = american_to_decimal(price)
            if prob is not None and dec:
                ev[side] = prob * dec - 1
        mkt = None
        do, du = american_to_decimal(ln["over_price"]), american_to_decimal(ln["under_price"])
        if do and du:
            mkt = (1 / do) / (1 / do + 1 / du)
        side = max(ev, key=ev.get) if ev else None
        if side and ev[side] < MIN_EV:
            side = None
        if side and mkt is not None:
            if (po if side == "over" else pu) - (mkt if side == "over" else 1 - mkt) < MIN_PROB_EDGE:
                side = None
        if side and m in RB_ONLY and position not in (None, "RB"):
            side = None
        out[m] = {**ln, "label": LABELS[m], "projection": round(p, 1), "model": round(model, 1),
                  "diff": round(model - line, 1),
                  "tier": ("bet" if m in BET_MARKETS else "watch") if side else None,
                  "prob_over": round(po, 3) if po is not None else None,
                  "prob_under": round(pu, 3) if pu is not None else None,
                  "market_prob_over": round(mkt, 3) if mkt is not None else None,
                  "side": side, "ev": round(ev[side], 3) if side else None,
                  "suspect": bool(side and ev[side] >= SUSPECT_EV),
                  "price": ln["over_price"] if side == "over" else ln["under_price"] if side == "under" else None,
                  "book": ln["over_book"] if side == "over" else ln["under_book"] if side == "under" else None}
    t = tds.get(k)
    p = proj.get("anytime_td")
    if t and p is not None:
        dec = american_to_decimal(t["price"])
        ev = p * dec - 1 if dec else None
        side = ("yes" if ev is not None and ev >= MIN_EV and p - 1 / dec >= MIN_TD_EDGE and t["price"] <= MAX_TD_PRICE
                else None)
        out["anytime_td"] = {"label": LABELS["anytime_td"], "line": None, "projection": round(p, 3),
                             "prob_over": round(p, 3), "over_price": t["price"], "over_book": t["book"],
                             "books": t["books"], "fetched_at": t["fetched_at"], "side": side,
                             "ev": round(ev, 3) if side else None, "suspect": bool(side and ev >= SUSPECT_EV),
                             "tier": "watch" if side else None,
                             "price": t["price"] if side else None, "book": t["book"] if side else None}
    return out


def best_bets(players: list, tier: str = "bet", limit: int = 40) -> list:
    rows = []
    for p in players:
        for m, e in (p.get("lines") or {}).items():
            if e.get("side") and e.get("tier") == tier:
                rows.append({"game_id": p["game_id"], "player": p["player"], "team": p["team"], "position": p["position"],
                             "status": p.get("status"), "market": m, **e})
    rows.sort(key=lambda r: (r["suspect"], -(r["ev"] or 0)))
    return rows[:limit]
