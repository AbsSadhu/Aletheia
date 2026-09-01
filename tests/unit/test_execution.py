from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from aletheia.core.execution.live_gate import LiveExecutionGate
from aletheia.core.execution.models import ExecutionMode, OrderRequest
from aletheia.core.execution.paper_trader import PaperTrader
from aletheia.core.execution.storage import ExecutionStorage
from aletheia.core.marketdata.adapters import MarketDataAdapter
from aletheia.core.marketdata.engine import MarketDataEngine
from aletheia.core.models import MarketQuote


class FakeAdapter(MarketDataAdapter):
    name = "fake"

    async def get_quote(self, symbol: str, exchange: str) -> list[MarketQuote]:
        return [
            MarketQuote(
                symbol=symbol.upper(),
                exchange=exchange,
                close=100.0,
                open=99.0,
                high=101.0,
                low=98.0,
                volume=1000.0,
                provider=self.name,
            )
        ]


def test_paper_trader_buy_and_sell(tmp_path: Path) -> None:
    storage = ExecutionStorage(tmp_path / "execution.sqlite3")
    market = MarketDataEngine(tmp_path / "market.duckdb", adapters=[FakeAdapter()])
    trader = PaperTrader(storage=storage, market_data=market)

    async def scenario() -> None:
        buy = await trader.submit_order(
            OrderRequest(symbol="RELIANCE", exchange="NSE", side="BUY", quantity=10)
        )
        assert buy.simulated_fill_price == 100.0
        assert len(trader.list_positions()) == 1

        sell = await trader.submit_order(
            OrderRequest(symbol="RELIANCE", exchange="NSE", side="SELL", quantity=4, limit_price=110)
        )
        assert sell.simulated_pnl == 40.0
        positions = trader.list_positions()
        assert positions[0].quantity == 6

    asyncio.run(scenario())


def test_live_gate_enforces_confirmation(tmp_path: Path) -> None:
    gate = LiveExecutionGate(ExecutionStorage(tmp_path / "execution.sqlite3"))
    with pytest.raises(PermissionError):
        gate.set_mode(ExecutionMode.LIVE, confirm=False, paper_observation_days=7)

    with pytest.raises(PermissionError):
        gate.set_mode(ExecutionMode.LIVE, confirm=True, paper_observation_days=1)

    state = gate.set_mode(ExecutionMode.PAPER, confirm=False, paper_observation_days=0)
    assert state.mode == ExecutionMode.PAPER


def test_live_gate_pause_blocks_execution(tmp_path: Path) -> None:
    gate = LiveExecutionGate(ExecutionStorage(tmp_path / "execution.sqlite3"))
    gate.pause()
    with pytest.raises(PermissionError):
        gate.assert_order_allowed()
