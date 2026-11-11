"""Feature engineering for the NBA stat projection model.

A faithful port of Shawn's nba_usage_and_defense_model.py /
predictions_nba_usage_and_defense_model.py -- same windows, same formulas,
same feature names -- so models trained on the old "NBA Player Stats.xlsx"
and models trained here see identical inputs. The only change is the source:
it reads the columns nba_player_stats.parquet carries (get_nba_data.py kept
the legacy names: PLAYER, TEAM, Opponent, GAME DATE, MIN, PTS ... Location).

Two entry points:

  build_features(history)              every past player-game, for training
  build_slate_features(history, slate) tonight's rows, for prediction

MINUTES ARE THE ONE INPUT THAT ISN'T HISTORY. Every other feature is known
before tip (recent form, opponent defense, pace, rest, usage), so the slate
features are published WITHOUT minutes and the site fills in MIN -- default
or user-edited -- at request time. That's what makes editable minutes cheap:
nothing but the model call reruns.

No imports from app.* so the pipeline (run as a plain script) and the API
can both use it.
"""
from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd

ROLLING_GAMES = 5
OLYMPIC_GAMES = 10
MIN_SHORT = 3        # games needed before the 5-game windows are used
MIN_LONG = 5         # ...and the 10-game ones
OPP_WINDOW = 10
PACE_WINDOW = 10

TARGETS = ["PTS", "AST", "REB", "TOV", "BLK", "STL", "3PM"]
NEEDED = ["PLAYER", "TEAM", "Opponent", "GAME DATE", "MIN", "FGA", "FTA", "OREB", "Location"] + TARGETS

TEAMS = ["ATL", "BKN", "BOS", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW", "HOU", "IND", "LAC", "LAL",
         "MEM", "MIA", "MIL", "MIN", "NOP", "NYK", "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR",
         "UTA", "WAS"]


def feature_columns(with_usage: bool) -> List[str]:
    """The exact feature list (and order) Shawn's models were saved with."""
    base = (["MIN", "is_b2b", "is_3in4", "is_3plus_away", "PACE_rel"]
            + [f"{s}_roll{ROLLING_GAMES}" for s in TARGETS]
            + [f"{s}_oly{OLYMPIC_GAMES}" for s in TARGETS]
            + [f"{s}_roll{ROLLING_GAMES}_oppAdj" for s in TARGETS]
            + [f"{s}_oly{OLYMPIC_GAMES}_oppAdj" for s in TARGETS]
            + [f"Opp_{s}_rel" for s in TARGETS]
            + ["Location_Home"]
            + [f"Opponent_{t}" for t in TEAMS[1:]])          # drop_first dropped ATL
    return base + (["USG_SHARE_roll5", "USG_SHARE_roll10"] if with_usage else [])


def _olympic_mean(a: np.ndarray) -> float:
    if len(a) < 3:
        return float(np.mean(a))
    s = np.sort(a)
    return float(s[1:-1].mean())


def _games_last_4(dates: pd.Series) -> list:
    d = dates.values
    out = []
    for i in range(len(d)):
        window = d[max(0, i - 3):i + 1]
        out.append(int(((d[i] - window) <= np.timedelta64(3, "D")).sum()))
    return out


def _away_streak(s: pd.Series) -> list:
    streak, out = 0, []
    for v in s:
        streak = streak + 1 if v == 1 else 0
        out.append(streak)
    return out


