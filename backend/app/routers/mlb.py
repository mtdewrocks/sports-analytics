from fastapi import APIRouter, Depends, Query
from typing import Optional
from app.auth.dependencies import require_access
from app.data import mlb as mlb_data

router = APIRouter(prefix="/api/mlb", tags=["mlb"])

@router.get("/pitchers")
def pitchers(_=Depends(require_access)):
    return mlb_data.get_pitchers()

@router.get("/matchup")
def matchup(pitcher: str = Query(...), _=Depends(require_access)):
    return mlb_data.get_pitcher_matchup(pitcher)

@router.get("/hot-hitters")
def hot_hitters(_=Depends(require_access)):
    return mlb_data.get_hot_hitters()

@router.get("/props")
def props(team: Optional[str] = Query(None), player: Optional[str] = Query(None), market: Optional[str] = Query(None), _=Depends(require_access)):
    return mlb_data.get_mlb_props(team, player, market)

@router.post("/refresh")
def refresh_cache(_=Depends(require_access)):
    """Clear the MLB data cache so fresh files are fetched from GitHub on next request."""
    from app.data.loader import get_mlb_data
    get_mlb_data.cache_clear()
    return {"status": "cache cleared"}

@router.get("/debug")
def debug():
    """No-auth debug: shows what MLB data files loaded and their row counts."""
    from app.data.loader import get_mlb_data
    data = get_mlb_data()
    result = {}
    for key, df in data.items():
        result[key] = {
            "rows": len(df),
            "columns": list(df.columns[:5]) if not df.empty else [],
            "empty": df.empty,
        }
    return result
