from __future__ import annotations

import base64
import hashlib
import logging
from typing import Optional
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


class DatabaseEncryptor:
    """Helper to encrypt and decrypt sensitive database columns at rest."""

    def __init__(self, raw_key: Optional[str]) -> None:
        self.fernet: Optional[Fernet] = None
        if raw_key:
            # Derive a secure 32-byte Fernet key from any string key using SHA-256
            hashed = hashlib.sha256(raw_key.encode("utf-8")).digest()
            base64_key = base64.urlsafe_b64encode(hashed)
            self.fernet = Fernet(base64_key)
            logger.info("DatabaseEncryptor: Initialized with encryption key.")
        else:
            logger.debug("DatabaseEncryptor: Initialized without encryption key. Data will be stored in plain text.")

    def encrypt(self, plain_text: Optional[str]) -> Optional[str]:
        if plain_text is None:
            return None
        if not self.fernet:
            return plain_text
        # Encrypt and prefix with __enc__: to identify encrypted values
        token = self.fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")
        return f"__enc__:{token}"

    def decrypt(self, cipher_text: Optional[str]) -> Optional[str]:
        if cipher_text is None:
            return None
        if not self.fernet:
            return cipher_text
        if cipher_text.startswith("__enc__:"):
            token = cipher_text[len("__enc__:"):]
            try:
                return self.fernet.decrypt(token.encode("utf-8")).decode("utf-8")
            except Exception as e:
                logger.error("DatabaseEncryptor: Decryption failed. Possible invalid key or corrupted database data.")
                raise ValueError("Failed to decrypt database value. Check your ALETHEIA_DB_ENCRYPTION_KEY.") from e
        return cipher_text
