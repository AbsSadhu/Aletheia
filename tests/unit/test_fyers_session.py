import hashlib
import json
import urllib.parse
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aletheia.core.api.routers import brokers
from aletheia.core.events.bus import EventBus
from aletheia.core.marketdata.feed_manager import FeedManager
from aletheia.core.marketdata.live_feed import MarketFeedPoller
from aletheia.core.marketdata.watchlist import WatchlistStore
from aletheia.extensions.brokers import fyers_session as fy
from aletheia.extensions.brokers import zerodha_session
from aletheia.extensions.data import fyers_stream


def test_login_url_matches_the_sdk_format() -> None:
    url = fy.login_url("ABC-100", "http://127.0.0.1:8899/cb", "nonce1")
    parts = urllib.parse.urlsplit(url)
    assert (
        f"{parts.scheme}://{parts.netloc}{parts.path}"
        == "https://api-t1.fyers.in/api/v3/generate-authcode"
    )
    q = dict(urllib.parse.parse_qsl(parts.query))
    assert q == {
        "client_id": "ABC-100",
        "redirect_uri": "http://127.0.0.1:8899/cb",
        "response_type": "code",
        "state": "nonce1",
    }


async def test_exchange_sends_the_documented_hash_and_returns_the_token() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        return httpx.Response(
            200, json={"s": "ok", "code": 200, "access_token": "AT", "refresh_token": "RT"}
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    data = await fy.exchange_auth_code("ABC-100", "sekret", "the_code", client)

    assert data["access_token"] == "AT"
    assert seen["url"] == "https://api-t1.fyers.in/api/v3/validate-authcode"
    assert seen["body"] == {
        "grant_type": "authorization_code",
        "appIdHash": hashlib.sha256(b"ABC-100:sekret").hexdigest(),
        "code": "the_code",
    }


async def test_exchange_rejection_raises_with_fyers_message() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(
                200, json={"s": "error", "code": -413, "message": "invalid auth code"}
            )
        )
    )
    with pytest.raises(fy.FyersAuthError, match="invalid auth code"):
        await fy.exchange_auth_code("A", "S", "bad", client)


def test_token_expires_at_0630_ist() -> None:
    now = datetime(2026, 10, 26, 3, 30, tzinfo=UTC)  # 09:00 IST, after today's 06:30 reset
    assert fy.token_is_fresh((now - timedelta(hours=1)).isoformat(), now)  # 08:00 IST today
    assert not fy.token_is_fresh(
        (now - timedelta(hours=3)).isoformat(), now
    )  # 06:00 IST: before reset
    assert not fy.token_is_fresh(None, now)


def test_token_boundary_is_0630_not_0600() -> None:
    now = datetime(2026, 10, 26, 3, 30, tzinfo=UTC)  # 09:00 IST
    just_after = (datetime(2026, 10, 26, 1, 5, tzinfo=UTC)).isoformat()  # 06:35 IST
    just_before = (datetime(2026, 10, 26, 0, 40, tzinfo=UTC)).isoformat()  # 06:10 IST
    assert fy.token_is_fresh(just_after, now)
    assert not fy.token_is_fresh(just_before, now)  # Kite's 06:00 rule would wrongly accept this


def test_ws_token_is_app_id_colon_access_token_and_none_when_stale(monkeypatch) -> None:
    cfg = SimpleNamespace(
        fyers_app_id="ABC-100",
        fyers_access_token="AT",
        fyers_token_date=datetime.now(UTC).isoformat(),
        fyers_secret="s",
    )
    monkeypatch.setattr(fy, "ConfigManager", lambda: SimpleNamespace(load=lambda: cfg))
    assert fy.current_ws_token() == "ABC-100:AT"
    cfg.fyers_token_date = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    assert fy.current_ws_token() is None
    cfg.fyers_token_date = datetime.now(UTC).isoformat()
    cfg.fyers_access_token = None
    assert fy.current_ws_token() is None
    assert fy.session_status() == {"configured": True, "logged_in": False}


# -- routes ---------------------------------------------------------------------------
@pytest.fixture
def client(monkeypatch):
    cfg = SimpleNamespace(fyers_app_id="ABC-100", fyers_secret="sekret")
    monkeypatch.setattr(brokers, "ConfigManager", lambda: SimpleNamespace(load=lambda: cfg))
    app = FastAPI()
    app.include_router(brokers.router)
    app.include_router(brokers.callback_router)
    return TestClient(app), cfg


def test_login_url_endpoint_includes_state_and_redirect(client) -> None:
    c, _ = client
    body = c.get("/api/v1/brokers/fyers/login-url").json()
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(body["url"]).query))
    assert q["client_id"] == "ABC-100" and q["state"]
    assert body["redirect_uri"].endswith("/api/v1/brokers/fyers/callback")
    assert q["redirect_uri"] == body["redirect_uri"]


