from fastapi import APIRouter, Depends, Query
from typing import Optional, List
from app.auth.dependencies import require_access
from app.data import nba as nba_data

router = APIRouter(prefix="/api/nba", tags=["nba"])

@router.get("/players")
def players(_=Depends(require_access)):
    return nba_data.get_players()

@router.get("/teammates")
def teammates(player: str = Query(...), _=Depends(require_access)):
    return nba_data.get_teammates(player)

@router.get("/game-log")
def game_log(
    player: str = Query(...),
    stat: str = Query("pts"),
    threshold: float = Query(0),
    with_player: Optional[str] = Query(None),
    without_player: Optional[str] = Query(None),
    b2b: bool = Query(False),
    three_in_four: bool = Query(False),
    _=Depends(require_access),
):
    return nba_data.get_game_log(player, stat, threshold, with_player, without_player, b2b, three_in_four)

@router.get("/in-out")
def in_out(player: str = Query(...), exclude: List[str] = Query(default=[]), _=Depends(require_access)):
    return nba_data.get_in_out(player, exclude)

@router.get("/props")
def props(
    player: Optional[str] = Query(None),
    market: Optional[str] = Query(None),
    side: Optional[str] = Query(None),
    bookmaker: Optional[str] = Query(None),
    _=Depends(require_access),
):
    return nba_data.get_props(player, market, side, bookmaker)

@router.get("/debug-columns")
def debug_columns():
    """Public endpoint — no auth needed. Shows NBA data column names and 2 sample rows."""
    from app.data.loader import get_nba_data
    df = get_nba_data()
    sample = df.head(2).fillna("").to_dict(orient="records")
    return {"columns": list(df.columns), "shape": list(df.shape), "sample": sample}

@router.get("/debug-with-player")
def debug_with_player(player: str = Query(...), with_player: str = Query(...)):
    """Debug why with_player returns empty. No auth needed."""
    import pandas as pd
    from app.data.loader import get_nba_data
    from app.data.nba import _normalize, _player_col

    df = get_nba_data()
    col = _player_col(df)

    date_col = next((c for c in ["game_date", "gameid", "date", "game_id"] if c in df.columns), None)
    team_col = next((c for c in ["team", "team_abbreviation", "tm"] if c in df.columns), None)
    played_col = next((c for c in ["played", "game_played"] if c in df.columns), None)

    player_norm = _normalize(player)
    wp_norm = _normalize(with_player)

    player_df = df[df[col].str.lower().str.strip() == player_norm].copy()
    wp_df_all = df[df[col].str.lower().str.strip() == wp_norm].copy()

    df_ref = df.copy()
    if date_col:
        df_ref["_date"] = pd.to_datetime(df_ref[date_col], errors="coerce").dt.date
        player_df["_date"] = pd.to_datetime(player_df[date_col], errors="coerce").dt.date
        wp_df_all["_date"] = pd.to_datetime(wp_df_all[date_col], errors="coerce").dt.date

    if played_col:
        df_ref_played = df_ref[pd.to_numeric(df_ref[played_col], errors="coerce") == 1]
    else:
        df_ref_played = df_ref

    wp_rows = df_ref_played[df_ref_played[col].str.lower().str.strip() == wp_norm]
    wp_keys = set(zip(wp_rows["_date"], wp_rows[team_col])) if (date_col and team_col) else set()

    player_keys = set(zip(player_df["_date"], player_df[team_col])) if (date_col and team_col) else set()
    overlap = player_keys & wp_keys

    # Sample a few actual values
    player_sample = list(player_keys)[:5]
    wp_sample = list(wp_keys)[:5]

    return {
        "date_col": date_col,
        "team_col": team_col,
        "played_col": played_col,
        "anchor_total_rows": len(player_df),
        "with_player_total_rows": len(wp_df_all),
        "with_player_played1_rows": len(wp_rows),
        "anchor_unique_keys": len(player_keys),
        "with_player_unique_keys": len(wp_keys),
        "overlapping_keys": len(overlap),
        "anchor_sample_keys": [str(k) for k in player_sample],
        "with_player_sample_keys": [str(k) for k in wp_sample],
    }
