"""MLB business logic layer — mirrors mlb_data.py from the original Dash app."""
from typing import Optional, List, Dict, Any
import math
import pandas as pd
from app.data.loader import get_mlb_data, get_mlb_props_data, ttl_cache, MLB_TTL
from app.data.hit_rate import grade_over_under, split_season_recent, RECENT_WINDOW


def _normalize(name: str) -> str:
    return name.strip().lower()


def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    cols_lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in cols_lower:
            return cols_lower[c.lower()]
    return None


def _convert_savant_name(name: str) -> str:
    """Convert 'Last, First' format to 'First Last'."""
    try:
        last, first = name.split(", ")
        return f"{first} {last}"
    except Exception:
        return name


def _starter_row(starters_df: pd.DataFrame, pitcher_norm: str):
    """The starters.parquet row for a dropdown value, or None.

    Accepts either spelling: `pitcher` is the MLB Stats API form the dropdown
    uses, `savant_name` is the "Last, First" form the Excel-backed sections
    still use. Matching both keeps this working whichever way the dropdown is
    wired, and returning the row gives callers `pitcher_id` for exact joins.
    """
    if starters_df is None or starters_df.empty:
        return None
    if "pitcher" not in starters_df.columns:
        return None

    match = starters_df["pitcher"].str.lower().str.strip() == pitcher_norm
    if "savant_name" in starters_df.columns:
        match = match | (starters_df["savant_name"].str.lower().str.strip() == pitcher_norm)

    hit = starters_df[match]
    return None if hit.empty else hit.iloc[0]


# Sanity bounds — corrupted historical values can reach e+100 from accumulation bugs
_PERCENT_STATS = {"Weighted K%", "Weighted BB%", "Weighted GB%", "Weighted LD%",
                  "Weighted FB%", "Weighted HR/FB", "Weighted Soft%", "Weighted Med%", "Weighted Hard%"}
_RATE_STATS    = {"Weighted AVG", "Weighted BABIP", "Weighted wOBA", "Weighted SLG", "ISO Pitcher"}
_ERA_STATS     = {"Weighted FIP", "Weighted xFIP"}


def _sane(val, stat):
    if val is None:
        return None
    if stat in _PERCENT_STATS and not (0 <= val <= 100):
        return None
    if stat in _RATE_STATS and not (0 <= val <= 2):
        return None
    if stat in _ERA_STATS and not (0 <= val <= 15):
        return None
    return val


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------
def get_pitchers() -> List[str]:
    """Every pitcher with a start this season, for the dropdown.

    Season-long rather than today's probables, so a user can look up any
    starter at any time. Sourced from starters.parquet, which uses the same
    MLB Stats API names as daily_matchups.parquet -- so a dropdown selection
    matches the matchup table without any name conversion.
    """
    starters_df = get_mlb_data().get("starters", pd.DataFrame())
    if starters_df.empty:
        return []
    return sorted(starters_df["pitcher"].dropna().unique().tolist())


def get_pitcher_matchup(pitcher_name: str) -> Dict[str, Any]:
    """
    Return pitcher matchup data matching the original Dash app structure:
    - season_stats: key season metrics row
    - game_logs: recent game-by-game logs
    - splits: vs L / vs R pivot
    - percentiles: reshaped percentile data for charting
    - opposing_hitters: today's opposing lineup with stats
    """
    data = get_mlb_data()
    pitcher_norm = _normalize(pitcher_name)

    # Resolved once and reused by sections 1 and 2.
    starters_df = data.get("starters", pd.DataFrame())
    starter = _starter_row(starters_df, pitcher_norm)

    # ------------------------------------------------------------------
    # 1. Season stats — starters.parquet (MLB Stats API)
    # ------------------------------------------------------------------
    season_stats = {}
    try:
        if starter is not None:
            # ERA, WHIP and K/IP are recomputed from summed components in
            # get_starters.py, so a traded pitcher's line is whole rather than
            # one team's partial figures.
            candidate = {
                "Handedness": {"R": "RHP", "L": "LHP"}.get(
                    starter.get("throws"), starter.get("throws")
                ),
                "GS": starter.get("games_started"),
                "W": starter.get("wins"),
                "L": starter.get("losses"),
                "ERA": starter.get("era"),
                "IP": starter.get("innings"),
                "SO": starter.get("strikeouts"),
                "K/IP": starter.get("k_per_ip"),
                "WHIP": starter.get("whip"),
            }
            for key, val in candidate.items():
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    continue
                # numpy scalars are not JSON serializable
                season_stats[key] = val.item() if hasattr(val, "item") else val
    except Exception as e:
        print(f"Warning: season_stats section failed for {pitcher_name}: {e}")

    # ------------------------------------------------------------------
    # 2. Game logs — pitcher_logs.parquet (MLB Stats API)
    # ------------------------------------------------------------------
    game_logs = []
    try:
        logs_df = data.get("pitcher_logs", pd.DataFrame())

        if not logs_df.empty and starter is not None:
            # Join on the id: pitcher_logs carries MLB-format names, so this
            # sidesteps the name-format question entirely.
            sub = logs_df[logs_df["pitcher_id"] == int(starter["pitcher_id"])].copy()

            sub["date"] = pd.to_datetime(sub["date"], errors="coerce")
            sub = sub[sub["date"].notna()].sort_values("date", ascending=False).head(10)

            display = {
                "date": "Date",
                "opponent": "Opponent",
                "wins": "W",
                "losses": "L",
                "innings": "IP",
                "hits": "H",
                "runs": "R",
                "earned_runs": "ER",
                "home_runs": "HR",
                "walks": "BB",
                "strikeouts": "SO",
                "pitches": "Pitches",
            }
            cols = [c for c in display if c in sub.columns]
            sub = sub[cols].rename(columns=display)

            if "Date" in sub.columns:
                # Built from parts rather than strftime("%-m/..."), which is
                # platform specific and raises on Windows.
                sub["Date"] = (
                    sub["Date"].dt.month.astype(str) + "/"
                    + sub["Date"].dt.day.astype(str) + "/"
                    + sub["Date"].dt.year.astype(str)
                )

            sub = sub.astype(object).where(sub.notna(), "")
            game_logs = sub.to_dict(orient="records")
    except Exception as e:
        print(f"Warning: game_logs section failed for {pitcher_name}: {e}")

    # ------------------------------------------------------------------
    # 3. Splits — pitcher_splits.parquet (Statcast, 2025 + 2026 pooled)
    # ------------------------------------------------------------------
    # (parquet column, display label) in the order the table renders.
    SPLIT_STATS = [
        ("tbf", "TBF"),
        ("ip", "IP"),
        ("avg", "AVG"),
        ("babip", "BABIP"),
        ("woba", "wOBA"),
        ("slg", "SLG"),
        ("iso", "ISO"),
        ("hr_allowed", "HR"),
        ("hr_rate", "HR Rate"),
        ("k_pct", "K%"),
        ("bb_pct", "BB%"),
        ("gb_pct", "GB%"),
        ("ld_pct", "LD%"),
        ("fb_pct", "FB%"),
        ("iffb_pct", "IFFB%"),
        ("hr_fb_pct", "HR/FB"),
        ("soft_pct", "Soft%"),
        ("med_pct", "Med%"),
        ("hard_pct", "Hard%"),
        ("avg_ev", "Avg EV"),
        ("fip", "FIP"),
        ("xfip", "xFIP"),
    ]

    splits = []
    try:
        splits_df = data.get("pitcher_splits", pd.DataFrame())

        if not splits_df.empty and starter is not None:
            # Join on the id -- this file is keyed on player_id, so there is no
            # name-format question at all.
            sub = splits_df[splits_df["player_id"] == int(starter["pitcher_id"])].copy()
            sub = sub[sub["split"].isin(["vs L", "vs R"])]

            if not sub.empty:
                sub = sub.set_index("split")
                rows = []
                for column, label in SPLIT_STATS:
                    if column not in sub.columns:
                        continue
                    row = {"Statistic": label}
                    for hand in ("vs L", "vs R"):
                        value = sub[column].get(hand)
                        if value is None or pd.isna(value):
                            row[hand] = ""
                        else:
                            # numpy scalars are not JSON serializable
                            row[hand] = value.item() if hasattr(value, "item") else value
                    rows.append(row)

                # Column order the frontend renders: vs L | Statistic | vs R
                splits = [
                    {"vs L": r.get("vs L", ""), "Statistic": r["Statistic"], "vs R": r.get("vs R", "")}
                    for r in rows
                ]
    except Exception as e:
        print(f"Warning: splits section failed for {pitcher_name}: {e}")

    # ------------------------------------------------------------------
    # 4. Percentiles — Pitcher_Percentile_Rankings.csv (reshaped for chart)
    # ------------------------------------------------------------------
    percentiles = []
    try:
        pct_df = data.get("pitcher_percentiles", pd.DataFrame())
        if not pct_df.empty:
            rename_map = {
                "xera": "Expected ERA", "xba": "Expected Batting Avg",
                "fb_velocity": "Fastball Velo", "exit_velocity": "Avg Exit Velocity",
                "k_percent": "K %", "chase_percent": "Chase %", "whiff_percent": "Whiff %",
                "brl_percent": "Barrel %", "hard_hit_percent": "Hard-Hit %", "bb_percent": "BB %",
            }
            pct_df = pct_df.rename(columns={k: v for k, v in rename_map.items() if k in pct_df.columns})

            sub = pd.DataFrame()
            # This CSV carries player_id (the MLBAM id), so prefer an exact id
            # join -- it removes accents, suffixes and initials as failure modes.
            id_col = _find_col(pct_df, ["player_id"])
            if id_col and starter is not None:
                ids = pd.to_numeric(pct_df[id_col], errors="coerce")
                sub = pct_df[ids == int(starter["pitcher_id"])].copy()

            if sub.empty:
                name_col = _find_col(pct_df, ["player_name"])
                if name_col:
                    pct_df["converted_name"] = pct_df[name_col].apply(_convert_savant_name)
                    sub = pct_df[pct_df["converted_name"].str.lower().str.strip() == pitcher_norm].copy()

            if not sub.empty:
                stat_cols = [c for c in ["Fastball Velo", "Avg Exit Velocity", "Chase %",
                                         "Whiff %", "K %", "BB %", "Barrel %", "Hard-Hit %"]
                             if c in sub.columns]
                melted = pd.melt(sub[stat_cols], var_name="Statistic", value_name="Percentile")
                percentiles = melted.fillna("").to_dict(orient="records")
    except Exception as e:
        print(f"Warning: percentiles section failed for {pitcher_name}: {e}")

    # ------------------------------------------------------------------
    # 5. Opposing hitters — daily_matchups.parquet (built by GitHub Actions)
    # ------------------------------------------------------------------
    opposing_hitters = []
    try:
        matchups_df = data.get("matchups", pd.DataFrame())
        if not matchups_df.empty:
            sub = matchups_df[
                matchups_df["pitcher"].str.lower().str.strip() == pitcher_norm
            ].copy()

            # Splits were already computed against this starter's throwing hand
            # and last_week_ba is already joined in, so nothing to merge here.
            display = {
                "player": "Player",
                "bats": "Bats",
                "batting_order": "Batting Order",
                "split_avg": "Average",
                "split_woba": "wOBA",
                "split_obp": "OBP",
                "split_slg": "SLG",
                "split_ops": "OPS",
                "split_iso": "ISO",
                "split_k_pct": "K%",
                "split_bb_pct": "BB%",
                "last_week_ba": "Last Week BA",
            }
            cols = [c for c in display if c in sub.columns]
            sub = sub[cols].rename(columns=display)

            for col in ("Average", "wOBA", "OBP", "SLG", "OPS", "ISO", "Last Week BA"):
                if col in sub.columns:
                    sub[col] = pd.to_numeric(sub[col], errors="coerce").round(3)
            for col in ("K%", "BB%"):
                if col in sub.columns:
                    sub[col] = pd.to_numeric(sub[col], errors="coerce").round(1)

            if "Batting Order" in sub.columns:
                sub = sub.sort_values("Batting Order")

            # Nullable dtypes hold pd.NA, which is not JSON serializable.
            sub = sub.astype(object).where(sub.notna(), "")
            opposing_hitters = sub.to_dict(orient="records")
    except Exception as e:
        print(f"Warning: opposing_hitters section failed for {pitcher_name}: {e}")

    # ------------------------------------------------------------------
    # 6. Pitcher's own rate allowed by handedness -- sourced from the same
    #    pitcher_splits.parquet used for the Splits table above (see section
    #    3), NOT from daily_matchups.parquet. That file requires the day's
    #    lineup to have posted before it produces any rows at all, even
    #    though a pitcher's own AVG/wOBA/etc. vs each hand has nothing to do
    #    with who's actually in the opposing lineup. This is available as
    #    soon as the starter is known and pitcher_splits.parquet has been
    #    built, matching the same ID-based join as section 3.
    # ------------------------------------------------------------------
    pitcher_splits = {}
    try:
        splits_source = data.get("pitcher_splits", pd.DataFrame())
        if not splits_source.empty and starter is not None:
            sub = splits_source[splits_source["player_id"] == int(starter["pitcher_id"])].copy()
            p_cols = {
                "avg": "avg", "woba": "woba", "slg": "slg", "iso": "iso",
                "k_pct": "k_pct", "bb_pct": "bb_pct", "hr_rate": "hr_pct",
            }
            for raw_hand, label in [("R", "vs_r"), ("L", "vs_l")]:
                hand_rows = sub[sub["split"] == f"vs {raw_hand}"]
                if hand_rows.empty:
                    continue
                row = hand_rows.iloc[0]
                entry = {}
                for src, dest in p_cols.items():
                    if src in row and pd.notna(row[src]):
                        entry[dest] = round(float(row[src]), 3 if dest not in ("k_pct", "bb_pct", "hr_pct") else 1)
                if entry:
                    pitcher_splits[label] = entry
    except Exception as e:
        print(f"Warning: pitcher_splits section failed for {pitcher_name}: {e}")

    return {
        "pitcher": pitcher_name,
        "season_stats": season_stats,
        "game_logs": game_logs,
        "splits": splits,
        "percentiles": percentiles,
        "opposing_hitters": opposing_hitters,
        "pitcher_splits": pitcher_splits,
    }


