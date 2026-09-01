from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

try:
    import keyring
    from keyring.errors import KeyringError
except Exception:  # pragma: no cover
    keyring = None

    class KeyringError(Exception):
        pass


from aletheia.security.secrets import decrypt_sensitive, encrypt_sensitive, mask_for_logs

APP_DIR = Path.home() / ".aletheia"
CONFIG_PATH = APP_DIR / "config.json"
ENV_PATH = Path.cwd() / ".env"
KEYRING_SERVICE = "aletheia"

SENSITIVE_FIELDS = {
    "anthropic_api_key",
    "openai_api_key",
    "gemini_api_key",
    "zerodha_api_key",
    "zerodha_api_secret",
    "tradingview_session",
    "db_encryption_key",
}

# Field names below match aletheia.core.config.settings.Settings 1:1 (where a
# Settings counterpart exists) so this map is a trivial ALETHEIA_ prefix, not
# a translation table. zerodha_api_key/zerodha_api_secret/tradingview_session
# have no Settings equivalent (broker/TradingView creds are ConfigManager-only)
# and are intentionally absent here, matching prior behavior.
ENV_FIELD_MAP = {
    "ollama_base_url": "ALETHEIA_OLLAMA_BASE_URL",
    "default_llm_model": "ALETHEIA_DEFAULT_LLM_MODEL",
    "default_llm_provider": "ALETHEIA_DEFAULT_LLM_PROVIDER",
    "openai_api_key": "OPENAI_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "gemini_api_key": "GEMINI_API_KEY",
    "yfinance_enabled": "ALETHEIA_YFINANCE_ENABLED",
    "ccxt_enabled": "ALETHEIA_CCXT_ENABLED",
    "sqlite_path": "ALETHEIA_SQLITE_PATH",
    "db_encryption_key": "ALETHEIA_DB_ENCRYPTION_KEY",
    "duckdb_path": "ALETHEIA_DUCKDB_PATH",
    "log_dir": "ALETHEIA_LOG_DIR",
    "backup_dir": "ALETHEIA_BACKUP_DIR",
}


# Pre-rename field/value names, kept only so a config.json or keyring entry
# saved before the AletheiaConfig/Settings name unification still loads
# correctly instead of silently reverting to defaults. New saves always use
# the current names; this is read-side only.
_LEGACY_FIELD_NAMES = {
    "ollama_host": "ollama_base_url",
    "ollama_model": "default_llm_model",
    "frontier_provider": "default_llm_provider",
    "claude_api_key": "anthropic_api_key",
    "gpt_api_key": "openai_api_key",
    "db_path": "sqlite_path",
}
_LEGACY_PROVIDER_VALUES = {"local": "ollama", "claude": "anthropic", "gpt": "openai"}


