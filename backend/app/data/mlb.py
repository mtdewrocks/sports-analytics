"""MLB business logic layer — mirrors mlb_data.py from the original Dash app."""
from typing import Optional, List, Dict, Any
import pandas as pd
from app.data.loader import get_mlb_data


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


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def get_pitchers() -> List[str]:
    """Return sorted list of today's pitcher names (Baseball Savant name)."""
    data = get_mlb_data()

    # Historical starters has Baseball_Savant_Name — this is the canonical pitcher list
    starters_df = data.get("historical_starters", pd.DataFrame())
    if not starters_df.empty:
        col = _find_col(starters_df, ["Baseball_Savant_Name", "baseball_savant_name", "savant_name"])
        if col:
            return sorted(starters_df[col].dropna().unique().tolist())

    # Fallback: pitcher season stats Name column
    stats_df = data.get("pitcher_season_stats", pd.DataFrame())
    if not stats_df.empty:
        col = _find_col(stats_df, ["name", "pitcher_name", "pitcher"])
        if col:
            return sorted(stats_df[col].dropna().unique().tolist())

    return []


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

    # ------------------------------------------------------------------
    # 1. Season stats — Pitcher_Season_Stats.xlsx merged with Historical_Starting_Pitchers
    # ------------------------------------------------------------------
    stats_df = data.get("pitcher_season_stats", pd.DataFrame())
    starters_df = data.get("historical_starters", pd.DataFrame())

    season_stats = {}
    if not stats_df.empty and not starters_df.empty:
        # Merge on Name <-> Baseball_Savant_Name
        name_col = _find_col(stats_df, ["name"])
        savant_col = _find_col(starters_df, ["baseball_savant_name"])
        if name_col and savant_col:
            merged = stats_df.merge(starters_df, left_on=name_col, right_on=savant_col, how="left")
            savant_merged_col = _find_col(merged, ["baseball_savant_name"])
            if savant_merged_col:
                row = merged[merged[savant_merged_col].str.lower().str.strip() == pitcher_norm]
                if not row.empty:
                    keep = ["Name", "Handedness", "GS", "W", "L", "ERA", "IP", "SO", "WHIP"]
                    available = [c for c in keep if _find_col(row, [c])]
                    season_stats = row[[_find_col(row, [c]) for c in available]].iloc[0].fillna("").to_dict()

    elif not stats_df.empty:
        name_col = _find_col(stats_df, ["name", "baseball_savant_name"])
        if name_col:
            row = stats_df[stats_df[name_col].str.lower().str.strip() == pitcher_norm]
            if not row.empty:
                season_stats = row.iloc[0].fillna("").to_dict()

    # ------------------------------------------------------------------
    # 2. Game logs — 2025_Pitching_Logs.xlsx
    # ------------------------------------------------------------------
    gl_df = data.get("pitcher_game_logs", pd.DataFrame())
    game_logs = []
    if not gl_df.empty:
        name_col = _find_col(gl_df, ["name"])
        if name_col:
            sub = gl_df[gl_df[name_col].str.lower().str.strip() == pitcher_norm].copy()
            # Keep display columns matching the original app
            keep = ["Date", "Opp", "Opponent", "W", "L", "IP", "BF", "H", "R", "ER", "HR", "BB", "SO", "Pit"]
            keep_actual = [_find_col(sub, [c]) for c in keep if _find_col(sub, [c])]
            sub = sub[keep_actual]
            # Rename Opp -> Opponent if needed
            opp_col = _find_col(sub, ["opp"])
            if opp_col and opp_col != "Opponent":
                sub = sub.rename(columns={opp_col: "Opponent"})
            # Sort newest first
            date_col = _find_col(sub, ["date"])
            if date_col:
                sub = sub.sort_values(date_col, ascending=False)
            game_logs = sub.fillna("").to_dict(orient="records")

    # ------------------------------------------------------------------
    # 3. Splits — Season_Aggregated_Pitcher_Statistics.xlsx (vs L / vs R pivot)
    # ------------------------------------------------------------------
    splits_df = data.get("pitcher_splits", pd.DataFrame())
    splits = []
    if not splits_df.empty:
        savant_col = _find_col(splits_df, ["baseball savant name", "baseball_savant_name"])
        if savant_col:
            sub = splits_df[splits_df[savant_col].str.lower().str.strip() == pitcher_norm].copy()
            if not sub.empty:
                id_vars = [c for c in ["Pitcher", "Team", "Handedness", "Opposing Team", "Name",
                                       "Rotowire Name", "Split", "Baseball Savant Name", "Tm"]
                           if _find_col(sub, [c])]
                id_vars_actual = [_find_col(sub, [c]) for c in id_vars]
                try:
                    melted = pd.melt(sub, id_vars=id_vars_actual, var_name="Statistic", value_name="Value")
                    split_col = _find_col(melted, ["split"])
                    pivot = melted.pivot_table("Value", index="Statistic", columns=split_col).reset_index()
                    # Reorder columns: vs L | Statistic | vs R
                    cols = [c for c in ["vs L", "Statistic", "vs R"] if c in pivot.columns]
                    if cols:
                        pivot = pivot[cols]
                    splits = pivot.fillna("").to_dict(orient="records")
                except Exception:
                    splits = sub.fillna("").to_dict(orient="records")

    # ------------------------------------------------------------------
    # 4. Percentiles — Pitcher_Percentile_Rankings.csv (reshaped for chart)
    # ------------------------------------------------------------------
    pct_df = data.get("pitcher_percentiles", pd.DataFrame())
    percentiles = []
    if not pct_df.empty:
        rename_map = {
            "xera": "Expected ERA", "xba": "Expected Batting Avg",
            "fb_velocity": "Fastball Velo", "exit_velocity": "Avg Exit Velocity",
            "k_percent": "K %", "chase_percent": "Chase %", "whiff_percent": "Whiff %",
            "brl_percent": "Barrel %", "hard_hit_percent": "Hard-Hit %", "bb_percent": "BB %",
        }
        pct_df = pct_df.rename(columns={k: v for k, v in rename_map.items() if k in pct_df.columns})
        name_col = _find_col(pct_df, ["player_name"])
        if name_col:
            pct_df["converted_name"] = pct_df[name_col].apply(_convert_savant_name)
            sub = pct_df[pct_df["converted_name"].str.lower().str.strip() == pitcher_norm].copy()
            if not sub.empty:
                stat_cols = [c for c in ["Fastball Velo", "Avg Exit Velocity", "Chase %",
                                         "Whiff %", "K %", "BB %", "Barrel %", "Hard-Hit %"]
                             if c in sub.columns]
                id_cols = [c for c in ["converted_name"] if c in sub.columns]
                melted = pd.melt(sub[id_cols + stat_cols], id_vars=id_cols,
                                 var_name="Statistic", value_name="Percentile")
                percentiles = melted[["Statistic", "Percentile"]].fillna("").to_dict(orient="records")

    # ------------------------------------------------------------------
    # 5. Opposing hitters — Combined_Daily_Data.xlsx filtered by pitcher
    # ------------------------------------------------------------------
    daily_df = data.get("combined_daily", pd.DataFrame())
    last_week_df = data.get("last_week_stats", pd.DataFrame())
    opposing_hitters = []

    if not daily_df.empty:
        pitcher_col = _find_col(daily_df, ["baseball savant name", "baseball_savant_name", "pitcher"])
        if pitcher_col:
            sub = daily_df[daily_df[pitcher_col].str.lower().str.strip() == pitcher_norm].copy()
            # Merge last week BA
            if not last_week_df.empty and not sub.empty:
                name_col_lw = _find_col(last_week_df, ["name"])
                ba_col = _find_col(last_week_df, ["ba"])
                if name_col_lw and ba_col:
                    lw = last_week_df[[name_col_lw, ba_col]].rename(
                        columns={name_col_lw: "Name", ba_col: "Last Week BA"}
                    )
                    savant_col = _find_col(sub, ["savant name", "savant_name"])
                    if savant_col:
                        sub = sub.merge(lw, left_on=savant_col, right_on="Name", how="left").drop(columns=["Name"], errors="ignore")

            # Keep useful display columns
            keep = ["fg_name", "Savant Name", "Bats", "Batting Order", "Average",
                    "wOBA", "ISO", "K%", "BB%", "Fly Ball %", "Hard Contact %", "Last Week BA"]
            keep_actual = [_find_col(sub, [c]) for c in keep if _find_col(sub, [c])]
            sub = sub[keep_actual]

            order_col = _find_col(sub, ["batting order"])
            if order_col:
                sub = sub.sort_values(order_col)

            opposing_hitters = sub.fillna("").to_dict(orient="records")

    return {
        "pitcher": pitcher_name,
        "season_stats": season_stats,
        "game_logs": game_logs,
        "splits": splits,
        "percentiles": percentiles,
        "opposing_hitters": opposing_hitters,
    }


