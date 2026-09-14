from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SECRET_KEY: str = "changeme-in-production-use-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7
    DATABASE_URL: str = "sqlite:///./sports_analytics.db"
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PRICE_ID_MONTHLY: str = ""
    STRIPE_PRICE_ID_YEARLY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    FRONTEND_URL: str = "http://localhost:5173"
    TRIAL_DAYS: int = 30
    NBA_STATS_URL: str = "https://github.com/mtdewrocks/sports_analysis/raw/main/data/NBA_Player_Stats.parquet"
    NFL_STATS_URL: str = "https://github.com/mtdewrocks/sports_analysis/raw/main/data/Player_Stats_Weekly.parquet"
    NFL_TEAM_STATS_URL: str = "https://github.com/mtdewrocks/sports_analysis/raw/main/data/2025_Team_Stats.xlsx"
    NBA_PROPS_URL: str = "https://github.com/mtdewrocks/sports_analysis/raw/main/data/Basketball_Props.xlsx"
    # Release assets rather than files on `main`. Same URL SHAPE -- loader.py
    # builds every path as f"{base}/{filename}" and needs no change -- but the
    # bytes now come out of a GitHub Release instead of git history, so an
    # hourly data refresh no longer writes a commit, no longer grows the repo,
    # and no longer triggers a Render redeploy.
    #
    # Release assets are a FLAT namespace per tag: there are no subdirectories,
    # so filenames must be unique within a tag. That is why MLB and NFL get
    # separate tags rather than one shared one.
    #
    # Pitcher headshots deliberately stay on `main` -- they are append-only,
    # cause no history churn, and the frontend links them as a directory
    # (MLBMatchup.tsx IMAGE_BASE), which a flat asset namespace cannot serve.
    MLB_BASE_URL: str = "https://github.com/mtdewrocks/sports-analytics/releases/download/data-mlb"
    NFL_BASE_URL: str = "https://github.com/mtdewrocks/sports-analytics/releases/download/data-nfl"

settings = Settings()

# SQLAlchemy requires "postgresql://" but Render provides "postgres://"
# Auto-fix this common gotcha so it works regardless of what Render gives us
if settings.DATABASE_URL.startswith("postgres://"):
    settings.DATABASE_URL = settings.DATABASE_URL.replace("postgres://", "postgresql://", 1)
