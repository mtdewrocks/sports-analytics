"""Odds arithmetic shared by the EV Finder, Alt-Line Value and the snapshot
builder. Pure functions, no pandas, no I/O -- so they can be unit tested on
their own and imported both from the app (`app.odds_math`) and from the
plain scripts in this folder that put backend/app/ on sys.path.

Conventions
-----------
* Prices are AMERICAN odds (-110, +130). Anything that isn't a real price
  (None, NaN, 0, or between -100 and +100 exclusive) is treated as missing
  rather than guessed at.
* Probabilities are 0..1.
* EV is returned PER 1 UNIT STAKED: 0.097 means +$9.70 per $100 bet.
"""

from __future__ import annotations

import math
from typing import Optional, Sequence


def is_price(odds) -> bool:
    try:
        o = float(odds)
    except (TypeError, ValueError):
        return False
    return not math.isnan(o) and (o >= 100 or o <= -100)


def implied_prob(odds: float) -> float:
    """Break-even probability of an American price, vig included.
    -110 -> 0.5238, +130 -> 0.4348."""
    o = float(odds)
    return -o / (-o + 100.0) if o < 0 else 100.0 / (o + 100.0)


def to_decimal(odds: float) -> float:
    """-110 -> 1.909, +130 -> 2.30."""
    o = float(odds)
    return 1.0 + (100.0 / -o if o < 0 else o / 100.0)


def prob_to_american(p: float) -> Optional[int]:
    """Fair American price for a probability. 0.5 -> +100 (not -100, so a
    coin flip reads the way books print it)."""
    if not 0 < p < 1:
        return None
    if p > 0.5:
        return -int(round(p / (1.0 - p) * 100.0))
    return int(round((1.0 - p) / p * 100.0))


def devig_two_way(over_odds: float, under_odds: float) -> Optional[float]:
    """Fair probability of the OVER side, vig removed by proportional
    (multiplicative) normalization -- the standard method, and the one the
    page explains to users. Returns None unless both sides are real prices
    and the pair actually carries a margin (an overround below 1 would mean
    the "pair" is really an arb, i.e. the two prices aren't from one market).
    """
    if not (is_price(over_odds) and is_price(under_odds)):
        return None
    a, b = implied_prob(over_odds), implied_prob(under_odds)
    total = a + b
    if total < 1.0:
        return None
    return a / total


def ev_per_unit(p: float, odds: float) -> float:
    """Expected profit per 1 unit staked at `odds` if the true chance of
    winning is `p`. 0.517 at +112 -> +0.0966."""
    return p * (to_decimal(odds) - 1.0) - (1.0 - p)


def median(values: Sequence[float]) -> Optional[float]:
    xs = sorted(float(v) for v in values)
    n = len(xs)
    if n == 0:
        return None
    mid = n // 2
    return xs[mid] if n % 2 else (xs[mid - 1] + xs[mid]) / 2.0


def median_price(prices: Sequence[float]) -> Optional[float]:
    """Median of American prices, taken in PROBABILITY space and converted
    back. Averaging American odds directly is wrong across the +/- boundary
    (the "middle" of -105 and +105 is not 0)."""
    probs = [implied_prob(p) for p in prices if is_price(p)]
    m = median(probs)
    if m is None:
        return None
    return prob_to_american(m)


def shrink_toward(hits: float, n: float, prior_p: float, prior_n: float) -> float:
    """Beta-binomial style shrinkage of an observed hit rate toward a prior.

    With prior_n = 15, a 3-for-4 streak on a rung the market prices at 30%
    reads as (3 + 4.5) / (4 + 15) = 39%, not 75% -- which is the whole point:
    small samples on long-odds rungs are where naive hit rates lie most.
    """
    if n <= 0:
        return prior_p
    return (hits + prior_p * prior_n) / (n + prior_n)
