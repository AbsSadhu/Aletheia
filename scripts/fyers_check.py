"""Step-by-step check of your Fyers live-feed setup.

    .venv\\Scripts\\python.exe scripts\\fyers_check.py            # streams RELIANCE and TCS
    .venv\\Scripts\\python.exe scripts\\fyers_check.py INFY SBIN   # other NSE symbols

Each line prints PASS/FAIL with what to fix. Ticks only flow while the market is open
(Mon-Fri 09:15-15:30 IST); outside those hours it still verifies login and the connection.
"""

from __future__ import annotations

import asyncio
import sys
import time

from aletheia.config.config_manager import ConfigManager
from aletheia.core.events.bus import EventBus, Topics
from aletheia.core.marketdata.hours import market_status
from aletheia.extensions.brokers import fyers_session
from aletheia.extensions.data.fyers_stream import FyersStream, default_python, to_fyers_symbol

STREAM_SECONDS = 15


def report(ok: bool | None, step: str, detail: str = "") -> None:
    mark = {True: "PASS", False: "FAIL", None: "INFO"}[ok]
    print(f"[{mark}] {step}" + (f" - {detail}" if detail else ""))


def yahoo_reference(symbol: str) -> float | None:
    try:
        import yfinance as yf

        h = yf.Ticker(f"{symbol}.NS").history(period="5d")
        return float(h["Close"].iloc[-1]) if not h.empty else None
    except Exception:  # noqa: BLE001
        return None


async def main(symbols: list[str]) -> int:
    cfg = ConfigManager().load()
    if not (cfg.fyers_app_id and cfg.fyers_secret):
        report(
            False,
            "Credentials",
            "app ID / secret missing. Settings -> Broker Integrations -> Fyers.",
        )
        return 1
    report(True, "Credentials", f"app ID {cfg.fyers_app_id}")

    if not default_python().exists():
        report(
            False,
            "Helper environment",
            "missing. Run: .venv\\Scripts\\python.exe scripts\\fyers_setup.py",
        )
        return 1
    report(True, "Helper environment", str(default_python()))

    token = fyers_session.current_ws_token()
    if token is None:
        report(
            False,
            "Login",
            "no valid token. Fyers tokens expire at 06:30 IST every day: Settings -> Connect Fyers, then re-run.",
        )
        return 1
    report(True, "Login", "valid token for today")

    mkt = market_status()
    report(None, "Market", f"{mkt['label']} (IST {mkt['ist_time']})")

    bus = EventBus()
    seen: list[dict] = []

    async def on_quote(event) -> None:
        seen.append(event.payload)

    bus.subscribe(Topics.MARKET_QUOTE, on_quote)
    stream = FyersStream(fyers_session.current_ws_token, bus, emit_interval=1.0)
    await stream.set_symbols({("NSE", s): to_fyers_symbol(s, "NSE") or "" for s in symbols})
    task = asyncio.create_task(stream.run())
    print(f"... streaming {', '.join(symbols)} for {STREAM_SECONDS}s")
    start = time.time()
    while time.time() - start < STREAM_SECONDS:
        await asyncio.sleep(1)
    status = stream.status()
    stream.stop()
    try:
        await asyncio.wait_for(task, 10)
    except Exception:  # noqa: BLE001
        task.cancel()

    if status["needs_login"]:
        report(False, "Stream", status["error"] or "login expired")
        return 1
    if not status["connected"] and not seen:
        report(False, "Stream", status["error"] or "could not connect")
        return 1
    report(True, "Stream", "connected")

    if not seen:
        if mkt["is_open"]:
            report(False, "Live ticks", "market is open but no ticks arrived; check the symbols")
            return 1
        report(None, "Live ticks", "none (expected: market closed). Re-run during 09:15-15:30 IST.")
    else:
        latest = {q["symbol"]: q for q in seen}
        report(
            True,
            "Live ticks",
            f"{len(seen)} updates in {STREAM_SECONDS}s across {len(latest)} symbols",
        )
        for sym, q in latest.items():
            ref = yahoo_reference(sym)
            plausible = ref is None or 0.8 <= q["close"] / ref <= 1.25
            report(
                plausible,
                f"Price sanity {sym}",
                f"stream {q['close']} vs Yahoo last close {ref}"
                + ("" if plausible else " - MISMATCH, do not trade on this"),
            )
    print(
        "\nIf all PASS: set live_feed_provider to fyers (Settings), restart the backend, open Live Market."
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main([s.upper() for s in sys.argv[1:]] or ["RELIANCE", "TCS"])))
