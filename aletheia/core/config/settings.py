from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ALETHEIA_",
        case_sensitive=False,
    )

    env: str = "development"
    debug: bool = True
    host: str = "127.0.0.1"
    port: int = 8899
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173,tauri://localhost"
    sqlite_path: Path = Field(default=Path("./data/aletheia.sqlite3"))
    duckdb_path: Path = Field(default=Path("./data/aletheia.duckdb"))
    data_dir: Path = Field(default=Path("./data"))
    reports_dir: Path = Field(default=Path("./data/reports"))
    exports_dir: Path = Field(default=Path("./data/exports"))
    ollama_base_url: str = "http://127.0.0.1:11434"
    default_llm_provider: str = "ollama"
    default_llm_model: str = "mistral:7b"
    enable_cloud_llm_fallback: bool = False
    enable_audit_logs: bool = True
    enable_desktop_bridge: bool = True
    yfinance_enabled: bool = True
    ccxt_enabled: bool = True
    nse_enabled: bool = True
    rbi_enabled: bool = True
    langsmith_tracing: bool = False
    langsmith_api_key: str | None = None
    langsmith_project: str = "aletheia"

    def ensure_directories(self) -> None:
        for path in (self.data_dir, self.reports_dir, self.exports_dir):
            path.mkdir(parents=True, exist_ok=True)

        import os
        if self.langsmith_tracing:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            if self.langsmith_api_key:
                os.environ["LANGCHAIN_API_KEY"] = self.langsmith_api_key
            os.environ["LANGCHAIN_PROJECT"] = self.langsmith_project

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings

