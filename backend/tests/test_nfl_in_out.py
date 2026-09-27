import pandas as pd

from app.data.nfl import in_out_split


def _anchor(rows):
    df = pd.DataFrame(rows, columns=["season", "week", "team", "targets"])
    return df.assign(_p="alec pierce")


def _snaps(rows):
    return pd.DataFrame(rows, columns=["season", "week", "team", "player"])


def test_prior_season_without_snap_data_is_not_counted_as_without():
    # The bug: 2025 box scores, 2026-only snaps -> every 2025 game read as "without".
    anchor = _anchor([(2025, 1, "IND", 5), (2025, 2, "IND", 6), (2026, 1, "IND", 6), (2026, 2, "IND", 1)])
    snaps = _snaps([(2026, 1, "IND", "Alec Pierce"), (2026, 1, "IND", "Josh Downs"),
                    (2026, 2, "IND", "Alec Pierce"), (2026, 2, "IND", "Josh Downs")])
    out = in_out_split(anchor, snaps, ["Josh Downs"])
    assert len(out["with"]) == 2 and len(out["without"]) == 0 and out["skipped"] == 2


def test_with_and_without_within_a_season():
    anchor = _anchor([(2025, 1, "IND", 5), (2025, 2, "IND", 9)])
    snaps = _snaps([(2025, 1, "IND", "Alec Pierce"), (2025, 1, "IND", "Josh Downs"),
                    (2025, 2, "IND", "Alec Pierce")])                  # Downs missed week 2
    out = in_out_split(anchor, snaps, ["Josh Downs"])
    assert list(out["with"]["week"]) == [1] and list(out["without"]["week"]) == [2]


def test_season_teammate_was_elsewhere_is_skipped():
    anchor = _anchor([(2026, 1, "IND", 5)])
    snaps = _snaps([(2026, 1, "IND", "Alec Pierce"), (2026, 1, "NYJ", "Old Teammate")])
    out = in_out_split(anchor, snaps, ["Old Teammate"])
    assert out["skipped"] == 1 and out["with"].empty and out["without"].empty
