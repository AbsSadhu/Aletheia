from fastapi.testclient import TestClient
from aletheia.core.main import app

def test_agent_golden_pipeline():
    client = TestClient(app)
    
    # 1. Trigger the run
    response = client.post(
        "/api/v1/runs",
        json={
            "prompt": "Golden Regression Test Portfolio",
            "portfolio": {
                "name": "GoldenPortfolio",
                "holdings": [
                    {
                        "symbol": "RELIANCE",
                        "quantity": 10,
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
    
    # Verify RunSummary structure
    assert "summary" in data
    summary = data["summary"]
    assert "run_id" in summary
    assert summary["status"] == "completed"
    
    # 2. Verify Collector Output schema
    assert "collector_output" in data
    assert isinstance(data["collector_output"], list)
    assert len(data["collector_output"]) > 0
    collector = data["collector_output"][0]
    assert "symbol" in collector
    assert "provider_used" in collector
    assert "quotes" in collector
    assert isinstance(collector["quotes"], list)
    
    # 3. Verify Oracle Output schema
    assert "oracle_output" in data
    assert isinstance(data["oracle_output"], list)
    assert len(data["oracle_output"]) > 0
    oracle = data["oracle_output"][0]
    assert "symbol" in oracle
    assert oracle["signal"] in ["BUY", "HOLD", "REDUCE"]
    assert isinstance(oracle["confidence"], float)
    assert 0.0 <= oracle["confidence"] <= 1.0
    assert "rationale" in oracle
    assert isinstance(oracle["rationale"], list)
    
    # 4. Verify Sentinel Output schema
    assert "sentinel_output" in data
    sentinel = data["sentinel_output"]
    assert sentinel is not None
    assert "portfolio_var_95" in sentinel
    assert "concentration_risk" in sentinel
    assert "max_single_position_pct" in sentinel
    assert "market_regime" in sentinel
    
    # 5. Verify Sage Output schema
    assert "sage_output" in data
    assert isinstance(data["sage_output"], list)
    assert len(data["sage_output"]) > 0
    sage = data["sage_output"][0]
    assert "symbol" in sage
    assert "scenario" in sage
    assert "tax_summary" in sage["scenario"]
    assert "tax_drag_pct" in sage["scenario"]["tax_summary"]
    
    # 6. Verify Scribe Output schema
    assert "scribe_output" in data
    scribe = data["scribe_output"]
    assert scribe is not None
    assert "executive_summary" in scribe
    assert "overall_confidence" in scribe
    assert "agreement_level" in scribe
    assert "recommendations" in scribe
    assert isinstance(scribe["recommendations"], list)
    
    # 7. Verify Trace & Spans are captured and retrievable
    run_id = summary["run_id"]
    trace_response = client.get(f"/api/v1/runs/{run_id}/trace")
    assert trace_response.status_code == 200
    trace_data = trace_response.json()
    assert trace_data["run_id"] == run_id
    
    # Events traces list
    assert "trace" in trace_data
    assert isinstance(trace_data["trace"], list)
    assert len(trace_data["trace"]) > 0
    
    # Node execution spans list
    assert "spans" in trace_data
    assert isinstance(trace_data["spans"], list)
    assert len(trace_data["spans"]) > 0
    
    # Verify structure of spans
    for span in trace_data["spans"]:
        assert "node" in span
        assert span["node"] in ["collect", "oracle", "sentinel", "sage", "scribe", "debate", "portfolio_manager", "sentiment", "fundamental", "options_flow", "critic"]
        assert "start_time" in span
        assert "end_time" in span
        assert "duration" in span
        assert isinstance(span["duration"], float)
        assert "llm_calls" in span
        assert isinstance(span["llm_calls"], list)
