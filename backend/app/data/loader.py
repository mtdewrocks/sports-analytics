import io
import time
from functools import wraps

import pandas as pd
import requests

from app.config import settings


# How long an EMPTY refresh is trusted before the next request tries again --
# short, unlike the real TTLs above, because an empty result is exactly the
# shape a failed fetch degrades to (see the is_empty comment below) and
# shouldn't get to block real data from loading for a full hour.
EMPTY_RETRY_SECONDS = 30


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

            # loader.py's own `_load()` helper degrades a failed fetch (a
            # timeout, a 404, a corrupt parquet) to an EMPTY frame instead of
            # raising, specifically so one bad fetch doesn't 500 the page --
            # but that means an empty result reaching this decorator can mean
            # either "genuinely fetched, genuinely nothing there" or "the
            # fetch quietly failed". Treating the two the same way exceptions
            # are treated -- keep serving the last real value, if there is
            # one -- avoids a transient GitHub hiccup wiping a page (e.g. NFL
            # Team Usage going blank) for a full TTL. With no real value
            # cached yet, the empty result is still served (so a page with
            # genuinely no data yet doesn't hang), but only trusted for
            # EMPTY_RETRY_SECONDS rather than the full TTL, so the next
            # request retries soon instead of waiting out the hour.
            is_empty = hasattr(value, "empty") and value.empty
            if is_empty and hit:
                print(f"Warning: {func.__name__} refresh came back empty; serving cached copy")
                return hit[0]

            store[key] = (value, now - seconds + EMPTY_RETRY_SECONDS if is_empty else now)
            return value

        wrapper.cache_clear = store.clear
        return wrapper

    return decorator


# Files rewritten by GitHub Actions through the day.
MLB_TTL = 600     # 10 minutes
# Other sports, updated far less often.
OTHER_TTL = 3600  # 1 hour


# Where a file lived before the move to release assets. Keyed by the release
# base so a URL can be rewritten back to its old home.
#
# This exists so the migration can go one workflow at a time instead of as a
# flag day. Point the config at the release now; a file whose workflow has not
# been converted yet is still on `main` and is served from there, with a line
# in the log naming it. When the log goes quiet, every producer has moved and
# this whole block (plus LEGACY_BASES) can be deleted.
LEGACY_BASES = {
    "https://github.com/mtdewrocks/sports-analytics/releases/download/data-mlb":
        "https://github.com/mtdewrocks/sports-analytics/raw/main/backend/data/mlb",
    "https://github.com/mtdewrocks/sports-analytics/releases/download/data-nfl":
        "https://github.com/mtdewrocks/sports-analytics/raw/main/backend/data/nfl",
}


def _legacy_url(url: str) -> str | None:
    for release_base, raw_base in LEGACY_BASES.items():
        if url.startswith(release_base):
            return raw_base + url[len(release_base):]
    return None


def _fetch_bytes(url: str) -> bytes:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "*/*",
        # GitHub raw sits behind a CDN that will happily hand back a cached
        # copy, which would defeat the TTL above.
        "Cache-Control": "no-cache",
    }
    r = requests.get(url, headers=headers, timeout=30)

    # A 404 on a release asset means that file's producer hasn't been converted
    # yet, so fall back to where it still lives. Only 404 -- a 500 or a timeout
    # is GitHub having a bad minute, and retrying those against a different URL
    # would just mask it.
    if r.status_code == 404:
        legacy = _legacy_url(url)
        if legacy:
            print(f"Note: {url.rsplit('/', 1)[-1]} not in its release yet; serving from main")
            r = requests.get(legacy, headers=headers, timeout=30)

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
    """Full schedule, from get_nfl_weekly_stats.py's own parquet output --
    same nflverse source it already fetches internally for scoring, now
    also persisted as its own committed file so this matches the same
    scheduled-script-writes-a-parquet pattern every other NFL/MLB data
    source in this app already follows, rather than hitting a live
    third-party URL directly on every cache refresh. The script runs
    daily, so a missed scheduled run (a known, if rare, GitHub Actions
    quirk -- see the bullpen logs incident) costs at most a day's staleness
    against a weekly game schedule, not a meaningful gap.
    """
    base = settings.NFL_BASE_URL
    return _load(f"{base}/nfl_schedule.parquet", pd.read_parquet, "nfl schedule")


