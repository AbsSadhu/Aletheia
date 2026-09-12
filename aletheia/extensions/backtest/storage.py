from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from aletheia.extensions.backtest.models import BacktestResult


class BacktestResultStore:
    """Minimal SQLite persistence for backtest results, keyed by run_id.

    Exists so a hypothesis's `backtest_run_id` can reference a real, later
    look-up-able result instead of an arbitrary string with nothing backing
    it — see `aletheia.extensions.hypotheses.registry.HypothesisRegistry`'s
    auto-validation, which reads a stored result's Sharpe ratio here.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS backtest_results (
                    run_id TEXT PRIMARY KEY,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def save(self, result: BacktestResult) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO backtest_results (run_id, result_json, created_at) "
                "VALUES (?, ?, ?)",
                (result.run_id, result.model_dump_json(), datetime.now(UTC).isoformat()),
            )
            conn.commit()

    def get(self, run_id: str) -> BacktestResult | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT result_json FROM backtest_results WHERE run_id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        return BacktestResult.model_validate_json(row[0])
