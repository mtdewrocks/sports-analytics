"""NBA props: alternate-ladder merge in the middles builder, gap-bet pricing."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import build_prop_middles as bpm  # noqa: E402
import props_config  # noqa: E402

from app.data import nba_gaps  # noqa: E402


def test_nba_is_a_props_sport():
    cfg = props_config.SPORTS["nba"]
    assert cfg.output == "NBA_Props.parquet" and len(cfg.all_markets) == 27


def _leg(market, line, book, o, u):
    return {"Player": "Test Guard", "market": market, "Line": line, "bookmakers": book,
            "Over Price": o, "Under Price": u, "event_id": "e1"}


def test_main_line_pairs_with_other_books_alternate_rung():
    df = pd.DataFrame([
        _leg("points", 21.5, "betmgm", -140, 115),
        _leg("points_alternate", 22.5, "fanduel", 110, None),
        _leg("points", 21.5, "betmgm", -140, 115),          # duplicate row
    ])
    pairs = bpm.find_pairs(bpm.merge_alternate_ladders(df))
    assert len(pairs) == 1
    p = pairs.iloc[0]
    assert (p["kind"], p["market"], p["window"]) == ("anti_middle", "points", "22")
    # unmerged, the two legs sit in different (Player, market) groups
    assert bpm.find_pairs(df).empty


def test_gap_bet_priced_from_history(monkeypatch):
    pairs = pd.DataFrame([{
        "Player": "Test Guard", "market": "points", "kind": "anti_middle",
        "over_book": "fanduel", "over_line": 22.5, "over_price": 110.0,
        "under_book": "betmgm", "under_line": 21.5, "under_price": 115.0,
        "stake_over_pct": 50.6, "one_wins_pct": 6.21, "breakeven_window_rate_pct": 5.8,
        "commence_time": (pd.Timestamp.now(tz="UTC") + pd.Timedelta(hours=3)).isoformat(),
        "home_team": "New York Knicks", "away_team": "Milwaukee Bucks",
        "fetched_at": "2026-11-10T18:00:00+00:00", "dfs_leg": "",
    }])
    pts = [22] * 3 + [18, 25, 30, 20, 24, 27, 19] * 3 + [21] * 6    # 3 of 30 land on 22
    stats = pd.DataFrame({"player": "Test Guard", "team": "NYK", "pts": pts, "played": 1,
                          "date": pd.date_range("2026-10-01", periods=len(pts))})
    monkeypatch.setattr(nba_gaps, "get_middles_data", lambda sport: pairs)
    monkeypatch.setattr(nba_gaps, "get_nba_all_seasons", lambda: stats)

    out = nba_gaps.get_gap_bets(include_negative=True)
    r = out["rows"][0]
    assert r["gap"] == "22" and r["games"] == 30 and r["landing_pct"] == 10.0
    assert r["ev_pct"] == round(100 * (0.9 * 0.0621 - 0.1), 2)          # lands too often -> negative
    assert out["lines_as_of"] == "2026-11-10T18:00:00+00:00"
    assert nba_gaps.get_gap_bets()["rows"] == []                          # hidden by default


def test_name_key_matches_accents_and_suffixes():
    assert nba_gaps.name_key("Nikola Jokić") == nba_gaps.name_key("Nikola Jokic")
    assert nba_gaps.name_key("Jaren Jackson Jr.") == nba_gaps.name_key("Jaren Jackson Jr")


def test_totals_markets_and_modelled_landing_rate():
    cfg = props_config.SPORTS["nba"]
    assert {"totals", "team_totals"} <= set(cfg.core_markets)
    assert {"alternate_totals", "alternate_team_totals"} <= set(cfg.alt_markets)
    # alternate_ prefix folds into the base market so a main total pairs with an alt rung
    df = pd.DataFrame([
        {**_leg("totals", 227.5, "betmgm", -125, 108), "Player": "Away @ Home"},
        {**_leg("alternate_totals", 228.5, "fanduel", 110, None), "Player": "Away @ Home"},
    ])
    pairs = bpm.find_pairs(bpm.merge_alternate_ladders(df))
    assert list(pairs["market"]) == ["totals"] and pairs.iloc[0]["window"] == "228"
    # ~2.2% for one number at sd 18
    assert abs(nba_gaps._normal_window(228, 228, 228.0, 18.0) - 0.0222) < 0.001


def test_gap_log_first_sighting_and_grading(monkeypatch):
    import build_gap_log as bgl
    now = pd.Timestamp("2026-11-04T18:00:00Z")
    pair = {"Player": "Test Guard", "market": "points", "kind": "anti_middle",
            "commence_time": "2026-11-05T00:30:00+00:00", "over_book": "fanduel", "over_line": 33.5,
            "under_book": "betmgm", "under_line": 32.5, "over_price": 115.0, "under_price": 110.0,
            "one_wins_pct": 6.2, "breakeven_window_rate_pct": 5.8, "stake_over_pct": 49.4,
            "window": "33", "dfs_leg": "", "home_team": "", "away_team": ""}
    log = bgl.update_log(pd.DataFrame([pair]), pd.DataFrame(), now)
    again = bgl.update_log(pd.DataFrame([{**pair, "over_price": 130.0}]), log, now + pd.Timedelta(hours=1))
    assert len(again) == 1 and again.iloc[0]["over_price"] == 115.0          # first-seen price kept

    pts = [20] * 12 + [33]                               # last game (Nov 4 ET) lands in the gap
    stats = pd.DataFrame({"player": "Test Guard", "team": "NYK", "pts": pts, "played": 1,
                          "season": 2027, "date": pd.date_range("2026-10-23", periods=len(pts))})
    monkeypatch.setattr(nba_gaps, "get_nba_gap_log", lambda: again)
    monkeypatch.setattr(nba_gaps, "get_nba_all_seasons", lambda: stats)
    rec = nba_gaps.get_gap_record()
    assert rec["overall"] == {"bets": 1, "one_leg_won": 0, "gap_hits": 1, "return_pct": -100.0, "net_per_100": -100.0}
    assert rec["recent"][0]["result"] == 33.0


def test_injury_impact_finds_beneficiary(monkeypatch):
    from app.data import nba_injury_impact as nii
    rows = []
    days = pd.date_range("2026-10-21", periods=10)
    for i, d in enumerate(days):
        star_plays = i < 7
        if star_plays:
            rows.append({"player": "Star Guard", "team": "LAL", "date": d, "min": 36, "pts": 30, "reb": 8, "ast": 8, "fga": 22, "pra": 46})
        rows.append({"player": "Wing Two", "team": "LAL", "date": d, "min": 34 if star_plays else 38,
                     "pts": 22 if star_plays else 29, "reb": 4, "ast": 5 if star_plays else 3, "fga": 16 if star_plays else 21,
                     "pra": 31 if star_plays else 36})
    stats = pd.DataFrame(rows).assign(season=2027, played=1)
    stats["season"] = stats["season"].astype("Int64")
    inj = pd.DataFrame([{"player": "Star Guard", "team": "Los Angeles Lakers", "status": "Out",
                         "detail": "Ankle", "source_updated": "2026-11-10T15:00Z"}])
    monkeypatch.setattr(nii, "get_nba_all_seasons", lambda: stats)
    monkeypatch.setattr(nii, "get_injuries_data", lambda sport: inj)
    monkeypatch.setattr(nii, "get_nba_schedule", lambda: pd.DataFrame())
    out = nii.get_injury_impact()
    card = out["players"][0]
    assert card["team"] == "LAL" and card["basis_label"] == "2026-27"
    b = card["beneficiaries"][0]
    assert b["player"] == "Wing Two" and b["delta"]["pts"] == 7.0 and "pts" in b["flags"] and "min" in b["flags"]
    assert (b["games_with"], b["games_without"]) == (7, 3)
    assert nii.match_key("Mikel Brown Jr.") == nii.match_key("Mikel Brown")


def test_gap_bets_one_pair_per_game_and_no_even_money(monkeypatch):
    from app.data import nba_gaps
    tip = (pd.Timestamp.now(tz="UTC") + pd.Timedelta(hours=5)).isoformat()
    base = {"kind": "anti_middle", "Player": "Pat Guard", "market": "points", "commence_time": tip,
            "stake_over_pct": 50.0, "breakeven_window_rate_pct": 8.0, "home_team": "A", "away_team": "B"}
    pairs = pd.DataFrame([
        {**base, "under_book": "fanduel", "under_line": 20.5, "under_price": 115, "over_book": "draftkings",
         "over_line": 21.5, "over_price": 110, "one_wins_pct": 6.0},
        {**base, "under_book": "betmgm", "under_line": 20.5, "under_price": 120, "over_book": "draftkings",
         "over_line": 21.5, "over_price": 112, "one_wins_pct": 8.0},
        {**base, "under_book": "espnbet", "under_line": 20.5, "under_price": 100, "over_book": "draftkings",
         "over_line": 21.5, "over_price": 150, "one_wins_pct": 20.0},          # even-money leg: dropped
    ])
    stats = pd.DataFrame({"player": "Pat Guard", "team": "AAA", "pts": [15, 18, 25, 30, 12, 24, 27, 16, 19, 23, 26, 17],
                          "date": pd.date_range("2026-10-01", periods=12, freq="2D")})
    monkeypatch.setattr(nba_gaps, "get_middles_data", lambda sport: pairs)
    monkeypatch.setattr(nba_gaps, "get_nba_all_seasons", lambda: stats)
    rows = nba_gaps.get_gap_bets(include_negative=True)["rows"]
    assert len(rows) == 1
    assert rows[0]["under_book"] == "betmgm" and rows[0]["under_price"] == 120
