"""
Position Sizing — Fixed Fractional and Half-Kelly methods.
"""

from __future__ import annotations

import math


class PositionSizer:
    """
    Provides two position sizing methods:
      - fixed_fractional: risk a fixed % of portfolio per trade
      - half_kelly: risk Kelly fraction / 2 to reduce variance
    """

    @staticmethod
    def fixed_fractional(
        portfolio_value: float,
        pct: float = 2.0,
    ) -> float:
        """
        Risk a fixed percentage of portfolio per trade.

        Parameters
        ----------
        portfolio_value : float
            Total portfolio value in base currency.
        pct : float
            Percentage to risk (e.g., 2.0 = 2% of portfolio).

        Returns
        -------
        float
            Maximum position size in base currency.
        """
        if portfolio_value <= 0 or pct <= 0:
            return 0.0
        return portfolio_value * (pct / 100.0)

    @staticmethod
    def half_kelly(
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        portfolio_value: float,
        kelly_multiplier: float = 0.5,
    ) -> float:
        """
        Kelly Criterion / kelly_multiplier to reduce variance.

        Kelly formula: f* = (p * b - q) / b
        where p = win_rate, q = 1 - win_rate, b = avg_win / avg_loss

        Half-Kelly (default multiplier=0.5) dramatically reduces
        drawdown risk while retaining most of the growth benefit.

        Parameters
        ----------
        win_rate : float     0–1
        avg_win : float      average profit per winning trade (positive)
        avg_loss : float     average loss per losing trade (positive magnitude)
        portfolio_value : float
        kelly_multiplier : float   0.5 = half-Kelly (default)

        Returns
        -------
        float
            Position size in base currency. Returns 0 if edge is negative.
        """
        if avg_loss <= 0 or win_rate <= 0 or win_rate >= 1:
            return 0.0

        b = avg_win / avg_loss
        p = win_rate
        q = 1.0 - win_rate

        kelly_pct = (p * b - q) / b

        # Guard against negative Kelly (no edge)
        if kelly_pct <= 0:
            return 0.0

        # Cap Kelly at 20% even before halving (safety ceiling)
        kelly_pct = min(kelly_pct, 0.20)
        adjusted_pct = kelly_pct * kelly_multiplier

        return portfolio_value * adjusted_pct

    @staticmethod
    def compute_units(
        position_size_currency: float,
        price: float,
    ) -> float:
        """Convert a position size in currency to number of units/shares."""
        if price <= 0:
            return 0.0
        return math.floor(position_size_currency / price)

    @staticmethod
    def compute_shares(
        capital: float,
        price: float,
        pct: float = 2.0,
        portfolio_value: float | None = None,
    ) -> int:
        """
        Compute number of whole shares given a capital allocation.

        Parameters
        ----------
        capital : float
            Direct capital to allocate (if portfolio_value is None),
            or overridden by pct * portfolio_value if provided.
        price : float
            Current price per share.
        pct : float
            Percentage of portfolio_value to allocate (only used if portfolio_value set).
        portfolio_value : float | None
            If provided, allocates pct% of this instead of capital.
        """
        if price <= 0:
            return 0
        alloc = (portfolio_value * pct / 100) if portfolio_value else capital
        return int(math.floor(alloc / price))

    @staticmethod
    def validate_constraints(
        position_size_currency: float,
        portfolio_value: float,
        max_position_pct: float = 10.0,
        min_cash_reserve_pct: float = 5.0,
        current_invested_pct: float = 0.0,
    ) -> tuple[float, list[str]]:
        """
        Apply hard constraints to a proposed position size.

        Returns (adjusted_size, list_of_constraint_violations).
        """
        violations: list[str] = []

        # Max position size
        max_size = portfolio_value * (max_position_pct / 100.0)
        if position_size_currency > max_size:
            violations.append(
                f"Position size {position_size_currency:.2f} exceeds max "
                f"{max_position_pct:.1f}% ({max_size:.2f}). Capped."
            )
            position_size_currency = max_size

        # Minimum cash reserve
        available_pct = 100.0 - current_invested_pct - min_cash_reserve_pct
        max_from_cash = portfolio_value * (available_pct / 100.0)
        if position_size_currency > max_from_cash:
            violations.append(
                f"Position would breach minimum cash reserve of {min_cash_reserve_pct:.1f}%. "
                f"Capped to {max_from_cash:.2f}."
            )
            position_size_currency = max(0.0, max_from_cash)

        return position_size_currency, violations