def get_hot_hitters() -> List[Dict[str, Any]]:
    """Batters hot over the last seven days.

    The window and thresholds (7 days, 18+ PA, .350+ BA) are applied in
    build_hot_hitters.py against the raw components, so this is a straight
    read -- filtering here would be applying a cut to already-cut data.
    """
    hot = get_mlb_data().get("hot_hitters", pd.DataFrame())
    if hot.empty:
        return []

    # Team lookup -- joined on player_id against a fresh daily roster
    # snapshot (get_mlb_rosters.py), not fuzzy name matching against a
    # game log. This is both more robust (no accent/suffix mismatches) and
    # more complete (every active player has a roster spot, regardless of
    # whether they've appeared in a recent box score).
    team_by_id: Dict[int, str] = {}
    rosters = get_mlb_data().get("mlb_rosters", pd.DataFrame())
    if not rosters.empty and "player_id" in rosters.columns and "team" in rosters.columns:
        team_by_id = rosters.dropna(subset=["player_id"]).set_index(
            rosters["player_id"].astype(int)
        )["team"].to_dict()

    # "AVG" rather than "BA" -- unambiguous next to OBP/SLG/OPS, and it
    # matches the "Average" column on the matchup table.
    display = {
        "player": "Player",
        "games": "G",
        "pa": "PA",
        "ab": "AB",
        "h": "H",
        "hr": "HR",
        "bb": "BB",
        "so": "SO",
        "ba": "AVG",
        "obp": "OBP",
        "slg": "SLG",
        "ops": "OPS",
        "woba": "wOBA",
        "k_pct": "K%",
        "bb_pct": "BB%",
    }
    cols = [c for c in display if c in hot.columns]
    out = hot[cols].rename(columns=display)
    if "player_id" in hot.columns:
        out["Team"] = hot["player_id"].apply(
            lambda pid: team_by_id.get(int(pid), "") if pd.notna(pid) else ""
        )
    else:
        out["Team"] = ""
    # Team right after Player, not tacked on at the end.
    ordered = ["Player", "Team"] + [c for c in out.columns if c not in ("Player", "Team")]
    out = out[ordered]

    # Nullable dtypes hold pd.NA, which is not JSON serializable.
    out = out.astype(object).where(out.notna(), "")
    return out.to_dict(orient="records")


_EXCLUDED_BOOKS = {
    "ballybet", "betonlineag", "betparx", "betr_us_dfs",
    "betrivers", "bovada", "dabble_us_dfs", "hardrockbet_oh", "mybookieag",
}


def get_mlb_props(team=None, player=None, market=None):
    """Kept as the MLB entry point; the implementation is shared with NFL in
    app/data/props.py, since get_props.py emits one schema for both sports."""
    from app.data.props import get_props
    return get_props("mlb", team, player, market)

def _ip_to_outs(ip: Any) -> int:
    """MLB's innings-pitched string ('1.2') is outs in disguise -- the part
    after the dot is outs-within-the-inning (0, 1 or 2), not tenths."""
    try:
        s = str(ip)
        whole, _, frac = s.partition(".")
        whole = int(whole) if whole else 0
        frac = int(frac[:1]) if frac else 0
        return whole * 3 + frac
    except Exception:
        return 0


def _outs_to_ip(outs: int) -> str:
    return f"{outs // 3}.{outs % 3}"


# The 30 real MLB teams, exactly as the Stats API names them (matches the
# "team" strings written into bullpen_logs.parquet, so lookups still line
# up). Hardcoded rather than read from data on purpose: a pitcher optioned
# to the minors after starting at the MLB level can get mistagged with his
# current (minor-league) affiliate during the appearance-log bootstrap --
# see get_bullpen_logs.py's bootstrap step -- which briefly put "Durham
# Bulls" in the dropdown. A fixed list can't pick up that kind of leak
# regardless of what ends up in the data files, and it also means this
# never requires a network fetch or file read at all.
MLB_TEAMS = [
    "Arizona Diamondbacks", "Athletics", "Atlanta Braves", "Baltimore Orioles",
    "Boston Red Sox", "Chicago Cubs", "Chicago White Sox", "Cincinnati Reds",
    "Cleveland Guardians", "Colorado Rockies", "Detroit Tigers", "Houston Astros",
    "Kansas City Royals", "Los Angeles Angels", "Los Angeles Dodgers", "Miami Marlins",
    "Milwaukee Brewers", "Minnesota Twins", "New York Mets", "New York Yankees",
    "Philadelphia Phillies", "Pittsburgh Pirates", "San Diego Padres", "San Francisco Giants",
    "Seattle Mariners", "St. Louis Cardinals", "Tampa Bay Rays", "Texas Rangers",
    "Toronto Blue Jays", "Washington Nationals",
]


def get_bullpen_teams() -> List[str]:
    """The 30 MLB teams, for the bullpen page's team selector."""
    return sorted(MLB_TEAMS)


