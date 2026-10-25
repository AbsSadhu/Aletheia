import hashlib
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from aletheia.core.execution.live_broker import LiveBroker, LiveOrderRejected
from aletheia.core.execution.live_gate import LiveExecutionGate
from aletheia.core.execution.models import ExecutionMode, OrderRequest, PaperTradeResult
from aletheia.core.execution.storage import ExecutionStorage
from aletheia.extensions.brokers import zerodha, zerodha_session
from aletheia.extensions.brokers.zerodha import KiteAuthError, ZerodhaKiteConnector


# -- Kite OAuth / connector ---------------------------------------------------
async def test_exchange_request_token_sends_documented_checksum() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["form"] = dict(httpx.QueryParams(request.content.decode()))
        return httpx.Response(200, json={"status": "success", "data": {"access_token": "AT"}})

    client = httpx.AsyncClient(base_url=zerodha.ROOT, transport=httpx.MockTransport(handler))
    data = await zerodha.exchange_request_token("key", "secret", "rt", client)

    assert data["access_token"] == "AT"
    assert seen["form"]["checksum"] == hashlib.sha256(b"keyrtsecret").hexdigest()


async def test_exchange_rejection_raises() -> None:
    client = httpx.AsyncClient(
        base_url=zerodha.ROOT,
        transport=httpx.MockTransport(
            lambda r: httpx.Response(403, json={"status": "error", "message": "bad token"})
        ),
    )
    with pytest.raises(KiteAuthError, match="bad token"):
        await zerodha.exchange_request_token("k", "s", "rt", client)


def _connector(handler) -> ZerodhaKiteConnector:
    client = httpx.AsyncClient(base_url=zerodha.ROOT, transport=httpx.MockTransport(handler))
    return ZerodhaKiteConnector("key", "tok", client=client)


async def test_place_order_form_and_auth_header() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["authorization"]
        seen["path"] = request.url.path
        seen["form"] = dict(httpx.QueryParams(request.content.decode()))
        return httpx.Response(200, json={"status": "success", "data": {"order_id": "123"}})

    res = await _connector(handler).place_order("infy", "buy", 3, "LIMIT", 1500.0)

    assert res == {"order_id": "123", "status": "submitted"}
    assert seen["auth"] == "token key:tok" and seen["path"] == "/orders/regular"
    assert seen["form"]["tradingsymbol"] == "INFY"
    assert seen["form"]["product"] == "CNC" and seen["form"]["price"] == "1500.0"


async def test_place_order_validation_and_token_errors() -> None:
    c = _connector(lambda r: httpx.Response(200, json={"status": "success", "data": {}}))
    with pytest.raises(ValueError):
        await c.place_order("INFY", "BUY", 1, "LIMIT", None)
    with pytest.raises(ValueError):
        await c.place_order("INFY", "BUY", 1, "SL-M", 1.0)

    expired = _connector(
        lambda r: httpx.Response(
            403, json={"status": "error", "error_type": "TokenException", "message": "expired"}
        )
    )
    with pytest.raises(KiteAuthError):
        await expired.get_orders()
    with pytest.raises(KiteAuthError):
        await ZerodhaKiteConnector("k", None).get_orders()


def test_token_freshness_boundary_is_6am_ist() -> None:
    now = datetime(2026, 10, 26, 3, 0, tzinfo=UTC)  # 08:30 IST
    assert zerodha_session.token_is_fresh((now - timedelta(hours=1)).isoformat(), now)
    stale = (now - timedelta(hours=4)).isoformat()  # 04:30 IST, before the 06:00 reset
    assert not zerodha_session.token_is_fresh(stale, now)
    assert not zerodha_session.token_is_fresh(None, now)


def test_login_state_is_single_use() -> None:
    s = zerodha_session.new_login_state()
    assert zerodha_session.consume_login_state(s) is True
    assert zerodha_session.consume_login_state(s) is False
    assert zerodha_session.consume_login_state("forged") is False


# -- Live order safety checks -------------------------------------------------
class _FakeConnector:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def place_order(self, **kw):
        self.calls.append(kw)
        return {"order_id": "OID1", "status": "submitted"}


