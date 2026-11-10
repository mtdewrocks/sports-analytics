"""NFL projections: the fitting and feature code behind get_nfl_projections.py.

Two models, blended where that tested better:

  SIMULATION  nfl_sim.py plays every game out 4,000 times, snap by snap.
              Here we fit what it needs from 2021+ play-by-play: league
              tendencies (play call, clock, yards, 4th downs, kicks), each
              team's offense/defense profile, and each player's share of
              targets and carries IN EACH SITUATION (trailing / close /
              leading / red zone). Each game is anchored to its Vegas
              implied points, so the sim supplies game flow -- plays, time
              of possession, pass/run split, who gets the ball when a team
              is chasing -- not a disagreement with the market.
  DIRECT      LightGBM per stat on recent form, role (snap share, target
              share), team and opponent ratings, Vegas implied points and
              teammates who are out.

Every feature for an UPCOMING game is built the same way as for a past one:
the upcoming game is appended as a row with no stats, and all the rolling
inputs are "everything before this row", so there's no separate code path to
drift out of sync with training.
"""
from __future__ import annotations

import re
import unicodedata
from math import erf, sqrt
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

SKILL = ["QB", "RB", "WR", "TE", "FB"]

PBP_COLS = [
    "game_id", "season", "week", "season_type", "posteam", "defteam", "home_team", "away_team", "play_type",
    "down", "ydstogo", "yardline_100", "game_seconds_remaining", "qtr", "score_differential", "pass", "rush",
    "qb_scramble", "sack", "interception", "complete_pass", "incomplete_pass", "yards_gained", "fumble_lost",
    "field_goal_attempt", "field_goal_result", "kick_distance", "punt_attempt", "two_point_attempt", "qb_kneel",
    "qb_spike", "pass_oe", "receiver_player_id", "rusher_player_id", "passer_player_id", "fixed_drive",
    "fixed_drive_result", "play_id", "epa", "success", "wp",
]

DIRECT_STATS = {
    "attempts": "pass_att", "completions": "pass_cmp", "passing_yards": "pass_yds", "passing_tds": "pass_tds",
    "passing_interceptions": "pass_int", "carries": "rush_att", "rushing_yards": "rush_yds",
    "rushing_tds": "rush_tds", "targets": "targets", "receptions": "rec", "receiving_yards": "rec_yds",
    "receiving_tds": "rec_tds",
}

# stat: (positions, row filter, extra opponent feature)
SPEC = {
    "pass_yds": (["QB"], "qb", "opp_pos_pass_yds"), "pass_att": (["QB"], "qb", None),
    "pass_cmp": (["QB"], "qb", None), "pass_tds": (["QB"], "qb", None),
    "rush_att": (["RB", "QB", "FB", "WR"], "any", "opp_pos_rush_yds"),
    "rush_yds": (["RB", "QB", "FB", "WR"], "any", "opp_pos_rush_yds"),
    "rec": (["WR", "TE", "RB", "FB"], "any", "opp_pos_rec"),
    "rec_yds": (["WR", "TE", "RB", "FB"], "any", "opp_pos_rec_yds"),
    "rush_rec_yds": (["RB", "WR", "TE", "FB"], "any", "opp_pos_rec_yds"),
    "any_td": (["RB", "WR", "TE", "QB", "FB"], "any", None),
}
CTX = ["implied_pts", "team_spread", "home", "dome", "wind", "pr_pass_rate", "pr_plays", "pr_epa", "pr_pass_epa",
       "pr_rush_epa", "opp_pr_pass_epa_allowed", "opp_pr_rush_epa_allowed", "opp_pr_epa_allowed",
       "opp_pr_plays_allowed", "tm_out_tgt_share", "tm_out_carries", "n_games", "pos_code"]
