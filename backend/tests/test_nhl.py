"""NHL pipeline + page payloads, driven by synthetic games (tests/nhl_fixture.py).

The live NHL API isn't reachable from CI, so these check the LOGIC -- that
shift charts become the right lines and power-play units, that the pipeline
round-trips through parquet, and that every page payload builds and is JSON-
serialisable -- plus the parsers against hand-written documents in the
API's shape. `python backend/app/get_nhl_data.py --smoke <game_id>` is the
check against the real thing.
"""

import io
import json
from pathlib import Path

import pandas as pd
import pytest

import nhl_api
from tests.nhl_fixture import make_game, make_league
from nhl_processing import process_game, zone_for


# ── processing ─────────────────────────────────────────────────────────────

def test_process_recovers_lines_pairs_and_pp_units():
    g, b, p, s, truth = make_game()
    out = process_game(g, b, p, s)
    units = {(u["team"], u["unit"]): set(int(x) for x in u["players_key"].split("-")) for u in out["units"]}
    for side, team in (("H", "CAR"), ("A", "FLA")):
        T = truth[side]
        for i, line in enumerate(T["lines"]):
            assert units[(team, f"L{i + 1}")] == set(line)
        for i, pair in enumerate(T["pairs"]):
            assert units[(team, f"D{i + 1}")] == set(pair)
    assert units[("CAR", "PP1")] == set(truth["H"]["pp1"])
    assert units[("CAR", "PP2")] == set(truth["H"]["pp2"])
    teams = {t["team"]: t for t in out["teams"]}
    assert teams["CAR"]["pp_opps"] == 2 and teams["FLA"]["pp_opps"] == 1
    assert teams["CAR"]["sec_pp"] == 240 and teams["CAR"]["sec_sh"] == 120
    assert teams["CAR"]["goals_for"] == truth["score"]["CAR"]
    sk = {r["player_id"]: r for r in out["skaters"]}
    assert sk[1000]["pp_unit"] == "PP1" and sk[1000]["line"] == "L1"
    assert sk[1000]["pp_toi"] == 140
    assert sk[1000]["linemates"] and "1001" in sk[1000]["linemates"]


def test_shots_are_flipped_to_attack_positive_x():
    g, b, p, s, _ = make_game()
    out = process_game(g, b, p, s)
    xs = [sh["x"] for sh in out["shots"]]
    assert xs and min(xs) >= 40          # fixture shots are all 40-85 ft toward the net


def test_zone_for():
    assert zone_for(85, 0) == "net_front"
    assert zone_for(72, 3) == "slot"
    assert zone_for(60, -4) == "high_slot"
    assert zone_for(70, 20) == "left_circle" and zone_for(70, -20) == "right_circle"
    assert zone_for(35, 10) == "left_point" and zone_for(35, -10) == "right_point"
    assert zone_for(95, 5) == "wide"


def test_process_without_shift_charts_still_counts_the_game():
    g, b, p, _, _ = make_game()
    out = process_game(g, b, p, [])
    assert out["units"] == [] and len(out["teams"]) == 2
    assert all(r["pp_toi"] is None for r in out["skaters"])
    assert not out["teams"][0]["has_shifts"]


# ── parsers (documents in the live API's shape) ────────────────────────────

BOX = {
    "id": 2025020001, "season": 20252026, "gameType": 2,
    "awayTeam": {"abbrev": "FLA", "score": 2}, "homeTeam": {"abbrev": "CAR", "score": 3},
    "playerByGameStats": {
        "awayTeam": {"forwards": [{"playerId": 8478403, "name": {"default": "S. Reinhart"}, "position": "C",
                                   "goals": 1, "assists": 0, "sog": 4, "hits": 1, "blockedShots": 0, "pim": 0,
                                   "powerPlayGoals": 1, "toi": "19:42", "shifts": 22}],
                     "defense": [], "goalies": [
                         {"playerId": 8475683, "name": {"default": "S. Bobrovsky"}, "toi": "58:40",
                          "starter": True, "decision": "L", "saveShotsAgainst": "27/30", "goalsAgainst": 3},
                         {"playerId": 1, "name": {"default": "Backup"}, "toi": "00:00", "starter": False}]},
        "homeTeam": {"forwards": [], "defense": [], "goalies": []},
    },
}


def test_parse_boxscore():
    out = nhl_api.parse_boxscore(BOX)
    assert out["away"] == "FLA" and out["home"] == "CAR"
    sk = out["skaters"][0]
    assert sk["toi"] == 1182 and sk["sog"] == 4 and sk["pp_goals"] == 1
    gb = out["goalies"][0]
    assert gb["saves"] == 27 and gb["shots_against"] == 30 and gb["starter"]


