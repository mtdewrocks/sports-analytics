"""Work out WHY our wOBA differs from FanGraphs. Reads the local store only.

Run in Spyder: just press Run. No arguments, no re-pull.

wOBA is  sum(woba_value) / sum(woba_denom), and by definition:

    denominator = AB + unintentional BB + HBP + SF     (IBB and sac bunts excluded)
    numerator   = w1B*1B + w2B*2B + w3B*3B + wHR*HR + wBB*uBB + wHBP*HBP

If your counting stats already match FanGraphs, then AB and the hit types are
right, so a wOBA gap can only come from one of two places:

  1. DENOMINATOR COMPOSITION -- Savant including or excluding something
     FanGraphs doesn't (intentional walks and sacrifice bunts are the usual
     suspects). A denominator that is too small inflates wOBA.

  2. THE WEIGHTS -- Savant's linear weights differing from FanGraphs'. These are
     recomputed every season, and mid-season the current year's constants are
     provisional on both sides, so they can legitimately disagree slightly.

This script tests both. Because woba_num is literally a weighted sum of event
counts, regressing it on those counts recovers the exact weights Savant used --
compare them against FanGraphs' published constants for the season.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def script_dir() -> Path:
    try:
        return Path(__file__).resolve().parent
    except NameError:
        return Path.cwd().resolve()


HERE = script_dir()
sys.path.insert(0, str(HERE))

# ---------------------------------------------------------------- CONFIG ----
SEASON = 2026
STORE = HERE / "data" / f"daily_components_{SEASON}.parquet"
ROLE = "batter"
MIN_PA = 100          # ignore tiny samples; they add noise, not signal
# ----------------------------------------------------------------------------

log = logging.getLogger("woba")

# FanGraphs' published wOBA constants, from https://www.fangraphs.com/guts.aspx?type=cn
# These move every season and in-season figures are provisional.
FG_WEIGHTS_BY_SEASON = {
    2026: {"wBB": 0.698, "wHBP": 0.729, "w1B": 0.889, "w2B": 1.260, "w3B": 1.594, "wHR": 2.046},
    2025: {"wBB": 0.691, "wHBP": 0.722, "w1B": 0.882, "w2B": 1.252, "w3B": 1.584, "wHR": 2.037},
    2024: {"wBB": 0.689, "wHBP": 0.720, "w1B": 0.882, "w2B": 1.254, "w3B": 1.590, "wHR": 2.050},
    2023: {"wBB": 0.696, "wHBP": 0.726, "w1B": 0.883, "w2B": 1.244, "w3B": 1.569, "wHR": 2.004},
}
FG_REFERENCE = FG_WEIGHTS_BY_SEASON.get(
    SEASON, {"wBB": 0.690, "wHBP": 0.722, "w1B": 0.888, "w2B": 1.271, "w3B": 1.616, "wHR": 2.101}
)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s",
                        stream=sys.stdout, force=True)

    if not STORE.exists():
        print(f"No store at {STORE}\nRun update_stats.py first.")
        return 1

    store = pd.read_parquet(STORE)
    store = store[store["role"] == ROLE]
    totals = store.groupby("player_id", as_index=False).sum(numeric_only=True)
    totals = totals[totals["pa"] >= MIN_PA]
    print(f"{len(totals)} {ROLE}s with {MIN_PA}+ PA\n")

    # ---------------------------------------------------------------------- #
    # 1. Which denominator definition does Savant's woba_denom actually match?
    # ---------------------------------------------------------------------- #
    ubb = totals["bb"] - totals["ibb"]
    candidates = {
        "AB + uBB + HBP + SF          (FanGraphs definition)":
            totals["ab"] + ubb + totals["hbp"] + totals["sf"],
        "AB + BB + HBP + SF           (IBB NOT excluded)":
            totals["ab"] + totals["bb"] + totals["hbp"] + totals["sf"],
        "AB + uBB + HBP + SF + SH     (sac bunts included)":
            totals["ab"] + ubb + totals["hbp"] + totals["sf"] + totals["sh"],
        "PA                           (everything)":
            totals["pa"],
    }

    print("=" * 72)
    print("1. DENOMINATOR -- what does Savant's woba_denom equal?")
    print("=" * 72)
    observed = totals["woba_den"]
    best = None
    for label, candidate in candidates.items():
        diff = (observed - candidate)
        exact = int((diff.abs() < 1e-6).sum())
        print(f"  {label}")
        print(f"      exact matches {exact:4d}/{len(totals)}   "
              f"mean diff {diff.mean():+.3f}   total diff {diff.sum():+.0f}")
        if best is None or exact > best[1]:
            best = (label, exact)
    print(f"\n  --> closest fit: {best[0]}  ({best[1]}/{len(totals)} exact)")

    if best[1] < len(totals) * 0.95:
        print(
            "\n  WARNING: no definition fits cleanly. If woba_denom is smaller than\n"
            "  the FanGraphs definition, that alone inflates our wOBA -- a missing\n"
            "  plate appearance that should contribute 0 to the numerator but 1 to\n"
            "  the denominator raises the ratio."
        )

    # ---------------------------------------------------------------------- #
    # 2. Recover the weights Savant used, by least squares.
    #    woba_num is a weighted sum of event counts, so this is near-exact.
    # ---------------------------------------------------------------------- #
    print("\n" + "=" * 72)
    print("2. WEIGHTS -- solving woba_num for the linear weights Savant used")
    print("=" * 72)

    design = pd.DataFrame({
        "w1B": totals["singles"], "w2B": totals["doubles"],
        "w3B": totals["triples"], "wHR": totals["hr"],
        "wBB": ubb, "wHBP": totals["hbp"],
    }).astype(float)
    target = totals["woba_num"].astype(float).to_numpy()

    solution, residuals, rank, _ = np.linalg.lstsq(design.to_numpy(), target, rcond=None)
    fitted = design.to_numpy() @ solution
    r2 = 1 - ((target - fitted) ** 2).sum() / ((target - target.mean()) ** 2).sum()

    print(f"  fit quality R^2 = {r2:.6f}   (should be ~1.000 -- woba_num IS a")
    print(f"                                weighted sum of these counts)\n")
    print(f"  {'event':6}{'recovered':>12}{'FanGraphs ref':>15}{'difference':>13}")
    print("  " + "-" * 44)
    for name, value in zip(design.columns, solution):
        reference = FG_REFERENCE[name]
        print(f"  {name:6}{value:>12.4f}{reference:>15.4f}{value - reference:>+13.4f}")

    if r2 < 0.999:
        print(
            "\n  R^2 below 0.999 means woba_num is NOT explained by these six events\n"
            "  alone -- something else is contributing to the numerator. Check for\n"
            "  unclassified events in the update_stats.py log."
        )

    # ---------------------------------------------------------------------- #
    # 3. Is the gap a flat scale factor or does it track event mix?
    # ---------------------------------------------------------------------- #
    print("\n" + "=" * 72)
    print("3. SHAPE OF THE GAP")
    print("=" * 72)

    fg_denominator = totals["ab"] + ubb + totals["hbp"] + totals["sf"]
    our_woba = totals["woba_num"] / totals["woba_den"].where(totals["woba_den"] > 0)
    woba_fg_denominator = totals["woba_num"] / fg_denominator.where(fg_denominator > 0)

    delta = (our_woba - woba_fg_denominator).dropna()
    print(f"  wOBA using Savant's denominator vs the FanGraphs denominator:")
    print(f"      mean difference {delta.mean():+.5f}   max {delta.abs().max():.5f}")
    if delta.abs().mean() > 0.0005:
        print("      --> the denominator alone explains a meaningful part of the gap")
    else:
        print("      --> denominators agree; the gap is in the weights, not the counts")

    mix = pd.DataFrame({
        "bb_rate": ubb / totals["pa"],
        "hr_rate": totals["hr"] / totals["pa"],
        "k_rate": totals["so"] / totals["pa"],
        "hbp_rate": totals["hbp"] / totals["pa"],
    })
    print("\n  Correlation of our wOBA with event mix (for reference when you")
    print("  compare against the FanGraphs column in your workbook):")
    for column in mix.columns:
        print(f"      {column:10} r = {our_woba.corr(mix[column]):+.3f}")

    print(
        "\n" + "=" * 72 + "\n"
        "HOW TO READ THIS\n" + "=" * 72 + "\n"
        "  * Section 1 says which denominator Savant uses. If it is NOT the\n"
        "    FanGraphs definition, that is your answer.\n"
        "  * Section 2 recovers Savant's weights. Compare them to the current\n"
        "    season's constants at fangraphs.com/guts.aspx -- if they differ,\n"
        "    the two sources genuinely disagree and neither is wrong. Mid-season\n"
        "    constants are provisional on both sides.\n"
        "  * If both sections look clean, the remaining suspect is the extra\n"
        "    partial day of games: set EXCLUDE_TODAY = True in update_stats.py\n"
        "    and re-run before comparing again."
    )
    return 0


if __name__ == "__main__":
    code = main()
    if "ipykernel" in sys.modules or "spyder_kernels" in sys.modules or hasattr(sys, "ps1"):
        print(f"\n[done, exit code {code}]")
    else:
        sys.exit(code)
