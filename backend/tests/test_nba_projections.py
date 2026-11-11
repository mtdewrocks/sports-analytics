"""NBA Projections: feature port, default minutes, edges, live re-projection."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import nba_projection_edges as E  # noqa: E402
import nba_projection_features as F  # noqa: E402


def _history(n_days=30):
    rows, rng = [], np.random.default_rng(0)
    teams = [("NYK", "BOS"), ("BOS", "NYK")]
    for i, d in enumerate(pd.date_range("2026-10-01", periods=n_days, freq="2D")):
        for team, opp in teams:
            for j in range(8):
                rows.append({"PLAYER": f"{team} P{j}", "TEAM": team, "Opponent": opp, "GAME DATE": d,
                             "MIN": (mn := int(36 - 3 * j + rng.integers(-6, 7))), "PTS": int(0.6 * mn + rng.integers(-3, 4)), "AST": int(rng.integers(0, 8)),
                             "REB": int(rng.integers(0, 10)), "TOV": 2, "BLK": 1, "STL": 1, "3PM": 2,
                             "FGA": 12, "FTA": 4, "OREB": 1, "Location": "Home" if (team == "NYK") == (i % 2 == 0) else "Away",
                             "Played": 1})
    return pd.DataFrame(rows)


def test_feature_columns_match_shawns_saved_lists():
    cols = F.feature_columns(True)
    assert cols[:5] == ["MIN", "is_b2b", "is_3in4", "is_3plus_away", "PACE_rel"]
    assert cols[-2:] == ["USG_SHARE_roll5", "USG_SHARE_roll10"] and "Opponent_ATL" not in cols
    assert len(cols) == 72 and len(F.feature_columns(False)) == 70


def test_training_and_slate_features_use_prior_games_only():
    h = _history()
    X = F.build_features(h)
    assert not X.empty and X[F.feature_columns(True)].notna().all().all()
    last = h["GAME DATE"].max()
    slate = pd.DataFrame({"PLAYER": ["NYK P0"], "TEAM": ["NYK"], "Opponent": ["BOS"],
                          "GAME DATE": [last + pd.Timedelta(days=2)], "Location": ["Home"]})
    s = F.build_slate_features(h, slate)
    assert len(s) == 1 and np.isnan(s["MIN"].iloc[0])
    prev5 = h[h["PLAYER"] == "NYK P0"].sort_values("GAME DATE")["PTS"].tail(5).mean()
    assert s["PTS_roll5"].iloc[0] == prev5                  # tonight's row sees only past games


def test_default_minutes_shares_newly_out_and_fits_240():
    s = pd.DataFrame({"TEAM": ["LAL"] * 9, "PLAYER": list("ABCDEFGHI"),
                      "ew_min": [36, 32, 30, 28, 24, 20, 16, 12, 10],
                      "played_last": [True] * 9, "out": [True] + [False] * 8})
    m = F.default_minutes(s)
    assert m.iloc[0] == 0 and m.iloc[1] > 32                 # star out, teammates up
    assert m.sum() < 240                                     # under 240: nothing trimmed or inflated
    deep = pd.DataFrame({"TEAM": ["LAL"] * 13, "PLAYER": list("ABCDEFGHIJKLM"),
                         "ew_min": [34, 32, 30, 28, 26, 22, 18, 14, 12, 12, 10, 8, 6],
                         "played_last": [True] * 13, "out": [False] * 13})
    d = F.default_minutes(deep)
    assert abs(d.sum() - 240) < 0.5                          # bench trimmed to fit
    assert list(d.iloc[:7]) == [34, 32, 30, 28, 26, 22, 18]  # 15+ minute players left alone


def test_main_line_and_expected_value_edges():
    props = pd.DataFrame([
        {"Player": "Jalen Brunson", "market": "points", "Line": 25.5, "bookmakers": "fanduel", "Over Price": -115, "Under Price": -105, "fetched_at": "t"},
        {"Player": "Jalen Brunson", "market": "points", "Line": 25.5, "bookmakers": "draftkings", "Over Price": -105, "Under Price": -115, "fetched_at": "t"},
        {"Player": "Jalen Brunson", "market": "points", "Line": 26.5, "bookmakers": "betmgm", "Over Price": 105, "Under Price": -125, "fetched_at": "t"},
        {"Player": "Jalen Brunson", "market": "points_alternate", "Line": 30.5, "bookmakers": "fanduel", "Over Price": 250, "Under Price": None, "fetched_at": "t"},
    ])
    lines = E.main_lines(props, set())
    ln = lines[(E.match_key("Jalen Brunson"), "points")]
    assert ln["line"] == 25.5 and ln["over_price"] == -105 and ln["over_book"] == "draftkings"
    # results spread evenly from half to 1.5x the projection
    cal = {"PTS": {"edges": [], "ratios": [list(np.linspace(0.5, 1.5, 199))]}}
    e = E.edges_for("Jalen Brunson", {"PTS": 27.6}, lines, cal)["points"]
    assert abs(e["model_prob_over"] - 0.578) < 0.01 and e["market_prob_over"] == 0.5
    # shrunk toward 50% and averaged with the book: 57.8% -> ~53% -> not enough
    assert abs(e["prob_over"] - (0.5 * (0.5 + E.PROB_SHRINK * 0.078) + 0.25)) < 0.01 and e["side"] is None
    e = E.edges_for("Jalen Brunson", {"PTS": 30.0}, lines, cal)["points"]
    assert e["side"] == "over" and e["price"] == -105 and 0.07 < e["ev"] < 0.13 and not e["suspect"]
    # +5% on price alone isn't enough when the model barely disagrees with the book
    assert E.edges_for("Jalen Brunson", {"PTS": 26.5}, lines, cal)["points"]["side"] is None
    # no calibration -> no chance -> nothing flagged
    assert E.edges_for("Jalen Brunson", {"PTS": 27.6}, lines)["points"]["side"] is None


def _history_v2(n_days=40):
    h = _history(n_days)
    h["STARTER"] = (h["PLAYER"].str[-1].astype(int) < 5).astype(int)
    h["Season"] = 2027
    return h


def _v2_models(h, vegas=False, odds=None):
    import get_nba_projections as G
    X = F.build_features_v2(h, odds)
    models = {}
    for st in F.TARGETS:
        m, cols = G._fit(X, st, vegas)
        models[st] = (m, cols, True)
    return models, G._fit_minutes(F.build_minutes_training(h))


def _slate(h):
    last = h["GAME DATE"].max() + pd.Timedelta(days=2)
    base = pd.DataFrame([{"PLAYER": f"{t} P{j}", "TEAM": t, "Opponent": o, "GAME DATE": last, "Location": loc}
                         for t, o, loc in (("NYK", "BOS", "Home"), ("BOS", "NYK", "Away")) for j in range(8)])
    feats = F.build_slate_features(h, base)
    sl = F.slate_minutes_inputs(h, base.assign(played_last=True, out=False, status=None, injury=None,
                                              espn_game_id=1, start_utc="2026-12-01T00:00:00Z",
                                              home="NYK", away="BOS"))
    feats = feats.merge(sl, on=["PLAYER", "TEAM", "Opponent", "GAME DATE", "Location"], how="left")
    feats["start_rate5"] = feats["start5"]
    return feats


def test_minutes_model_and_per_minute_projection(monkeypatch):
    from app.data import nba_projections as NP
    h = _history_v2()
    models, mb = _v2_models(h)
    feats = _slate(h)
    mins = F.model_minutes(feats, mb)
    for t, g in feats.assign(m=mins).groupby("TEAM"):
        assert g["m"].sum() <= 240.5 and (g["m"] > 0).all()
    feats["default_min"] = mins
    monkeypatch.setattr(NP, "get_projection_slate", lambda: feats)
    monkeypatch.setattr(NP, "_cached_boosters", lambda: (models, {"trained_through": "x"}))
    NP._models["minutes"] = mb
    monkeypatch.setattr(NP, "get_props_data", lambda sport: pd.DataFrame())
    monkeypatch.setattr(NP, "get_injuries_data", lambda sport: pd.DataFrame(
        [{"player": "NYK P1", "status": "Out", "detail": "Knee"}]))
    out = NP.get_projections()
    nyk = [t for t in out["games"][0]["teams"] if t["team"] == "NYK"][0]
    p1 = [p for p in nyk["players"] if p["player"] == "NYK P1"][0]
    assert p1["minutes"] == 0 and p1["projection"]["PTS"] == 0 and p1["status"] == "Out"   # live injury applied
    lo = NP.get_projections(1, {"NYK P0": 20})
    hi = NP.get_projections(1, {"NYK P0": 36})
    pts = lambda o: [p for t in o["games"][0]["teams"] for p in t["players"] if p["player"] == "NYK P0"][0]["projection"]["PTS"]  # noqa: E731
    assert pts(hi) > pts(lo) * 1.5                     # per-minute: more minutes, proportionally more


def test_teammate_out_shifts_usage():
    h = _history_v2()
    models, _ = _v2_models(h)
    feats = _slate(h)
    base_min = pd.Series([30.0] * len(feats), index=feats.index)
    a = F.predict_stats(models, feats, base_min)
    m2 = base_min.copy()
    m2[feats["PLAYER"] == "NYK P0"] = 0
    b = F.predict_stats(models, feats, m2)
    ctx = F.slate_context(feats, m2)
    assert ctx.loc[feats["PLAYER"] == "NYK P1", "usg_newly_out"].iloc[0] > 0
    assert b.loc[feats["PLAYER"] == "NYK P0", "PTS"].iloc[0] == 0


def test_train_picks_vegas_only_when_it_helps():
    import get_nba_projections as G
    h = _history_v2(60)
    games = h[["GAME DATE", "TEAM", "Opponent", "Location"]].drop_duplicates()
    home = games[games["Location"] == "Home"]
    odds = pd.DataFrame({"espn_game_id": range(len(home)), "date": home["GAME DATE"].dt.date.astype(str),
                         "home": home["TEAM"], "away": home["Opponent"], "total": 220.0, "home_spread": -3.0})
    X = F.build_features_v2(h, odds)
    assert X["implied_pts"].notna().mean() > 0.9 and set(X.loc[X["TEAM"] == "NYK", "implied_pts"].dropna().unique()) <= {111.5, 108.5}
    b = G.train(h, odds)
    assert b["vegas_coverage"] > 0.9 and isinstance(b["uses_vegas"], bool) and b["minutes_model"]["model"]


def test_espn_odds_parse_and_history():
    import get_nba_data as N
    h, a = {"team": {"abbreviation": "NY"}}, {"team": {"abbreviation": "MIL"}}
    assert N.parse_odds({"odds": [{"details": "NY -4.5", "overUnder": 228.5}]}, h, a) == (228.5, -4.5)
    assert N.parse_odds({"odds": [{"details": "MIL -2", "overUnder": 230}]}, h, a) == (230.0, 2.0)
    assert N.parse_odds({}, h, a) == (None, None)


def test_short_history_gets_partial_windows_without_borrowing_other_players():
    """A player with fewer than 10 games (rookie, or back from a long injury)
    gets his long-window features from the games he has -- and never from
    the previous player's rows in the frame."""
    h = _history(n_days=30)
    new = h[h["PLAYER"] == "NYK P0"].tail(7).copy()
    new["PLAYER"] = "NYK Z9"                       # sorts after the others on his team
    new["PTS"] = 40
    X = F._engineer(F._clean(pd.concat([h, new], ignore_index=True)))
    z = X[X["PLAYER"] == "NYK Z9"].sort_values("GAME DATE")
    assert z["PTS_oly10"].isna().sum() == 5         # needs 5 prior games
    assert (z["PTS_oly10"].dropna() == 40).all()     # only his own games
    assert (z["PTS_roll5"].dropna() == 40).all() and z["USG_SHARE_roll10"].notna().sum() == 2


def test_odds_history_consensus_line():
    import get_nba_odds_history as OH
    ev = {"home_team": "Boston Celtics", "bookmakers": [
        {"markets": [{"key": "spreads", "outcomes": [{"name": "Boston Celtics", "point": -6.5}, {"name": "Miami Heat", "point": 6.5}]},
                     {"key": "totals", "outcomes": [{"name": "Over", "point": 221.5}, {"name": "Under", "point": 221.5}]}]},
        {"markets": [{"key": "spreads", "outcomes": [{"name": "Boston Celtics", "point": -7.5}]},
                     {"key": "totals", "outcomes": [{"name": "Over", "point": 222.5}]}]},
        {"markets": [{"key": "spreads", "outcomes": [{"name": "Boston Celtics", "point": -6.5}]}]}]}
    assert OH.consensus(ev) == {"home_spread": -6.5, "total": 222.0}
    assert OH.TEAMS["LA Clippers"] == "LAC"
