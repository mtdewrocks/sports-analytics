"""Site-wide report card: how the EV Finder's flagged plays did vs. the close.

Built from build_flagged_plays.py's logs. CLV is the measure because it's
meaningful after dozens of plays; win/loss needs thousands.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from app.data.loader import get_flagged_plays_data, ttl_cache


def summarize_plays(df: pd.DataFrame) -> Dict[str, Any]:
    g = df[pd.to_numeric(df.get("clv_pct"), errors="coerce").notna()] if not df.empty else df
    if g.empty:
        return {"graded": 0, "avg_clv_pct": None, "beat_close_pct": None}
    clv = pd.to_numeric(g["clv_pct"], errors="coerce")
    return {"graded": int(len(g)), "avg_clv_pct": round(float(clv.mean()), 2),
            "beat_close_pct": round(float((clv > 0).mean() * 100), 1)}


@ttl_cache(600)
def get_report_card() -> Dict[str, Any]:
    frames = []
    for sport in ("nfl", "mlb"):
        df = get_flagged_plays_data(sport)
        if not df.empty:
            frames.append(df.assign(sport=sport))
    if not frames:
        return {"overall": summarize_plays(pd.DataFrame()), "flagged": 0, "by": []}
    df = pd.concat(frames, ignore_index=True)
    rows: List[Dict[str, Any]] = []
    for label, sub in (("NFL", df[df["sport"] == "nfl"]), ("MLB", df[df["sport"] == "mlb"]),
                       ("Sharp fair price", df[df["source"] == "sharp"]),
                       ("Consensus fair price", df[df["source"] == "consensus"]),
                       ("Edge 2-5%", df[pd.to_numeric(df["ev_pct"], errors="coerce") < 5]),
                       ("Edge 5%+", df[pd.to_numeric(df["ev_pct"], errors="coerce") >= 5])):
        s = summarize_plays(sub)
        if s["graded"]:
            rows.append({"label": label, **s})
    return {"overall": summarize_plays(df), "flagged": int(len(df)), "by": rows}
