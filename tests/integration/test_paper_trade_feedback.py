"""
Integration test: Paper Trade Feedback Loop

Drives the real API (against the throwaway data directory from tests/conftest.py):
submit a paper order, list trades and positions, settle a trade, read execution state,
search memory, and ask for risk metrics. Every test places its own order, so none
depends on what another test left behind.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aletheia.core.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def place_order(client: TestClient, side: str = "BUY", quantity: int = 1) -> dict:
    response = client.post(
        "/api/v1/execution/paper-order",
        json={
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "side": side,
            "quantity": quantity,
            "order_type": "MARKET",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["trade"]


class TestPaperOrderCreation:
    def test_order_comes_back_as_a_filled_trade_that_echoes_the_request(self, client):
        trade = place_order(client, quantity=2)
        assert trade["trade_id"]
        assert (trade["symbol"], trade["side"], trade["simulated_qty"]) == ("RELIANCE", "BUY", 2)
        assert trade["status"] == "filled"
        assert trade["simulated_fill_price"] > 0

    def test_new_trade_appears_in_the_history(self, client):
        trade = place_order(client)
        response = client.get("/api/v1/execution/paper-trades?limit=50")
        assert response.status_code == 200
        assert trade["trade_id"] in [t["trade_id"] for t in response.json()["trades"]]

    def test_buying_opens_a_position(self, client):
        place_order(client)
        response = client.get("/api/v1/execution/positions")
        assert response.status_code == 200
        reliance = [p for p in response.json()["positions"] if p["symbol"] == "RELIANCE"]
        assert reliance and reliance[0]["quantity"] >= 1


class TestSettleTrade:
    def test_settling_an_unknown_trade_is_a_404(self, client):
        response = client.post(
            "/api/v1/execution/paper-trades/nonexistent-uuid-0000/settle",
            params={"actual_close": 110.0},
        )
        assert response.status_code == 404, response.text

    def test_settling_above_the_fill_books_the_profit(self, client):
        trade = place_order(client, quantity=3)
        actual_close = trade["simulated_fill_price"] * 1.05

        response = client.post(
            f"/api/v1/execution/paper-trades/{trade['trade_id']}/settle",
            params={"actual_close": actual_close},
        )

        assert response.status_code == 200, response.text
        settled = response.json()["trade"]
        expected = (actual_close - trade["simulated_fill_price"]) * 3
        assert settled["simulated_pnl"] == pytest.approx(expected, abs=0.01)
        assert settled["simulated_pnl"] > 0
        assert settled["status"] == "settled"

    def test_settling_below_the_fill_books_a_loss(self, client):
        trade = place_order(client)
        response = client.post(
            f"/api/v1/execution/paper-trades/{trade['trade_id']}/settle",
            params={"actual_close": trade["simulated_fill_price"] * 0.9},
        )
        assert response.status_code == 200, response.text
        assert response.json()["trade"]["simulated_pnl"] < 0


class TestExecutionState:
    def test_state_reports_a_known_mode(self, client):
        response = client.get("/api/v1/execution/state")
        assert response.status_code == 200
        assert response.json()["state"]["mode"] in ("simulation", "paper", "live")


class TestMemoryEndpoints:
    def test_vector_search_on_an_empty_store_returns_no_results(self, client):
        response = client.get("/api/v1/memory/vector-search?q=RELIANCE&limit=3")
        assert response.status_code == 200, response.text
        assert response.json() == {"results": []}

    def test_agent_memory_endpoint(self, client):
        response = client.get("/api/v1/memory/oracle?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert data["agent"] == "oracle"
        assert isinstance(data["observations"], list)

    def test_agent_critique_endpoint(self, client):
        response = client.get("/api/v1/memory/oracle/critique")
        assert response.status_code == 200
        data = response.json()
        assert data["agent"] == "oracle"
        assert isinstance(data["history"], list)


class TestRiskMetrics:
    def test_no_equity_curve_is_reported_plainly(self, client):
        response = client.get("/api/v1/risk/metrics")
        assert response.status_code == 200
        data = response.json()
        assert data["metrics"] is None
        assert "backtest" in data["message"].lower()