def get_hot_hitters() -> List[Dict[str, Any]]:
    """Return hot hitters — batters from last week with PA>=20 and BA>=.350."""
    data = get_mlb_data()
    lw_df = data.get("last_week_stats", pd.DataFrame())
    if lw_df.empty:
        return []
    pa_col = _find_col(lw_df, ["pa"])
    ba_col = _find_col(lw_df, ["ba"])
    if pa_col and ba_col:
        hot = lw_df[(pd.to_numeric(lw_df[pa_col], errors="coerce") >= 20) &
                    (pd.to_numeric(lw_df[ba_col], errors="coerce") >= 0.350)]
        return hot.fillna("").to_dict(orient="records")
    return lw_df.head(25).fillna("").to_dict(orient="records")


def get_mlb_props(
    team: Optional[str] = None,
    player: Optional[str] = None,
    market: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Return MLB props filtered by team, player, and/or market."""
    data = get_mlb_data()
    props_df = data.get("props", pd.DataFrame())
    if props_df.empty:
        return []

    props_df = props_df.copy()
    props_df.columns = [c.strip().lower().replace(" ", "_") for c in props_df.columns]

    player_col = _find_col(props_df, ["player", "player_name", "name"])
    team_col = _find_col(props_df, ["team", "team_name", "mlb_team_long"])
    market_col = _find_col(props_df, ["market", "prop_type", "stat", "bet_type", "category"])

    if team and team_col:
        props_df = props_df[props_df[team_col].str.upper().str.strip() == team.strip().upper()]
    if player and player_col:
        props_df = props_df[props_df[player_col].str.lower().str.strip() == _normalize(player)]
    if market and market_col:
        props_df = props_df[props_df[market_col].str.lower().str.strip() == _normalize(market)]

    return props_df.fillna("").to_dict(orient="records")