def test_login_url_needs_configured_credentials(client) -> None:
    c, cfg = client
    cfg.fyers_secret = None
    assert c.get("/api/v1/brokers/fyers/login-url").status_code == 400


def test_callback_rejects_forged_state_before_calling_fyers(client, monkeypatch) -> None:
    c, _ = client

    async def boom(*a, **k):  # pragma: no cover - must not be reached
        raise AssertionError("token exchange attempted with a forged state")

    monkeypatch.setattr(fy, "exchange_auth_code", boom)
    r = c.get(
        "/api/v1/brokers/fyers/callback", params={"s": "ok", "auth_code": "x", "state": "forged"}
    )
    assert r.status_code == 400 and "state" in r.text


def test_callback_success_saves_the_token(client, monkeypatch) -> None:
    c, _ = client
    saved = {}

    async def fake_exchange(app_id, secret, code, client=None):
        saved["args"] = (app_id, secret, code)
        return {"access_token": "AT123"}

    monkeypatch.setattr(fy, "exchange_auth_code", fake_exchange)
    monkeypatch.setattr(fy, "save_access_token", lambda t: saved.setdefault("token", t))
    state = zerodha_session.new_login_state()
    r = c.get(
        "/api/v1/brokers/fyers/callback", params={"s": "ok", "auth_code": "CODE", "state": state}
    )
    assert r.status_code == 200 and "Fyers connected" in r.text
    assert saved["args"] == ("ABC-100", "sekret", "CODE") and saved["token"] == "AT123"
    # the nonce is single use
    again = c.get(
        "/api/v1/brokers/fyers/callback", params={"s": "ok", "auth_code": "CODE", "state": state}
    )
    assert again.status_code == 400


def test_callback_handles_fyers_refusal(client, monkeypatch) -> None:
    c, _ = client

    async def reject(*a, **k):
        raise fy.FyersAuthError("invalid auth code")

    monkeypatch.setattr(fy, "exchange_auth_code", reject)
    state = zerodha_session.new_login_state()
    r = c.get(
        "/api/v1/brokers/fyers/callback", params={"s": "ok", "auth_code": "bad", "state": state}
    )
    assert r.status_code == 400 and "invalid auth code" in r.text
    state = zerodha_session.new_login_state()
    assert (
        c.get("/api/v1/brokers/fyers/callback", params={"s": "error", "state": state}).status_code
        == 400
    )


# -- feed manager in Fyers mode ----------------------------------------------------------
class _Collector:
    async def collect_for_holding(self, holding):  # pragma: no cover
        raise AssertionError


def _manager(tmp_path, **settings):
    store = WatchlistStore(tmp_path / "w.json")
    base = dict(
        live_feed_provider="fyers",
        market_feed_enabled=True,
        market_feed_interval_secs=15.0,
        market_feed_emit_interval_secs=1.0,
    )
    base.update(settings)
    bus = EventBus()
    return FeedManager(
        SimpleNamespace(**base), bus, store, MarketFeedPoller(_Collector(), bus)
    ), store


async def test_fyers_mode_without_helper_env_gives_setup_hint(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(fyers_stream, "default_python", lambda: tmp_path / "missing" / "python.exe")
    from aletheia.core.marketdata import feed_manager

    monkeypatch.setattr(feed_manager, "default_python", lambda: tmp_path / "missing" / "python.exe")
    m, _ = _manager(tmp_path)
    await m.start()
    st = m.status()
    assert m.stream is None and st["provider"] == "fyers" and st["mode"] == "polling"
    assert "fyers_setup.py" in st["setup_hint"]


async def test_fyers_mode_maps_nse_only_and_flags_bse(tmp_path, monkeypatch) -> None:
    from aletheia.core.marketdata import feed_manager

    py = tmp_path / "python.exe"
    py.write_text("")
    monkeypatch.setattr(feed_manager, "default_python", lambda: py)
    m, store = _manager(tmp_path)
    from aletheia.core.marketdata.watchlist import WatchItem

    store.save([WatchItem(symbol="TCS", exchange="NSE"), WatchItem(symbol="TCS", exchange="BSE")])
    await m._start_fyers()
    await m.apply_watchlist()

    assert m.stream.covers("TCS", "NSE") and not m.stream.covers("TCS", "BSE")
    assert m.unresolved_symbols() == ["TCS:BSE"]  # surfaced in the UI as "unknown"
    # not connected yet, so the poller still serves everything
    assert m.status()["mode"] == "polling"


async def test_needs_login_is_surfaced_as_the_setup_hint(tmp_path, monkeypatch) -> None:
    from aletheia.core.marketdata import feed_manager

    py = tmp_path / "python.exe"
    py.write_text("")
    monkeypatch.setattr(feed_manager, "default_python", lambda: py)
    m, _ = _manager(tmp_path)
    await m._start_fyers()
    m.stream.needs_login = True
    m.stream.last_error = "Fyers login required."
    assert m.status()["setup_hint"] == "Fyers login required."
