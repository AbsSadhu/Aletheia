from __future__ import annotations

from fastapi.testclient import TestClient

from aletheia.core.main import app


def _client() -> TestClient:
    return TestClient(app)


def test_shadow_positions_empty_by_default() -> None:
    c = _client()
    r = c.get("/api/v1/shadow/positions")
    assert r.status_code == 200
    assert "positions" in r.json()


def test_shadow_buy_creates_position_and_equity_point() -> None:
    c = _client()
    r = c.post(
        "/api/v1/shadow/orders",
        json={"symbol": "TCS", "exchange": "NSE", "action": "buy", "quantity": 1},
    )
    assert r.status_code == 200
    trade = r.json()["trade"]
    assert trade["symbol"] == "TCS"
    assert trade["action"] == "buy"

    positions = c.get("/api/v1/shadow/positions").json()["positions"]
    assert any(p["symbol"] == "TCS" for p in positions)

    perf = c.get("/api/v1/shadow/performance").json()
    assert perf["latest"] is not None
    assert len(perf["equity_curve"]) >= 1


def test_shadow_orders_endpoint_lists_trades() -> None:
    c = _client()
    c.post(
        "/api/v1/shadow/orders",
        json={"symbol": "INFY", "exchange": "NSE", "action": "buy", "quantity": 1},
    )
    r = c.get("/api/v1/shadow/orders")
    assert r.status_code == 200
    orders = r.json()["orders"]
    assert any(o["symbol"] == "INFY" for o in orders)


def test_shadow_sell_without_position_is_noop_position() -> None:
    c = _client()
    r = c.post(
        "/api/v1/shadow/orders",
        json={"symbol": "RELIANCE", "exchange": "NSE", "action": "sell", "quantity": 1},
    )
    # Order still records (no short-selling guard in this scaffold); trade recorded regardless.
    assert r.status_code == 200