def _engineer(df: pd.DataFrame) -> pd.DataFrame:
    """Shawn's sections 3-8, unchanged in substance. Rows with NaN targets
    (tonight's slate) get every feature computed from PRIOR games only --
    each rolling window sits behind a shift(1)."""
    df = df.sort_values(["PLAYER", "GAME DATE"]).reset_index(drop=True)
    g = df.groupby("PLAYER")

    for stat in TARGETS:
        sh = g[stat].shift(1)
        # min_periods: a player with fewer than 10 games on file (a rookie, or a
        # veteran back from a season-long injury) used to get NaN here, and the
        # models -- which never trained on NaN -- read that as "fringe player"
        # (Damian Lillard, 9 games back from his Achilles: 9.8 points projected
        # off a 20-point average). Half a window is enough to use.
        # grouped, so a window never reaches back into the previous player's
        # rows (with full windows the NaN from shift(1) used to block that)
        gs = sh.groupby(df["PLAYER"])
        df[f"{stat}_roll{ROLLING_GAMES}"] = gs.transform(lambda x: x.rolling(ROLLING_GAMES, min_periods=MIN_SHORT).mean())
        df[f"{stat}_oly{OLYMPIC_GAMES}"] = gs.transform(
            lambda x: x.rolling(OLYMPIC_GAMES, min_periods=MIN_LONG).apply(_olympic_mean, raw=True))

    prev = g["GAME DATE"].shift(1)
    df["is_b2b"] = ((df["GAME DATE"] - prev).dt.days == 1).astype(int)
    df["games_4d"] = g["GAME DATE"].transform(_games_last_4)
    df["is_3in4"] = (df["games_4d"] >= 3).astype(int)
    away = (df["Location"] == "Away").astype(int)
    df["is_3plus_away"] = (away.groupby(df["PLAYER"]).transform(_away_streak) >= 3).astype(int)
    df = df.drop(columns=["games_4d"])

    df["USG_PROXY"] = df["FGA"] + 0.44 * df["FTA"] + df["TOV"]
    df["TEAM_USG"] = df.groupby(["TEAM", "GAME DATE"])["USG_PROXY"].transform("sum")
    df["USG_SHARE"] = df["USG_PROXY"] / df["TEAM_USG"]
    us = df.groupby("PLAYER")["USG_SHARE"].shift(1)
    ug = us.groupby(df["PLAYER"])
    df["USG_SHARE_roll5"] = ug.transform(lambda x: x.rolling(5, min_periods=MIN_SHORT).mean())
    df["USG_SHARE_roll10"] = ug.transform(lambda x: x.rolling(10, min_periods=MIN_LONG).mean())

    # min_count=1: a slate date (all NaN) sums to NaN rather than 0, so it
    # can never leak into anyone's rolling average
    team_allowed = (df.groupby(["Opponent", "GAME DATE"])[TARGETS].sum(min_count=1).reset_index())
    league_allowed = team_allowed.groupby("GAME DATE")[TARGETS].mean().reset_index()
    for stat in TARGETS:
        team_allowed[f"{stat}_opp_roll"] = team_allowed.groupby("Opponent")[stat].shift(1).rolling(OPP_WINDOW).mean()
        league_allowed[f"{stat}_lg_roll"] = league_allowed[stat].shift(1).rolling(OPP_WINDOW).mean()
    opp = team_allowed.merge(league_allowed[["GAME DATE"] + [f"{s}_lg_roll" for s in TARGETS]], on="GAME DATE", how="left")
    for stat in TARGETS:
        opp[f"Opp_{stat}_rel"] = opp[f"{stat}_opp_roll"] / opp[f"{stat}_lg_roll"]
    df = df.merge(opp[["Opponent", "GAME DATE"] + [f"Opp_{s}_rel" for s in TARGETS]],
                  on=["Opponent", "GAME DATE"], how="left")

    for stat in TARGETS:
        r, o, rel = f"{stat}_roll{ROLLING_GAMES}", f"{stat}_oly{OLYMPIC_GAMES}", f"Opp_{stat}_rel"
        df[f"{r}_oppAdj"] = df[r] * df[rel]
        df[f"{o}_oppAdj"] = df[o] * df[rel]

    df["POSS"] = df["FGA"] + 0.44 * df["FTA"] - df["OREB"] + df["TOV"]
    team_pace = df.groupby(["TEAM", "GAME DATE"])["POSS"].mean().reset_index()
    league_pace = team_pace.groupby("GAME DATE")["POSS"].mean().reset_index(name="LEAGUE_PACE")
    team_pace["PACE_roll"] = team_pace.groupby("TEAM")["POSS"].shift(1).rolling(PACE_WINDOW).mean()
    league_pace["PACE_lg_roll"] = league_pace["LEAGUE_PACE"].shift(1).rolling(PACE_WINDOW).mean()
    pace = team_pace.merge(league_pace, on="GAME DATE", how="left")
    pace["PACE_rel"] = pace["PACE_roll"] / pace["PACE_lg_roll"]
    df = df.merge(pace[["TEAM", "GAME DATE", "PACE_rel"]], on=["TEAM", "GAME DATE"], how="left")

    df["Location_Home"] = (df["Location"] == "Home").astype(int)
    for t in TEAMS[1:]:
        df[f"Opponent_{t}"] = (df["Opponent"] == t).astype(int)
    return df


