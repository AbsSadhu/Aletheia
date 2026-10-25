import numpy as np
import pandas as pd
import pytest

from aletheia.core.signals import quant


def _ohlcv(n: int = 300, drift: float = 0.001, end: str | None = None) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    close = 100 * np.cumprod(1 + drift + rng.normal(0, 0.01, n))
    idx = pd.bdate_range(end=end or pd.Timestamp.now().normalize(), periods=n)
    return pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": 1_000_000,
        },
        index=idx,
    )


class _StubRegistry:
    """Signals BUY whenever the last close is above the one 5 bars earlier."""

    def __init__(self) -> None:
        self.max_len_seen = 0

    def compute_all(self, df):
        self.max_len_seen = max(self.max_len_seen, len(df))
        return {"df": df}

    def composite_signal(self, results):
        df = results["df"]
        up = df["close"].iloc[-1] > df["close"].iloc[-6]
        return {"signal": "BUY" if up else "SELL", "composite_score": 0.5 if up else -0.5}


def test_no_history_gives_hold_zero_confidence() -> None:
    out = quant.compute_quant_signal(None)
    assert (out.signal, out.confidence, out.data_quality) == ("HOLD", 0.0, "insufficient_history")


def test_short_history_is_insufficient() -> None:
    out = quant.compute_quant_signal(_ohlcv(60))
    assert out.data_quality == "insufficient_history"
    assert out.confidence == 0.0


def test_stale_history_is_rejected() -> None:
    out = quant.compute_quant_signal(_ohlcv(300, end="2020-01-01"))
    assert out.data_quality == "stale"
    assert out.signal == "HOLD"


def test_real_registry_produces_valid_signal_and_prices() -> None:
    out = quant.compute_quant_signal(_ohlcv(300))
    assert out.data_quality == "ok"
    assert out.signal in {"BUY", "HOLD", "REDUCE"}
    assert 0.0 <= out.confidence <= 0.9
    assert out.atr and out.atr > 0
    if out.signal == "BUY":
        assert out.stop_loss_price < out.target_price
    if out.signal == "REDUCE":
        assert out.stop_loss_price is None and out.target_price is None


def test_walk_forward_never_sees_future_bars() -> None:
    df = quant.normalize_ohlcv(_ohlcv(300))
    reg = _StubRegistry()
    stats = quant.walk_forward_hit_rates(df, reg)
    assert reg.max_len_seen <= len(df) - quant.HORIZON
    assert stats["BUY"][1] + stats["REDUCE"][1] > 0


def test_confidence_is_shrunk_and_capped_on_few_samples() -> None:
    assert quant.calibrated_confidence(5, 5) == quant.LOW_SAMPLE_CAP  # 100% but tiny sample
    assert quant.calibrated_confidence(0, 0) == 0.5
    assert quant.calibrated_confidence(60, 100) == pytest.approx(0.5909, abs=1e-3)
    assert quant.calibrated_confidence(100, 100) == 0.9


def test_atr_matches_constant_range() -> None:
    df = quant.normalize_ohlcv(_ohlcv(50))
    df["high"] = df["close"] + 1.0
    df["low"] = df["close"] - 1.0
    df["close"] = 100.0
    df["high"], df["low"] = 101.0, 99.0
    assert quant.compute_atr(df) == pytest.approx(2.0)
