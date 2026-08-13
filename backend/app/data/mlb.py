"""MLB business logic layer — mirrors mlb_data.py from the original Dash app."""
from typing import Optional, List, Dict, Any
import pandas as pd
from app.data.loader import get_mlb_data, get_mlb_props_data


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
                "split_iso": "ISO",
                "split_k_pct": "K%",
                "split_bb_pct": "BB%",
                "last_week_ba": "Last Week BA",
            }
            cols = [c for c in display if c in sub.columns]
            sub = sub[cols].rename(columns=display)

            for col in ("Average", "wOBA", "ISO", "Last Week BA"):
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

    return {
        "pitcher": pitcher_name,
        "season_stats": season_stats,
        "game_logs": game_logs,
        "splits": splits,
        "percentiles": percentiles,
        "opposing_hitters": opposing_hitters,
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

    # Nullable dtypes hold pd.NA, which is not JSON serializable.
    out = out.astype(object).where(out.notna(), "")
    return out.to_dict(orient="records")


_EXCLUDED_BOOKS = {
    "ballybet", "betonlineag", "betparx", "betr_us_dfs",
    "betrivers", "bovada", "dabble_us_dfs", "hardrockbet_oh", "mybookieag",
}


def get_mlb_props(
    team: Optional[str] = None,
    player: Optional[str] = None,
    market: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return MLB props pivoted wide (one row per player/line/market, sportsbooks as columns)."""
    props_df = get_mlb_props_data()
    if props_df.empty:
        return []

    props_df = props_df.copy()
    props_df.columns = [c.strip().lower().replace(" ", "_") for c in props_df.columns]

    player_col  = _find_col(props_df, ["player", "player_name", "name"])
    market_col  = _find_col(props_df, ["market", "prop_type", "stat", "bet_type", "category"])
    book_col    = _find_col(props_df, ["bookmakers", "bookmaker", "sportsbook"])
    price_col   = _find_col(props_df, ["over_price", "price", "over"])
    line_col    = _find_col(props_df, ["line", "line_value"])

    # Remove excluded sportsbooks
    if book_col:
        props_df = props_df[~props_df[book_col].str.lower().isin(_EXCLUDED_BOOKS)]

    # Optional row-level filters
    if player and player_col:
        props_df = props_df[props_df[player_col].str.lower().str.strip() == _normalize(player)]
    if market and market_col:
        props_df = props_df[props_df[market_col].str.lower().str.strip() == _normalize(market)]

    # Pivot to wide format
    if book_col and price_col and player_col:
        idx = [c for c in [player_col, line_col, market_col] if c]
        try:
            pivot = props_df.pivot_table(
                index=idx,
                columns=book_col,
                values=price_col,
                aggfunc="first",
            ).reset_index()
            pivot.columns.name = None

            # Build line_id display label
            pivot["line_id"] = pivot[player_col].astype(str)
            if line_col and line_col in pivot.columns:
                pivot["line_id"] = pivot["line_id"] + " " + pivot[line_col].astype(str)
            if market_col and market_col in pivot.columns:
                pivot["line_id"] = pivot["line_id"] + " " + pivot[market_col].astype(str)

            # Reorder: line_id first, then meta, then sportsbook columns
            meta = [c for c in idx if c in pivot.columns]
            books = [c for c in pivot.columns if c not in meta and c != "line_id"]
            pivot = pivot[["line_id"] + meta + books]
            return pivot.fillna("").to_dict(orient="records")
        except Exception as e:
            print(f"Warning: props pivot failed: {e}")

    return props_df.fillna("").to_dict(orient="records")