def get_bullpen_status(team: str, days: int = 7) -> Dict[str, Any]:
    """Rolling workload for one team's bullpen, with season rate stats.

    Thin wrapper: loads the two source files once and hands off to
    _bullpen_status_for(), the shared per-team computation also used by
    get_bullpen_report() below to build every team's card in one pass
    without loading bullpen_logs.parquet / season_pitching_stats.parquet
    30 times over.
    """
    logs = get_mlb_data().get("bullpen_logs", pd.DataFrame())
    season = get_mlb_data().get("season_pitching_stats", pd.DataFrame())
    return _bullpen_status_for(logs, season, team, days)


def _bullpen_status_for(logs: pd.DataFrame, season: pd.DataFrame,
                         team: str, days: int = 7) -> Dict[str, Any]:
    """Rolling workload for one team's bullpen, with season rate stats.

    Day-by-day pitch counts/outings come from bullpen_logs.parquet (see
    get_bullpen_logs.py) -- that's the only source with per-appearance
    detail. ERA/WHIP/K%/BB%/throwing hand come from
    season_pitching_stats.parquet (see get_season_pitching_stats.py)
    instead of being computed from the rolling log, since a ~14-day window
    is too small a sample for a meaningful rate stat and starters.parquet
    excludes anyone with 0 games started.

    Takes the two source frames as arguments rather than loading them
    itself -- see get_bullpen_status() (one team) and get_bullpen_report()
    (all 30) above/below, which are the only two callers and load once
    between them.
    """
    empty = {
        "team": team, "days": [], "kpis": {}, "relievers": [],
        "freshness": "unknown", "recent_performance": None,
    }
    if logs.empty:
        return empty

    sub = logs[logs["team"].str.lower().str.strip() == _normalize(team)].copy()
    if sub.empty:
        return empty

    sub["date"] = pd.to_datetime(sub["date"], errors="coerce")
    sub = sub[sub["date"].notna()]
    sub["outs"] = sub["innings"].apply(_ip_to_outs)

    # ---- Role classification, done first so true starters can be excluded
    # from both the table and the KPI totals below. A rotation starter's
    # ordinary 90-100 pitch outing every five days always reads as "heavy"
    # workload on its own, which would make a perfectly rested bullpen look
    # tired. Openers stay in -- they're functionally a bullpen role even
    # though they're credited as the starter in the box score.
    OPENER_OUTS_THRESHOLD = 9  # 3.0 IP -- a "start" shorter than this reads as an opener/bulk role, not a true SP

    def recent_role(g: pd.DataFrame) -> str:
        """RP vs. (SP or OP), then SP vs. OP, decided from two different
        questions rather than one average.

        Whether he's *currently pitching in relief* comes from just the
        single most recent appearance -- averaging across recent starts let
        a pitcher's established rotation turns outweigh what he actually did
        in his very next outing (e.g. a starter who'd gone 5+ innings twice,
        then threw a one-off 4-inning relief outing, still averaged out to
        "SP" and got excluded from the table, hiding a real relief
        appearance). The latest appearance alone answers that correctly, and
        self-corrects the moment he starts again.

        But if his last appearance WAS a start, SP-vs-opener is a strategic
        role question, not a one-game one -- so that part still averages
        across his recent starts specifically (ignoring any relief outings
        mixed in), so a single truncated start (rain delay, early injury
        exit, a blowout hook) doesn't misclassify a real workhorse starter
        as an opener just because that one outing happened to be short.
        """
        g = g.sort_values("date")
        if not g.iloc[-1]["is_starter"]:
            return "RP"
        recent_starts = g[g["is_starter"]].tail(5)
        return "SP" if recent_starts["outs"].mean() >= OPENER_OUTS_THRESHOLD else "OP"

    role_by_id = {pid: recent_role(g) for pid, g in sub.groupby("pitcher_id")}
    sp_ids = {pid for pid, role in role_by_id.items() if role == "SP"}
    sub = sub[~sub["pitcher_id"].isin(sp_ids)]
    if sub.empty:
        return empty

    season_by_id: Dict[int, Dict[str, Any]] = {}
    if not season.empty:
        season_by_id = season.set_index("pitcher_id").to_dict(orient="index")

    # Anchored on the most recent date with real data, not today's calendar
    # date -- the daily pull only ever captures completed games (see the
    # zero-pitch filter in get_bullpen_logs.py, which drops a probable
    # starter's all-zero placeholder row for a game that hasn't been played
    # yet), so today's date simply won't be present in `sub` until there's
    # an actual finished appearance to report. Anchoring on today's calendar
    # date instead would always add an empty, incomplete "today" column --
    # showing 0 pitches (misread as fully fresh) and dragging down the
    # 3-day/7-day averages by dividing by a day that hasn't happened yet.
    last_date = sub["date"].max()
    day_list = pd.date_range(end=last_date, periods=days).normalize()

    # ---- KPI strip: rolling pitches/IP over 1, 3 and 7 days (bullpen arms only, SP excluded) ----
    #
    # Thresholds are the real bottom-25th/top-25th percentile of league-wide
    # bullpen workload for EACH window separately, not one fixed pair reused
    # everywhere. A longer window's typical range is naturally narrower than
    # a single day's -- averaging smooths out single-day spikes -- so the
    # 7-day cutoffs are tighter than the 1-day ones. Computed from
    # bullpen_logs.parquet across all 30 teams (~2 weeks of real data, since
    # that file is a rolling window, not a season archive -- these may
    # shift somewhat as more of the season accumulates naturally into it).
    WINDOW_THRESHOLDS = {
        1: (35, 80),
        3: (45, 70),
        7: (50, 65),
    }

    def window_totals(n: int) -> Dict[str, Any]:
        cutoff = last_date - pd.Timedelta(days=n - 1)
        w = sub[sub["date"] >= cutoff]
        outs = int(w["outs"].sum())
        pitches = int(w["pitches"].sum())

        per_day = pitches / n
        fresh_cutoff, tired_cutoff = WINDOW_THRESHOLDS[n]
        if per_day > tired_cutoff:
            level = "tired"
        elif per_day < fresh_cutoff:
            level = "fresh"
        else:
            level = "neutral"

        return {"pitches": pitches, "ip": _outs_to_ip(outs), "level": level}

    kpis = {"1_day": window_totals(1), "3_day": window_totals(3), "7_day": window_totals(7)}

    # ---- Per-pitcher rows (SP already excluded from `sub` above) ------------
    relievers = []
    for pid, g in sub.groupby("pitcher_id"):
        g = g.sort_values("date")
        name = g["pitcher"].iloc[-1]
        season_row = season_by_id.get(int(pid), {})

        role = role_by_id[pid]
        # Hand still comes from the season file -- bullpen_logs has no
        # handedness column, and throwing hand doesn't change mid-season.
        hand = season_row.get("throws", "") or ""

        era = season_row.get("era")
        whip = season_row.get("whip")
        k_pct = season_row.get("k_pct")
        bb_pct = season_row.get("bb_pct")

        by_date = {d.date(): row for d, row in g.set_index("date").iterrows()}
        day_cells = []
        for d in day_list:
            row = by_date.get(d.date())
            if row is None:
                day_cells.append(None)
            else:
                day_cells.append({
                    "pitches": int(row["pitches"]),
                    "ip": row["innings"],
                    "h": int(row["hits"]),
                    "er": int(row["earned_runs"]),
                    "bb": int(row["walks"]),
                })

        def clean(v):
            if v is None or (isinstance(v, float) and pd.isna(v)):
                return None
            return v.item() if hasattr(v, "item") else v

        relievers.append({
            "pitcher_id": int(pid),
            "name": name,
            "role": role,
            "hand": hand,
            "era": clean(era),
            "whip": clean(whip),
            "k_pct": clean(k_pct),
            "bb_pct": clean(bb_pct),
            "days": day_cells,
        })

    # Best ERA first -- lets you see at a glance whether the top relievers
    # are tired, which tells you the weaker arms are next in line. Missing
    # ERA (no season stats yet, e.g. just recalled) sorts to the bottom
    # rather than the top, since an unknown is not the same as a good one.
    relievers.sort(key=lambda r: r["era"] if r["era"] is not None else float("inf"))

    # Built from parts rather than strftime("%-m/%-d"), which is platform
    # specific and raises on Windows (see get_pitcher_matchup above).
    day_labels = [f"{d.strftime('%a')} {d.month}/{d.day}" for d in day_list]

    # Recent PERFORMANCE (ERA/WHIP), not just workload -- a well-rested
    # bullpen that's been getting hit hard is a different risk than a tired
    # one that's been lights-out, so both are surfaced. Reuses the exact
    # same reliever-only `sub` and `last_date` as the fatigue KPIs above,
    # so the two numbers can never disagree about who counts as a reliever.
    PERFORMANCE_WINDOW_DAYS = 7
    perf_cutoff = last_date - pd.Timedelta(days=PERFORMANCE_WINDOW_DAYS - 1)
    perf_window = sub[sub["date"] >= perf_cutoff]
    perf_outs = int(perf_window["outs"].sum())
    recent_performance = None
    if perf_outs > 0:
        earned_runs = pd.to_numeric(perf_window["earned_runs"], errors="coerce").fillna(0).sum()
        hits = pd.to_numeric(perf_window["hits"], errors="coerce").fillna(0).sum()
        walks = pd.to_numeric(perf_window["walks"], errors="coerce").fillna(0).sum()
        ip = perf_outs / 3
        recent_performance = {
            "days": PERFORMANCE_WINDOW_DAYS,
            "era": round(earned_runs * 9 / ip, 2),
            "whip": round((hits + walks) / ip, 2),
            "ip": round(ip, 1),
        }

    return {
        "team": team,
        "days": day_labels,
        "kpis": kpis,
        "relievers": relievers,
        "freshness": kpis["3_day"]["level"],
        "recent_performance": recent_performance,
    }