def _clean(history: pd.DataFrame) -> pd.DataFrame:
    df = history.copy()
    missing = [c for c in NEEDED if c not in df.columns]
    if missing:
        raise KeyError(f"history is missing columns: {missing}")
    df["GAME DATE"] = pd.to_datetime(df["GAME DATE"]).dt.normalize()
    if "Played" in df.columns:
        df = df[pd.to_numeric(df["Played"], errors="coerce") == 1]
    return df


def build_features(history: pd.DataFrame) -> pd.DataFrame:
    """Every past player-game with features, dropping rows whose windows
    aren't full yet (Shawn's dropna)."""
    df = _engineer(_clean(history))
    need = feature_columns(True)
    return df.dropna(subset=need + TARGETS).reset_index(drop=True)


def build_slate_features(history: pd.DataFrame, slate: pd.DataFrame) -> pd.DataFrame:
    """Features for tonight. `slate` has PLAYER, TEAM, Opponent, GAME DATE,
    Location (one row per player expected to dress). MIN is filled with NaN
    here; the caller supplies minutes at prediction time."""
    hist = _clean(history)
    s = slate.copy()
    s["GAME DATE"] = pd.to_datetime(s["GAME DATE"]).dt.normalize()
    for c in NEEDED:
        if c not in s.columns:
            s[c] = np.nan
    s["MIN"] = np.nan
    s["_slate"] = True
    hist["_slate"] = False
    df = _engineer(pd.concat([hist, s[hist.columns.intersection(s.columns).tolist()]], ignore_index=True, sort=False))
    out = df[df["_slate"] == True].drop(columns=["_slate"])  # noqa: E712
    return out.reset_index(drop=True)


def usage_adjust(pred: pd.DataFrame, target: float = 0.85) -> pd.DataFrame:
    """Shawn's step 11: if the listed players' recent usage shares sum to
    less than `target`, scale everyone's points and assists up to fill it.
    Only meaningful when each team's whole rotation is listed -- which the
    automated slate guarantees (and is why a hand-built three-player file
    used to triple everyone's points)."""
    out = []
    for _, grp in pred.groupby("TEAM"):
        grp = grp.copy()
        total = grp["USG_SHARE_roll5"].sum()
        factor = (target / total) if total and total < target else 1.0
        grp["USG_SHARE_adj"] = grp["USG_SHARE_roll5"] * factor
        grp["PTS_adj"] = grp["PTS_raw"] * factor
        grp["AST_adj"] = grp["AST_raw"] * factor
        out.append(grp)
    return pd.concat(out, ignore_index=True) if out else pred


# ---------------------------------------------------------------------------
# Default minutes
# ---------------------------------------------------------------------------
# Chosen by backtest on every 2025-26 and 2026-27 game (mins_bt*.py, Nov 2026):
#
#   plain last-5 average                         5.07 min average miss
#   recency-weighted (half-life 4 games)         4.98
#   + share out ALL absent rotation minutes      worse (5.1-6.2): someone out
#                                                for weeks is already baked into
#                                                his teammates' recent minutes
#   + share out only NEWLY absent players'       4.90  <- this
#     minutes (played last game, out tonight),
#     and take back from a RETURNING player
#
# 30% of a newly-out player's usual minutes go to his available teammates in
# proportion to their own minutes; a returning regular takes 30% of his back.
# Back-to-backs move starters' minutes by ~0.35, too small to bother with.
EW_HALFLIFE = 4
SHARE_OUT = 0.3
SHARE_RETURN = 0.3
ROTATION_MIN = 10       # players this size and up absorb or give back minutes
NEWLY_OUT_MIN = 12
RETURNING_MIN = 15
MAX_MIN = 42.0
TEAM_MINUTES = 240.0
BENCH_MIN = 15.0


