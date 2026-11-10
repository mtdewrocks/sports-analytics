"""NFL Projections: simulation behaviour, situational shares, edges, grading."""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))
import nfl_sim as NS  # noqa: E402
import nfl_projection_edges as E  # noqa: E402
import nfl_projection_model as M  # noqa: E402

CAL = json.loads((APP / "nfl_projection_calibration.json").read_text())


def _league():
    q = np.linspace(0.005, 0.995, 100)
    spec = {
        "play_call": {"coef": [-1.85, -0.8, 0.64, 1.47, 0.3, 1.16, 0.17, -2.95, 0.68, 0.5, 0.25], "intercept": -2.03},
        "clock": {f"{s}|{c}": list(np.linspace(*((30, 45) if c == "run" and s == "normal" else (2, 8)), 25))
                  for s in ("normal", "two_min", "late_lead", "late_trail") for c in ("run", "stop")},
        "yards": {"run": list(np.quantile(np.random.default_rng(0).gamma(1.3, 3.3, 5000) - 0.5, q)),
                  "cmp": list(np.quantile(np.random.default_rng(1).gamma(1.6, 7.0, 5000), q)),
                  "sack": list(np.linspace(-12, -2, 100)), "scramble": list(np.linspace(0, 15, 100))},
        "fourth": {}, "fg": {"coef": -0.1014, "intercept": 6.14}, "punt_net": list(np.linspace(30, 55, 100)),
        "kickoff_start_ydl100": 70.0,
        "rates": {"sack": 0.064, "scramble": 0.048, "int": 0.023, "cmp": 0.65, "fumble_lost": 0.0073, "xp": 0.95},
    }
    lg = {f"{s}_{k}": v for s in ("off", "def") for k, v in
          (("proe", 0.0), ("sack", 0.064), ("scramble", 0.048), ("int", 0.023), ("cmp", 0.65), ("ypcmp", 11.0),
           ("ypc", 4.3), ("pace", 38.0))}
    return NS.League(spec, lg), lg


def _team(lg, **kw):
    base = {k.split("_", 1)[1]: v for k, v in lg.items() if k.startswith("off_")}
    return {"off": {**base, **kw}, "def": dict(base)}


def test_sim_is_reproducible_and_plausible():
    L, lg = _league()
    a = NS.simulate(L, _team(lg), _team(lg), n=400, seed=3, yards_shift=1.7)
    b = NS.simulate(L, _team(lg), _team(lg), n=400, seed=3, yards_shift=1.7)
    assert np.array_equal(a["pts_home"], b["pts_home"])
    plays = a["plays_home"].mean() + a["plays_away"].mean()
    assert 100 < plays < 170                           # synthetic clock here; the fitted one gives ~122
    top = (a["top_home"] + a["top_away"]).mean() / 60
    assert 50 < top <= 60


def test_better_offense_scores_more_and_wins_more():
    L, lg = _league()
    r = NS.simulate(L, _team(lg, ypcmp=13.0, ypc=5.0), _team(lg), n=1500, seed=1, yards_shift=1.7)
    assert r["pts_home"].mean() > r["pts_away"].mean() + 2
    assert ((r["pts_home"] - r["pts_away"]) > 0).mean() > 0.55


def test_trailing_team_throws_more():
    """Game script comes from the snap-level play call: the weaker team ends
    up behind, and behind means more dropbacks per snap."""
    L, lg = _league()
    r = NS.simulate(L, _team(lg, ypcmp=14.0, ypc=5.5), _team(lg, ypcmp=8.5, ypc=3.5), n=1500, seed=2, yards_shift=1.7)
    fav = r["drops_home"].sum() / r["plays_home"].sum()
    dog = r["drops_away"].sum() / r["plays_away"].sum()
    assert dog > fav


def test_player_layer_sums_to_team_and_uses_situational_shares():
    L, lg = _league()
    # player 0 gets every target when trailing, none otherwise
    tgt = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 1.0, 0.0], [0.0, 1.0, 0.0]])
    car = np.array([[0.0, 1.0, 0.0]] * 4)
    pl = {"tgt": tgt, "car": car, "catch": np.ones(3), "ypr": np.zeros(3), "ypc": np.zeros(3), "qb_col": -1}
    r = NS.simulate(L, _team(lg, ypcmp=7.0, ypc=3.0), _team(lg, ypcmp=14.0, ypc=5.5), n=600, seed=4,
                    yards_shift=1.7, players=(pl, pl))
    home = r["players"][0]
    assert np.allclose(home["tgt"].sum(1), home["qb"]["att"] - home["qb"]["int"])
    assert home["tgt"][:, 0].mean() > 3        # the weak home side trails a lot -> his trailing share matters
    assert np.allclose(home["rec_yds"].sum(1), home["qb"]["pass_yds"])


