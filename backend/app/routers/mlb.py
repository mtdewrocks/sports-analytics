from fastapi import APIRouter, Depends, Query
from typing import Optional
from app.auth.dependencies import require_access
from app.data import mlb as mlb_data

router = APIRouter(prefix="/api/mlb", tags=["mlb"])

@router.get("/pitchers")
def pitchers(_=Depends(require_access)):
    from app.data.loader import get_pitcher_names
    names = get_pitcher_names()
    if names:
        return names
    # Fallback to full data load if parquet not available
    return mlb_data.get_pitchers()

@router.get("/matchup")
def matchup(pitcher: str = Query(...), _=Depends(require_access)):
    return mlb_data.get_pitcher_matchup(pitcher)

@router.get("/pitcher-props")
def pitcher_props(pitcher: str = Query(...), _=Depends(require_access)):
    from app.data.props import get_pitcher_props
    return get_pitcher_props(pitcher)

@router.get("/hot-hitters")
def hot_hitters(_=Depends(require_access)):
    return mlb_data.get_hot_hitters()

@router.get("/game-log/players")
def game_log_players(_=Depends(require_access)):
    return mlb_data.get_mlb_game_log_players()

@router.get("/game-log/all-players")
def game_log_all_players(_=Depends(require_access)):
    """Combined batter + pitcher list for the Game Log's single unified
    search box -- see get_mlb_game_log_all_players()'s docstring."""
    return mlb_data.get_mlb_game_log_all_players()

@router.get("/game-log")
def game_log(
    player: str = Query(...),
    stat: str = Query("batter_hits"),
    threshold: float = Query(0),
    home_away: Optional[str] = Query(None, pattern="^(home|away)$"),
    pitcher_hand: Optional[str] = Query(None, pattern="^(L|R)$"),
    _=Depends(require_access),
):
    return mlb_data.get_mlb_game_log(player, stat, threshold, home_away, pitcher_hand)

@router.get("/pitcher-game-log/players")
def pitcher_game_log_players(_=Depends(require_access)):
    return mlb_data.get_mlb_pitcher_game_log_players()

@router.get("/pitcher-game-log")
def pitcher_game_log(
    player: str = Query(...),
    stat: str = Query("pitcher_strikeouts"),
    threshold: float = Query(0),
    home_away: Optional[str] = Query(None, pattern="^(home|away)$"),
    _=Depends(require_access),
):
    return mlb_data.get_mlb_pitcher_game_log(player, stat, threshold, home_away)

@router.get("/pitcher-daily-report")
def pitcher_daily_report(_=Depends(require_access)):
    return mlb_data.get_pitcher_daily_report()

@router.get("/todays-matchups")
def todays_matchups(_=Depends(require_access)):
    return mlb_data.get_mlb_todays_matchups()

@router.get("/weather")
def weather(_=Depends(require_access)):
    return mlb_data.get_mlb_weather()

@router.get("/matchup-edge")
def matchup_edge(_=Depends(require_access)):
    """Toughest/Best Matchups (hits), Platoon Edge Finder, and Strikeout
    Risk/Contact Matchups for today's slate -- see
    get_mlb_matchup_edge()'s docstring in app/data/mlb.py."""
    return mlb_data.get_mlb_matchup_edge()

@router.get("/team-matchup")
def team_matchup(team_a: str = Query(...), team_b: str = Query(...), _=Depends(require_access)):
    return mlb_data.get_mlb_team_matchup(team_a, team_b)

@router.get("/bullpen/teams")
def bullpen_teams(_=Depends(require_access)):
    return mlb_data.get_bullpen_teams()

@router.get("/bullpen")
def bullpen(team: str = Query(...), _=Depends(require_access)):
    return mlb_data.get_bullpen_status(team)

@router.get("/bullpen/report")
def bullpen_report(_=Depends(require_access)):
    return mlb_data.get_bullpen_report()

@router.get("/props")
def props(team: Optional[str] = Query(None), player: Optional[str] = Query(None), market: Optional[str] = Query(None), _=Depends(require_access)):
    return mlb_data.get_mlb_props(team, player, market)

@router.get("/middles")
def mlb_middles(kind: Optional[str] = Query(None), player: Optional[str] = Query(None),
                market: Optional[str] = Query(None), _=Depends(require_access)):
    from app.data.props import get_middles
    return get_middles("mlb", kind, player, market)

@router.get("/hit-rate-sheet/players")
def hit_rate_sheet_players(_=Depends(require_access)):
    return mlb_data.get_mlb_hit_rate_sheet_players()

@router.get("/hit-rate-sheet")
def hit_rate_sheet(
    market: Optional[str] = Query(None), min_pct: float = Query(0),
    min_odds: Optional[float] = Query(None), period: str = Query("season", pattern="^(season|recent)$"),
    player: Optional[str] = Query(None), books: Optional[str] = Query(None),
    _=Depends(require_access),
):
    return mlb_data.get_mlb_hit_rate_sheet(market, min_pct, min_odds, period, player, books)


@router.get("/ev")
def mlb_ev(
    source: str = Query("auto", pattern="^(auto|sharp|consensus)$"),
    min_edge: float = Query(2.0, ge=0, le=100), min_books: int = Query(2, ge=1, le=10),
    market: Optional[str] = Query(None), player: Optional[str] = Query(None),
    _=Depends(require_access),
):
    """EV Finder -- see app/data/ev.py."""
    from app.data.ev import get_ev
    return get_ev("mlb", source, min_edge, min_books, market, player)


@router.get("/alt-value")
def mlb_alt_value(
    market: Optional[str] = Query(None), player: Optional[str] = Query(None),
    min_ev: float = Query(3.0, ge=0, le=100), flagged_only: bool = Query(True),
    rungs: str = Query("core", pattern="^(core|all)$"), favorable_only: bool = Query(False),
    _=Depends(require_access),
):
    """Alt-Line Value -- see app/data/alt_value.py."""
    from app.data.alt_value import get_alt_value
    return get_alt_value("mlb", mlb_data.get_mlb_hit_rate_sheet, market, player, min_ev, flagged_only,
                         rungs, favorable_only)


@router.post("/refresh")
def refresh_cache(_=Depends(require_access)):
    """Clear all MLB data caches so fresh files are fetched from GitHub on next request."""
    from app.data.loader import get_mlb_data, get_pitcher_names
    get_mlb_data.cache_clear()
    get_pitcher_names.cache_clear()
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
