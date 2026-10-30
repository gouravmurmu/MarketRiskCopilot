"""Settings loaded from environment variables (or a local .env file)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///riskcopilot.db"
    fred_api_key: str | None = None

    history_start: str = "2015-01-01"
    # Model used for limit checks and the headline number on the dashboard.
    primary_model: str = "hs_500"
    primary_confidence: float = 0.99
    mc_paths: int = 20_000
    mc_seed: int = 42
    stress_start: str = "2020-02-01"
    stress_end: str = "2021-01-31"


@lru_cache
def get_settings() -> Settings:
    return Settings()