def _migrate_legacy_config_dict(data: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(data)
    for old_name, new_name in _LEGACY_FIELD_NAMES.items():
        if old_name in migrated and new_name not in migrated:
            migrated[new_name] = migrated.pop(old_name)
        else:
            migrated.pop(old_name, None)
    provider = migrated.get("default_llm_provider")
    if provider in _LEGACY_PROVIDER_VALUES:
        migrated["default_llm_provider"] = _LEGACY_PROVIDER_VALUES[provider]
    return migrated


class AletheiaConfig(BaseModel):
    ollama_base_url: str = "http://localhost:11434"
    default_llm_model: str = "mistral:7b"
    default_llm_provider: Literal["anthropic", "openai", "gemini", "ollama"] = "ollama"
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    zerodha_api_key: str | None = None
    zerodha_api_secret: str | None = None
    tradingview_session: str | None = None
    yfinance_enabled: bool = True
    ccxt_enabled: bool = True
    sqlite_path: str = "~/.aletheia/aletheia.db"
    db_encryption_key: str | None = None
    duckdb_path: str = "~/.aletheia/quotes.duckdb"
    log_dir: str = "~/.aletheia/logs"
    backup_dir: str = "~/.aletheia/backups"

    def expanded(self) -> "AletheiaConfig":
        return self.model_copy(
            update={
                "sqlite_path": str(Path(self.sqlite_path).expanduser()),
                "duckdb_path": str(Path(self.duckdb_path).expanduser()),
                "log_dir": str(Path(self.log_dir).expanduser()),
                "backup_dir": str(Path(self.backup_dir).expanduser()),
            }
        )

    def masked_dict(self) -> dict[str, Any]:
        data = self.expanded().model_dump()
        for field in SENSITIVE_FIELDS:
            data[field] = mask_for_logs(data.get(field))
        return data


class ConfigManager:
    def __init__(self, config_path: Path = CONFIG_PATH, env_path: Path = ENV_PATH) -> None:
        self.config_path = config_path
        self.env_path = env_path

    def load(self) -> AletheiaConfig:
        data = self._load_file_config()
        data.update(self._load_keyring_secrets())
        data.update(self._load_env_overrides())
        config = AletheiaConfig(**data).expanded()
        self._validate_config(config)
        return config

    def save(self, config: AletheiaConfig) -> AletheiaConfig:
        config = config.expanded()
        self._validate_config(config)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        payload: dict[str, Any] = {}
        for key, value in config.model_dump().items():
            if value is None:
                payload[key] = None
            elif key in SENSITIVE_FIELDS:
                payload[key] = encrypt_sensitive(str(value))
            else:
                payload[key] = value

        self.config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._store_keyring_secrets(config)
        self._sync_env_file(config)
        return config

    def set_value(self, key: str, value: str) -> AletheiaConfig:
        if key not in AletheiaConfig.model_fields:
            raise KeyError(f"Unknown config key: {key}")
        config = self.load()
        current_value = getattr(config, key)
        parsed: Any = value
        if isinstance(current_value, bool):
            parsed = value.strip().lower() in {"1", "true", "yes", "y", "on"}
        updated = config.model_copy(update={key: parsed})
        return self.save(updated)

    def reset(self) -> None:
        if self.config_path.exists():
            self.config_path.unlink()
        if self.env_path.exists():
            self.env_path.unlink()
        for field in SENSITIVE_FIELDS:
            self._delete_keyring_secret(field)

    def _validate_config(self, config: AletheiaConfig) -> None:
        if config.default_llm_provider != "ollama":
            field_name = {
                "openai": "openai_api_key",
                "anthropic": "anthropic_api_key",
                "gemini": "gemini_api_key",
            }[config.default_llm_provider]
            if not getattr(config, field_name):
                raise ValidationError.from_exception_data(
                    "AletheiaConfig",
                    [
                        {
                            "type": "missing",
                            "loc": (field_name,),
                            "msg": f"{field_name} is required for provider {config.default_llm_provider}",
                            "input": None,
                        }
                    ],
                )

        for field in ("sqlite_path", "duckdb_path"):
            Path(getattr(config, field)).expanduser().parent.mkdir(parents=True, exist_ok=True)
        for field in ("log_dir", "backup_dir"):
            Path(getattr(config, field)).expanduser().mkdir(parents=True, exist_ok=True)

    def _load_file_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        decoded: dict[str, Any] = {}
        for key, value in raw.items():
            decoded[key] = decrypt_sensitive(value) if isinstance(value, str) else value
        return _migrate_legacy_config_dict(decoded)

    def _load_keyring_secrets(self) -> dict[str, str]:
        if keyring is None:
            return {}
        values: dict[str, str] = {}
        for field in SENSITIVE_FIELDS:
            legacy_field = next(
                (old for old, new in _LEGACY_FIELD_NAMES.items() if new == field), None
            )
            for lookup_name in (field, legacy_field):
                if lookup_name is None:
                    continue
                try:
                    secret = keyring.get_password(KEYRING_SERVICE, lookup_name)
                except KeyringError:
                    continue
                if secret:
                    values[field] = secret
                    break
        return values

    def _store_keyring_secrets(self, config: AletheiaConfig) -> None:
        if keyring is None:
            return
        for field in SENSITIVE_FIELDS:
            value = getattr(config, field)
            if not value:
                self._delete_keyring_secret(field)
                continue
            try:
                keyring.set_password(KEYRING_SERVICE, field, value)
            except KeyringError:
                continue

    def _delete_keyring_secret(self, field: str) -> None:
        if keyring is None:
            return
        try:
            keyring.delete_password(KEYRING_SERVICE, field)
        except Exception:
            return

    def _load_env_overrides(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for field, env_name in ENV_FIELD_MAP.items():
            raw = os.getenv(env_name)
            if raw is None or raw == "":
                continue
            if isinstance(AletheiaConfig.model_fields[field].default, bool):
                data[field] = raw.strip().lower() in {"1", "true", "yes", "y", "on"}
            else:
                data[field] = raw

        return data

    def _sync_env_file(self, config: AletheiaConfig) -> None:
        current: dict[str, str] = {}
        if self.env_path.exists():
            for line in self.env_path.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    key, value = line.split("=", 1)
                    current[key] = value

        current["ALETHEIA_DEFAULT_LLM_PROVIDER"] = config.default_llm_provider
        current["ALETHEIA_DEFAULT_LLM_MODEL"] = config.default_llm_model
        current["ALETHEIA_OLLAMA_BASE_URL"] = config.ollama_base_url
        current["ALETHEIA_YFINANCE_ENABLED"] = str(config.yfinance_enabled).lower()
        current["ALETHEIA_CCXT_ENABLED"] = str(config.ccxt_enabled).lower()
        current["ALETHEIA_SQLITE_PATH"] = config.sqlite_path
        current["ALETHEIA_DUCKDB_PATH"] = config.duckdb_path
        current["ALETHEIA_DB_ENCRYPTION_KEY"] = config.db_encryption_key or ""
        # Settings.openai_api_key/.anthropic_api_key/.gemini_api_key are read
        # under the ALETHEIA_ env_prefix (see core/config/settings.py) — that's
        # the name aletheia.core.llm.chat_llm actually reads. The bare names
        # are also written in case anything else expects the SDKs' own
        # conventional env var names directly.
        current["ALETHEIA_OPENAI_API_KEY"] = config.openai_api_key or ""
        current["ALETHEIA_ANTHROPIC_API_KEY"] = config.anthropic_api_key or ""
        current["ALETHEIA_GEMINI_API_KEY"] = config.gemini_api_key or ""
        current["OPENAI_API_KEY"] = config.openai_api_key or ""
        current["ANTHROPIC_API_KEY"] = config.anthropic_api_key or ""
        current["GEMINI_API_KEY"] = config.gemini_api_key or ""

        self.env_path.write_text(
            "".join(f"{key}={current[key]}\n" for key in sorted(current)),
            encoding="utf-8",
        )
