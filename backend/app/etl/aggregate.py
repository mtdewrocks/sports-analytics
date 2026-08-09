"""Pitch-level Statcast -> daily component aggregates.

Design rule: **store numerators and denominators, never rates.** Counting stats
sum; rates do not. Because every column here is additive, any window the
dashboard wants -- season to date, last 30 days, vs LHP only, all of last
season -- is a SUM over rows, and a revised game only rewrites one day.

Grain: one row per (player_id, role, opp_hand, game_date).

`opp_hand` is always the *opponent's* handedness, so one column serves both
roles: for a batter it is the pitcher's throwing hand, for a pitcher it is the
batter's stance. That makes "vs LHP" and "vs LHB" the same query shape.

This module is deliberately pure pandas -- no pybaseball, no database -- so the
logic is unit-testable against hand-built fixtures.
"""

from __future__ import annotations

import logging

import pandas as pd

from .events import (
    CATCHER_INTERFERENCE_EVENTS,
    HBP_EVENTS,
    HIT_EVENTS,
    INTENT_WALK_EVENTS,
    OUTS_BY_EVENT,
    PA_EVENTS,
    SAC_BUNT_EVENTS,
    SAC_FLY_EVENTS,
    STRIKEOUT_EVENTS,
    WALK_EVENTS,
    unknown_events,
)

log = logging.getLogger(__name__)

#: Columns the aggregator needs from a raw Statcast pull.
REQUIRED_COLUMNS = (
    "game_pk",
    "game_date",
    "at_bat_number",
    "pitch_number",
    "batter",
    "pitcher",
    "stand",
    "p_throws",
    "events",
)

#: Additive component columns, in table order. Everything downstream derives
#: from these.
COMPONENT_COLUMNS = (
    "pa",
    "ab",
    "h",
    "singles",
    "doubles",
    "triples",
    "hr",
    "bb",
    "ibb",
    "hbp",
    "so",
    "sf",
    "sh",
    "ci",
    "pitches",
    "woba_num",
    "woba_den",
    "xwoba_con_sum",
    "xwoba_con_n",
    "outs_batter_events",
)

KEY_COLUMNS = ("player_id", "role", "opp_hand", "game_date", "season")

_ROLE_SPEC = {
    "batter": ("batter", "p_throws"),
    "pitcher": ("pitcher", "stand"),
}


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    """Coerce a column to float, returning zeros if it is absent."""
    if column not in frame.columns:
        return pd.Series(0.0, index=frame.index)
    return pd.to_numeric(frame[column], errors="coerce").fillna(0.0)


def _pitch_mask(frame: pd.DataFrame) -> pd.Series:
    """Rows that represent an actual pitch.

    Not every Statcast row is one. Since 2017 an intentional walk requires no
    pitches, so those plate appearances can appear with no pitch payload; the
    `type` column (S/B/X) is the cleanest signal that a pitch was thrown, and
    counting such rows would inflate pitches-per-PA.
    """
    if "type" in frame.columns:
        return frame["type"].notna()
    return frame["pitch_number"].notna()


def _validate(pitches: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in pitches.columns]
    if missing:
        raise ValueError(f"Statcast frame is missing required columns: {missing}")


def pa_indicators(pa: pd.DataFrame) -> pd.DataFrame:
    """Per-plate-appearance indicator columns.

    Public because the calibration script needs PA-level granularity to do
    split-half reliability, and duplicating the event taxonomy there would let
    the two drift apart.
    """
    events = pa["events"]

    indicators = pd.DataFrame(index=pa.index)
    indicators["pa"] = 1
    for event_name, column in HIT_EVENTS.items():
        indicators[column] = (events == event_name).astype("int64")
    indicators["bb"] = events.isin(WALK_EVENTS).astype("int64")
    indicators["ibb"] = events.isin(INTENT_WALK_EVENTS).astype("int64")
    indicators["hbp"] = events.isin(HBP_EVENTS).astype("int64")
    indicators["so"] = events.isin(STRIKEOUT_EVENTS).astype("int64")
    indicators["sf"] = events.isin(SAC_FLY_EVENTS).astype("int64")
    indicators["sh"] = events.isin(SAC_BUNT_EVENTS).astype("int64")
    indicators["ci"] = events.isin(CATCHER_INTERFERENCE_EVENTS).astype("int64")
    indicators["outs_batter_events"] = events.map(OUTS_BY_EVENT).fillna(0).astype("int64")

    # wOBA: Statcast ships per-event numerator and denominator already computed
    # with the correct season-specific linear weights. Summing them avoids
    # hardcoding weights that change every year.
    indicators["woba_num"] = _numeric(pa, "woba_value")
    indicators["woba_den"] = _numeric(pa, "woba_denom")

    # xwOBA on contact only. `estimated_woba_using_speedangle` is populated for
    # batted balls, so this is xwOBAcon -- NOT Savant's overall xwOBA, which
    # also folds in strikeouts and walks. Named accordingly to avoid confusion.
    xwoba = pd.to_numeric(
        pa.get("estimated_woba_using_speedangle", pd.Series(index=pa.index, dtype="float64")),
        errors="coerce",
    )
    indicators["xwoba_con_sum"] = xwoba.fillna(0.0)
    indicators["xwoba_con_n"] = xwoba.notna().astype("int64")

    # AB eligibility, needed for AB-denominated stats at PA granularity.
    indicators["ab"] = (
        1
        - indicators["bb"]
        - indicators["hbp"]
        - indicators["sf"]
        - indicators["sh"]
        - indicators["ci"]
    ).clip(lower=0)

    return indicators


