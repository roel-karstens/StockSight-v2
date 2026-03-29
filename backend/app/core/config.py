"""
config.py — Application settings via Pydantic BaseSettings.

Reads from environment variables / .env file.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ENV: str = "development"
    APP_NAME: str = "StockSight"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://portfolio:portfolio_secret@localhost:5432/portfolio_db"
    )

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Cache TTLs (seconds)
    CACHE_TTL_PRICES: int = 3600  # 1 hour
    CACHE_TTL_FUNDAMENTALS: int = 86400  # 24 hours

    # HTTP scraping
    REQUEST_TIMEOUT: int = 30
    REQUEST_DELAY: float = 1.5  # polite delay between scrape requests

    # DCF defaults
    DCF_DEFAULT_WACC: float = 0.10
    DCF_DEFAULT_TERMINAL_GROWTH: float = 0.03
    DCF_DEFAULT_YEARS: int = 10

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