# Scan order for get_bullpen_report(): most in-need-of-attention first. Ties
# within a tier break by 3-day pitch count, heaviest first, so "tired" isn't
# just one undifferentiated bucket -- the bullpen that's thrown the most
# still floats to the very top of it.
_FRESHNESS_RANK = {"tired": 0, "neutral": 1, "fresh": 2, "unknown": 3}


def get_bullpen_report(days: int = 7) -> List[Dict[str, Any]]:
    """Every team's bullpen status in one call, sorted tired-first.

    Was: a per-team page where seeing who around the league is gassed meant
    clicking through all 30 teams' dropdown entries one at a time. That's
    backwards for what this data is actually good for -- workload is a
    scan, not a lookup, the same reason Pitcher Daily Report shows every
    starting pitcher on one page instead of a per-pitcher picker.

    Loads bullpen_logs.parquet / season_pitching_stats.parquet ONCE and
    reuses _bullpen_status_for() (the exact same per-team computation
    get_bullpen_status() calls) for each of the 30 teams, rather than
    calling that public function 30 times over and re-fetching/re-filtering
    the same two source frames on every single one.
    """
    logs = get_mlb_data().get("bullpen_logs", pd.DataFrame())
    season = get_mlb_data().get("season_pitching_stats", pd.DataFrame())
    if logs.empty:
        return []

    reports = []
    for team in MLB_TEAMS:
        report = _bullpen_status_for(logs, season, team, days)
        # _bullpen_status_for()'s own "empty" sentinel has no relievers --
        # a team genuinely absent from bullpen_logs.parquet (not just having
        # a quiet week), which a blank card wouldn't explain. Skipped rather
        # than shown, same as get_bullpen_status() already treating it as
        # "no data" rather than "zero workload".
        if report["relievers"]:
            reports.append(report)

    def sort_key(r: Dict[str, Any]) -> tuple:
        rank = _FRESHNESS_RANK.get(r["freshness"], 3)
        pitches_3day = r["kpis"].get("3_day", {}).get("pitches", 0)
        return (rank, -pitches_3day)

    reports.sort(key=sort_key)
    return reports


# ---------------------------------------------------------------------------
# Pitcher Daily Report -- one row per starting pitcher across the whole
# day's slate, combining recent-form averages with today's opposing
# lineup's toughness. No lines/odds yet (deferred until the sportsbook data
# question is settled) -- this version shows recent averages and opponent
# context only, matching the original Excel report with the props-dependent
# columns removed.
# ---------------------------------------------------------------------------

# Fixed, absolute thresholds -- NOT percentile-based (the flags previously
# computed in build_matchups.py used "top/bottom 25% of TODAY'S specific
# slate," which shifts day to day depending on who else is playing; these
# mean the same thing every day regardless of the rest of the slate).
HITTER_FLAG_THRESHOLDS = {
    "high_k_hitter": ("split_k_pct", "ge", 20),
    "high_bb_hitter": ("split_bb_pct", "ge", 8.5),
    "high_avg_hitter": ("split_avg", "ge", 0.270),
    "low_avg_hitter": ("split_avg", "le", 0.230),
    "high_iso_hitter": ("split_iso", "ge", 0.200),
    # No exact threshold given for wOBA -- .370 is a placeholder (a commonly
    # cited "excellent hitter" cutoff on the standard wOBA scale). Trivial
    # one-line change once a real number is confirmed.
    "high_woba_hitter": ("split_woba", "ge", 0.370),
}


# ── MLB Matchup: team records, recent form, head-to-head ───────────────────
LAST_N_FORM_GAMES = 10


def _team_games(schedule: pd.DataFrame, team: str) -> pd.DataFrame:
    """Every completed game a team has played, sorted chronologically,
    with that team's own perspective (runs_for/runs_against/won) attached
    -- so a caller doesn't need to separately handle the home/away cases."""
    home = schedule[schedule["home_team"] == team].copy()
    home["runs_for"], home["runs_against"] = home["home_score"], home["away_score"]
    away = schedule[schedule["away_team"] == team].copy()
    away["runs_for"], away["runs_against"] = away["away_score"], away["home_score"]

    games = pd.concat([home, away], ignore_index=True)
    if games.empty:
        return games
    games["won"] = games["runs_for"] > games["runs_against"]
    games["date"] = pd.to_datetime(games["date"], errors="coerce")
    return games.sort_values("date")


def get_team_record_and_form(team: str, last_n: int = LAST_N_FORM_GAMES) -> Dict[str, Any]:
    """Season record plus recent form (last N games record + run
    differential) for one team, both derived from the same completed-games
    source -- a team's full-season strength and its current trajectory are
    often genuinely different stories (a good team playing poorly lately,
    or vice versa), so both are surfaced rather than just the season line.
    """
    schedule = get_mlb_data().get("schedule_results", pd.DataFrame())
    if schedule.empty:
        return {"team": team, "wins": None, "losses": None, "last_n": None}

    games = _team_games(schedule, team)
    if games.empty:
        return {"team": team, "wins": None, "losses": None, "last_n": None}

    wins = int(games["won"].sum())
    losses = int(len(games) - wins)

    recent = games.tail(last_n)
    recent_wins = int(recent["won"].sum())
    recent_losses = int(len(recent) - recent_wins)
    run_diff = round(float((recent["runs_for"] - recent["runs_against"]).mean()), 1) if not recent.empty else None

    return {
        "team": team,
        "wins": wins,
        "losses": losses,
        "last_n": {
            "games": len(recent),
            "wins": recent_wins,
            "losses": recent_losses,
            "avg_run_diff": run_diff,
        },
    }


def get_head_to_head(team_a: str, team_b: str) -> Dict[str, Any]:
    """This season's completed games between two specific teams -- record
    and average runs scored by each, from the same completed-games source
    used for team_record_and_form. Team-name matching is exact (both teams
    already come from the same MLB Stats API naming convention used
    throughout this file), so no normalization is needed here."""
    schedule = get_mlb_data().get("schedule_results", pd.DataFrame())
    if schedule.empty:
        return {"team_a": team_a, "team_b": team_b, "games": 0}

    matchups = schedule[
        ((schedule["home_team"] == team_a) & (schedule["away_team"] == team_b))
        | ((schedule["home_team"] == team_b) & (schedule["away_team"] == team_a))
    ]
    if matchups.empty:
        return {"team_a": team_a, "team_b": team_b, "games": 0}

    team_a_runs, team_b_runs, team_a_wins = [], [], 0
    for _, g in matchups.iterrows():
        if g["home_team"] == team_a:
            a_score, b_score = g["home_score"], g["away_score"]
        else:
            a_score, b_score = g["away_score"], g["home_score"]
        team_a_runs.append(a_score)
        team_b_runs.append(b_score)
        if a_score > b_score:
            team_a_wins += 1

    games = len(matchups)
    return {
        "team_a": team_a,
        "team_b": team_b,
        "games": games,
        "team_a_wins": team_a_wins,
        "team_b_wins": games - team_a_wins,
        "team_a_avg_runs": round(sum(team_a_runs) / games, 1),
        "team_b_avg_runs": round(sum(team_b_runs) / games, 1),
    }


def get_mlb_todays_matchups() -> List[Dict[str, Any]]:
    """Today's actual scheduled games, not an arbitrary pick-any-two-teams
    list -- comparing two teams that aren't even playing each other isn't
    a real matchup. One row per game_pk is enough to know both sides (each
    row already carries both "team" and "opponent" regardless of whether
    that specific game's opponent pitcher has been announced yet)."""
    probable = get_mlb_data().get("probable_starters", pd.DataFrame())
    if probable.empty:
        return []

    matchups = []
    for game_pk, group in probable.groupby("game_pk"):
        row = group.iloc[0]
        if "is_home" not in row or pd.isna(row.get("is_home")):
            continue
        home, away = (row["team"], row["opponent"]) if row["is_home"] else (row["opponent"], row["team"])
        matchups.append({"game_pk": int(game_pk), "away_team": away, "home_team": home, "label": f"{away} @ {home}"})

    return sorted(matchups, key=lambda m: m["label"])


def _team_starter_and_splits(team: str) -> Optional[Dict[str, Any]]:
    """Today's probable starter for one team, plus their season AVG/K%/BB%/
    wOBA/ISO split vs LHB and vs RHB (pitcher_splits.parquet) -- shown as
    two columns rather than one blended number, since a matchup page's
    whole point is knowing how this pitcher fares against the specific
    mix of hitters he's facing today, and a blended number throws that
    away (a pitcher dominant against one side and mediocre against the
    other looks identical to an average pitcher on a blended figure)."""
    probable = get_mlb_data().get("probable_starters", pd.DataFrame())
    if probable.empty:
        return None
    match = probable[probable["team"] == team]
    if match.empty:
        return None
    row = match.iloc[0]
    pitcher_name, pitcher_id = row.get("pitcher"), row.get("pitcher_id")

    splits_source = get_mlb_data().get("pitcher_splits", pd.DataFrame())
    vs_l, vs_r = None, None
    if not splits_source.empty and pd.notna(pitcher_id):
        sub = splits_source[splits_source["player_id"] == int(pitcher_id)]
        cols = {"avg": "avg", "k_pct": "k_pct", "bb_pct": "bb_pct", "woba": "woba", "iso": "iso"}
        for raw_hand, target in [("L", "vs_l"), ("R", "vs_r")]:
            hand_row = sub[sub["split"] == f"vs {raw_hand}"]
            if hand_row.empty:
                continue
            r = hand_row.iloc[0]
            entry = {dest: round(float(r[src]), 3 if dest in ("avg", "woba", "iso") else 1)
                     for src, dest in cols.items() if src in r and pd.notna(r[src])}
            if target == "vs_l":
                vs_l = entry
            else:
                vs_r = entry

    return {"pitcher": pitcher_name, "vs_l": vs_l, "vs_r": vs_r}


