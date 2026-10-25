"""NSE/BSE cash-market session, from weekday and clock only.

Exchange holidays are NOT known here, so on a holiday this reports "open" during normal hours
even though no ticks arrive. Callers should present that as "no data" rather than an outage.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta

_IST = timedelta(hours=5, minutes=30)
PRE_OPEN = time(9, 0)
OPEN = time(9, 15)
CLOSE = time(15, 30)


def market_status(now: datetime | None = None) -> dict[str, str | bool]:
    now = now or datetime.now(UTC)
    ist = (now if now.tzinfo else now.replace(tzinfo=UTC)).astimezone(UTC) + _IST
    t = ist.time()
    if ist.weekday() >= 5:
        state, label = "closed", "Closed (weekend)"
    elif PRE_OPEN <= t < OPEN:
        state, label = "pre_open", "Pre-open session"
    elif OPEN <= t < CLOSE:
        state, label = "open", "Market open"
    elif t < PRE_OPEN:
        state, label = "closed", "Closed (opens 09:15 IST)"
    else:
        state, label = "closed", "Closed (after 15:30 IST)"
    return {
        "state": state,
        "label": label,
        "is_open": state == "open",
        "ist_time": ist.strftime("%H:%M:%S"),
        "note": "Based on weekday hours only; exchange holidays are not included.",
    }