LGB = {"learning_rate": 0.04, "num_leaves": 15, "min_data_in_leaf": 50, "feature_fraction": 0.8,
       "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 2.0, "verbose": -1, "seed": 3}
TEAM_STATS = ["epa", "sr", "pass_epa", "rush_epa", "pass_rate", "plays", "drives", "td_rate", "fg_rate", "to_rate"]


def key(name) -> str:
    s = unicodedata.normalize("NFKD", str(name))
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = re.sub(r"[.'’]", "", s)
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return " ".join(s.split())


def implied_points(spread_line, total_line, home: bool):
    """nflverse spread_line is positive when the HOME team is favored."""
    return total_line / 2 + (spread_line / 2 if home else -spread_line / 2)


# ---------------------------------------------------------------------------
# Plays
# ---------------------------------------------------------------------------

def prep_plays(P: pd.DataFrame, G: pd.DataFrame):
    """All plays (for kicks/4th downs) and scrimmage snaps with the
    situation columns the sim is fit on."""
    P = P[P.season_type.isin(["REG", "POST"])].sort_values(["game_id", "play_id"]).reset_index(drop=True)
    P["elapsed"] = (P.game_seconds_remaining - P.groupby("game_id").game_seconds_remaining.shift(-1)).clip(0, 60)
    P = P.merge(G[["game_id", "gameday", "spread_line"]], on="game_id", how="left")
    # the offense's own pregame spread, negative = favored
    P["tsp"] = np.where(P.posteam == P.home_team, -P.spread_line, P.spread_line)
    S = P[P.play_type.isin(["pass", "run"]) & (P.two_point_attempt != 1) & (P.qb_kneel != 1)
          & (P.qb_spike != 1) & P.down.notna()].copy()
    S["dropback"] = (S["pass"] == 1).astype(int)
    S["res"] = np.select([S.sack == 1, S.incomplete_pass == 1, S.interception == 1, S.complete_pass == 1,
                          S.qb_scramble == 1], ["sack", "inc", "int", "cmp", "scramble"], "run")
    S["sd"] = S.score_differential.clip(-21, 21)
    S["tfrac"] = S.game_seconds_remaining / 3600
    S["two_min"] = ((S.qtr.isin([2, 4])) & (S.game_seconds_remaining % 1800 <= 120)).astype(int)
    S["clk"] = np.where(S.res.isin(["inc", "int"]), "stop", "run")
    late = S.game_seconds_remaining <= 300
    S["sit"] = np.select([S.two_min == 1, late & (S.sd > 0), late & (S.sd < 0)], ["two_min", "late_lead", "late_trail"],
                         "normal")
    return P, S


def _call_X(d):
    spn = d.tsp.fillna(0).clip(-14, 14) / 14
    return np.c_[d.down == 1, d.down == 2, d.down == 3, np.log1p(d.ydstogo), d.yardline_100 / 100, d.sd / 21,
                 d.tfrac, (d.sd / 21) * (1 - d.tfrac), d.two_min, d.two_min * (d.sd < 0), (d.yardline_100 <= 10),
                 spn, spn * d.tfrac]


def fit_league(P: pd.DataFrame, S: pd.DataFrame) -> dict:
    from sklearn.linear_model import LogisticRegression
    c = S[S.down <= 3]
    lr = LogisticRegression(max_iter=500).fit(_call_X(c).astype(float), c.dropback)
    clock = {f"{sit}|{clk}": np.quantile(g.elapsed.dropna(), np.linspace(.02, .98, 25)).round(1).tolist()
             for (sit, clk), g in S.groupby(["sit", "clk"]) if g.elapsed.notna().sum() > 20}
    q = np.linspace(0.005, 0.995, 100)
    dist = {r: np.quantile(S[S.res == r].yards_gained, q).round(2).tolist() for r in ["run", "cmp", "sack", "scramble"]}
    F = P[P.down == 4].copy()
    F["choice"] = np.select([F.play_type.isin(["pass", "run"]), F.field_goal_attempt == 1, F.punt_attempt == 1],
                            ["go", "fg", "punt"], "other")
    F = F[F.choice != "other"]
    F["yb"] = pd.cut(F.yardline_100, [0, 5, 10, 20, 30, 37, 45, 55, 65, 100], labels=False)
    F["db"] = pd.cut(F.ydstogo, [0, 1, 3, 6, 99], labels=False)
    F["late_trail"] = ((F.game_seconds_remaining <= 600) & (F.score_differential < 0)).astype(int)
    fourth = F.groupby(["yb", "db", "late_trail"]).choice.value_counts(normalize=True).unstack(fill_value=0)
    K = P[(P.field_goal_attempt == 1) & P.kick_distance.notna()]
    fg = LogisticRegression().fit(K[["kick_distance"]], (K.field_goal_result == "made").astype(int))
    pu = P[P.punt_attempt == 1]
    punt_net = np.quantile((pu.yards_gained.fillna(0) + pu.kick_distance.fillna(0)).clip(0, 70), q).round(1).tolist()
    # where drives start after a score (i.e. after a kickoff), under the
    # current kickoff rule (2025+): first snap of each drive that follows a
    # touchdown or field goal
    recent = S[S.season >= max(2025, int(S.season.min()))].sort_values(["game_id", "play_id"])
    start = recent.groupby(["game_id", "fixed_drive"]).yardline_100.first()
    res = P[P.season >= max(2025, int(P.season.min()))].groupby(["game_id", "fixed_drive"]).fixed_drive_result.last()
    prev = res.groupby(level=0).shift(1)
    ko = start[prev.reindex(start.index).isin(["Touchdown", "Field goal"])].dropna()
    att = S[S.res.isin(["cmp", "inc", "int"])]
    db = S[S.dropback == 1]
    return {
        "play_call": {"coef": lr.coef_[0].round(4).tolist(), "intercept": float(lr.intercept_[0])},
        "clock": clock, "yards": dist,
        "fourth": {f"{int(a)}|{int(b)}|{int(c)}": row.round(3).to_dict() for (a, b, c), row in fourth.iterrows()},
        "fg": {"coef": float(fg.coef_[0][0]), "intercept": float(fg.intercept_[0])},
        "punt_net": punt_net, "kickoff_start_ydl100": float(ko.median()),
        "kickoff_start_dist": np.quantile(ko, np.linspace(.02, .98, 25)).round(0).tolist(),
        "rates": {"sack": float(db.res.eq("sack").mean()), "scramble": float(db.res.eq("scramble").mean()),
                  "int": float(att.res.eq("int").mean()), "cmp": float(att.res.eq("cmp").mean()),
                  "fumble_lost": float(S.fumble_lost.mean()), "xp": 0.95},
    }


# ---------------------------------------------------------------------------
# Team profiles
# ---------------------------------------------------------------------------

def _ew_priors(T: pd.DataFrame, cols: List[str], hl: float = 6, regress: float = 0.35):
    """Exponentially weighted 'everything before this game', pulled 35% back
    to league average at each new season. Rows with no stats (upcoming
    games) get a prior but don't update it."""
    T = T.sort_values(["team", "gameday"]).reset_index(drop=True)
    w = 0.5 ** (1 / hl)
    lg = T[cols].mean()
    out = {c: np.full(len(T), np.nan) for c in cols}
    vals = T[cols].to_numpy(float)
    seasons = T.season.to_numpy()
    lgv = lg.to_numpy(float)
    for _, idx in T.groupby("team").indices.items():
        v = None
        last = None
        for i in idx:
            if v is not None and last is not None and seasons[i] != last:
                v = lgv + (1 - regress) * (v - lgv)
            if v is not None:
                for j, c in enumerate(cols):
                    out[c][i] = v[j]
            x = vals[i]
            if not np.isnan(x).all():
                x = np.where(np.isnan(x), lgv if v is None else v, x)
                v = x if v is None else w * v + (1 - w) * x
            last = seasons[i]
    for c in cols:
        T["pr_" + c] = out[c]
    return T, lg


def _upcoming_team_rows(U: pd.DataFrame) -> pd.DataFrame:
    r = []
    for g in U.itertuples():
        r += [{"game_id": g.game_id, "team": g.home_team, "opp": g.away_team},
              {"game_id": g.game_id, "team": g.away_team, "opp": g.home_team}]
    return pd.DataFrame(r)


def sim_team_priors(S: pd.DataFrame, G: pd.DataFrame, U: pd.DataFrame):
    """Each team's offense and defense as the sim sees them."""
    db = S[S.dropback == 1]
    att = S[S.res.isin(["cmp", "inc", "int"])]
    dr = S[S.res == "run"]
    neutral = S[(S.sit == "normal") & (S.clk == "run") & (S.sd.abs() <= 10)]
    rows = {}
    for side, by in (("off", "posteam"), ("def", "defteam")):
        k = ["game_id", by]
        a = pd.DataFrame({
            "proe": S[S.sd.abs() <= 10].groupby(k).pass_oe.mean(),
            "sack": db.assign(x=db.res.eq("sack")).groupby(k).x.mean(),
            "scramble": db.assign(x=db.res.eq("scramble")).groupby(k).x.mean(),
            "int": att.assign(x=att.res.eq("int")).groupby(k).x.mean(),
            "cmp": att.assign(x=att.res.eq("cmp")).groupby(k).x.mean(),
            "ypcmp": S[S.res == "cmp"].groupby(k).yards_gained.mean(),
            "ypc": dr.groupby(k).yards_gained.mean(),
            "pace": neutral.groupby(k).elapsed.mean(),
        })
        a.index.names = ["game_id", "team"]
        rows[side] = a.add_prefix(side + "_")
    T = rows["off"].join(rows["def"], how="outer").reset_index()
    T = pd.concat([T, _upcoming_team_rows(U)[["game_id", "team"]]], ignore_index=True)
    T = T.merge(G[["game_id", "season", "gameday"]], on="game_id")
    cols = [c for c in T.columns if c.startswith(("off_", "def_"))]
    return _ew_priors(T, cols)


def rating_priors(P: pd.DataFrame, G: pd.DataFrame, U: pd.DataFrame) -> pd.DataFrame:
    """Efficiency ratings (EPA, success rate, drive results) used by the
    direct player models and the ratings + market game model."""
    plays = P[P.play_type.isin(["pass", "run"]) & P.epa.notna() & P.posteam.notna()]
    eff = plays[(plays.wp >= 0.1) & (plays.wp <= 0.9)]
    k = ["game_id", "posteam"]
    g = eff.groupby(k)
    off = pd.DataFrame({"epa": g.epa.mean(), "sr": g.success.mean(),
                        "pass_epa": eff[eff["pass"] == 1].groupby(k).epa.mean(),
                        "rush_epa": eff[eff["rush"] == 1].groupby(k).epa.mean(),
                        "pass_rate": eff[eff.down.isin([1, 2])].groupby(k)["pass"].mean()}).reset_index()
    vol = plays.groupby(k).size().rename("plays").reset_index()
    dr = P.dropna(subset=["fixed_drive", "posteam"]).groupby(k + ["fixed_drive"]).fixed_drive_result.last().reset_index()
    dr["td"] = dr.fixed_drive_result.eq("Touchdown")
    dr["fg"] = dr.fixed_drive_result.eq("Field goal")
    dr["to"] = dr.fixed_drive_result.isin(["Turnover", "Turnover on downs", "Opp touchdown"])
    dd = dr.groupby(k).agg(drives=("td", "size"), td_rate=("td", "mean"), fg_rate=("fg", "mean"),
                           to_rate=("to", "mean")).reset_index()
    T = off.merge(vol, on=k).merge(dd, on=k, how="left").rename(columns={"posteam": "team"})
    meta = G[["game_id", "home_team", "away_team"]]
    T = T.merge(meta, on="game_id")
    T["opp"] = np.where(T.team == T.home_team, T.away_team, T.home_team)
    T = T.drop(columns=["home_team", "away_team"])
    T = pd.concat([T, _upcoming_team_rows(U)], ignore_index=True)
    D = T[["game_id", "team"] + TEAM_STATS].rename(columns={"team": "opp", **{s: f"{s}_allowed" for s in TEAM_STATS}})
    T = T.merge(D, on=["game_id", "opp"], how="left")
    T = T.merge(G[["game_id", "season", "gameday"]], on="game_id")
    cols = TEAM_STATS + [f"{s}_allowed" for s in TEAM_STATS]
    T, _ = _ew_priors(T, cols)
    return T[["game_id", "team"] + [f"pr_{c}" for c in cols]]


# ---------------------------------------------------------------------------
# Game model A: ratings + market
# ---------------------------------------------------------------------------

def game_features(G: pd.DataFrame, TP: pd.DataFrame) -> pd.DataFrame:
    feats = [c for c in TP.columns if c.startswith("pr_")]
    H = TP.rename(columns={f: "h_" + f for f in feats}).rename(columns={"team": "home_team"})
    A = TP.rename(columns={f: "a_" + f for f in feats}).rename(columns={"team": "away_team"})
    X = G.merge(H, on=["game_id", "home_team"]).merge(A, on=["game_id", "away_team"])
    X["rest_diff"] = X.home_rest - X.away_rest
    X["dome"] = X.roof.isin(["dome", "closed"]).astype(int)
    X["wind"] = X.wind.fillna(0)
    X["neutral"] = (X.location == "Neutral").astype(int)
    for s in TEAM_STATS:
        X[f"d_{s}"] = X[f"h_pr_{s}"] + X[f"a_pr_{s}_allowed"]   # home offense + what the away defense allows
        X[f"e_{s}"] = X[f"a_pr_{s}"] + X[f"h_pr_{s}_allowed"]
    return X


MARGIN_F = [f"d_{s}" for s in TEAM_STATS] + [f"e_{s}" for s in TEAM_STATS] + ["rest_diff", "div_game", "neutral", "spread_line"]
TOTAL_F = ([f"{p}_pr_{s}" for p in ("h", "a") for s in TEAM_STATS]
           + [f"{p}_pr_{s}_allowed" for p in ("h", "a") for s in TEAM_STATS] + ["dome", "wind", "total_line"])


def fit_game_model(X: pd.DataFrame):
    from sklearn.linear_model import RidgeCV
    tr = X.dropna(subset=MARGIN_F + TOTAL_F + ["result"])
    tr = tr[tr.season >= tr.season.min() + 1]           # first season's priors are cold
    m = RidgeCV(alphas=np.logspace(-2, 3, 30)).fit(tr[MARGIN_F], tr.result)
    t = RidgeCV(alphas=np.logspace(-2, 3, 30)).fit(tr[TOTAL_F], tr.total)
    sd = float(np.std(tr.result - m.predict(tr[MARGIN_F])))
    return {"margin": m, "total": t, "sd": sd}


def win_prob(margin: float, sd: float) -> float:
    return 0.5 * (1 + erf(margin / (sd * sqrt(2))))


# ---------------------------------------------------------------------------
# Players: direct-model features
# ---------------------------------------------------------------------------

def player_features(PS: pd.DataFrame, SN: pd.DataFrame, G: pd.DataFrame, TP: pd.DataFrame,
                    upcoming: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """One row per player-game. `upcoming` rows (player_id, player_display_name,
    position, team, opponent_team, game_id, season, week) carry no stats; their
    features are built from every earlier game exactly as for history."""
    PS = PS[PS.season_type.isin(["REG", "POST"]) & PS.position.isin(SKILL)].copy()
    PS["k"] = PS.player_display_name.map(key)
    SN = SN[SN.offense_snaps > 0].copy()
    SN["k"] = SN.player.map(key)
    PS = PS.merge(SN[["season", "week", "team", "k", "offense_pct"]].drop_duplicates(["season", "week", "team", "k"]),
                  on=["season", "week", "team", "k"], how="left")
    PS = PS.rename(columns=DIRECT_STATS)
    for c in DIRECT_STATS.values():
        PS[c] = PS[c].fillna(0)
    PS["rush_rec_yds"] = PS.rush_yds + PS.rec_yds
    PS["any_td"] = ((PS.rush_tds + PS.rec_tds) > 0).astype(float)
    PS["_up"] = 0
    if upcoming is not None and len(upcoming):
        up = upcoming.copy()
        up["_up"] = 1
        up["k"] = up.player_display_name.map(key)
        PS = pd.concat([PS, up], ignore_index=True)
    PS = PS.drop(columns=[c for c in ("gameday", "home_team", "away_team", "spread_line", "total_line", "roof", "wind",
                                      "temp") if c in PS.columns])
    PS = PS.merge(G[["game_id", "gameday", "home_team", "away_team", "spread_line", "total_line", "roof", "wind", "temp"]],
                  on="game_id", how="left")
    PS["home"] = (PS.team == PS.home_team).astype(int)
    PS["team_spread"] = np.where(PS.home == 1, -PS.spread_line, PS.spread_line)     # negative = favored
    PS["implied_pts"] = PS.total_line / 2 - PS.team_spread / 2
    PS["dome"] = PS.roof.isin(["dome", "closed"]).astype(int)
    PS["wind"] = PS.wind.fillna(0)
    PS = PS.sort_values(["player_id", "gameday", "_up"]).reset_index(drop=True)
    g = PS.groupby("player_id")
    ewc = list(DIRECT_STATS.values()) + ["rush_rec_yds", "target_share", "air_yards_share", "wopr", "offense_pct"]
    for c in ewc:
        s = PS[c].where(PS._up == 0)
        PS[f"ew_{c}"] = s.groupby(PS.player_id).transform(lambda x: x.shift(1).ewm(halflife=4, ignore_na=True).mean())
        PS[f"last_{c}"] = s.groupby(PS.player_id).shift(1)
    # depth, yards after catch, first downs, and slower-moving volume
    # (each tested a little better; target share is the stickiest receiver stat)
    for c in ("receiving_air_yards", "receiving_yards_after_catch", "receiving_first_downs", "rushing_first_downs"):
        if c not in PS.columns:
            PS[c] = np.nan
    PS["_adot"] = PS.receiving_air_yards / PS.targets.replace(0, np.nan)
    for src, name, hl in (("receiving_air_yards", "ew_air_yds", 4), ("_adot", "ew_adot", 6),
                          ("receiving_yards_after_catch", "ew_yac", 4), ("receiving_first_downs", "ew_rec_fd", 4),
                          ("rushing_first_downs", "ew_rush_fd", 4), ("rush_att", "ew_long_rush_att", 8),
                          ("rush_yds", "ew_long_rush_yds", 8), ("rec_yds", "ew_long_rec_yds", 8),
                          ("targets", "ew_long_targets", 8)):
        s = PS[src].where(PS._up == 0)
        PS[name] = s.groupby(PS.player_id).transform(lambda x: x.shift(1).ewm(halflife=hl, ignore_na=True).mean())
    ts_ = PS.target_share.where(PS._up == 0)
    PS["ew_szn_tgt_share"] = ts_.groupby([PS.player_id, PS.season]).transform(lambda x: x.shift(1).expanding().mean())
    PS = PS.drop(columns=["_adot"])
    PS["n_games"] = g.cumcount()
    PS = PS.merge(TP, on=["game_id", "team"], how="left")
    OP = TP.rename(columns={c: "opp_" + c for c in TP.columns if c.startswith("pr_")}).rename(columns={"team": "opponent_team"})
    PS = PS.merge(OP, on=["game_id", "opponent_team"], how="left")
    for c in ["rec_yds", "rec", "rush_yds", "pass_yds", "targets"]:
        a = (PS.assign(_v=PS[c].where(PS._up == 0)).groupby(["opponent_team", "position", "gameday"])._v
             .sum(min_count=1).reset_index().sort_values(["opponent_team", "position", "gameday"]))
        a[f"opp_pos_{c}"] = a.groupby(["opponent_team", "position"])._v.transform(
            lambda s: s.shift(1).ewm(halflife=6, ignore_na=True).mean())
        PS = PS.merge(a[["opponent_team", "position", "gameday", f"opp_pos_{c}"]],
                      on=["opponent_team", "position", "gameday"], how="left")
    # teammates who played the team's previous game but aren't playing this one
    tg = PS[["team", "gameday"]].drop_duplicates().sort_values(["team", "gameday"])
    tg["prev"] = tg.groupby("team").gameday.shift(1)
    who = PS.groupby(["team", "gameday"]).player_id.apply(set).to_dict()
    ts = PS.set_index(["team", "gameday", "player_id"])[["ew_target_share", "ew_rush_att"]]
    ts = ts[~ts.index.duplicated()].to_dict("index")
    mt, mc = [], []
    for r in tg.itertuples():
        gone = who.get((r.team, r.prev), set()) - who.get((r.team, r.gameday), set()) if pd.notna(r.prev) else set()
        mt.append(sum((ts.get((r.team, r.prev, p)) or {}).get("ew_target_share", 0) or 0 for p in gone))
        mc.append(sum((ts.get((r.team, r.prev, p)) or {}).get("ew_rush_att", 0) or 0 for p in gone))
    tg["tm_out_tgt_share"] = mt
    tg["tm_out_carries"] = mc
    PS = PS.merge(tg[["team", "gameday", "tm_out_tgt_share", "tm_out_carries"]], on=["team", "gameday"], how="left")
    PS["pos_code"] = PS.position.map({"QB": 0, "RB": 1, "FB": 1, "WR": 2, "TE": 3})
    return PS


def _direct_rows(X: pd.DataFrame, st: str) -> pd.DataFrame:
    pos, flt, _ = SPEC[st]
    d = X[X.position.isin(pos)]
    d = d[d.ew_pass_att >= 15] if flt == "qb" else d[d.n_games >= 2]
    return d.dropna(subset=["implied_pts"])


def direct_cols(X: pd.DataFrame, st: str) -> List[str]:
    ew = sorted(c for c in X.columns if c.startswith(("ew_", "last_")))
    opp = SPEC[st][2]
    return CTX + ew + ([opp] if opp else [])


def train_direct(X: pd.DataFrame, first_season: int) -> Dict[str, tuple]:
    import lightgbm as lgb
    models = {}
    H = X[(X._up == 0) & (X.season >= first_season)]
    for st in SPEC:
        d = _direct_rows(H, st)
        if SPEC[st][1] == "qb":
            d = d[d.pass_att >= 5]
        cols = direct_cols(X, st)
        obj = "binary" if st == "any_td" else ("l1" if "yds" in st else "poisson")
        m = lgb.train({**LGB, "objective": obj}, lgb.Dataset(d[cols].astype(float), label=d[st].astype(float)), 600)
        models[st] = (m, cols)
    return models


# ---------------------------------------------------------------------------
# Players: simulation layer (situational shares)
# ---------------------------------------------------------------------------

def player_share_games(S: pd.DataFrame, G: pd.DataFrame, upcoming: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Per player-game targets and carries by situation (s0 trailing by 4+,
    s1 close, s2 leading by 4+, rz red zone), plus efficiency inputs, with
    'everything before this game' EW columns."""
    S = S.assign(state=np.select([S.sd <= -4, S.sd >= 4], [0, 2], 1), rz=(S.yardline_100 <= 20).astype(int))
    tg = S[S.res.isin(["cmp", "inc", "int"]) & S.receiver_player_id.notna()]
    ca = S[(S.res == "run") & S.rusher_player_id.notna()]

    def counts(df, pid, pre):
        a = df.groupby(["game_id", "posteam", pid, "state"]).size().unstack(fill_value=0).reindex(columns=[0, 1, 2], fill_value=0)
        a.columns = [f"{pre}_s{c}" for c in a.columns]
        rz = df[df.rz == 1].groupby(["game_id", "posteam", pid]).size().rename(f"{pre}_rz")
        a = a.join(rz, how="left").fillna(0)
        a.index.names = ["game_id", "team", "pid"]
        return a
    T = counts(tg, "receiver_player_id", "tgt").join(counts(ca, "rusher_player_id", "car"), how="outer").fillna(0)
    rec = tg[tg.res == "cmp"].groupby(["game_id", "posteam", "receiver_player_id"]).yards_gained.agg(["size", "sum"])
    rec.columns = ["rec", "rec_yds"]
    rec.index.names = ["game_id", "team", "pid"]
    ry = ca.groupby(["game_id", "posteam", "rusher_player_id"]).yards_gained.sum().rename("rush_yds")
    ry.index.names = ["game_id", "team", "pid"]
    T = T.join(rec, how="left").join(ry, how="left").fillna(0).reset_index()
    C = [f"{p}_{s}" for p in ("tgt", "car") for s in ("s0", "s1", "s2", "rz")]
    for c in C:
        T[c + "_team"] = T.groupby(["game_id", "team"])[c].transform("sum")
    T["_up"] = 0
    if upcoming is not None and len(upcoming):
        T = pd.concat([T, upcoming[["game_id", "team", "pid"]].assign(_up=1)], ignore_index=True)
    T = T.merge(G[["game_id", "season", "gameday"]], on="game_id").sort_values(["pid", "team", "gameday", "_up"])
    T = T.reset_index(drop=True)
    g = T.groupby(["pid", "team"])
    for c in C + [c + "_team" for c in C] + ["rec", "rec_yds", "rush_yds"]:
        T["ew_" + c] = g[c].transform(lambda s: s.shift(1).ewm(halflife=4, ignore_na=True).mean())
    for p in ("tgt", "car"):
        T[f"ew_{p}_all"] = T[[f"ew_{p}_s0", f"ew_{p}_s1", f"ew_{p}_s2"]].sum(1)
        T[f"ew_{p}_all_team"] = T[[f"ew_{p}_s0_team", f"ew_{p}_s1_team", f"ew_{p}_s2_team"]].sum(1)
    T["n_prior"] = g.cumcount()
    return T


def _shares(rows: pd.DataFrame, pre: str, k: float = 15.0, cap: float = 1.0) -> np.ndarray:
    allsh = (rows[f"ew_{pre}_all"] / rows[f"ew_{pre}_all_team"].replace(0, np.nan)).fillna(0).values
    out = []
    for st in ("s0", "s1", "s2", "rz"):
        num = rows[f"ew_{pre}_{st}"].fillna(0).values
        den = rows[f"ew_{pre}_{st}_team"].fillna(0).values
        sh = np.where(den > 0, num / np.where(den > 0, den, 1), 0)
        w = den / (den + k)          # thin situational sample -> lean on his overall share
        out.append(w * sh + (1 - w) * allsh)
    A = np.array(out)
    tot = A.sum(1, keepdims=True)
    A = np.where(tot > 1, A / tot, A)
    # `cap`: most of what's left over belonged to players who aren't playing;
    # hand it back to those who are, keeping a small slice for fringe players
    tot = A.sum(1, keepdims=True)
    A = np.where((1 - tot) > cap, A * (1 - cap) / np.where(tot > 0, tot, 1), A)
    other = np.clip(1 - A.sum(1, keepdims=True), 0, 1)   # everyone not listed
    return np.hstack([A, other])


def player_arrays(rows: pd.DataFrame, qb_pid: Optional[str]) -> dict:
    rows = rows.fillna({c: 0 for c in rows.columns if c.startswith("ew_")})
    catch = ((rows.ew_rec + 3 * 0.65) / (rows.ew_tgt_all + 3)).fillna(0.65).values / 0.65
    ypr = ((rows.ew_rec_yds + 5 * 11.0) / (rows.ew_rec + 5)).fillna(11).values - 11.0
    # A back's own yards per carry barely carries over week to week (tested:
    # the more it's shrunk toward average, the better) -- so it's shrunk hard.
    # Catch rate and yards per catch DO carry over, so those stay light.
    ypc = ((rows.ew_rush_yds + 150 * 4.2) / (rows.ew_car_all + 150)).fillna(4.2).values - 4.2
    qcol = int(np.where(rows.pid.values == qb_pid)[0][0]) if qb_pid is not None and qb_pid in set(rows.pid) else -1
    # carries capped (tested better: an absent back's carries go to the other
    # backs); targets not (spreading them tested worse)
    return {"tgt": _shares(rows, "tgt"), "car": _shares(rows, "car", cap=0.04), "catch": np.r_[catch, 1.0],
            "ypr": np.r_[ypr, 0.0], "ypc": np.r_[ypc, 0.0], "qb_col": qcol}


# ---------------------------------------------------------------------------
# Final numbers
# ---------------------------------------------------------------------------

SIM_STAT = {"rec": "rec", "rec_yds": "rec_yds", "rush_att": "car", "rush_yds": "rush_yds"}
STACK_POS = {"rec": {"WR", "TE", "RB"}, "rec_yds": {"WR", "TE", "RB"}, "rush_att": {"RB"}, "rush_yds": {"RB"},
             "pass_yds": {"QB"}}


def combine(st: str, position: str, direct: Optional[float], sim_med: Optional[float], cal: dict) -> Optional[float]:
    """Direct model and simulation, stacked with the weights that tested best
    on 2025-26 (both carry information; neither alone was best)."""
    if direct is None or np.isnan(direct):
        return None
    w = (cal.get("stack") or {}).get(st)
    if w and position in STACK_POS.get(st, ()) and sim_med is not None and not np.isnan(sim_med):
        return float(max(0.0, w["intercept"] + w["coef"][0] * direct + w["coef"][1] * sim_med))
    return float(max(0.0, direct))


def td_prob(direct: Optional[float], sim: Optional[float], cal: dict) -> Optional[float]:
    if direct is None and sim is None:
        return None
    w = cal.get("td_sim_weight", 0.6) if sim is not None else 0.0
    p = w * (sim or 0) + (1 - w) * (direct if direct is not None else sim)
    m = np.asarray(cal.get("td_map") or [[0, 0], [1, 1]])
    return float(np.interp(p, m[:, 0], m[:, 1]))


def prob_over(st: str, projection: Optional[float], line: float, cal: dict) -> Optional[float]:
    """Chance the result beats `line`: projection plus how actual results
    have landed around projections of this size (2025-26 out of sample)."""
    c = (cal.get("residuals") or {}).get(st)
    if not c or projection is None:
        return None
    b = int(np.searchsorted(np.asarray(c["edges"]), projection))
    vals = projection + np.asarray(c["resid"][min(b, len(c["resid"]) - 1)])
    cut = line if line % 1 else line + 0.5          # whole-number line: a push isn't a win
    return float(np.clip((vals > cut).mean(), 0.01, 0.99))
