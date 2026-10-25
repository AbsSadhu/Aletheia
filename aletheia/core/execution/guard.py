"""Risk limits for paper and shadow trading.

The analysis pipeline already enforces position/sector/VaR caps inside a run, but orders placed
*outside* a run (paper orders, the shadow trader) used to bypass them: the shadow trader bought
one share regardless of account size, and a SELL with no position invented cash. This guard puts
the same `PortfolioManagerConstraintChecker` in front of those paths, so paper results reflect
what the account could really have done.

Sector concentration is not enforced here: paper/shadow positions carry no sector, and treating
every symbol as one "unknown" sector would wrongly cap the whole book.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from aletheia.core.execution.portfolio_constraints import (
    PortfolioConstraints,
    PortfolioManagerConstraintChecker,
)


class RiskLimitExceeded(Exception):
    def __init__(self, message: str, violations: list[str] | None = None) -> None:
        super().__init__(message)
        self.violations = violations or []


@dataclass
class GuardDecision:
    approved_qty: int
    reduced: bool = False
    notes: list[str] = field(default_factory=list)


class ExecutionGuard:
    def __init__(self, settings: Any = None) -> None:
        if settings is None:
            from aletheia.core.config.settings import get_settings

            settings = get_settings()
        self.risk_per_trade_pct = settings.risk_per_trade_pct
        self.fallback_position_pct = settings.fallback_position_pct
        self.checker = PortfolioManagerConstraintChecker(
            PortfolioConstraints(
                max_position_size_pct=settings.pm_max_position_size_pct,
                max_sector_concentration_pct=100.0,  # see module docstring
                min_cash_reserve_pct=settings.pm_min_cash_reserve_pct,
            )
        )

    def size_buy(self, price: float, equity: float, stop_price: float | None = None) -> int:
        """Whole shares such that hitting the stop loses `risk_per_trade_pct` of equity.

        Without a usable stop (no ATR, or stop at/above price) fall back to a fixed slice of
        equity. The position-size cap is applied afterwards by `check_buy`.
        """
        if price <= 0 or equity <= 0:
            return 0
        if stop_price is not None and 0 < stop_price < price:
            qty = (equity * self.risk_per_trade_pct / 100.0) / (price - stop_price)
        else:
            qty = (equity * self.fallback_position_pct / 100.0) / price
        return max(int(math.floor(qty)), 0)

    def check_buy(
        self,
        symbol: str,
        quantity: float,
        price: float,
        equity: float,
        cash: float,
        current_position_value: float = 0.0,
    ) -> GuardDecision:
        """Approve, shrink, or reject (raise) a BUY. Callers decide whether a shrink is acceptable."""
        decision = self.checker.check(
            symbol=symbol,
            action="BUY",
            quantity=quantity,
            price=price,
            portfolio_value=equity,
            current_position_value=current_position_value,
            current_cash=cash,
        )
        if decision.decision not in ("EXECUTE", "REDUCE") or not decision.approved_qty:
            raise RiskLimitExceeded(
                decision.override_reason or "Order violates portfolio limits.", decision.violations
            )
        approved = int(decision.approved_qty)
        # The checker only shrinks for position size; never let a shrunk order breach the cash floor.
        reserve = equity * self.checker.constraints.min_cash_reserve_pct / 100.0
        affordable = int(math.floor((cash - reserve) / price)) if price > 0 else 0
        if affordable < 1:
            raise RiskLimitExceeded(
                f"Not enough cash for {symbol} after the {reserve:,.0f} reserve.",
                decision.violations,
            )
        approved = min(approved, affordable)
        reduced = approved < int(quantity)
        return GuardDecision(
            approved_qty=approved,
            reduced=reduced,
            notes=decision.violations if reduced else [],
        )

    @staticmethod
    def check_sell(symbol: str, quantity: float, held_quantity: float) -> None:
        if held_quantity <= 0:
            raise RiskLimitExceeded(f"No open position in {symbol} to sell.")
        if quantity > held_quantity:
            raise RiskLimitExceeded(
                f"Cannot sell {quantity:g} {symbol}; only {held_quantity:g} held."
            )
