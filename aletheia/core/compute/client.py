"""
ComputeClient — async Python client for the aletheia-engine Rust sidecar.

Falls back gracefully to the PyO3 module (aletheia_rust) when the sidecar
is not running, so the codebase works in both modes.

Usage:
    client = ComputeClient()
    indicators = await client.indicators(closes=prices, sma_window=20, ...)
    metrics = await client.portfolio_metrics(returns=daily_returns)
    paths = await client.monte_carlo(initial_value=100_000, daily_vol=0.01)
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from aletheia.core.config.settings import get_settings

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0


class ComputeClient:
    """
    Thin async client for aletheia-engine.

    When `settings.compute_engine_enabled` is False (default), all calls are
    routed to the PyO3 fallback layer so development works without the sidecar.
    """

    def __init__(self) -> None:
        self._settings = get_settings()
        self._base_url = self._settings.compute_engine_url.rstrip("/")

    # ------------------------------------------------------------------
    # Technical Indicators
    # ------------------------------------------------------------------

    async def indicators(
        self,
        closes: list[float],
        highs: list[float] | None = None,
        lows: list[float] | None = None,
        volumes: list[float] | None = None,
        sma_window: int = 20,
        macd_fast: int = 12,
        macd_slow: int = 26,
        macd_signal: int = 9,
        bollinger_window: int = 20,
        bollinger_std: float = 2.0,
    ) -> dict[str, Any]:
        """Full technical indicator suite from the Rust engine."""
        payload = {
            "closes": closes,
            "sma_window": sma_window,
            "macd_fast": macd_fast,
            "macd_slow": macd_slow,
            "macd_signal": macd_signal,
            "bollinger_window": bollinger_window,
            "bollinger_std": bollinger_std,
        }
        if highs:
            payload["highs"] = highs
        if lows:
            payload["lows"] = lows
        if volumes:
            payload["volumes"] = volumes

        if self._use_sidecar():
            res = await self._post("/compute/indicators", payload)
            if res:
                return res
        return self._fallback_indicators(closes, sma_window)

    # ------------------------------------------------------------------
    # Portfolio Metrics
    # ------------------------------------------------------------------

    async def portfolio_metrics(
        self,
        returns: list[float],
        equity_curve: list[float] | None = None,
        risk_free_rate: float = 0.065,
        periods_per_year: float = 252.0,
    ) -> dict[str, Any]:
        """Sharpe, Sortino, Calmar, max drawdown from the Rust engine."""
        payload: dict[str, Any] = {
            "returns": returns,
            "risk_free_rate": risk_free_rate,
            "periods_per_year": periods_per_year,
        }
        if equity_curve:
            payload["equity_curve"] = equity_curve

        if self._use_sidecar():
            res = await self._post("/compute/portfolio-metrics", payload)
            if res:
                # Handle Infinity / NaN serialized to JSON null
                for key in ["sharpe", "sortino", "calmar"]:
                    if res.get(key) is None:
                        res[key] = float("inf")
                return res
        return self._fallback_portfolio_metrics(returns, risk_free_rate, periods_per_year)

    # ------------------------------------------------------------------
    # Monte Carlo
    # ------------------------------------------------------------------

    async def monte_carlo(
        self,
        initial_value: float,
        daily_vol: float,
        daily_drift: float = 0.0,
        n_paths: int = 1000,
        n_days: int = 252,
    ) -> dict[str, Any]:
        """Monte Carlo portfolio path simulation from the Rust engine."""
        payload = {
            "initial_value": initial_value,
            "daily_vol": daily_vol,
            "daily_drift": daily_drift,
            "n_paths": n_paths,
            "n_days": n_days,
        }
        if self._use_sidecar():
            res = await self._post("/compute/monte-carlo", payload)
            if res:
                return res
        return self._fallback_monte_carlo(initial_value, daily_vol, n_paths, n_days)

    # ------------------------------------------------------------------
    # Correlation Matrix
    # ------------------------------------------------------------------

    async def correlation(
        self,
        returns_matrix: list[list[float]],
        labels: list[str] | None = None,
    ) -> dict[str, Any]:
        """Correlation matrix computation from the Rust engine."""
        payload: dict[str, Any] = {"returns_matrix": returns_matrix}
        if labels:
            payload["labels"] = labels
        if self._use_sidecar():
            res = await self._post("/compute/correlation", payload)
            if res:
                return res
        return self._fallback_correlation(returns_matrix, labels)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def is_engine_available(self) -> bool:
        """Check if the Rust sidecar is reachable."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                r = await client.get(f"{self._base_url}/health")
                return r.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _use_sidecar(self) -> bool:
        return self._settings.compute_engine_enabled

    async def _post(self, path: str, payload: dict) -> dict:
        url = f"{self._base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=_DEFAULT_TIMEOUT) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.warning("ComputeClient: sidecar call to %s failed (%s), using PyO3 fallback", path, exc)
            return {}

    # ------------------------------------------------------------------
    # PyO3 fallbacks (used when sidecar is not running)
    # ------------------------------------------------------------------

    def _fallback_indicators(self, closes: list[float], window: int) -> dict[str, Any]:
        try:
            from aletheia_rust import calculate_technical_indicators_rust  # type: ignore[import]
            return calculate_technical_indicators_rust(closes, window)
        except ImportError:
            logger.warning("aletheia_rust not compiled — returning empty indicators")
            return {"sma": [], "ema": [], "rsi": []}

    def _fallback_portfolio_metrics(
        self, returns: list[float], rfr: float, ppy: float
    ) -> dict[str, Any]:
        try:
            from aletheia_rust import (  # type: ignore[import]
                calculate_sharpe_rust,
                calculate_sortino_rust,
                calculate_calmar_rust,
                calculate_max_drawdown_rust,
            )
            equity = [1.0]
            v = 1.0
            for r in returns:
                v *= 1.0 + r
                equity.append(v)
            dd_result = calculate_max_drawdown_rust(equity)
            return {
                "sharpe": calculate_sharpe_rust(returns, rfr, ppy),
                "sortino": calculate_sortino_rust(returns, 0.0, ppy),
                "calmar": calculate_calmar_rust(returns, ppy),
                "max_drawdown": dd_result["max_drawdown"],
                "max_drawdown_pct": dd_result["max_drawdown_pct"],
                "annualized_return": (sum(returns) / max(len(returns), 1)) * ppy,
                "annualized_vol": 0.0,
            }
        except ImportError:
            return {
                "sharpe": 0.0, "sortino": 0.0, "calmar": 0.0,
                "max_drawdown": 0.0, "max_drawdown_pct": 0.0,
                "annualized_return": 0.0, "annualized_vol": 0.0,
            }

    def _fallback_monte_carlo(
        self, initial_value: float, daily_vol: float, n_paths: int, n_days: int
    ) -> dict[str, Any]:
        try:
            from aletheia_rust import monte_carlo_portfolio_paths_rust  # type: ignore[import]
            return monte_carlo_portfolio_paths_rust(initial_value, daily_vol, 0.0, n_paths, n_days)
        except ImportError:
            return {"p50": [initial_value] * (n_days + 1), "n_paths": n_paths, "n_days": n_days}

    def _fallback_correlation(
        self, returns_matrix: list[list[float]], labels: list[str] | None
    ) -> dict[str, Any]:
        try:
            from aletheia_rust import correlation_matrix_rust  # type: ignore[import]
            result = correlation_matrix_rust(returns_matrix)
            if labels:
                result["labels"] = labels
            return result
        except ImportError:
            n = len(returns_matrix)
            return {"matrix": [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)], "n_assets": n}

    # ------------------------------------------------------------------
    # Intelligence Sprint -- Regime Detection
    # ------------------------------------------------------------------

    async def regime_detection(self, returns: list, n_regimes: int = 3) -> dict:
        """Detect market regime from return series."""
        payload = {"returns": returns, "n_regimes": n_regimes}
        if self._use_sidecar():
            res = await self._post("/compute/regime", payload)
            if res:
                return res
        return self._fallback_regime(returns, n_regimes)

    def _fallback_regime(self, returns: list, n_regimes: int) -> dict:
        try:
            from aletheia_rust import regime_detection_rust  # type: ignore[import]
            return regime_detection_rust(returns, n_regimes)
        except ImportError:
            return {"current_regime": "unknown", "regime_sequence": [], "regime_labels": []}

    # ------------------------------------------------------------------
    # Intelligence Sprint -- Fama-French Factor Model
    # ------------------------------------------------------------------

    async def factor_model(self, returns: list, market_returns: list, smb: list = None, hml: list = None) -> dict:
        """Compute Fama-French 3-factor model exposures."""
        n = len(returns)
        smb = smb or [0.0] * n
        hml = hml or [0.0] * n
        payload = {"returns": returns, "market": market_returns, "smb": smb, "hml": hml}
        if self._use_sidecar():
            res = await self._post("/compute/factor-model", payload)
            if res:
                return res
        return self._fallback_factor_model(returns, market_returns, smb, hml)

    def _fallback_factor_model(self, returns: list, market_returns: list, smb: list, hml: list) -> dict:
        try:
            from aletheia_rust import fama_french_rust  # type: ignore[import]
            return fama_french_rust(returns, market_returns, smb, hml)
        except ImportError:
            n = len(returns)
            if n < 2: return {"alpha": 0.0, "beta": 1.0, "smb_loading": 0.0, "hml_loading": 0.0, "r_squared": 0.0}
            ym = sum(returns)/n; xm = sum(market_returns)/n
            cov = sum((returns[i]-ym)*(market_returns[i]-xm) for i in range(n))/n
            var = sum((market_returns[i]-xm)**2 for i in range(n))/n
            beta = cov/var if var > 0 else 1.0
            return {"alpha": ym-beta*xm, "beta": beta, "smb_loading": 0.0, "hml_loading": 0.0, "r_squared": 0.0}

    # ------------------------------------------------------------------
    # Intelligence Sprint -- Options Flow
    # ------------------------------------------------------------------

    async def options_flow(self, calls_oi: list, puts_oi: list, calls_iv: list, puts_iv: list, iv_52w_high: float = 50.0, iv_52w_low: float = 10.0) -> dict:
        """Compute PCR, IV rank, OI concentration metrics."""
        payload = {"calls_oi": calls_oi, "puts_oi": puts_oi, "calls_iv": calls_iv, "puts_iv": puts_iv, "iv_52w_high": iv_52w_high, "iv_52w_low": iv_52w_low}
        if self._use_sidecar():
            res = await self._post("/compute/options-flow", payload)
            if res:
                return res
        return self._fallback_options_flow(calls_oi, puts_oi, calls_iv, puts_iv, iv_52w_high, iv_52w_low)

    def _fallback_options_flow(self, calls_oi: list, puts_oi: list, calls_iv: list, puts_iv: list, iv_52w_high: float, iv_52w_low: float) -> dict:
        try:
            from aletheia_rust import options_flow_metrics_rust  # type: ignore[import]
            return options_flow_metrics_rust(calls_oi, puts_oi, calls_iv, puts_iv, iv_52w_high, iv_52w_low)
        except ImportError:
            tc = sum(calls_oi); tp = sum(puts_oi); pcr = tp/tc if tc > 0 else 1.0
            return {"put_call_ratio": pcr, "iv_rank": 50.0, "oi_concentration": "BEARISH_OI" if pcr>1.3 else ("BULLISH_OI" if pcr<0.7 else "NEUTRAL"), "iv_signal": "NEUTRAL"}

    # ------------------------------------------------------------------
    # Intelligence Sprint -- Brier Score (sync)
    # ------------------------------------------------------------------

    def brier_score(self, predictions: list, outcomes: list) -> float:
        """Compute Brier score for confidence calibration."""
        try:
            from aletheia_rust import brier_score_rust  # type: ignore[import]
            return brier_score_rust(predictions, outcomes)
        except ImportError:
            if not predictions: return 0.0
            return sum((p-o)**2 for p,o in zip(predictions,outcomes))/len(predictions)
