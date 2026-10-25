"""Angel One SmartAPI login, shared by the REST quote provider and the WebSocket stream.

One login yields both tokens: `jwtToken` (REST + the stream's Authorization header) and
`feedToken` (the stream's x-feed-token header). Sessions last about a day; we renew early.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import struct
import time
import uuid

import httpx

logger = logging.getLogger(__name__)

ROOT = "https://apiconnect.angelone.in"
LOGIN_PATH = "/rest/auth/angelbroking/user/v1/loginByPassword"
SESSION_TTL_SECS = 20 * 3600


def totp_now(secret: str, at: float | None = None, digits: int = 6, step: int = 30) -> str:
    """RFC 6238 TOTP (SHA-1), as used by Angel One's login."""
    key = base64.b32decode(secret.replace(" ", "").upper() + "=" * (-len(secret) % 8))
    counter = int((time.time() if at is None else at) // step)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 10**digits
    return str(code).zfill(digits)


def load_credentials() -> dict[str, str] | None:
    """Credentials from ConfigManager (Settings page / CLI), or None if any is missing."""
    from aletheia.config.config_manager import ConfigManager

    cfg = ConfigManager().load()
    creds = {
        "api_key": cfg.angel_one_api_key,
        "client_code": cfg.angel_one_client_code,
        "pin": cfg.angel_one_pin,
        "totp_secret": cfg.angel_one_totp_secret,
    }
    if not all(creds.values()):
        return None
    return {k: str(v) for k, v in creds.items()}


class AngelOneSession:
    def __init__(
        self,
        credentials: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._credentials = credentials
        self._client = client
        self.jwt: str | None = None
        self.feed_token: str | None = None
        self._at = 0.0
        self.last_error: str | None = None

    def credentials(self) -> dict[str, str] | None:
        return self._credentials if self._credentials is not None else load_credentials()

    def headers(self, api_key: str, jwt: str | None = None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "127.0.0.1",
            "X-MACAddress": f"{uuid.getnode():012x}",
            "X-PrivateKey": api_key,
        }
        if jwt:
            headers["Authorization"] = f"Bearer {jwt}"
        return headers

    async def http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(base_url=ROOT, timeout=10.0)
        return self._client

    def invalidate(self) -> None:
        self.jwt = None
        self.feed_token = None

    async def ensure(self) -> bool:
        """True when a live session exists (logging in if needed)."""
        if self.jwt and time.time() - self._at < SESSION_TTL_SECS:
            return True
        creds = self.credentials()
        if creds is None:
            self.last_error = "Angel One credentials are not configured."
            return False
        try:
            http = await self.http()
            resp = await http.post(
                LOGIN_PATH,
                headers=self.headers(creds["api_key"]),
                json={
                    "clientcode": creds["client_code"],
                    "password": creds["pin"],
                    "totp": totp_now(creds["totp_secret"]),
                },
            )
            body = resp.json()
        except Exception as exc:
            self.last_error = f"Login request failed: {exc}"
            logger.warning("AngelOneSession: %s", self.last_error)
            return False
        data = body.get("data") or {}
        if not body.get("status") or not data.get("jwtToken"):
            self.last_error = f"Login rejected: {body.get('message') or 'unknown reason'}"
            logger.warning("AngelOneSession: %s", self.last_error)
            return False
        self.jwt, self.feed_token, self._at = data["jwtToken"], data.get("feedToken"), time.time()
        self.last_error = None
        return True
