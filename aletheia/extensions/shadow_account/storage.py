import sqlite3
import json
import logging
from typing import List, Optional
from datetime import datetime
from aletheia.extensions.shadow_account.models import TradeEntry, VirtualPosition, AccountSnapshot

logger = logging.getLogger(__name__)

class ShadowAccountStorage:
    def __init__(self, db_path: str = "shadow_account.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    symbol TEXT,
                    action TEXT,
                    quantity REAL,
                    price REAL,
                    timestamp TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP,
                    total_equity REAL,
                    cash_balance REAL,
                    positions TEXT
                )
            ''')
            conn.commit()

    def log_trade(self, trade: TradeEntry):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT INTO trades (id, symbol, action, quantity, price, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (trade.id, trade.symbol, trade.action, trade.quantity, trade.price, trade.timestamp.isoformat()))
            conn.commit()

    def get_trades(self, symbol: Optional[str] = None) -> List[TradeEntry]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if symbol:
                rows = conn.execute("SELECT * FROM trades WHERE symbol = ? ORDER BY timestamp ASC", (symbol,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM trades ORDER BY timestamp ASC").fetchall()
            
            return [TradeEntry(
                id=row['id'],
                symbol=row['symbol'],
                action=row['action'],
                quantity=row['quantity'],
                price=row['price'],
                timestamp=datetime.fromisoformat(row['timestamp'])
            ) for row in rows]

    def save_snapshot(self, snapshot: AccountSnapshot):
        with sqlite3.connect(self.db_path) as conn:
            positions_json = json.dumps([p.model_dump(mode='json') for p in snapshot.positions])
            conn.execute('''
                INSERT INTO snapshots (timestamp, total_equity, cash_balance, positions)
                VALUES (?, ?, ?, ?)
            ''', (snapshot.timestamp.isoformat(), snapshot.total_equity, snapshot.cash_balance, positions_json))
            conn.commit()

    def get_latest_snapshot(self) -> Optional[AccountSnapshot]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM snapshots ORDER BY timestamp DESC LIMIT 1").fetchone()
            if row:
                positions = [VirtualPosition(**p) for p in json.loads(row['positions'])]
                return AccountSnapshot(
                    timestamp=datetime.fromisoformat(row['timestamp']),
                    total_equity=row['total_equity'],
                    cash_balance=row['cash_balance'],
                    positions=positions
                )
            return None
