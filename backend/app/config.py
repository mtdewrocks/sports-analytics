from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    SECRET_KEY: str = "changeme-in-production-use-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 7
    DATABASE_URL: str = "sqlite:///./sports_analytics.db"
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PRICE_ID: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    FRONTEND_URL: str = "http://localhost:5173"
    TRIAL_DAYS: int = 30
    NBA_STATS_URL: str = "https://github.com/mtdewrocks/sports_analysis/raw/main/data/NBA_Player_Stats.parquet"
    NFL_STATS_URL: str = "https://github.com/mtdewrocks/sports_analysis/raw/main/data/Player_Stats_Weekly.parquet"
    NFL_TEAM_STATS_URL: str = "https://github.com/mtdewrocks/sports_analysis/raw/main/data/2025_Team_Stats.xlsx"
    NFL_SCHEDULE_URL: str = "https://github.com/mtdewrocks/sports_analysis/raw/main/data/schedule.xlsx"
    NBA_PROPS_URL: str = "https://github.com/mtdewrocks/sports_analysis/raw/main/data/Basketball_Props.xlsx"
    MLB_BASE_URL: str = "https://github.com/mtdewrocks/matchup/raw/main/assets"

settings = Settings()

# SQLAlchemy requires "postgresql://" but Render provides "postgres://"
# Auto-fix this common gotcha so it works regardless of what Render gives us
if settings.DATABASE_URL.startswith("postgres://"):
    settings.DATABASE_URL = settings.DATABASE_URL.replace("postgres://", "postgresql://", 1)
