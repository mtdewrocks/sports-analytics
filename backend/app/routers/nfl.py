from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional, List
from app.auth.dependencies import require_access
from app.data import nfl as nfl_data

router = APIRouter(prefix="/api/nfl", tags=["nfl"])

@router.get("/players")
def players(_=Depends(require_access)):
    return nfl_data.get_players()

@router.get("/stats")
def stats(_=Depends(require_access)):
    return nfl_data.get_available_stats()

@router.get("/game-log/players")
def game_log_players(_=Depends(require_access)):
    return nfl_data.get_game_log_players()

@router.get("/game-log")
def game_log(
    player: str = Query(...), stat: str = Query("passing_yards"), threshold: float = Query(0),
    win_loss: Optional[str] = Query(None, pattern="^(W|L)$"),
    margin_operator: Optional[str] = Query(None, pattern="^(<|>)$"),
    margin_value: Optional[float] = Query(None),
    season: Optional[int] = Query(None),
    _=Depends(require_access),
):
    return nfl_data.get_game_log(player, stat, threshold, win_loss, margin_operator, margin_value, season)

@router.get("/position-vs-defense")
def position_vs_defense(
    opponent: str = Query(...), position: str = Query(..., pattern="^(RB|WR|TE|QB)$"),
    exclude_player: Optional[str] = Query(None),
    _=Depends(require_access),
):
    return nfl_data.get_nfl_position_vs_defense(opponent, position, exclude_player)

@router.get("/weather")
def weather(_=Depends(require_access)):
    return nfl_data.get_nfl_weather()

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

@router.get("/usage/players")
def usage_players(_=Depends(require_access)):
    return nfl_data.get_nfl_usage_players()

@router.get("/usage/trend")
def usage_trend(
    player: str = Query(...),
    stat: str = Query("targets"),
    _=Depends(require_access),
):
    try:
        return nfl_data.get_player_usage_trend(player, stat)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/fantasy-matchup/current-week")
def fantasy_matchup_current_week(players: List[str] = Query(..., min_length=2, max_length=4), _=Depends(require_access)):
    return nfl_data.get_fantasy_matchup_current_week(players)

@router.get("/fantasy-matchup/season")
def fantasy_matchup_season(players: List[str] = Query(..., min_length=2, max_length=4), _=Depends(require_access)):
    return nfl_data.get_fantasy_matchup_season(players)

@router.get("/teammates")
def teammates(player: str = Query(...), _=Depends(require_access)):
    return nfl_data.get_nfl_teammates(player)

@router.get("/in-out")
def in_out(player: str = Query(...), exclude: List[str] = Query(default=[]), _=Depends(require_access)):
    return nfl_data.get_nfl_in_out(player, exclude)

@router.get("/season-screener")
def season_screener(
    season: int = Query(...),
    position: Optional[str] = Query(None),
    filters: List[str] = Query(default=[]),
    _=Depends(require_access),
):
    return nfl_data.get_nfl_season_screener(season, position, filters)


@router.get("/props")
def nfl_props(team: str | None = Query(None), player: str | None = Query(None),
              market: str | None = Query(None), _=Depends(require_access)):
    from app.data.props import get_props
    return get_props("nfl", team, player, market)


@router.get("/middles")
def nfl_middles(kind: str | None = Query(None), player: str | None = Query(None),
                market: str | None = Query(None), _=Depends(require_access)):
    from app.data.props import get_middles
    return get_middles("nfl", kind, player, market)

@router.get("/hit-rate-sheet/players")
def nfl_hit_rate_sheet_players(_=Depends(require_access)):
    return nfl_data.get_nfl_hit_rate_sheet_players()

@router.get("/hit-rate-sheet")
def nfl_hit_rate_sheet(
    market: Optional[str] = Query(None), min_pct: float = Query(0),
    min_odds: Optional[float] = Query(None), period: str = Query("season", pattern="^(season|recent)$"),
    player: Optional[str] = Query(None), books: Optional[str] = Query(None),
    _=Depends(require_access),
):
    return nfl_data.get_nfl_hit_rate_sheet(market, min_pct, min_odds, period, player, books)


@router.get("/ev")
def nfl_ev(
    source: str = Query("auto", pattern="^(auto|sharp|consensus)$"),
    min_edge: float = Query(2.0, ge=0, le=100), min_books: int = Query(2, ge=1, le=10),
    market: Optional[str] = Query(None), player: Optional[str] = Query(None),
    _=Depends(require_access),
):
    """EV Finder -- see app/data/ev.py."""
    from app.data.ev import get_ev
    return get_ev("nfl", source, min_edge, min_books, market, player)


@router.get("/alt-value")
def nfl_alt_value(
    market: Optional[str] = Query(None), player: Optional[str] = Query(None),
    min_ev: float = Query(3.0, ge=0, le=100), flagged_only: bool = Query(True),
    _=Depends(require_access),
):
    """Alt-Line Value -- see app/data/alt_value.py."""
    from app.data.alt_value import get_alt_value
    return get_alt_value("nfl", nfl_data.get_nfl_hit_rate_sheet, market, player, min_ev, flagged_only)
