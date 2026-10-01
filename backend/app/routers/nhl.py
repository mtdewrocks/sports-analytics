from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import require_access
from app.data import nhl as nhl_data

router = APIRouter(prefix="/api/nhl", tags=["nhl"])


@router.get("/players")
def players(_=Depends(require_access)):
    return nhl_data.players()


@router.get("/slate")
def slate(date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), _=Depends(require_access)):
    return nhl_data.slate(date)


@router.get("/game-log")
def game_log(
    player_id: int = Query(...),
    stat: str = Query("sog"),
    threshold: float = Query(0.5),
    season: Optional[int] = Query(None),
    home_away: str = Query("all", pattern="^(all|home|away)$"),
    pp_role: str = Query("all", pattern="^(all|pp1|not_pp1)$"),
    min_toi: Optional[float] = Query(None, ge=0, le=40),
    opp_goalie: str = Query("all", pattern="^(all|starter|backup)$"),
    rest: str = Query("all", pattern="^(all|b2b|rested)$"),
    starts_only: bool = Query(True),
    _=Depends(require_access),
):
    return nhl_data.game_log(player_id, stat, threshold, season, home_away, pp_role, min_toi,
                             opp_goalie, rest, starts_only)


@router.get("/matchup")
def matchup(game_id: int = Query(...), _=Depends(require_access)):
    return nhl_data.matchup(game_id)


@router.get("/goalie-report")
def goalie_report(date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), _=Depends(require_access)):
    return nhl_data.goalie_report(date)


@router.get("/schedule-spots")
def schedule_spots(date: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), _=Depends(require_access)):
    return nhl_data.schedule_spots(date)


@router.get("/lines")
def lines(game_id: int = Query(...), mode: str = Query("last", pattern="^(last|common)$"),
          _=Depends(require_access)):
    return nhl_data.lines(game_id, mode)


@router.get("/deep-dive")
def deep_dive(game_id: int = Query(...), attacking: str = Query("away", pattern="^(away|home)$"),
              strength: str = Query("5v5", pattern="^(5v5|pp|all)$"), _=Depends(require_access)):
    return nhl_data.deep_dive(game_id, attacking, strength)


@router.get("/meta")
def meta(_=Depends(require_access)):
    return nhl_data.meta()
