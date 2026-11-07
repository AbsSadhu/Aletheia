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


# --- surface endpoint ---------------------------------------------------------------------------


def _surface(client, **over):
    params = {"spot": 100, "strike": 100, "vol_pct": 25, "rate_pct": 7, "kind": "call", **over}
    return client.get("/api/v1/options/surface", params=params)


def test_surface_grid_matches_the_point_pricer() -> None:
    from fastapi.testclient import TestClient

    from aletheia.core.main import app

    client = TestClient(app)
    body = _surface(client, metric="price", max_days=60, spot_points=11, day_points=7).json()
    assert len(body["values"]) == 7 and len(body["values"][0]) == 11
    assert len(body["days"]) == 7 and len(body["spots"]) == 11
    # Every grid point equals what /options/price says for the same inputs.
    for i in (0, 3, 6):
        for j in (0, 5, 10):
            point = client.get(
                "/api/v1/options/price",
                params={
                    "spot": body["spots"][j],
                    "strike": 100,
                    "days": body["days"][i],
                    "vol_pct": 25,
                    "rate_pct": 7,
                    "kind": "call",
                },
            ).json()
            assert body["values"][i][j] == pytest.approx(point["price"], abs=2e-3)
    assert body["min"] == min(v for row in body["values"] for v in row)


def test_surface_call_price_rises_with_spot_and_units_match_the_price_endpoint() -> None:
    from fastapi.testclient import TestClient

    from aletheia.core.main import app

    client = TestClient(app)
    row = _surface(client, metric="price", day_points=5).json()["values"][2]
    assert row == sorted(row)  # a call is worth more as spot rises
    theta = _surface(client, metric="theta", spot_points=5, day_points=5).json()
    assert theta["max"] <= 0  # a long call loses value to time decay (per day)
    delta = _surface(client, metric="delta", kind="put").json()
    assert -1.0 <= delta["min"] and delta["max"] <= 0.0


def test_surface_validates_its_inputs() -> None:
    from fastapi.testclient import TestClient

    from aletheia.core.main import app

    client = TestClient(app)
    assert _surface(client, metric="rho").status_code == 422
    assert _surface(client, spot_range_pct=99).status_code == 422
    assert _surface(client, max_days=1).status_code == 422
    assert _surface(client, vol_pct=0).status_code == 422
