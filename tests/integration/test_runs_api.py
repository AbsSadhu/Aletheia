from fastapi.testclient import TestClient

from aletheia.core.main import app


def test_health_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["service"] == "ALETHEIA"


def test_create_run_endpoint() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/runs",
        json={
            "prompt": "Analyze a starter portfolio",
            "portfolio": {
                "name": "Demo",
                "holdings": [
                    {
                        "symbol": "RELIANCE",
                        "quantity": 5,
                        "average_price": 2500,
                        "asset_type": "equity",
                        "exchange": "NSE",
                        "tax_profile": "equity",
                    }
                ],
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["status"] == "completed"
    assert data["collector_output"][0]["provider_used"] in {"static_seed", "yfinance"}
    assert data["oracle_output"]
    assert data["sentinel_output"] is not None
    assert data["sage_output"]
    assert data["scribe_output"] is not None


def test_portfolio_analysis_endpoint() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/portfolio-analysis",
        json={
            "name": "Starter",
            "base_currency": "INR",
            "holdings": [
                {
                    "symbol": "RELIANCE",
                    "quantity": 5,
                    "average_price": 2500,
                    "asset_type": "equity",
                    "exchange": "NSE",
                    "tax_profile": "equity",
                }
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["scribe_output"]["recommendations"]