def default_minutes(slate: pd.DataFrame) -> pd.Series:
    """Projected minutes per row. Needs columns TEAM, ew_min (recency-weighted
    minutes), played_last (played his team's previous game), out (ruled out
    tonight). Rows are tonight's candidates for each team, out players included
    so their minutes can be shared out."""
    s = slate.copy()
    s["ew_min"] = pd.to_numeric(s["ew_min"], errors="coerce").fillna(0.0).astype(float)
    s["out"] = s["out"].fillna(False).astype(bool)
    s["played_last"] = s["played_last"].fillna(False).astype(bool)
    proj = s["ew_min"].copy()
    for _, g in s.groupby("TEAM"):
        idx = g.index
        missing = g.loc[g["out"] & g["played_last"] & (g["ew_min"] >= NEWLY_OUT_MIN), "ew_min"].sum()
        back = g.loc[~g["out"] & ~g["played_last"] & (g["ew_min"] >= RETURNING_MIN), "ew_min"].sum()
        rot = g[~g["out"] & (g["ew_min"] >= ROTATION_MIN)]
        if len(rot) and rot["ew_min"].sum() > 0 and (missing or back):
            shift = (SHARE_OUT * missing - SHARE_RETURN * back) * rot["ew_min"] / rot["ew_min"].sum()
            proj.loc[rot.index] = (rot["ew_min"] + shift).clip(0, MAX_MIN)
        proj.loc[idx[g["out"].values]] = 0.0
        # A game has 240 minutes. Deep-bench players who show up in recent
        # box scores often don't play, so if the team adds up to more, trim
        # the bench (under BENCH_MIN) to fit -- starters are left alone.
        # Backtest: 6.52 -> 6.27 average miss across everyone listed.
        tp = proj.loc[idx]
        bench = tp < BENCH_MIN
        over = tp.sum() - TEAM_MINUTES
        if over > 0 and tp[bench].sum() > 0:
            proj.loc[tp[bench].index] = tp[bench] * max(0.0, 1 - over / tp[bench].sum())
    return proj.round(1)


def recent_minutes(history: pd.DataFrame) -> pd.DataFrame:
    """Per player: latest team, recency-weighted minutes and last game date --
    the inputs default_minutes() needs, from box scores."""
    h = _clean(history)
    h = h.sort_values(["PLAYER", "GAME DATE"])
    h["ew_min"] = h.groupby("PLAYER")["MIN"].transform(lambda x: x.ewm(halflife=EW_HALFLIFE).mean())
    last = h.groupby("PLAYER").tail(1)[["PLAYER", "TEAM", "GAME DATE", "ew_min"]]
    return last.rename(columns={"GAME DATE": "last_game"}).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Minutes model (replaces the hand-tuned rule as the default when available)
# ---------------------------------------------------------------------------
# Tested on 2026-27 games (trained on 2025-26):  recency-weighted minutes 5.39,
# the rule above 5.29, this model 4.83 average miss -- the gain is all bench
# and mid-rotation (10-30 min: ~0.6 better); starters are unchanged at 4.2.
# "share" (his minutes as a slice of the rotation that's available tonight)
# carries most of it. Rotation = 10+ minute players, which is what the injury
# report tells you before tip; deep-bench DNPs aren't knowable, so they're
# deliberately left out of every team-level input.
MINUTES_FEATURES = ["ew", "last", "l3", "l10sd", "start5", "last_start", "rest", "is_home",
                    "played_last", "team_missing", "team_returning", "share", "ngames",
                    # blowouts (final margin 20+, either way) pull starters early,
                    # so minutes in competitive games are tracked separately
                    "ew_close", "l3_close", "blow5", "last_blow"]
BLOWOUT_MARGIN = 20
MINUTES_PARAMS = {"objective": "l1", "learning_rate": 0.05, "num_leaves": 15, "min_data_in_leaf": 60,
                  "feature_fraction": 0.9, "bagging_fraction": 0.8, "bagging_freq": 1, "verbose": -1, "seed": 1}
MINUTES_ROUNDS = 500


