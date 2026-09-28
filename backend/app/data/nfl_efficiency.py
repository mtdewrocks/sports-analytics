"""Team efficiency for the NFL Matchup page and the Matchup Deep Dive.

Reads team_efficiency.parquet (get_nfl_team_efficiency.py, from nflverse
play-by-play) and ranks every stat 1-32 within its window and side.

Rank direction: 1st always means best at it. For an offense that's gaining
(high EPA, low sack rate); for a defense it's stopping the same thing, so a
defense's rank runs the other way. Pace stats have no better or worse --
they rank by most (fastest, pass-heaviest) and aren't coloured.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from app.data.loader import ttl_cache

# key: (label, better for the offense: "high" | "low" | None, format)
STATS: Dict[str, tuple] = {
    "epa_per_play": ("EPA per play", "high", "epa"),
    "success_rate": ("Success rate", "high", "pct"),
    "explosive_rate": ("Explosive play rate", "high", "pct1"),
    "yards_per_play": ("Yards per play", "high", "dec1"),
    "dropback_epa": ("Dropback EPA", "high", "epa"),
    "dropback_success": ("Dropback success rate", "high", "pct"),
    "cpoe": ("Completion % over expected", "high", "signed1"),
    "sack_rate": ("Sack rate", "low", "pct1"),
    "explosive_pass_rate": ("Explosive passes (20+ yds)", "high", "pct"),
    "net_yards_per_dropback": ("Net yards per dropback", "high", "dec1"),
    "rush_success": ("Rush success rate", "high", "pct"),
    "yards_per_carry": ("Yards per carry", "high", "dec1"),
    "explosive_run_rate": ("Explosive runs (10+ yds)", "high", "pct"),
    "stuff_rate": ("Stuff rate (runs for 0 or less)", "low", "pct"),
    "points_per_drive": ("Points per drive", "high", "dec2"),
    "score_rate": ("Drives ending in points", "high", "pct"),
    "td_rate": ("Drives ending in a TD", "high", "pct"),
    "three_and_out_rate": ("3-and-out rate", "low", "pct"),
    "plays_per_drive": ("Plays per drive", "high", "dec1"),
    "start_yardline": ("Avg starting field position", "high", "own"),
    "turnover_rate": ("Turnovers per drive", "low", "pct"),
    "third_down_rate": ("3rd-down conversion", "high", "pct"),
    "third_down_distance": ("Avg yards to go on 3rd down", "low", "dec1"),
    "early_down_success": ("Early-down success (1st & 2nd)", "high", "pct"),
    "red_zone_td_rate": ("Red zone TD rate", "high", "pct"),
    "red_zone_trips_per_game": ("Red zone trips per game", "high", "dec1"),
    "proe": ("Pass rate over expected (neutral)", None, "signedpct"),
    "neutral_pass_rate": ("Neutral pass rate", None, "pct"),
    "seconds_per_play": ("Seconds per play (neutral)", None, "dec1"),
    "plays_per_game": ("Plays per game", None, "dec1"),
    "penalty_yards_per_game": ("Penalty yards per game", "low", "dec1"),
}

# Deep Dive tabs -> sections -> stats.
TABS = [
    ("passing_rushing", "Passing & Rushing", [
        ("Overall", ["epa_per_play", "success_rate", "explosive_rate", "yards_per_play"]),
        ("Passing", ["dropback_epa", "dropback_success", "cpoe", "sack_rate", "explosive_pass_rate",
                     "net_yards_per_dropback"]),
        ("Rushing", ["rush_success", "yards_per_carry", "explosive_run_rate", "stuff_rate"]),
    ]),
    ("drives", "Drives", [
        ("Drives", ["points_per_drive", "score_rate", "td_rate", "three_and_out_rate", "plays_per_drive",
                    "start_yardline", "turnover_rate"]),
    ]),
    ("situations", "Situations", [
        ("Situations", ["third_down_rate", "third_down_distance", "early_down_success", "red_zone_td_rate",
                        "red_zone_trips_per_game"]),
    ]),
    ("pace", "Pace", [
        ("Pace & tendencies", ["proe", "neutral_pass_rate", "seconds_per_play", "plays_per_game",
                               "penalty_yards_per_game"]),
    ]),
]

# Ranks this far apart mark an edge on the Deep Dive.
EDGE_GAP = 15
# "Last 4 games" is offered once every team has played this many.
LAST4_FROM_GAMES = 5

# The Matchup page's new rows: (section, stat, side, label).
MATCHUP_ROWS = [
    ("Efficiency", "epa_per_play", "off", "EPA Per Play"),
    ("Efficiency", "success_rate", "off", "Success Rate (%)"),
    ("Efficiency", "points_per_drive", "off", "Points Per Drive"),
    ("Efficiency", "three_and_out_rate", "off", "3-and-Out Rate (%)"),
    ("Efficiency", "explosive_rate", "off", "Explosive Play Rate (%)"),
    ("Defense", "epa_per_play", "def", "EPA Per Play Allowed"),
    ("Defense", "points_per_drive", "def", "Points Per Drive Allowed"),
]


def fmt(stat: str, v: Optional[float]) -> str:
    if v is None or pd.isna(v):
        return "—"
    kind = STATS[stat][2]
    if kind == "pct":
        return f"{v * 100:.0f}%"
    if kind == "pct1":
        return f"{v * 100:.1f}%"
    if kind == "signedpct":
        return f"{v * 100:+.1f}%"
    if kind == "epa":
        out = f"{v:+.2f}"
        return "0.00" if out in ("+0.00", "-0.00") else out
    if kind == "signed1":
        return f"{v:+.1f}"
    if kind == "dec2":
        return f"{v:.2f}"
    if kind == "own":
        return f"own {v:.0f}"
    return f"{v:.1f}"


def rank_table(df: pd.DataFrame) -> pd.DataFrame:
    """Adds `rank` (1 = best at it) within each (window, side, stat). Pure,
    so it's tested directly."""
    out = []
    for (window, side, stat), g in df.groupby(["window", "side", "stat"]):
        better = STATS.get(stat, (None, None, None))[1]
        if better is None:
            ascending = False                      # pace: 1st = most
        else:
            high_good = (better == "high") == (side == "off")
            ascending = not high_good
        g = g.copy()
        g["rank"] = g["value"].rank(ascending=ascending, method="min")
        out.append(g)
    return pd.concat(out) if out else df.assign(rank=None)


