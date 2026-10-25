"""Fyers API v3 login: build the login URL, exchange the auth code, keep the daily token.

Flow (confirmed from Fyers' official SDK `SessionModel`):
  1. Open  https://api-t1.fyers.in/api/v3/generate-authcode?client_id=<app id>&redirect_uri=...
           &response_type=code&state=<nonce>
  2. After login Fyers redirects to the registered redirect URI with  ?s=ok&auth_code=...&state=...
  3. POST  https://api-t1.fyers.in/api/v3/validate-authcode
           {"grant_type": "authorization_code", "appIdHash": sha256("<app id>:<secret>"), "code": <auth_code>}
  4. The data WebSocket authenticates with the string  "<app id>:<access token>".
Access tokens expire daily at 06:30 IST, so you log in once each trading day.
"""

from __future__ import annotations

import hashlib
import urllib.parse
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from aletheia.config.config_manager import ConfigManager

API = "https://api-t1.fyers.in/api/v3"
_IST = timedelta(hours=5, minutes=30)
EXPIRY_HOUR, EXPIRY_MINUTE = 6, 30


class FyersAuthError(RuntimeError):
    """Login rejected or no usable session; the user must log in again."""


def login_url(app_id: str, redirect_uri: str, state: str) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state,
        }
    )
    return f"{API}/generate-authcode?{query}"


async def exchange_auth_code(
    app_id: str, secret: str, auth_code: str, client: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    body = {
        "grant_type": "authorization_code",
        "appIdHash": hashlib.sha256(f"{app_id}:{secret}".encode()).hexdigest(),
        "code": auth_code,
    }
    own = client is None
    http = client or httpx.AsyncClient(timeout=15.0)
    try:
        resp = await http.post(f"{API}/validate-authcode", json=body)
        data = resp.json()
    finally:
        if own:
            await http.aclose()
    if data.get("s") != "ok" or not data.get("access_token"):
        raise FyersAuthError(data.get("message") or "Fyers rejected the auth code.")
    return dict(data)


def token_is_fresh(issued_at_iso: str | None, now: datetime | None = None) -> bool:
    """Fresh only if issued after the most recent 06:30 IST expiry."""
    if not issued_at_iso:
        return False
    now = now or datetime.now(UTC)
    ist_now = now + _IST
    boundary = ist_now.replace(hour=EXPIRY_HOUR, minute=EXPIRY_MINUTE, second=0, microsecond=0)
    if ist_now < boundary:
        boundary -= timedelta(days=1)
    issued = datetime.fromisoformat(issued_at_iso)
    if issued.tzinfo is None:
        issued = issued.replace(tzinfo=UTC)
    return issued + _IST >= boundary


def save_access_token(access_token: str) -> None:
    manager = ConfigManager()
    cfg = manager.load().model_copy(
        update={
            "fyers_access_token": access_token,
            "fyers_token_date": datetime.now(UTC).isoformat(),
        }
    )
    manager.save(cfg)


def current_ws_token() -> str | None:
    """`app_id:access_token` for the data socket, or None if not logged in / expired today."""
    cfg = ConfigManager().load()
    if not (cfg.fyers_app_id and cfg.fyers_access_token):
        return None
    if not token_is_fresh(cfg.fyers_token_date):
        return None
    return f"{cfg.fyers_app_id}:{cfg.fyers_access_token}"


def session_status() -> dict[str, bool]:
    cfg = ConfigManager().load()
    return {
        "configured": bool(cfg.fyers_app_id and cfg.fyers_secret),
        "logged_in": current_ws_token() is not None,
    }
