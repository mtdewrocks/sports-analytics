import pandas as pd

from get_injuries import diff_statuses, merge_sources, normalize_status, parse_espn, parse_nflverse, player_key

ESPN = {"injuries": [{"displayName": "Carolina Panthers", "injuries": [
    {"status": "Out", "date": "2026-09-26T15:00Z", "shortComment": "hamstring",
     "athlete": {"displayName": "Chuba Hubbard", "position": {"abbreviation": "RB"}},
     "details": {"type": "Hamstring", "side": "Left"}},
    {"status": "Questionable", "athlete": {"displayName": "Tetairoa McMillan",
                                           "position": {"abbreviation": "WR"}}},
    {"athlete": {"displayName": "No Status Guy"}},
]}]}


def test_parse_espn_skips_incomplete_rows():
    rows = parse_espn(ESPN, "nfl")
    assert [r["player"] for r in rows] == ["Chuba Hubbard", "Tetairoa McMillan"]
    assert rows[0]["status"] == "Out" and rows[0]["detail"] == "Hamstring Left"
    assert parse_espn({}, "nfl") == [] and parse_espn({"injuries": [{}]}, "nfl") == []


def test_player_key_and_status():
    assert player_key("Kenneth Walker III") == player_key("kenneth walker")
    assert player_key("José Ramírez") == "jose ramirez"
    assert normalize_status("15-Day-IL") == "IL-15" and normalize_status("  ") is None


def test_nflverse_latest_week_only_and_merge():
    nv = pd.DataFrame([
        {"week": 2, "team": "CAR", "full_name": "Chuba Hubbard", "gsis_id": "00-1", "position": "RB",
         "report_status": "Questionable", "practice_status": "Limited"},
        {"week": 3, "team": "CAR", "full_name": "Chuba Hubbard", "gsis_id": "00-1", "position": "RB",
         "report_status": "Doubtful", "report_primary_injury": "Hamstring",
         "practice_status": "Did Not Participate In Practice"},
        {"week": 3, "team": "CAR", "full_name": "Healthy Guy", "gsis_id": "00-2",
         "report_status": None, "practice_status": "Full Participation in Practice"},
    ])
    rows = parse_nflverse(nv)
    assert len(rows) == 1 and rows[0]["team"] == "Carolina Panthers" and rows[0]["status"] == "Doubtful"
    merged = merge_sources(parse_espn(ESPN, "nfl"), rows)
    hub = merged[merged["player"] == "Chuba Hubbard"].iloc[0]
    assert hub["status"] == "Out" and hub["gsis_id"] == "00-1" and hub["practice"].startswith("Did Not")


def test_diff_logs_changes_new_and_cleared():
    prev = pd.DataFrame([
        {"sport": "nfl", "player": "A", "player_key": "a", "team": "T", "status": "Questionable"},
        {"sport": "nfl", "player": "B", "player_key": "b", "team": "T", "status": "Out"},
    ])
    cur = pd.DataFrame([
        {"sport": "nfl", "player": "A", "player_key": "a", "team": "T", "status": "Out"},
        {"sport": "nfl", "player": "C", "player_key": "c", "team": "T", "status": "Doubtful"},
    ])
    d = diff_statuses(prev, cur, "2026-09-26T12:00:00+00:00")
    got = {(r["player"], None if pd.isna(r["old_status"]) else r["old_status"], r["new_status"])
           for r in d.to_dict(orient="records")}
    assert got == {("A", "Questionable", "Out"), ("C", None, "Doubtful"), ("B", "Out", "Active")}


def test_redistribute_scales_shares_and_skips_qb_carries():
    from app.data.injuries import redistribute, is_meaningful
    inj = {"player_id": "x", "target_share": 0.20, "carry_share": 0.40}
    mates = [{"player_id": "a", "name": "A", "target_share": 0.24, "carry_share": 0.30, "position": "RB"},
             {"player_id": "q", "name": "Q", "target_share": 0.0, "carry_share": 0.20, "position": "QB"},
             {"player_id": "x", "name": "X", "target_share": 0.20, "carry_share": 0.40}]
    t = redistribute(inj, mates, "targets")
    assert t == [{"player": "A", "share": 24.0, "est_share": 30.0, "gain": 6.0}]
    c = redistribute(inj, mates, "carries")
    assert [b["player"] for b in c] == ["A"] and c[0]["est_share"] == 50.0
    assert is_meaningful("Questionable", "Out") and is_meaningful("Out", "Active")
    assert not is_meaningful(None, "Active") and not is_meaningful("Out", "Out")
