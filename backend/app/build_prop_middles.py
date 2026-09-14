"""Find middles and arbs across books in Daily_Props.parquet.

    python backend/app/build_prop_middles.py --sport mlb
    python backend/app/build_prop_middles.py --sport nfl

Reads:  backend/data/<slug>/<the props file for that sport>
Writes: backend/data/<slug>/<slug>_prop_middles.parquet

Costs no API credits -- it is pure analysis of what get_mlb_props.py already
pulled.

WHAT COUNTS, AND THE DISTINCTION THAT MATTERS
---------------------------------------------
The opportunity is a PAIR of legs: an Over at one book and an Under at
another. The previous version grouped by player+market and kept any group with
more than one distinct line, which finds candidates but never pairs them -- so
it could not check the three things that decide whether a pair is real:

  DIRECTION. The Over must sit on the LOWER line. Over 1.5 / Under 2.5 both win
  when the batter gets exactly 2. Over 2.5 / Under 1.5 is the same two numbers
  in the other order and can NEVER both win -- it is the trap this screen
  exists to filter out, and a group-by cannot see it.

  DIFFERENT BOOKS. One book will not price both sides of a gap against itself.

  BOTH LEGS. `(Over Price >= 100) | (Under Price >= 100)` tests one ROW, but a
  row is one book at one line. The condition you actually want is that the Over
  leg and the Under leg -- different rows -- are both plus money.

And then the distinction your description blurs:

  SAME LINE (gap 0) is not a middle, it is an ARBITRAGE. Over 1.5 at +110 and
  Under 1.5 at +105: exactly one wins, and because both are plus money you
  profit either way. There is no window; there is nothing to land on.

  DIFFERENT LINES (gap > 0) is a true MIDDLE. Both bets win if the result lands
  strictly between the lines. Outside that window one wins and one loses, and
  whether that costs you anything depends on the prices.

Both are worth surfacing, so both are here, labelled. Note that a middle can
ALSO be an arb -- if the two prices alone clear the vig, the window is free
upside on top. Those are the best rows on the board and they are rare.

THE MATH
--------
Stakes are split so the two single-win outcomes pay the same, which is the
standard way to price a middle:

    stake_over = dec_under / (dec_over + dec_under)

    single_win_return = dec_over x dec_under / (dec_over + dec_under)
    one_wins_pct      = single_win_return - 1      (per 1 unit staked)
    window_pct        = 2 x single_win_return - 1

one_wins_pct >= 0 means the pair is an arb before the window is considered.
breakeven_window_rate_pct is how often the window has to land to make a
middle that loses money outside it worth taking.

THE DIRECTION IS THE WHOLE THING
--------------------------------
The Over must be on the LOWER line. Swap them and the arithmetic inverts:

    Over 1.5 @ +120 / Under 2.5 @ +115   ->  both win on exactly 2
    Over 1.5 @ +120 / Under 0.5 @ +150   ->  both LOSE on exactly 1

The second pair is not a middle with a smaller edge, it is the opposite bet.
Staked for equal returns it pays +17% whenever one leg wins and -100% when the
result is exactly 1 -- so it only breaks even if a batter gets exactly one hit
less than 14.5% of the time, against a real rate nearer 35-40%. `--include-
reverse` will list these, labelled `reverse`, precisely so the difference is
visible; they are excluded by default.

A CAVEAT WORTH KEEPING IN MIND
------------------------------
A screen like this mostly surfaces STALE PRICES, not free money. A book showing
the far side of an arb usually has not updated yet, and the line often moves or
the bet is voided before it fills. Treat `one_wins_pct > 0` as "look at this
now", not as realised profit -- and the bigger the apparent edge, the more
likely it is that the price is simply wrong and will not stand.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

# See get_props.py -- same reason, same fix.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from props_config import SPORTS  # noqa: E402

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"

# Books to ignore -- carried over from the original script (ones you can't or
# won't bet at). A book you cannot actually place the bet at is not an
# opportunity, it is a distraction.
EXCLUDED_BOOKS = {
    "williamhill_us", "betrivers", "betonlineag",
    "bovada", "hardrockbet", "mybookieag",
}

# NOTE: the *_alternate markets are deliberately NOT excluded here, unlike the
# original script. Alternate lines are the entire reason a gap can exist -- the
# main market is one line per book, so an Over and an Under on DIFFERENT
# numbers almost always means at least one leg came off an alternate ladder.
# Filtering them out leaves you hunting middles in the one place they cannot
# occur, which is why the old version only ever surfaced same-line rows.

MIN_PRICE = 100          # "plus money" required on BOTH legs


def american_to_decimal(odds: float) -> float:
    """+150 -> 2.5, -120 -> 1.833..."""
    if odds is None or (isinstance(odds, float) and math.isnan(odds)):
        return float("nan")
    odds = float(odds)
    if odds == 0:
        return float("nan")
    return 1.0 + (odds / 100.0 if odds > 0 else 100.0 / abs(odds))


def _span(lo: int, hi: int) -> tuple[str, int]:
    if hi < lo:
        return "", 0
    return (str(lo) if lo == hi else f"{lo}-{hi}"), hi - lo + 1


def middle_window(over_line: float, under_line: float) -> tuple[str, int]:
    """Integer results where BOTH legs win.

    Over wins when result > over_line, Under wins when result < under_line, so
    both win on the integers strictly between them -- which requires the Over
    to sit on the LOWER line. Hits, doubles, walks, strikeouts and outs are all
    integers, which is what makes the window countable rather than an interval.

        Over 1.5 / Under 2.5  ->  both win on exactly 2.
    """
    return _span(math.floor(over_line) + 1, math.ceil(under_line) - 1)


def reverse_window(over_line: float, under_line: float) -> tuple[str, int]:
    """Integer results where BOTH legs LOSE -- the mirror image.

    When the Over sits on the HIGHER line, the two legs no longer overlap; they
    leave a hole between them instead.

        Over 1.5 / Under 0.5  ->  Over needs 2+, Under needs 0.
                                  Exactly 1 loses both.

    This is not a middle. It is the shape a middle would have if you ran it
    backwards, and for a market like hits the hole sits on the single most
    common outcome. Priced and reported so it can be told apart at a glance
    rather than silently dropped.
    """
    return _span(math.ceil(under_line), math.floor(over_line))


def find_pairs(df: pd.DataFrame, min_price: float = MIN_PRICE,
               include_reverse: bool = False) -> pd.DataFrame:
    """Every Over/Under leg pair across different books, priced.

    Records (not itertuples) because the column names carry spaces -- "Over
    Price" comes back from itertuples as a positional `_5`, which is how the
    first version of this silently read the wrong column.
    """
    rows = []
    for (player, market), grp in df.groupby(["Player", "market"], dropna=True):
        overs = grp[grp["Over Price"].notna() & (grp["Over Price"] >= min_price)].to_dict("records")
        unders = grp[grp["Under Price"].notna() & (grp["Under Price"] >= min_price)].to_dict("records")
        if not overs or not unders:
            continue

        for o in overs:
            for u in unders:
                if o["bookmakers"] == u["bookmakers"]:
                    continue

                over_line, under_line = float(o["Line"]), float(u["Line"])
                gap = under_line - over_line

                dec_o = american_to_decimal(o["Over Price"])
                dec_u = american_to_decimal(u["Under Price"])
                if math.isnan(dec_o) or math.isnan(dec_u):
                    continue

                # Return if exactly one leg wins, with stakes split so either
                # single win pays the same.
                single = dec_o * dec_u / (dec_o + dec_u)

                if gap >= 0:
                    window, width = middle_window(over_line, under_line)
                    one_wins = single - 1.0          # the usual outcome
                    both = 2.0 * single - 1.0        # the window: both legs cash
                    if width == 0:
                        kind = "arb" if one_wins > 0 else "no-edge"
                    else:
                        kind = "middle+arb" if one_wins > 0 else "middle"
                    # How often the window must land to cover the outside cost.
                    breakeven = (-one_wins / (both - one_wins)) if one_wins < 0 else 0.0
                else:
                    # Over on the HIGHER line: the legs leave a hole rather than
                    # an overlap, and the window is where BOTH lose.
                    window, width = reverse_window(over_line, under_line)
                    one_wins = single - 1.0
                    both = -1.0                      # the window: both legs lose
                    kind = "reverse"
                    # Max tolerable chance of landing in the hole: p = (s-1)/s.
                    breakeven = (single - 1.0) / single if single > 0 else 0.0
                    if not include_reverse:
                        continue

                if kind == "no-edge":
                    continue

                rows.append({
                    "Player": player,
                    "market": market,
                    "kind": kind,
                    "over_book": o["bookmakers"],
                    "over_line": over_line,
                    "over_price": float(o["Over Price"]),
                    "under_book": u["bookmakers"],
                    "under_line": under_line,
                    "under_price": float(u["Under Price"]),
                    "gap": round(gap, 1),
                    "window": window,
                    "window_width": width,
                    "stake_over_pct": round(100 * dec_u / (dec_o + dec_u), 1),
                    "one_wins_pct": round(100 * one_wins, 2),
                    "window_pct": round(100 * both, 2),
                    "breakeven_window_rate_pct": round(100 * breakeven, 1),
                    "commence_time": o.get("commence_time"),
                    "home_team": o.get("home_team"),
                    "away_team": o.get("away_team"),
                    # Older of the two legs: a pair is only as current as its
                    # staler side, and claiming the fresher one would overstate
                    # how live the opportunity is.
                    "fetched_at": min(
                        [str(x) for x in (o.get("fetched_at"), u.get("fetched_at")) if x]
                        or [""]
                    ) or None,
                })

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    # Guaranteed beats probable; reverse pairs sink to the bottom where they
    # belong, kept only so you can see they were considered and why they lost.
    out["_rank"] = out["kind"].map(
        {"middle+arb": 0, "arb": 1, "middle": 2, "reverse": 3}).fillna(4)
    return (out.sort_values(["_rank", "one_wins_pct", "window_pct"],
                            ascending=[True, False, False])
               .drop(columns="_rank")
               .reset_index(drop=True))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-price", type=float, default=MIN_PRICE,
                    help="minimum American odds on BOTH legs (default +100)")
    ap.add_argument("--sport", required=True, choices=sorted(SPORTS))
    ap.add_argument("--include-reverse", action="store_true",
                    help="also list Over-high/Under-low pairs, which lose BOTH legs "
                         "in the gap between the lines (off by default)")
    args = ap.parse_args()

    cfg = SPORTS[args.sport]
    source = DATA_ROOT / cfg.slug / cfg.output
    output = DATA_ROOT / cfg.slug / f"{cfg.slug}_prop_middles.parquet"

    if not source.exists():
        print(f"{source} not found -- run get_props.py --sport {cfg.slug} first.")
        return 0

    df = pd.read_parquet(source)
    if df.empty:
        print("props file is empty; nothing to scan")
        return 0

    before = len(df)
    df = df[~df["bookmakers"].str.lower().isin(EXCLUDED_BOOKS)]
    df = df.dropna(subset=["Line"])
    print(f"{before} rows -> {len(df)} after book exclusions")

    pairs = find_pairs(df, args.min_price, args.include_reverse)
    if pairs.empty:
        print("no qualifying pairs")
        output.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame().to_parquet(output, index=False)
        return 0

    counts = pairs["kind"].value_counts().to_dict()
    print(f"{len(pairs)} pairs: {counts}")
    print("\ntop 10:")
    cols = ["Player", "market", "kind", "over_book", "over_line", "over_price",
            "under_book", "under_line", "under_price", "window",
            "one_wins_pct", "window_pct", "breakeven_window_rate_pct"]
    print(pairs[cols].head(10).to_string(index=False))

    output.parent.mkdir(parents=True, exist_ok=True)
    pairs.to_parquet(output, index=False)
    print(f"\nwrote {len(pairs)} rows -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