def _team_lineup_averages(team: str) -> Optional[Dict[str, Any]]:
    """Straight (not plate-appearance-weighted) average of today's actual
    starting lineup's AVG/wOBA/ISO/BB%/K%, already split vs. the specific
    opposing starter's throwing hand by daily_matchups.parquet itself.
    Straight average rather than PA-weighted deliberately: today's 9
    starters will each get roughly the same 3-4 at-bats in this one game,
    so the season-long-imbalance problem PA-weighting exists to solve
    doesn't apply here. Returns None (not zeros) until the lineup posts --
    daily_matchups.parquet has no rows for a team at all until then."""
    matchups = get_mlb_data().get("matchups", pd.DataFrame())
    if matchups.empty:
        return None
    sub = matchups[matchups["team"] == team]
    if sub.empty:
        return None

    cols = {"split_avg": "avg", "split_woba": "woba", "split_iso": "iso", "split_k_pct": "k_pct", "split_bb_pct": "bb_pct"}
    out = {}
    for src, dest in cols.items():
        if src not in sub.columns:
            continue
        vals = pd.to_numeric(sub[src], errors="coerce").dropna()
        if len(vals) > 0:
            out[dest] = round(float(vals.mean()), 3 if dest in ("avg", "woba", "iso") else 1)
    out["batters"] = len(sub)
    # `hits_from` (not `bats`) -- it's the side each batter actually stands on
    # for THIS game, already resolved for switch hitters (see
    # build_matchups.py), which is the same column every split_* average
    # above was computed against. A blended "straight average" line hides
    # whether that number is nine same-handed bats or a genuine mix, which
    # matters when judging how much a single-handed pitcher/reliever
    # actually neutralizes this lineup.
    if "hits_from" in sub.columns:
        hand_counts = sub["hits_from"].value_counts()
        out["lh_count"] = int(hand_counts.get("L", 0))
        out["rh_count"] = int(hand_counts.get("R", 0))
    return out


def _team_hitting_vs_handedness(team: str, opponent_pitcher_id: Optional[int]) -> Optional[Dict[str, Any]]:
    """This team's own wOBA vs. the specific throwing hand of the
    opponent's starter -- season-pooled (2025+2026, same convention as
    pitcher_splits.parquet) and last 30 days, from
    build_team_hitting_splits.py. Available early (doesn't need a posted
    lineup), unlike the today's-lineup averages section elsewhere on this
    page -- this is a team-wide figure, not specific to today's 9 starters.
    """
    if pd.isna(opponent_pitcher_id):
        return None
    starters_df = get_mlb_data().get("starters", pd.DataFrame())
    if starters_df.empty:
        return None
    match = starters_df[starters_df["pitcher_id"] == int(opponent_pitcher_id)]
    if match.empty:
        return None
    throws = match.iloc[0].get("throws")
    if throws not in ("L", "R"):
        return None

    splits_source = get_mlb_data().get("team_hitting_splits", pd.DataFrame())
    if splits_source.empty:
        return None
    sub = splits_source[(splits_source["team"] == team) & (splits_source["split"] == f"vs {throws}")]
    if sub.empty:
        return None

    out = {"vs_hand": throws}
    for window in ("season", "last_30_days"):
        row = sub[sub["window"] == window]
        if not row.empty:
            out[window] = {"woba": float(row.iloc[0]["woba"]), "pa": int(row.iloc[0]["pa"])}
    return out if len(out) > 1 else None


def get_mlb_team_matchup(team_a: str, team_b: str) -> Dict[str, Any]:
    """Combined record/recent-form, starting pitcher splits, bullpen
    status, team-wide hitting-vs-handedness, and lineup averages for both
    teams, plus head-to-head -- one response so the frontend doesn't need
    eight separate round trips. Each team's pitcher/lineup/hitting context
    is keyed off the OTHER team (a team's own lineup faces the OPPONENT's
    pitcher, not its own)."""
    team_a_pitcher = _team_starter_and_splits(team_a)
    team_b_pitcher = _team_starter_and_splits(team_b)
    probable = get_mlb_data().get("probable_starters", pd.DataFrame())

    def pitcher_id_for(team: str) -> Optional[int]:
        if probable.empty:
            return None
        match = probable[probable["team"] == team]
        return match.iloc[0].get("pitcher_id") if not match.empty else None

    return {
        "team_a": get_team_record_and_form(team_a),
        "team_b": get_team_record_and_form(team_b),
        "head_to_head": get_head_to_head(team_a, team_b),
        "team_a_pitcher": team_a_pitcher,
        "team_b_pitcher": team_b_pitcher,
        "team_a_bullpen": get_bullpen_status(team_a),
        "team_b_bullpen": get_bullpen_status(team_b),
        "team_a_lineup_vs_b": _team_lineup_averages(team_a),
        "team_b_lineup_vs_a": _team_lineup_averages(team_b),
        "team_a_hitting_vs_b": _team_hitting_vs_handedness(team_a, pitcher_id_for(team_b)),
        "team_b_hitting_vs_a": _team_hitting_vs_handedness(team_b, pitcher_id_for(team_a)),
    }


def get_pitcher_daily_report() -> Dict[str, Any]:
    """One row per starting pitcher with a game today: recent-form averages
    (last up to 10 starts) plus today's opposing lineup's aggregate
    toughness and count of standout hitters, using fixed thresholds rather
    than the percentile-based flags build_matchups.py computes for other
    purposes.

    Driven by probable_starters.parquet (today's announced starters,
    independent of lineups) rather than daily_matchups.parquet (which has
    ZERO rows until a lineup has actually posted) -- a pitcher's own recent
    form and the fact that they're starting today are both known well
    before the lineup, so every starter shows up immediately. Only the
    opposing-lineup columns (opp_avg, opp_k_pct, the high_*_hitter counts)
    come through as None for a given pitcher until that specific game's
    lineup exists, rather than the whole pitcher not appearing at all.
    """
    data = get_mlb_data()

    probable = data.get("probable_starters", pd.DataFrame())
    logs = data.get("pitcher_logs", pd.DataFrame())
    matchups = data.get("matchups", pd.DataFrame())

    if probable.empty:
        return {"date": None, "pitchers": []}

    today = str(probable["date"].iloc[0]) if "date" in probable.columns else None

    # ---- Recent-form averages, last up to 10 starts per pitcher ----------
    recent_avg = pd.DataFrame()
    if not logs.empty:
        logs = logs.copy()
        logs["date"] = pd.to_datetime(logs["date"], errors="coerce")
        logs = logs[logs["date"].notna()].sort_values(["pitcher_id", "date"], ascending=[True, False])
        logs["game_num"] = logs.groupby("pitcher_id").cumcount() + 1
        recent = logs[logs["game_num"] <= 10].copy()
        recent["outs"] = recent["innings"].apply(_ip_to_outs)

        recent_avg = recent.groupby(["pitcher_id", "pitcher"], as_index=False).agg(
            games=("game_num", "max"),
            avg_outs=("outs", "mean"),
            avg_hits=("hits", "mean"),
            avg_er=("earned_runs", "mean"),
            avg_so=("strikeouts", "mean"),
            avg_bb=("walks", "mean"),
        )

    # ---- Today's opposing lineup: toughness + standout-hitter counts -----
    # Deliberately allowed to stay empty if no lineup has posted for anyone
    # yet -- the merge below then leaves these columns as None rather than
    # dropping any pitcher from the report.
    matchup_agg = pd.DataFrame()
    if not matchups.empty:
        m = matchups.copy()
        for flag_col, (source_col, op, threshold) in HITTER_FLAG_THRESHOLDS.items():
            if source_col not in m.columns:
                m[flag_col] = 0
                continue
            vals = pd.to_numeric(m[source_col], errors="coerce")
            m[flag_col] = (vals >= threshold if op == "ge" else vals <= threshold).fillna(False).astype(int)

        matchup_agg = m.groupby("pitcher", as_index=False).agg(
            opp_avg=("split_avg", "mean"),
            opp_k_pct=("split_k_pct", "mean"),
            opp_bb_pct=("split_bb_pct", "mean"),
            high_k_hitter=("high_k_hitter", "sum"),
            high_bb_hitter=("high_bb_hitter", "sum"),
            high_avg_hitter=("high_avg_hitter", "sum"),
            low_avg_hitter=("low_avg_hitter", "sum"),
            high_iso_hitter=("high_iso_hitter", "sum"),
            high_woba_hitter=("high_woba_hitter", "sum"),
        )

    # Driving table: every announced starter today, regardless of whether
    # anything else below has data for them yet.
    combined = probable[["pitcher", "team", "opponent"]].drop_duplicates(subset=["pitcher"]).copy()
    if not recent_avg.empty:
        combined = combined.merge(recent_avg.drop(columns=["pitcher_id"]), on="pitcher", how="left")
    if not matchup_agg.empty:
        combined = combined.merge(matchup_agg, on="pitcher", how="left")

    def clean(v, digits=1):
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return None
        return round(float(v), digits)

    def clean_int(v):
        return int(v) if pd.notna(v) else None

    out = []
    for _, r in combined.iterrows():
        out.append({
            "player": r["pitcher"],
            "team": r["team"],
            "opposing_team": r["opponent"],
            "games": clean_int(r.get("games")) or 0,
            "avg_outs": clean(r.get("avg_outs")),
            "avg_hits": clean(r.get("avg_hits")),
            "avg_er": clean(r.get("avg_er")),
            "avg_so": clean(r.get("avg_so")),
            "avg_bb": clean(r.get("avg_bb")),
            "opp_avg": clean(r.get("opp_avg"), 3),
            "opp_k_pct": clean(r.get("opp_k_pct")),
            "opp_bb_pct": clean(r.get("opp_bb_pct")),
            "high_k_hitter": clean_int(r.get("high_k_hitter")),
            "high_bb_hitter": clean_int(r.get("high_bb_hitter")),
            "high_avg_hitter": clean_int(r.get("high_avg_hitter")),
            "low_avg_hitter": clean_int(r.get("low_avg_hitter")),
            "high_iso_hitter": clean_int(r.get("high_iso_hitter")),
            "high_woba_hitter": clean_int(r.get("high_woba_hitter")),
        })

    return {"date": today, "pitchers": out}


