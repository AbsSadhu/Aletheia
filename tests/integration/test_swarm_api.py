"""Regression coverage for the swarm endpoints: both preset teams and
SwarmRuntime existed before aletheia/core/api/routers/swarm.py was added,
but nothing anywhere called either — no CLI command, no API route, no test.
These assert the wiring works end-to-end, not that the LLM produces good
output (no Ollama is assumed to be running in CI; ReActLoop surfaces that as
an "error" SSE event per worker rather than crashing, and that's what's
being verified here).
"""

from fastapi.testclient import TestClient

from aletheia.core.main import app


def test_list_swarm_presets() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/swarm/presets")
    assert response.status_code == 200
    presets = response.json()["presets"]
    assert "investment_team" in presets
    assert "due_diligence_team" in presets


def test_run_swarm_unknown_preset_returns_400() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/swarm/run", json={"preset": "does_not_exist", "prompt": "Analyze RELIANCE"}
    )
    assert response.status_code == 400


def test_run_swarm_streams_one_event_per_worker() -> None:
    client = TestClient(app)
    with client.stream(
        "POST",
        "/api/v1/swarm/run",
        json={"preset": "due_diligence_team", "prompt": "Analyze RELIANCE"},
    ) as response:
        assert response.status_code == 200
        body = "".join(response.iter_text())

    # due_diligence_team has 2 workers; each worker's name should appear at
    # least once in the stream (as the "worker" field on its events).
    assert "News Analyst" in body
    assert "SEC Analyst" in body
