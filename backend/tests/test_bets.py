from types import SimpleNamespace

import pandas as pd

from app.bets.grading import closing_for, settle, summarize
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


def test_settle():
    assert settle(27, 26.5, "over") == "win" and settle(27, 26.5, "under") == "loss"
    assert settle(3, 3.0, "over") == "push"
    assert settle(1, None, "over") == "win" and settle(0, None, "over") == "loss"
    assert settle(None, 1.5, "over") is None


def test_summary_roi_and_clv():
    bets = [SimpleNamespace(result="win", price=150, clv_pct=3.0, verification="verified"),
            SimpleNamespace(result="loss", price=-110, clv_pct=-1.0, verification="verified"),
            SimpleNamespace(result="pending", price=120, clv_pct=None, verification="self_reported")]
    s = summarize(bets)
    assert s["record"] == {"win": 1, "loss": 1, "push": 0}
    assert s["units"] == 0.5 and s["roi_pct"] == 25.0
    assert s["avg_clv_pct"] == 1.0 and s["beat_close_pct"] == 50.0 and s["verified_share_pct"] == 67


def test_flagged_plays_first_sighting_and_grading():
    ev = [{**BET, "price": -110, "fair_pct": 52, "ev_pct": 3, "source": "sharp", "consensus_books": 1,
           "commence_time": "2026-01-01T00:00:00Z", "home_team": "NYK", "away_team": "BOS"}]
    first = new_flags(ev, pd.DataFrame(), "t0")
    assert len(first) == 1
    assert new_flags(ev, first, "t1").empty          # already logged: not re-added
    graded = grade(first, CLOSES, pd.Timestamp("2026-01-02", tz="UTC"))
    assert abs(float(graded.iloc[0]["clv_pct"]) - 1.65) < 0.05


def test_today_tiers_and_stake_sizing():
    from app.data.today import alt_longshot_ok, ev_longshot_ok, stake_pct, tier
    assert tier(-250) == "standard" and tier(250) == "standard"
    assert tier(251) == "longshot" and tier(600) == "longshot"
    assert tier(601) is None and tier(-300) is None
    # -110 at 55%: quarter-Kelly ~1.4%, under the 2% cap.
    assert abs(stake_pct(0.55, -110, "standard") - 1.36) < 0.05
    # +400 at 24%: quarter-Kelly 1.25%, capped at 0.5% for a long shot.
    assert stake_pct(0.24, 400, "longshot") == 0.5
    assert stake_pct(0.40, 150, "standard") == 0.0          # no edge, no stake
    assert ev_longshot_ok({"ev_pct": 8, "source": "consensus", "consensus_books": 3})
    assert not ev_longshot_ok({"ev_pct": 8, "source": "consensus", "consensus_books": 2})
    assert not ev_longshot_ok({"ev_pct": 4, "source": "sharp"})
    assert alt_longshot_ok({"season_sample": "10/30", "recent_sample": "3/10", "implied_pct": 22})
    assert not alt_longshot_ok({"season_sample": "10/30", "recent_sample": "1/10", "implied_pct": 22})
    assert not alt_longshot_ok({"season_sample": "5/15", "recent_sample": "4/10", "implied_pct": 22})


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
