"""
Tests for ComputeClient and aletheia-engine Rust sidecar integration.
"""
import pytest
from aletheia.core.compute.client import ComputeClient
from aletheia.core.config.settings import get_settings


@pytest.mark.asyncio
async def test_compute_engine_availability() -> None:
    client = ComputeClient()
    # Check if the sidecar is running and available
    available = await client.is_engine_available()
    assert available is True, "aletheia-engine sidecar should be running and responsive"


@pytest.mark.asyncio
async def test_sidecar_indicators() -> None:
    client = ComputeClient()
    closes = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0, 18.0, 19.0]
    highs = [11.0] * 10
    lows = [9.0] * 10
    volumes = [1000.0] * 10

    # Ensure compute sidecar is enabled in settings (it should be since we updated .env)
    assert get_settings().compute_engine_enabled is True

    result = await client.indicators(
        closes=closes,
        highs=highs,
        lows=lows,
        volumes=volumes,
        sma_window=3,
        macd_fast=3,
        macd_slow=6,
        macd_signal=2,
        bollinger_window=5,
        bollinger_std=1.5,
    )

    assert "sma" in result
    assert "ema" in result
    assert "rsi" in result
    assert "macd_line" in result
    assert "bb_upper" in result
    assert "vwap" in result

    # Check vwap is non-empty
    assert result["vwap"] is not None
    assert len(result["vwap"]) == len(closes)


@pytest.mark.asyncio
async def test_sidecar_portfolio_metrics() -> None:
    client = ComputeClient()
    # Daily returns: 0.1% daily gain
    returns = [0.001] * 100

    result = await client.portfolio_metrics(
        returns=returns,
        risk_free_rate=0.065,
        periods_per_year=252.0,
    )

    assert "sharpe" in result
    assert "sortino" in result
    assert "calmar" in result
    assert "max_drawdown" in result
    assert "annualized_return" in result
    assert "annualized_vol" in result

    # Standard positive drift should give positive Sharpe and Sortino
    assert result["sharpe"] > 0
    assert result["sortino"] > 0
    assert result["max_drawdown"] == 0.0  # constant positive returns means no drawdown


@pytest.mark.asyncio
async def test_sidecar_monte_carlo() -> None:
    client = ComputeClient()
    result = await client.monte_carlo(
        initial_value=10000.0,
        daily_vol=0.02,
        daily_drift=0.0005,
        n_paths=100,
        n_days=10,
    )

    assert "p5" in result
    assert "p50" in result
    assert "p95" in result
    assert result["n_paths"] == 100
    assert result["n_days"] == 10
    assert len(result["p50"]) == 11  # n_days + 1


@pytest.mark.asyncio
async def test_sidecar_correlation() -> None:
    client = ComputeClient()
    # Two identical series, one opposite
    series_a = [1.0, 2.0, 3.0, 4.0, 5.0]
    series_b = [1.0, 2.0, 3.0, 4.0, 5.0]
    series_c = [5.0, 4.0, 3.0, 2.0, 1.0]

    result = await client.correlation(
        returns_matrix=[series_a, series_b, series_c],
        labels=["A", "B", "C"],
    )

    assert "matrix" in result
    assert "labels" in result
    matrix = result["matrix"]
    assert len(matrix) == 3
    # A and B are perfectly correlated (1.0)
    assert abs(matrix[0][1] - 1.0) < 1e-4
    # A and C are perfectly negatively correlated (-1.0)
    assert abs(matrix[0][2] - (-1.0)) < 1e-4
