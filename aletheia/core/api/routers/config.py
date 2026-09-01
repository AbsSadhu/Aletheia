"""System configuration endpoints (backed by ConfigManager, see also Settings).

  GET  /config
  POST /config
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1")


@router.get("/config")
async def get_config() -> dict:
    """Retrieve the current system configuration with masked secrets."""
    from aletheia.config.config_manager import ConfigManager
    config = ConfigManager().load()
    return config.masked_dict()


@router.post("/config")
async def update_config(updated_config: dict) -> dict:
    """Update system configuration, save to disk/keyring, and refresh settings cache."""
    from aletheia.config.config_manager import ConfigManager, AletheiaConfig
    from aletheia.core.config.settings import get_settings

    manager = ConfigManager()
    current = manager.load()
    current_dict = current.model_dump()

    for key, val in updated_config.items():
        if key in current_dict:
            # If the user submitted a masked placeholder, keep the existing value
            if isinstance(val, str) and (all(c == "*" for c in val) or "..." in val):
                continue
            current_dict[key] = val

    try:
        new_config = AletheiaConfig(**current_dict)
        saved = manager.save(new_config)
        # Clear settings cache so new settings are loaded on the next call
        get_settings.cache_clear()
        return saved.masked_dict()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