def test_shares_shrink_thin_situations_toward_overall():
    rows = pd.DataFrame({
        "pid": ["a", "b"],
        **{f"ew_tgt_{s}": [v, 1.0] for s, v in (("s0", 0.0), ("s1", 5.0), ("s2", 5.0), ("rz", 0.0))},
        **{f"ew_tgt_{s}_team": [1.0, 1.0] if s in ("s0", "rz") else [20.0, 20.0] for s in ("s0", "s1", "s2", "rz")},
    })
    rows["ew_tgt_all"] = rows[["ew_tgt_s0", "ew_tgt_s1", "ew_tgt_s2"]].sum(1)
    rows["ew_tgt_all_team"] = rows[["ew_tgt_s0_team", "ew_tgt_s1_team", "ew_tgt_s2_team"]].sum(1)
    A = M._shares(rows, "tgt")
    assert A.shape == (4, 3)
    assert np.allclose(A.sum(1), 1.0)
    assert A[0, 0] > 0.15            # 0 of 1 trailing target, but his overall share is ~24%


def test_implied_points_and_spread_sign():
    # nflverse spread_line > 0 means the home team is favored
    assert M.implied_points(3.0, 45.0, True) == 24.0
    assert M.implied_points(3.0, 45.0, False) == 21.0


def test_combine_and_calibration_are_sane():
    v = M.combine("rec_yds", "WR", 60.0, 55.0, CAL)
    assert 45 < v < 70
    assert M.combine("rec_yds", "QB", 3.0, 50.0, CAL) == 3.0          # stack only where it was fit
    p_low, p_high = M.prob_over("rec_yds", 60.0, 40.5, CAL), M.prob_over("rec_yds", 60.0, 80.5, CAL)
    assert p_low > 0.6 and p_high < 0.35
    assert abs(M.prob_over("rec", 4.0, 3.5, CAL) - (1 - (1 - M.prob_over("rec", 4.0, 3.5, CAL)))) < 1e-9
    assert 0 < M.td_prob(0.3, 0.35, CAL) < 0.5


def _props(rows):
    return pd.DataFrame([{"Player": p, "market": m, "Line": l, "bookmakers": b, "Over Price": o, "Under Price": u,
                          "fetched_at": "2026-11-10T12:00:00+00:00"} for p, m, l, b, o, u in rows])


def test_edges_flag_receiving_bets_and_mark_other_markets_watch():
    props = _props([
        ("Joe Receiver", "receptions", 6.5, "fanduel", -110, -110),
        ("Joe Receiver", "receptions", 6.5, "draftkings", -112, -108),
        ("Joe Receiver", "rush_yds", 40.5, "fanduel", -110, -110),
        ("Joe Receiver", "anytime_td", None, "fanduel", 250, None),
    ])
    lines = E.main_lines(props, set(), E.MARKETS)
    tds = E.td_prices(props, set())
    nomkt = {**CAL, "market_weight": {}}          # judge the raw projections here
    e = E.edges_for("Joe Receiver", {"rec": 3.5, "rush_yds": 20.0, "anytime_td": 0.45}, lines, tds, nomkt, "RB")
    assert e["receptions"]["side"] == "under" and e["receptions"]["tier"] == "bet"
    assert e["receptions"]["under_price"] == -108                       # best price at the main line
    assert e["rush_yds"]["side"] == "under" and e["rush_yds"]["tier"] == "watch"
    assert e["anytime_td"]["side"] == "yes" and e["anytime_td"]["tier"] == "watch"
    # rushing chances were calibrated on running backs only
    e2 = E.edges_for("Joe Receiver", {"rush_yds": 20.0}, lines, tds, nomkt, "QB")
    assert e2["rush_yds"]["side"] is None
    bets = E.best_bets([{"game_id": "g", "player": "Joe Receiver", "team": "X", "position": "RB", "lines": e}])
    assert [b["market"] for b in bets] == ["receptions"]


