"""Fyers live stream: the helper-process protocol, tick conversion, and failure handling.

The bridge is exercised for real (a subprocess running fyers_bridge.py) against a stand-in for
Fyers' SDK in tests/fixtures/fake_fyers. Not covered here, and not coverable without a Fyers
account: the actual SDK talking to Fyers' servers.
"""

import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


from aletheia.core.events.bus import EventBus, Topics
from aletheia.extensions.data import fyers_stream as fs
from aletheia.extensions.data.fyers_stream import (
    BRIDGE_PATH,
    FyersStream,
    from_fyers_symbol,
    tick_to_quote,
    to_fyers_symbol,
)

STUB = str(Path(__file__).resolve().parents[1] / "fixtures" / "fake_fyers")


def _env(stub: bool = True) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = STUB if stub else ""
    return env


async def spawn_bridge(stub: bool = True):
    return await asyncio.create_subprocess_exec(
        sys.executable,
        str(BRIDGE_PATH),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=_env(stub),
    )


# -- pure conversions ---------------------------------------------------------------
def test_symbol_mapping_is_nse_equity_only() -> None:
    assert to_fyers_symbol("reliance", "NSE") == "NSE:RELIANCE-EQ"
    assert to_fyers_symbol("M&M", "NSE") == "NSE:M&M-EQ"
    assert to_fyers_symbol("RELIANCE", "BSE") is None  # BSE series suffixes vary per stock
    assert to_fyers_symbol("BTC/USDT", "BINANCE") is None
    assert from_fyers_symbol("NSE:SBIN-EQ") == ("SBIN", "NSE")
    assert from_fyers_symbol("NSE:NIFTY50-INDEX") is None
    assert from_fyers_symbol("garbage") is None


def test_tick_to_quote_maps_fields_in_rupees() -> None:
    now = time.time()
    q = tick_to_quote(
        {
            "symbol": "NSE:RELIANCE-EQ", "ltp": 1250.5, "open_price": 1240.0, "high_price": 1260.0,
            "low_price": 1235.0, "prev_close_price": 1200.0, "chp": 4.21, "vol_traded_today": 99,
            "last_traded_time": int(now) - 3, "type": "sf",
        }
    )  # fmt: skip
    assert (q["symbol"], q["exchange"], q["close"]) == ("RELIANCE", "NSE", 1250.5)
    assert q["prev_close"] == 1200.0 and q["change_pct"] == 4.21 and q["volume"] == 99.0
    assert q["provider"] == "fyers_stream" and q["stream"] is True
    assert q["as_of"].startswith(time.strftime("%Y-%m-%d", time.gmtime(now - 3)))


def test_tick_to_quote_rejects_unusable_ticks() -> None:
    base = {"symbol": "NSE:TCS-EQ", "ltp": 10.0}
    assert tick_to_quote({**base, "ltp": 0}) is None
    assert tick_to_quote({**base, "ltp": float("nan")}) is None
    assert tick_to_quote({**base, "ltp": None}) is None
    assert tick_to_quote({"symbol": "NSE:NIFTY50-INDEX", "ltp": 10.0}) is None
    assert tick_to_quote({"ltp": 10.0}) is None


def test_tick_to_quote_derives_change_when_fyers_omits_it() -> None:
    q = tick_to_quote({"symbol": "NSE:TCS-EQ", "ltp": 110.0, "prev_close_price": 100.0})
    assert q["change_pct"] == 10.0


def test_implausible_exchange_time_falls_back_to_receive_time() -> None:
    q = tick_to_quote({"symbol": "NSE:TCS-EQ", "ltp": 1.0, "last_traded_time": 5})  # 1970
    assert q["as_of"][:4] == time.strftime("%Y", time.gmtime())


# -- the real bridge against the SDK stand-in ----------------------------------------
def _read_events(proc: subprocess.Popen, n: int, timeout: float = 10.0) -> list[dict]:
    out, start = [], time.time()
    while len(out) < n and time.time() - start < timeout:
        line = proc.stdout.readline()
        if not line:
            break
        out.append(json.loads(line))  # raises if SDK noise leaked into the protocol stream
    return out


def _bridge(stub: bool = True) -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, str(BRIDGE_PATH)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=_env(stub),
    )  # fmt: skip


def _send(proc: subprocess.Popen, obj: dict) -> None:
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