def test_parse_pbp_and_shifts():
    pbp = {"gameType": 2, "homeTeam": {"id": 12, "abbrev": "CAR"}, "awayTeam": {"id": 13, "abbrev": "FLA"},
           "rosterSpots": [{"playerId": 5, "teamId": 12, "firstName": {"default": "Seb"},
                            "lastName": {"default": "Aho"}, "positionCode": "C"}],
           "plays": [
               {"typeDescKey": "shot-on-goal", "periodDescriptor": {"number": 2, "periodType": "REG"},
                "timeInPeriod": "05:10", "situationCode": "1551", "sortOrder": 10, "homeTeamDefendingSide": "right",
                "details": {"xCoord": -70, "yCoord": 5, "shootingPlayerId": 5, "eventOwnerTeamId": 12}},
               {"typeDescKey": "goal", "periodDescriptor": {"number": 5, "periodType": "SO"},
                "timeInPeriod": "00:00", "details": {}},
           ]}
    out = nhl_api.parse_pbp(pbp)
    assert out["roster"][5] == {"name": "Seb Aho", "team": "CAR", "pos": "C"}
    assert len(out["events"]) == 1            # shootout dropped
    e = out["events"][0]
    assert e["sec"] == 1200 + 310 and e["owner"] == "CAR" and e["situation"] == "1551"
    sh = nhl_api.parse_shifts([
        {"playerId": 5, "teamAbbrev": "CAR", "period": 1, "startTime": "00:00", "endTime": "00:45",
         "duration": "00:45", "typeCode": 517},
        {"playerId": 5, "teamAbbrev": "CAR", "period": 1, "startTime": "10:00", "endTime": "10:00",
         "duration": None, "typeCode": 505},
    ])
    assert sh == [{"player_id": 5, "team": "CAR", "start": 0, "end": 45}]


def test_parse_schedule_and_roster():
    g = nhl_api.parse_schedule_game({"id": 2026020001, "season": 20262027, "gameType": 2,
                                     "gameDate": "2026-09-29", "startTimeUTC": "2026-09-29T21:00:00Z",
                                     "awayTeam": {"abbrev": "FLA"}, "homeTeam": {"abbrev": "CAR"},
                                     "gameState": "FUT", "venue": {"default": "Lenovo Center"}})
    assert g["away"] == "FLA" and g["state"] == "FUT" and g["venue"] == "Lenovo Center"
    ro = nhl_api.parse_roster("CAR", {"goalies": [{"id": 9, "firstName": {"default": "P"},
                                                   "lastName": {"default": "K"}, "positionCode": "G"}]})
    assert ro == [{"player_id": 9, "player": "P K", "team": "CAR", "pos": "G"}]
    assert nhl_api.season_for(pd.Timestamp("2026-09-29").date()) == 20262027
    assert nhl_api.season_for(pd.Timestamp("2027-04-01").date()) == 20262027


# ── pipeline -> files -> pages ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def league_dir(tmp_path_factory):
    import get_nhl_data as pipe
    out = tmp_path_factory.mktemp("nhl")
    rows, games = make_league("2026-11-10")
    by_team = {}
    for r in rows:
        for t in (r["home"], r["away"]):
            by_team.setdefault((t, r["season"]), []).append(r)

    mp = pytest.MonkeyPatch()
    mp.setattr(pipe, "OUT", out)
    mp.setattr(pipe, "TEAMS", {"CAR": 1, "FLA": 1, "NYR": 1, "BOS": 1})
    mp.setattr(pipe, "today_central", lambda: pd.Timestamp("2026-11-10").date())
    mp.setattr(pipe.nhl_api, "fetch_club_schedule", lambda t, s: by_team.get((t, s), []))
    mp.setattr(pipe, "fetch_game", lambda g: process_game(*games[int(g["game_id"])]))
    roster_doc = lambda team: {"goalies": [{"id": base + 30 + i, "firstName": {"default": team},
                                            "lastName": {"default": f"Goalie {base + 30 + i}"}}
                                           for i in range(2)]} if (base := {"CAR": 1000, "FLA": 2000, "NYR": 3000,
                                                                            "BOS": 4000}[team]) else {}
    mp.setattr(pipe.nhl_api, "fetch_roster", roster_doc)
    mp.setattr("sys.argv", ["get_nhl_data.py"])
    assert pipe.main() == 0
    # second run is incremental: nothing new to do, files unchanged in size
    n1 = len(pd.read_parquet(out / "nhl_team_games.parquet"))
    assert pipe.main() == 0
    assert len(pd.read_parquet(out / "nhl_team_games.parquet")) == n1
    mp.undo()
    return out


