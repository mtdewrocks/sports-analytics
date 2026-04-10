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
    try:
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
                        # Map K -> SO if SO not present
                        if "SO" not in season_stats:
                            k_col = _find_col(row, ["k"])
                            if k_col:
                                season_stats["SO"] = int(row[k_col].iloc[0])

        elif not stats_df.empty:
            name_col = _find_col(stats_df, ["name", "baseball_savant_name"])
            if name_col:
                row = stats_df[stats_df[name_col].str.lower().str.strip() == pitcher_norm]
                if not row.empty:
                    season_stats = row.iloc[0].fillna("").to_dict()

        # Supplement season_stats with GS / W / L / SO from 2026 game logs
        gl_df_agg = data.get("pitcher_game_logs", pd.DataFrame())
        if not gl_df_agg.empty and season_stats:
            name_col_gl = _find_col(gl_df_agg, ["name"])
            if name_col_gl:
                pitcher_logs = gl_df_agg[gl_df_agg[name_col_gl].str.lower().str.strip() == pitcher_norm]
                if not pitcher_logs.empty:
                    gs_col = _find_col(pitcher_logs, ["gs"])
                    w_col  = _find_col(pitcher_logs, ["w"])
                    l_col  = _find_col(pitcher_logs, ["l"])
                    so_col = _find_col(pitcher_logs, ["so"])
                    if gs_col and "GS" not in season_stats:
                        season_stats["GS"] = int(pitcher_logs[gs_col].astype(float).sum())
                    if w_col and "W" not in season_stats:
                        season_stats["W"] = int(pitcher_logs[w_col].astype(float).sum())
                    if l_col and "L" not in season_stats:
                        season_stats["L"] = int(pitcher_logs[l_col].astype(float).sum())
                    if so_col and "SO" not in season_stats:
                        season_stats["SO"] = int(pitcher_logs[so_col].astype(float).sum())

        # Compute K/IP (baseball IP convention: .1 = 1/3 inn, .2 = 2/3 inn)
        if season_stats:
            ip_raw = float(season_stats.get("IP", 0) or 0)
            ip_frac = round(ip_raw - int(ip_raw), 1)
            ip_true = int(ip_raw) + (ip_frac * 10 / 3)
            so_val = int(season_stats.get("SO", 0) or 0)
            if ip_true > 0:
                season_stats["K/IP"] = round(so_val / ip_true, 2)
    except Exception as e:
        print(f"Warning: season_stats section failed for {pitcher_name}: {e}")

    # ------------------------------------------------------------------
    # 2. Game logs — 2026_Pitching_Logs.xlsx
    # ------------------------------------------------------------------
    game_logs = []
    try:
        gl_df = data.get("pitcher_game_logs", pd.DataFrame())
        if not gl_df.empty:
            name_col = _find_col(gl_df, ["name"])
            if name_col:
                sub = gl_df[gl_df[name_col].str.lower().str.strip() == pitcher_norm].copy()
                keep = ["Date", "OPP", "Opponent", "W", "L", "IP", "H", "R", "ER", "HR", "BB", "SO", "Total_Pitches"]
                keep_actual = [_find_col(sub, [c]) for c in keep if _find_col(sub, [c])]
                sub = sub[keep_actual]
                opp_col = _find_col(sub, ["opp", "opponent"])
                if opp_col and opp_col != "Opponent":
                    sub = sub.rename(columns={opp_col: "Opponent"})
                pit_col = _find_col(sub, ["total_pitches"])
                if pit_col and pit_col != "Pitches":
                    sub = sub.rename(columns={pit_col: "Pitches"})
                date_col = _find_col(sub, ["date"])
                if date_col:
                    sub[date_col] = pd.to_datetime(sub[date_col], errors="coerce")
                    sub = sub[sub[date_col].dt.year == 2026]
                    sub = sub.sort_values(date_col, ascending=False)
                    sub = sub.head(10)
                    sub[date_col] = sub[date_col].apply(lambda d: f"{d.month}/{d.day}/{d.year}" if pd.notna(d) else "")
                game_logs = sub.fillna("").to_dict(orient="records")
    except Exception as e:
        print(f"Warning: game_logs section failed for {pitcher_name}: {e}")

    # ------------------------------------------------------------------
    # 3. Splits — combine 2025 (Season_Aggregated) + 2026 (Pitcher_Season_Stats)
    #    using TBF-weighted averaging
    # ------------------------------------------------------------------
    STAT_ORDER = [
        "TBF", "Weighted AVG", "Weighted BABIP", "Weighted wOBA", "Weighted SLG",
        "ISO Pitcher", "HR", "Pitcher HR Rate", "Weighted K%", "Weighted BB%",
        "Weighted GB%", "Weighted LD%", "Weighted FB%", "Weighted HR/FB",
        "Weighted Soft%", "Weighted Med%", "Weighted Hard%", "Weighted FIP", "Weighted xFIP",
    ]
    WEIGHTED_STATS = [
        "Weighted AVG", "Weighted BABIP", "Weighted wOBA", "Weighted SLG",
        "Weighted K%", "Weighted BB%", "Weighted GB%", "Weighted LD%", "Weighted FB%",
        "Weighted HR/FB", "Weighted Soft%", "Weighted Med%", "Weighted Hard%",
        "Weighted FIP", "Weighted xFIP",
    ]

    splits_df   = data.get("pitcher_splits_hist", pd.DataFrame())
    stats_df_26 = data.get("pitcher_season_stats", pd.DataFrame())
    splits = []
    try:
        def _get_splits_row(df, savant_candidates):
            col = _find_col(df, savant_candidates)
            if col is None:
                return pd.DataFrame()
            return df[df[col].str.lower().str.strip() == pitcher_norm].copy()

        sub25 = _get_splits_row(splits_df,   ["baseball savant name", "baseball_savant_name"])
        sub26 = _get_splits_row(stats_df_26, ["baseball savant name", "baseball_savant_name"])

        for df in [sub25, sub26]:
            sc = _find_col(df, ["split"])
            if sc and sc != "Split":
                df.rename(columns={sc: "Split"}, inplace=True)

        combined_rows = []
        for split_val in ["vs L", "vs R"]:
            row25 = sub25[sub25["Split"] == split_val] if not sub25.empty and "Split" in sub25.columns else pd.DataFrame()
            row26 = sub26[sub26["Split"] == split_val] if not sub26.empty and "Split" in sub26.columns else pd.DataFrame()

            tbf25 = float(row25["TBF"].iloc[0]) if not row25.empty and "TBF" in row25.columns else 0
            tbf26 = float(row26["TBF"].iloc[0]) if not row26.empty and "TBF" in row26.columns else 0
            total_tbf = tbf25 + tbf26
            if total_tbf == 0:
                continue

            hr25 = float(row25["HR"].iloc[0]) if not row25.empty and "HR" in row25.columns else 0
            hr26 = float(row26["HR"].iloc[0]) if not row26.empty and "HR" in row26.columns else 0

            out = {"Split": split_val, "TBF": int(total_tbf), "HR": int(hr25 + hr26)}
            out["Pitcher HR Rate"] = round((hr25 + hr26) / total_tbf, 3) if total_tbf else ""

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

        for stat in WEIGHTED_STATS:
                v25_raw = float(row25[stat].iloc[0]) if not row25.empty and stat in row25.columns else None
                v26_raw = float(row26[stat].iloc[0]) if not row26.empty and stat in row26.columns else None
                v25 = _sane(v25_raw, stat)
                v26 = _sane(v26_raw, stat)
                if v25 is not None and v26 is not None:
                    combined = (tbf25 * v25 + tbf26 * v26) / total_tbf
                elif v25 is not None:
                    combined = v25
                elif v26 is not None:
                    combined = v26
                else:
                    combined = None
                out[stat] = round(combined, 3) if combined is not None else ""

            wslg = out.get("Weighted SLG", "")
            wavg = out.get("Weighted AVG", "")
            out["ISO Pitcher"] = round(float(wslg) - float(wavg), 3) if wslg != "" and wavg != "" else ""
            combined_rows.append(out)

        if combined_rows:
            combined_df = pd.DataFrame(combined_rows).set_index("Split").T.reset_index()
            combined_df = combined_df.rename(columns={"index": "Statistic"})
            order_map = {s: i for i, s in enumerate(STAT_ORDER)}
            combined_df["_ord"] = combined_df["Statistic"].map(order_map).fillna(999)
            combined_df = combined_df.sort_values("_ord").drop(columns=["_ord"])
            cols = [c for c in ["vs L", "Statistic", "vs R"] if c in combined_df.columns]
            splits = combined_df[cols].fillna("").to_dict(orient="records")
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
    except Exception as e:
        print(f"Warning: percentiles section failed for {pitcher_name}: {e}")

    # ------------------------------------------------------------------
    # 5. Opposing hitters — Combined_Daily_Data.xlsx filtered by pitcher
    # ------------------------------------------------------------------
    opposing_hitters = []
    try:
        daily_df = data.get("combined_daily", pd.DataFrame())
        last_week_df = data.get("last_week_stats", pd.DataFrame())
        if not daily_df.empty:
            pitcher_col = _find_col(daily_df, ["baseball savant name", "baseball_savant_name", "pitcher"])
            if pitcher_col:
                sub = daily_df[daily_df[pitcher_col].str.lower().str.strip() == pitcher_norm].copy()
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
                keep = ["fg_name", "Savant Name", "Bats", "Batting Order", "Average",
                        "wOBA", "ISO", "K%", "BB%", "Fly Ball %", "Hard Contact %", "Last Week BA"]
                keep_actual = [_find_col(sub, [c]) for c in keep if _find_col(sub, [c])]
                sub = sub[keep_actual]
                order_col = _find_col(sub, ["batting order"])
                if order_col:
                    sub = sub.sort_values(order_col)
                opposing_hitters = sub.fillna("").to_dict(orient="records")
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
