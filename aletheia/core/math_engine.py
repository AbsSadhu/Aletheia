import logging

logger = logging.getLogger(__name__)

try:
    from aletheia_rust import (
        options_pricing_rust,
        monte_carlo_var_rust,
        calculate_technical_indicators_rust,
    )
    RUST_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Failed to import aletheia_rust: {e}. Falling back to Python implementations (if available).")
    RUST_AVAILABLE = False


class MathEngine:
    """Centralized math engine bridging Python and Rust."""

    @staticmethod
    def calculate_technicals(closes: list[float], window: int = 14) -> dict:
        if RUST_AVAILABLE:
            return calculate_technical_indicators_rust(closes, window)
        raise NotImplementedError("Rust module not available")

    @staticmethod
    def options_pricing(s: float, k: float, t: float, r: float, v: float, is_call: bool = True) -> dict:
        """
        Black-Scholes options pricing via Rust.
        s: Spot price
        k: Strike price
        t: Time to maturity (years)
        r: Risk-free rate
        v: Volatility
        """
        if RUST_AVAILABLE:
            return options_pricing_rust(s, k, t, r, v, is_call)
        raise NotImplementedError("Rust module not available")

    @staticmethod
    def monte_carlo_var(portfolio_value: float, daily_vol: float, simulations: int = 10000, confidence: float = 0.95) -> dict:
        if RUST_AVAILABLE:
            return monte_carlo_var_rust(portfolio_value, daily_vol, simulations, confidence)
        raise NotImplementedError("Rust module not available")
