import pandas as pd
import pytest

import app.data.ev as ev

FUTURE = (pd.Timestamp.now(tz="UTC") + pd.Timedelta(days=1)).isoformat()
PAST = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=1)).isoformat()


def _rows(prices, start=FUTURE, player="Jalen Brunson", line=26.5):
    return [{
        "Player": player, "market": "points", "Line": line, "bookmakers": b,
        "Over Price": o, "Under Price": u, "commence_time": start,
        "home_team": "NYK", "away_team": "BOS", "event_id": "e1",
        "fetched_at": "2026-09-25T12:00:00+00:00", "alt_fetched_at": None,
    } for b, o, u in prices]


@pytest.fixture
def patch(monkeypatch):
    def _set(rows, snaps=None):
        monkeypatch.setattr(ev, "get_props_data", lambda s: pd.DataFrame(rows))
        monkeypatch.setattr(ev, "get_odds_snapshots_data",
                            lambda s: snaps if snaps is not None else pd.DataFrame())
    return _set


def test_sharp_source_flags_soft_book(patch):
    patch(_rows([("pinnacle", -118, -102), ("fanduel", 112, -140), ("draftkings", -115, -105)]))
    out = ev.get_ev("nba", source="auto")
    assert len(out) == 1
    r = out[0]
    assert (r["book"], r["side"], r["price"], r["source"]) == ("fanduel", "over", 112, "sharp")
    assert r["ev_pct"] == pytest.approx(9.7, abs=0.1)
    # Pinnacle is a reference, never a bet.
    assert all(x["book"] != "pinnacle" for x in out)


def test_sharp_only_skips_lines_without_pinnacle(patch):
    patch(_rows([("fanduel", 112, -140), ("draftkings", -115, -105), ("betmgm", -118, -102)]))
    assert ev.get_ev("nba", source="sharp") == []


def test_consensus_is_leave_one_out(patch):
    # The -118 book must be judged against the OTHER books only.
    patch(_rows([("draftkings", -135, 115), ("fanduel", -132, 112), ("betmgm", -138, 115),
                 ("espnbet", -140, 118), ("fanatics", -118, -102)]))
    out = ev.get_ev("nba", source="consensus", min_edge=1.0)
    hit = [r for r in out if r["book"] == "fanatics" and r["side"] == "over"]
    assert hit, out
    assert hit[0]["consensus_books"] == 4
    assert hit[0]["median_price"] in (-135, -136, -137)
    assert 1.0 <= hit[0]["ev_pct"] <= 3.5


def test_breakeven_outlier_not_flagged(patch):
    # Case A: -118 looks like a discount vs -135 but is fair once the vig is out.
    patch(_rows([("draftkings", -135, 105), ("fanduel", -135, 105), ("betmgm", -135, 105),
                 ("fanatics", -118, None)]))
    assert ev.get_ev("nba", source="consensus", min_edge=1.0) == []


def test_min_books_and_dfs_and_live_excluded(patch):
    rows = _rows([("draftkings", -135, 115), ("prizepicks", 150, None), ("fanatics", -118, -102)])
    rows += _rows([("draftkings", -110, -110), ("fanduel", -110, -110), ("betmgm", 150, -200)],
                  start=PAST, player="Live Guy")
    patch(rows)
    out = ev.get_ev("nba", source="consensus", min_books=2)
    assert out == []  # only one other two-way book for Brunson; Live Guy has started
    assert all(r["book"] != "prizepicks" for r in ev.get_ev("nba", source="consensus", min_books=1))


def test_price_since_from_snapshots(patch):
    snaps = pd.DataFrame([{
        "event_id": "e1", "Player": "Jalen Brunson", "market": "points", "Line": 26.5,
        "bookmakers": "fanduel", "Over Price": 112, "Under Price": -140,
        "observed_at": "2026-09-25T11:40:00+00:00",
    }])
    patch(_rows([("pinnacle", -118, -102), ("fanduel", 112, -140)]), snaps)
    out = ev.get_ev("nba")
    assert out[0]["price_since"] == "2026-09-25T11:40:00+00:00"


def test_one_card_per_bet_with_other_books(patch):
    patch(_rows([("pinnacle", -108, -123), ("betmgm", -140, 110), ("draftkings", -135, 106),
                 ("fanduel", -130, -110)]))
    out = ev.get_ev("nba", source="auto")
    unders = [r for r in out if r["side"] == "under"]
    assert len(unders) == 1
    assert (unders[0]["book"], unders[0]["price"]) == ("betmgm", 110)
    assert [o["book"] for o in unders[0]["other_books"]] == ["draftkings"]
