"""Predict strikeouts for today's probable starters.

For each starter: expected K, a typical range (Poisson 10th-90th pct),
and P(over) for common lines. Opposing lineup K propensity uses the
confirmed lineup when posted, else the opponent's last lineup.

Usage: python src/predict_k.py [YYYY-MM-DD] [--line 6.5]
Output: output/k_predictions_{date}.csv
"""
import sys
from datetime import date as date_cls
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.stats import poisson

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import FEAT_DIR, MODEL_DIR, OUT_DIR
from src.predict_upcoming import (get_schedule, pitcher_info, confirmed_lineup,
                                  projected_lineup, latest_features,
                                  team_abbrevs)

LINES = [3.5, 4.5, 5.5, 6.5, 7.5]


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    day = args[0] if args else str(date_cls.today())
    extra_line = None
    if "--line" in sys.argv:
        extra_line = float(sys.argv[sys.argv.index("--line") + 1])

    bundle = joblib.load(MODEL_DIR / "k_model.joblib")
    model, feats = bundle["model"], bundle["features"]

    pit = pd.read_parquet(FEAT_DIR / "pitcher_daily.parquet")
    ars = pd.read_parquet(FEAT_DIR / "pitcher_arsenal_daily.parquet")
    park = pd.read_parquet(FEAT_DIR / "park_daily.parquet")
    bh = pd.read_parquet(FEAT_DIR / "batter_vs_hand_daily.parquet")
    kt = pd.read_parquet(FEAT_DIR / "k_table.parquet")
    pw = pd.read_parquet(FEAT_DIR / "pitcher_whiff_daily.parquet")
    bvc = pd.read_parquet(FEAT_DIR / "batter_vs_class_daily.parquet")
    ru = pd.read_parquet(FEAT_DIR / "relief_usage_daily.parquet")
    abbr = team_abbrevs()
    day_ts = pd.Timestamp(day)

    rows = []
    for g in get_schedule(day):
        if g["status"]["abstractGameState"] != "Preview":
            continue
        for side, opp in (("home", "away"), ("away", "home")):
            prob = g["teams"][side].get("probablePitcher")
            if not prob:
                continue
            sp_id = prob["id"]
            try:
                hand, sp_name, _ = pitcher_info(sp_id, day[:4])
            except Exception:
                hand, sp_name = "R", prob.get("fullName", str(sp_id))

            hist = kt[kt["pitcher"] == sp_id].sort_values("game_date")
            if hist.empty:
                print(f"skip {sp_name}: no starter history in data")
                continue
            last = hist.iloc[-1]
            f = dict(is_home=1 if side == "home" else 0,
                     month=int(day[5:7]),
                     starts_career=len(hist),
                     bf_last5_avg=float(hist["bf"].tail(5).mean()),
                     k_last5_avg=float(hist["k"].tail(5).mean()),
                     p_days_rest=min((day_ts - last["game_date"]).days, 15))
            f.update(latest_features(pit, ["pitcher"], [sp_id], "p_"))
            f.update(latest_features(ars, ["pitcher"], [sp_id], "ars_"))
            f.update(latest_features(pw, ["pitcher"], [sp_id], "pw_"))
            if "ars_r30_velo_fb" in f and "ars_exp_velo_fb" in f:
                f["ars_velo_fb_delta"] = f["ars_r30_velo_fb"] - f["ars_exp_velo_fb"]

            # own team's pen usage yesterday / last 3 days
            own_abbr = abbr.get(g["teams"][side]["team"]["id"], "")
            if len(ru):
                recent = ru[(ru["def_team"] == own_abbr)
                            & (ru["game_date"] >= day_ts - pd.Timedelta("3D"))
                            & (ru["game_date"] < day_ts)]
                f["pen_bf_yesterday"] = float(
                    recent[recent["game_date"] == day_ts - pd.Timedelta("1D")]
                    ["rel_bf"].sum())
                f["pen_bf_last3"] = float(recent["rel_bf"].sum())

            # opposing lineup (confirmed if posted, else last lineup)
            opp_team = g["teams"][opp]["team"]
            lineup = confirmed_lineup(g["gamePk"], opp_team["id"]) or \
                projected_lineup(opp_team["id"], day)
            src = "confirmed" if confirmed_lineup(g["gamePk"], opp_team["id"]) \
                else "projected"
            krs, wobas = [], []
            wclass = {c: [] for c in ("fb", "br", "os")}
            for pid, _ in lineup:
                lf = latest_features(bh, ["batter", "p_throws"], [pid, hand], "")
                if lf:
                    krs.append(lf.get("exp_k_rate"))
                    wobas.append(lf.get("exp_woba"))
                for c in wclass:
                    cf = latest_features(bvc[bvc["pitch_class"] == c],
                                         ["batter"], [pid], "")
                    if cf:
                        wclass[c].append(cf.get("exp_whiff_rate"))
            if krs:
                f["opp_exp_k_rate"] = float(np.nanmean(krs))
                f["opp_exp_woba"] = float(np.nanmean(wobas))
                f["opp_n"] = len(krs)
            num, den = 0.0, 0.0
            for c, vals in wclass.items():
                if vals:
                    f[f"opp_whiff_{c}"] = float(np.nanmean(vals))
                    u = f.get(f"ars_exp_usage_{c}", 0.33)
                    num += u * f[f"opp_whiff_{c}"]
                    den += u
            if den:
                f["matchup_whiff"] = num / den

            home_abbr = abbr.get(g["teams"]["home"]["team"]["id"], "")
            f.update(latest_features(park, ["home_team"], [home_abbr], "park_"))
            kr = (f.get("p_exp_k_rate", 0.22) + f.get("opp_exp_k_rate", 0.22)) / 2
            f["analytic_k"] = f["bf_last5_avg"] * kr

            rows.append({"date": day, "game_pk": g["gamePk"],
                         "pitcher": sp_name, "pitcher_id": sp_id,
                         "team": g["teams"][side]["team"]["name"],
                         "opponent": opp_team["name"], "lineup_source": src,
                         **f})
    if not rows:
        print("no predictable starters for", day)
        return
    X = pd.DataFrame(rows)
    mu = model.predict(X.reindex(columns=feats)).clip(0.5, 15)
    out = X[["date", "game_pk", "pitcher", "pitcher_id", "team", "opponent",
             "lineup_source"]].copy()
    out["expected_k"] = mu.round(2)
    out["range_10th"] = poisson.ppf(0.10, mu).astype(int)
    out["range_90th"] = poisson.ppf(0.90, mu).astype(int)
    lines = LINES + ([extra_line] if extra_line and extra_line not in LINES else [])
    for line in lines:
        out[f"p_over_{line}"] = (1 - poisson.cdf(int(np.floor(line)), mu)).round(3)
    out = out.sort_values("expected_k", ascending=False)
    dest = OUT_DIR / f"k_predictions_{day}.csv"
    out.to_csv(dest, index=False)
    print(out[["pitcher", "team", "opponent", "expected_k", "range_10th",
               "range_90th", "p_over_5.5", "lineup_source"]].to_string(index=False))
    print(f"\nsaved -> {dest}")


if __name__ == "__main__":
    main()
