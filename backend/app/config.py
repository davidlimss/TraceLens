from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://loginvestigator:change-me@localhost:5432/loginvestigator"
    redis_url: str = "redis://localhost:6379/0"
    evidence_storage_path: Path = Path("storage/evidence")
    cors_origins: str = "http://localhost:3000"
    server_timezone: str = "Asia/Jakarta"
    correlation_window_minutes: int = 10
    brute_force_window_minutes: int = 10
    brute_force_threshold: int = 5
    github_models_token: str = ""
    github_models_endpoint: str = "https://models.github.ai/inference"
    github_models_model: str = "openai/gpt-4.1-mini"
    llm_max_tool_rounds: int = 8
    llm_max_tool_calls: int = 20
    llm_max_same_tool_repetition: int = 2
    llm_no_progress_limit: int = 2
    llm_timeout_seconds: int = 60
    llm_max_tool_result_characters: int = 8000
    llm_max_output_tokens: int = 2048
    max_upload_bytes: int = 50 * 1024 * 1024
    upload_rate_limit: int = 10
    chat_rate_limit: int = 20
    rate_limit_window_seconds: int = 60
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "change-me-local"
    session_ttl_hours: int = 12
    secure_cookies: bool = False
    allow_raw_log_to_external_provider: bool = False
    stuck_job_minutes: int = 10
    integrity_check_interval_seconds: int = 86400

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
