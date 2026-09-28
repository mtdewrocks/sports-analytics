"""Closing-line value (market_core.closing_for), the flagged-plays log behind
the EV Finder report card, and the Daily Briefing's play and line-move rules."""

import pandas as pd

from app.market_core import closing_for
from build_flagged_plays import grade, new_flags

CLOSES = pd.DataFrame([
    {"event_id": "e1", "Player": "Jalen Brunson", "market": "points", "Line": 26.5,
     "bookmakers": "pinnacle", "Over Price": -125, "Under Price": 105},
    {"event_id": "e1", "Player": "Jalen Brunson", "market": "points", "Line": 26.5,
     "bookmakers": "fanduel", "Over Price": -130, "Under Price": 100},
])
BET = {"event_id": "e1", "player": "Jalen Brunson", "market": "points", "line": 26.5,
       "side": "over", "book": "fanduel", "price": -110}


def test_clv_uses_pinnacle_fair_close():
    c = closing_for(BET, CLOSES)
    # Pinnacle -125/+105 -> fair over 53.25%; -110 decimal 1.909 -> +1.65% CLV.
    assert c["close_price"] == -130
    assert abs(c["close_fair_pct"] - 53.25) < 0.05
    assert abs(c["clv_pct"] - 1.65) < 0.05


def test_clv_none_when_line_moved():
    assert closing_for({**BET, "line": 27.5}, CLOSES) is None


def test_flagged_plays_first_sighting_and_grading():
    ev = [{**BET, "price": -110, "fair_pct": 52, "ev_pct": 3, "source": "sharp", "consensus_books": 1,
           "commence_time": "2026-01-01T00:00:00Z", "home_team": "NYK", "away_team": "BOS"}]
    first = new_flags(ev, pd.DataFrame(), "t0")
    assert len(first) == 1
    assert new_flags(ev, first, "t1").empty          # already logged: not re-added
    graded = grade(first, CLOSES, pd.Timestamp("2026-01-02", tz="UTC"))
    assert abs(float(graded.iloc[0]["clv_pct"]) - 1.65) < 0.05


def test_briefing_play_rules():
    from app.data.briefing import _play_ok
    assert _play_ok({"price": -250, "ev_pct": 2}) == "standard"
    assert _play_ok({"price": 400, "ev_pct": 8, "source": "consensus", "consensus_books": 3}) == "longshot"
    assert _play_ok({"price": 400, "ev_pct": 8, "source": "consensus", "consensus_books": 2}) is None
    assert _play_ok({"price": 400, "ev_pct": 4, "source": "sharp"}) is None
    assert _play_ok({"price": 700, "ev_pct": 20, "source": "sharp"}) is None
    assert _play_ok({"price": -300, "ev_pct": 3}) is None
    assert _play_ok({"price": 110, "ev_pct": 3, "suspicious": True}) is None


def test_briefing_line_moves_filters_noise():
    from app.data.briefing import line_moves
    now = pd.Timestamp("2026-09-27T12:00:00Z")
    future = "2026-09-27T17:00:00Z"
    props = pd.DataFrame([
        {"event_id": "e", "Player": "Starter", "market": "rush_yds", "Line": 55.5, "commence_time": future},
        {"event_id": "e", "Player": "Backup", "market": "reception_yds", "Line": 0.5, "commence_time": future},
        {"event_id": "e", "Player": "Steady", "market": "receptions", "Line": 4.5, "commence_time": future},
    ])
    snaps = pd.DataFrame([
        {"event_id": "e", "Player": "Starter", "market": "rush_yds", "Line": 42.5, "bookmakers": "dk",
         "observed_at": "2026-09-26T20:00:00+00:00"},
        {"event_id": "e", "Player": "Backup", "market": "reception_yds", "Line": 1.5, "bookmakers": "dk",
         "observed_at": "2026-09-26T20:00:00+00:00"},
        {"event_id": "e", "Player": "Steady", "market": "receptions", "Line": 4.5, "bookmakers": "dk",
         "observed_at": "2026-09-26T20:00:00+00:00"},
    ])
    out = line_moves("nfl", props, snaps, now)
    assert [o["title"] for o in out] == ["Starter rushing yards 42.5 → 55.5"]
