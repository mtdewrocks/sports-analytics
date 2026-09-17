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

  SWAPPED LINES (gap < 0) is an ANTI-MIDDLE, not a busted middle to discard.
  Over on the HIGHER line and Under on the LOWER line leaves a gap where BOTH
  legs lose instead of both winning -- see "THE DIRECTION IS THE WHOLE THING"
  below. It is still a real, nameable bet: profitable everywhere except that
  one narrow result, which is exactly the trade for someone confident the
  game won't land there. Labelled `anti_middle`, always included -- not an
  opt-in flag anymore, since discarding it entirely was hiding a real
  strategy rather than just a trap.

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

With MIN_PRICE=100 requiring plus money on both legs (both decimal odds
>= 2.0), single_win_return is provably >= 1 (AM-GM on 1/dec_o + 1/dec_u),
with equality ONLY when both legs are priced at exactly +100. That is the
one case where an anti-middle has zero edge -- it can only break even (the
window never lands) or lose everything (it does), never actually profit --
so those rows are dropped in find_pairs() rather than shown as a real
opportunity with nothing behind it.

THE DIRECTION IS THE WHOLE THING
--------------------------------
The Over must be on the LOWER line for a middle. Swap them and the arithmetic
inverts into the other tradeable shape, the anti-middle:

    Over 1.5 @ +120 / Under 2.5 @ +115   ->  middle: both win on exactly 2
    Over 2.5 @ +120 / Under 1.5 @ +150   ->  anti-middle: both LOSE on exactly 2

The second pair isn't a middle with a smaller edge, and it isn't garbage
either -- it is the opposite bet, correct for the opposite belief. Staked for
equal returns it profits on every outcome except landing exactly in the gap,
so it is a bet that the result will land somewhere else, priced by how
confident you are that it will. `breakeven_window_rate_pct` is the number that
matters here: the highest chance the gap result can have before this stops
being worth it. Compare that number to how likely the gap outcome actually is
for the market in question -- that comparison is a judgment call this script
doesn't make, because it depends on how discrete the stat is:

  MLB counting stats (hits, total bases, RBIs) take few possible values, so a
  one-value gap is often a genuinely common outcome -- "exactly 2 total
  bases" can be a 25-30% occurrence, comfortably above almost any breakeven
  this math produces. These usually are the trap they look like.

  Continuous-ish markets (NFL passing/rushing yards, NBA points) spread
  across a much wider range, so a similarly narrow gap is far less likely to
  be the one number that lands -- "exactly 75 rushing yards" is a much
  thinner slice of the distribution than "exactly 2 total bases" is. These
  are where an anti-middle is more likely to actually clear its breakeven.

This script does not know a market's outcome distribution and doesn't try to
handicap `anti_middle` rows for you -- it prices the trade and leaves the "is
this gap actually unlikely" judgment to the person reading the page.

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

from props_config import (  # noqa: E402
    DFS_BOOKS, NO_SINGLE_BET_BOOKS, SPORTS, UNBETTABLE_BOOKS,
)

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"

# Pairing drops both kinds: books you won't bet at, AND pick'em apps where a
# single leg can't be placed at the quoted price. The second group stays in
# Daily_Props.parquet and on the props page -- they're excluded from PAIRS,
# not from the data.
EXCLUDED_BOOKS = UNBETTABLE_BOOKS | NO_SINGLE_BET_BOOKS

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


def anti_middle_window(over_line: float, under_line: float) -> tuple[str, int]:
    """Integer results where BOTH legs LOSE -- the mirror image of a middle.

    When the Over sits on the HIGHER line, the two legs no longer overlap; they
    leave a hole between them instead.

        Over 1.5 / Under 0.5  ->  Over needs 2+, Under needs 0.
                                  Exactly 1 loses both.

    This is the anti-middle's window -- not a busted middle, the trade for
    someone confident the result won't be the one number in this hole. For a
    market with few possible outcomes (MLB hits, total bases) the hole is
    often the single most common result, which makes the bet a bad one; for a
    market spread across a wide range (NFL yardage, NBA points) the same
    one-number hole is a much thinner slice of what can happen. See the
    module docstring's THE DIRECTION IS THE WHOLE THING section.
    """
    return _span(math.ceil(under_line), math.floor(over_line))


def find_pairs(df: pd.DataFrame, min_price: float = MIN_PRICE) -> pd.DataFrame:
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
                    # an overlap, and the window is where BOTH lose. A real,
                    # nameable trade (see THE DIRECTION IS THE WHOLE THING in
                    # the module docstring) -- always included, not gated
                    # behind a flag, since discarding it entirely was hiding a
                    # real strategy rather than just a trap.
                    window, width = anti_middle_window(over_line, under_line)
                    one_wins = single - 1.0
                    both = -1.0                      # the window: both legs lose
                    kind = "anti_middle"
                    # Max tolerable chance of landing in the hole: p = (s-1)/s.
                    breakeven = (single - 1.0) / single if single > 0 else 0.0

                if kind == "no-edge":
                    continue

                if kind == "anti_middle" and one_wins <= 1e-9:
                    # Both legs at exactly +100 (dec 2.0 each) -- the only way
                    # an anti-middle can hit zero edge here, see THE MATH
                    # above. There's no scenario where this pays: outside the
                    # window it's a flat break-even, inside it you lose
                    # everything. Not a real candidate, just noise that reads
                    # as an opportunity ("worth it only if the window lands
                    # under 0% of the time") when there's nothing to take.
                    continue

                # Flagged, not filtered. A pick'em leg cannot usually be taken
                # as a standalone bet at the price shown, so the payout columns
                # on these rows describe arithmetic rather than something you
                # can actually place -- but the pair is still a real signal
                # that the two sides disagree about the number.
                dfs = sorted({o["bookmakers"], u["bookmakers"]} & DFS_BOOKS)

                rows.append({
                    "Player": player,
                    "market": market,
                    "kind": kind,
                    "dfs_leg": ",".join(dfs),
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
    # Guaranteed beats probable; anti-middles sink to the bottom of that
    # ordering, not because they're worse, but because they need a judgment
    # call (is the hole actually unlikely?) that a guaranteed-money row
    # doesn't -- see THE DIRECTION IS THE WHOLE THING in the module docstring.
    out["_rank"] = out["kind"].map(
        {"middle+arb": 0, "arb": 1, "middle": 2, "anti_middle": 3}).fillna(4)
    return (out.sort_values(["_rank", "one_wins_pct", "window_pct"],
                            ascending=[True, False, False])
               .drop(columns="_rank")
               .reset_index(drop=True))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-price", type=float, default=MIN_PRICE,
                    help="minimum American odds on BOTH legs (default +100)")
    ap.add_argument("--sport", required=True, choices=sorted(SPORTS))
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

    pairs = find_pairs(df, args.min_price)
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
