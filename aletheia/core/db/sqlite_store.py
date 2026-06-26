from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from aletheia.core.models import Portfolio, RunResult, RunStatus, RunSummary


class SQLiteStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    error_message TEXT,
                    result_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS portfolios (
                    name TEXT PRIMARY KEY,
                    base_currency TEXT NOT NULL,
                    holdings_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def upsert_run(self, summary: RunSummary, result: RunResult | None = None) -> None:
        payload = result.model_dump_json() if result else None
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (run_id, status, prompt, created_at, updated_at, error_message, result_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status = excluded.status,
                    prompt = excluded.prompt,
                    updated_at = excluded.updated_at,
                    error_message = excluded.error_message,
                    result_json = excluded.result_json
                """,
                (
                    summary.run_id,
                    summary.status.value,
                    summary.prompt,
                    summary.created_at.isoformat(),
                    summary.updated_at.isoformat(),
                    summary.error_message,
                    payload,
                ),
            )

    def list_runs(self, limit: int = 20) -> list[RunSummary]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT run_id, status, prompt, created_at, updated_at, error_message
                FROM runs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            RunSummary(
                run_id=row["run_id"],
                status=RunStatus(row["status"]),
                prompt=row["prompt"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                error_message=row["error_message"],
            )
            for row in rows
        ]

    def get_run(self, run_id: str) -> RunResult | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT result_json FROM runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None or row["result_json"] is None:
            return None
        return RunResult.model_validate(json.loads(row["result_json"]))

    def save_portfolio(self, portfolio: Portfolio) -> None:
        import datetime

        now = datetime.datetime.now(datetime.UTC).isoformat()
        holdings_data = [h.model_dump() for h in portfolio.holdings]
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO portfolios (name, base_currency, holdings_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    base_currency = excluded.base_currency,
                    holdings_json = excluded.holdings_json,
                    updated_at = excluded.updated_at
                """,
                (
                    portfolio.name,
                    portfolio.base_currency,
                    json.dumps(holdings_data),
                    now,
                    now,
                ),
            )

    def get_portfolio(self, name: str) -> Portfolio | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT name, base_currency, holdings_json FROM portfolios WHERE name = ?",
                (name,),
            ).fetchone()
        if row is None:
            return None
        holdings = json.loads(row["holdings_json"])
        return Portfolio(
            name=row["name"],
            base_currency=row["base_currency"],
            holdings=holdings,
        )

    def list_portfolios(self) -> list[Portfolio]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT name, base_currency, holdings_json FROM portfolios ORDER BY name ASC"
            ).fetchall()
        return [
            Portfolio(
                name=row["name"],
                base_currency=row["base_currency"],
                holdings=json.loads(row["holdings_json"]),
            )
            for row in rows
        ]

    def delete_portfolio(self, name: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM portfolios WHERE name = ?", (name,))
            return cursor.rowcount > 0
