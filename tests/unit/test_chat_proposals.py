"""Order proposals: the agent can only ask; a user click places the paper trade, at most once."""

import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from aletheia.core.api import dependencies
from aletheia.core.api.routers import chat as chat_router
from aletheia.core.db.chat_store import ChatStore
from aletheia.core.execution.guard import RiskLimitExceeded
from aletheia.core.main import app
from aletheia.core.tools import order_proposal_tool
from aletheia.core.tools.order_proposal_tool import ProposePaperOrderTool
from aletheia.core.tools.registry import build_registry, split_display


@pytest.fixture
def store(monkeypatch, tmp_path):
    s = ChatStore(tmp_path / "chat.sqlite3")
    monkeypatch.setattr(chat_router, "get_chat_store", lambda: s)
    return s


@pytest.fixture
def priced(monkeypatch):
    monkeypatch.setattr(
        order_proposal_tool,
        "load_bars",
        lambda *a, **k: {"symbol": "RELIANCE.NS", "currency": "INR", "bars": [{"close": 1190.0}]},
    )


class _FakeTrader:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.orders: list = []

    async def submit_order(self, order, run_id=None):
        if self.error:
            raise self.error
        self.orders.append(order)
        return SimpleNamespace(
            simulated_fill_price=1190.5,
            trade_id="t-1",
            model_dump=lambda mode="json": {"trade_id": "t-1", "symbol": order.symbol},
        )


class _FakeGate:
    def __init__(self, paused: bool = False):
        self.paused = paused

    def assert_order_allowed(self):
        if self.paused:
            raise PermissionError("Execution is paused.")


def _wire(monkeypatch, trader, gate=None):
    monkeypatch.setattr(dependencies, "get_paper_trader", lambda: trader)
    monkeypatch.setattr(dependencies, "get_live_gate", lambda: gate or _FakeGate())


async def _propose(store, **args):
    tid = store.create_thread("t", None, None)
    out = await ProposePaperOrderTool(store, tid).execute(
        **{"symbol": "reliance.ns", "side": "buy", "quantity": 10, **args}
    )
    return tid, out


async def test_proposing_stores_a_pending_card_and_places_nothing(store, priced) -> None:
    trader_calls = []
    tid, out = await _propose(store, rationale="trend looks fine")
    result, display = split_display(out)
    assert (
        result["status"] == "awaiting_user_confirmation"
        and "Do not say it was placed" in result["instruction"]
    )
    assert display["symbol"] == "RELIANCE" and display["side"] == "BUY"  # normalised
    assert display["estimated_value"] == 11900.0 and display["currency"] == "INR"
    saved = store.get_proposal(result["proposal_id"])
    assert saved["status"] == "pending" and saved["thread_id"] == tid and not trader_calls


@pytest.mark.parametrize(
    ("args", "fragment"),
    [
        ({"side": "HOLD"}, "BUY or SELL"),
        ({"quantity": 0}, "between 1"),
        ({"quantity": 10**6}, "between 1"),
        ({"quantity": "many"}, "whole number"),
        ({"order_type": "LIMIT"}, "limit_price"),
        ({"exchange": "NYSE"}, "NSE or BSE"),
    ],
)
async def test_bad_proposals_are_refused(store, priced, args, fragment) -> None:
    _, out = await _propose(store, **args)
    assert fragment in out["error"]
    with sqlite3.connect(store.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM proposals").fetchone()[0] == 0


async def test_unpriceable_symbol_is_not_proposed(store, monkeypatch) -> None:
    monkeypatch.setattr(order_proposal_tool, "load_bars", lambda *a, **k: {"error": "none"})
    _, out = await _propose(store)
    assert "Could not price" in out["error"]


def test_proposal_tool_is_not_in_the_default_registry() -> None:
    assert "propose_paper_order" not in {t.name for t in build_registry().list_tools()}


async def test_execute_places_one_paper_trade_even_when_clicked_twice(
    store, priced, monkeypatch
) -> None:
    trader = _FakeTrader()
    _wire(monkeypatch, trader)
    tid, out = await _propose(store)
    pid = out["proposal_id"]
    client = TestClient(app)

    first = client.post(f"/api/v1/chat/proposals/{pid}/execute")
    assert first.status_code == 200 and first.json()["proposal"]["status"] == "executed"
    second = client.post(f"/api/v1/chat/proposals/{pid}/execute")
    assert second.status_code == 409 and "already placed" in second.json()["message"]

    assert (
        len(trader.orders) == 1
        and trader.orders[0].side == "BUY"
        and trader.orders[0].symbol == "RELIANCE"
    )
    # The model can see on its next turn that the order really went through.
    assert "Paper order placed" in store.history(tid)[-1]["content"]
    assert (
        client.get(f"/api/v1/chat/proposals/{pid}").json()["outcome"]["trade"]["trade_id"] == "t-1"
    )


async def test_rejected_and_expired_proposals_never_execute(store, priced, monkeypatch) -> None:
    trader = _FakeTrader()
    _wire(monkeypatch, trader)
    client = TestClient(app)

    _, out = await _propose(store)
    assert (
        client.post(f"/api/v1/chat/proposals/{out['proposal_id']}/reject").json()["status"]
        == "rejected"
    )
    assert client.post(f"/api/v1/chat/proposals/{out['proposal_id']}/execute").status_code == 409

    _, old = await _propose(store)
    stale = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE proposals SET created_at = ? WHERE id = ?", (stale, old["proposal_id"])
        )
    expired = client.post(f"/api/v1/chat/proposals/{old['proposal_id']}/execute")
    assert expired.status_code == 409 and "expired" in expired.json()["message"]
    assert trader.orders == []


async def test_risk_limit_and_paused_failures_are_reported_and_final(
    store, priced, monkeypatch
) -> None:
    client = TestClient(app)
    _wire(monkeypatch, _FakeTrader(RiskLimitExceeded("Order too large.", ["max_position"])))
    _, a = await _propose(store)
    r = client.post(f"/api/v1/chat/proposals/{a['proposal_id']}/execute")
    assert r.status_code == 422 and "too large" in r.json()["message"]
    assert store.get_proposal(a["proposal_id"])["status"] == "failed"

    _wire(monkeypatch, _FakeTrader(), _FakeGate(paused=True))
    _, b = await _propose(store)
    r = client.post(f"/api/v1/chat/proposals/{b['proposal_id']}/execute")
    assert r.status_code == 409 and "paused" in r.json()["message"]
    # A failed proposal is final: it cannot be retried into a trade later.
    _wire(monkeypatch, _FakeTrader())
    assert client.post(f"/api/v1/chat/proposals/{b['proposal_id']}/execute").status_code == 409


def test_unknown_proposal_is_404(store) -> None:
    client = TestClient(app)
    assert client.get("/api/v1/chat/proposals/nope").status_code == 404
    assert client.post("/api/v1/chat/proposals/nope/execute").status_code == 404
    assert client.post("/api/v1/chat/proposals/nope/reject").status_code == 404
