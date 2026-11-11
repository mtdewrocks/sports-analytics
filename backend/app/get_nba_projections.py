"""Daily NBA stat projections -- Shawn's model, automated.

    python backend/app/get_nba_projections.py

Runs in update_nba.yml right after get_nba_data.py, so the box scores and
schedule it reads are minutes old. Replaces the manual loop: scrape stats ->
hand-build a minutes file -> edit TODAY_FILE -> run -> paste into
nba_predictions.xlsx -> merge with FanDuel lines.

1. TRAIN. Shawn's feature set (nba_projection_features.py, identical names and
   windows) plus the v2 changes documented there (per-minute targets,
   starter rate, teammates' usage, this season weighted x3, Vegas lines when
   they help) on every 2025-26 and 2026-27 game -- one LightGBM model per
   stat plus a minutes model. Compared on 2026-27 games neither had seen, the
   first version already matched or beat the original random forests on
   every stat at ~1% of the size, which is what lets the site rerun it live
   when a user edits minutes. Retrained every run so it includes last night.

2. SLATE. Tonight's games (or the next game day), each team's rotation =
   anyone who played for them in their last 10 games, the injury report
   applied (Out players kept at 0 minutes so theirs can be shared out).

3. MINUTES. A minutes model (recent minutes, starter role, his share of the
   rotation available tonight, who's newly out or back, rest): 4.83 minutes
   average miss on 2026-27 vs 5.29 for the earlier hand-tuned rule, which
   stays as the fallback. The site lets users override any of them.

4. FEATURES WITHOUT MINUTES are published for the slate, so the API only has
   to fill in MIN and call the model.

5. LOG the default projections for grading once games are final.

Outputs (backend/data/nba/, published to data-nba):
  nba_projection_model.json      the seven stat models, the minutes model,
                                 calibration and holdout scores
  nba_projection_slate.parquet   tonight's players, features, default minutes
  nba_projection_log.parquet     every default projection, for grading
  nba_projection_plays.parquet   projections past Shawn's thresholds vs the
                                 main line, at the best price -- graded too
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import nba_projection_features as F  # noqa: E402
import nba_projection_edges as E  # noqa: E402
from props_config import DFS_BOOKS, SHARP_BOOKS, UNBETTABLE_BOOKS  # noqa: E402

OUT = HERE.parent / "data" / "nba"
ET = ZoneInfo("America/New_York")
ROTATION_LOOKBACK_GAMES = 10
HOLDOUT_DAYS = 21
CALIBRATION_DAYS = 90      # game days, not calendar days, so the offseason doesn't empty it
CAL_BINS = 8
CAL_QUANTILES = np.linspace(0.005, 0.995, 199)
LOG_RETAIN_DAYS = 400

PARAMS = {
    "objective": "poisson", "learning_rate": 0.08, "num_leaves": 7, "min_data_in_leaf": 40,
    "bagging_fraction": 0.8, "bagging_freq": 1, "feature_fraction": 0.8, "lambda_l2": 1.0,
    "verbose": -1, "seed": 42,
}
ROUNDS = 400


def match_key(name: str) -> str:
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r"[.'’]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv)\b", "", s)
    return " ".join(s.split())


def _weights(df: pd.DataFrame) -> np.ndarray:
    cur = df["Season"].max() if "Season" in df.columns else None
    w = np.where(df["Season"] == cur, F.SEASON_WEIGHT, 1.0) if cur is not None else np.ones(len(df))
    return w


def _fit(train: pd.DataFrame, stat: str, vegas: bool = False):
    """Per-minute model: stat / minute, weighted by minutes (and by season)."""
    import lightgbm as lgb
    cols = F.feature_columns_v2(stat, vegas)
    t = train[train["MIN"] >= 5]
    ds = lgb.Dataset(t[cols].astype(float), label=(t[stat] / t["MIN"]).astype(float),
                     weight=t["MIN"].astype(float).values * _weights(t))
    return lgb.train(PARAMS, ds, num_boost_round=ROUNDS), cols


def _fit_minutes(train: pd.DataFrame, cols=None):
    import lightgbm as lgb
    cols = cols or F.MINUTES_FEATURES
    ds = lgb.Dataset(train[cols].astype(float), label=train["MIN"].astype(float),
                     weight=_weights(train))
    return lgb.train(F.MINUTES_PARAMS, ds, num_boost_round=F.MINUTES_ROUNDS)


def _holdout_mae(tr, te, vegas: bool) -> dict:
    out = {}
    for st in F.TARGETS:
        m, cols = _fit(tr, st, vegas)
        p = m.predict(te[cols].astype(float)) * te["MIN"].values
        out[st] = round(float(np.abs(p - te[st]).mean()), 3)
    return out


def calibrate(X: pd.DataFrame, M: pd.DataFrame, vegas: bool, mcols=None) -> dict:
    """How actual results spread around a projection -- the piece that turns
    "projects 26 vs a 20.5 line" into a chance of going over.

    Fit the stat AND minutes models on everything before the last
    CALIBRATION_DAYS game days, project those games the way tonight's are
    projected (minutes from the minutes model, not what he actually played),
    and keep the distribution of actual / projected for CAL_BINS bands of
    projection size.

    Tested Nov 2026 by calibrating as of Oct 31 and grading Nov 1-9:
      * a bell curve around the projection ran ~10 points high on overs --
        scoring is lopsided (a few big nights pull the average above the
        typical game), which the empirical ratios capture
      * a 45-day window chased short-term bias; 90 game days was steadier:
        within 1-3 points of the actual hit rate for PTS/REB/AST/3PM
      * it still rates the very top projections' overs a bit low (40% vs 48%
        hit) -- the conservative direction
    """
    days = np.sort(X["GAME DATE"].unique())
    start = pd.Timestamp(days[-CALIBRATION_DAYS - 1]) if len(days) > CALIBRATION_DAYS else X["GAME DATE"].min()
    tr, cal = X[X["GAME DATE"] <= start], X[X["GAME DATE"] > start]
    mtr = M[M["GAME DATE"] <= start]
    if len(cal) < 1000 or len(tr) < 2000:
        return {}
    mcols = mcols or F.MINUTES_FEATURES
    mm = _fit_minutes(mtr, mcols)
    extra = [c for c in mcols if c not in cal.columns]
    cal = cal.merge(M[["PLAYER", "GAME DATE"] + extra], on=["PLAYER", "GAME DATE"], how="inner")
    proj_min = np.clip(mm.predict(cal[mcols].astype(float)), 0, F.MAX_MIN)
    pred = {}
    for st in F.TARGETS:
        m, cols = _fit(tr, st, vegas)
        pred[st] = m.predict(cal[cols].astype(float)) * proj_min
    pred["PRA"] = pred["PTS"] + pred["REB"] + pred["AST"]
    actual = {st: cal[st].values for st in F.TARGETS}
    actual["PRA"] = actual["PTS"] + actual["REB"] + actual["AST"]
    out = {}
    for st, p in pred.items():
        y = actual[st]
        edges = np.quantile(p, np.linspace(0, 1, CAL_BINS + 1))
        tables = []
        for i in range(CAL_BINS):
            lo, hi = edges[i], edges[i + 1]
            m = (p >= lo) & (p <= hi) if i == 0 else (p > lo) & (p <= hi)
            ratio = y[m] / np.maximum(p[m], 0.1)
            tables.append([round(float(v), 4) for v in np.quantile(ratio, CAL_QUANTILES)])
        out[st] = {"edges": [round(float(e), 4) for e in edges[1:-1]], "ratios": tables, "rows": int(len(p))}
    return out


VEGAS_MIN_COVERAGE = 0.6     # share of training rows with a pregame line before Vegas features are tried


def train(history: pd.DataFrame, odds: pd.DataFrame = None) -> dict:
    """Fit on everything, after scoring fits on everything but the last
    HOLDOUT_DAYS -- with and without Vegas features when there's enough line
    history -- so the run picks whichever predicts better and the page can say
    how far off the model typically is."""
    X = F.build_features_v2(history, odds)
    M = F.build_minutes_training(history)
    if odds is not None and not odds.empty:
        M = M.merge(F.team_odds(odds), on=["TEAM", "GAME DATE"], how="left")
    for c in F.VEGAS_FEATURES:
        if c not in M.columns:
            M[c] = np.nan
    cutoff = X["GAME DATE"].max() - pd.Timedelta(days=HOLDOUT_DAYS)
    tr, te = X[X["GAME DATE"] <= cutoff], X[X["GAME DATE"] > cutoff]

    coverage = float(X["implied_pts"].notna().mean()) if "implied_pts" in X.columns else 0.0
    holdout, holdout_vegas, vegas = {}, None, False
    if len(te) > 200 and len(tr) > 2000:
        holdout = _holdout_mae(tr, te, False)
        if coverage >= VEGAS_MIN_COVERAGE:
            holdout_vegas = _holdout_mae(tr, te, True)
            # points carry the bets that matter most, so they get double weight
            score = lambda h: 2 * h["PTS"] + sum(h.values())  # noqa: E731
            vegas = score(holdout_vegas) < score(holdout)
    # Minutes get the pregame spread and implied points too: starters average
    # ~31 min when the spread is under 8 and ~29.5 above it (blowout risk).
    # Tested Nov 2026: minutes miss 4.81 -> 4.75, starters 4.40 -> 4.25.
    m_vegas = float(M["abs_spread"].notna().mean()) >= VEGAS_MIN_COVERAGE
    mcols = F.MINUTES_FEATURES + (F.VEGAS_FEATURES if m_vegas else [])
    minutes_holdout = None
    mtr, mte = M[M["GAME DATE"] <= cutoff], M[M["GAME DATE"] > cutoff]
    if len(mte) > 200 and len(mtr) > 2000:
        mm = _fit_minutes(mtr, mcols)
        minutes_holdout = round(float(np.abs(mm.predict(mte[mcols].astype(float)) - mte["MIN"]).mean()), 2)

    calibration = calibrate(X, M, vegas, mcols)
    models = {}
    for st in F.TARGETS:
        m, cols = _fit(X, st, vegas)
        models[st] = {"features": cols, "model": m.model_to_string(), "per_minute": True}
    mm = _fit_minutes(M, mcols)
    return {
        "version": 2,
        "trained_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "trained_through": X["GAME DATE"].max().date().isoformat(),
        "rows": int(len(X)),
        "params": PARAMS, "rounds": ROUNDS,
        # MAE with ACTUAL minutes on the last HOLDOUT_DAYS -- the floor the
        # default minutes add to
        "holdout_mae": holdout_vegas if vegas else holdout, "holdout_days": HOLDOUT_DAYS,
        "holdout_mae_no_vegas": holdout, "holdout_mae_vegas": holdout_vegas,
        "uses_vegas": vegas, "vegas_coverage": round(coverage, 3),
        "minutes_holdout_mae": minutes_holdout,
        "calibration": calibration, "calibration_days": CALIBRATION_DAYS,
        "models": models,
        "minutes_model": {"features": mcols, "model": mm.model_to_string()},
    }


def load_models(bundle: dict) -> dict:
    """{stat: (booster, features, per_minute)} for F.predict_stats."""
    import lightgbm as lgb
    return {st: (lgb.Booster(model_str=v["model"]), v["features"], bool(v.get("per_minute")))
            for st, v in bundle["models"].items()}


def build_slate(history: pd.DataFrame, schedule: pd.DataFrame, injuries: pd.DataFrame,
                minutes_booster=None) -> pd.DataFrame:
    today = datetime.now(ET).date().isoformat()
    sched = schedule.copy()
    up = sched[(sched["date"] >= today) & (sched["state"] != "post")]
    if up.empty:
        return pd.DataFrame()
    day = today if (up["date"] == today).any() else up["date"].min()
    games = up[up["date"] == day]

    recent = F.recent_minutes(history)
    h = history.copy()
    h["GAME DATE"] = pd.to_datetime(h["GAME DATE"]).dt.normalize()
    team_dates = h.groupby("TEAM")["GAME DATE"].apply(lambda s: sorted(s.unique()))

    status = {}
    if injuries is not None and not injuries.empty:
        for r in injuries.itertuples():
            status[match_key(r.player)] = (r.status, getattr(r, "detail", None))

    rows = []
    for g in games.itertuples():
        total = getattr(g, "total", None)
        hs = getattr(g, "home_spread", None)
        for team, opp, loc in ((g.home, g.away, "Home"), (g.away, g.home, "Away")):
            dates = team_dates.get(team, [])
            if not len(dates):
                continue
            window = set(dates[-ROTATION_LOOKBACK_GAMES:])
            last3 = set(dates[-3:])
            prev = dates[-1]
            roster = recent[(recent["TEAM"] == team) & (recent["last_game"].isin(window))]
            implied = abs_spread = None
            if total is not None and hs is not None and pd.notna(total) and pd.notna(hs):
                implied = total / 2 - hs / 2 if loc == "Home" else total / 2 + hs / 2
                abs_spread = abs(hs)
            for p in roster.itertuples():
                st, detail = status.get(match_key(p.PLAYER), (None, None))
                # Someone who hasn't played in 3+ games and isn't on the injury
                # report is usually out of the rotation (or in the G League);
                # listing him at his old minutes cost ~2 min of accuracy across
                # the board in backtest. Injury-listed players stay, so Out
                # players' minutes can be shared and returning ones show up.
                if p.last_game not in last3 and st is None:
                    continue
                rows.append({
                    "PLAYER": p.PLAYER, "TEAM": team, "Opponent": opp, "Location": loc,
                    "GAME DATE": pd.Timestamp(day), "espn_game_id": int(g.espn_game_id),
                    "start_utc": g.start_utc, "home": g.home, "away": g.away,
                    "ew_min": round(float(p.ew_min), 2),
                    "played_last": bool(p.last_game == prev),
                    "status": st, "injury": detail, "out": st == "Out",
                    "implied_pts": implied, "abs_spread": abs_spread,
                })
    slate = pd.DataFrame(rows)
    if slate.empty:
        return slate
    slate = F.slate_minutes_inputs(history, slate)
    slate["default_min"] = (F.model_minutes(slate, minutes_booster) if minutes_booster is not None
                            else F.default_minutes(slate))
    return slate


def _at_minutes(proj: dict, minutes, default_min) -> dict:
    """The same projection at different minutes (the stat models are per
    minute, so it scales). None when there's nothing to compare."""
    if minutes is None or not default_min or pd.isna(minutes) or default_min <= 0:
        return None
    f = float(minutes) / float(default_min)
    return {s: float(proj[s]) * f for s in F.TARGETS if s in proj}