def test_no_flag_when_close_to_the_line():
    props = _props([("Ann Catcher", "reception_yds", 55.5, "fanduel", -110, -110)])
    e = E.edges_for("Ann Catcher", {"rec_yds": 56.0}, E.main_lines(props, set(), E.MARKETS), {}, CAL, "WR")
    assert e["reception_yds"]["side"] is None


def test_long_td_prices_not_flagged():
    props = _props([("Deep Bench", "anytime_td", None, "fanduel", 4000, None)])
    e = E.edges_for("Deep Bench", {"anytime_td": 0.07}, {}, E.td_prices(props, set()), CAL)
    assert e["anytime_td"]["side"] is None


def test_upcoming_rows_use_only_earlier_games():
    """A player's features for next week equal what a played game would have
    seen: EW of every game before it, none of its own."""
    G = pd.DataFrame({"game_id": ["g1", "g2", "g3"], "gameday": pd.to_datetime(["2026-09-07", "2026-09-14", "2026-09-21"]),
                      "home_team": "AAA", "away_team": "BBB", "spread_line": 3.0, "total_line": 44.0,
                      "roof": "outdoors", "wind": 5.0, "temp": 70.0})
    PS = pd.DataFrame({"player_id": "p1", "player_display_name": "Pat One", "position": "WR", "season": 2026,
                       "week": [1, 2], "season_type": "REG", "game_id": ["g1", "g2"], "team": "AAA",
                       "opponent_team": "BBB", "receptions": [4, 8], "receiving_yards": [40, 100], "targets": [6, 10],
                       "target_share": 0.25, "air_yards_share": 0.3, "wopr": 0.5})
    for c in M.DIRECT_STATS:
        if c not in PS.columns:
            PS[c] = 0
    SN = pd.DataFrame({"season": 2026, "week": [1, 2], "team": "AAA", "player": "Pat One", "offense_snaps": 50,
                       "offense_pct": [0.8, 0.9]})
    TP = pd.DataFrame({"game_id": ["g1", "g2", "g3"], "team": "AAA"})
    up = pd.DataFrame([{"player_id": "p1", "player_display_name": "Pat One", "position": "WR", "team": "AAA",
                        "opponent_team": "BBB", "game_id": "g3", "season": 2026, "week": 3, "season_type": "REG"}])
    X = M.player_features(PS, SN, G, TP, up)
    u = X[X._up == 1].iloc[0]
    played2 = X[(X._up == 0) & (X.game_id == "g2")].iloc[0]
    assert u.last_rec == 8 and played2.last_rec == 4
    assert 4 < u.ew_rec < 8 and u.n_games == 2


def test_projection_is_pulled_toward_the_line_before_pricing():
    props = _props([("Ann Catcher", "reception_yds", 60.5, "fanduel", -110, -110)])
    lines = E.main_lines(props, set(), E.MARKETS)
    e = E.edges_for("Ann Catcher", {"rec_yds": 40.0}, lines, {}, CAL, "WR")["reception_yds"]
    w = CAL["market_weight"]["rec_yds"]
    assert e["model"] == 40.0 and abs(e["projection"] - ((1 - w) * 40.0 + w * 60.5)) < 0.06
    raw = E.edges_for("Ann Catcher", {"rec_yds": 40.0}, lines, {}, {**CAL, "market_weight": {}}, "WR")["reception_yds"]
    assert e["prob_under"] < raw["prob_under"]


def test_props_history_flatten_and_budget():
    import pytest
    import get_nfl_props_history as H
    payload = {"timestamp": "2025-09-07T16:30:00Z", "data": {
        "id": "ev1", "commence_time": "2025-09-07T17:00:00Z", "home_team": "Detroit Lions", "away_team": "Green Bay Packers",
        "bookmakers": [{"key": "fanduel", "markets": [{"key": "player_receptions", "outcomes": [
            {"name": "Over", "description": "Amon-Ra St. Brown", "price": -120, "point": 6.5},
            {"name": "Under", "description": "Amon-Ra St. Brown", "price": -105, "point": 6.5}]}]}]}}
    df = H.flatten(payload)
    assert len(df) == 1 and df.market.iloc[0] == "receptions" and df.Line.iloc[0] == 6.5
    assert df["Over Price"].iloc[0] == -120 and df.observed_at.iloc[0] == "2025-09-07T16:30:00Z"
    m = H.Meter(100)
    m.spent = 60
    with pytest.raises(H.OverBudget):
        m.check(50)
    m.check(40)
