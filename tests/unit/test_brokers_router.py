from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from aletheia.core.api.routers import brokers
from aletheia.extensions.brokers import zerodha_session


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(brokers.router)
    app.include_router(brokers.callback_router)
    return TestClient(app)


def test_callback_rejects_unknown_state_without_touching_kite() -> None:
    r = _client().get(
        "/api/v1/brokers/zerodha/callback",
        params={"request_token": "t", "status": "success", "state": "forged"},
    )
    assert r.status_code == 400
    assert "state" in r.text


def test_callback_rejects_failed_login() -> None:
    state = zerodha_session.new_login_state()
    r = _client().get(
        "/api/v1/brokers/zerodha/callback", params={"status": "error", "state": state}
    )
    assert r.status_code == 400


def test_callback_state_is_single_use() -> None:
    state = zerodha_session.new_login_state()
    c = _client()
    c.get("/api/v1/brokers/zerodha/callback", params={"status": "error", "state": state})
    again = c.get("/api/v1/brokers/zerodha/callback", params={"status": "error", "state": state})
    assert "unknown or expired state" in again.text
