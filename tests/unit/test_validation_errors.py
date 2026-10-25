"""A custom validator that raises ValueError used to turn bad input into a 500
("Object of type ValueError is not JSON serializable") instead of a 422."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, field_validator

from aletheia.core.config.settings import get_settings
from aletheia.core.main import register_exception_handlers


class _Body(BaseModel):
    symbol: str

    @field_validator("symbol")
    @classmethod
    def _check(cls, v: str) -> str:
        if " " in v:
            raise ValueError("no spaces allowed")
        return v


def test_custom_validator_failure_is_a_422_with_readable_detail() -> None:
    app = FastAPI()
    register_exception_handlers(app, get_settings())

    @app.post("/x")
    async def x(body: _Body) -> dict:
        return {"ok": True}

    r = TestClient(app).post("/x", json={"symbol": "bad sym"})

    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert "no spaces allowed" in str(body["detail"])
