"""Statcast `events` taxonomy.

The most common source of wrong plate-appearance counts is treating every
non-null `events` value as the end of a PA. It isn't -- Statcast also records
baserunning outcomes (caught stealing, pickoffs, wild pitches) in the same
column, mid-PA. Those rows must not count as plate appearances.

Every set below is explicit so it can be audited and corrected. If the
FanGraphs reconciliation reports a systematic gap, this file is where you fix
it, not the aggregation code.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Plate-appearance outcomes
# --------------------------------------------------------------------------- #

HIT_EVENTS = {
    "single": "singles",
    "double": "doubles",
    "triple": "triples",
    "home_run": "hr",
}

# Outs (and errors) charged to the batter that end a plate appearance.
BATTED_OUT_EVENTS = {
    "field_out",
    "force_out",
    "grounded_into_double_play",
    "double_play",
    "triple_play",
    "fielders_choice",
    "fielders_choice_out",
    "field_error",
    "sac_fly",
    "sac_fly_double_play",
    "sac_bunt",
    "sac_bunt_double_play",
    "other_out",
    "batter_interference",
}

STRIKEOUT_EVENTS = {"strikeout", "strikeout_double_play"}
WALK_EVENTS = {"walk", "intent_walk"}
INTENT_WALK_EVENTS = {"intent_walk"}
HBP_EVENTS = {"hit_by_pitch"}
SAC_FLY_EVENTS = {"sac_fly", "sac_fly_double_play"}
SAC_BUNT_EVENTS = {"sac_bunt", "sac_bunt_double_play"}
CATCHER_INTERFERENCE_EVENTS = {"catcher_interf"}

#: Every event that terminates a plate appearance.
PA_EVENTS = (
    set(HIT_EVENTS)
    | BATTED_OUT_EVENTS
    | STRIKEOUT_EVENTS
    | WALK_EVENTS
    | HBP_EVENTS
    | CATCHER_INTERFERENCE_EVENTS
)

# --------------------------------------------------------------------------- #
# Baserunning outcomes -- these appear in `events` but do NOT end a PA
# --------------------------------------------------------------------------- #

BASERUNNING_EVENTS = {
    "caught_stealing_2b",
    "caught_stealing_3b",
    "caught_stealing_home",
    "stolen_base_2b",
    "stolen_base_3b",
    "stolen_base_home",
    "pickoff_1b",
    "pickoff_2b",
    "pickoff_3b",
    "pickoff_caught_stealing_2b",
    "pickoff_caught_stealing_3b",
    "pickoff_caught_stealing_home",
    "pickoff_error_1b",
    "pickoff_error_2b",
    "pickoff_error_3b",
    "wild_pitch",
    "passed_ball",
    "balk",
    "other_advance",
    "runner_double_play",
    "cs_double_play",
    "defensive_indiff",
    "error",
    "game_advisory",
    "ejection",
    "at_bat_start",
    "os_ruling_pending_prior",
    "os_ruling_pending_primary",
}

# --------------------------------------------------------------------------- #
# Outs recorded, for pitcher innings
# --------------------------------------------------------------------------- #

#: Outs charged on a batter-terminating event. Deliberately excludes
#: baserunning outs (caught stealing, pickoffs), which DO count toward real
#: innings pitched -- so IP derived from this is a slight undercount. Pitches
#: per batter faced is exact; prefer it where you can.
OUTS_BY_EVENT: dict[str, int] = {
    "strikeout": 1,
    "field_out": 1,
    "force_out": 1,
    "fielders_choice_out": 1,
    "sac_fly": 1,
    "sac_bunt": 1,
    "other_out": 1,
    "batter_interference": 1,
    "strikeout_double_play": 2,
    "grounded_into_double_play": 2,
    "double_play": 2,
    "sac_fly_double_play": 2,
    "sac_bunt_double_play": 2,
    "triple_play": 3,
}


def unknown_events(observed: set[str]) -> set[str]:
    """Events that have never been classified.

    Called by the ETL on every run: MLB adds event codes occasionally, and an
    unclassified code would silently vanish from the totals. Better to log a
    warning than to under-count PAs for a whole season without noticing.
    """
    return {
        e
        for e in observed
        if e and e not in PA_EVENTS and e not in BASERUNNING_EVENTS
    }
