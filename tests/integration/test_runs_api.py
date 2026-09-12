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


def test_export_endpoint_labels_pdf_export_honestly() -> None:
    """`/export?format=pdf` must not label a response `application/pdf`
    unless it's an actual PDF — weasyprint's native libraries are commonly
    missing (as they are in this test environment), and the fallback is
    plain HTML."""
    client = TestClient(app)
    create_response = client.post(
        "/api/v1/runs",
        json={
            "prompt": "Analyze a starter portfolio for export",
            "portfolio": {
                "name": "DemoExport",
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
    run_id = create_response.json()["summary"]["run_id"]

    export_response = client.get(f"/api/v1/runs/{run_id}/export?format=pdf")
    assert export_response.status_code == 200
    content_type = export_response.headers["content-type"]
    if content_type.startswith("application/pdf"):
        assert export_response.content.startswith(b"%PDF")
    else:
        assert content_type.startswith("text/html")
        assert b"<html" in export_response.content.lower()


def test_export_endpoint_excel_format() -> None:
    client = TestClient(app)
    create_response = client.post(
        "/api/v1/runs",
        json={
            "prompt": "Analyze a starter portfolio for excel export",
            "portfolio": {
                "name": "DemoExcel",
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
    run_id = create_response.json()["summary"]["run_id"]

    export_response = client.get(f"/api/v1/runs/{run_id}/export?format=excel")
    assert export_response.status_code == 200
    assert export_response.content[:2] == b"PK"
