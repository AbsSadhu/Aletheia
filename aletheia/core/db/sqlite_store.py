from __future__ import annotations

import json
import sqlite3
import datetime
import queue
import threading
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from aletheia.core.models import (
    Portfolio,
    RunResult,
    RunStatus,
    RunSummary,
    AgentEvent,
    AgentName,
)

logger = logging.getLogger(__name__)


class SQLiteConnectionPool:
    """Thread-safe SQLite connection pool that enables WAL mode and foreign key support."""

    def __init__(self, db_path: Path, max_connections: int = 10, timeout: float = 5.0) -> None:
        self.db_path = db_path
        self.max_connections = max_connections
        self.timeout = timeout
        self._pool: queue.Queue[sqlite3.Connection] = queue.Queue(maxsize=max_connections)
        self._allocated = 0
        self._lock = threading.Lock()

    def get_connection(self) -> sqlite3.Connection:
        try:
            conn = self._pool.get_nowait()
            try:
                conn.execute("SELECT 1")
                return conn
            except sqlite3.Error:
                try:
                    conn.close()
                except Exception:
                    pass
        except queue.Empty:
            pass

        with self._lock:
            if self._allocated < self.max_connections:
                conn = self._create_connection()
                self._allocated += 1
                return conn

        try:
            return self._pool.get(timeout=self.timeout)
        except queue.Empty:
            raise sqlite3.OperationalError("SQLite Connection Pool: Timeout getting connection")

    def return_connection(self, conn: sqlite3.Connection) -> None:
        try:
            self._pool.put_nowait(conn)
        except queue.Full:
            try:
                conn.close()
            except Exception:
                pass
            with self._lock:
                self._allocated -= 1

    def _create_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def close_all(self) -> None:
        with self._lock:
            while not self._pool.empty():
                try:
                    conn = self._pool.get_nowait()
                    conn.close()
                except queue.Empty:
                    break
            self._allocated = 0


class SQLiteStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        self.pool = SQLiteConnectionPool(self.db_path)
        
        # Initialize database column-level encryptor
        from aletheia.core.config.settings import get_settings
        from aletheia.core.security.encryption import DatabaseEncryptor
        settings = get_settings()
        self.encryptor = DatabaseEncryptor(settings.db_encryption_key)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = self.pool.get_connection()
        try:
            yield connection
            connection.commit()
        except Exception:
            try:
                connection.rollback()
            except Exception:
                pass
            raise
        finally:
            self.pool.return_connection(connection)

    def _initialize(self) -> None:
        # Run Alembic migrations programmatically
        from alembic.config import Config
        from alembic import command
        
        project_root = Path(__file__).resolve().parent.parent.parent.parent
        ini_path = project_root / "alembic.ini"
        if not ini_path.exists():
            ini_path = Path("alembic.ini")
            
        if ini_path.exists():
            try:
                alembic_cfg = Config(str(ini_path))
                db_url = f"sqlite:///{self.db_path.resolve().as_posix()}"
                alembic_cfg.set_main_option("sqlalchemy.url", db_url)
                alembic_cfg.set_main_option("script_location", str(project_root / "alembic"))
                
                command.upgrade(alembic_cfg, "head")
                logger.info("SQLiteStore: Database migrated to head successfully via Alembic.")
                self._legacy_initialize()
            except Exception as e:
                logger.exception("SQLiteStore: Alembic migration failed, fallback to legacy schema check:")
                self._legacy_initialize()
        else:
            logger.warning("SQLiteStore: alembic.ini not found, running legacy initialization.")
            self._legacy_initialize()

    def _legacy_initialize(self) -> None:
        # Connect directly to perform initialization (before pool is configured)
        conn = sqlite3.connect(self.db_path)
        try:
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    payload_json TEXT,
                    FOREIGN KEY(run_id) REFERENCES runs(run_id) ON DELETE CASCADE
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_events_run_id ON agent_events(run_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_agent_events_timestamp ON agent_events(timestamp)"
            )
            # ── Confidence Calibration ──────────────────────────────────────
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS confidence_calibration (
                    record_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    predicted_signal TEXT NOT NULL,
                    predicted_confidence REAL NOT NULL,
                    actual_return_7d REAL,
                    actual_return_30d REAL,
                    brier_score REAL,
                    recorded_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_calibration_symbol ON confidence_calibration(symbol, agent)"
            )
            # ── SEBI Compliance Log (append-only) ───────────────────────────
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS compliance_log (
                    log_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    action TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    reasoning_hash TEXT NOT NULL,
                    disclaimer TEXT NOT NULL,
                    logged_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_compliance_logged_at ON compliance_log(logged_at)"
            )
            # Enforce append-only on compliance_log
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS compliance_no_update
                    BEFORE UPDATE ON compliance_log
                    BEGIN SELECT RAISE(ABORT, 'compliance_log is immutable'); END
                """
            )
            conn.execute(
                """
                CREATE TRIGGER IF NOT EXISTS compliance_no_delete
                    BEFORE DELETE ON compliance_log
                    BEGIN SELECT RAISE(ABORT, 'compliance_log is immutable'); END
                """
            )
            conn.commit()
        finally:
            conn.close()

    def upsert_run(self, summary: RunSummary, result: RunResult | None = None) -> None:
        payload = result.model_dump_json() if result else None
        encrypted_payload = self.encryptor.encrypt(payload)
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
                    encrypted_payload,
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
        decrypted_json = self.encryptor.decrypt(row["result_json"])
        if decrypted_json is None:
            return None
        return RunResult.model_validate(json.loads(decrypted_json))

    def save_portfolio(self, portfolio: Portfolio) -> None:
        import datetime

        now = datetime.datetime.now(datetime.UTC).isoformat()
        holdings_data = [h.model_dump() for h in portfolio.holdings]
        encrypted_holdings = self.encryptor.encrypt(json.dumps(holdings_data))
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
                    encrypted_holdings,
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
        decrypted_json = self.encryptor.decrypt(row["holdings_json"])
        holdings = json.loads(decrypted_json) if decrypted_json else []
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
        
        portfolios = []
        for row in rows:
            decrypted_json = self.encryptor.decrypt(row["holdings_json"])
            holdings = json.loads(decrypted_json) if decrypted_json else []
            portfolios.append(
                Portfolio(
                    name=row["name"],
                    base_currency=row["base_currency"],
                    holdings=holdings,
                )
            )
        return portfolios

    def delete_portfolio(self, name: str) -> bool:
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM portfolios WHERE name = ?", (name,))
            return cursor.rowcount > 0

    def save_agent_event(self, event: AgentEvent) -> None:
        payload_json = json.dumps(event.payload) if event.payload is not None else None
        encrypted_payload = self.encryptor.encrypt(payload_json)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO agent_events (run_id, agent, message, timestamp, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.run_id,
                    event.agent.value,
                    event.message,
                    event.timestamp.isoformat(),
                    encrypted_payload,
                ),
            )

    def get_agent_events(self, run_id: str) -> list[AgentEvent]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT agent, message, timestamp, payload_json
                FROM agent_events
                WHERE run_id = ?
                ORDER BY id ASC
                """,
                (run_id,),
            ).fetchall()

        events = []
        for row in rows:
            decrypted_json = self.encryptor.decrypt(row["payload_json"])
            payload = json.loads(decrypted_json) if decrypted_json is not None else None
            events.append(
                AgentEvent(
                    run_id=run_id,
                    agent=AgentName(row["agent"]),
                    message=row["message"],
                    timestamp=datetime.datetime.fromisoformat(row["timestamp"]),
                    payload=payload,
                )
            )
        return events

    def prune_old_events(self, days: int) -> int:
        import datetime
        cutoff = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)).isoformat()
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM agent_events WHERE timestamp < ?", (cutoff,))
            return cursor.rowcount

    # ── Confidence Calibration ─────────────────────────────────────────────

    def record_confidence(
        self,
        run_id: str,
        symbol: str,
        agent: str,
        predicted_signal: str,
        predicted_confidence: float,
    ) -> str:
        """Record a prediction for later outcome tracking. Returns record_id."""
        from aletheia.core.models import ConfidenceRecord
        rec = ConfidenceRecord(
            run_id=run_id,
            symbol=symbol,
            agent=agent,
            predicted_signal=predicted_signal,
            predicted_confidence=predicted_confidence,
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO confidence_calibration
                (record_id, run_id, symbol, agent, predicted_signal, predicted_confidence, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (rec.record_id, rec.run_id, rec.symbol, rec.agent,
                 rec.predicted_signal, rec.predicted_confidence,
                 rec.recorded_at.isoformat()),
            )
        return rec.record_id

    def update_calibration_outcome(
        self,
        record_id: str,
        actual_return_7d: float | None,
        actual_return_30d: float | None,
        brier_score: float | None,
    ) -> None:
        """Update calibration record with actual outcomes."""
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE confidence_calibration
                SET actual_return_7d = ?, actual_return_30d = ?, brier_score = ?
                WHERE record_id = ?
                """,
                (actual_return_7d, actual_return_30d, brier_score, record_id),
            )

    def get_calibration_score(self, symbol: str, agent: str, lookback: int = 20) -> float | None:
        """Return rolling Brier score for an agent on a symbol. Lower = better calibrated."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT brier_score FROM confidence_calibration
                WHERE symbol = ? AND agent = ? AND brier_score IS NOT NULL
                ORDER BY recorded_at DESC
                LIMIT ?
                """,
                (symbol, agent, lookback),
            ).fetchall()
        if not rows:
            return None
        scores = [r[0] for r in rows]
        return round(sum(scores) / len(scores), 4)

    def get_pending_calibration_records(self, days_old: int = 7) -> list[dict]:
        """Return records where outcomes are not yet filled (>N days old)."""
        import datetime
        cutoff = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days_old)).isoformat()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT record_id, symbol, predicted_signal, predicted_confidence, recorded_at
                FROM confidence_calibration
                WHERE actual_return_7d IS NULL AND recorded_at < ?
                ORDER BY recorded_at ASC
                LIMIT 100
                """,
                (cutoff,),
            ).fetchall()
        return [dict(r) for r in rows]

    # ── SEBI Compliance Log ────────────────────────────────────────────────

    def log_compliance(
        self,
        run_id: str,
        symbol: str,
        action: str,
        confidence: float,
        reasoning_hash: str,
        disclaimer: str,
    ) -> str:
        """Append a SEBI compliance log entry. Returns log_id."""
        from aletheia.core.models import SEBIComplianceLog
        entry = SEBIComplianceLog(
            run_id=run_id,
            symbol=symbol,
            action=action,
            confidence=confidence,
            reasoning_hash=reasoning_hash,
            disclaimer=disclaimer,
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO compliance_log
                (log_id, run_id, symbol, action, confidence, reasoning_hash, disclaimer, logged_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (entry.log_id, entry.run_id, entry.symbol, entry.action,
                 entry.confidence, entry.reasoning_hash, entry.disclaimer,
                 entry.logged_at.isoformat()),
            )
        return entry.log_id

    def get_compliance_log(
        self,
        from_date: str | None = None,
        to_date: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Query compliance log by date range."""
        query = "SELECT * FROM compliance_log WHERE 1=1"
        params: list = []
        if from_date:
            query += " AND logged_at >= ?"
            params.append(from_date)
        if to_date:
            query += " AND logged_at <= ?"
            params.append(to_date)
        query += " ORDER BY logged_at DESC LIMIT ?"
        params.append(limit)
        with self.connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
