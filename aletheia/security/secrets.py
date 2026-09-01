from __future__ import annotations

import base64
import hashlib
import os
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

MASTER_KEY_ENV = "ALETHEIA_MASTER_KEY"
MASTER_KEY_FILE = Path.home() / ".aletheia" / ".master_key"


def _derive_fernet_key(raw_key: str) -> bytes:
    digest = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _load_master_key() -> str:
    env_key = os.getenv(MASTER_KEY_ENV)
    if env_key:
        return env_key

    if MASTER_KEY_FILE.exists():
        return MASTER_KEY_FILE.read_text(encoding="utf-8").strip()

    MASTER_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    generated = Fernet.generate_key().decode("utf-8")
    MASTER_KEY_FILE.write_text(generated, encoding="utf-8")
    return generated


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    return Fernet(_derive_fernet_key(_load_master_key()))


def encrypt_sensitive(value: str) -> str:
    token = _fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"enc:{token}"


def decrypt_sensitive(encrypted: str) -> str:
    if not encrypted.startswith("enc:"):
        return encrypted
    token = encrypted.removeprefix("enc:")
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt secret with current Aletheia master key.") from exc


def mask_for_logs(value: str | None) -> str:
    if not value:
        return "<empty>"
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-3:]}"
