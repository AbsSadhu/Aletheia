import logging
from typing import List, Dict, Any
from aletheia.extensions.shadow_account.storage import ShadowAccountStorage

logger = logging.getLogger(__name__)

class ShadowAccountReporter:
    def __init__(self, storage: ShadowAccountStorage):
        self.storage = storage

    def generate_summary(self) -> Dict[str, Any]:
        snapshot = self.storage.get_latest_snapshot()
        if not snapshot:
            return {"status": "No active shadow account or snapshots."}

        total_unrealized_pnl = sum(p.unrealized_pnl for p in snapshot.positions)
        
        return {
            "timestamp": snapshot.timestamp.isoformat(),
            "total_equity": snapshot.total_equity,
            "cash_balance": snapshot.cash_balance,
            "total_unrealized_pnl": total_unrealized_pnl,
            "positions": [
                {
                    "symbol": p.symbol,
                    "quantity": p.quantity,
                    "avg_price": p.average_price,
                    "current_price": p.current_price,
                    "unrealized_pnl": p.unrealized_pnl
                }
                for p in snapshot.positions
            ]
        }

    def generate_trade_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        trades = self.storage.get_trades()
        # Return most recent trades first
        trades = sorted(trades, key=lambda t: t.timestamp, reverse=True)[:limit]
        return [
            {
                "id": t.id,
                "symbol": t.symbol,
                "action": t.action,
                "quantity": t.quantity,
                "price": t.price,
                "timestamp": t.timestamp.isoformat()
            }
            for t in trades
        ]
