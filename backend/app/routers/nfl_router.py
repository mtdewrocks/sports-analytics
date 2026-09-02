from fastapi import APIRouter, Depends, Query
from typing import Optional
from app.auth.dependencies import require_access
from app.data import nfl as nfl_data

router = APIRouter(prefix="/api/nfl", tags=["nfl"])

@router.get("/players")
def players(_=Depends(require_access)):
    return nfl_data.get_players()

@router.get("/stats")
def stats(_=Depends(require_access)):
    return nfl_data.get_available_stats()

@router.get("/game-log")
def game_log(player: str = Query(...), stat: str = Query("passing_yards"), threshold: float = Query(0), _=Depends(require_access)):
    return nfl_data.get_game_log(player, stat, threshold)

@router.get("/matchups")
def matchups(_=Depends(require_access)):
    return nfl_data.get_matchups()

@router.get("/matchup")
def matchup(matchup: str = Query(...), _=Depends(require_access)):
    return nfl_data.get_matchup_detail(matchup)

@router.get("/game-script")
def game_script(matchup: str = Query(...), _=Depends(require_access)):
    return nfl_data.get_game_script_projection(matchup)

@router.get("/mismatches/categories")
def mismatch_categories(_=Depends(require_access)):
    return nfl_data.get_mismatch_categories()

@router.get("/mismatches")
def mismatches(category: str = Query(...), week: Optional[int] = Query(None), _=Depends(require_access)):
    return nfl_data.get_weekly_mismatches(category, week)

@router.get("/usage/teams")
def usage_teams(_=Depends(require_access)):
    return nfl_data.get_nfl_teams()

@router.get("/usage")
def usage(team: str = Query(...), week: Optional[int] = Query(None), _=Depends(require_access)):
    return nfl_data.get_team_usage(team, week)
