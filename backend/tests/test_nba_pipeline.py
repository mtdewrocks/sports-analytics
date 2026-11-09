"""get_nba_data.py: box score transform, rest flags, ESPN scoreboard parsing."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import get_nba_data as g  # noqa: E402


def _box_row(**kw):
    row = {
        "game_id": 1, "season": 2027, "season_type": 2, "game_date": "2026-10-28",
        "athlete_id": 10.0, "athlete_display_name": "Test Guard", "team_abbreviation": "GS",
        "opponent_team_abbreviation": "NY", "home_away": "home", "team_winner": True,
        "minutes": 34.0, "did_not_play": False, "starter": True,
        "points": 25, "field_goals_made": 9, "field_goals_attempted": 18,
        "three_point_field_goals_made": 3, "three_point_field_goals_attempted": 8,
        "free_throws_made": 4, "free_throws_attempted": 5, "offensive_rebounds": 1,
        "defensive_rebounds": 9, "rebounds": 10, "assists": 6, "steals": 1, "blocks": 0,
        "turnovers": 3, "fouls": 2, "plus_minus": 7,
    }
    row.update(kw)
    return row


def test_transform_matches_old_columns():
    raw = pd.DataFrame([
        _box_row(),
        _box_row(athlete_id=11.0, athlete_display_name="Bench Guy", minutes=None, did_not_play=True),
        _box_row(athlete_id=12.0, team_abbreviation="STARS", opponent_team_abbreviation="WORLD"),
        _box_row(athlete_id=13.0, season_type=1),                       # preseason
    ])
    out = g.transform_box(raw)
    assert len(out) == 1
    r = out.iloc[0]
    assert (r["TEAM"], r["Opponent"], r["MATCH UP"], r["Location"]) == ("GSW", "NYK", "GSW vs. NYK", "Home")
    assert r["FP"] == 25 + 12 + 9 + 3 - 3 and r["DblDbl"] == 1 and r["PRA"] == 41
    assert r["GameID"] == "GSW_2026-10-28" and r["Season"] == 2027 and r["Played"] == 1


def test_rest_flags_by_team_and_season():
    raw = pd.DataFrame([_box_row(game_date=d) for d in ("2026-10-28", "2026-10-29", "2026-10-31")]
                       + [_box_row(game_date="2026-04-12", season=2026)])
    out = g.add_schedule_flags(g.transform_box(raw)).set_index("Date")
    assert out.loc["2026-10-29", "back_to_back"] == 1
    assert out.loc["2026-10-31", "back_to_back"] == 0 and out.loc["2026-10-31", "third_in_four"] == 1
    assert out.loc["2026-10-28", "back_to_back"] == 0      # previous season's game doesn't count


def test_parse_scoreboard():
    doc = {"events": [
        {"id": "401", "date": "2026-10-31T00:00Z", "season": {"year": 2027, "type": 2},
         "competitions": [{"status": {"type": {"state": "pre", "shortDetail": "10/30 - 7:00 PM EDT"}},
                           "venue": {"fullName": "Madison Square Garden"},
                           "broadcasts": [{"names": ["ESPN"]}],
                           "competitors": [
                               {"homeAway": "home", "score": "0", "team": {"abbreviation": "NY"}},
                               {"homeAway": "away", "score": "0", "team": {"abbreviation": "SA"}}]}]},
        {"id": "402", "date": "2026-10-31T01:00Z", "season": {"year": 2027, "type": 2},
         "competitions": [{"competitors": [
             {"homeAway": "home", "team": {"abbreviation": "STARS"}},
             {"homeAway": "away", "team": {"abbreviation": "WORLD"}}]}]},
    ]}
    rows = g.parse_scoreboard(doc)
    assert len(rows) == 1
    r = rows[0]
    assert (r["home"], r["away"], r["date"], r["state"]) == ("NYK", "SAS", "2026-10-30", "pre")
    assert r["home_score"] is None and r["broadcast"] == "ESPN"


def test_season_for():
    from datetime import date
    assert g.season_for(date(2026, 10, 30)) == 2027
    assert g.season_for(date(2027, 4, 1)) == 2027
