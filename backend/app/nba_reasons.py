"""Plain-English reasons behind an NBA projection, for the pick emails.

Each reason is a "what if": the same models re-run with one factor set to
neutral (an average opponent, average pace, no injured teammates, rested,
a typical Vegas game, his usual form). The projection minus that re-run is
how much the factor moved tonight's number, in real units -- so "IND allows
14% more threes than average (+0.3)" means the matchup alone added 0.3
threes. Minutes are explained directly: tonight's projected minutes vs his
recent average.

Only reasons that push the same way as the pick are shown, biggest first.
These explain why OUR MODEL likes a side -- the books know these things too.
"""
from __future__ import annotations

from typing import Callable, Dict, List

import numpy as np
import pandas as pd

try:
    from app import nba_projection_edges as E
    from app import nba_projection_features as F
except ImportError:                                   # pragma: no cover
    import nba_projection_edges as E
    import nba_projection_features as F

NEUTRAL_IMPLIED = 114.0      # a typical team total
NEUTRAL_SPREAD = 6.0
STAT_WORDS = {"PTS": "points", "REB": "rebounds", "AST": "assists", "3PM": "threes",
              "BLK": "blocks", "STL": "steals", "TOV": "turnovers"}
MIN_SHARE = 0.03             # a reason must move the projection 3%+ ...
MIN_UNITS = {"3PM": 0.08, "BLK": 0.05, "STL": 0.05, "TOV": 0.08}   # ...and at least this much (default 0.15)


def _matchup(s):
    s = s.copy()
    for st in F.TARGETS:
        rel = f"Opp_{st}_rel"
        if rel in s.columns:
            for w in (f"{st}_roll{F.ROLLING_GAMES}", f"{st}_oly{F.OLYMPIC_GAMES}"):
                if f"{w}_oppAdj" in s.columns and w in s.columns:
                    s[f"{w}_oppAdj"] = s[w]
            s[rel] = 1.0
    return s


def _pace(s):
    return s.assign(PACE_rel=1.0) if "PACE_rel" in s.columns else s


def _vegas(s):
    s = s.copy()
    if "implied_pts" in s.columns:
        s["implied_pts"] = NEUTRAL_IMPLIED
    if "abs_spread" in s.columns:
        s["abs_spread"] = NEUTRAL_SPREAD
    return s


def _rest(s):
    return s.assign(**{c: 0 for c in ("is_b2b", "is_3in4", "is_3plus_away") if c in s.columns})


def _teammates(s):
    s = s.copy()
    if "usg_newly_out" in s.columns:
        s["mates_usg"] = s["mates_usg"] + s["usg_newly_out"]
        s["usg_newly_out"] = 0.0
    return s


def _form(s):
    s = s.copy()
    for st in F.TARGETS:
        r, o = f"{st}_roll{F.ROLLING_GAMES}", f"{st}_oly{F.OLYMPIC_GAMES}"
        if r in s.columns and o in s.columns:
            s[r] = s[o]
            if f"{r}_oppAdj" in s.columns and f"{o}_oppAdj" in s.columns:
                s[f"{r}_oppAdj"] = s[f"{o}_oppAdj"]
    return s


FACTORS: Dict[str, Callable] = {"matchup": _matchup, "pace": _pace, "vegas": _vegas, "rest": _rest,
                                "teammates": _teammates, "form": _form}


def effects(models: dict, slate: pd.DataFrame, minutes: pd.Series) -> Dict[str, pd.DataFrame]:
    """factor -> per-player, per-stat change in the projection it caused."""
    base = F.predict_stats(models, slate, minutes)
    out = {}
    for name, fn in FACTORS.items():
        alt = F.predict_stats(models, slate, minutes, adjust=fn)
        out[name] = base[F.TARGETS] - alt[F.TARGETS]
    out["_base"] = base
    return out


def _fmt(x: float) -> str:
    return f"{x:+.1f}" if abs(x) >= 0.95 else f"{x:+.2f}".replace("0.", ".")


