from functools import lru_cache
import pandas as pd
import requests
import io
from app.config import settings

def _fetch_bytes(url: str) -> bytes:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept": "*/*"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    return r.content

@lru_cache(maxsize=1)
def get_nba_data() -> pd.DataFrame:
    raw = _fetch_bytes(settings.NBA_STATS_URL)
    df = pd.read_parquet(io.BytesIO(raw))
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]
    return df

@lru_cache(maxsize=1)
def get_nfl_stats() -> pd.DataFrame:
    raw = _fetch_bytes(settings.NFL_STATS_URL)
    df = pd.read_parquet(io.BytesIO(raw))
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]
    return df

@lru_cache(maxsize=1)
def get_nfl_team_stats() -> pd.DataFrame:
    raw = _fetch_bytes(settings.NFL_TEAM_STATS_URL)
    return pd.read_excel(io.BytesIO(raw))

@lru_cache(maxsize=1)
def get_nfl_schedule() -> pd.DataFrame:
    raw = _fetch_bytes(settings.NFL_SCHEDULE_URL)
    return pd.read_excel(io.BytesIO(raw))

@lru_cache(maxsize=1)
def get_nba_props() -> pd.DataFrame:
    raw = _fetch_bytes(settings.NBA_PROPS_URL)
    return pd.read_excel(io.BytesIO(raw))

@lru_cache(maxsize=1)
def get_pitcher_names() -> list:
    """Lightweight loader — only fetches the small pitcher names parquet file."""
    base = settings.MLB_BASE_URL
    try:
        raw = _fetch_bytes(f"{base}/Historical_Starting_Pitchers.parquet")
        df = pd.read_parquet(io.BytesIO(raw))
        col = next((c for c in df.columns if "savant_name" in c.lower() or "savant name" in c.lower()), df.columns[0])
        return sorted(df[col].dropna().unique().tolist())
    except Exception as e:
        print(f"Warning: could not load pitcher names parquet: {e}")
        return []

@lru_cache(maxsize=1)
def get_mlb_props_data() -> pd.DataFrame:
    """Separate cache for props — only loaded when MLBProps page is accessed."""
    base = settings.MLB_BASE_URL
    try:
        raw = _fetch_bytes(f"{base}/Daily_Props.xlsx")
        return pd.read_excel(io.BytesIO(raw))
    except Exception as e:
        print(f"Warning: could not load props: {e}")
        return pd.DataFrame()

@lru_cache(maxsize=1)
def get_mlb_data() -> dict:
    base = settings.MLB_BASE_URL

    # Core matchup files — parquet where available, smallest xlsx otherwise
    xlsx_files = {
        "pitcher_season_stats":   f"{base}/Pitcher_Season_Stats.xlsx",
        "historical_starters":    f"{base}/Historical_Starting_Pitchers.xlsx",
        "pitcher_splits_hist":    f"{base}/Historical_Pitcher_Splits.xlsx",
        "combined_daily":         f"{base}/Combined_Daily_Data.xlsx",
        "last_week_stats":        f"{base}/Last_Week_Stats.xlsx",
    }
    parquet_files = {
        "pitcher_game_logs":      f"{base}/Pitcher_Game_Logs_2026.parquet",
    }
    csv_files = {
        "pitcher_percentiles":    f"{base}/Pitcher_Percentile_Rankings.csv",
        "hitter_percentiles":     f"{base}/Hitter_Percentile_Rankings.csv",
    }

    result = {}

    for key, url in xlsx_files.items():
        try:
            raw = _fetch_bytes(url)
            result[key] = pd.read_excel(io.BytesIO(raw))
        except Exception as e:
            print(f"Warning: could not load {key}: {e}")
            result[key] = pd.DataFrame()

    for key, url in parquet_files.items():
        try:
            raw = _fetch_bytes(url)
            result[key] = pd.read_parquet(io.BytesIO(raw))
        except Exception as e:
            print(f"Warning: could not load {key}: {e}")
            result[key] = pd.DataFrame()

    for key, url in csv_files.items():
        try:
            raw = _fetch_bytes(url)
            result[key] = pd.read_csv(io.BytesIO(raw))
        except Exception as e:
            print(f"Warning: could not load {key}: {e}")
            result[key] = pd.DataFrame()

    return result