def test_bridge_relays_clean_json_despite_sdk_printing_to_stdout() -> None:
    proc = _bridge()
    try:
        _send(proc, {"cmd": "start", "token": "APP-100:tok", "symbols": ["NSE:SBIN-EQ"]})
        events = _read_events(proc, 6)  # every line must parse as JSON
        kinds = [e["ev"] for e in events]
        assert kinds[0] == "connected"
        ticks = [e["data"] for e in events if e["ev"] == "tick"]
        assert ticks and all(t["symbol"] == "NSE:SBIN-EQ" for t in ticks)
        assert any(e["ev"] == "info" for e in events)  # the subscribe ack is not a tick
    finally:
        _send(proc, {"cmd": "stop"})
        assert proc.wait(timeout=10) == 0


def test_bridge_set_replaces_the_subscription() -> None:
    proc = _bridge()
    try:
        _send(proc, {"cmd": "start", "token": "APP-100:tok", "symbols": ["NSE:SBIN-EQ"]})
        _read_events(proc, 4)
        _send(proc, {"cmd": "set", "symbols": ["NSE:TCS-EQ"]})
        time.sleep(0.3)  # let in-flight SBIN ticks drain
        _read_events(proc, 5)
        later = _read_events(proc, 6)
        symbols = {e["data"]["symbol"] for e in later if e["ev"] == "tick"}
        assert symbols == {"NSE:TCS-EQ"}
    finally:
        _send(proc, {"cmd": "stop"})
        proc.wait(timeout=10)


def test_bridge_exits_when_the_parent_goes_away() -> None:
    proc = _bridge()
    _send(proc, {"cmd": "start", "token": "APP-100:tok", "symbols": ["NSE:SBIN-EQ"]})
    _read_events(proc, 2)
    proc.stdin.close()  # parent died: stdin hits EOF
    assert proc.wait(timeout=10) == 0  # no orphaned helper


def test_bridge_reports_fatal_when_the_sdk_is_missing() -> None:
    proc = _bridge(stub=False)
    try:
        out, _ = proc.communicate(
            json.dumps({"cmd": "start", "token": "x", "symbols": []}) + "\n", timeout=15
        )
    finally:
        proc.kill()
    event = json.loads(out.splitlines()[0])
    assert event["ev"] == "fatal" and "not installed" in event["message"]
    assert proc.returncode == 2


def test_bridge_rejects_a_missing_token() -> None:
    proc = _bridge()
    out, _ = proc.communicate(json.dumps({"cmd": "start"}) + "\n", timeout=15)
    assert json.loads(out.splitlines()[0])["ev"] == "fatal"
    assert proc.returncode == 2


# -- the async stream, end to end through the real bridge ------------------------------
async def _run_stream(token: str | None, seconds: float, **kw):
    bus = EventBus()
    got: list[dict] = []

    async def on_q(e) -> None:
        got.append(e.payload)

    bus.subscribe(Topics.MARKET_QUOTE, on_q)
    spawns = {"n": 0}

    async def spawn():
        spawns["n"] += 1
        return await spawn_bridge()

    s = FyersStream(lambda: token, bus, emit_interval=0.1, spawn=spawn, token_poll_secs=0.1, **kw)
    await s.set_symbols({("NSE", "SBIN"): "NSE:SBIN-EQ", ("NSE", "TCS"): "NSE:TCS-EQ"})
    task = asyncio.create_task(s.run())
    await asyncio.sleep(seconds)
    return s, task, got, spawns


async def _finish(s: FyersStream, task: asyncio.Task) -> None:
    s.stop()
    await asyncio.wait_for(task, 15)


async def test_stream_publishes_coalesced_quotes_end_to_end() -> None:
    s, task, got, _ = await _run_stream("APP-100:tok", 2.0)
    try:
        assert s.status()["connected"] is True and s.status()["ticks"] > 5
        by_symbol = {q["symbol"] for q in got}
        assert by_symbol == {"SBIN", "TCS"}
        # the stand-in ticks every 50 ms; with a 100 ms flush we publish far fewer than we receive
        assert len(got) < s.ticks_total
        q = got[-1]
        assert q["provider"] == "fyers_stream" and q["close"] > 1000
        assert s.covers("SBIN", "NSE") and not s.covers("SBIN", "BSE")
        assert ("SBIN", "NSE") in s.last_quotes
    finally:
        await _finish(s, task)


async def test_stream_applies_a_new_watchlist_live() -> None:
    s, task, got, _ = await _run_stream("APP-100:tok", 1.2)
    try:
        await s.set_symbols({("NSE", "INFY"): "NSE:INFY-EQ"})
        await asyncio.sleep(1.5)
        got.clear()
        await asyncio.sleep(1.0)
        assert {q["symbol"] for q in got} == {"INFY"}
    finally:
        await _finish(s, task)


async def test_expired_token_stops_retrying_and_asks_for_login() -> None:
    s, task, got, spawns = await _run_stream("APP-100:EXPIRED", 1.5)
    try:
        st = s.status()
        assert st["needs_login"] is True and "expired" in st["error"].lower()
        assert got == [] and st["connected"] is False
        assert spawns["n"] == 1  # a restart cannot fix an expired token, so it must not spin
    finally:
        await _finish(s, task)


async def test_a_fresh_token_resumes_after_expiry() -> None:
    bus = EventBus()
    token = {"v": "APP-100:EXPIRED"}
    spawns = {"n": 0}

    async def spawn():
        spawns["n"] += 1
        return await spawn_bridge()

    s = FyersStream(lambda: token["v"], bus, emit_interval=0.1, spawn=spawn, token_poll_secs=0.1)
    await s.set_symbols({("NSE", "SBIN"): "NSE:SBIN-EQ"})
    task = asyncio.create_task(s.run())
    await asyncio.sleep(1.2)
    assert s.status()["needs_login"] is True
    token["v"] = "APP-100:newtoken"  # user logs in again
    await asyncio.sleep(2.0)
    try:
        assert s.status()["connected"] is True and s.status()["needs_login"] is False
        assert spawns["n"] == 2
    finally:
        await _finish(s, task)


async def test_no_token_means_login_required_not_a_crash() -> None:
    s, task, _, spawns = await _run_stream(None, 0.6)
    try:
        assert s.status()["needs_login"] is True and spawns["n"] == 0
        assert "login" in s.status()["error"].lower()
    finally:
        await _finish(s, task)


async def test_crashing_helper_is_restarted() -> None:
    s, task, _, spawns = await _run_stream("APP-100:CRASH", 3.5)
    try:
        assert spawns["n"] >= 2
        assert s.status()["reconnects"] >= 1
    finally:
        await _finish(s, task)


async def test_missing_helper_environment_gives_an_actionable_error(tmp_path) -> None:
    bus = EventBus()
    s = FyersStream(
        lambda: "APP-100:tok", bus, python=tmp_path / "nope" / "python.exe", token_poll_secs=0.1
    )
    task = asyncio.create_task(s.run())
    await asyncio.sleep(0.5)
    try:
        assert "fyers_setup.py" in (s.status()["error"] or "")
    finally:
        await _finish(s, task)


async def test_helper_without_the_sdk_stops_instead_of_looping() -> None:
    bus = EventBus()
    spawns = {"n": 0}

    async def spawn():
        spawns["n"] += 1
        return await spawn_bridge(stub=False)

    s = FyersStream(lambda: "APP-100:tok", bus, spawn=spawn, token_poll_secs=0.1)
    await s.set_symbols({("NSE", "SBIN"): "NSE:SBIN-EQ"})
    task = asyncio.create_task(s.run())
    await asyncio.wait_for(task, 20)  # it should end by itself
    assert spawns["n"] == 1 and "not installed" in s.status()["error"]


def test_default_python_points_at_the_isolated_venv() -> None:
    p = fs.default_python()
    assert ".aletheia" in str(p) and "fyers-venv" in str(p)


# -- behaviours observed from the REAL SDK with a bad token ------------------------------
@pytest.mark.parametrize("suffix", ["INVALID", "REJECTED"])
async def test_real_sdk_auth_failures_ask_for_login_and_never_look_connected(suffix) -> None:
    # -300 "Please provide valid token" is exactly what the real SDK returned for a bad token,
    # and it still fires on_connect afterwards. That must not read as "streaming".
    s, task, got, spawns = await _run_stream(f"APP-100:{suffix}", 1.5)
    try:
        st = s.status()
        assert st["needs_login"] is True and st["connected"] is False
        assert "log in again" in st["error"].lower()
        assert got == [] and spawns["n"] == 1
    finally:
        await _finish(s, task)


async def test_connected_only_after_the_authentication_ack() -> None:
    s, task, _, _ = await _run_stream("APP-100:tok", 1.5)
    try:
        assert s.status()["connected"] is True and s.status()["needs_login"] is False
    finally:
        await _finish(s, task)