@ttl_cache(3600)
def _ranked() -> pd.DataFrame:
    from app.data.loader import get_nfl_team_efficiency
    df = get_nfl_team_efficiency()
    return rank_table(df) if not df.empty else df


def _lookup(df: pd.DataFrame, window: str) -> Dict[tuple, Dict[str, Any]]:
    sub = df[df["window"] == window]
    return {(r["team"], r["side"], r["stat"]): r for r in sub.to_dict(orient="records")}


def _cell(look: Dict, team: str, side: str, stat: str) -> Dict[str, Any]:
    r = look.get((team, side, stat))
    if r is None:
        return {"value": None, "display": "—", "rank": None}
    rank = None if pd.isna(r["rank"]) else int(r["rank"])
    return {"value": r["value"], "display": fmt(stat, r["value"]), "rank": rank}


def matchup_rows(team: str) -> List[Dict[str, Any]]:
    """The Matchup page's efficiency rows for one team, season window, in
    the same row shape as the rest of its table (plus `section`/`display`)."""
    df = _ranked()
    if df.empty:
        return []
    look = _lookup(df, "season")
    rows = []
    for section, stat, side, label in MATCHUP_ROWS:
        c = _cell(look, team, side, stat)
        kind = STATS[stat][2]
        value = c["value"]
        if value is not None and not pd.isna(value):
            value = round(value * 100, 1) if kind in ("pct", "pct1") else round(value, 2)
        rows.append({"stat": label, "value": value, "display": c["display"], "rank": c["rank"],
                     "section": section, "new": True})
    return rows


def deep_dive(away: str, home: str, window: str = "season") -> Dict[str, Any]:
    """Both matchups at once for every stat: away offense vs home defense,
    and home offense vs away defense, with ranks and an edge flag."""
    df = _ranked()
    if df.empty:
        return {"away": away, "home": home, "window": window, "tabs": [], "last4_available": False}
    teams_games = df.drop_duplicates("team").set_index("team")["games_played"]
    last4_available = bool(teams_games.min() >= LAST4_FROM_GAMES)
    use = window if (window == "season" or last4_available) else "season"
    look = _lookup(df, use)

    def pair(off_team: str, def_team: str, stat: str) -> Dict[str, Any]:
        o, d = _cell(look, off_team, "off", stat), _cell(look, def_team, "def", stat)
        edge = None
        if STATS[stat][1] is not None and o["rank"] and d["rank"] and abs(o["rank"] - d["rank"]) >= EDGE_GAP:
            edge = "off" if o["rank"] < d["rank"] else "def"
        return {"off": o, "def": d, "edge": edge}

    tabs = []
    for key, title, sections in TABS:
        tabs.append({"key": key, "title": title, "sections": [
            {"title": sec, "stats": [{
                "stat": s, "label": STATS[s][0], "colored": STATS[s][1] is not None,
                "lower_better": STATS[s][1] == "low",
                "away_off": pair(away, home, s), "home_off": pair(home, away, s),
            } for s in stats]} for sec, stats in sections]})
    season = int(df["season"].iloc[0]) if "season" in df.columns else None
    return {"away": away, "home": home, "window": use, "season": season,
            "last4_available": last4_available, "last4_from_games": LAST4_FROM_GAMES,
            "games": {away: int(teams_games.get(away, 0)), home: int(teams_games.get(home, 0))},
            "tabs": tabs}
