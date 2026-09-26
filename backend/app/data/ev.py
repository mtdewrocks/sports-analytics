"""EV Finder: props where one sportsbook is paying more than the bet is worth.

No model involved. The "true" chance of each side comes from the market
itself, with the vig removed:

  SHARP      Pinnacle's two-way price on the same line, de-vigged. Used
             whenever Pinnacle hangs that exact line.
  CONSENSUS  Every OTHER sportsbook's two-way price on the same line,
             de-vigged book by book, then the median of those fair
             probabilities. Leave-one-out on purpose: the book being judged
             never votes on its own fair price, so a single outlier can't
             drag the consensus toward itself and hide its own edge.

Then every book's price on each side is compared with that fair chance, and
EV = p x payout - (1 - p). A price far from the pack that is only breakeven
once the vig comes out is NOT flagged -- that's the case the page explains.

What's never evaluated or used for consensus:
  * DFS / pick'em apps -- their "price" is a share of a multi-pick payout,
    not a bet you can place alone (see props_config.NO_SINGLE_BET_BOOKS).
  * UNBETTABLE_BOOKS.
  * Games that have started -- their lines are frozen pre-game snapshots.
Sharp books are used ONLY as the reference, never as a book to bet.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from app.data.loader import get_odds_snapshots_data, get_props_data
from app.market_core import best_book_only, compute_ev  # noqa: F401  (re-exported)


def _price_since(sport: str) -> Dict[tuple, str]:
    """(event_id, Player, market, Line, book) -> when the CURRENT price was
    first seen, from the snapshot history (it only records changes, so the
    last row per key is the moment the live price appeared). Empty until
    snapshots exist; the page then just omits the "posted X ago" note."""
    snaps = get_odds_snapshots_data(sport)
    if snaps.empty or "observed_at" not in snaps.columns:
        return {}
    s = snaps.sort_values("observed_at").drop_duplicates(
        subset=["event_id", "Player", "market", "Line", "bookmakers"], keep="last")
    line = pd.to_numeric(s["Line"], errors="coerce")
    return {
        (str(e), str(p), str(m), None if pd.isna(l) else float(l), str(b)): str(t)
        for e, p, m, l, b, t in zip(s["event_id"], s["Player"], s["market"],
                                   line, s["bookmakers"], s["observed_at"])
    }


def get_ev(
    sport: str,
    source: str = "auto",
    min_edge: float = 2.0,
    min_books: int = 2,
    market: Optional[str] = None,
    player: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """EV Finder rows for one sport, from the current props file. The math is
    app/market_core.compute_ev -- shared with build_flagged_plays.py."""
    return compute_ev(get_props_data(sport), _price_since(sport), source, min_edge,
                      min_books, market, player)
