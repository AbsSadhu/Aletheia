"""
Extended Risk Metrics — Sharpe, Sortino, Calmar, CVaR, Win Rate, Profit Factor, etc.

This module augments the basic VaR computation in the original metrics.py
with a full suite of quantitative risk statistics used by the Sentinel agent.
"""

from __future__ import annotations

import math
import numpy as np
import pandas as pd

from pydantic import BaseModel

from aletheia.core.models import MarketQuote, Portfolio, SentinelOutput


# ---------------------------------------------------------------------------
# Pydantic Models
# ---------------------------------------------------------------------------


class RiskMetrics(BaseModel):
    """Full risk metric suite for a portfolio or backtest result."""

    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    var_95: float
    cvar_95: float
    skewness: float
    kurtosis: float
    information_ratio: float | None = None
    comment: str = ""


class PortfolioConstraints(BaseModel):
    """User-configurable hard limits enforced by the Portfolio Manager node."""

    max_position_size_pct: float = 10.0  # % of portfolio per position
    max_sector_concentration_pct: float = 25.0  # % per sector
    max_portfolio_var: float = 0.05  # absolute VaR limit (rupees fraction)
    max_leverage: float = 1.0  # 1.0 = no leverage
    min_cash_reserve_pct: float = 5.0  # always keep this % in cash
    max_drawdown_pct: float = 20.0  # hard stop if drawdown exceeds this


# ---------------------------------------------------------------------------
# Core Computations
# ---------------------------------------------------------------------------


def compute_sharpe(returns: pd.Series, risk_free_rate: float = 0.065 / 252) -> float:
    """Annualised Sharpe ratio (risk-free default = 6.5% pa, Indian T-bill proxy)."""
    if returns.empty or returns.std() == 0:
        return 0.0
    excess = returns - risk_free_rate
    return float(excess.mean() / excess.std() * math.sqrt(252))


def compute_sortino(returns: pd.Series, risk_free_rate: float = 0.065 / 252) -> float:
    """Annualised Sortino ratio (downside std only)."""
    if returns.empty:
        return 0.0
    excess = returns - risk_free_rate
    downside = excess[excess < 0]
    downside_std = downside.std() if len(downside) > 1 else 1e-9
    if downside_std == 0:
        return float("inf") if excess.mean() > 0 else 0.0
    return float(excess.mean() / downside_std * math.sqrt(252))


def compute_max_drawdown(returns: pd.Series) -> float:
    """Maximum peak-to-trough drawdown as a positive percentage."""
    if returns.empty:
        return 0.0
    cumulative = (1 + returns).cumprod()
    rolling_max = cumulative.cummax()
    drawdowns = (cumulative - rolling_max) / rolling_max
    return float(abs(drawdowns.min()))


def compute_calmar(returns: pd.Series) -> float:
    """Calmar ratio = annualised return / max drawdown."""
    ann_return = float(returns.mean() * 252)
    max_dd = compute_max_drawdown(returns)
    if max_dd == 0:
        return float("inf") if ann_return > 0 else 0.0
    return ann_return / max_dd


def compute_var_95(returns: pd.Series) -> float:
    """Parametric VaR at 95% confidence (positive = loss)."""
    if returns.empty:
        return 0.0
    return float(-np.percentile(returns.dropna(), 5))


def compute_cvar_95(returns: pd.Series) -> float:
    """Conditional VaR (Expected Shortfall) at 95% — average of worst 5%."""
    if returns.empty:
        return 0.0
    clean = returns.dropna()
    cutoff = np.percentile(clean, 5)
    tail = clean[clean <= cutoff]
    return float(-tail.mean()) if len(tail) > 0 else 0.0


def compute_win_rate(returns: pd.Series) -> float:
    """Fraction of positive-return periods."""
    if returns.empty:
        return 0.0
    return float((returns > 0).sum() / len(returns))


def compute_profit_factor(returns: pd.Series) -> float:
    """Gross profit / gross loss (positive number; > 1 = profitable)."""
    gross_profit = returns[returns > 0].sum()
    gross_loss = abs(returns[returns < 0].sum())
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 1.0
    return float(gross_profit / gross_loss)


def compute_information_ratio(returns: pd.Series, benchmark_returns: pd.Series) -> float:
    """IR = annualised active return / tracking error."""
    active = returns - benchmark_returns
    if active.std() == 0:
        return 0.0
    return float(active.mean() / active.std() * math.sqrt(252))


