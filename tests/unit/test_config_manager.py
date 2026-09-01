from __future__ import annotations

import json
from pathlib import Path

from aletheia.config.config_manager import AletheiaConfig, ConfigManager


def test_config_manager_round_trip(tmp_path: Path) -> None:
    manager = ConfigManager(config_path=tmp_path / "config.json", env_path=tmp_path / ".env")
    config = AletheiaConfig(
        default_llm_provider="openai",
        default_llm_model="gpt-4o-mini",
        openai_api_key="sk-secret-123456",
        sqlite_path=str(tmp_path / "data" / "aletheia.sqlite3"),
        duckdb_path=str(tmp_path / "data" / "quotes.duckdb"),
        log_dir=str(tmp_path / "logs"),
        backup_dir=str(tmp_path / "backups"),
    )

    manager.save(config)

    payload = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert payload["openai_api_key"].startswith("enc:")

    loaded = manager.load()
    assert loaded.default_llm_provider == "openai"
    assert loaded.openai_api_key == "sk-secret-123456"
    assert "..." in loaded.masked_dict()["openai_api_key"]


def test_sync_env_file_uses_settings_prefixed_llm_keys(tmp_path: Path) -> None:
    """
    Regression test: `_sync_env_file` used to write bare `OPENAI_API_KEY` /
    `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` into `.env`, but `Settings` (see
    core/config/settings.py, env_prefix="ALETHEIA_") only reads the
    ALETHEIA_-prefixed forms — so an API key entered via the desktop Settings
    UI was silently never seen by aletheia.core.llm.chat_llm. Assert the
    written .env carries the prefixed names Settings actually reads.
    """
    from aletheia.core.config.settings import Settings

    manager = ConfigManager(config_path=tmp_path / "config.json", env_path=tmp_path / ".env")
    manager.save(
        AletheiaConfig(
            default_llm_provider="openai",
            openai_api_key="sk-test-openai",
            anthropic_api_key="sk-test-anthropic",
            gemini_api_key="test-gemini",
            sqlite_path=str(tmp_path / "db.sqlite3"),
            duckdb_path=str(tmp_path / "quotes.duckdb"),
            log_dir=str(tmp_path / "logs"),
            backup_dir=str(tmp_path / "backups"),
        )
    )

    env_text = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "ALETHEIA_OPENAI_API_KEY=sk-test-openai" in env_text
    assert "ALETHEIA_ANTHROPIC_API_KEY=sk-test-anthropic" in env_text
    assert "ALETHEIA_GEMINI_API_KEY=test-gemini" in env_text

    settings = Settings(_env_file=tmp_path / ".env")
    assert settings.openai_api_key == "sk-test-openai"
    assert settings.anthropic_api_key == "sk-test-anthropic"
    assert settings.gemini_api_key == "test-gemini"


def test_env_overrides_file(tmp_path: Path, monkeypatch) -> None:
    manager = ConfigManager(config_path=tmp_path / "config.json", env_path=tmp_path / ".env")
    manager.save(
        AletheiaConfig(
            default_llm_model="llama2",
            sqlite_path=str(tmp_path / "db.sqlite3"),
            duckdb_path=str(tmp_path / "quotes.duckdb"),
            log_dir=str(tmp_path / "logs"),
            backup_dir=str(tmp_path / "backups"),
        )
    )
    monkeypatch.setenv("ALETHEIA_DEFAULT_LLM_MODEL", "mistral:7b")
    assert manager.load().default_llm_model == "mistral:7b"