# ---------------------------------------------------------------------------
# Hit Rate Sheet -- bulk per-market scan across every MLB batter/pitcher
# line currently priced, rather than the one-player-at-a-time shape of
# get_pitcher_matchup() above. See app/data/hit_rate.py for the shared,
# sport-agnostic grading/window-splitting helpers this reuses; everything
# below is just wiring MLB's own data sources into that shape.
# ---------------------------------------------------------------------------

MLB_RECENT_GAMES = RECENT_WINDOW["mlb"]

# Hit-rate-sheet market key -> batter_logs.parquet column, or a derivation
# function taking one game's row and returning a float.
#
# Sourced from the MLB Stats API's own hitting game log (get_batter_logs.py),
# not the Statcast-based daily_components file: runs, RBIs and stolen bases
# have no equivalent anywhere in Statcast event data, and totalBases comes
# back as a real field here instead of being reconstructed from extra-base
# hits (that reconstruction is still what build_hot_hitters.py does for its
# own, unrelated rolling-average feature -- this just doesn't need to).
#
# Batter markets are spelled `batter_*` to disambiguate from the pitcher
# markets below (bare "strikeouts" is ambiguous between "batter struck
# out" and "pitcher recorded a strikeout") -- matching the same prefix
# get_props.py itself uses before stripping it for the raw feed (see
# PropsExplorer.tsx's MARKET_LABELS comment).
#
# first_home_run is a real sportsbook market but needs play-order (who
# homered first), which a per-game total can't tell you -- left out rather
# than approximated. Everything else the API's hitting stat carries is here.
MLB_BATTER_MARKET_STAT: Dict[str, Any] = {
    "batter_hits": "hits",
    "batter_home_runs": "home_runs",
    "batter_doubles": "doubles",
    "batter_walks": "walks",
    "batter_strikeouts": "strikeouts",
    "batter_rbis": "rbi",
    "batter_runs_scored": "runs",
    "batter_stolen_bases": "stolen_bases",
    "batter_total_bases": "total_bases",
    # Not a field the API returns directly -- back it out from hits minus
    # the extra-base-hit types, same idea as total_bases used to need.
    "batter_singles": lambda r: r["hits"] - r["doubles"] - r["triples"] - r["home_runs"],
    "batter_hits_runs_rbis": lambda r: r["hits"] + r["runs"] + r["rbi"],
}

# Hit-rate-sheet market key -> pitcher_logs.parquet column (or derivation).
# Already fully gradeable today -- pitcher_logs.parquet is fetched for the
# Pitcher Matchup page above, no new data plumbing needed for these.
MLB_PITCHER_MARKET_STAT: Dict[str, Any] = {
    "pitcher_earned_runs": "earned_runs",
    "pitcher_strikeouts": "strikeouts",
    "pitcher_hits_allowed": "hits",
    "pitcher_walks": "walks",
    "pitcher_outs": lambda r: _ip_to_outs(r["innings"]),
    # A Yes/No market ("did he record a win"), not an over/under line --
    # graded the same way as the numeric markets by treating "yes" as 1.0
    # and grading against an effective line of 1 (see get_mlb_hit_rate_sheet).
    "pitcher_record_a_win": lambda r: 1.0 if r["wins"] == 1 else 0.0,
}

MLB_MARKET_STAT_MAP: Dict[str, Any] = {**MLB_BATTER_MARKET_STAT, **MLB_PITCHER_MARKET_STAT}

# Yes/No markets graded against a fixed effective line rather than whatever
# (usually missing) numeric line get_props.py's feed carries for them.
_MLB_YES_NO_MARKETS = {"pitcher_record_a_win"}

# Hit-rate-sheet market key -> the market key get_props.py actually writes.
# Batter markets there have their `batter_` prefix already stripped;
# pitcher markets keep theirs -- same convention PropsExplorer.tsx's
# MARKET_LABELS comment documents on the frontend side.
_MLB_PROPS_MARKET_KEY: Dict[str, str] = {k: k.replace("batter_", "", 1) for k in MLB_BATTER_MARKET_STAT}
_MLB_PROPS_MARKET_KEY.update({k: k for k in MLB_PITCHER_MARKET_STAT})

# Columns get_props()'s pivot carries that are never a sportsbook -- kept in
# sync with props.py's own pivot output rather than PropsExplorer.tsx's
# META_COLS (a larger, cross-sport superset), since this only needs to
# match what get_props("mlb") itself can actually emit.
_MLB_PROPS_META_COLS = {"line_id", "player", "market", "line", "fetched_at", "commence_time", "home_team", "away_team", "is_live"}


def _stat_value(row, spec) -> float:
    try:
        val = spec(row) if callable(spec) else row.get(spec)
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return 0.0
        return float(val)
    except Exception:
        return 0.0


def _is_number(v) -> bool:
    try:
        f = float(v)
        return not math.isnan(f)
    except (TypeError, ValueError):
        return False


def _batter_logs_for_market(market: str) -> pd.DataFrame:
    """One row per (player_id, game_date) for one batter market, sorted
    ascending by date, with a `stat_value` column already computed --
    ready to feed straight into split_season_recent()/grade_over_under().

    Sourced from batter_logs.parquet (see get_mlb_data(), get_batter_logs.py)
    rather than a second per-player lookup mechanism -- this IS the
    bulk-shaped internal helper the Hit Rate Sheet spec calls for, scanning
    every batter at once instead of one player_id at a time.
    """
    spec = MLB_BATTER_MARKET_STAT[market]
    logs = get_mlb_data().get("batter_logs", pd.DataFrame())
    if logs.empty:
        return pd.DataFrame()

    logs = logs.copy()
    logs["date"] = pd.to_datetime(logs["date"], errors="coerce")
    logs = logs[logs["date"].notna()].sort_values("date")

    if callable(spec):
        logs["stat_value"] = logs.apply(lambda r: _stat_value(r, spec), axis=1)
    else:
        logs["stat_value"] = pd.to_numeric(logs[spec], errors="coerce").fillna(0.0)

    return logs.rename(columns={"date": "game_date"})[["player_id", "game_date", "stat_value"]]


def _pitcher_logs_for_market(market: str) -> pd.DataFrame:
    """Same (player_id, game_date, stat_value) shape as
    _batter_logs_for_market() above, sourced from pitcher_logs.parquet --
    already fetched and already used by get_pitcher_matchup()'s game_logs
    section."""
    spec = MLB_PITCHER_MARKET_STAT[market]
    logs = get_mlb_data().get("pitcher_logs", pd.DataFrame())
    if logs.empty:
        return pd.DataFrame()

    logs = logs.copy()
    logs["date"] = pd.to_datetime(logs["date"], errors="coerce")
    logs = logs[logs["date"].notna()].sort_values("date")

    if callable(spec):
        logs["stat_value"] = logs.apply(lambda r: _stat_value(r, spec), axis=1)
    else:
        logs["stat_value"] = pd.to_numeric(logs[spec], errors="coerce").fillna(0.0)

    return logs.rename(columns={"pitcher_id": "player_id", "date": "game_date"})[
        ["player_id", "game_date", "stat_value"]
    ]


# The Hit Rate Sheet's default view scans every market at once, and typing
# in the player box doesn't narrow that -- the player filter is applied per
# props row further down, after the game log for a market has already been
# built. Without caching, that means re-parsing dates, re-sorting, and (for
# derived markets) re-running a row-wise .apply() over the FULL season for
# every batter or pitcher, for every one of ~17 markets, on every request --
# including every keystroke in the search box. The underlying parquet is
# already cached by get_mlb_data() (MLB_TTL), but the per-market grouping
# done here was rebuilt from scratch each time regardless. Caching it at
# this level means it is computed once per market per MLB_TTL window and
# every request after that is a dict lookup.
@ttl_cache(MLB_TTL)
def _batter_values_by_player(market: str) -> Dict[Any, List[float]]:
    log = _batter_logs_for_market(market)
    if log.empty:
        return {}
    return {pid: g["stat_value"].tolist() for pid, g in log.groupby("player_id")}


@ttl_cache(MLB_TTL)
def _pitcher_values_by_player(market: str) -> Dict[Any, List[float]]:
    log = _pitcher_logs_for_market(market)
    if log.empty:
        return {}
    return {pid: g["stat_value"].tolist() for pid, g in log.groupby("player_id")}


