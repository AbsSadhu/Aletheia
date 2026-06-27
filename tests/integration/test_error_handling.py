from fastapi.testclient import TestClient
from aletheia.core.main import app


def test_validation_error_envelope() -> None:
    client = TestClient(app)
    # Post invalid data (missing prompt)
    response = client.post("/api/v1/runs", json={})
    assert response.status_code == 422
    data = response.json()
    assert data["code"] == "VALIDATION_ERROR"
    assert "message" in data
    assert "detail" in data


def test_404_error_envelope() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/runs/non-existent-run-id-12345")
    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "HTTP_404"
    assert data["message"] == "Run not found"
