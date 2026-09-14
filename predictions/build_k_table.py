"""Build the training table for the pitcher-strikeout model: one row per
STARTER-game with label k = strikeouts recorded in that game.

Features (all strictly as-of before the game):
  p_*      pitcher overall rolling/career rates (K%, whiff-adjacent stats)
  ars_*    arsenal usage, fastball velo + trend
  opp_*    opposing starting lineup's K propensity vs this pitcher's hand
  park_*   venue rates
  bf_*     recent workload: batters faced per start (expected opportunity)
  analytic_k  expected_bf x blended K rate (first-principles baseline)

Run after build_features.py. Output: data/features/k_table.parquet
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import FEAT_DIR, RAW_DIR
from src.build_training_table import asof_join


def main():
    pa = pd.read_parquet(FEAT_DIR / "pa.parquet")

    # --- starters and their game K totals --------------------------------
    first = (pa.sort_values("at_bat_number")
               .groupby(["game_pk", "inning_topbot"], sort=False)
               .first().reset_index())
    starters = first[["game_pk", "inning_topbot", "pitcher", "game_date",
                      "home_team", "away_team"]].copy()
    starters["is_home"] = (starters["inning_topbot"] == "Top").astype("int8")

    per_game = (pa.groupby(["game_pk", "pitcher"], sort=False)
                  .agg(k=("k", "sum"), bf=("pa", "sum"),
                       game_year=("game_year", "first")).reset_index())
    g = starters.merge(per_game, on=["game_pk", "pitcher"], how="left")
    g["hand"] = g["pitcher"].map(
        pa[["pitcher", "p_throws"]].drop_duplicates("pitcher")
          .set_index("pitcher")["p_throws"])

    # --- recent workload: batters faced per start (leak-free) -------------
    g = g.sort_values(["pitcher", "game_date"]).reset_index(drop=True)
    grp = g.groupby("pitcher")
    g["bf_last5_avg"] = (grp["bf"].transform(
        lambda s: s.shift(1).rolling(5, min_periods=1).mean()))
    g["k_last5_avg"] = (grp["k"].transform(
        lambda s: s.shift(1).rolling(5, min_periods=1).mean()))
    g["starts_career"] = grp.cumcount()
    g["p_days_rest"] = grp["game_date"].diff().dt.days.clip(upper=15)

    # --- opposing lineup K propensity vs this hand ------------------------
    # lineup = first 9 distinct batters on the batting side of his halves
    bat_side = pa.merge(g[["game_pk", "pitcher"]].rename(
        columns={"pitcher": "starter"}), on="game_pk")
    faced = bat_side[bat_side["pitcher"] == bat_side["starter"]]
    lineup = (faced.sort_values("at_bat_number")
                   .drop_duplicates(["game_pk", "batter"])
                   .groupby("game_pk").head(9)
              [["game_pk", "batter", "game_date", "p_throws"]])
    bh = pd.read_parquet(FEAT_DIR / "batter_vs_hand_daily.parquet")
    lineup = asof_join(lineup, bh, ["batter", "p_throws"], "x_")
    opp = (lineup.groupby("game_pk")
                 .agg(opp_exp_k_rate=("x_exp_k_rate", "mean"),
                      opp_r30_k_rate=("x_r30_k_rate", "mean"),
                      opp_exp_woba=("x_exp_woba", "mean"),
                      opp_n=("batter", "size")).reset_index())
    g = g.merge(opp, on="game_pk", how="left")

    # lineup whiff rate vs each pitch class (for arsenal-weighted matchup)
    bvc = pd.read_parquet(FEAT_DIR / "batter_vs_class_daily.parquet")
    base = lineup[["game_pk", "batter", "game_date"]]
    for c in ("fb", "br", "os"):
        sub = bvc[bvc["pitch_class"] == c][["batter", "game_date",
                                            "exp_whiff_rate"]]
        j = asof_join(base, sub, ["batter"], f"w{c}_")
        agg = (j.groupby("game_pk")[f"w{c}_exp_whiff_rate"].mean()
                 .reset_index(name=f"opp_whiff_{c}"))
        g = g.merge(agg, on="game_pk", how="left")

    # --- pitcher stats, arsenal, park -------------------------------------
    pit = pd.read_parquet(FEAT_DIR / "pitcher_daily.parquet")
    ars = pd.read_parquet(FEAT_DIR / "pitcher_arsenal_daily.parquet")
    park = pd.read_parquet(FEAT_DIR / "park_daily.parquet")
    pw = pd.read_parquet(FEAT_DIR / "pitcher_whiff_daily.parquet")
    g = asof_join(g, pit, ["pitcher"], "p_")
    g = asof_join(g, ars, ["pitcher"], "ars_")
    g = asof_join(g, park, ["home_team"], "park_")
    g = asof_join(g, pw, ["pitcher"], "pw_")

    # arsenal-weighted matchup whiff: lineup's whiff vs each class x usage
    num, den = 0.0, 0.0
    for c in ("fb", "br", "os"):
        u = g.get(f"ars_exp_usage_{c}")
        w = g.get(f"opp_whiff_{c}")
        if u is not None and w is not None:
            uu = u.fillna(0.33)
            num = num + uu * w.fillna(w.mean())
            den = den + uu
    if not np.isscalar(den):
        g["matchup_whiff"] = num / den

    # pen fatigue: own team's relief batters faced yesterday / last 3 days
    ru = pd.read_parquet(FEAT_DIR / "relief_usage_daily.parquet")
    g["own_team"] = g["home_team"].where(g["is_home"] == 1, g["away_team"])
    if len(ru):
        ru = ru.rename(columns={"def_team": "own_team"})
        for lag_name, days in (("pen_bf_yesterday", 1), ("pen_bf_last3", 3)):
            total = 0.0
            for d in range(1, days + 1):
                lag = ru.copy()
                lag["game_date"] = lag["game_date"] + pd.Timedelta(days=d)
                lag = lag.rename(columns={"rel_bf": "x"})
                g = g.merge(lag[["own_team", "game_date", "x"]],
                            on=["own_team", "game_date"], how="left")
                total = total + g.pop("x").fillna(0)
            g[lag_name] = total
    else:
        g["pen_bf_yesterday"] = 0.0
        g["pen_bf_last3"] = 0.0
    if "ars_r30_velo_fb" in g and "ars_exp_velo_fb" in g:
        g["ars_velo_fb_delta"] = g["ars_r30_velo_fb"] - g["ars_exp_velo_fb"]

    meta_file = RAW_DIR / "game_meta.parquet"
    if meta_file.exists():
        meta = pd.read_parquet(meta_file)
        g = g.merge(meta, on="game_pk", how="left")
        g["is_day"] = (g["day_night"] == "day").astype("int8")

    # --- analytic baseline -------------------------------------------------
    league_k = pa["k"].sum() / pa["pa"].sum()
    kr = (g["p_exp_k_rate"].fillna(league_k)
          + g["opp_exp_k_rate"].fillna(league_k)) / 2
    g["analytic_k"] = g["bf_last5_avg"].fillna(24) * kr
    g["month"] = g["game_date"].dt.month

    out = FEAT_DIR / "k_table.parquet"
    g.to_parquet(out, index=False)
    print(f"k table: {len(g):,} starts, mean K = {g['k'].mean():.2f} -> {out}")


if __name__ == "__main__":
    main()
