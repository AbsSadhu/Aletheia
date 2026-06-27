import pytest
import sqlite3
from aletheia.core.db.sqlite_store import SQLiteStore


@pytest.fixture
def temp_store(tmp_path):
    db_file = tmp_path / "test_sebi.sqlite3"
    store = SQLiteStore(db_file)
    return store


def test_sebi_compliance_logging(temp_store):
    # 1. Log a compliance entry
    log_id = temp_store.log_compliance(
        run_id="run-sebi-1",
        symbol="INFY",
        action="BUY",
        confidence=0.9,
        reasoning_hash="hash123",
        disclaimer="Standard SEBI Disclaimer",
    )
    assert log_id is not None
    assert len(log_id) > 0

    # 2. Retrieve logs
    logs = temp_store.get_compliance_log()
    assert len(logs) == 1
    assert logs[0]["run_id"] == "run-sebi-1"
    assert logs[0]["symbol"] == "INFY"
    assert logs[0]["action"] == "BUY"
    assert logs[0]["disclaimer"] == "Standard SEBI Disclaimer"

    # 3. Test immutability (immutable log)
    # Attempting to update a compliance record should raise sqlite3.IntegrityError due to trigger
    with temp_store.connect() as conn:
        with pytest.raises(sqlite3.IntegrityError, match="compliance_log is immutable"):
            conn.execute("UPDATE compliance_log SET action = 'SELL' WHERE log_id = ?", (log_id,))

    # Attempting to delete a compliance record should raise sqlite3.IntegrityError due to trigger
    with temp_store.connect() as conn:
        with pytest.raises(sqlite3.IntegrityError, match="compliance_log is immutable"):
            conn.execute("DELETE FROM compliance_log WHERE log_id = ?", (log_id,))
