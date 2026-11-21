"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database ---
    database_url: str = "postgresql+asyncpg://opensre:opensre@localhost:5432/opensre"
    demo_database_url: str = "postgresql+asyncpg://opensre:opensre@localhost:5432/opensre_demo"

    # --- Backend ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"
    demo_admin_key: str = "change-me-admin-key"
    demo_fault_secret: str = "change-me-fault-secret"

    # --- Demo API / runtime lab ---
    demo_api_url: str = "http://localhost:8001"
    prometheus_url: str = "http://localhost:9090"
    demo_log_path: str = "./var/log/demo-api/app.log"

    # --- AI model provider ---
    llm_provider: str = "ollama"  # ollama | hosted
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.1:8b"
    llm_api_key: str = ""
    llm_timeout_seconds: float = 120.0
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096
    llm_tool_calling: bool = True

    # --- Investigation limits ---
    investigation_max_iterations: int = 6
    investigation_max_tool_calls: int = 20
    investigation_max_wall_time_seconds: float = 300.0
    investigation_max_context_bytes: int = 200_000
    investigation_max_tool_output_bytes: int = 262_144
    investigation_tool_timeout_seconds: float = 20.0

    # --- GitHub integration ---
    github_token: str = ""
    github_allowed_repos: str = ""
    github_webhook_secret: str = ""
    github_investigate_success: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_repos(self) -> set[str]:
        return {r.strip().lower() for r in self.github_allowed_repos.split(",") if r.strip()}

    @property
    def llm_configured(self) -> bool:
        if self.llm_provider == "ollama":
            return bool(self.llm_base_url and self.llm_model)
        return bool(self.llm_base_url and self.llm_model and self.llm_api_key)

    def github_repo_allowed(self, full_name: str) -> bool:
        repos = self.allowed_repos
        if not repos:
            return False
        return full_name.strip().lower() in repos


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