def _setup(tmp_path, **overrides):
    storage = ExecutionStorage(tmp_path / "exec.sqlite3")
    gate = LiveExecutionGate(storage)
    settings = SimpleNamespace(
        live_trading_enabled=True,
        api_keys=["k"],
        live_max_order_value=25000.0,
        live_max_order_qty=500,
        live_max_orders_per_day=2,
    )
    for k, v in overrides.items():
        setattr(settings, k, v)
    connector = _FakeConnector()

    async def factory():
        return connector

    return LiveBroker(gate, storage, settings, factory), gate, storage, connector


def _go_live(gate, storage) -> None:
    for i in range(7):  # fabricate 7 distinct paper-trading days
        ts = datetime.now(UTC) - timedelta(days=i)
        storage.record_trade(
            PaperTradeResult(
                symbol="X",
                exchange="NSE",
                side="buy",
                recommendation="BUY",
                simulated_qty=1,
                simulated_fill_price=1,
                timestamp=ts,
            )
        )
    gate.set_mode(
        ExecutionMode.LIVE, confirm=True, paper_observation_days=storage.paper_observation_days()
    )


def _order(**kw) -> OrderRequest:
    base = dict(symbol="INFY", side="BUY", quantity=10, order_type="LIMIT", limit_price=1500.0)
    return OrderRequest(**{**base, **kw})


async def test_default_state_sends_nothing(tmp_path) -> None:
    broker, gate, storage, conn = _setup(tmp_path)  # simulation mode
    with pytest.raises(LiveOrderRejected):
        await broker.place(_order(), confirm=True)
    assert conn.calls == []
    assert storage.list_live_orders()[0]["status"] == "rejected"


@pytest.mark.parametrize(
    "overrides,order_kw,confirm,match",
    [
        ({"live_trading_enabled": False}, {}, True, "disabled"),
        ({"api_keys": []}, {}, True, "API_KEYS"),
        ({}, {}, False, "confirm"),
        ({}, {"quantity": 501}, True, "Quantity exceeds"),
        ({}, {"quantity": 2.5}, True, "whole number"),
        ({}, {"limit_price": 3000.0}, True, "exceeds the cap"),
        ({}, {"order_type": "MARKET", "limit_price": None}, True, "price"),
        ({}, {"exchange": "NYSE"}, True, "NSE/BSE"),
        ({}, {"order_type": "SL-M"}, True, "MARKET or LIMIT"),
    ],
)
async def test_each_check_blocks_before_the_broker(tmp_path, overrides, order_kw, confirm, match):
    broker, gate, storage, conn = _setup(tmp_path, **overrides)
    _go_live(gate, storage)
    with pytest.raises(LiveOrderRejected, match=match):
        await broker.place(_order(**order_kw), confirm=confirm)
    assert conn.calls == []


async def test_paused_blocks(tmp_path) -> None:
    broker, gate, storage, conn = _setup(tmp_path)
    _go_live(gate, storage)
    gate.pause()
    with pytest.raises(LiveOrderRejected, match="paused"):
        await broker.place(_order(), confirm=True)
    assert conn.calls == []


async def test_valid_order_goes_through_and_daily_cap_applies(tmp_path) -> None:
    broker, gate, storage, conn = _setup(tmp_path)
    _go_live(gate, storage)

    res = await broker.place(_order(), confirm=True)
    assert res["order_id"] == "OID1"
    assert conn.calls[0]["qty"] == 10 and conn.calls[0]["price"] == 1500.0
    await broker.place(_order(), confirm=True)
    with pytest.raises(LiveOrderRejected, match="Daily cap"):
        await broker.place(_order(), confirm=True)
    assert len(conn.calls) == 2


async def test_market_order_uses_reference_price_for_value_cap(tmp_path) -> None:
    broker, gate, storage, conn = _setup(tmp_path)
    _go_live(gate, storage)
    mkt = _order(order_type="MARKET", limit_price=None, quantity=100)
    with pytest.raises(LiveOrderRejected, match="exceeds the cap"):
        await broker.place(mkt, confirm=True, reference_price=1500.0)  # 150k > 25k
    small = mkt.model_copy(update={"quantity": 10})
    await broker.place(small, confirm=True, reference_price=1500.0)
    assert conn.calls[-1]["price"] is None


def test_observation_days_are_measured_not_claimed(tmp_path) -> None:
    storage = ExecutionStorage(tmp_path / "e.sqlite3")
    gate = LiveExecutionGate(storage)
    assert storage.paper_observation_days() == 0
    with pytest.raises(PermissionError):
        gate.set_mode(
            ExecutionMode.LIVE,
            confirm=True,
            paper_observation_days=storage.paper_observation_days(),
        )
