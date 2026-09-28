import pandas as pd

from app.data.nfl_efficiency import fmt, rank_table
from app.get_nfl_team_efficiency import side_stats


def _pbp():
    rows = []
    # One game, two drives for KC on offense vs LV.
    base = dict(season=2026, season_type="REG", week=1, game_id="g1", posteam="KC", defteam="LV",
                qb_kneel=0, qb_spike=0, cpoe=None, qtr=1, wp=0.5, pass_oe=0.0, penalty=0, penalty_team=None,
                penalty_yards=0, third_down_converted=0, third_down_failed=0)
    # drive 1: pass 25 yds, run 3, TD (7 pts); drive 2: three-and-out punt
    plays = [
        (1, 1, 10, 75, 1, 0, 25, 1.2, 1, "Touchdown", 2, 3, 0, 7, 3600),
        (1, 2, 10, 50, 0, 1, 3, 0.1, 1, "Touchdown", 2, 3, 0, 7, 3570),
        (1, 1, 10, 47, 0, 1, 47, 4.0, 1, "Touchdown", 2, 3, 0, 7, 3540),
        (2, 1, 10, 80, 0, 1, 0, -0.6, 0, "Punt", 0, 3, 7, 7, 3000),
        (2, 2, 10, 80, 1, 0, 2, -0.4, 0, "Punt", 0, 3, 7, 7, 2970),
        (2, 3, 8, 78, 1, 0, 0, -1.5, 0, "Punt", 0, 3, 7, 7, 2940),
    ]
    for drive, down, togo, yl, dropback, rush, yds, epa, succ, res, fd, n, s0, s1, gsr in plays:
        rows.append({**base, "drive": drive, "fixed_drive": drive, "down": down, "ydstogo": togo,
                     "yardline_100": yl, "qb_dropback": dropback, "rush_attempt": rush, "pass_attempt": dropback,
                     "pass": dropback, "sack": 0, "yards_gained": yds, "epa": epa, "success": succ,
                     "fixed_drive_result": res, "drive_first_downs": fd, "drive_play_count": n,
                     "posteam_score": s0, "posteam_score_post": s1, "game_seconds_remaining": gsr,
                     "third_down_failed": 1 if down == 3 else 0, "play_type": "pass" if dropback else "run"})
    return pd.DataFrame(rows)


def test_side_stats_drives_and_rates():
    s = side_stats(_pbp(), "posteam", "KC", {"g1"})
    assert s["points_per_drive"] == 3.5                 # 7 and 0
    assert s["three_and_out_rate"] == 0.5 and s["td_rate"] == 0.5
    assert abs(s["explosive_rate"] - 2 / 6) < 1e-9       # 25-yd pass, 47-yd run
    assert s["third_down_rate"] == 0.0
    assert s["start_yardline"] == 100 - (75 + 80) / 2   # own 22.5
    d = side_stats(_pbp(), "defteam", "LV", {"g1"})
    assert d["points_per_drive"] == 3.5                  # the defense side sees the same drives


def test_rank_direction_offense_vs_defense_and_pace():
    df = pd.DataFrame([
        {"window": "season", "side": "off", "stat": "epa_per_play", "team": "A", "value": 0.2},
        {"window": "season", "side": "off", "stat": "epa_per_play", "team": "B", "value": -0.1},
        {"window": "season", "side": "def", "stat": "epa_per_play", "team": "A", "value": 0.2},
        {"window": "season", "side": "def", "stat": "epa_per_play", "team": "B", "value": -0.1},
        {"window": "season", "side": "off", "stat": "sack_rate", "team": "A", "value": 0.09},
        {"window": "season", "side": "off", "stat": "sack_rate", "team": "B", "value": 0.04},
        {"window": "season", "side": "off", "stat": "plays_per_game", "team": "A", "value": 70},
        {"window": "season", "side": "off", "stat": "plays_per_game", "team": "B", "value": 55},
    ])
    r = rank_table(df).set_index(["side", "stat", "team"])["rank"]
    assert r[("off", "epa_per_play", "A")] == 1          # high EPA is good on offense
    assert r[("def", "epa_per_play", "B")] == 1          # low EPA allowed is good on defense
    assert r[("off", "sack_rate", "B")] == 1             # fewer sacks is good on offense
    assert r[("off", "plays_per_game", "A")] == 1        # pace: 1st = most


def test_fmt():
    assert fmt("success_rate", 0.4267) == "43%"
    assert fmt("epa_per_play", -0.0659) == "-0.07" and fmt("epa_per_play", -0.001) == "0.00"
    assert fmt("start_yardline", 30.7) == "own 31"
    assert fmt("proe", -0.018) == "-1.8%"
