"""Broker connection (OAuth) endpoints: Zerodha and Fyers.

GET /brokers/zerodha/status
GET /brokers/zerodha/login-url
GET /brokers/fyers/status
GET /brokers/fyers/login-url

The OAuth redirect targets, GET /brokers/zerodha/callback and /brokers/fyers/callback, live on `callback_router` below,
which main.py mounts WITHOUT the X-API-Key dependency: it is a browser redirect from Kite and
can't send headers. It is protected instead by a single-use `state` nonce issued by login-url.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from aletheia.config.config_manager import ConfigManager
from aletheia.extensions.brokers import fyers_session
from aletheia.extensions.brokers import zerodha_session as session
from aletheia.extensions.brokers.zerodha import KiteAuthError, exchange_request_token, login_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")
callback_router = APIRouter(prefix="/api/v1")


@router.get("/brokers/zerodha/status")
async def zerodha_status() -> dict:
    return session.session_status()


@router.get("/brokers/zerodha/login-url")
async def zerodha_login_url() -> dict:
    cfg = ConfigManager().load()
    if not cfg.zerodha_api_key or not cfg.zerodha_api_secret:
        raise HTTPException(status_code=400, detail="Set Zerodha API key and secret in Settings.")
    return {"url": login_url(cfg.zerodha_api_key, state=session.new_login_state())}


def _page(message: str, ok: bool) -> HTMLResponse:
    colour = "#2e7d32" if ok else "#c62828"
    return HTMLResponse(
        f"<html><body style='font-family:sans-serif;padding:2rem'>"
        f"<h3 style='color:{colour}'>{message}</h3>You can close this tab.</body></html>",
        status_code=200 if ok else 400,
    )


@callback_router.get("/brokers/zerodha/callback", response_class=HTMLResponse)
async def zerodha_callback(
    request_token: str | None = None, status: str | None = None, state: str | None = None
) -> HTMLResponse:
    if not session.consume_login_state(state):
        return _page("Login rejected: unknown or expired state. Start again from Aletheia.", False)
    if status != "success" or not request_token:
        return _page("Zerodha login was not completed.", False)
    cfg = ConfigManager().load()
    if not cfg.zerodha_api_key or not cfg.zerodha_api_secret:
        return _page("Zerodha API key/secret are not configured.", False)
    try:
        data = await exchange_request_token(
            cfg.zerodha_api_key, cfg.zerodha_api_secret, request_token
        )
    except KiteAuthError as exc:
        logger.warning("Zerodha token exchange failed: %s", exc)
        return _page(f"Zerodha rejected the login: {exc}", False)
    session.save_access_token(data["access_token"])
    return _page("Zerodha connected.", True)


# -- Fyers ---------------------------------------------------------------------


def _fyers_redirect_uri() -> str:
    from aletheia.core.config.settings import get_settings

    st = get_settings()
    return f"http://{st.host}:{st.port}/api/v1/brokers/fyers/callback"


@router.get("/brokers/fyers/status")
async def fyers_status() -> dict:
    return {**fyers_session.session_status(), "redirect_uri": _fyers_redirect_uri()}


@router.get("/brokers/fyers/login-url")
async def fyers_login_url() -> dict:
    cfg = ConfigManager().load()
    if not cfg.fyers_app_id or not cfg.fyers_secret:
        raise HTTPException(status_code=400, detail="Set the Fyers app ID and secret in Settings.")
    url = fyers_session.login_url(
        cfg.fyers_app_id, _fyers_redirect_uri(), session.new_login_state()
    )
    return {"url": url, "redirect_uri": _fyers_redirect_uri()}


@callback_router.get("/brokers/fyers/callback", response_class=HTMLResponse)
async def fyers_callback(
    auth_code: str | None = None, s: str | None = None, state: str | None = None
) -> HTMLResponse:
    if not session.consume_login_state(state):
        return _page("Login rejected: unknown or expired state. Start again from Aletheia.", False)
    if s != "ok" or not auth_code:
        return _page("Fyers login was not completed.", False)
    cfg = ConfigManager().load()
    if not cfg.fyers_app_id or not cfg.fyers_secret:
        return _page("Fyers app ID/secret are not configured.", False)
    try:
        data = await fyers_session.exchange_auth_code(cfg.fyers_app_id, cfg.fyers_secret, auth_code)
    except fyers_session.FyersAuthError as exc:
        logger.warning("Fyers token exchange failed: %s", exc)
        return _page(f"Fyers rejected the login: {exc}", False)
    fyers_session.save_access_token(data["access_token"])
    # Start the live stream now if it was waiting for a login.
    try:
        from aletheia.core.api.dependencies import get_feed_manager

        await get_feed_manager().start()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not start the Fyers stream after login: %s", exc)
    return _page("Fyers connected.", True)
