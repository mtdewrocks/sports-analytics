import io
import time
from functools import wraps

import pandas as pd
import requests

from app.config import settings


def ttl_cache(seconds: int):
    """Cache a result, re-running the function once it goes stale.

    lru_cache never expires: a worker fetched these files on its first request
    and then served that snapshot until the process restarted, so the hourly
    GitHub Actions updates stayed invisible until a redeploy.

    On a failed refresh the previous value is kept rather than raising -- a
    dashboard showing ten-minute-old numbers beats a 500.
    """
    def decorator(func):
        store: dict = {}

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            hit = store.get(key)
            now = time.time()

            if hit and now - hit[1] < seconds:
                return hit[0]

            try:
                value = func(*args, **kwargs)
            except Exception as e:
                if hit:
                    print(f"Warning: {func.__name__} refresh failed ({e}); serving cached copy")
                    return hit[0]
                raise

            store[key] = (value, now)
            return value

        wrapper.cache_clear = store.clear
        return wrapper

    return decorator


# Files rewritten by GitHub Actions through the day.
MLB_TTL = 600     # 10 minutes
# Other sports, updated far less often.
OTHER_TTL = 3600  # 1 hour


def _fetch_bytes(url: str) -> bytes:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
        # GitHub raw sits behind a CDN that will happily hand back a cached
        # copy, which would defeat the TTL above.
        "Cache-Control": "no-cache",
    }
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.content


def _load(url: str, reader, key: str) -> pd.DataFrame:
    """Fetch and parse one file, degrading to an empty frame on failure."""
    try:
        return reader(io.BytesIO(_fetch_bytes(url)))
    except Exception as e:
        print(f"Warning: could not load {key}: {e}")
        return pd.DataFrame()


@ttl_cache(OTHER_TTL)
def get_nfl_snap_counts() -> pd.DataFrame:
    """Snap-by-snap participation from nflverse (sourced from Pro Football
    Reference), pulled directly like get_nfl_schedule() rather than from the
    app's own re-hosted files. Used as the "did this player actually play"
    signal for the NFL In/Out page -- presence in this file for a given
    game_id is a real played/inactive signal, unlike the box-score stats
    file (which has no way to distinguish "played and recorded a zero" from
    "wasn't active that week" -- this file mirrors the explicit 'played'
    column NBA's data already has).

    Falls back to last season if the current one has no games yet, same
    convention as the rest of this app's NFL pulls.
    """
    from datetime import date
    season = date.today().year if date.today().month >= 9 else date.today().year - 1
    url = f"https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{season}.csv"
    df = _load(url, lambda buf: pd.read_csv(buf, low_memory=False), "nfl snap counts")
    if df.empty:
        prior_url = f"https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{season - 1}.csv"
        df = _load(prior_url, lambda buf: pd.read_csv(buf, low_memory=False), "nfl snap counts (prior season fallback)")
    return df


@ttl_cache(OTHER_TTL)
def get_nba_data() -> pd.DataFrame:
    raw = _fetch_bytes(settings.NBA_STATS_URL)
    df = pd.read_parquet(io.BytesIO(raw))
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]
    return df


@ttl_cache(OTHER_TTL)
def get_nfl_stats() -> pd.DataFrame:
    raw = _fetch_bytes(settings.NFL_STATS_URL)
    df = pd.read_parquet(io.BytesIO(raw))
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]
    return df


@ttl_cache(OTHER_TTL)
def get_nfl_team_stats() -> pd.DataFrame:
    """Team offense/defense stats + ranks, from get_nfl_weekly_stats.py.

    Replaces the old NFL_TEAM_STATS_URL Excel file (produced by a manually
    run script) with this repo's own automated pipeline output.
    """
    base = settings.NFL_BASE_URL
    return _load(f"{base}/team_stats.parquet", pd.read_parquet, "nfl team stats")


@ttl_cache(OTHER_TTL)
def get_nfl_schedule() -> pd.DataFrame:
    """Full schedule, pulled directly from nflverse rather than the old
    manually-uploaded Excel file. Same source get_nfl_weekly_stats.py uses
    internally for scoring -- not filtered to a season here, so callers can
    slice whichever season/week they need.
    """
    return _load(
        "https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv",
        lambda buf: pd.read_csv(buf, low_memory=False),
        "nfl schedule",
    )


@ttl_cache(OTHER_TTL)
def get_nba_props() -> pd.DataFrame:
    raw = _fetch_bytes(settings.NBA_PROPS_URL)
    return pd.read_excel(io.BytesIO(raw))


@ttl_cache(OTHER_TTL)
def get_nfl_player_week_usage() -> pd.DataFrame:
    """Target share / rush share, overall and red-zone-only, from get_nfl_pbp.py.

    Points at this repo's own backend/data/nfl/ instead of the legacy
    sports_analysis repo -- the first piece of NFL data built on the new
    play-by-play pipeline rather than the old manually-run Excel process.
    """
    base = settings.NFL_BASE_URL
    return _load(f"{base}/player_week_usage.parquet", pd.read_parquet, "nfl player-week usage")