def team_minutes_context(df: pd.DataFrame) -> pd.DataFrame:
    """Team-level minutes inputs from player rows of ONE game per team.
    Needs TEAM, ew, played_last, out. Out players contribute what they take
    away (team_missing) and nothing to the available rotation."""
    d = df.copy()
    d["out"] = d["out"].fillna(False).astype(bool)
    d["played_last"] = d["played_last"].fillna(False).astype(bool)
    newly = d["out"] & d["played_last"] & (d["ew"] >= NEWLY_OUT_MIN)
    back = ~d["out"] & ~d["played_last"] & (d["ew"] >= RETURNING_MIN)
    avail = ~d["out"] & (d["ew"] >= ROTATION_MIN)
    d["team_missing"] = d["ew"].where(newly, 0).groupby(d["TEAM"]).transform("sum")
    d["team_returning"] = d["ew"].where(back, 0).groupby(d["TEAM"]).transform("sum")
    tot = d["ew"].where(avail, 0).groupby(d["TEAM"]).transform("sum")
    d["share"] = (d["ew"] / tot.replace(0, np.nan)).where(d["ew"] >= ROTATION_MIN)
    return d


def _with_margins(h: pd.DataFrame) -> pd.DataFrame:
    """Final margin of each player's game (team points minus opponent's, from
    the box scores) and whether it was a blowout."""
    tp = h.groupby(["TEAM", "GAME DATE"])["PTS"].sum().rename("_tp").reset_index()
    op = tp.rename(columns={"TEAM": "Opponent", "_tp": "_op"})
    h = h.merge(tp, on=["TEAM", "GAME DATE"], how="left").merge(op, on=["Opponent", "GAME DATE"], how="left")
    h["margin"] = h["_tp"] - h["_op"]
    h["blow"] = (h["margin"].abs() >= BLOWOUT_MARGIN).astype(float).where(h["margin"].notna())
    return h.drop(columns=["_tp", "_op"])


def _close_minutes(m: np.ndarray, blow: np.ndarray) -> tuple:
    """(EW minutes, mean of the last 3) over games that weren't blowouts;
    NaN when there are none."""
    keep = m[blow != 1]
    if len(keep) == 0:
        return np.nan, np.nan
    return float(pd.Series(keep).ewm(halflife=EW_HALFLIFE).mean().iloc[-1]), float(keep[-3:].mean())


def build_minutes_training(history: pd.DataFrame) -> pd.DataFrame:
    """One row per player-game with the inputs as they stood BEFORE tip."""
    h = _with_margins(_clean(history)).sort_values(["PLAYER", "GAME DATE"]).reset_index(drop=True)
    g = h.groupby("PLAYER")
    h["ew"] = g["MIN"].transform(lambda s: s.shift(1).ewm(halflife=EW_HALFLIFE).mean())
    close = h["MIN"].where(h["blow"] != 1)
    gc = close.groupby(h["PLAYER"])
    h["ew_close"] = gc.transform(lambda s: s.shift(1).ewm(halflife=EW_HALFLIFE, ignore_na=True).mean())
    h["l3_close"] = gc.transform(lambda s: s.shift(1).rolling(10, min_periods=1).apply(
        lambda a: np.nanmean(a[~np.isnan(a)][-3:]) if (~np.isnan(a)).any() else np.nan, raw=True))
    h["blow5"] = g["blow"].transform(lambda s: s.shift(1).rolling(5, min_periods=1).mean())
    h["last_blow"] = g["blow"].shift(1)
    h["ew_after"] = g["MIN"].transform(lambda s: s.ewm(halflife=EW_HALFLIFE).mean())
    h["last"] = g["MIN"].shift(1)
    h["l3"] = g["MIN"].transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
    h["l10sd"] = g["MIN"].transform(lambda s: s.shift(1).rolling(10, min_periods=3).std())
    st = h["STARTER"] if "STARTER" in h.columns else pd.Series(np.nan, index=h.index)
    h["_st"] = pd.to_numeric(st, errors="coerce")
    h["start5"] = h.groupby("PLAYER")["_st"].transform(lambda s: s.shift(1).rolling(5, min_periods=1).mean())
    h["last_start"] = h.groupby("PLAYER")["_st"].shift(1)
    h["rest"] = (h["GAME DATE"] - g["GAME DATE"].shift(1)).dt.days.clip(upper=10)
    h["is_home"] = (h["Location"] == "Home").astype(int)
    h["ngames"] = g.cumcount()

    dates = h.groupby("TEAM")["GAME DATE"].apply(lambda s: sorted(s.unique()))
    prev_of = {(t, ds[i]): ds[i - 1] for t, ds in dates.items() for i in range(1, len(ds))}
    h["_prev_team_game"] = [prev_of.get((t, d)) for t, d in zip(h["TEAM"], h["GAME DATE"])]
    h["played_last"] = (g["GAME DATE"].shift(1) == h["_prev_team_game"])

    # newly out = played the team's previous game, not this one (would be on
    # the injury report); their ew as of that previous game
    plays = h.groupby(["TEAM", "GAME DATE"])["PLAYER"].apply(set).to_dict()
    ew_after = h.set_index(["TEAM", "GAME DATE", "PLAYER"])["ew_after"].to_dict()
    missing = {}
    for (t, d), ps in plays.items():
        p = prev_of.get((t, d))
        gone = plays.get((t, p), set()) - ps if p is not None else set()
        missing[(t, d)] = float(sum(v for v in (ew_after.get((t, p, x), 0) for x in gone) if v >= NEWLY_OUT_MIN))
    h["team_missing"] = [missing.get((t, d), 0.0) for t, d in zip(h["TEAM"], h["GAME DATE"])]
    back = (~h["played_last"]) & (h["ew"] >= RETURNING_MIN)
    h["team_returning"] = h["ew"].where(back, 0).groupby([h["TEAM"], h["GAME DATE"]]).transform("sum")
    tot = h["ew"].where(h["ew"] >= ROTATION_MIN, 0).groupby([h["TEAM"], h["GAME DATE"]]).transform("sum")
    h["share"] = (h["ew"] / tot.replace(0, np.nan)).where(h["ew"] >= ROTATION_MIN)
    h["played_last"] = h["played_last"].astype(int)
    return h.dropna(subset=["ew"]).reset_index(drop=True)


