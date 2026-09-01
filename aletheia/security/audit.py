from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from aletheia.security.secrets import mask_for_logs

SENSITIVE_FIELD_MARKERS = ("key", "secret", "token", "password", "session")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            if any(marker in str(key).lower() for marker in SENSITIVE_FIELD_MARKERS):
                result[key] = mask_for_logs(str(item) if item is not None else None)
            else:
                result[key] = _redact(item)
        return result
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    if isinstance(value, set):
        return {_redact(item) for item in value}
    return value


def redact_secrets(func: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return func(*args, **_redact(kwargs))

    return wrapper