def test_pipeline_outputs(league_dir):
    tg = pd.read_parquet(league_dir / "nhl_team_games.parquet")
    assert {"xgf", "xga", "xgf5", "xga5", "b2b", "rest_days"} <= set(tg.columns)
    assert tg["b2b"].any()
    gg = pd.read_parquet(league_dir / "nhl_goalie_games.parquet")
    assert {"gsax", "xga", "is_no1"} <= set(gg.columns)
    sk = pd.read_parquet(league_dir / "nhl_skater_games.parquet")
    assert {"ixg", "opp_goalie_backup", "pp_unit", "line"} <= set(sk.columns)
    meta = json.loads((league_dir / "nhl_meta.json").read_text())
    assert meta["total_games"] == tg["game_id"].nunique()


@pytest.fixture(scope="module")
def pages(league_dir):
    from app.data import loader, nhl
    mp = pytest.MonkeyPatch()
    base = loader.settings.NHL_BASE_URL
    real = loader._fetch_bytes

    def fake_fetch(url):
        if url.startswith(base):
            p = Path(league_dir) / url.rsplit("/", 1)[-1]
            if not p.exists():
                raise FileNotFoundError(p)
            return p.read_bytes()
        return real(url)
    mp.setattr(loader, "_fetch_bytes", fake_fetch)
    mp.setattr(nhl, "get_injuries_data", lambda s: pd.DataFrame([
        {"player": "Hurt Guy", "team": "Carolina Hurricanes", "position": "C", "status": "Out", "detail": "Knee"}]))
    mp.setattr(nhl, "today_ct", lambda: pd.Timestamp("2026-11-10").date())
    for name in dir(loader):
        if name.startswith("get_nhl_"):
            getattr(loader, name).cache_clear()
    nhl.clear_cache()
    yield nhl
    nhl.clear_cache()
    mp.undo()


def _json(x):
    return json.loads(json.dumps(x, allow_nan=False))   # what Starlette does: numpy/NaN would 500


def test_players_and_game_log(pages):
    ps = _json(pages.players())
    assert any(p["is_goalie"] for p in ps) and any(not p["is_goalie"] for p in ps)
    log = _json(pages.game_log(1000, "sog", 0.5))
    assert not log.get("error"), log
    assert log["season"] == 20262027 and not log["fallback"]
    assert log["games"] and {"last5", "last10", "last20", "season", "pp1"} <= set(log["over_counts"])
    assert log["splits"] and log["next_game"]["opp_goalie"]["status"] in ("Projected", "Confirmed")
    filt = _json(pages.game_log(1000, "sog", 0.5, pp_role="not_pp1"))
    assert len(filt["games"]) <= len(log["games"])
    glog = _json(pages.game_log(1030, "saves", 20.5))
    assert glog["player"]["is_goalie"] and glog["games"][0]["saves"] is not None
    last_season = _json(pages.game_log(1000, "points", 0.5, season=20252026))
    assert last_season["season"] == 20252026


def test_matchup_goalies_spots_lines_deep_dive(pages):
    sl = _json(pages.slate())
    assert sl["date"] == "2026-11-10" and sl["games"]
    gid = sl["games"][0]["game_id"]
    m = _json(pages.matchup(gid))
    assert m["sections"] and m["away"]["goalie"]["status"] == "Projected"
    assert any(i["player"] == "Hurt Guy" for i in m["home"]["injuries"] + m["away"]["injuries"])
    gr = _json(pages.goalie_report())
    assert gr["games"] and all(len(g["goalies"]) == 2 for g in gr["games"])
    ss = _json(pages.schedule_spots())
    assert ss["rows"] and all("spot" in r for r in ss["rows"])
    ln = _json(pages.lines(gid))
    assert ln["teams"][0]["units"], ln
    assert {u["unit"] for u in ln["teams"][0]["units"]} >= {"L1", "L2", "D1"}
    ln2 = _json(pages.lines(gid, "common"))
    assert ln2["teams"][0]["units"]
    dd = _json(pages.deep_dive(gid, "away", "5v5"))
    assert len(dd["zones"]) == 8 and dd["quality"]["for"]["hd_share"] is not None
    assert _json(pages.deep_dive(gid, "home", "pp"))["strength"] == "pp"
