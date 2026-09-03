from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from aletheia.core.execution.models import (
    ExecutionMode,
    ExecutionState,
    PaperPosition,
    PaperTradeResult,
)


class ExecutionStorage:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_trades (
                    trade_id TEXT PRIMARY KEY,
                    run_id TEXT,
                    symbol TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    side TEXT NOT NULL,
                    recommendation TEXT NOT NULL,
                    simulated_qty REAL NOT NULL,
                    simulated_fill_price REAL NOT NULL,
                    simulated_pnl REAL NOT NULL,
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS paper_positions (
                    symbol TEXT NOT NULL,
                    exchange TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    average_price REAL NOT NULL,
                    realized_pnl REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (symbol, exchange)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_state (
                    singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
                    mode TEXT NOT NULL,
                    paused INTEGER NOT NULL,
                    observation_days_required INTEGER NOT NULL,
                    live_approved_at TEXT
                )
                """
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO execution_state
                    (singleton_id, mode, paused, observation_days_required, live_approved_at)
                VALUES (1, 'simulation', 0, 7, NULL)
                """
            )
            conn.commit()

    def record_trade(self, trade: PaperTradeResult) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO paper_trades
                    (trade_id, run_id, symbol, exchange, side, recommendation, simulated_qty,
                     simulated_fill_price, simulated_pnl, timestamp, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.trade_id,
                    trade.run_id,
                    trade.symbol,
                    trade.exchange,
                    trade.side,
                    trade.recommendation,
                    trade.simulated_qty,
                    trade.simulated_fill_price,
                    trade.simulated_pnl,
                    trade.timestamp.isoformat(),
                    trade.status,
                ),
            )
            conn.commit()

    def upsert_position(self, position: PaperPosition) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO paper_positions (symbol, exchange, quantity, average_price, realized_pnl, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, exchange) DO UPDATE SET
                    quantity = excluded.quantity,
                    average_price = excluded.average_price,
                    realized_pnl = excluded.realized_pnl,
                    updated_at = excluded.updated_at
                """,
                (
                    position.symbol,
                    position.exchange,
                    position.quantity,
                    position.average_price,
                    position.realized_pnl,
                    position.updated_at.isoformat(),
                ),
            )
            conn.commit()

    def delete_position(self, symbol: str, exchange: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM paper_positions WHERE symbol = ? AND exchange = ?",
                (symbol, exchange),
            )
            conn.commit()

    def get_position(self, symbol: str, exchange: str) -> PaperPosition | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM paper_positions WHERE symbol = ? AND exchange = ?",
                (symbol, exchange),
            ).fetchone()
        if row is None:
            return None
        return PaperPosition(
            symbol=row["symbol"],
            exchange=row["exchange"],
            quantity=row["quantity"],
            average_price=row["average_price"],
            realized_pnl=row["realized_pnl"],
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    def list_positions(self) -> list[PaperPosition]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM paper_positions ORDER BY symbol, exchange"
            ).fetchall()
        return [
            PaperPosition(
                symbol=row["symbol"],
                exchange=row["exchange"],
                quantity=row["quantity"],
                average_price=row["average_price"],
                realized_pnl=row["realized_pnl"],
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )
            for row in rows
        ]

    def list_trades(self, limit: int = 50) -> list[PaperTradeResult]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM paper_trades ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            PaperTradeResult(
                trade_id=row["trade_id"],
                run_id=row["run_id"],
                symbol=row["symbol"],
                exchange=row["exchange"],
                side=row["side"],
                recommendation=row["recommendation"],
                simulated_qty=row["simulated_qty"],
                simulated_fill_price=row["simulated_fill_price"],
                simulated_pnl=row["simulated_pnl"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                status=row["status"],
            )
            for row in rows
        ]

    def get_state(self) -> ExecutionState:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM execution_state WHERE singleton_id = 1").fetchone()
        return ExecutionState(
            mode=ExecutionMode(row["mode"]),
            paused=bool(row["paused"]),
            observation_days_required=row["observation_days_required"],
            live_approved_at=(
                datetime.fromisoformat(row["live_approved_at"]) if row["live_approved_at"] else None
            ),
        )

    def update_trade_settlement(
        self, trade_id: str, actual_close: float, realized_pnl: float
    ) -> None:
        """Persist actual close price and realized PnL for a settled trade."""
        with self._connect() as conn:
            # Migrate column if not yet present (idempotent)
            try:
                conn.execute("ALTER TABLE paper_trades ADD COLUMN actual_close REAL")
            except sqlite3.OperationalError:
                pass  # Column already exists
            conn.execute(
                """
                UPDATE paper_trades
                SET simulated_pnl = ?, status = 'settled', actual_close = ?
                WHERE trade_id = ?
                """,
                (round(realized_pnl, 2), actual_close, trade_id),
            )
            conn.commit()

    def save_state(self, state: ExecutionState) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE execution_state
                SET mode = ?, paused = ?, observation_days_required = ?, live_approved_at = ?
                WHERE singleton_id = 1
                """,
                (
                    state.mode.value,
                    int(state.paused),
                    state.observation_days_required,
                    state.live_approved_at.isoformat() if state.live_approved_at else None,
                ),
            )
            conn.commit()
