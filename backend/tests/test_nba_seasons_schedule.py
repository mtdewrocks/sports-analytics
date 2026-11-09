"""NBA pages: current-season scoping, Game Log season picker, schedule/rest."""
from datetime import date

import pandas as pd

from app.data import nba


def _stats():
    rows = []
    for season, d, team, opp, pts in [
        (2026, "2026-04-10", "NYK", "BOS", 30), (2026, "2026-04-12", "NYK", "BOS", 20),
        (2027, "2026-11-08", "NYK", "MIL", 25), (2027, "2026-11-09", "NYK", "MIL", 35),
    ]:
        rows.append({"player": "Test Guard", "team": team, "opponent": opp, "game_date": pd.Timestamp(d),
                     "date": pd.Timestamp(d), "season": season, "pts": pts, "played": 1, "min": 34,
                     "location": "Home"})
        rows.append({"player": "Other Guy", "team": opp, "opponent": team, "game_date": pd.Timestamp(d),
                     "date": pd.Timestamp(d), "season": season, "pts": 10, "played": 1, "min": 30,
                     "location": "Away"})
    df = pd.DataFrame(rows)
    df["season"] = df["season"].astype("Int64")
    return df


def _patch(monkeypatch, stats, sched=None):
    monkeypatch.setattr(nba, "get_nba_all_seasons", lambda: stats)
    monkeypatch.setattr(nba, "get_nba_data", lambda: stats[stats["season"] == stats["season"].max()].reset_index(drop=True))
    if sched is not None:
        monkeypatch.setattr(nba, "get_nba_schedule", lambda: sched)


def test_game_log_season_scopes(monkeypatch):
    _patch(monkeypatch, _stats())
    cur = nba.get_game_log("Test Guard", "pts", 22, season="current")
    assert [g["stat_value"] for g in cur["games"]] == [25.0, 35.0]
    assert cur["games"][0]["season"] == "2026-27" and cur["games"][0]["home"] is True
    assert len(nba.get_game_log("Test Guard", "pts", 0, season="last")["games"]) == 2
    assert nba.get_game_log("Test Guard", "pts", 0, season="both")["over_counts"]["season"]["total"] == 4
    assert nba.get_game_log("Nobody", "pts", 0)["over_counts"]["season"]["total"] == 0


def test_seasons_labels(monkeypatch):
    _patch(monkeypatch, _stats())
    out = nba.get_seasons()
    assert out["current"] == 2027
    assert [o["scope"] for o in out["options"]] == ["current", "last", "both"]
    assert out["options"][1]["label"] == "Last season (2025-26)"


def test_schedule_defaults_to_next_game_day_and_rest(monkeypatch):
    sched = pd.DataFrame([
        {"espn_game_id": 1, "date": "2026-11-10", "start_utc": "2026-11-11T00:30:00+00:00", "state": "pre",
         "status": "7:30 PM", "home": "NYK", "away": "MIL", "home_score": None, "away_score": None,
         "broadcast": "MSG", "venue": "MSG"},
        {"espn_game_id": 2, "date": "2026-11-12", "start_utc": "2026-11-13T00:00:00+00:00", "state": "pre",
         "status": "7:00 PM", "home": "BOS", "away": "NYK", "home_score": None, "away_score": None,
         "broadcast": None, "venue": None},
    ])
    _patch(monkeypatch, _stats(), sched)
    monkeypatch.setattr(nba, "_today_et", lambda: date(2026, 11, 10))
    out = nba.get_schedule()
    assert out["date"] == "2026-11-10" and out["is_today"] and len(out["games"]) == 1
    g = out["games"][0]
    assert g["tip"] == "7:30 PM ET"
    assert g["home_rest"] == {"last_game": "2026-11-09", "days_rest": 0, "back_to_back": True}

    monkeypatch.setattr(nba, "_today_et", lambda: date(2026, 11, 11))   # no games -> next day
    assert nba.get_schedule()["date"] == "2026-11-12"
