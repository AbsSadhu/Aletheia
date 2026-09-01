from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from aletheia.security.audit import _redact


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, dict):
            record.args = _redact(record.args)
        return True


def configure_logging(log_dir: Path, level: str = "INFO") -> None:
    root = logging.getLogger()
    if getattr(root, "_aletheia_configured", False):
        return

    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(SecretRedactionFilter())

    file_handler = RotatingFileHandler(
        log_dir / "aletheia.log",
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(SecretRedactionFilter())

    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(console_handler)
    root.addHandler(file_handler)
    root._aletheia_configured = True  # type: ignore[attr-defined]