def compute_full_risk_metrics(
    returns: pd.Series,
    benchmark_returns: pd.Series | None = None,
    risk_free_rate: float = 0.065 / 252,
) -> RiskMetrics:
    """
    Compute the complete risk metric suite from a series of period returns.

    Parameters
    ----------
    returns : pd.Series
        Daily/period percentage returns (e.g. [0.01, -0.005, ...])
    benchmark_returns : pd.Series, optional
        Benchmark returns for Information Ratio calculation
    risk_free_rate : float
        Per-period risk-free rate (default = 6.5% pa / 252)
    """
    sharpe = compute_sharpe(returns, risk_free_rate)
    sortino = compute_sortino(returns, risk_free_rate)
    calmar = compute_calmar(returns)
    max_dd = compute_max_drawdown(returns)
    win_rate = compute_win_rate(returns)
    profit_factor = compute_profit_factor(returns)
    var_95 = compute_var_95(returns)
    cvar_95 = compute_cvar_95(returns)
    skewness = float(returns.skew()) if not returns.empty else 0.0
    kurtosis = float(returns.kurtosis()) if not returns.empty else 0.0
    ir = (
        compute_information_ratio(returns, benchmark_returns)
        if benchmark_returns is not None
        else None
    )

    # Auto-generate comment
    flags: list[str] = []
    if sharpe < 1.0:
        flags.append(f"Sharpe {sharpe:.2f} < 1.0: low risk-adjusted return")
    if max_dd > 0.20:
        flags.append(f"Max drawdown {max_dd:.1%} > 20%: high tail risk")
    if win_rate < 0.45:
        flags.append(f"Win rate {win_rate:.1%} < 45%: more losers than winners")
    if calmar < 0.5:
        flags.append(f"Calmar {calmar:.2f} < 0.5: RISKY")

    return RiskMetrics(
        sharpe=round(sharpe, 4),
        sortino=round(sortino, 4),
        calmar=round(calmar, 4),
        max_drawdown=round(max_dd, 4),
        win_rate=round(win_rate, 4),
        profit_factor=round(profit_factor, 4),
        var_95=round(var_95, 4),
        cvar_95=round(cvar_95, 4),
        skewness=round(skewness, 4),
        kurtosis=round(kurtosis, 4),
        information_ratio=round(ir, 4) if ir is not None else None,
        comment=" | ".join(flags) if flags else "Risk metrics within acceptable ranges.",
    )


# ---------------------------------------------------------------------------
# Portfolio-level helpers (retain existing interface)
# ---------------------------------------------------------------------------


def portfolio_market_values(
    portfolio: Portfolio, quotes_by_symbol: dict[str, MarketQuote]
) -> dict[str, float]:
    values: dict[str, float] = {}
    for holding in portfolio.holdings:
        quote = quotes_by_symbol.get(holding.symbol.upper())
        if quote is None:
            continue
        values[holding.symbol.upper()] = holding.quantity * quote.close
    return values


def fallback_assess_portfolio_risk(
    portfolio: Portfolio, quotes_by_symbol: dict[str, MarketQuote]
) -> dict:
    """Pure-Python risk estimate used when aletheia_rust is unavailable."""
    values = portfolio_market_values(portfolio, quotes_by_symbol)
    total_value = sum(values.values()) or 1.0
    weights = {symbol: value / total_value for symbol, value in values.items()}
    max_weight = max(weights.values(), default=0.0)

    daily_move_estimate = 0.0
    for holding in portfolio.holdings:
        quote = quotes_by_symbol.get(holding.symbol.upper())
        if quote is None or quote.open in (None, 0):
            continue
        daily_move_estimate += abs((quote.close - quote.open) / quote.open) * weights.get(
            holding.symbol.upper(), 0.0
        )

    portfolio_var_95 = -(total_value * max(daily_move_estimate * 1.65, 0.01))
    concentration_risk = round(max_weight, 4)
    regime = "balanced"
    alerts: list[str] = []

    if max_weight > 0.4:
        regime = "concentrated"
        alerts.append("Single-position exposure is above 40% of portfolio market value.")
    if daily_move_estimate > 0.04:
        regime = "volatile"
        alerts.append("Observed mark-to-market volatility is elevated for the sampled holdings.")

    confidence = 0.55
    if not values:
        alerts.append("Risk metrics are estimated with incomplete market data.")
        confidence = 0.2

    return {
        "portfolio_var_95": round(portfolio_var_95, 2),
        "concentration_risk": concentration_risk,
        "max_single_position_pct": round(max_weight * 100, 2),
        "market_regime": regime,
        "confidence": confidence,
        "alerts": alerts,
    }


def assess_portfolio_risk(
    portfolio: Portfolio, quotes_by_symbol: dict[str, MarketQuote]
) -> SentinelOutput:
    from aletheia.core.compute.client import ComputeClient

    res = ComputeClient().assess_portfolio_risk(portfolio, quotes_by_symbol)
    return SentinelOutput(
        portfolio_var_95=res["portfolio_var_95"],
        concentration_risk=res["concentration_risk"],
        max_single_position_pct=res["max_single_position_pct"],
        market_regime=res["market_regime"],
        confidence=res["confidence"],
        alerts=res["alerts"],
    )
