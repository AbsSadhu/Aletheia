import threading
import time
import pytest
from pathlib import Path
from aletheia.core.db.sqlite_store import SQLiteStore
from aletheia.core.models import AgentEvent, AgentName, RunSummary, RunStatus


def test_sqlite_concurrency(tmp_path: Path):
    db_file = tmp_path / "test_concurrency.sqlite3"
    
    # 1. Initialize SQLiteStore
    store = SQLiteStore(db_file)
    
    # Pre-populate a run so foreign keys work
    run_id = "test-run-123"
    summary = RunSummary(
        run_id=run_id,
        status=RunStatus.RUNNING,
        prompt="Test Concurrency Prompt",
    )
    store.upsert_run(summary)
    
    # 2. Define target write worker
    num_threads = 10
    writes_per_thread = 50
    errors = []
    
    def worker(worker_id: int):
        for i in range(writes_per_thread):
            try:
                event = AgentEvent(
                    run_id=run_id,
                    agent=AgentName.COLLECTOR,
                    message=f"Worker {worker_id} - Event {i}",
                    payload={"worker": worker_id, "index": i}
                )
                store.save_agent_event(event)
            except Exception as exc:
                errors.append(exc)
                
    # 3. Start threads
    threads = []
    for t_id in range(num_threads):
        thread = threading.Thread(target=worker, args=(t_id,))
        threads.append(thread)
        thread.start()
        
    # 4. Wait for completion
    for thread in threads:
        thread.join()
        
    # Clean up pool
    store.pool.close_all()
    
    # 5. Assertions
    assert len(errors) == 0, f"Encountered concurrency errors: {[str(e) for e in errors]}"
    
    # Read back events
    events = store.get_agent_events(run_id)
    assert len(events) == num_threads * writes_per_thread
    
    # Verify contents
    messages = [e.message for e in events]
    for t_id in range(num_threads):
        for i in range(writes_per_thread):
            assert f"Worker {t_id} - Event {i}" in messages
