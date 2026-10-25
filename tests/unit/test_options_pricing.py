import math

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aletheia.core.api.routers import options
from aletheia.core.compute.client import ComputeClient


def test_textbook_black_scholes_value() -> None:
    # Hull: S=42, K=40, r=10%, v=20%, T=0.5 -> call 4.76, put 0.81.
    call = ComputeClient._fallback_options_pricing(42, 40, 0.5, 0.10, 0.20, True)
    put = ComputeClient._fallback_options_pricing(42, 40, 0.5, 0.10, 0.20, False)
    assert call["price"] == pytest.approx(4.76, abs=0.01)
    assert put["price"] == pytest.approx(0.81, abs=0.01)


def test_put_call_parity_and_greek_signs() -> None:
    s, k, t, r, v = 100.0, 95.0, 0.75, 0.07, 0.3
    c = ComputeClient._fallback_options_pricing(s, k, t, r, v, True)
    p = ComputeClient._fallback_options_pricing(s, k, t, r, v, False)
    assert c["price"] - p["price"] == pytest.approx(s - k * math.exp(-r * t), abs=1e-9)
    assert 0 < c["delta"] < 1 and -1 < p["delta"] < 0
    assert c["gamma"] == pytest.approx(p["gamma"]) and c["vega"] == pytest.approx(p["vega"])
    assert c["vega"] > 0


def test_expired_option_is_intrinsic() -> None:
    out = ComputeClient._fallback_options_pricing(110, 100, 0.0, 0.07, 0.3, True)
    assert out["price"] == 10.0 and out["delta"] == 1.0


def test_endpoint_shapes_units() -> None:
    app = FastAPI()
    app.include_router(options.router)
    r = TestClient(app).get(
        "/api/v1/options/price",
        params={"spot": 100, "strike": 100, "days": 30, "vol_pct": 25, "kind": "put"},
    )
    body = r.json()
    assert r.status_code == 200 and body["kind"] == "put"
    assert body["price"] > 0 and body["delta"] < 0 and body["theta_per_day"] < 0
    bad = TestClient(app).get(
        "/api/v1/options/price", params={"spot": -1, "strike": 1, "days": 1, "vol_pct": 1}
    )
    assert bad.status_code == 422
