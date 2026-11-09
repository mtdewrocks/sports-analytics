from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel
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
    season: str = Query("current", description="current | last | both"),
    _=Depends(require_access),
):
    return nba_data.get_game_log(player, stat, threshold, with_player, without_player, b2b, three_in_four, min_minutes, season)

@router.get("/seasons")
def seasons(_=Depends(require_access)):
    return nba_data.get_seasons()

@router.get("/schedule")
def schedule(date: Optional[str] = Query(None, description="YYYY-MM-DD (Eastern); default today or next game day"),
             _=Depends(require_access)):
    return nba_data.get_schedule(date)

@router.get("/in-out")
def in_out(player: str = Query(...), exclude: List[str] = Query(default=[]), _=Depends(require_access)):
    return nba_data.get_in_out(player, exclude)

@router.get("/in-out/beneficiary")
def in_out_beneficiary(excluded_player: str = Query(...), stat: str = Query("min"), _=Depends(require_access)):
    return nba_data.get_biggest_beneficiary(excluded_player, stat)

@router.get("/props")
def props(team: Optional[str] = Query(None), player: Optional[str] = Query(None),
          market: Optional[str] = Query(None), _=Depends(require_access)):
    """Line-shopping grid from NBA_Props.parquet (get_props.py --sport nba),
    the same shared pivot the MLB and NFL Props pages use."""
    from app.data.props import get_props as shared_props
    return shared_props("nba", team, player, market)

@router.get("/middles")
def nba_middles(kind: Optional[str] = Query(None), player: Optional[str] = Query(None),
                market: Optional[str] = Query(None), _=Depends(require_access)):
    from app.data.props import get_middles
    return get_middles("nba", kind, player, market)

@router.get("/gap-bets")
def gap_bets(include_negative: bool = Query(False), market: Optional[str] = Query(None),
             _=Depends(require_access)):
    """Anti-middles with each player's historical landing rate -- see app/data/nba_gaps.py."""
    from app.data.nba_gaps import get_gap_bets
    return get_gap_bets(include_negative, market)

@router.get("/gap-bets/record")
def gap_bets_record(_=Depends(require_access)):
    """Graded history of every gap bet the page has shown."""
    from app.data.nba_gaps import get_gap_record
    return get_gap_record()

@router.get("/injury-impact")
def injury_impact(team: Optional[str] = Query(None), include_day_to_day: bool = Query(True),
                  _=Depends(require_access)):
    """Injured players and the teammates their absence helps -- see app/data/nba_injury_impact.py."""
    from app.data.nba_injury_impact import get_injury_impact
    return get_injury_impact(team, include_day_to_day)

class ProjectionRequest(BaseModel):
    game_id: Optional[int] = None
    minutes: dict = {}

@router.get("/projections")
def projections(game_id: Optional[int] = Query(None), _=Depends(require_access)):
    """Tonight's projections at default minutes -- see app/data/nba_projections.py."""
    from app.data.nba_projections import get_projections
    return get_projections(game_id)

@router.post("/projections")
def projections_custom(req: ProjectionRequest = Body(...), _=Depends(require_access)):
    """Rerun the model with user-edited minutes ({player name: minutes})."""
    from app.data.nba_projections import get_projections
    return get_projections(req.game_id, req.minutes)

@router.get("/projections/record")
def projections_record(_=Depends(require_access)):
    from app.data.nba_projections import get_projection_record
    return get_projection_record()

@router.get("/ev")
def nba_ev(
    source: str = Query("auto", pattern="^(auto|sharp|consensus)$"),
    min_edge: float = Query(2.0, ge=0, le=100), min_books: int = Query(2, ge=1, le=10),
    market: Optional[str] = Query(None), player: Optional[str] = Query(None),
    _=Depends(require_access),
):
    """EV Finder -- see app/data/ev.py."""
    from app.data.ev import get_ev
    return get_ev("nba", source, min_edge, min_books, market, player)

@router.get("/teams")
def teams(_=Depends(require_access)):
    return nba_data.get_teams()

@router.get("/team-usage")
def team_usage(
    team: str = Query(...),
    metric: str = Query("fga"),
    scope: str = Query("season"),
    _=Depends(require_access),
):
    return nba_data.get_team_usage(team, metric, scope)

@router.get("/team-matchup")
def team_matchup(
    team_a: str = Query(...),
    team_b: str = Query(...),
    _=Depends(require_access),
):
    return nba_data.get_team_matchup(team_a, team_b)

