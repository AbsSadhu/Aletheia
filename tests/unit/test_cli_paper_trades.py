"""`aletheia paper settle` must only pick up trades that are still waiting for a close price."""

from datetime import UTC, date, datetime

from aletheia.cli.paper_trades import unsettled_buys
from aletheia.core.execution.models import PaperTradeResult


def _trade(side: str = "BUY", status: str = "filled", day: int = 1) -> PaperTradeResult:
    return PaperTradeResult(
        symbol="RELIANCE",
        exchange="NSE",
        side=side,
        recommendation="BUY",
        simulated_qty=1,
        simulated_fill_price=100.0,
        timestamp=datetime(2026, 11, day, 10, tzinfo=UTC),
        status=status,
    )


def test_already_settled_trades_are_not_settled_again() -> None:
    open_buy, settled_buy = _trade(), _trade(status="settled")
    assert unsettled_buys([open_buy, settled_buy], date(2026, 11, 5)) == [open_buy]


def test_only_buys_up_to_the_settle_date() -> None:
    early, late, sell = _trade(day=2), _trade(day=9), _trade(side="SELL")
    assert unsettled_buys([early, late, sell], date(2026, 11, 5)) == [early]
