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
    assert cfg.output == "NBA_Props.parquet" and len(cfg.all_markets) == 23


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
