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

    # API
    cors_origins: str = "http://localhost:3000"  # comma-separated
    eod_token: str | None = None  # bearer token for POST /jobs/eod
    approve_token: str | None = None  # optional bearer token for approving commentary

    # AI copilot
    anthropic_api_key: str | None = None
    agent_model: str = "claude-opus-5-5"
    agent_effort: str = "medium"
    agent_max_tool_calls: int = 8
    agent_max_retries: int = 2
    chat_daily_limit: int = 200  # questions per UTC day, protects the API budget


@lru_cache
def get_settings() -> Settings:
    return Settings()
