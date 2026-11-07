import numpy as np
from typing import Any, Dict, List


def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.0) -> float:
    if not returns:
        return 0.0
    returns_arr = np.array(returns)
    excess_returns = returns_arr - risk_free_rate
    std_dev = np.std(excess_returns)
    if std_dev == 0:
        return 0.0
    return float(np.mean(excess_returns) / std_dev * np.sqrt(252))


def calculate_sortino_ratio(returns: List[float], risk_free_rate: float = 0.0) -> float:
    if not returns:
        return 0.0
    returns_arr = np.array(returns)
    excess_returns = returns_arr - risk_free_rate
    downside_returns = excess_returns[excess_returns < 0]
    downside_std = np.std(downside_returns) if len(downside_returns) > 0 else 0
    if downside_std == 0:
        return 0.0
    return float(np.mean(excess_returns) / downside_std * np.sqrt(252))


def calculate_max_drawdown(equity_curve: List[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for value in equity_curve:
        if value > peak:
            peak = value
        dd = (peak - value) / peak
        if dd > max_dd:
            max_dd = dd
    return max_dd


def calculate_win_rate(trades_pnl: List[float]) -> float:
    if not trades_pnl:
        return 0.0
    wins = sum(1 for pnl in trades_pnl if pnl > 0)
    return float(wins / len(trades_pnl))


def calculate_profit_factor(trades_pnl: List[float]) -> float:
    gross_profit = sum(pnl for pnl in trades_pnl if pnl > 0)
    gross_loss = abs(sum(pnl for pnl in trades_pnl if pnl < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return float(gross_profit / gross_loss)


def split_segments(equity_curve: List[float], earlier_share: float = 0.6) -> List[Dict[str, Any]]:
    """Return/drawdown/Sharpe for the earlier and later part of an equity curve.

    A strategy that only worked in one stretch of history looks fine in aggregate; this makes the
    split visible. It is not out-of-sample testing (nothing was fitted), only a consistency check.
    Needs at least 40 points; otherwise returns nothing.
    """
    if len(equity_curve) < 40:
        return []
    cut = int(len(equity_curve) * earlier_share)
    out: List[Dict[str, Any]] = []
    for label, part in (("earlier", equity_curve[: cut + 1]), ("later", equity_curve[cut:])):
        rets = [(b - a) / a for a, b in zip(part, part[1:]) if a > 0]
        out.append(
            {
                "label": label,
                "bars": len(part) - 1,
                "total_return": (part[-1] - part[0]) / part[0] if part[0] > 0 else 0.0,
                "max_drawdown": calculate_max_drawdown(part),
                "sharpe_ratio": calculate_sharpe_ratio(rets),
            }
        )
    return out
