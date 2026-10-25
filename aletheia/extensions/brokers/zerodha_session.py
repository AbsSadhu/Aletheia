"""Persisting and reusing the daily Kite access token (stored encrypted via ConfigManager)."""

from __future__ import annotations

import secrets
import time
from datetime import UTC, datetime, timedelta

from aletheia.config.config_manager import ConfigManager
from aletheia.extensions.brokers.zerodha import KiteAuthError, ZerodhaKiteConnector

_IST = timedelta(hours=5, minutes=30)
_STATE_TTL_SECS = 600
_pending_states: dict[str, float] = {}


def new_login_state() -> str:
    """CSRF nonce carried through Kite's redirect so only a login we started is accepted."""
    now = time.time()
    for k in [k for k, t in _pending_states.items() if now - t > _STATE_TTL_SECS]:
        del _pending_states[k]
    state = secrets.token_urlsafe(24)
    _pending_states[state] = now
    return state


def consume_login_state(state: str | None) -> bool:
    ts = _pending_states.pop(state or "", None)
    return ts is not None and time.time() - ts <= _STATE_TTL_SECS


def token_is_fresh(issued_at_iso: str | None, now: datetime | None = None) -> bool:
    """Kite tokens expire ~06:00 IST daily: fresh only if issued after the latest 06:00 IST."""
    if not issued_at_iso:
        return False
    now = now or datetime.now(UTC)
    ist_now = now + _IST
    boundary = ist_now.replace(hour=6, minute=0, second=0, microsecond=0)
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
            "zerodha_access_token": access_token,
            "zerodha_token_date": datetime.now(UTC).isoformat(),
        }
    )
    manager.save(cfg)


def session_status() -> dict[str, bool]:
    cfg = ConfigManager().load()
    return {
        "configured": bool(cfg.zerodha_api_key and cfg.zerodha_api_secret),
        "logged_in": bool(cfg.zerodha_access_token) and token_is_fresh(cfg.zerodha_token_date),
    }


async def connector_from_config() -> ZerodhaKiteConnector:
    cfg = ConfigManager().load()
    if not cfg.zerodha_api_key or not cfg.zerodha_access_token:
        raise KiteAuthError("Zerodha is not connected. Log in from Settings.")
    if not token_is_fresh(cfg.zerodha_token_date):
        raise KiteAuthError("Zerodha session expired (tokens reset ~6 AM IST). Log in again.")
    return ZerodhaKiteConnector(cfg.zerodha_api_key, cfg.zerodha_access_token)
