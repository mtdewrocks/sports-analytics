from app.data.alt_value import build_ladders, score_rung


def row(line, odds, season, recent, player="Tarik Skubal", market="pitcher_strikeouts", live=False):
    return {"player": player, "market": market, "line": line, "team": "DET", "opponent": "vs CLE",
            "odds_by_book": odds, "season_sample": season, "recent_sample": recent,
            "season_pct": 0, "recent_pct": 0, "commence_time": "2026-09-26T23:00:00Z",
            "fetched_at": "2026-09-25T12:00:00+00:00", "is_live": live}


LADDER = [
    row(3.5, {"draftkings": -350, "fanduel": -380}, "27/30", "9/10"),
    row(4.5, {"draftkings": -150, "fanduel": -160}, "22/30", "8/10"),
    row(5.5, {"betmgm": 130, "fanduel": 115}, "17/30", "6/10"),
    row(6.5, {"fanduel": 210}, "10/30", "3/10"),
    row(7.5, {"caesars": 380}, "5/30", "1/10"),
]


def test_best_rung_is_highest_ev_among_flagged():
    out = build_ladders(LADDER, min_ev=3.0, min_games=10)
    assert len(out) == 1
    lad = out[0]
    best = [r for r in lad["rungs"] if r["is_best"]]
    assert len(best) == 1 and best[0]["line"] == lad["best_line"]
    assert best[0]["ev_pct"] == max(r["ev_pct"] for r in lad["rungs"] if r["flagged"])
    assert [r["line"] for r in lad["rungs"]] == [3.5, 4.5, 5.5, 6.5, 7.5]


def test_dfs_books_ignored_for_best_price():
    r = score_rung(row(5.5, {"prizepicks": 300, "betmgm": 130}, "17/30", "6/10"))
    assert (r["best_book"], r["best_price"]) == ("betmgm", 130)
    assert score_rung(row(5.5, {"underdog": 300}, "17/30", "6/10")) is None


def test_small_sample_never_flags():
    out = build_ladders([row(5.5, {"betmgm": 130}, "2/2", "2/2"),
                         row(6.5, {"betmgm": 230}, "2/2", "2/2")], min_games=4)
    assert out == []
    allv = build_ladders([row(5.5, {"betmgm": 130}, "2/2", "2/2"),
                          row(6.5, {"betmgm": 230}, "2/2", "2/2")], min_games=4, flagged_only=False)
    assert allv and not allv[0]["enough_games"] and allv[0]["best_line"] is None


def test_extreme_longshot_not_flagged():
    out = build_ladders([row(0.5, {"fanduel": -150}, "45/84", "5/10", market="batter_hits"),
                         row(3.5, {"fanduel": 22500}, "1/84", "1/10", market="batter_hits")],
                        min_games=10)
    assert out == []


def test_live_and_yes_no_rows_skipped():
    rows = [row(5.5, {"betmgm": 130}, "17/30", "6/10", live=True),
            row("Yes", {"betmgm": 130}, "17/30", "6/10", market="pitcher_record_a_win")]
    assert build_ladders(rows, flagged_only=False, min_rungs=1) == []


def test_core_range_is_minus_400_to_plus_600():
    rows = [row(0.5, {"fanatics": -8000}, "29/30", "10/10"),
            row(1.5, {"fanatics": -1400}, "27/30", "10/10"),
            row(2.5, {"betmgm": -400}, "25/30", "8/10"),
            row(3.5, {"espnbet": -220}, "23/30", "7/10"),
            row(4.5, {"fanduel": 128}, "18/30", "6/10"),
            row(6.5, {"fanduel": 600}, "11/30", "5/10"),
            row(8.5, {"espnbet": 2000}, "2/30", "1/10")]
    out = build_ladders(rows, min_games=10, rung_range="core", flagged_only=False)
    assert [r["line"] for r in out[0]["rungs"]] == [2.5, 3.5, 4.5, 6.5]
    assert len(build_ladders(rows, min_games=10, rung_range="all", flagged_only=False)[0]["rungs"]) == 7


def test_context_fn_attached_and_favorable_filter():
    rows = [row(4.5, {"fanduel": 128}, "18/30", "6/10"), row(5.5, {"espnbet": 240}, "14/30", "6/10")]
    out = build_ladders(rows, min_games=10, context_fn=lambda l: {"verdict": "tough"})
    assert out[0]["matchup"] == {"verdict": "tough"}
    assert build_ladders(rows, min_games=10, context_fn=lambda l: {"verdict": "tough"},
                         favorable_only=True) == []


def test_absurd_ev_rung_is_marked_and_never_best():
    rows = [row(4.5, {"fanduel": 128}, "18/30", "6/10"),
            row(5.5, {"espnbet": 500}, "20/30", "7/10")]
    out = build_ladders(rows, min_games=10, flagged_only=False)
    r55 = [r for r in out[0]["rungs"] if r["line"] == 5.5][0]
    assert r55["suspicious"] and not r55["is_best"] and not r55["flagged"]