@ttl_cache(OTHER_TTL)
def get_nfl_weather_forecast() -> pd.DataFrame:
    """Live wind/temp/precip forecast for upcoming (not-yet-started) NFL
    games, from Open-Meteo -- see get_weather_forecast.py's own docstring
    for the full methodology. Rebuilt every 2 hours by that script, so this
    OTHER_TTL just bounds how long a worker serves its own last fetch
    between GitHub Actions runs, not how often the forecast itself moves.
    """
    base = settings.NFL_BASE_URL
    return _load(f"{base}/nfl_weather_forecast.parquet", pd.read_parquet, "nfl weather forecast")


@ttl_cache(OTHER_TTL)
def get_nfl_game_lines() -> pd.DataFrame:
    """Daily game-level spreads/totals, from get_game_lines.py -- pulled
    once a day (separate from the frequent player-props pull) since
    spreads/totals live on the Odds API's bulk sport-level endpoint, so one
    call covers every upcoming game. Preferred over get_nfl_schedule()'s
    own baked-in spread_line/total_line by get_game_script_projection()
    when a match exists here, since this reflects the CURRENT sportsbook
    line rather than whatever nflverse's schedule file had at its own last
    once-a-day refresh from a third-party source.
    """
    base = settings.NFL_BASE_URL
    return _load(f"{base}/game_lines.parquet", pd.read_parquet, "nfl game lines")


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


@ttl_cache(OTHER_TTL)
def get_nfl_season_totals() -> pd.DataFrame:
    """Per-player season totals across multiple seasons, from
    get_nfl_season_totals.py -- feeds the Season Stat Screener page.
    Pulled directly from nflverse, not Player_Stats_Weekly.parquet, since
    that file was found to have zero rows for the current in-progress
    season.
    """
    base = settings.NFL_BASE_URL
    return _load(f"{base}/player_season_totals.parquet", pd.read_parquet, "nfl season totals")


@ttl_cache(OTHER_TTL)
def get_nfl_player_box_stats() -> pd.DataFrame:
    """Per-player weekly box scores (passing/rushing/receiving), current
    season plus the one before it, from get_nfl_player_box_stats.py --
    feeds the NFL Game Log page's season toggle. A separate source from
    get_nfl_stats() (Player_Stats_Weekly.parquet) for the same reason as
    get_nfl_season_totals() above: that legacy file was found to sit frozen
    on last season and never pick up the current one.
    """
    base = settings.NFL_BASE_URL
    return _load(f"{base}/player_box_stats.parquet", pd.read_parquet, "nfl player box stats")


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


# Props files by sport. Both sports write the same schema from get_props.py,
# so one reader serves both -- only the URL differs.
_PROPS_URLS = {
    "mlb": lambda: settings.MLB_PROPS_URL,
    "nfl": lambda: settings.NFL_PROPS_URL,
}
_MIDDLES_URLS = {
    "mlb": lambda: f"{settings.MLB_BASE_URL}/mlb_prop_middles.parquet",
    "nfl": lambda: f"{settings.NFL_BASE_URL}/nfl_prop_middles.parquet",
}


_SNAPSHOT_URLS = {
    "mlb": lambda: f"{settings.MLB_BASE_URL}/mlb_odds_snapshots.parquet",
    "nfl": lambda: f"{settings.NFL_BASE_URL}/nfl_odds_snapshots.parquet",
}
_CLOSING_URLS = {
    "mlb": lambda: f"{settings.MLB_BASE_URL}/mlb_closing_lines.parquet",
    "nfl": lambda: f"{settings.NFL_BASE_URL}/nfl_closing_lines.parquet",
}


@ttl_cache(MLB_TTL)
def get_odds_snapshots_data(sport: str) -> pd.DataFrame:
    """Price history from build_odds_snapshots.py -- one row per prop per
    book each time its price CHANGED. Empty until the first workflow run
    after that script ships; every reader treats empty as "no history yet"."""
    url = _SNAPSHOT_URLS.get(sport)
    if url is None:
        return pd.DataFrame()
    return _load(url(), pd.read_parquet, f"{sport} odds snapshots")