@ttl_cache(OTHER_TTL)
def get_nfl_weekly_defense_ranks() -> pd.DataFrame:
    """Historical week-by-week defensive ranks, from get_nfl_weekly_defense_ranks.py.
    Used to show what a defense was ranked ENTERING the week a given game log
    row was actually played -- team_stats.parquet only has the current
    snapshot, which can't answer that for a past game.
    """
    base = settings.NFL_BASE_URL
    return _load(f"{base}/weekly_defense_ranks.parquet", pd.read_parquet, "nfl weekly defense ranks")


@ttl_cache(OTHER_TTL)
def get_nfl_defense_by_position() -> pd.DataFrame:
    """Historical week-by-week defensive ranks split by the OPPONENT'S
    POSITION (rushing vs RB/QB, receiving vs RB/WR/TE), from
    get_nfl_defense_by_position.py. Same entering-the-week timing as
    get_nfl_weekly_defense_ranks() above, just with a position split the
    team-level file can't provide.
    """
    base = settings.NFL_BASE_URL
    return _load(f"{base}/weekly_defense_by_position.parquet", pd.read_parquet, "nfl defense by position")


@ttl_cache(OTHER_TTL)
def get_nfl_team_game_script() -> pd.DataFrame:
    """Team pass/run mix by score situation and quarter, from
    get_nfl_game_script.py. Feeds the Matchup page's game-script projection
    section.
    """
    base = settings.NFL_BASE_URL
    return _load(f"{base}/team_game_script.parquet", pd.read_parquet, "nfl team game script")


@ttl_cache(OTHER_TTL)
def get_nfl_player_situational_usage() -> pd.DataFrame:
    """Player carry/target share by score situation, from
    get_nfl_player_situational_usage.py. Feeds the Matchup page's
    "who this might shift volume toward" section.
    """
    base = settings.NFL_BASE_URL
    return _load(f"{base}/player_situational_usage.parquet", pd.read_parquet, "nfl player situational usage")


@ttl_cache(OTHER_TTL)
def get_nfl_rosters() -> pd.DataFrame:
    """Current team rosters, from get_nfl_rosters.py -- used to filter
    player-level projections to players actually still on the team, since
    the underlying usage data can be a season-old fallback (see that
    script's docstring for the Mike Evans example).
    """
    base = settings.NFL_BASE_URL
    return _load(f"{base}/rosters.parquet", pd.read_parquet, "nfl rosters")


@ttl_cache(MLB_TTL)
def get_pitcher_names() -> list:
    """Lightweight loader — the pitcher dropdown only.

    Reads starters.parquet: every pitcher with a start this season, named from
    the MLB Stats API so the value matches daily_matchups.parquet exactly.
    """
    base = settings.MLB_BASE_URL
    try:
        raw = _fetch_bytes(f"{base}/starters.parquet")
        df = pd.read_parquet(io.BytesIO(raw))
        return sorted(df["pitcher"].dropna().unique().tolist())
    except Exception as e:
        print(f"Warning: could not load starters parquet: {e}")
        return []


@ttl_cache(MLB_TTL)
def get_mlb_props_data() -> pd.DataFrame:
    """Separate cache for props — only loaded when the MLBProps page is hit."""
    base = settings.MLB_BASE_URL
    return _load(f"{base}/Daily_Props.xlsx", pd.read_excel, "props")


@ttl_cache(MLB_TTL)
def get_mlb_data() -> dict:
    base = settings.MLB_BASE_URL

    # (key, filename, reader)
    files = [
        # --- MLB Stats API, rebuilt by GitHub Actions ---
        ("starters", "starters.parquet", pd.read_parquet),          # dropdown + season stats
        ("season_pitching_stats", "season_pitching_stats.parquet", pd.read_parquet),  # all pitchers, SP+RP
        ("pitcher_logs", "pitcher_logs.parquet", pd.read_parquet),  # recent game logs
        ("bullpen_logs", "bullpen_logs.parquet", pd.read_parquet),  # all appearances, for bullpen workload
        ("matchups", "daily_matchups.parquet", pd.read_parquet),    # opposing hitters
        ("probable_starters", "probable_starters.parquet", pd.read_parquet),  # today's starters, no lineup required
        ("schedule_results", "schedule_results.parquet", pd.read_parquet),  # completed games -- records, recent form, head-to-head
        # --- Statcast, rebuilt by GitHub Actions ---
        ("hot_hitters", "hot_hitters.parquet", pd.read_parquet),    # hot hitters table
        ("mlb_rosters", "mlb_rosters.parquet", pd.read_parquet),    # player_id -> current team lookup
        ("pitcher_splits", "pitcher_splits.parquet", pd.read_parquet),  # vs L / vs R
        ("pitcher_percentiles", "pitcher_percentiles.parquet", pd.read_parquet),
        ("hitter_percentiles", "hitter_percentiles.parquet", pd.read_parquet),
    ]

    return {key: _load(f"{base}/{name}", reader, key) for key, name, reader in files}
