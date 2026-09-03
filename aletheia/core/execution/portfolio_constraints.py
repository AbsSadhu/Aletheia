"""
Deterministic Portfolio Manager constraint checker.

This runs AFTER Sage's LLM recommendation, BEFORE any execution.
It enforces hard limits that the LLM cannot bypass.

Constraints enforced:
  - max_position_size_pct: max % of portfolio per holding
  - max_sector_concentration_pct: max % in any single sector
  - max_portfolio_var: max portfolio VaR (95%)
  - max_leverage: max gross leverage
  - min_cash_reserve_pct: minimum cash buffer

Returns a PortfolioManagerDecision, which is FINAL.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PortfolioConstraints(BaseModel):
    """User-configurable hard constraints. Enforced deterministically."""

    max_position_size_pct: float = Field(
        default=10.0, ge=0.1, le=100.0, description="Max % of portfolio in any single position"
    )
    max_sector_concentration_pct: float = Field(
        default=25.0, ge=1.0, le=100.0, description="Max % of portfolio in any single sector"
    )
    max_portfolio_var: float = Field(
        default=0.05, ge=0.001, description="Max VaR at 95% confidence level"
    )
    max_leverage: float = Field(
        default=1.0, ge=0.1, description="Max gross leverage (1.0 = no leverage)"
    )
    min_cash_reserve_pct: float = Field(
        default=5.0, ge=0.0, description="Min cash buffer as % of portfolio"
    )


class PortfolioManagerDecision(BaseModel):
    """Final execution gate — cannot be overridden by LLM agents."""

    decision: Literal["EXECUTE", "SKIP", "REDUCE"]
    approved_qty: float | None = None  # adjusted if REDUCE
    override_reason: str | None = None
    violations: list[str] = Field(default_factory=list)
    original_qty: float | None = None


class PortfolioManagerConstraintChecker:
    """
    Deterministic constraint checker that forms the final execution gate.
    LLM agents (Oracle, Sentinel, Sage, Scribe) produce *advisory* outputs;
    this class enforces hard rules that cannot be bypassed by the LLM.
    """

    def __init__(self, constraints: PortfolioConstraints | None = None) -> None:
        self.constraints = constraints or PortfolioConstraints()

    def check(
        self,
        *,
        symbol: str,
        action: str,  # "BUY" | "SELL" | "HOLD"
        quantity: float,
        price: float,
        portfolio_value: float,
        current_position_value: float = 0.0,
        sector: str = "unknown",
        sector_exposure: float = 0.0,  # current sector exposure as fraction of portfolio
        portfolio_var_95: float = 0.0,
        current_leverage: float = 1.0,
        current_cash: float = 0.0,
    ) -> PortfolioManagerDecision:
        """
        Evaluate a proposed trade against portfolio constraints.
        Returns a final decision: EXECUTE, REDUCE, or SKIP.
        """
        if action == "HOLD":
            return PortfolioManagerDecision(decision="EXECUTE", approved_qty=0)

        if action not in ("BUY", "SELL"):
            return PortfolioManagerDecision(
                decision="SKIP",
                override_reason=f"Unknown action: {action}",
            )

        violations: list[str] = []
        proposed_value = quantity * price

        # 1. Position size check
        if portfolio_value > 0:
            new_position_value = current_position_value + proposed_value
            position_pct = (new_position_value / portfolio_value) * 100
            if position_pct > self.constraints.max_position_size_pct:
                violations.append(
                    f"Position size {position_pct:.1f}% > max {self.constraints.max_position_size_pct:.1f}%"
                )

        # 2. Sector concentration check
        if portfolio_value > 0:
            new_sector_pct = (
                (sector_exposure * portfolio_value + proposed_value) / portfolio_value
            ) * 100
            if new_sector_pct > self.constraints.max_sector_concentration_pct:
                violations.append(
                    f"Sector '{sector}' concentration {new_sector_pct:.1f}% > max {self.constraints.max_sector_concentration_pct:.1f}%"
                )

        # 3. VaR check
        if portfolio_var_95 > self.constraints.max_portfolio_var:
            violations.append(
                f"Portfolio VaR {portfolio_var_95:.2%} > max {self.constraints.max_portfolio_var:.2%}"
            )

        # 4. Leverage check
        if current_leverage > self.constraints.max_leverage:
            violations.append(
                f"Leverage {current_leverage:.2f}x > max {self.constraints.max_leverage:.2f}x"
            )

        # 5. Cash reserve check
        if action == "BUY" and portfolio_value > 0:
            min_cash = portfolio_value * (self.constraints.min_cash_reserve_pct / 100)
            cash_after = current_cash - proposed_value
            if cash_after < min_cash:
                violations.append(
                    f"Cash after trade ₹{cash_after:.0f} < min reserve ₹{min_cash:.0f}"
                )

        if not violations:
            return PortfolioManagerDecision(
                decision="EXECUTE",
                approved_qty=quantity,
                original_qty=quantity,
            )

        # Attempt REDUCE: compute max allowed quantity under position size constraint
        if portfolio_value > 0:
            max_position_val = (self.constraints.max_position_size_pct / 100) * portfolio_value
            headroom = max(0.0, max_position_val - current_position_value)
            reduced_qty = headroom / price if price > 0 else 0.0

            if reduced_qty >= 1.0:  # At least 1 share worth executing
                return PortfolioManagerDecision(
                    decision="REDUCE",
                    approved_qty=int(reduced_qty),
                    original_qty=quantity,
                    override_reason="Reduced to fit within position size constraint",
                    violations=violations,
                )

        return PortfolioManagerDecision(
            decision="SKIP",
            original_qty=quantity,
            override_reason=f"Constraint violations: {'; '.join(violations)}",
            violations=violations,
        )

    def bulk_check(
        self,
        candidates: list[dict],
        portfolio_value: float,
        current_cash: float,
    ) -> list[tuple[dict, PortfolioManagerDecision]]:
        """Check multiple trade candidates; return (candidate, decision) pairs."""
        results = []
        for candidate in candidates:
            decision = self.check(
                symbol=candidate.get("symbol", "UNKNOWN"),
                action=candidate.get("action", "HOLD"),
                quantity=candidate.get("quantity", 0.0),
                price=candidate.get("price", 0.0),
                portfolio_value=portfolio_value,
                current_position_value=candidate.get("current_position_value", 0.0),
                sector=candidate.get("sector", "unknown"),
                sector_exposure=candidate.get("sector_exposure", 0.0),
                portfolio_var_95=candidate.get("portfolio_var_95", 0.0),
                current_leverage=candidate.get("current_leverage", 1.0),
                current_cash=current_cash,
            )
            results.append((candidate, decision))
            # Update cash for subsequent checks (greedy)
            if decision.decision in ("EXECUTE", "REDUCE") and candidate.get("action") == "BUY":
                used_qty = decision.approved_qty or 0
                current_cash -= used_qty * candidate.get("price", 0.0)
        return results