def slate_minutes_inputs(history: pd.DataFrame, slate: pd.DataFrame) -> pd.DataFrame:
    """Player-level minutes inputs for tonight (team-level ones are added by
    team_minutes_context, because they depend on who's out)."""
    h = _with_margins(_clean(history)).sort_values(["PLAYER", "GAME DATE"])
    st = pd.to_numeric(h["STARTER"], errors="coerce") if "STARTER" in h.columns else pd.Series(np.nan, index=h.index)
    h = h.assign(_st=st)
    rows = []
    for p, g in h.groupby("PLAYER"):
        m = g["MIN"].astype(float)
        bl = g["blow"].values
        ewc, l3c = _close_minutes(m.values, bl)
        rows.append({"PLAYER": p, "ew_close": ewc, "l3_close": l3c,
                     "blow5": float(np.nanmean(bl[-5:])) if np.isfinite(bl[-5:]).any() else np.nan,
                     "last_blow": float(bl[-1]),
                     "ew": float(m.ewm(halflife=EW_HALFLIFE).mean().iloc[-1]),
                     "last": float(m.iloc[-1]), "l3": float(m.tail(3).mean()),
                     "l10sd": float(m.tail(10).std()) if len(m) >= 3 else np.nan,
                     "start5": float(g["_st"].tail(5).mean()), "last_start": float(g["_st"].iloc[-1]),
                     "last_game": g["GAME DATE"].iloc[-1], "ngames": int(len(g))})
    inp = pd.DataFrame(rows)
    s = slate.merge(inp, on="PLAYER", how="left")
    s["rest"] = (pd.to_datetime(s["GAME DATE"]) - pd.to_datetime(s["last_game"])).dt.days.clip(upper=10)
    s["is_home"] = (s["Location"] == "Home").astype(int)
    return s.drop(columns=["last_game"])


def model_minutes(slate: pd.DataFrame, booster) -> pd.Series:
    """Default minutes from the minutes model: Out -> 0, the 240-minute bench
    trim from default_minutes() applied on top."""
    d = team_minutes_context(slate)
    # the booster's own feature list, so a model trained before a feature was
    # added still runs on a newer slate (and vice versa, with NaN)
    cols = booster.feature_name() if hasattr(booster, "feature_name") else MINUTES_FEATURES
    X = d.reindex(columns=cols).astype(float).copy()
    if "played_last" in X.columns:
        X["played_last"] = d["played_last"].astype(int)
    pred = pd.Series(np.clip(booster.predict(X), 0, MAX_MIN), index=d.index)
    pred[d["out"].values] = 0.0
    for _, g in d.groupby("TEAM"):
        tp = pred.loc[g.index]
        bench = tp < BENCH_MIN
        over = tp.sum() - TEAM_MINUTES
        if over > 0 and tp[bench].sum() > 0:
            pred.loc[tp[bench].index] = tp[bench] * max(0.0, 1 - over / tp[bench].sum())
    return pred.round(1)


