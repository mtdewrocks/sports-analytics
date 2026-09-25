import pandas as pd

from build_odds_snapshots import closing_lines, new_snapshot_rows, prune

NOW = pd.Timestamp("2026-09-25T20:00:00Z")


def props(over=-110, under=-110, start="2026-09-25T23:00:00Z", fetched="2026-09-25T19:00:00+00:00",
          market="hits", book="fanduel"):
    return pd.DataFrame([{
        "Player": "A", "market": market, "Line": 1.5, "bookmakers": book,
        "Over Price": over, "Under Price": under, "commence_time": start,
        "home_team": "H", "away_team": "A", "event_id": "e1",
        "fetched_at": fetched, "alt_fetched_at": "2026-09-25T15:00:00+00:00",
    }])


def test_first_run_records_everything():
    out = new_snapshot_rows(props(), pd.DataFrame(), NOW.isoformat())
    assert len(out) == 1 and out.iloc[0]["observed_at"] == "2026-09-25T19:00:00+00:00"


def test_unchanged_price_adds_nothing_changed_price_adds_row():
    first = new_snapshot_rows(props(), pd.DataFrame(), NOW.isoformat())
    same = new_snapshot_rows(props(fetched="2026-09-25T20:00:00+00:00"), first, NOW.isoformat())
    assert same.empty
    moved = new_snapshot_rows(props(over=-120, fetched="2026-09-25T20:00:00+00:00"), first, NOW.isoformat())
    assert len(moved) == 1 and moved.iloc[0]["Over Price"] == -120


def test_alt_markets_use_alt_timestamp():
    out = new_snapshot_rows(props(market="hits_alternate"), pd.DataFrame(), NOW.isoformat())
    assert out.iloc[0]["observed_at"] == "2026-09-25T15:00:00+00:00"


def test_closing_line_uses_last_pre_start_props_price():
    started = props(start="2026-09-25T19:30:00Z", fetched="2026-09-25T19:00:00+00:00", over=-125)
    closes = closing_lines(started, pd.DataFrame(), pd.DataFrame(), NOW, NOW.isoformat())
    assert len(closes) == 1
    c = closes.iloc[0]
    assert c["Over Price"] == -125 and c["minutes_before_start"] == 30
    # Final once recorded: a later call doesn't duplicate or change it.
    again = closing_lines(started.assign(**{"Over Price": -200}), pd.DataFrame(), closes, NOW, NOW.isoformat())
    assert len(again) == 1 and again.iloc[0]["Over Price"] == -125


def test_not_started_games_have_no_close():
    assert closing_lines(props(), pd.DataFrame(), pd.DataFrame(), NOW, NOW.isoformat()).empty


def test_prune_by_game_start():
    old = new_snapshot_rows(props(start="2026-08-01T00:00:00Z"), pd.DataFrame(), NOW.isoformat())
    new = new_snapshot_rows(props(), pd.DataFrame(), NOW.isoformat())
    kept = prune(pd.concat([old, new]), NOW, 21)
    assert len(kept) == 1
