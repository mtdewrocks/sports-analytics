import pandas as pd
import pytest

import app.data.mlb_context as ctx

GAME = "2026-09-26T23:05:00Z"


def lineup_row(player, order, bats="R", throws="R", k=22.0, woba=0.320, pk=22.0, pw=0.320,
               pitcher="Tarik Skubal", team="Cleveland Guardians", pall_k=30.0):
    return {"player": player, "batting_order": order, "bats": bats, "throws": throws,
            "split_k_pct": k, "split_woba": woba, "p_split_k_pct": pk, "p_split_woba": pw,
            "p_all_k_pct": pall_k, "pitcher": pitcher, "team": team, "game_time_utc": GAME}


@pytest.fixture
def data(monkeypatch):
    def _set(rows):
        splits = pd.DataFrame([
            {"split": "vs L", "tbf": 1000, "woba": 0.320, "k_pct": 22.0},
            {"split": "vs R", "tbf": 1000, "woba": 0.320, "k_pct": 22.0},
        ])
        monkeypatch.setattr(ctx, "get_mlb_data",
                            lambda: {"matchups": pd.DataFrame(rows), "pitcher_splits": splits})
        ctx._tables.cache_clear()
    return _set


def test_high_k_lineup_is_favorable_for_pitcher_strikeouts(data):
    data([lineup_row(f"H{i}", i, k=26.0) for i in range(1, 10)])
    c = ctx.mlb_ladder_context({"player": "Tarik Skubal", "market": "pitcher_strikeouts", "commence_time": GAME})
    assert c["status"] == "ok" and c["verdict"] == "favorable"
    assert any("26.0%" in f for f in c["facts"])


def test_low_woba_lineup_favors_outs_over(data):
    data([lineup_row(f"H{i}", i, woba=0.280) for i in range(1, 10)])
    c = ctx.mlb_ladder_context({"player": "Tarik Skubal", "market": "pitcher_outs", "commence_time": GAME})
    assert c["verdict"] == "favorable"
    hits = ctx.mlb_ladder_context({"player": "Tarik Skubal", "market": "pitcher_hits_allowed", "commence_time": GAME})
    assert hits["verdict"] == "tough"


def test_batter_context_and_batting_order(data):
    data([lineup_row("José Ramírez", 3, woba=0.380, pw=0.360)])
    c = ctx.mlb_ladder_context({"player": "Jose Ramirez", "market": "batter_total_bases", "commence_time": GAME})
    assert c["verdict"] == "favorable" and c["batting_order"] == 3
    assert c["facts"][0] == "Batting 3rd"
    assert any(".380" in f for f in c["facts"])


def test_other_game_or_no_lineup(data):
    data([lineup_row("José Ramírez", 3)])
    later = ctx.mlb_ladder_context({"player": "Jose Ramirez", "market": "batter_hits",
                                    "commence_time": "2026-09-28T23:05:00Z"})
    assert later["status"] == "no_lineup"
    nobody = ctx.mlb_ladder_context({"player": "Nobody", "market": "batter_hits", "commence_time": GAME})
    assert nobody["status"] == "no_lineup" and nobody["verdict"] is None


def test_neutral_when_close_to_league(data):
    data([lineup_row(f"H{i}", i, k=22.5) for i in range(1, 10)])
    c = ctx.mlb_ladder_context({"player": "Tarik Skubal", "market": "pitcher_strikeouts", "commence_time": GAME})
    assert c["verdict"] == "neutral"
