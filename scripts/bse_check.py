"""Check the free BSE-website quote feed (unofficial; no account). Run it during market hours.

    .venv\\Scripts\\python.exe scripts\\bse_check.py                 # RELIANCE TCS INFY, 30 s
    .venv\\Scripts\\python.exe scripts\\bse_check.py SBIN ITC 60     # symbols, then seconds

The key question it answers: is BSE's public data actually live? Each quote carries the exchange's own
'as on' time (minute resolution). During market hours the script compares that time with your clock:
a lag of 0-1 minutes means live; several minutes means delayed, whatever the feed claims.
"""

from __future__ import annotations

import asyncio
import sys
import time

from aletheia.core.events.bus import EventBus, Topics
from aletheia.core.marketdata.hours import market_status
from aletheia.extensions.data.bse_web_stream import BseWebStream, load_bse_scrips

DEFAULT_SECONDS = 30


def report(ok: bool | None, step: str, detail: str = "") -> None:
    mark = {True: "PASS", False: "FAIL", None: "INFO"}[ok]
    print(f"[{mark}] {step}" + (f" - {detail}" if detail else ""))


async def main(symbols: list[str], seconds: int) -> int:
    try:
        scrips = await load_bse_scrips()
    except Exception as exc:  # noqa: BLE001
        report(False, "BSE scrip list", f"could not download: {exc}")
        return 1
    report(True, "BSE scrip list", f"{len(scrips)} active equities")
    missing = [s for s in symbols if s not in scrips]
    if missing:
        report(False, "Symbols", f"not found on BSE: {', '.join(missing)}")
        symbols = [s for s in symbols if s in scrips]
        if not symbols:
            return 1

    mkt = market_status()
    report(None, "Market", f"{mkt['label']} (IST {mkt['ist_time']})")

    bus = EventBus()
    seen: list[dict] = []

    async def on_quote(event) -> None:
        seen.append(event.payload)

    bus.subscribe(Topics.MARKET_QUOTE, on_quote)
    stream = BseWebStream(bus, poll_secs=2.0)
    await stream.set_symbols({("NSE", s): scrips[s] for s in symbols})
    task = asyncio.create_task(stream.run())
    print(f"... polling {', '.join(symbols)} every 2s for {seconds}s")
    start = time.time()
    while time.time() - start < seconds:
        await asyncio.sleep(1)
    status = stream.status()
    stream.stop()
    await asyncio.wait_for(task, 10)

    if not seen:
        report(False, "BSE quotes", status["error"] or "no data (blocked network?)")
        return 1
    report(True, "BSE quotes", f"{len(seen)} responses, {status['reconnects']} recoveries")
    for sym in symbols:
        rows = [q for q in seen if q["symbol"] == sym]
        if not rows:
            report(False, sym, "no quotes")
            continue
        prices = [q["close"] for q in rows]
        moved = len(set(prices)) > 1
        last = rows[-1]
        report(
            None,
            sym,
            f"last {last['close']}, as on {last['exchange_time']}, {len(set(prices))} distinct price(s) in {len(rows)} polls",
        )
        if mkt["is_open"]:
            lag = last["data_lag_secs"]
            live = lag is not None and lag <= 120
            report(
                live,
                f"{sym} freshness",
                f"exchange time is {lag:.0f}s behind your clock"
                + ("" if live else " - DELAYED, do not treat as live")
                if lag is not None
                else "no exchange timestamp",
            )
            if moved:
                report(True, f"{sym} ticking", "price changed while polling")
    if not mkt["is_open"]:
        print("\nMarket is closed, so freshness cannot be judged. Re-run Mon-Fri 09:15-15:30 IST.")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    secs = DEFAULT_SECONDS
    if args and args[-1].isdigit():
        secs, args = int(args.pop()), args
    sys.exit(asyncio.run(main([a.upper() for a in args] or ["RELIANCE", "TCS", "INFY"], secs)))
