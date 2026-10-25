from types import SimpleNamespace

import pytest

from aletheia.core.execution.guard import ExecutionGuard, RiskLimitExceeded
from aletheia.core.execution.models import OrderRequest
from aletheia.core.execution.paper_trader import PaperTrader
from aletheia.core.execution.storage import ExecutionStorage
from aletheia.core.models import OracleOutput
from aletheia.extensions.shadow_account.account import ShadowAccount
from aletheia.extensions.shadow_account.scanner import EntryExitScanner
from aletheia.extensions.shadow_account.storage import ShadowAccountStorage

SETTINGS = SimpleNamespace(
    risk_per_trade_pct=1.0,
    fallback_position_pct=5.0,
    pm_max_position_size_pct=20.0,
    pm_min_cash_reserve_pct=5.0,
)


class _Engine:
    def __init__(self, price: float = 100.0) -> None:
        self.price = price

    async def get_quote(self, request):
        return SimpleNamespace(close=self.price)


def test_size_buy_risks_one_percent_to_the_stop() -> None:
    g = ExecutionGuard(SETTINGS)
    # 1% of 1,000,000 = 10,000 risk; 100 - 95 = 5 per share -> 2000 shares
    assert g.size_buy(100.0, 1_000_000, stop_price=95.0) == 2000


def test_size_buy_falls_back_without_a_usable_stop() -> None:
    g = ExecutionGuard(SETTINGS)
    assert g.size_buy(100.0, 1_000_000, stop_price=None) == 500  # 5% slice
    assert g.size_buy(100.0, 1_000_000, stop_price=120.0) == 500  # stop above price is nonsense
    assert g.size_buy(0.0, 1_000_000) == 0


def test_check_buy_shrinks_to_position_cap() -> None:
    g = ExecutionGuard(SETTINGS)
    d = g.check_buy("X", 5000, 100.0, equity=1_000_000, cash=1_000_000)
    assert d.reduced and d.approved_qty == 2000  # 20% of 1M / 100


def test_check_buy_never_breaches_cash_reserve() -> None:
    g = ExecutionGuard(SETTINGS)
    # cash 100k, reserve 5% of 1M = 50k -> only 50k spendable = 500 shares
    d = g.check_buy("X", 1500, 100.0, equity=1_000_000, cash=100_000)
    assert d.approved_qty == 500
    assert g.check_buy("X", 10, 100.0, equity=1_000_000, cash=50_500).approved_qty == 5
    with pytest.raises(RiskLimitExceeded):
        g.check_buy("X", 10, 100.0, equity=1_000_000, cash=50_000)  # nothing above the reserve


def test_check_buy_counts_existing_position() -> None:
    g = ExecutionGuard(SETTINGS)
    with pytest.raises(RiskLimitExceeded):
        g.check_buy("X", 10, 100.0, 1_000_000, 1_000_000, current_position_value=200_000)


def test_check_sell_rejects_unheld_and_oversized() -> None:
    with pytest.raises(RiskLimitExceeded, match="No open position"):
        ExecutionGuard.check_sell("X", 1, 0)
    with pytest.raises(RiskLimitExceeded, match="only 5"):
        ExecutionGuard.check_sell("X", 6, 5)
    ExecutionGuard.check_sell("X", 5, 5)


async def test_paper_order_over_limit_is_rejected_not_resized(tmp_path) -> None:
    trader = PaperTrader(
        ExecutionStorage(tmp_path / "e.sqlite3"),
        _Engine(100.0),
        guard=ExecutionGuard(SETTINGS),
        starting_cash=1_000_000,
    )
    with pytest.raises(RiskLimitExceeded, match="most allowed"):
        await trader.submit_order(OrderRequest(symbol="X", side="BUY", quantity=5000))
    ok = await trader.submit_order(OrderRequest(symbol="X", side="BUY", quantity=1000))
    assert ok.simulated_qty == 1000
    with pytest.raises(RiskLimitExceeded, match="only 1000"):
        await trader.submit_order(OrderRequest(symbol="X", side="SELL", quantity=2000))


async def test_scanner_sizes_by_stop_and_never_double_buys(tmp_path) -> None:
    storage = ShadowAccountStorage(str(tmp_path / "s.sqlite3"))
    account = ShadowAccount(storage, _Engine(100.0), 1_000_000, guard=ExecutionGuard(SETTINGS))
    scanner = EntryExitScanner(account, guard=ExecutionGuard(SETTINGS))

    buy = OracleOutput(symbol="X", signal="BUY", confidence=0.8, stop_loss_price=95.0)
    first = await scanner.scan([buy])
    # 2000 shares wanted, but the 20% position cap shrinks it to 2000 -> exactly the cap
    assert first[0]["action"] == "buy" and first[0]["qty"] == 2000

    again = await scanner.scan([buy])
    assert again == []  # already held

    sell = OracleOutput(symbol="X", signal="REDUCE", confidence=0.8)
    out = await scanner.scan([sell])
    assert out[0]["action"] == "sell" and out[0]["qty"] == 2000  # whole position, not 1 share
    _, _, held = account.account_state()
    assert "X" not in held


async def test_scanner_ignores_low_confidence_and_bad_data(tmp_path) -> None:
    storage = ShadowAccountStorage(str(tmp_path / "s.sqlite3"))
    account = ShadowAccount(storage, _Engine(100.0), 1_000_000, guard=ExecutionGuard(SETTINGS))
    scanner = EntryExitScanner(account, guard=ExecutionGuard(SETTINGS))
    weak = OracleOutput(symbol="X", signal="BUY", confidence=0.4)
    nodata = OracleOutput(symbol="Y", signal="BUY", confidence=0.9, data_quality="stale")
    assert await scanner.scan([weak, nodata]) == []