# Same idea as the two functions above -- name_to_id/team_by_name only
# depend on which roster/starters table a market reads (batter vs pitcher),
# not on the market itself, so without this every one of the ~11 batter (or
# ~6 pitcher) markets in the default "All Markets" scan was rebuilding the
# exact same two dicts from the exact same rosters/starters frame.
@ttl_cache(MLB_TTL)
def _mlb_batter_name_lookup() -> "tuple[Dict[str, Any], Dict[str, str]]":
    rosters = get_mlb_data().get("mlb_rosters", pd.DataFrame())
    if rosters.empty or "player_id" not in rosters.columns or "player" not in rosters.columns:
        return {}, {}
    name_to_id = dict(zip(rosters["player"].astype(str).apply(_normalize), rosters["player_id"]))
    team_by_name = (
        dict(zip(rosters["player"].astype(str).apply(_normalize), rosters["team"]))
        if "team" in rosters.columns else {}
    )
    return name_to_id, team_by_name


@ttl_cache(MLB_TTL)
def _mlb_pitcher_name_lookup() -> "tuple[Dict[str, Any], Dict[str, str]]":
    starters_df = get_mlb_data().get("starters", pd.DataFrame())
    if starters_df.empty or "pitcher_id" not in starters_df.columns or "pitcher" not in starters_df.columns:
        return {}, {}
    name_to_id = dict(zip(starters_df["pitcher"].astype(str).apply(_normalize), starters_df["pitcher_id"]))
    team_by_name = (
        dict(zip(starters_df["pitcher"].astype(str).apply(_normalize), starters_df["team"]))
        if "team" in starters_df.columns else {}
    )
    return name_to_id, team_by_name


@ttl_cache(MLB_TTL)
def _mlb_game_lines_lookup() -> Dict[tuple, dict]:
    """(home_team, away_team) -> that game's row in game_lines.parquet
    (get_game_lines.py, refreshed once a day), for the Hit Rate Sheet's
    Game Line / Total columns. Built once per MLB_TTL window instead of
    once per output row -- same discipline as the name/team lookups above.

    Keyed by the same full Odds-API team-name strings get_props() itself
    already carries as home_team/away_team (both come from the same Odds
    API), so no name-format bridging is needed here -- unlike NFL, where
    the schedule's nflverse abbreviations require NFL_TEAM_ABBR (see
    app/data/nfl.py).
    """
    lines = get_mlb_data().get("game_lines", pd.DataFrame())
    if lines.empty or "home_team" not in lines.columns or "away_team" not in lines.columns:
        return {}
    return {(r["home_team"], r["away_team"]): r for r in lines.to_dict(orient="records")}


def get_mlb_hit_rate_sheet_players() -> List[str]:
    """Distinct player names with at least one live prop right now -- the
    actual searchable universe for the Hit Rate Sheet's Player field, not
    every batter/pitcher who's ever logged a game. Sourced from
    get_props("mlb"), the exact same call the sheet itself makes, so this
    list and the sheet can never disagree about who's actually on it."""
    from app.data.props import get_props
    props_rows = get_props("mlb")
    if not props_rows:
        return []
    names = {str(r.get("player", "")).strip() for r in props_rows if r.get("player")}
    return sorted(names)


