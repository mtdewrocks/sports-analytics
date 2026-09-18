"""Shared cross-sport helpers for the Hit Rate Sheet: grading a game log
against a line, and splitting a per-game series into "season" vs "recent"
windows. Used by the bulk-scan `get_*_hit_rate_sheet()` functions in
app/data/mlb.py, app/data/nfl.py and app/data/nba.py.

Each sport keeps its own MARKET_STAT_MAP (a market key -> either a single
game-log column name, or a small function that derives a float from one
game's row -- see e.g. MLB_BATTER_MARKET_STAT in app/data/mlb.py for a
composite like total bases) in that sport's own data module rather than
here. Putting the maps here too would need this module to import
sport-specific helpers (e.g. mlb.py's `_ip_to_outs()` for `pitcher_outs`)
while those sport modules import the grading helpers below -- a real
import cycle. Keeping the maps sport-local avoids that; this module stays
the sport-agnostic half.

Standardizes the over/under comparison as `value >= line` counts as an
Over hit. This resolves a real inconsistency already in the codebase:
app/data/nba.py::get_game_log() grades with a strict `>`, while
app/data/nfl.py::get_game_log() already uses `>=`. Going forward, `>=` is
the standard for any NEW grading code -- this module and everything built
on it. The older per-player game-log endpoints are left exactly as they
are; fixing their long-standing behavior is a separate decision for
another day, not something to sneak in as a side effect of this feature.
"""
from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Sequence, Union

# A market's stat spec is either the name of a single game-log column, or a
# function taking one game's row (a dict-like / pandas Series) and
# returning a float -- for composite/derived markets.
StatSpec = Union[str, Callable[[Any], float]]

# Per-sport "recent form" window, in games -- the mockup's Time Period
# toggle's "Recent" option. Season always means the full current season for
# all three sports, so there's no equivalent SEASON_WINDOW constant needed.
RECENT_WINDOW: Dict[str, int] = {
    "mlb": 10,
    "nfl": 5,
    "nba": 10,
}


def resolve_stat_value(row: Any, spec: StatSpec) -> float:
    """Apply one market's stat spec to a single game-log row, tolerating a
    missing column, a NaN, or a derivation function that raises -- any of
    which degrade to 0.0 rather than blowing up the whole bulk scan over
    one bad row."""
    try:
        if callable(spec):
            val = spec(row)
        else:
            val = row[spec] if not hasattr(row, "get") else row.get(spec)
    except Exception:
        return 0.0

    if val is None:
        return 0.0
    try:
        f = float(val)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(f) else f


def grade_over_under(values: Sequence[float], line: float) -> Dict[str, Any]:
    """Grade a list of per-game stat values against a line, Over-only.

    `value >= line` counts as a hit -- see module docstring for why this is
    `>=` rather than the strict `>` one of the existing per-sport game logs
    still uses. Returns 0/0/0.0 for an empty sample rather than raising or
    dividing by zero.
    """
    total = len(values)
    if total == 0:
        return {"over": 0, "total": 0, "pct": 0.0}
    over = sum(1 for v in values if v >= line)
    return {"over": over, "total": total, "pct": round(over / total, 4)}


def split_season_recent(values_sorted_by_date: Sequence[float], recent_n: int) -> Dict[str, List[float]]:
    """Split a per-game series -- already sorted ASCENDING by date -- into
    the full season and the trailing `recent_n` games.

    Takes a plain sorted list rather than a DataFrame + date column: every
    caller has already done its own sport-specific sorting (game_date for
    MLB, season+week for NFL, game_date for NBA) by the time it gets here,
    so this stays a pure, five-line function with no per-sport knowledge of
    its own.
    """
    values = list(values_sorted_by_date)
    recent = values[-recent_n:] if recent_n > 0 else values
    return {"season": values, "recent": recent}