def _one_role(
    pitches: pd.DataFrame,
    pa_rows: pd.DataFrame,
    role: str,
) -> pd.DataFrame:
    id_col, hand_col = _ROLE_SPEC[role]
    group_keys = [id_col, hand_col, "game_date"]

    # ---- pitch counts come from ALL rows, not just PA-terminating ones ----
    thrown = pitches[_pitch_mask(pitches)]
    pitch_counts = (
        thrown.groupby(group_keys, dropna=True, observed=True)
        .size()
        .rename("pitches")
        .reset_index()
    )

    # ---- everything else comes from one row per plate appearance ----
    pa = pa_rows.copy()
    indicators = pa_indicators(pa).drop(columns=["ab"])

    grouped = (
        pd.concat([pa[group_keys], indicators], axis=1)
        .groupby(group_keys, dropna=True, observed=True)
        .sum()
        .reset_index()
    )

    out = grouped.merge(pitch_counts, on=group_keys, how="outer")

    # A player can throw pitches on a date without any PA completing against
    # them (e.g. removed mid-count), so fill rather than drop.
    for column in COMPONENT_COLUMNS:
        if column not in out.columns:
            out[column] = 0
        out[column] = out[column].fillna(0)

    out["h"] = out["singles"] + out["doubles"] + out["triples"] + out["hr"]
    # PA = AB + BB + HBP + SF + SH + CI, so AB is the residual. `bb` already
    # includes intentional walks, which is why ibb is not subtracted again.
    out["ab"] = out["pa"] - out["bb"] - out["hbp"] - out["sf"] - out["sh"] - out["ci"]

    out = out.rename(columns={id_col: "player_id", hand_col: "opp_hand"})
    out["role"] = role
    out["game_date"] = pd.to_datetime(out["game_date"])
    out["season"] = out["game_date"].dt.year

    integer_columns = [c for c in COMPONENT_COLUMNS if c not in ("woba_num", "woba_den", "xwoba_con_sum")]
    for column in integer_columns:
        out[column] = out[column].round().astype("int64")
    out["player_id"] = out["player_id"].astype("int64")

    return out[list(KEY_COLUMNS) + list(COMPONENT_COLUMNS)]


def aggregate_daily(
    pitches: pd.DataFrame,
    *,
    game_types: tuple[str, ...] = ("R",),
) -> pd.DataFrame:
    """Roll pitch-level Statcast up to daily per-player-per-split components.

    Args:
        pitches: raw Statcast pull (one row per pitch).
        game_types: Statcast `game_type` codes to keep. Defaults to regular
            season only. This filter matters -- a date range that brushes
            spring training or the postseason will otherwise inflate totals and
            show up as an unexplained gap against FanGraphs.

    Returns:
        DataFrame keyed on (player_id, role, opp_hand, game_date) with additive
        component columns only. Empty frame with the right schema if there is
        no qualifying input.
    """
    if pitches is None or pitches.empty:
        return pd.DataFrame(columns=list(KEY_COLUMNS) + list(COMPONENT_COLUMNS))

    _validate(pitches)
    frame = pitches.copy()

    if game_types and "game_type" in frame.columns:
        before = len(frame)
        frame = frame[frame["game_type"].isin(game_types)]
        dropped = before - len(frame)
        if dropped:
            log.info("Dropped %d rows outside game_type %s", dropped, list(game_types))
    elif game_types:
        log.warning(
            "No `game_type` column present -- cannot filter to regular season. "
            "Totals may include spring training or postseason."
        )

    frame = frame[frame["stand"].isin(["L", "R"]) & frame["p_throws"].isin(["L", "R"])]
    if frame.empty:
        return pd.DataFrame(columns=list(KEY_COLUMNS) + list(COMPONENT_COLUMNS))

    strays = unknown_events(set(frame["events"].dropna().unique()))
    if strays:
        log.warning(
            "Unclassified Statcast events (excluded from PA counts, add them to "
            "etl/events.py): %s",
            sorted(strays),
        )

    pa_rows = frame[frame["events"].isin(PA_EVENTS)]

    # One PA should terminate exactly once. Duplicates mean a re-processed game
    # or an events code appearing mid-PA; keep the last pitch of the PA.
    duplicated = pa_rows.duplicated(subset=["game_pk", "at_bat_number"], keep=False)
    if duplicated.any():
        log.warning(
            "%d PA-terminating rows share a (game_pk, at_bat_number); keeping the "
            "highest pitch_number in each.",
            int(duplicated.sum()),
        )
        pa_rows = (
            pa_rows.sort_values("pitch_number")
            .drop_duplicates(subset=["game_pk", "at_bat_number"], keep="last")
        )

    frames = [_one_role(frame, pa_rows, role) for role in _ROLE_SPEC]
    result = pd.concat(frames, ignore_index=True)
    return result.sort_values(list(KEY_COLUMNS)).reset_index(drop=True)


