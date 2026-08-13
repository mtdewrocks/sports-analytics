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
    raw = _fetch_bytes(settings.NFL_TEAM_STATS_URL)
    return pd.read_excel(io.BytesIO(raw))


@ttl_cache(OTHER_TTL)
def get_nfl_schedule() -> pd.DataFrame:
    raw = _fetch_bytes(settings.NFL_SCHEDULE_URL)
    return pd.read_excel(io.BytesIO(raw))


@ttl_cache(OTHER_TTL)
def get_nba_props() -> pd.DataFrame:
    raw = _fetch_bytes(settings.NBA_PROPS_URL)
    return pd.read_excel(io.BytesIO(raw))


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
        ("pitcher_logs", "pitcher_logs.parquet", pd.read_parquet),  # recent game logs
        ("matchups", "daily_matchups.parquet", pd.read_parquet),    # opposing hitters
        # --- still Excel / CSV: splits and percentiles ---
        ("pitcher_splits_agg", "Season_Aggregated_Pitcher_Statistics.xlsx", pd.read_excel),
        ("pitcher_percentiles", "pitcher_percentiles.parquet", pd.read_parquet),
        ("hitter_percentiles", "hitter_percentiles.parquet", pd.read_parquet),
        # --- hot hitters (get_hot_hitters reads this key) ---
        ("last_week_stats", "Last_Week_Stats.xlsx", pd.read_excel),
    ]

    return {key: _load(f"{base}/{name}", reader, key) for key, name, reader in files}