@ttl_cache(MLB_TTL)
def get_closing_lines_data(sport: str) -> pd.DataFrame:
    """Last pre-game price per prop per book, from build_odds_snapshots.py."""
    url = _CLOSING_URLS.get(sport)
    if url is None:
        return pd.DataFrame()
    return _load(url(), pd.read_parquet, f"{sport} closing lines")


@ttl_cache(MLB_TTL)
def get_props_data(sport: str) -> pd.DataFrame:
    """Long-format props for one sport."""
    url = _PROPS_URLS.get(sport)
    if url is None:
        return pd.DataFrame()
    return _load(url(), pd.read_parquet, f"{sport} props")


@ttl_cache(MLB_TTL)
def get_middles_data(sport: str) -> pd.DataFrame:
    """Priced middle/arb pairs for one sport, from build_prop_middles.py."""
    url = _MIDDLES_URLS.get(sport)
    if url is None:
        return pd.DataFrame()
    return _load(url(), pd.read_parquet, f"{sport} middles")


@ttl_cache(MLB_TTL)
def get_mlb_props_data() -> pd.DataFrame:
    """Separate cache for props — only loaded when the MLBProps page is hit.

    Its own setting rather than MLB_BASE_URL so the producer can change without
    touching the rest of the loader -- which is exactly what happened: it was a
    hand-maintained xlsx on `main`, and is now a parquet built by
    update_props.yml and published to the data-mlb release.

    get_mlb_props() in app/data/mlb.py pivots this wide, and it finds its
    columns by name, so "Player" / "market" / "Line" / "bookmakers" /
    "Over Price" are a contract with get_mlb_props.py.
    """
    return _load(settings.MLB_PROPS_URL, pd.read_parquet, "props")


@ttl_cache(MLB_TTL)
def get_mlb_data() -> dict:
    base = settings.MLB_BASE_URL

    # (key, filename, reader)
    files = [
        # --- MLB Stats API, rebuilt by GitHub Actions ---
        ("starters", "starters.parquet", pd.read_parquet),          # dropdown + season stats
        ("season_pitching_stats", "season_pitching_stats.parquet", pd.read_parquet),  # all pitchers, SP+RP
        ("pitcher_logs", "pitcher_logs.parquet", pd.read_parquet),  # recent game logs
        ("batter_logs", "batter_logs.parquet", pd.read_parquet),   # per-game batter box scores (Hit Rate Sheet)
        ("bullpen_logs", "bullpen_logs.parquet", pd.read_parquet),  # all appearances, for bullpen workload
        ("matchups", "daily_matchups.parquet", pd.read_parquet),    # opposing hitters
        ("probable_starters", "probable_starters.parquet", pd.read_parquet),  # today's starters, no lineup required
        ("schedule_results", "schedule_results.parquet", pd.read_parquet),  # completed games -- records, recent form, head-to-head
        # --- Statcast, rebuilt by GitHub Actions ---
        ("hot_hitters", "hot_hitters.parquet", pd.read_parquet),    # hot hitters table
        ("mlb_rosters", "mlb_rosters.parquet", pd.read_parquet),    # player_id -> current team lookup
        ("pitcher_splits", "pitcher_splits.parquet", pd.read_parquet),  # vs L / vs R
        ("team_hitting_splits", "team_hitting_splits.parquet", pd.read_parquet),  # team wOBA vs LHP/RHP, season + L30
        ("pitcher_percentiles", "pitcher_percentiles.parquet", pd.read_parquet),
        ("hitter_percentiles", "hitter_percentiles.parquet", pd.read_parquet),
        # --- Odds API, rebuilt daily by get_game_lines.py (separate,
        # cheaper cadence from the props pull -- see that script's
        # docstring) ---
        ("game_lines", "game_lines.parquet", pd.read_parquet),  # daily spread/total, for Hit Rate Sheet
        # --- Open-Meteo, rebuilt every 2 hours by get_weather_forecast.py ---
        ("weather_forecast", "mlb_weather_forecast.parquet", pd.read_parquet),  # live forecast, upcoming games only
    ]

    return {key: _load(f"{base}/{name}", reader, key) for key, name, reader in files}
