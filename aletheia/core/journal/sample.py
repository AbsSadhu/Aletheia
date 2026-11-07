"""A synthetic Zerodha-style tradebook, so the journal review can be tried without a real file.

The trader it simulates holds losers longer than winners and buys after run-ups on purpose, so the
diagnostics have something to find. It is made up; the page labels results from it as synthetic.
"""

from __future__ import annotations

import io
import random
from datetime import datetime, timedelta

SYMBOLS = {
    "RELIANCE": 1250.0,
    "TCS": 3500.0,
    "INFY": 1500.0,
    "ITC": 420.0,
    "SBIN": 780.0,
    "HDFCBANK": 1650.0,
}
COLUMNS = "symbol,isin,trade_date,exchange,segment,series,trade_type,auction,quantity,price,trade_id,order_id,order_execution_time"


def sample_tradebook_csv(seed: int = 7, months: int = 6) -> str:
    rng = random.Random(seed)
    prices = dict(SYMBOLS)
    rows: list[tuple[datetime, str, str, int, float]] = []
    day = datetime(2026, 4, 1, 9, 30)
    end = day + timedelta(days=30 * months)
    while day < end:
        if day.weekday() < 5:
            for sym in prices:  # a drifting random walk per symbol
                prices[sym] *= 1 + rng.gauss(0.0004, 0.012)
            for sym in rng.sample(list(prices), k=rng.choice([1, 1, 2, 3])):
                qty = rng.choice([10, 20, 25, 50])
                entry = round(prices[sym] * (1 + rng.uniform(-0.004, 0.004)), 2)
                t_in = day.replace(hour=rng.randint(9, 13), minute=rng.randint(0, 59))
                win = rng.random() < 0.55
                if rng.random() < 0.35:  # intraday: out the same afternoon
                    move = rng.uniform(0.004, 0.015) * (1 if win else -1)
                    t_out = t_in + timedelta(hours=rng.randint(1, 4))
                else:  # swing: losers are held much longer than winners
                    hold = rng.randint(1, 6) if win else rng.randint(8, 30)
                    move = rng.uniform(0.02, 0.07) * (1 if win else -1)
                    t_out = t_in + timedelta(days=hold)
                    while t_out.weekday() >= 5:
                        t_out += timedelta(days=1)
                exit_price = round(entry * (1 + move), 2)
                rows.append((t_in, sym, "buy", qty, entry))
                rows.append((t_out, sym, "sell", qty, exit_price))
        day += timedelta(days=1)
    rows.sort(key=lambda r: r[0])
    out = io.StringIO()
    out.write(COLUMNS + "\n")
    for i, (ts, sym, side, qty, price) in enumerate(rows, start=1):
        out.write(
            f"{sym},INE000A01000,{ts:%Y-%m-%d},NSE,EQ,EQ,{side},false,{qty},{price},{9000 + i},{7000 + i},{ts:%Y-%m-%dT%H:%M:%S}\n"
        )
    return out.getvalue()
