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


def test_run_trace_endpoint() -> None:
    client = TestClient(app)
    # Create a run
    response = client.post(
        "/api/v1/runs",
        json={
            "prompt": "Analyze a starter portfolio for trace",
            "portfolio": {
                "name": "DemoTrace",
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
    run_id = response.json()["summary"]["run_id"]

    # Query trace
    trace_response = client.get(f"/api/v1/runs/{run_id}/trace")
    assert trace_response.status_code == 200
    trace_data = trace_response.json()
    assert trace_data["run_id"] == run_id
    assert isinstance(trace_data["trace"], list)
    assert len(trace_data["trace"]) > 0

    agents_seen = {event["agent"] for event in trace_data["trace"]}
    assert "collector" in agents_seen
    assert "oracle" in agents_seen
