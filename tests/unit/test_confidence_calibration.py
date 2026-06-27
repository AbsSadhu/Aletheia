import pytest
import datetime
from aletheia.core.db.sqlite_store import SQLiteStore


@pytest.fixture
def temp_store(tmp_path):
    db_file = tmp_path / "test_calibration.sqlite3"
    # instantiate SQLiteStore which automatically initializes tables
    store = SQLiteStore(db_file)
    return store


def test_confidence_calibration_crud(temp_store):
    # 1. Record a confidence prediction
    rec_id = temp_store.record_confidence(
        run_id="run-123",
        symbol="TATASTEEL",
        agent="oracle",
        predicted_signal="BUY",
        predicted_confidence=0.85,
    )
    assert rec_id is not None
    assert len(rec_id) > 0

    # 2. Update with outcome (e.g. 7d and 30d actual returns + computed brier score)
    temp_store.update_calibration_outcome(
        record_id=rec_id,
        actual_return_7d=0.05,
        actual_return_30d=0.12,
        brier_score=0.0225,  # (0.85 - 1.0) ^ 2 = 0.0225 if actual return was positive
    )

    # 3. Retrieve rolling calibration score (Brier score)
    avg_score = temp_store.get_calibration_score(symbol="TATASTEEL", agent="oracle")
    assert avg_score == 0.0225

    # 4. Check get_pending_calibration_records
    # Insert a record that is old (e.g. 10 days ago) and lacks outcome
    with temp_store.connect() as conn:
        old_time = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=10)).isoformat()
        conn.execute(
            """
            INSERT INTO confidence_calibration
            (record_id, run_id, symbol, agent, predicted_signal, predicted_confidence, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            ("rec-old", "run-old", "RELIANCE", "oracle", "BUY", 0.7, old_time),
        )

    pending = temp_store.get_pending_calibration_records(days_old=7)
    assert len(pending) == 1
    assert pending[0]["record_id"] == "rec-old"
    assert pending[0]["symbol"] == "RELIANCE"
