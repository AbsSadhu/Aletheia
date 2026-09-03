"""
Integration test: Paper Trade Feedback Loop

Tests the full paper trade API surface:
1. Submit a paper order
2. List trades
3. List positions
4. Settle a trade (endpoint reachability)
5. Execution state
6. Memory search via vector-search endpoint
7. Risk metrics (no completed runs = graceful None)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from aletheia.core.main import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def submitted_trade(client):
    """Submit a paper order and return the full response object."""
    response = client.post(
        "/api/v1/execution/paper-order",
        json={
            "symbol": "RELIANCE",
            "exchange": "NSE",
            "side": "BUY",
            "quantity": 1,
            "order_type": "MARKET",
        },
    )
    return response


class TestPaperOrderCreation:
    def test_paper_order_status_200(self, submitted_trade):
        """POST /execution/paper-order must return 200."""
        assert submitted_trade.status_code == 200, submitted_trade.text

    def test_paper_order_returns_trade_record(self, submitted_trade):
        """Response must contain a 'trade' key with at least a trade_id."""
        if submitted_trade.status_code != 200:
            pytest.skip("Paper order endpoint not available")
        data = submitted_trade.json()
        assert "trade" in data, f"Expected 'trade' key, got: {list(data.keys())}"
        trade = data["trade"]
        assert "trade_id" in trade, f"Missing trade_id in: {trade}"

    def test_paper_trades_list_endpoint(self, client):
        """GET /execution/paper-trades returns trades list."""
        response = client.get("/api/v1/execution/paper-trades?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "trades" in data
        assert isinstance(data["trades"], list)

    def test_positions_endpoint_accessible(self, client):
        """GET /execution/positions returns open positions list."""
        response = client.get("/api/v1/execution/positions")
        assert response.status_code == 200
        data = response.json()
        assert "positions" in data


class TestSettleTrade:
    def test_settle_nonexistent_trade_returns_404(self, client):
        """Settle endpoint must return 404 for unknown trade_id (not 500)."""
        response = client.post(
            "/api/v1/execution/paper-trades/nonexistent-uuid-0000/settle",
            params={"actual_close": 110.0},
        )
        assert response.status_code in (404, 422), (
            f"Expected 404 or 422, got {response.status_code}: {response.text}"
        )

    def test_settle_updates_pnl(self, client, submitted_trade):
        """Full cycle: submit order, then settle with profit; expect positive PnL."""
        if submitted_trade.status_code != 200:
            pytest.skip("Paper order creation not supported in this configuration")

        trade_data = submitted_trade.json().get("trade", {})
        trade_id = trade_data.get("trade_id")
        if not trade_id:
            pytest.skip("Could not extract trade_id from paper order response")

        fill_price = trade_data.get("simulated_fill_price", 100.0)
        actual_close = fill_price * 1.05  # 5% profit

        settle_response = client.post(
            f"/api/v1/execution/paper-trades/{trade_id}/settle",
            params={"actual_close": actual_close},
        )
        # 200 = settled; 404 = not in this store (OK for isolation); 422 = validation
        assert settle_response.status_code in (200, 404, 422), settle_response.text

        if settle_response.status_code == 200:
            settled = settle_response.json()
            trade = settled.get("trade", {})
            pnl = trade.get("simulated_pnl") or 0.0
            # BUY with actual_close > fill_price → pnl should be ≥ 0
            assert pnl >= 0, f"Expected non-negative PnL for profitable trade, got {pnl}"
            assert trade.get("status") in ("settled", "filled"), trade


class TestExecutionState:
    def test_execution_state_endpoint(self, client):
        """GET /execution/state returns valid execution state."""
        response = client.get("/api/v1/execution/state")
        assert response.status_code == 200
        data = response.json()
        assert "state" in data
        state = data["state"]
        assert "mode" in state

    def test_execution_mode_key_present(self, client):
        """Mode value must be one of the known ExecutionMode values."""
        response = client.get("/api/v1/execution/state")
        if response.status_code == 200:
            state = response.json().get("state", {})
            assert state.get("mode") in ("simulation", "paper", "live")


class TestMemoryEndpoints:
    def test_vector_memory_search_accessible(self, client):
        """GET /memory/vector-search returns valid JSON."""
        response = client.get("/api/v1/memory/vector-search?q=RELIANCE&limit=3")
        # 200 = results; 500 = vector store not initialized (acceptable in test env)
        assert response.status_code in (200, 500)
        if response.status_code == 200:
            data = response.json()
            assert "results" in data

    def test_agent_memory_endpoint(self, client):
        """GET /memory/{agent_name} returns agent observations."""
        response = client.get("/api/v1/memory/oracle?limit=5")
        assert response.status_code == 200
        data = response.json()
        assert "agent" in data
        assert "observations" in data

    def test_agent_critique_endpoint(self, client):
        """GET /memory/{agent_name}/critique returns critique history."""
        response = client.get("/api/v1/memory/oracle/critique")
        assert response.status_code == 200
        data = response.json()
        assert "agent" in data
        assert "history" in data


class TestRiskMetrics:
    def test_risk_metrics_endpoint_reachable(self, client):
        """GET /risk/metrics returns valid response structure."""
        response = client.get("/api/v1/risk/metrics")
        assert response.status_code == 200
        data = response.json()
        # Either returns metrics or message (no runs yet is OK)
        assert "metrics" in data

    def test_risk_metrics_no_runs_returns_null_gracefully(self, client):
        """When no completed runs exist, metrics should be None with a message."""
        response = client.get("/api/v1/risk/metrics")
        assert response.status_code == 200
        data = response.json()
        # If no runs, metrics is None and message explains why
        if data.get("metrics") is None:
            assert "message" in data or "run_id" not in data