def main() -> int:
    t0 = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    history = pd.read_parquet(OUT / "nba_player_stats.parquet")
    schedule = pd.read_parquet(OUT / "nba_schedule.parquet") if (OUT / "nba_schedule.parquet").exists() else pd.DataFrame()
    inj_path = OUT / "nba_injuries.parquet"
    injuries = pd.read_parquet(inj_path) if inj_path.exists() else pd.DataFrame()
    odds_path = OUT / "nba_game_odds.parquet"
    odds = pd.read_parquet(odds_path) if odds_path.exists() else pd.DataFrame()

    import lightgbm as lgb
    bundle = train(history, odds)
    (OUT / "nba_projection_model.json").write_text(json.dumps(bundle))
    print(f"trained on {bundle['rows']:,} games through {bundle['trained_through']}; "
          f"Vegas features {'ON' if bundle['uses_vegas'] else 'off'} (line coverage {bundle['vegas_coverage']:.0%})")
    print(f"  holdout MAE, actual minutes: {bundle['holdout_mae']}")
    if bundle["holdout_mae_vegas"]:
        print(f"  ... without Vegas {bundle['holdout_mae_no_vegas']} / with {bundle['holdout_mae_vegas']}")
    print(f"  minutes model holdout MAE: {bundle['minutes_holdout_mae']}")

    if schedule.empty:
        print("no schedule -- skipping slate")
        return 0
    mbooster = lgb.Booster(model_str=bundle["minutes_model"]["model"])
    slate = build_slate(history, schedule, injuries, mbooster)
    if slate.empty:
        print("no upcoming games -- skipping slate")
        return 0

    feats = F.build_slate_features(history, slate[["PLAYER", "TEAM", "Opponent", "GAME DATE", "Location"]])
    feats = feats.drop(columns=[c for c in ("implied_pts", "abs_spread") if c in feats.columns])
    feats = feats.merge(slate, on=["PLAYER", "TEAM", "Opponent", "GAME DATE", "Location"], how="left")
    st = feats["start5"] if "start5" in feats.columns else np.nan
    feats["start_rate5"] = st                     # same definition the stat model trained on
    model_cols = sorted({c for v in bundle["models"].values() for c in v["features"]}
                        - {"MIN", "mates_usg", "usg_newly_out"})
    keep = (["PLAYER", "TEAM", "Opponent", "GAME DATE", "Location", "espn_game_id", "start_utc", "home", "away",
             "ew_min", "played_last", "status", "injury", "out", "default_min", "USG_SHARE_roll10"]
            + F.MINUTES_FEATURES + F.VEGAS_FEATURES + model_cols)      # the API reruns minutes with these
    keep = list(dict.fromkeys(c for c in keep if c in feats.columns))
    feats = feats[keep]
    feats.to_parquet(OUT / "nba_projection_slate.parquet", index=False)
    print(f"slate: {feats['GAME DATE'].iloc[0].date()} -- {feats['espn_game_id'].nunique()} games, "
          f"{len(feats)} players ({int(feats['out'].sum())} ruled out)")

    proj = F.predict_stats(load_models(bundle), feats, feats["default_min"])
    log = feats[["PLAYER", "TEAM", "Opponent", "GAME DATE", "espn_game_id", "start_utc", "default_min", "status"]].merge(
        proj[["PLAYER", "TEAM"] + F.TARGETS], on=["PLAYER", "TEAM"])
    log = log[log["default_min"] > 0].copy()
    log["logged_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log_path = OUT / "nba_projection_log.parquet"
    if log_path.exists():
        old = pd.read_parquet(log_path)
        # The latest run before tip replaces that day's projections outright,
        # so a player dropped from the slate (ruled out late) doesn't linger.
        old = old[pd.to_datetime(old["GAME DATE"]) != pd.Timestamp(feats["GAME DATE"].iloc[0])]
        log = pd.concat([old, log], ignore_index=True)
        log = log[pd.to_datetime(log["GAME DATE"]) >= pd.Timestamp.now() - pd.Timedelta(days=LOG_RETAIN_DAYS)]
    log.to_parquet(log_path, index=False)
    print(f"logged {len(log):,} projections")

    props_path = OUT / "NBA_Props.parquet"
    if props_path.exists():
        lines = E.main_lines(pd.read_parquet(props_path), set(UNBETTABLE_BOOKS | SHARP_BOOKS | DFS_BOOKS))
        today_rows = log[pd.to_datetime(log["GAME DATE"]) == pd.Timestamp(feats["GAME DATE"].iloc[0])]
        plays = []
        recent_min = feats.drop_duplicates("PLAYER").set_index("PLAYER")["ew"].to_dict()
        for r in today_rows.to_dict("records"):
            alt = _at_minutes(r, recent_min.get(r["PLAYER"]), r["default_min"])
            for m, e in E.edges_for(r["PLAYER"], r, lines, bundle.get("calibration"), alt).items():
                if e["side"] and e["price"] is not None:
                    plays.append({"PLAYER": r["PLAYER"], "TEAM": r["TEAM"], "GAME DATE": r["GAME DATE"],
                                  "start_utc": r["start_utc"], "market": m, "side": e["side"], "line": e["line"],
                                  "price": e["price"], "book": e["book"], "projection": e["projection"],
                                  "diff": e["diff"], "ev": e["ev"],
                                  "prob": e["prob_over"] if e["side"] == "over" else e["prob_under"],
                                  "minutes": r["default_min"], "logged_at": r["logged_at"]})
        plays_path = OUT / "nba_projection_plays.parquet"
        new_plays = pd.DataFrame(plays)
        if plays_path.exists():
            old = pd.read_parquet(plays_path)
            old = old[pd.to_datetime(old["GAME DATE"]) != pd.Timestamp(feats["GAME DATE"].iloc[0])]
            new_plays = pd.concat([old, new_plays], ignore_index=True)
        if not new_plays.empty:
            new_plays.to_parquet(plays_path, index=False)
        print(f"plays flagged today (expected return >= {E.MIN_EV:.0%}): {len(plays)}")
    else:
        print("no NBA_Props.parquet -- skipping plays")
    print(f"done in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
