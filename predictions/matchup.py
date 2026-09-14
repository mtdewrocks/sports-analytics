"""Weighted arsenal-matchup features, shared by training and prediction.

For each batter-game row: weight the batter's rolling stats vs each pitch
class (fb/br/os) by the opposing starter's usage of that class.
Example: matchup_r30_woba = sum_c usage_c * batter_woba_vs_c / sum_c usage_c
"""
import numpy as np
import pandas as pd

CLASSES = ["fb", "br", "os"]
STATS = ["woba", "avg", "k_rate", "whiff_rate"]


def add_matchup_features(g: pd.DataFrame, priors: dict) -> pd.DataFrame:
    vc_pri, usage_pri = priors["vc"], priors["usage"]
    for pre in ("exp_", "r30_"):
        for stat in STATS:
            num, den = 0.0, 0.0
            for c in CLASSES:
                ucol, vcol = f"ars_{pre}usage_{c}", f"bvc_{c}_{pre}{stat}"
                u = g[ucol].fillna(usage_pri[c]) if ucol in g else pd.Series(usage_pri[c], index=g.index)
                v = g[vcol].fillna(vc_pri[c][stat]) if vcol in g else pd.Series(vc_pri[c][stat], index=g.index)
                num = num + u * v
                den = den + u
            g[f"matchup_{pre}{stat}"] = num / den
    # fastball velocity trend: recent vs career (negative = losing velo)
    if "ars_r30_velo_fb" in g and "ars_exp_velo_fb" in g:
        g["ars_velo_fb_delta"] = g["ars_r30_velo_fb"] - g["ars_exp_velo_fb"]
    return g


def add_opportunity_features(g: pd.DataFrame) -> pd.DataFrame:
    """Analytic P(>=1 hit) from per-PA hit rates and expected PAs.

    Splits expected PAs into ~2.6 vs the starter and the rest vs the bullpen,
    then P(hit) = 1 - (1-h_starter)^pa_s * (1-h_pen)^pa_pen.
    Requires: expected_pa, bh_exp_hit_rate, ph_exp_hit_rate, b_exp_hit_rate,
    and optionally bp_exp_hit_rate (falls back to batter rate if absent).
    """
    need = ["expected_pa", "bh_exp_hit_rate", "ph_exp_hit_rate", "b_exp_hit_rate"]
    if not all(c in g.columns for c in need):
        return g
    h_start = (g["bh_exp_hit_rate"] + g["ph_exp_hit_rate"]) / 2
    if "bp_exp_hit_rate" in g.columns:
        h_pen = (g["b_exp_hit_rate"] + g["bp_exp_hit_rate"].fillna(g["b_exp_hit_rate"])) / 2
    else:
        h_pen = g["b_exp_hit_rate"]
    pa_s = np.minimum(g["expected_pa"].fillna(4.1), 2.6)
    pa_p = (g["expected_pa"].fillna(4.1) - pa_s).clip(lower=0)
    g["analytic_p_hit"] = 1 - (1 - h_start.clip(0, 0.5)) ** pa_s \
                            * (1 - h_pen.clip(0, 0.5)) ** pa_p
    return g