def get_mlb_hit_rate_sheet(
    market: Optional[str] = None,
    min_pct: float = 0,
    min_odds: Optional[float] = None,
    period: str = "season",
    player: Optional[str] = None,
    books: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Hit Rate Sheet: one row per (player, market, line) MLB currently has
    a live sportsbook price for.

    Driven by get_props("mlb") -- the SAME current-lines source the Props
    page itself reads -- rather than by scanning every batter/pitcher game
    log row for every conceivable line: a market only belongs on this sheet
    if a book is actually offering it today, and the line to grade against,
    plus the best-price/book pair, both come directly from that one row.

    `books` is an optional CSV of sportsbook column names (as get_props()
    spells them, e.g. "draftkings,fanduel"); when given, best_odds/best_book
    are computed only across that subset -- mirroring the sheet's own Books
    toggle row, where checking/unchecking a book changes what "best odds"
    means rather than just hiding a column. Omit it (or send every book) to
    get the best price across every book get_props() returns.
    """
    from app.data.props import get_props

    markets = (
        [market] if market and market != "all" and market in MLB_MARKET_STAT_MAP
        else list(MLB_MARKET_STAT_MAP.keys())
    )

    props_rows = get_props("mlb")
    if not props_rows:
        return []
    # all_book_cols always goes into each row's odds_by_book (below) so the
    # frontend's Books toggle can recompute best-odds/hidden-count for any
    # subset of books it checks without a second request -- `books` here
    # only narrows best_odds/best_book/the row-presence check themselves,
    # for a caller that wants that subset applied server-side instead.
    all_book_cols = [c for c in props_rows[0].keys() if c not in _MLB_PROPS_META_COLS]
    book_cols = all_book_cols
    if books:
        wanted = {b.strip().lower() for b in books.split(",") if b.strip()}
        book_cols = [c for c in all_book_cols if c.lower() in wanted]

    # Grouped once instead of re-scanning the full props feed once per
    # market below -- cheap either way, but "All Markets" (the default
    # view) means up to len(MLB_MARKET_STAT_MAP) passes over the same list
    # otherwise.
    rows_by_market: Dict[str, List[dict]] = {}
    for row in props_rows:
        rows_by_market.setdefault(str(row.get("market", "")).lower(), []).append(row)

    name_to_id_batter, team_by_name_batter = _mlb_batter_name_lookup()
    name_to_id_pitcher, team_by_name_pitcher = _mlb_pitcher_name_lookup()
    game_lines_by_matchup = _mlb_game_lines_lookup()

    out: List[Dict[str, Any]] = []
    for mkt in markets:
        props_market_key = _MLB_PROPS_MARKET_KEY[mkt]
        # Alternate lines (e.g. "hits_alternate") are a SEPARATE market in
        # the raw feed from the standard one ("hits"), even though they're
        # the same stat -- a book posts them as different products. Shawn
        # wants both on the sheet: the standard line (usually 1.5 Hits) AND
        # whatever alt lines a book also offers (0.5, 2.5, ...), each as its
        # own row. The two buckets commonly overlap on the SAME player+line
        # (a book's alt-lines market often re-quotes its own standard line
        # alongside the others), so alt rows are only added for a
        # (player, line) not already covered by the standard market --
        # otherwise every alt-covered player would show a duplicate row for
        # their standard line.
        primary_rows = rows_by_market.get(props_market_key, [])
        alt_rows = rows_by_market.get(f"{props_market_key}_alternate", [])
        if alt_rows:
            covered = {(r.get("player"), r.get("line")) for r in primary_rows}
            candidate_rows = primary_rows + [
                r for r in alt_rows if (r.get("player"), r.get("line")) not in covered
            ]
        else:
            candidate_rows = primary_rows
        if not candidate_rows:
            continue

        is_batter_market = mkt in MLB_BATTER_MARKET_STAT
        by_player_id = _batter_values_by_player(mkt) if is_batter_market else _pitcher_values_by_player(mkt)
        if not by_player_id:
            continue

        name_to_id = name_to_id_batter if is_batter_market else name_to_id_pitcher
        team_by_name = team_by_name_batter if is_batter_market else team_by_name_pitcher

        for row in candidate_rows:
            player_name = str(row.get("player", "") or "")
            if not player_name:
                continue
            if player and player.lower() not in player_name.lower():
                continue

            pid = name_to_id.get(_normalize(player_name))
            if pid is None or pid not in by_player_id:
                continue

            values = by_player_id[pid]
            windows = split_season_recent(values, MLB_RECENT_GAMES)

            if mkt in _MLB_YES_NO_MARKETS:
                line_f = 1.0
            else:
                line_raw = row.get("line")
                if not _is_number(line_raw):
                    continue
                line_f = float(line_raw)

            season_grade = grade_over_under(windows["season"], line_f)
            recent_grade = grade_over_under(windows["recent"], line_f)
            selected_pct = season_grade["pct"] if period == "season" else recent_grade["pct"]
            if selected_pct * 100 < min_pct:
                continue

            offers = [(b, row.get(b)) for b in book_cols]
            offers = [(b, float(o)) for b, o in offers if _is_number(o)]
            if not offers:
                continue
            best_book, best_odds = max(offers, key=lambda x: x[1])
            if min_odds is not None and best_odds < min_odds:
                continue

            odds_by_book = {
                b: int(round(float(row.get(b))))
                for b in all_book_cols if _is_number(row.get(b))
            }

            team = team_by_name.get(_normalize(player_name))
            home_team, away_team = row.get("home_team"), row.get("away_team")
            opponent = None
            if team and home_team and away_team:
                if team == home_team:
                    opponent = f"vs {away_team}"
                elif team == away_team:
                    opponent = f"@ {home_team}"

            # Daily game-level spread/total from get_game_lines.py, one
            # dict lookup plus a couple of ternaries -- not a new pandas
            # scan per row (game_lines_by_matchup is built once above).
            game_line_row = game_lines_by_matchup.get((home_team, away_team)) if home_team and away_team else None
            total = None
            game_line = None
            if game_line_row is not None:
                raw_total = game_line_row.get("total_line")
                if pd.notna(raw_total):
                    total = float(raw_total)
                raw_spread = game_line_row.get("spread_line")
                if pd.notna(raw_spread) and team:
                    # spread_line is stored positive-means-home-favored (see
                    # get_game_lines.py's own sign-conversion comment).
                    # Converted here to the standard bettor-facing sign for
                    # THIS ROW'S OWN team -- an away-team player's line is
                    # the mirror of the home team's, exactly how a
                    # sportsbook posts each side separately.
                    if team == home_team:
                        game_line = round(-float(raw_spread), 1)
                    elif team == away_team:
                        game_line = round(float(raw_spread), 1)

            out.append({
                "player": player_name,
                "team": team,
                "opponent": opponent,
                "market": mkt,
                "line": "Yes" if mkt in _MLB_YES_NO_MARKETS else line_f,
                "season_pct": round(season_grade["pct"] * 100, 1),
                "season_sample": f"{season_grade['over']}/{season_grade['total']}",
                "recent_pct": round(recent_grade["pct"] * 100, 1),
                "recent_sample": f"{recent_grade['over']}/{recent_grade['total']}",
                "best_odds": int(round(best_odds)),
                "best_book": best_book,
                # Every book's price, unfiltered by `books` -- lets the
                # frontend's Books toggle recompute best-odds/hidden-count
                # for any checked subset locally, with no second request.
                "odds_by_book": odds_by_book,
                "estimated_line": False,
                # Carried through so the frontend's OddsDisclaimer can report
                # genuine staleness for what's on screen, same as Props/Middles
                # -- not part of the row's core contract, just passed along
                # from get_props()'s own per-row meta.
                "fetched_at": row.get("fetched_at"),
                # Daily spread (this row's own team, bettor-facing sign) and
                # total from game_lines.parquet -- None when there's no
                # game-lines match yet (line not posted, or the daily
                # pipeline hasn't run) or team/home/away couldn't be
                # resolved.
                "game_line": game_line,
                "total": total,
            })

    return out


# ---------------------------------------------------------------------------
# MLB Game Log (batters) -- Last 10 / Last 25 / Season hit rates, with a
# Home/Away split and a vs-LHP/vs-RHP split, mirroring the NBA and NFL Game
# Log pages. Built on the same batter_logs.parquet the Hit Rate Sheet already
# uses (see _batter_logs_for_market above) -- no new data pull.
# ---------------------------------------------------------------------------

@ttl_cache(MLB_TTL)
def _mlb_starting_pitcher_hand() -> pd.DataFrame:
    """One row per (game_pk, is_home) for the STARTING pitcher on that side,
    with his throwing hand attached: game_pk / is_home / pitcher_id /
    pitcher / throws.

    Built once per MLB_TTL window and reused for every batter's game-log
    request, rather than re-merging pitcher_logs.parquet + starters.parquet
    per call. `games_started == 1` isolates the starter from any reliever
    who also has a row for that game_pk in pitcher_logs.parquet.
    """
    data = get_mlb_data()
    pitcher_logs = data.get("pitcher_logs", pd.DataFrame())
    starters_df = data.get("starters", pd.DataFrame())
    if pitcher_logs.empty or "games_started" not in pitcher_logs.columns:
        return pd.DataFrame(columns=["game_pk", "is_home", "pitcher_id", "pitcher", "throws"])

    starters_only = pitcher_logs[pitcher_logs["games_started"] == 1][
        ["game_pk", "is_home", "pitcher_id", "pitcher"]
    ].drop_duplicates(subset=["game_pk", "is_home"])

    pid_to_throws = (
        dict(zip(starters_df["pitcher_id"], starters_df["throws"]))
        if not starters_df.empty and "throws" in starters_df.columns else {}
    )
    starters_only = starters_only.copy()
    starters_only["throws"] = starters_only["pitcher_id"].map(pid_to_throws)
    return starters_only


@ttl_cache(MLB_TTL)
def _mlb_batter_index() -> Dict[str, int]:
    """Display label -> player_id, for the Game Log player dropdown.

    Almost every name in batter_logs.parquet is unique, but at least one
    real collision exists this season (two different MLB players both named
    Max Muncy -- Dodgers vs Athletics), so a bare name isn't always a safe
    key. A colliding name gets its current team appended ("Max Muncy
    (Athletics)"); every other name stays plain, so this only changes the
    label for the players who actually need it.
    """
    logs = get_mlb_data().get("batter_logs", pd.DataFrame())
    if logs.empty:
        return {}
    rosters = get_mlb_data().get("mlb_rosters", pd.DataFrame())
    team_by_id = (
        dict(zip(rosters["player_id"], rosters["team"]))
        if not rosters.empty and "player_id" in rosters.columns else {}
    )

    index: Dict[str, int] = {}
    for name, ids in logs.groupby("player")["player_id"].unique().items():
        ids = list(ids)
        if len(ids) == 1:
            index[name] = int(ids[0])
        else:
            for pid in ids:
                team = team_by_id.get(pid, "unknown team")
                index[f"{name} ({team})"] = int(pid)
    return index


def get_mlb_game_log_players() -> List[str]:
    return sorted(_mlb_batter_index().keys())


def get_mlb_game_log(
    player: str,
    stat: str = "batter_hits",
    threshold: float = 0,
    home_away: Optional[str] = None,
    pitcher_hand: Optional[str] = None,
) -> Dict[str, Any]:
    """Per-game log for one batter, gradeable against a threshold, with an
    optional Home/Away filter and an optional vs-LHP/vs-RHP filter (matched
    against that specific game's actual starting pitcher -- see
    _mlb_starting_pitcher_hand() -- the same handedness read the Pitcher
    Matchup page's own vs L / vs R splits are built from, not a separate
    guess).

    Shape mirrors the NBA/NFL game-log endpoints: `games` (most recent 60 --
    plenty for the chart and the recent-games table without dragging a full
    150+ game season across the wire) and `over_counts` for Last 10, Last 25
    and the full Season -- graded from the FULL filtered season, not just
    the returned 60, so Season and even Last 25 stay correct for a player
    with more than 60 games on the books.
    """
    empty_counts = {
        "last10": {"over": 0, "total": 0, "pct": 0.0},
        "last25": {"over": 0, "total": 0, "pct": 0.0},
        "season": {"over": 0, "total": 0, "pct": 0.0},
    }

    if stat not in MLB_BATTER_MARKET_STAT:
        return {"games": [], "over_counts": empty_counts}

    player_id = _mlb_batter_index().get(player)
    if player_id is None:
        return {"games": [], "over_counts": empty_counts}

    logs = get_mlb_data().get("batter_logs", pd.DataFrame())
    if logs.empty:
        return {"games": [], "over_counts": empty_counts}

    rows = logs[logs["player_id"] == player_id].copy()
    if rows.empty:
        return {"games": [], "over_counts": empty_counts}

    rows["date"] = pd.to_datetime(rows["date"], errors="coerce")
    rows = rows[rows["date"].notna()]

    starter_hand = _mlb_starting_pitcher_hand()
    if not starter_hand.empty:
        rows = rows.merge(starter_hand, on="game_pk", how="left", suffixes=("", "_opp"))
        # The merge brings in BOTH teams' starters for a shared game_pk --
        # keep only the one on the other side of the ball from this batter.
        # A game with no starter recorded at all (is_home_opp is NaN, e.g.
        # an opener/bullpen game with no games_started row) is kept as-is
        # rather than dropped, just without a hand to filter/display.
        rows = rows[rows["is_home_opp"].isna() | (rows["is_home_opp"] != rows["is_home"])]
        rows = rows.drop_duplicates(subset=["game_pk"], keep="first")
    else:
        rows["pitcher"] = None
        rows["throws"] = None

    spec = MLB_BATTER_MARKET_STAT[stat]
    if callable(spec):
        rows["stat_value"] = rows.apply(lambda r: _stat_value(r, spec), axis=1)
    else:
        rows["stat_value"] = pd.to_numeric(rows[spec], errors="coerce").fillna(0.0)

    if home_away in ("home", "away"):
        rows = rows[rows["is_home"] == (home_away == "home")]
    if pitcher_hand in ("L", "R"):
        rows = rows[rows["throws"] == pitcher_hand]

    rows = rows.sort_values("date")
    if rows.empty:
        return {"games": [], "over_counts": empty_counts}

    all_values = rows["stat_value"].tolist()
    over_counts = {
        "last10": grade_over_under(all_values[-10:], threshold),
        "last25": grade_over_under(all_values[-25:], threshold),
        "season": grade_over_under(all_values, threshold),
    }

    recent = rows.tail(60)
    games: List[Dict[str, Any]] = []
    for _, r in recent.iterrows():
        opp_pitcher = r.get("pitcher")
        opp_hand = r.get("throws")
        d = r["date"]
        # Built from parts rather than strftime("%-m/%-d"), which is
        # platform specific and raises on Windows -- same convention as the
        # pitcher-matchup game log above.
        games.append({
            "game_date": f"{d.month}/{d.day}",
            "opponent": str(r.get("opponent") or ""),
            "is_home": bool(r.get("is_home")),
            "at_bats": int(r["at_bats"]) if _is_number(r.get("at_bats")) else None,
            "hits": int(r["hits"]) if _is_number(r.get("hits")) else None,
            # Full box-score line, not just AB/H -- the table used to show
            # only those two plus whatever stat was selected, which meant
            # picking "Hits" made the exact same number show up in both the
            # H column and the Stat column. Runs/RBI/HR/SB round it out to a
            # real trip line so the table reads the same regardless of which
            # stat happens to be selected.
            "runs": int(r["runs"]) if _is_number(r.get("runs")) else None,
            "rbi": int(r["rbi"]) if _is_number(r.get("rbi")) else None,
            "home_runs": int(r["home_runs"]) if _is_number(r.get("home_runs")) else None,
            "stolen_bases": int(r["stolen_bases"]) if _is_number(r.get("stolen_bases")) else None,
            "opp_pitcher": opp_pitcher if isinstance(opp_pitcher, str) else None,
            "opp_pitcher_hand": opp_hand if opp_hand in ("L", "R") else None,
            "stat_value": r["stat_value"],
        })

    return {"games": games, "over_counts": over_counts}
