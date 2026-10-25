import datetime as dt

import pandas as pd
import pytest

from aletheia.core.db.sqlite_store import SQLiteStore
from aletheia.core.signals.outcomes import brier_for, resolve_pending_outcomes


def test_brier_scoring_by_signal() -> None:
    assert brier_for("BUY", 0.8, 3.0) == pytest.approx(0.04)
    assert brier_for("BUY", 0.8, -3.0) == pytest.approx(0.64)
    assert brier_for("REDUCE", 0.7, -1.0) == pytest.approx(0.09)
    assert brier_for("HOLD", 0.5, 1.0) == pytest.approx(0.25)
    assert brier_for("HOLD", 0.5, 5.0) == pytest.approx(0.25)


async def test_resolver_fills_outcomes_and_enables_calibration_score(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "t.sqlite3")
    rec_id = store.record_confidence("run-1", "INFY", "oracle", "BUY", 0.8)
    old = (dt.datetime.now(dt.UTC) - dt.timedelta(days=40)).isoformat()
    with store.connect() as conn:
        conn.execute("UPDATE confidence_calibration SET recorded_at = ?", (old,))

    start = pd.Timestamp.now().normalize() - pd.Timedelta(days=40)
    idx = pd.date_range(start, periods=41, freq="D")
    df = pd.DataFrame({"Close": [100.0 + i for i in range(41)]}, index=idx)

    async def loader(symbol: str):
        return df

    assert await resolve_pending_outcomes(store, loader) == 1
    assert store.get_calibration_score("INFY", "oracle") == pytest.approx(0.04)
    assert store.get_pending_calibration_records(days_old=7) == []
    assert rec_id


async def test_resolver_skips_when_no_price_data(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "t.sqlite3")
    store.record_confidence("run-1", "INFY", "oracle", "BUY", 0.8)
    with store.connect() as conn:
        conn.execute(
            "UPDATE confidence_calibration SET recorded_at = ?",
            ((dt.datetime.now(dt.UTC) - dt.timedelta(days=40)).isoformat(),),
        )

    async def loader(symbol: str):
        return None

    assert await resolve_pending_outcomes(store, loader) == 0
