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
def get_mlb_data() -> dict:
    base = settings.MLB_BASE_URL
    files = {
        "pitcher_stats": f"{base}/Pitcher_Stats.xlsx",
        "pitcher_game_logs": f"{base}/MLB_Pitcher_Game_Logs.xlsx",
        "hitter_stats": f"{base}/Aggregated_Hitter_Statistics.xlsx",
        "hitter_game_logs": f"{base}/Hitter_Game_Logs.xlsx",
        "current_hitters": f"{base}/current_day_hitters.xlsx",
        "pitcher_percentiles": f"{base}/Pitcher_Percentile_Rankings.csv",
        "hot_hitters": f"{base}/Top_Hitter_Picks.xlsx",
        "props": f"{base}/Daily_Props.xlsx",
    }
    result = {}
    for key, url in files.items():
        try:
            raw = _fetch_bytes(url)
            result[key] = pd.read_csv(io.BytesIO(raw)) if url.endswith(".csv") else pd.read_excel(io.BytesIO(raw))
        except Exception as e:
            print(f"Warning: could not load {key}: {e}")
            result[key] = pd.DataFrame()
    return result
