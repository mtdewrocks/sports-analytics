import pandas as pd
import pytest

import app.data.mlb as mlb
import app.data.mlb_game_log_context as ctx


def blog(pid, pk, is_home, pa=4, ab=4, h=1, d=0, t=0, hr=0, bb=0, so=1, date="2026-09-20", opp="X"):
    return {"player_id": pid, "player": f"P{pid}", "game_pk": pk, "date": date, "opponent": opp,
            "is_home": is_home, "at_bats": ab, "plate_appearances": pa, "runs": 0, "hits": h,
            "doubles": d, "triples": t, "home_runs": hr, "rbi": 0, "walks": bb, "strikeouts": so,
            "stolen_bases": 0, "total_bases": h + d + 2 * t + 3 * hr}


def _clear():
    for f in (ctx._hitter_season_rates, ctx._lineups_faced, ctx._league_vs_hand, ctx._flag_counts_by_game,
              mlb._mlb_pitcher_index, mlb._mlb_batter_index, mlb._mlb_batter_bats_index,
              mlb._mlb_starting_pitcher_hand):
        f.cache_clear()


@pytest.fixture
def data(monkeypatch):
    def _set(d):
        monkeypatch.setattr(ctx, "get_mlb_data", lambda: d)
        monkeypatch.setattr(mlb, "get_mlb_data", lambda: d)
        monkeypatch.setattr(ctx, "_props_df", lambda: pd.DataFrame())
        _clear()
    yield _set
    _clear()


def test_prop_line_matches_the_pages_grading():
    # The page grades value >= threshold, so "1" is the 0.5 line.
    assert ctx.prop_line_for_threshold(1) == 0.5
    assert ctx.prop_line_for_threshold(5) == 4.5
    assert ctx.prop_line_for_threshold(0.5) == 0.5
    assert ctx.prop_line_for_threshold(0) is None


def test_lineup_faced_uses_the_nine_busiest_hitters_at_season_rates(data):
    # Away side of game 1: nine regulars who strike out once in 4 PA, plus a
    # one-PA pinch hitter who whiffs -- he must not be in the nine.
    rows = [blog(i, 1, False, so=1) for i in range(1, 10)] + [blog(99, 1, False, pa=1, ab=1, h=0, so=1)]
    data({"batter_logs": pd.DataFrame(rows)})
    faced = ctx.lineup_faced_for(1, pitcher_is_home=True)
    assert faced["k_pct"] == 25.0 and faced["avg"] == 0.25
    assert ctx.lineup_faced_for(1, pitcher_is_home=False) is None  # nobody batted for the home side


def test_batter_vs_hand_grades_only_that_hand():
    rows = pd.DataFrame({
        "throws": ["L", "L", "R"], "stat_value": [1, 0, 2],
        "at_bats": [4, 4, 4], "plate_appearances": [4, 4, 4], "hits": [1, 0, 2],
        "walks": [0, 0, 0], "strikeouts": [1, 2, 0], "total_bases": [1, 0, 3],
    })
    v = ctx.batter_vs_hand(rows, "L", 1)
    assert v["games"] == 2 and v["over"] == 1 and v["total"] == 2
    assert v["avg"] == 0.125 and v["k_pct"] == 37.5
    assert ctx.batter_vs_hand(rows, None, 1) is None


def test_pitcher_log_carries_lineups_and_next_start(data):
    pitcher_logs = pd.DataFrame([
        {"pitcher_id": 7, "pitcher": "Ace Lefty", "game_pk": 1, "date": "2026-09-10", "opponent": "Opp",
         "is_home": True, "wins": 1, "losses": 0, "innings": 6.0, "hits": 4, "runs": 1, "earned_runs": 1,
         "home_runs": 1, "walks": 2, "strikeouts": 8, "pitches": 95, "games_started": 1},
    ])
    batter_logs = pd.DataFrame([blog(i, 1, False, so=2) for i in range(1, 10)])
    matchups = pd.DataFrame([
        {"pitcher_id": 7, "pitcher": "Ace Lefty", "throws": "L", "team": "Opp", "batter_id": 100 + i,
         "split_k_pct": 30.0, "split_avg": 0.220, "split_woba": 0.290, "split_iso": 0.120, "split_bb_pct": 6.0,
         "all_k_pct": 29.0, "all_avg": 0.225, "all_woba": 0.295, "all_iso": 0.125, "all_bb_pct": 6.5,
         "game_time_utc": "2026-09-26T23:05:00Z"} for i in range(9)
    ])
    probable = pd.DataFrame([{"date": "2026-09-26", "game_pk": 2, "pitcher_id": 7, "pitcher": "Ace Lefty",
                              "team": "Home", "opponent": "Opp", "is_home": True}])
    data({"pitcher_logs": pitcher_logs, "batter_logs": batter_logs, "matchups": matchups,
          "probable_starters": probable, "starters": pd.DataFrame([{"pitcher_id": 7, "throws": "L"}]),
          "pitcher_splits": pd.DataFrame([{"player_id": 7, "split": "vs L", "tbf": 100, "avg": 0.2,
                                           "woba": 0.28, "iso": 0.1, "k_pct": 25.0, "bb_pct": 7.0}])})
    out = mlb.get_mlb_pitcher_game_log("Ace Lefty", "pitcher_strikeouts", 5)
    assert out["games"][0]["lineup"]["k_pct"] == 50.0
    ns = out["next_start"]
    assert ns["lineup_status"] == "posted" and ns["tonight"]["k_pct"] == 30.0
    assert ns["faced_avg"]["k_pct"] == 50.0 and ns["league"]["k_pct"] == 25.0
    assert ns["flag"]["key"] == "high_k_hitter" and ns["flag"]["count"] == 9
    # Tonight's lineup (29% K overall) is below his 50% faced average.
    assert ns["similar"]["side"] == "below" and ns["similar"]["total"] == 0
    assert ns["line"] == 4.5 and ns["walks_per_9"] == 3.0