# ---------------------------------------------------------------------------
# Model v2 (Nov 2026) -- what changed from Shawn's feature set, and why.
# Every change below was tested on 2026-27 games (model fit on 2025-26):
#
#   per-minute targets      predict stat/minute, multiply by minutes. Same
#                           accuracy (PTS 3.79 vs 3.79) but edits behave: 34 ->
#                           40 min adds 3.4 pts for a 20-pt scorer (his real
#                           rate says 4.1) instead of 3.0, rebounds 1.2 not 0.9
#   + recent starter rate   PTS 3.82 -> 3.80
#   + teammates' usage      PTS -> 3.79: how much usage the OTHER players
#                           tonight normally carry, and how much just left (a
#                           newly-out teammate). Learned, so it replaces the
#                           fixed "scale up to 85% usage" step
#   - 29 opponent dummies   no loss (3.82 -> 3.82); opponent defense features
#                           already carry it
#   x3 weight this season   PTS 3.67 -> 3.65 on November games
#   position defense        tested (opponent allowed by G/F/C), no gain, left out
#   Vegas implied points    used only when ESPN's pregame lines cover enough
#                           history AND they beat the no-Vegas fit on holdout
#                           (get_nba_projections.train decides each run)
# ---------------------------------------------------------------------------
CONTEXT_FEATURES = ["start_rate5", "mates_usg", "usg_newly_out"]
VEGAS_FEATURES = ["implied_pts", "abs_spread"]
SEASON_WEIGHT = 3.0


def feature_columns_v2(stat: str, vegas: bool = False) -> List[str]:
    base = [c for c in feature_columns(stat in ("PTS", "AST")) if not c.startswith("Opponent_")]
    return base + CONTEXT_FEATURES + (VEGAS_FEATURES if vegas else [])


def team_odds(odds: pd.DataFrame) -> pd.DataFrame:
    """One row per team-game: implied points (total/2 minus half its own
    spread) and the size of the spread (blowout risk)."""
    if odds is None or odds.empty:
        return pd.DataFrame(columns=["TEAM", "GAME DATE"] + VEGAS_FEATURES)
    o = odds.dropna(subset=["total", "home_spread"]).copy()
    o["GAME DATE"] = pd.to_datetime(o["date"]).dt.normalize()
    home = pd.DataFrame({"TEAM": o["home"], "GAME DATE": o["GAME DATE"],
                         "implied_pts": o["total"] / 2 - o["home_spread"] / 2, "abs_spread": o["home_spread"].abs()})
    away = pd.DataFrame({"TEAM": o["away"], "GAME DATE": o["GAME DATE"],
                         "implied_pts": o["total"] / 2 + o["home_spread"] / 2, "abs_spread": o["home_spread"].abs()})
    return pd.concat([home, away], ignore_index=True).drop_duplicates(["TEAM", "GAME DATE"], keep="last")


