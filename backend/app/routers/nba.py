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
    min_minutes: int = Query(0),
    _=Depends(require_access),
):
    return nba_data.get_game_log(player, stat, threshold, with_player, without_player, b2b, three_in_four, min_minutes)

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

