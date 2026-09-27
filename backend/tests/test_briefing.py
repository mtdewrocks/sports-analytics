import pandas as pd

from app.data.briefing import starters_from_snaps, trench_groups, usage_trends, weather_note


def test_weather_note_nfl_tiers():
    assert weather_note("nfl", 6, 10, 60) is None
    moderate = weather_note("nfl", 10, 30, 64)
    assert moderate["tag"] == "WIND" and moderate["tone"] == "warn" and "Moderate wind" in moderate["why"]
    strong = weather_note("nfl", 16, 0, 60)
    assert strong["tone"] == "warn" and "Strong wind" in strong["why"]
    assert weather_note("nfl", 3, 50, 60)["tag"] == "RAIN"
    assert weather_note("nfl", 3, 0, 25)["tag"] == "COLD"


def test_weather_note_mlb_uses_wind_effect():
    n = weather_note("mlb", 12, 0, 70, "Wind blowing out to center field.")
    assert n["tone"] == "warn" and n["why"].startswith("Wind blowing out")
    assert weather_note("mlb", 5, 0, 70) is None
    assert "delay" in weather_note("mlb", 0, 50, 70)["why"]


def _usage(rows):
    return pd.DataFrame(rows, columns=["season", "week", "posteam", "player_id", "player", "targets", "carries"])


def test_usage_trends_flags_a_real_change_only():
    rows = []
    for wk, (a, b) in enumerate([(2, 8), (9, 1)], start=1):   # A's share jumps in week 2
        rows += [(2026, wk, "MIN", "a", "A.Guy", a, 0), (2026, wk, "MIN", "b", "B.Guy", b, 0),
                 (2026, wk, "MIN", "c", "C.Guy", 5, 0)]
    out = usage_trends(_usage(rows), {"MIN"}, {"a": "Alpha Guy"}, {"a": "WR", "b": "WR", "c": "TE"})
    titles = [o["title"] for o in out]
    assert any(t.startswith("Alpha Guy (MIN WR) target share 13%") for t in titles)
    assert not any("C.Guy" in t for t in titles)          # steady share: no alert
    assert {o["tag"] for o in out} == {"UP", "DOWN"}


def test_usage_trends_skips_player_who_missed_recent_game():
    rows = [(2026, 1, "MIN", "a", "A", 8, 0), (2026, 1, "MIN", "b", "B", 2, 0),
            (2026, 2, "MIN", "b", "B", 10, 0)]
    out = usage_trends(_usage(rows), {"MIN"}, {}, {"a": "WR", "b": "WR"})
    assert all(not o["title"].startswith("A ") for o in out)


def _snaps(rows):
    return pd.DataFrame(rows, columns=["season", "week", "team", "player", "position", "offense_pct", "defense_pct"])


def test_starters_from_snaps_uses_games_played():
    rows = [(2026, 1, "NYG", "Big Tackle", "T", 1.0, 0), (2026, 2, "NYG", "Big Tackle", "T", 0.95, 0),
            (2026, 1, "NYG", "Backup Guard", "G", 0.10, 0), (2026, 2, "NYG", "Backup Guard", "G", 0.20, 0),
            (2026, 1, "NYG", "Top Corner", "CB", 0, 0.98),                 # hurt, missed week 2
            (2026, 2, "NYG", "Slot WR", "WR", 0.8, 0)]
    st = starters_from_snaps(_snaps(rows))
    assert ("NYG", "big tackle") in st and ("NYG", "top corner") in st
    assert ("NYG", "backup guard") not in st and ("NYG", "slot wr") not in st


def test_trench_groups_counts_starters_only():
    starters = {("NYG", "big tackle"): {}, ("NYG", "top corner"): {}, ("NYG", "nickel back"): {}}
    inj = pd.DataFrame([
        ("Big Tackle", "OT", "Out", "NYG"), ("Backup Guard", "G", "Out", "NYG"),
        ("Top Corner", "CB", "Questionable", "NYG"),
    ], columns=["player", "position", "status", "abbr"])
    groups = trench_groups(inj, "NYG", starters)
    assert [g["unit"] for g in groups] == ["oline"]        # one Q corner alone isn't a group
    assert groups[0]["out"] == ["Big Tackle (OT)"]
    inj.loc[len(inj)] = ("Nickel Back", "CB", "Questionable", "NYG")
    assert [g["unit"] for g in trench_groups(inj, "NYG", starters)] == ["oline", "secondary"]