def add_context(df: pd.DataFrame, odds: pd.DataFrame = None) -> pd.DataFrame:
    """Training-time context: starter rate from prior games; teammates' usage
    from who actually played (the same thing the injury report tells you
    before tip); Vegas lines when given."""
    d = df.sort_values(["PLAYER", "GAME DATE"]).copy()
    st = pd.to_numeric(d["STARTER"], errors="coerce") if "STARTER" in d.columns else pd.Series(np.nan, index=d.index)
    d["start_rate5"] = st.groupby(d["PLAYER"]).transform(lambda s: s.shift(1).rolling(5, min_periods=1).mean())
    u = d["USG_SHARE_roll10"].fillna(0)
    d["mates_usg"] = u.groupby([d["TEAM"], d["GAME DATE"]]).transform("sum") - u
    games = d[["TEAM", "GAME DATE"]].drop_duplicates().sort_values(["TEAM", "GAME DATE"])
    games["_prev"] = games.groupby("TEAM")["GAME DATE"].shift(1)
    plays = d.groupby(["TEAM", "GAME DATE"])["PLAYER"].apply(set).to_dict()
    usg = d.set_index(["TEAM", "GAME DATE", "PLAYER"])["USG_SHARE_roll10"].to_dict()
    out = []
    for t, g, p in zip(games["TEAM"], games["GAME DATE"], games["_prev"]):
        gone = plays.get((t, p), set()) - plays.get((t, g), set()) if pd.notna(p) else set()
        out.append(float(np.nansum([usg.get((t, p, x), 0) for x in gone])))
    games["usg_newly_out"] = out
    d = d.merge(games[["TEAM", "GAME DATE", "usg_newly_out"]], on=["TEAM", "GAME DATE"], how="left")
    if odds is not None and not odds.empty:
        d = d.merge(team_odds(odds), on=["TEAM", "GAME DATE"], how="left")
    else:
        for c in VEGAS_FEATURES:
            d[c] = np.nan
    return d


def build_features_v2(history: pd.DataFrame, odds: pd.DataFrame = None) -> pd.DataFrame:
    df = add_context(_engineer(_clean(history)), odds)
    need = [c for c in feature_columns_v2("PTS") if c not in CONTEXT_FEATURES]
    return df.dropna(subset=need + TARGETS).reset_index(drop=True)


def slate_context(slate: pd.DataFrame, minutes: pd.Series) -> pd.DataFrame:
    """Prediction-time teammates' usage, from tonight's minutes: anyone at 0
    isn't playing. Recomputed on every minutes edit."""
    s = slate.copy()
    playing = pd.Series(minutes.values > 0, index=s.index)
    u = s["USG_SHARE_roll10"].fillna(0)
    s["mates_usg"] = u.where(playing, 0).groupby(s["TEAM"]).transform("sum") - u.where(playing, 0)
    gone = (~playing) & s["played_last"].fillna(False).astype(bool)
    s["usg_newly_out"] = u.where(gone, 0).groupby(s["TEAM"]).transform("sum")
    return s


def predict_stats(models: dict, slate: pd.DataFrame, minutes: pd.Series) -> pd.DataFrame:
    """Shared by the pipeline and the API. models: {stat: (booster, features,
    per_minute)}. Players at 0 minutes get 0 of everything."""
    s = slate_context(slate, minutes)
    s["MIN"] = minutes.values
    out = s[["PLAYER", "TEAM"]].copy()
    for stat, (booster, cols, per_min) in models.items():
        X = s.reindex(columns=cols).astype(float)
        p = booster.predict(X)
        out[stat] = np.clip(p * s["MIN"].values if per_min else p, 0, None)
    out.loc[s["MIN"].values <= 0, list(models)] = 0.0
    return _redistribute_usage(out, s)


# How much of a newly-absent player's usage goes to each teammate, on top of
# what the stat models already add for "less usage on the floor". Tested on
# 381 teammate-games (Feb-Apr 2026) where a 24%+ usage player sat: the models
# alone came in 0.45 points and 0.23 assists low per teammate; handing the
# freed usage out in proportion to each teammate's own share removed the
# points bias and trimmed the error (4.35 -> 4.34). Rebounds, threes and the
# rest didn't move, so they're left alone. E.g. Luka out: Reaves +21%, about
# what he's done in 18 real games without him (+20% points per 36).
USAGE_REDISTRIBUTE = {"PTS": 1.0, "AST": 1.0}
USAGE_BUMP_CAP = 0.35


def _redistribute_usage(out: pd.DataFrame, s: pd.DataFrame) -> pd.DataFrame:
    if "usg_newly_out" not in s.columns:
        return out
    gone = s["usg_newly_out"].fillna(0).clip(0, 0.8).values
    own = s["USG_SHARE_roll10"].fillna(s.get("USG_SHARE_roll5")).fillna(0).clip(0, 0.6).values
    base = np.clip(gone * own / np.maximum(1 - gone, 0.2), 0, USAGE_BUMP_CAP)
    playing = s["MIN"].values > 0
    for stat, a in USAGE_REDISTRIBUTE.items():
        if stat in out.columns:
            out[stat] = out[stat].values * np.where(playing, 1 + a * base, 1)
    return out
