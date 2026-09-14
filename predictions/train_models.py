"""Train two models on the game-level table:

  Model A  probability model  -> calibrated P(hit) in percent
  Model B  binary classifier  -> yes/no with a threshold tuned on validation

Split: last season = test, prior seasons = train (final 15% of train dates
held out for calibration + threshold tuning).

Usage: python src/train_models.py [first_train_year]
  e.g. `python src/train_models.py 2021` trains on 2021+ only (features
  still use all downloaded history, which is fine -- older data informs
  a player's career stats without contributing training rows).
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
from lightgbm import LGBMClassifier, early_stopping, log_evaluation
from sklearn.calibration import calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (accuracy_score, brier_score_loss, f1_score,
                             log_loss, roc_auc_score)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import FEAT_DIR, MODEL_DIR, OUT_DIR, MIN_PRIOR_PA, EXCLUDE_FEATURES

CAT = ["platoon_adv", "is_home", "month", "lineup_slot", "is_day"]


def feature_cols(df):
    pref = ("b_", "bh_", "p_", "ph_", "ars_", "bvc_", "matchup_", "bp_", "park_")
    extra = [c for c in ("expected_pa", "analytic_p_hit") if c in df.columns]
    cols = [c for c in df.columns if c.startswith(pref)
            and df[c].dtype.kind in "fi"] + [c for c in CAT if c in df.columns] + extra
    return [c for c in cols if c not in EXCLUDE_FEATURES]


def main():
    df = pd.read_parquet(FEAT_DIR / "train_table.parquet")
    if len(sys.argv) > 1:
        start_year = int(sys.argv[1])
        df = df[df["game_year"] >= start_year]
        print(f"using seasons {start_year}+ only")
    df = df[df["b_exp_pa"].fillna(0) >= MIN_PRIOR_PA]  # need some batter history
    feats = feature_cols(df)
    print(f"{len(df):,} rows, {len(feats)} features")

    test_year = int(df["game_year"].max())
    if df["game_year"].nunique() > 1:
        # normal: train on earlier seasons, test on the last one
        train_all = df[df["game_year"] < test_year]
        test = df[df["game_year"] == test_year]
        split_desc = str(test_year)
    else:
        # single season: first 70% of dates = train, last 30% = test
        test_cut = df["game_date"].quantile(0.70)
        train_all = df[df["game_date"] <= test_cut]
        test = df[df["game_date"] > test_cut]
        split_desc = f"{test_year} after {test_cut.date()}"
    cut = train_all["game_date"].quantile(0.85)
    train = train_all[train_all["game_date"] <= cut]
    calib = train_all[train_all["game_date"] > cut]
    print(f"train {len(train):,} | calib {len(calib):,} | test {len(test):,} ({split_desc})")

    X_tr, y_tr = train[feats], train["got_hit"]
    X_ca, y_ca = calib[feats], calib["got_hit"]
    X_te, y_te = test[feats], test["got_hit"]

    gbm = LGBMClassifier(
        n_estimators=2000, learning_rate=0.03, num_leaves=63,
        min_child_samples=200, subsample=0.8, colsample_bytree=0.7,
        reg_lambda=1.0, random_state=13,
    )
    gbm.fit(X_tr, y_tr, eval_set=[(X_ca, y_ca)], eval_metric="binary_logloss",
            callbacks=[early_stopping(100), log_evaluation(0)])

    # ---- Model A: isotonic-calibrated probabilities ----------------------
    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(gbm.predict_proba(X_ca)[:, 1], y_ca)
    p_te = iso.predict(gbm.predict_proba(X_te)[:, 1])

    base = np.full(len(y_te), y_tr.mean())
    metrics = {
        "test_year": test_year,
        "n_test": int(len(y_te)),
        "base_hit_rate_train": float(y_tr.mean()),
        "model_A_probability": {
            "auc": float(roc_auc_score(y_te, p_te)),
            "log_loss": float(log_loss(y_te, p_te.clip(1e-6, 1 - 1e-6))),
            "brier": float(brier_score_loss(y_te, p_te)),
            "brier_baseline_constant": float(brier_score_loss(y_te, base)),
        },
    }

    # ---- Model B: yes/no classifier with tuned threshold -----------------
    p_ca = iso.predict(gbm.predict_proba(X_ca)[:, 1])
    ths = np.linspace(0.3, 0.8, 101)
    f1s = [f1_score(y_ca, p_ca >= t) for t in ths]
    accs = [accuracy_score(y_ca, p_ca >= t) for t in ths]
    th_f1 = float(ths[int(np.argmax(f1s))])
    th_acc = float(ths[int(np.argmax(accs))])
    yhat = p_te >= th_acc
    metrics["model_B_classifier"] = {
        "threshold_max_accuracy": th_acc,
        "threshold_max_f1": th_f1,
        "accuracy": float(accuracy_score(y_te, yhat)),
        "f1": float(f1_score(y_te, yhat)),
        "accuracy_baseline_always_yes": float(y_te.mean()),
    }

    # ---- Beat-the-Streak style check: precision of top picks per day -----
    t = test[["game_date"]].copy()
    t["p"], t["y"] = p_te, y_te.values
    ranked = t.sort_values("p", ascending=False)
    for k in (3, 5, 10):
        top = ranked.groupby("game_date").head(k)
        metrics[f"top{k}_picks_per_day_hit_rate"] = float(top["y"].mean())

    # ---- save -------------------------------------------------------------
    joblib.dump({"gbm": gbm, "iso": iso, "features": feats},
                MODEL_DIR / "prob_model.joblib")
    json.dump({"threshold": th_acc, "threshold_f1": th_f1},
              open(MODEL_DIR / "classifier_threshold.json", "w"), indent=2)
    json.dump(metrics, open(OUT_DIR / "metrics.json", "w"), indent=2)
    print(json.dumps(metrics, indent=2))

    # calibration plot
    frac, mean_p = calibration_curve(y_te, p_te, n_bins=15)
    plt.figure(figsize=(5, 5))
    plt.plot(mean_p, frac, "o-", label="model")
    plt.plot([0, 1], [0, 1], "--", color="gray", label="perfect")
    plt.xlabel("predicted P(hit)"); plt.ylabel("observed hit rate")
    plt.title(f"Calibration, {test_year} test"); plt.legend(); plt.tight_layout()
    plt.savefig(OUT_DIR / "calibration.png", dpi=120)

    imp = pd.Series(gbm.feature_importances_, index=feats).nlargest(20)
    plt.figure(figsize=(7, 6))
    imp.iloc[::-1].plot.barh()
    plt.title("Top 20 feature importances"); plt.tight_layout()
    plt.savefig(OUT_DIR / "feature_importance.png", dpi=120)
    print(f"saved models -> {MODEL_DIR}, plots/metrics -> {OUT_DIR}")


if __name__ == "__main__":
    main()
