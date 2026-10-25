"""Check the free per-second crypto feed (Binance public stream; no account or API key).

    .venv\\Scripts\\python.exe scripts\\crypto_check.py              # BTC/USDT and ETH/USDT
    .venv\\Scripts\\python.exe scripts\\crypto_check.py SOL/USDT     # other pairs

Crypto trades 24/7, so unlike the stock feeds this works at any hour. It prints how many
updates arrived, how stale each tick was when received, and compares the price with Yahoo as a
sanity check. If Binance is blocked in your region it says so.
"""

from __future__ import annotations

import asyncio
import sys
import time
from datetime import datetime

from aletheia.core.events.bus import EventBus, Topics
from aletheia.extensions.data.binance_stream import BinanceStream, to_stream_name

SECONDS = 10


def report(ok: bool | None, step: str, detail: str = "") -> None:
    mark = {True: "PASS", False: "FAIL", None: "INFO"}[ok]
    print(f"[{mark}] {step}" + (f" - {detail}" if detail else ""))


def yahoo_price(pair: str) -> float | None:
    try:
        import yfinance as yf

        base = pair.split("/")[0]
        h = yf.Ticker(f"{base}-USD").history(period="1d", interval="1m")
        return float(h["Close"].iloc[-1]) if not h.empty else None
    except Exception:  # noqa: BLE001
        return None


async def main(pairs: list[str]) -> int:
    bus = EventBus()
    seen: list[tuple[float, dict]] = []

    async def on_quote(event) -> None:
        seen.append((time.time(), event.payload))

    bus.subscribe(Topics.MARKET_QUOTE, on_quote)
    stream = BinanceStream(bus)
    await stream.set_symbols({("BINANCE", p): to_stream_name(p, "BINANCE") or "" for p in pairs})
    task = asyncio.create_task(stream.run())
    print(f"... streaming {', '.join(pairs)} for {SECONDS}s")
    await asyncio.sleep(SECONDS)
    status = stream.status()
    stream.stop()
    try:
        await asyncio.wait_for(task, 10)
    except Exception:  # noqa: BLE001
        task.cancel()

    if not seen:
        report(
            False,
            "Binance stream",
            status["error"] or "no data received (blocked network or region?)",
        )
        print("If Binance is blocked where you are, set ALETHEIA_CRYPTO_STREAM_ENABLED=false.")
        return 1
    report(True, "Binance stream", f"connected via {status['endpoint']}")

    for pair in pairs:
        rows = [(t, q) for t, q in seen if q["symbol"] == pair]
        if not rows:
            report(False, pair, "no ticks")
            continue
        rate = len(rows) / SECONDS
        lags = [t - datetime.fromisoformat(q["as_of"]).timestamp() for t, q in rows]
        report(
            0.5 <= rate <= 2.5,
            f"{pair} rate",
            f"{len(rows)} updates in {SECONDS}s (about {rate:.1f}/s), avg age on arrival {sum(lags) / len(lags):.2f}s",
        )
        last = rows[-1][1]["close"]
        ref = yahoo_price(pair)
        if ref:
            ok = abs(last / ref - 1) < 0.02
            report(ok, f"{pair} price sanity", f"stream {last} vs Yahoo {ref:.2f}")
        else:
            report(None, f"{pair} price sanity", f"stream {last} (Yahoo unavailable)")
    print("\nOK. Add crypto pairs (like BTC/USDT, exchange BINANCE) on the Live Market page.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main([a.upper() for a in sys.argv[1:]] or ["BTC/USDT", "ETH/USDT"])))
