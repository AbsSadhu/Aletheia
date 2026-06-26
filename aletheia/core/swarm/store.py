import sqlite3
import json
import uuid
from typing import Dict, Any, List
from datetime import datetime, UTC


class SwarmStore:
    """Stores swarm execution results."""

    def __init__(self, db_path: str = "swarm_results.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS swarm_runs (
                    id TEXT PRIMARY KEY,
                    prompt TEXT,
                    team_name TEXT,
                    results TEXT,
                    timestamp TIMESTAMP
                )
            """)
            conn.commit()

    def log_run(self, prompt: str, team_name: str, results: List[Dict[str, Any]]):
        run_id = str(uuid.uuid4())[:8]
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO swarm_runs (id, prompt, team_name, results, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """,
                (run_id, prompt, team_name, json.dumps(results), datetime.now(UTC).isoformat()),
            )
            conn.commit()
        return run_id
