"""
Factor Registry — auto-discovery and batch computation.

Usage:
    registry = FactorRegistry()
    results = registry.compute_all(ohlcv_df)  # -> Dict[str, FactorOutput]
"""

from __future__ import annotations

import importlib
import inspect
import logging
from pathlib import Path
from typing import Any

import pandas as pd

from aletheia.factors._base import Factor, FactorOutput

logger = logging.getLogger(__name__)

_BUILTIN_MODULES = [
    "aletheia.factors.momentum",
    "aletheia.factors.mean_reversion",
    "aletheia.factors.volume",
    "aletheia.factors.technicals",
]

_CUSTOM_FACTOR_DIR = Path.home() / ".aletheia" / "factors" / "custom"


class FactorRegistry:
    """
    Discovers all Factor subclasses from built-in and custom modules.
    Provides `compute_all(ohlcv)` for batch factor computation.
    """

    def __init__(self, include_custom: bool = True) -> None:
        self._factors: dict[str, Factor] = {}
        self._load_builtins()
        if include_custom:
            self._load_custom()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _load_builtins(self) -> None:
        for module_path in _BUILTIN_MODULES:
            try:
                mod = importlib.import_module(module_path)
                self._register_from_module(mod)
            except Exception as exc:
                logger.warning("Failed to load factor module %s: %s", module_path, exc)

    def _load_custom(self) -> None:
        if not _CUSTOM_FACTOR_DIR.exists():
            return
        for py_file in _CUSTOM_FACTOR_DIR.glob("*.py"):
            spec = importlib.util.spec_from_file_location(py_file.stem, py_file)  # type: ignore[attr-defined]
            if spec is None or spec.loader is None:
                continue
            try:
                mod = importlib.util.module_from_spec(spec)  # type: ignore[attr-defined]
                spec.loader.exec_module(mod)  # type: ignore[attr-defined]
                self._register_from_module(mod)
            except Exception as exc:
                logger.warning("Failed to load custom factor %s: %s", py_file.name, exc)

    def _register_from_module(self, mod: Any) -> None:
        for _, cls in inspect.getmembers(mod, inspect.isclass):
            if issubclass(cls, Factor) and cls is not Factor and hasattr(cls, "name") and cls.name:
                try:
                    instance = cls()
                    self._factors[cls.name] = instance
                    logger.debug("Registered factor: %s (%s)", cls.name, cls.category)
                except Exception as exc:
                    logger.warning("Failed to instantiate factor %s: %s", cls.__name__, exc)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, factor: Factor) -> None:
        """Manually register a factor instance."""
        self._factors[factor.name] = factor

    def list_factors(self) -> list[dict[str, str]]:
        return [
            {
                "name": f.name,
                "category": f.category,
                "description": f.description,
                "lookback_periods": str(f.lookback_periods),
            }
            for f in self._factors.values()
        ]

    # ------------------------------------------------------------------
    # Computation
    # ------------------------------------------------------------------

    def compute_all(self, ohlcv: pd.DataFrame) -> dict[str, FactorOutput]:
        """Compute all registered factors for the given OHLCV data."""
        results: dict[str, FactorOutput] = {}
        for name, factor in self._factors.items():
            results[name] = factor.safe_compute(ohlcv)
        return results

    def compute_factor(self, name: str, ohlcv: pd.DataFrame) -> FactorOutput | None:
        """Compute a single named factor."""
        factor = self._factors.get(name)
        if factor is None:
            return None
        return factor.safe_compute(ohlcv)

    def composite_signal(self, results: dict[str, FactorOutput]) -> dict[str, Any]:
        """
        Aggregate all factor signals into a composite score.

        Returns:
            composite_score: float in [-1, 1]  (-1=strong sell, +1=strong buy)
            signal: BUY/HOLD/SELL
            confidence: float
        """
        if not results:
            return {"composite_score": 0.0, "signal": "HOLD", "confidence": 0.0}

        score_sum = 0.0
        weight_sum = 0.0
        for output in results.values():
            if output.value != output.value:  # NaN check
                continue
            direction = (
                1.0 if output.signal == "BUY" else (-1.0 if output.signal == "SELL" else 0.0)
            )
            weight = output.confidence
            score_sum += direction * weight
            weight_sum += weight

        composite = score_sum / weight_sum if weight_sum > 0 else 0.0
        avg_conf = weight_sum / len(results)

        if composite > 0.2:
            signal = "BUY"
        elif composite < -0.2:
            signal = "SELL"
        else:
            signal = "HOLD"

        return {
            "composite_score": round(composite, 4),
            "signal": signal,
            "confidence": round(avg_conf, 4),
            "factor_count": len(results),
        }


# Module-level singleton
_registry: FactorRegistry | None = None


def get_registry(include_custom: bool = True) -> FactorRegistry:
    global _registry
    if _registry is None:
        _registry = FactorRegistry(include_custom=include_custom)
    return _registry
