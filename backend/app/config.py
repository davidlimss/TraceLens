from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_version: str = "0.2.0-beta.1"
    app_env: str = "development"
    require_migrations: bool = True
    schema_revision: str = "0007_vigil_replay_snapshots"
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
    # Provider-neutral LLM settings.  The legacy GITHUB_MODELS_* variables
    # remain as a backwards-compatible fallback for existing deployments.
    llm_provider: str = "github_models"
    llm_api_key: str = ""
    llm_endpoint: str = ""
    llm_model: str = ""
    llm_max_tool_rounds: int = 8
    llm_max_tool_calls: int = 20
    llm_max_same_tool_repetition: int = 2
    llm_no_progress_limit: int = 2
    llm_timeout_seconds: int = 60
    llm_max_tool_result_characters: int = 8000
    llm_max_output_tokens: int = 2048
    llm_max_repair_attempts: int = 2
    llm_max_plan_revisions: int = 3
    llm_max_hypotheses: int = 8
    max_upload_bytes: int = 50 * 1024 * 1024
    upload_rate_limit: int = 10
    chat_rate_limit: int = 20
    login_rate_limit: int = 10
    rate_limit_window_seconds: int = 60
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = "change-me-local"
    session_ttl_hours: int = 12
    secure_cookies: bool = False
    allow_raw_log_to_external_provider: bool = False
    stuck_job_minutes: int = 10
    agent_stuck_minutes: int = 5
    integrity_check_interval_seconds: int = 86400
    # External evidence plane.  These connectors are read-only and disabled by default.
    external_sources_enabled: bool = False
    external_case_field: str = "tracelens.case_id"
    external_search_timeout_seconds: float = 15.0
    external_max_results: int = 100
    external_max_retries: int = 2
    external_circuit_breaker_threshold: int = 3
    external_circuit_breaker_window_seconds: int = 60
    opensearch_url: str = ""
    opensearch_index: str = ""
    opensearch_username: str = ""
    opensearch_password: str = ""
    opensearch_api_key: str = ""
    splunk_url: str = ""
    splunk_index: str = ""
    splunk_token: str = ""
    splunk_case_field: str = "tracelens_case_id"
    wazuh_indexer_url: str = ""
    wazuh_index: str = "wazuh-alerts-*"
    wazuh_username: str = ""
    wazuh_password: str = ""
    wazuh_api_key: str = ""
    mcp_external_in_process: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
