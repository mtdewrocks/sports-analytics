"""A small expected-goals (xG) model for NHL unblocked shot attempts.

Why our own: MoneyPuck's xG is free but licensed for non-commercial use
only. This one is trained on the play-by-play the pipeline already stores,
so it carries no extra licence and can be retrained whenever.

Model: logistic regression (plain numpy, iteratively reweighted least
squares with a light ridge penalty) on distance, angle, shot type, rebound,
rush and strength. That is roughly the feature set of the public models
(Evolving-Hockey, MoneyPuck) minus the ones that need data we don't keep.
Empty-net attempts are excluded from training and get no xG: they would
otherwise dominate the goalie numbers built on top of this.

    model = fit_model(shots_df)      # dict, JSON-serialisable
    shots_df["xg"] = predict(shots_df, model)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import numpy as np
import pandas as pd

SHOT_TYPES = ["wrist", "snap", "slap", "backhand", "tip-in", "deflected", "wrap-around"]
MIN_TRAIN = 5000   # fewer shots than this -> keep the hand-set prior below

# Hand-set fallback (roughly: 10 ft ~ 18%, 30 ft ~ 6%, 60 ft ~ 1%) so the
# very first run, or a test with a synthetic game, still produces sane xG.
PRIOR = {
    "kind": "prior",
    "features": ["distance", "rebound", "rush", "pp", "sh"],
    "mean": [0, 0, 0, 0, 0], "std": [1, 1, 1, 1, 1],
    "coef": [-0.9, -0.06, 1.0, 0.3, 0.3, -0.3],
}


def _design(df: pd.DataFrame) -> pd.DataFrame:
    dist = df["distance"].astype(float).clip(0, 200)
    ang = df["angle"].astype(float).clip(0, 180) / 90.0
    st = df["shot_type"].fillna("unknown").astype(str).str.lower()
    out = pd.DataFrame({
        "distance": dist,
        "log_distance": np.log1p(dist),
        "angle": ang,
        "angle_sq": ang ** 2,
        "behind_net": (df["x"].astype(float) > 89).astype(float),
        "rebound": df["rebound"].astype(float),
        "rush": df["rush"].astype(float),
        "pp": (df["strength"] == "pp").astype(float),
        "sh": (df["strength"] == "sh").astype(float),
    }, index=df.index)
    for t in SHOT_TYPES:
        out[f"type_{t}"] = (st == t).astype(float)
    return out


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def fit_model(shots: pd.DataFrame, l2: float = 1.0, iters: int = 30) -> Dict[str, Any]:
    train = shots[~shots["empty_net"].astype(bool)].dropna(subset=["distance", "angle", "x"])
    if len(train) < MIN_TRAIN:
        return dict(PRIOR)
    X = _design(train)
    feats = list(X.columns)
    mean, std = X.mean().values, X.std().replace(0, 1).values
    Z = (X.values - mean) / std
    Z = np.hstack([np.ones((len(Z), 1)), Z])
    y = train["is_goal"].astype(float).values
    w = np.zeros(Z.shape[1])
    w[0] = np.log(max(y.mean(), 1e-4) / max(1 - y.mean(), 1e-4))
    reg = np.full(Z.shape[1], l2); reg[0] = 0.0
    for _ in range(iters):
        p = _sigmoid(Z @ w)
        grad = Z.T @ (y - p) - reg * w
        H = (Z * (p * (1 - p))[:, None]).T @ Z + np.diag(reg)
        step = np.linalg.solve(H, grad)
        w += step
        if np.abs(step).max() < 1e-6:
            break
    p = _sigmoid(Z @ w)
    ll = float(np.mean(y * np.log(p + 1e-12) + (1 - y) * np.log(1 - p + 1e-12)))
    # Sanity check: a fit that doesn't reproduce the league goal rate, or has
    # run off to huge coefficients (perfectly separable data), is worse than
    # the prior. Keep the prior and say so in the meta file.
    if not np.isfinite(w).all() or abs(p.mean() - y.mean()) > 0.1 * max(y.mean(), 1e-3) \
            or np.abs(w[1:]).max() > 20:
        return {**PRIOR, "kind": "prior (fit rejected)", "n": int(len(train))}
    return {
        "kind": "logistic", "features": feats, "mean": mean.tolist(), "std": std.tolist(),
        "coef": w.tolist(), "n": int(len(train)), "goal_rate": float(y.mean()),
        "log_loss": -ll, "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def predict(shots: pd.DataFrame, model: Dict[str, Any]) -> pd.Series:
    if shots.empty:
        return pd.Series([], dtype=float, index=shots.index)
    X = _design(shots)[model["features"]]
    Z = (X.values - np.array(model["mean"])) / np.array(model["std"])
    Z = np.hstack([np.ones((len(Z), 1)), Z])
    xg = pd.Series(_sigmoid(Z @ np.array(model["coef"])), index=shots.index).round(4)
    xg[shots["empty_net"].astype(bool)] = np.nan
    return xg
