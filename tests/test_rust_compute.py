"""
Tests for aletheia_rust PyO3 module — 30+ function validation suite.
"""
import math
import pytest


def _import_rust():
    try:
        import aletheia_rust
        return aletheia_rust
    except ImportError:
        pytest.skip("aletheia_rust not compiled — skipping Rust tests")


# ============================================================
# Technical Indicators
# ============================================================

class TestTechnicalIndicators:
    def test_sma_basic(self):
        rust = _import_rust()
        closes = [10.0, 11.0, 12.0, 13.0, 14.0]
        result = rust.calculate_technical_indicators_rust(closes, 3)
        assert "sma" in result
        sma = result["sma"]
        assert sma[0] is None and sma[1] is None  # not enough data
        assert abs(sma[2] - 11.0) < 0.01  # (10+11+12)/3

    def test_rsi_range(self):
        rust = _import_rust()
        closes = [float(x) for x in range(1, 40)]  # trending up
        result = rust.calculate_technical_indicators_rust(closes, 14)
        rsi = [x for x in result["rsi"] if x is not None]
        assert all(0.0 <= v <= 100.0 for v in rsi)

    def test_macd(self):
        rust = _import_rust()
        closes = [100.0 + i * 0.5 + (i % 3) for i in range(50)]
        result = rust.calculate_macd_rust(closes, 12, 26, 9)
        assert "macd_line" in result
        assert "signal_line" in result
        assert "histogram" in result
        assert len(result["macd_line"]) == len(closes)

    def test_bollinger_bands(self):
        rust = _import_rust()
        closes = [100.0 + (i % 5 - 2) for i in range(30)]
        result = rust.calculate_bollinger_bands_rust(closes, 20, 2.0)
        upper = [x for x in result["upper"] if x is not None]
        lower = [x for x in result["lower"] if x is not None]
        middle = [x for x in result["middle"] if x is not None]
        assert all(u >= m >= l for u, m, l in zip(upper, middle, lower))

    def test_atr(self):
        rust = _import_rust()
        n = 30
        highs = [100.0 + i for i in range(n)]
        lows = [99.0 + i for i in range(n)]
        closes = [99.5 + i for i in range(n)]
        result = rust.calculate_atr_rust(highs, lows, closes, 14)
        assert "atr" in result
        assert "tr" in result
        tr = result["tr"]
        assert all(t >= 0.0 for t in tr)

    def test_vwap(self):
        rust = _import_rust()
        n = 10
        highs = [101.0] * n
        lows = [99.0] * n
        closes = [100.0] * n
        volumes = [1000.0] * n
        result = rust.calculate_vwap_rust(highs, lows, closes, volumes)
        vwap = result["vwap"]
        assert all(abs(v - 100.0) < 0.01 for v in vwap), "VWAP should be ~100 for flat price"

    def test_obv(self):
        rust = _import_rust()
        closes = [100.0, 101.0, 102.0, 101.0, 103.0]
        volumes = [1000.0, 2000.0, 1500.0, 500.0, 3000.0]
        result = rust.calculate_obv_rust(closes, volumes)
        obv = result["obv"]
        assert obv[0] == 0.0
        assert obv[1] == 2000.0   # price up, add volume
        assert obv[2] == 3500.0   # price up, add 1500
        assert obv[3] == 3000.0   # price down, subtract 500
        assert obv[4] == 6000.0   # price up, add 3000

    def test_stochastic(self):
        rust = _import_rust()
        n = 20
        highs = [100.0 + i for i in range(n)]
        lows = [99.0 + i for i in range(n)]
        closes = [99.5 + i for i in range(n)]
        result = rust.calculate_stochastic_rust(highs, lows, closes, 14, 3)
        k = [x for x in result["pct_k"] if x is not None]
        assert all(0.0 <= v <= 100.0 for v in k)


# ============================================================
# Portfolio Analytics
# ============================================================

class TestPortfolioAnalytics:
    def test_correlation_matrix_identity(self):
        rust = _import_rust()
        # Same series → correlation = 1
        series = [1.0, 2.0, 3.0, 4.0, 5.0]
        result = rust.correlation_matrix_rust([[s for s in series], [s for s in series]])
        m = result["matrix"]
        assert abs(m[0][0] - 1.0) < 1e-6
        assert abs(m[0][1] - 1.0) < 1e-6

    def test_correlation_matrix_anti(self):
        rust = _import_rust()
        # Opposite series → correlation = -1
        a = [1.0, 2.0, 3.0, 4.0, 5.0]
        b = [5.0, 4.0, 3.0, 2.0, 1.0]
        result = rust.correlation_matrix_rust([a, b])
        m = result["matrix"]
        assert abs(m[0][1] - (-1.0)) < 1e-6

    def test_rolling_correlation(self):
        rust = _import_rust()
        a = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        result = rust.rolling_correlation_rust(a, a, 5)
        rc = [x for x in result["rolling_corr"] if x is not None]
        assert all(abs(v - 1.0) < 1e-6 for v in rc)

    def test_monte_carlo_paths_shape(self):
        rust = _import_rust()
        result = rust.monte_carlo_portfolio_paths_rust(100_000.0, 0.01, 0.0002, 500, 252)
        assert "p5" in result and "p50" in result and "p95" in result
        assert len(result["p50"]) == 253  # n_days + 1
        # p5 <= p50 <= p95 at each day
        for i in range(253):
            assert result["p5"][i] <= result["p50"][i] <= result["p95"][i]


