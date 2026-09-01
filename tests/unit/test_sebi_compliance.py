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


def test_hash_chain_links_entries_and_verifies_clean(temp_store):
    ids = [
        temp_store.log_compliance(
            run_id=f"run-{i}",
            symbol="RELIANCE",
            action="HOLD",
            confidence=0.7,
            reasoning_hash="h",
            disclaimer="d",
        )
        for i in range(3)
    ]
    log = temp_store.get_compliance_log(limit=10)
    by_id = {row["log_id"]: row for row in log}

    # First entry chains from the genesis hash.
    assert by_id[ids[0]]["prev_hash"] == "0" * 64
    # Each later entry's prev_hash is the previous entry's entry_hash.
    assert by_id[ids[1]]["prev_hash"] == by_id[ids[0]]["entry_hash"]
    assert by_id[ids[2]]["prev_hash"] == by_id[ids[1]]["entry_hash"]
    assert all(row["entry_hash"] for row in log)

    result = temp_store.verify_compliance_chain()
    assert result == {
        "total_entries": 3,
        "unverifiable_entries": [],
        "broken_entries": [],
        "chain_intact": True,
    }


def test_hash_chain_detects_tampering_that_bypasses_triggers(temp_store):
    log_id = temp_store.log_compliance(
        run_id="run-tamper",
        symbol="TCS",
        action="BUY",
        confidence=0.8,
        reasoning_hash="h",
        disclaimer="d",
    )
    temp_store.log_compliance(
        run_id="run-after",
        symbol="TCS",
        action="HOLD",
        confidence=0.5,
        reasoning_hash="h2",
        disclaimer="d2",
    )

    # Simulate a raw file edit that bypasses the app (and its UPDATE trigger,
    # which only blocks writes made through this SQLite connection's normal
    # SQL path — dropping it models an editor with direct file access).
    with temp_store.connect() as conn:
        conn.execute("DROP TRIGGER compliance_no_update")
        conn.execute("UPDATE compliance_log SET action = 'SELL' WHERE log_id = ?", (log_id,))

    result = temp_store.verify_compliance_chain()
    assert result["chain_intact"] is False
    assert log_id in result["broken_entries"]


def test_hash_chain_migration_from_pre_chain_schema(tmp_path):
    db_file = tmp_path / "legacy.sqlite3"
    raw = sqlite3.connect(db_file)
    raw.execute(
        """
        CREATE TABLE compliance_log (
            log_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, symbol TEXT NOT NULL,
            action TEXT NOT NULL, confidence REAL NOT NULL, reasoning_hash TEXT NOT NULL,
            disclaimer TEXT NOT NULL, logged_at TEXT NOT NULL
        )
        """
    )
    raw.execute(
        "INSERT INTO compliance_log VALUES ('old-1','run-x','INFY','BUY',0.7,'h','d','2026-01-01T00:00:00')"
    )
    raw.commit()
    raw.close()

    store = SQLiteStore(db_file)  # must migrate: add prev_hash/entry_hash columns
    new_id = store.log_compliance(
        run_id="run-y",
        symbol="INFY",
        action="SELL",
        confidence=0.6,
        reasoning_hash="h2",
        disclaimer="d2",
    )

    result = store.verify_compliance_chain()
    assert result["unverifiable_entries"] == ["old-1"]
    assert result["broken_entries"] == []
    assert result["chain_intact"] is True
    assert new_id not in result["unverifiable_entries"]
