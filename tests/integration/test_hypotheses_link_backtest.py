"""Regression coverage for POST /hypotheses/{id}/link-backtest.

Previously: a backtest_run_id that didn't match any stored result silently
"succeeded" -- the hypothesis got backtest_run_id set but was never
evaluated, with no error and no indication anything was wrong. Now the
endpoint rejects an unknown run_id with 404 before linking anything.
"""

from fastapi.testclient import TestClient

from aletheia.core.config.settings import get_settings
from aletheia.core.main import app
from aletheia.extensions.backtest.models import BacktestResult
from aletheia.extensions.backtest.storage import BacktestResultStore


def _propose_hypothesis(client: TestClient) -> str:
    response = client.post(
        "/api/v1/hypotheses",
        json={
            "title": "Test hypothesis",
            "description": "For link-backtest regression coverage.",
            "test_criteria": "Sharpe >= 1.0",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_link_backtest_unknown_run_id_returns_404_not_silent_success() -> None:
    client = TestClient(app)
    hypo_id = _propose_hypothesis(client)

    response = client.post(
        f"/api/v1/hypotheses/{hypo_id}/link-backtest",
        json={"backtest_run_id": "this-run-id-does-not-exist"},
    )

    assert response.status_code == 404


def test_link_backtest_known_run_id_links_and_auto_evaluates() -> None:
    client = TestClient(app)
    hypo_id = _propose_hypothesis(client)

    settings = get_settings()
    store = BacktestResultStore(str(settings.data_dir / "backtest_results.db"))
    store.save(
        BacktestResult(
            run_id="regression-test-run-id",
            strategy_name="sma_crossover",
            start_date="2024-01-01",
            end_date="2024-06-01",
            initial_capital=100_000.0,
            final_capital=120_000.0,
            total_return=0.20,
            metrics={"sharpe_ratio": 1.75},
            orders=[],
            equity_curve=[],
        )
    )

    response = client.post(
        f"/api/v1/hypotheses/{hypo_id}/link-backtest",
        json={"backtest_run_id": "regression-test-run-id"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["backtest_run_id"] == "regression-test-run-id"
    assert body["status"] == "validated"