def pa_level_frame(
    pitches: pd.DataFrame,
    role: str,
    *,
    game_types: tuple[str, ...] = ("R",),
) -> pd.DataFrame:
    """One row per plate appearance with indicator columns, for calibration.

    Split-half reliability needs to shuffle a player's individual plate
    appearances, which the daily aggregates have already collapsed. This
    reproduces that granularity using the same event taxonomy.
    """
    if pitches is None or pitches.empty:
        return pd.DataFrame()

    _validate(pitches)
    frame = pitches.copy()
    if game_types and "game_type" in frame.columns:
        frame = frame[frame["game_type"].isin(game_types)]
    frame = frame[frame["stand"].isin(["L", "R"]) & frame["p_throws"].isin(["L", "R"])]

    pa_rows = frame[frame["events"].isin(PA_EVENTS)]
    pa_rows = (
        pa_rows.sort_values("pitch_number")
        .drop_duplicates(subset=["game_pk", "at_bat_number"], keep="last")
    )
    if pa_rows.empty:
        return pd.DataFrame()

    # pitches thrown within each plate appearance, so pitches_per_pa can be
    # calibrated at the same granularity as the rate stats
    thrown = frame[_pitch_mask(frame)]
    per_pa_pitches = (
        thrown.groupby(["game_pk", "at_bat_number"], observed=True)
        .size()
        .rename("pitches")
        .reset_index()
    )
    pa_rows = pa_rows.merge(per_pa_pitches, on=["game_pk", "at_bat_number"], how="left")
    pa_rows["pitches"] = pa_rows["pitches"].fillna(0).astype("int64")

    id_col, hand_col = _ROLE_SPEC[role]
    keys = pa_rows[[id_col, hand_col, "game_date", "pitches"]].rename(
        columns={id_col: "player_id", hand_col: "opp_hand"}
    )
    indicators = pa_indicators(pa_rows).drop(columns=["pitches"], errors="ignore")
    out = pd.concat([keys.reset_index(drop=True), indicators.reset_index(drop=True)], axis=1)
    out["game_date"] = pd.to_datetime(out["game_date"])
    out["season"] = out["game_date"].dt.year
    out["h"] = out["singles"] + out["doubles"] + out["triples"] + out["hr"]
    out["extra_bases"] = out["doubles"] + 2 * out["triples"] + 3 * out["hr"]
    return out


# --------------------------------------------------------------------------- #
# Rate derivation -- used by the calibration script and the reconciliation
# report. Postgres computes these itself for the dashboard (see db/schema.sql);
# this is the same arithmetic in Python so the two can be cross-checked.
# --------------------------------------------------------------------------- #


def derive_rates(totals: pd.DataFrame) -> pd.DataFrame:
    """Add rate columns to a frame of summed components."""
    out = totals.copy()

    def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
        return (numerator / denominator.where(denominator > 0)).astype("float64")

    out["avg"] = safe_divide(out["h"], out["ab"])
    out["iso"] = safe_divide(
        out["doubles"] + 2 * out["triples"] + 3 * out["hr"], out["ab"]
    )
    out["k_rate"] = safe_divide(out["so"], out["pa"])
    out["bb_rate"] = safe_divide(out["bb"], out["pa"])
    out["woba"] = safe_divide(out["woba_num"], out["woba_den"])
    out["xwoba_con"] = safe_divide(out["xwoba_con_sum"], out["xwoba_con_n"])
    out["pitches_per_pa"] = safe_divide(out["pitches"], out["pa"])
    out["ip_est"] = out["outs_batter_events"] / 3.0
    out["pitches_per_inning_est"] = safe_divide(
        out["pitches"], out["outs_batter_events"] / 3.0
    )
    return out