# ============================================================
# Backtest Metrics
# ============================================================

class TestBacktestMetrics:
    def _trending_returns(self):
        return [0.001] * 252  # ~25% annual return, daily vol near zero

    def test_sharpe_trending(self):
        rust = _import_rust()
        returns = self._trending_returns()
        sharpe = rust.calculate_sharpe_rust(returns, 0.065, 252.0)
        # With ~25% annual return and near-zero vol, Sharpe should be very high
        assert sharpe > 5.0

    def test_sortino_trending(self):
        rust = _import_rust()
        returns = self._trending_returns()
        sortino = rust.calculate_sortino_rust(returns, 0.0, 252.0)
        assert sortino > 0.0

    def test_calmar(self):
        rust = _import_rust()
        returns = self._trending_returns()
        calmar = rust.calculate_calmar_rust(returns, 252.0)
        # Perfect trend → no drawdown → infinity (or very large)
        assert calmar == math.inf or calmar > 100.0

    def test_max_drawdown_flat(self):
        rust = _import_rust()
        # Flat equity curve → no drawdown
        equity = [100_000.0] * 100
        result = rust.calculate_max_drawdown_rust(equity)
        assert result["max_drawdown"] == 0.0
        assert result["max_drawdown_pct"] == 0.0

    def test_max_drawdown_peak_to_trough(self):
        rust = _import_rust()
        equity = [100.0, 110.0, 120.0, 90.0, 80.0, 100.0, 110.0]
        result = rust.calculate_max_drawdown_rust(equity)
        # Peak=120, trough=80, drawdown = (120-80)/120 ≈ 0.333
        assert abs(result["max_drawdown"] - (120.0 - 80.0) / 120.0) < 0.01
        assert "underwater" in result


# ============================================================
# BM25 and Memory
# ============================================================

class TestBM25:
    def test_basic_relevance(self):
        rust = _import_rust()
        query = "RELIANCE equity signals"
        docs = [
            "RELIANCE buy signal strong equity",
            "NIFTY50 index market cap",
            "RELIANCE equity returns NSE",
        ]
        scores = rust.bm25_score_rust(query, docs, 1.5, 0.75)
        assert len(scores) == 3
        # Doc 0 and 2 both mention "RELIANCE" and "equity" — both should score > doc 1
        assert scores[0] > scores[1]
        assert scores[2] > scores[1]

    def test_empty_query(self):
        rust = _import_rust()
        scores = rust.bm25_score_rust("", ["hello world"], 1.5, 0.75)
        assert scores == [0.0]

    def test_empty_docs(self):
        rust = _import_rust()
        scores = rust.bm25_score_rust("hello", [], 1.5, 0.75)
        assert scores == []


# ============================================================
# RateLimiter
# ============================================================

class TestRateLimiter:
    def test_basic_consume(self):
        rust = _import_rust()
        limiter = rust.RateLimiter(10.0, 10.0)  # 10 tokens/sec, capacity 10
        assert limiter.consume(5.0) is True
        assert limiter.consume(4.0) is True
        assert limiter.consume(2.0) is False  # only 1 token left

    def test_available(self):
        rust = _import_rust()
        limiter = rust.RateLimiter(10.0, 10.0)
        initial = limiter.available()
        assert 9.9 <= initial <= 10.1  # should be ~10 at start


# ============================================================
# Options Pricing
# ============================================================

class TestOptionsPricing:
    def test_call_at_the_money(self):
        rust = _import_rust()
        # ATM call: S=K=100, vol=20%, T=1yr, r=5%
        result = rust.options_pricing_rust(100.0, 100.0, 1.0, 0.05, 0.20, True)
        # Black-Scholes ATM call is ~10.45 at these parameters
        assert 8.0 < result["price"] < 14.0
        assert 0.4 < result["delta"] < 0.7

    def test_put_call_parity(self):
        rust = _import_rust()
        S, K, T, r, vol = 100.0, 100.0, 1.0, 0.05, 0.20
        call = rust.options_pricing_rust(S, K, T, r, vol, True)
        put = rust.options_pricing_rust(S, K, T, r, vol, False)
        # Put-call parity: C - P = S - K*e^(-rT)
        lhs = call["price"] - put["price"]
        rhs = S - K * math.exp(-r * T)
        assert abs(lhs - rhs) < 0.01
