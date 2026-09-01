"""
aletheia.factors — Alpha Factor Library

Auto-discovers and computes technical alpha factors for the Oracle agent.

Quick usage:
    from aletheia.factors import get_registry
    registry = get_registry()
    results = registry.compute_all(ohlcv_df)
    composite = registry.composite_signal(results)
"""

from aletheia.factors._base import Factor, FactorOutput
from aletheia.factors.registry import FactorRegistry, get_registry

# ICScorer depends on scipy — lazy-import to avoid breaking environments without scipy
def __getattr__(name: str):
    if name == "ICScorer":
        from aletheia.factors.ic_scorer import ICScorer  # type: ignore
        return ICScorer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = ["Factor", "FactorOutput", "FactorRegistry", "get_registry", "ICScorer"]
