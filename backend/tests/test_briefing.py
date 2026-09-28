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
            (2026, 2, "NYG", "Slot WR", "WR", 0.45, 0),                # rotates, still a regular
            (2026, 1, "NYG", "QB One", "QB", 1.0, 0), (2026, 1, "NYG", "QB Three", "QB", 0.0, 0),
            (2026, 2, "NYG", "QB One", "QB", 0.97, 0), (2026, 2, "NYG", "QB Two", "QB", 0.03, 0)]
    st = starters_from_snaps(_snaps(rows))
    assert ("NYG", "big tackle") in st and ("NYG", "top corner") in st and ("NYG", "slot wr") in st
    assert ("NYG", "backup guard") not in st
    assert ("NYG", "qb one") in st and ("NYG", "qb two") not in st and ("NYG", "qb three") not in st


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


def _trend(player, tag, pos, mates):
    return {"kind": "usage", "tag": tag, "team": "PHI", "player": player, "title": player, "detail": "Week 2 vs week 1",
            "_ctx": {"base_w": [1], "recent_w": [2], "teammates": mates, "position": pos}}


def _snap_map(rows):
    out = {}
    for name, w, pct in rows:
        out[("PHI", name.lower(), w)] = pct
        out[("PHI", "*", w)] = 1.0
    return out


def test_usage_trends_explained_by_injury_are_dropped_or_noted():
    from app.data.briefing import adjust_for_injuries
    snaps = _snap_map([("saquon barkley", 1, .71), ("saquon barkley", 2, .16),
                    ("tank bigsby", 1, .11), ("tank bigsby", 2, .34),
                    ("dallas goedert", 1, .95), ("dallas goedert", 2, .25),
                    ("wr one", 1, .48), ("wr one", 2, .84), ("wr two", 1, .60), ("wr two", 2, .62)])
    items = [
        _trend("Saquon Barkley", "DOWN", "RB", [("Tank Bigsby", "RB")]),        # hurt, healthy now -> dropped
        _trend("Tank Bigsby", "UP", "RB", [("Saquon Barkley", "RB")]),          # filled in; Barkley back -> dropped
        _trend("Dallas Goedert", "DOWN", "TE", []),                              # Out now -> dropped
        _trend("WR Two", "DOWN", "WR", [("WR One", "WR")]),                     # teammate back -> kept with note
    ]
    out = adjust_for_injuries(items, snaps, {("PHI", "dallas goedert"): "Out"})
    assert [o["player"] for o in out] == ["WR Two"]
    assert "WR One back to full snaps (48% → 84%)" in out[0]["detail"]


def test_filled_in_role_kept_while_starter_still_out():
    from app.data.briefing import adjust_for_injuries
    snaps = _snap_map([("saquon barkley", 1, .71), ("saquon barkley", 2, 0.0),
                    ("tank bigsby", 1, .11), ("tank bigsby", 2, .60)])
    out = adjust_for_injuries([_trend("Tank Bigsby", "UP", "RB", [("Saquon Barkley", "RB")])], snaps,
                              {("PHI", "saquon barkley"): "Out"})
    assert out and "Saquon Barkley out, so the bigger role likely continues" in out[0]["detail"]
