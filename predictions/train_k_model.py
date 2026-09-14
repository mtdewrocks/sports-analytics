"""Train the starter-strikeout model.

Output A: expected K count (Poisson-objective LightGBM regression).
Output B: P(over any line) derived from the predicted mean via the Poisson
          distribution, with an empirical calibration check for common lines.

Split: last season = test.
Usage: python src/train_k_model.py [first_train_year] [--test-year 2025]
  --test-year N   test on season N and ignore anything after it (for
                  apples-to-apples comparisons across model versions)
Saves models/k_model.joblib, output/k_metrics.json, output/k_calibration.png
"""
import json
import sys
from pathlib import Path

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor, early_stopping, log_evaluation
from scipy.stats import poisson

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import FEAT_DIR, MODEL_DIR, OUT_DIR

MIN_PRIOR_STARTS = 3   # need some starter history
LINES = [3.5, 4.5, 5.5, 6.5, 7.5]


def feature_cols(df):
    pref = ("p_", "ars_", "opp_", "park_", "bf_", "k_last", "pw_", "matchup_", "pen_")
    cat = [c for c in ("is_home", "is_day", "month") if c in df.columns]
    extra = [c for c in ("analytic_k", "starts_career") if c in df.columns]
    return [c for c in df.columns if c.startswith(pref)
            and df[c].dtype.kind in "fi" and c != "p_throws"] + cat + extra


def main():
    df = pd.read_parquet(FEAT_DIR / "k_table.parquet")
    if "--test-year" in sys.argv:
        ty = int(sys.argv[sys.argv.index("--test-year") + 1])
        df = df[df["game_year"] <= ty]
    args = [a for a in sys.argv[1:] if not a.startswith("--")
            and a != str(sys.argv[sys.argv.index("--test-year") + 1]
                         if "--test-year" in sys.argv else None)]
    if args:
        df = df[df["game_year"] >= int(args[0])]
    df = df[df["starts_career"] >= MIN_PRIOR_STARTS].dropna(subset=["k"])
    feats = feature_cols(df)
    print(f"{len(df):,} starts, {len(feats)} features")

    test_year = int(df["game_year"].max())
    train_all = df[df["game_year"] < test_year]
    test = df[df["game_year"] == test_year]
    cut = train_all["game_date"].quantile(0.85)
    train = train_all[train_all["game_date"] <= cut]
    valid = train_all[train_all["game_date"] > cut]
    print(f"train {len(train):,} | valid {len(valid):,} | test {len(test):,} ({test_year})")

    m = LGBMRegressor(objective="poisson", n_estimators=2000,
                      learning_rate=0.03, num_leaves=63,
                      min_child_samples=100, subsample=0.8,
                      colsample_bytree=0.7, reg_lambda=1.0, random_state=13)
    m.fit(train[feats], train["k"], eval_set=[(valid[feats], valid["k"])],
          eval_metric="poisson",
          callbacks=[early_stopping(100), log_evaluation(0)])

    mu = m.predict(test[feats]).clip(0.5, 15)
    y = test["k"].values
    metrics = {
        "test_year": test_year, "n_test": int(len(y)),
        "mae": float(np.abs(mu - y).mean()),
        "rmse": float(np.sqrt(((mu - y) ** 2).mean())),
        "mae_baseline_league_mean": float(np.abs(y.mean() - y).mean()),
        "mae_baseline_pitcher_last5": float(
            np.abs(test["k_last5_avg"].fillna(y.mean()) - y).mean()),
        "mean_k_actual": float(y.mean()), "mean_k_predicted": float(mu.mean()),
    }

    # over/under calibration: Poisson P(over) vs what actually happened
    over = {}
    for line in LINES:
        p_over = 1 - poisson.cdf(int(np.floor(line)), mu)
        actual = (y > line).astype(float)
        bins = np.clip((p_over * 5).astype(int), 0, 4)
        cal = [(float(p_over[bins == b].mean()), float(actual[bins == b].mean()),
                int((bins == b).sum())) for b in range(5) if (bins == b).any()]
        over[str(line)] = {"predicted_over_rate": float(p_over.mean()),
                           "actual_over_rate": float(actual.mean()),
                           "calibration_bins (pred, actual, n)": cal}
    metrics["over_under"] = over

    joblib.dump({"model": m, "features": feats}, MODEL_DIR / "k_model.joblib")
    json.dump(metrics, open(OUT_DIR / "k_metrics.json", "w"), indent=2)
    print(json.dumps({k: v for k, v in metrics.items() if k != "over_under"},
                     indent=2))
    print("over/under (line: predicted vs actual over-rate):")
    for line in LINES:
        o = over[str(line)]
        print(f"  {line}: {o['predicted_over_rate']:.3f} vs "
              f"{o['actual_over_rate']:.3f}")

    plt.figure(figsize=(6, 5))
    plt.scatter(mu, y, s=4, alpha=0.15)
    lim = [0, max(15, y.max() + 1)]
    plt.plot(lim, lim, "--", c="gray")
    plt.xlabel("predicted E[K]"); plt.ylabel("actual K")
    plt.title(f"Starter strikeouts, {test_year} test")
    plt.tight_layout(); plt.savefig(OUT_DIR / "k_calibration.png", dpi=120)
    print(f"saved -> {MODEL_DIR / 'k_model.joblib'}, {OUT_DIR}/k_metrics.json")


if __name__ == "__main__":
    main()