def reasons_for(i: int, row: pd.Series, market: str, side: str, eff: Dict[str, pd.DataFrame],
                slate: pd.DataFrame, minutes: float, n: int = 2) -> List[str]:
    """Up to n reasons for player row i's `side` of `market`, biggest first."""
    parts = E.MARKETS[market]
    sign = 1 if side == "over" else -1
    proj = float(sum(eff["_base"].loc[i, s] for s in parts))
    floor = max(MIN_SHARE * proj, sum(MIN_UNITS.get(s, 0.15) for s in parts) / max(1, len(parts)))
    cands = []
    single = parts[0] if len(parts) == 1 else None
    word = STAT_WORDS.get(single, "production") if single else "production"

    for name in FACTORS:
        d = float(sum(eff[name].loc[i, s] for s in parts))
        if d * sign < floor:
            continue
        if name == "matchup":
            opp = row.get("Opponent")
            rel = row.get(f"Opp_{single}_rel") if single else None
            if rel is not None and pd.notna(rel) and abs(rel - 1) >= 0.03:
                more = "more" if rel > 1 else "fewer"
                txt = f"{opp} allows {abs(rel - 1) * 100:.0f}% {more} {word} than average"
            else:
                txt = f"matchup with {opp}"
        elif name == "pace":
            pr = row.get("PACE_rel")
            txt = (f"{row['TEAM']} plays {abs(pr - 1) * 100:.0f}% {'faster' if pr > 1 else 'slower'} than average"
                   if pr is not None and pd.notna(pr) else "pace")
        elif name == "vegas":
            sp, ip = row.get("abs_spread"), row.get("implied_pts")
            if sp is not None and pd.notna(sp) and sp >= 10 and d < 0:
                txt = f"{sp:.1f}-point spread (blowout risk)"
            elif ip is not None and pd.notna(ip):
                txt = f"{row['TEAM']} expected to score {ip:.0f}"
            else:
                txt = "Vegas game total"
        elif name == "rest":
            txt = ("second night of a back-to-back" if row.get("is_b2b") else
                   "3rd game in 4 nights" if row.get("is_3in4") else "long road trip")
        elif name == "teammates":
            mates = slate[(slate["TEAM"] == row["TEAM"]) & slate["out"].fillna(False).astype(bool)
                          & slate["played_last"].fillna(False).astype(bool)]["PLAYER"].tolist()
            txt = (", ".join(m.split()[-1] for m in mates[:2]) + " out -- more shots to go around") if mates \
                else "teammates out"
        else:  # form
            r5_, o10_ = (row.get(f"{single}_roll{F.ROLLING_GAMES}"), row.get(f"{single}_oly{F.OLYMPIC_GAMES}")) \
                if single else (None, None)
            if single and pd.notna(r5_) and pd.notna(o10_) and abs(r5_ - o10_) < 0.1 * max(o10_, 1):
                continue                     # last 5 barely differs from last 10: not worth saying
            if single:
                r5, o10 = row.get(f"{single}_roll{F.ROLLING_GAMES}"), row.get(f"{single}_oly{F.OLYMPIC_GAMES}")
                txt = (f"{'hot' if d > 0 else 'cold'} lately: {r5:.1f} {word} a game over his last 5 vs {o10:.1f} over 10"
                       if pd.notna(r5) and pd.notna(o10) else ("hot lately" if d > 0 else "cold lately"))
            else:
                txt = "hot lately" if d > 0 else "cold lately"
        cands.append((abs(d), f"{txt} ({_fmt(d)})"))

    # minutes: explained directly, not by a re-run
    ew = row.get("ew")
    if ew is not None and pd.notna(ew) and ew > 0 and minutes > 0:
        d = proj * (1 - float(ew) / float(minutes))
        if d * sign >= floor:
            cands.append((abs(d), f"projected {minutes:.0f} min vs {float(ew):.0f} lately ({_fmt(d)})"))
    cands.sort(key=lambda c: -c[0])
    return [c[1] for c in cands[:n]]
