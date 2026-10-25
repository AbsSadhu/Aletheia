"""Step-by-step check of your Angel One setup. Run it after saving credentials:

    .venv\\Scripts\\python.exe scripts\\angel_check.py            # all checks
    .venv\\Scripts\\python.exe scripts\\angel_check.py RELIANCE   # test another symbol

Each step prints PASS/FAIL with what to fix. The streaming step only produces ticks while the
market is open (Mon-Fri 09:15-15:30 IST); outside hours it still checks the connection.
"""

from __future__ import annotations

import asyncio
import sys
import time

from aletheia.core.events.bus import EventBus, Topics
from aletheia.core.marketdata.hours import market_status
from aletheia.extensions.data.angel_session import AngelOneSession
from aletheia.extensions.data.angel_stream import AngelOneStream
from aletheia.extensions.data.providers.angel_one_provider import (
    AngelOneProvider,
    load_scrip_tokens,
)

STREAM_SECONDS = 12


def report(ok: bool | None, step: str, detail: str = "") -> None:
    mark = {True: "PASS", False: "FAIL", None: "INFO"}[ok]
    print(f"[{mark}] {step}" + (f" - {detail}" if detail else ""))


async def main(symbol: str) -> int:
    session = AngelOneSession()
    creds = session.credentials()
    if creds is None:
        report(
            False,
            "Credentials",
            "missing. Run:  .venv\\Scripts\\python.exe -m aletheia.cli.main config init  "
            "(or fill Settings -> Broker Integrations).",
        )
        return 1
    report(True, "Credentials", f"client code {creds['client_code']}, API key and PIN present")

    if not await session.ensure():
        hint = (
            "Check client code, PIN, and that TOTP was enabled at smartapi.angelone.in. "
            "A wrong TOTP secret or a clock that is off by >30s also fails here."
        )
        report(False, "Login", f"{session.last_error}. {hint}")
        return 1
    report(True, "Login", "got JWT" + (" and feed token" if session.feed_token else ""))
    if not session.feed_token:
        report(False, "Feed token", "login returned none; the WebSocket stream needs it")
        return 1

    try:
        scrips = await load_scrip_tokens()
    except Exception as exc:
        report(False, "Instrument list", f"download failed: {exc}")
        return 1
    token = scrips.get(("NSE", symbol))
    if token is None:
        report(False, "Instrument token", f"{symbol} is not an NSE cash equity")
        return 1
    report(True, "Instrument token", f"{symbol} -> {token} ({len(scrips)} NSE/BSE equities loaded)")

    provider = AngelOneProvider(session=session)
    quotes = await provider.get_quote(symbol, "NSE")
    if not quotes:
        report(False, "REST quote", "no quote returned (market data may need the API key enabled)")
        return 1
    ref = quotes[0].close
    report(True, "REST quote", f"{symbol} last price {ref}")

    mkt = market_status()
    report(None, "Market", f"{mkt['label']} (IST {mkt['ist_time']})")

    bus = EventBus()
    seen: list[dict] = []

    async def on_quote(event) -> None:
        seen.append(event.payload)

    bus.subscribe(Topics.MARKET_QUOTE, on_quote)

    async def reference(sym: str, exch: str) -> float | None:
        q = await provider.get_quote(sym, exch)
        return q[0].close if q else None

    stream = AngelOneStream(session, bus, emit_interval=1.0, scale_check=reference)
    await stream.set_symbols({("NSE", symbol): token})
    task = asyncio.create_task(stream.run())
    print(f"... streaming {symbol} for {STREAM_SECONDS}s")
    start = time.time()
    while time.time() - start < STREAM_SECONDS:
        await asyncio.sleep(1)
    stream.stop()
    task.cancel()
    status = stream.status()

    if not status["connected"] and not seen:
        report(False, "WebSocket", status["error"] or "could not connect")
        return 1
    report(True, "WebSocket", "connected")
    if seen:
        last = seen[-1]
        report(
            True,
            "Live ticks",
            f"{len(seen)} updates in {STREAM_SECONDS}s, last price {last['close']}",
        )
        ok = status["price_scale_verified"]
        report(
            ok if ok is not None else None,
            "Price scale",
            "streamed price matches the REST quote" if ok else "could not verify vs REST",
        )
    elif mkt["is_open"]:
        report(
            False, "Live ticks", "market is open but no ticks arrived; check the symbol and token"
        )
        return 1
    else:
        report(
            None,
            "Live ticks",
            "none (expected: the market is closed). Re-run during 09:15-15:30 IST.",
        )
    print("\nSetup looks good. Enable it in Settings (Angel One Live Feed), restart the backend,")
    print("and open the Live Market page.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1].upper() if len(sys.argv) > 1 else "RELIANCE")))
