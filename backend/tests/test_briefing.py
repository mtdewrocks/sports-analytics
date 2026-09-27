import pandas as pd

from app.data.briefing import usage_trends, weather_note


def test_weather_note_nfl_tiers():
    assert weather_note("nfl", 6, 10, 60) is None
    light = weather_note("nfl", 10, 30, 64)
    assert light["tag"] == "WIND" and light["tone"] == "neutral" and "Light wind" in light["why"]
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
