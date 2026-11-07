"""portfolio_analytics: the display carries a correlation matrix the chat renders in 3D."""

from __future__ import annotations

import numpy as np

from aletheia.core.tools import portfolio_tool


def _fake_bars(seed: int):
    def load(symbol, exchange, period, interval):  # noqa: ANN001, ANN202
        rng = np.random.default_rng(seed + ord(symbol[0]))  # a different series per symbol
        closes = 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, 120))
        return {
            "symbol": symbol,
            "bars": [
                {"time": 1_700_000_000 + i * 86400, "close": float(c)} for i, c in enumerate(closes)
            ],
        }

    return load


def test_display_contains_a_symmetric_unit_diagonal_matrix(monkeypatch) -> None:
    monkeypatch.setattr(portfolio_tool, "load_bars", _fake_bars(1))
    out = portfolio_tool._analyse(["AAA", "BBB", "CCC"], "NSE", "1y")
    matrix = out["_display"]["matrix"]
    assert matrix["labels"] == ["AAA", "BBB", "CCC"]
    v = np.array(matrix["values"])
    assert v.shape == (3, 3)
    assert np.allclose(np.diag(v), 1.0)
    assert np.allclose(v, v.T)
    assert (np.abs(v[np.triu_indices(3, 1)]) < 0.99).all()  # genuinely different series
