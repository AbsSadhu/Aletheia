from __future__ import annotations

from aletheia.core.db.sqlite_store import SQLiteStore
from aletheia.core.db.duckdb_store import DuckDBStore


class MemoryStore:
    def __init__(self, sqlite_store: SQLiteStore, duckdb_store: DuckDBStore) -> None:
        self.sqlite_store = sqlite_store
        self.duckdb_store = duckdb_store

    def remember_run(self, summary_id: str, note: str) -> None:
        # TODO: Store note in DuckDB with embeddings for semantic search
        pass

    def search_past_runs(self, query: str) -> list[dict]:
        # Placeholder for vector similarity search over DuckDB run summaries
        return [{"run_id": "mock_id", "content": "mock match for: " + query}]
