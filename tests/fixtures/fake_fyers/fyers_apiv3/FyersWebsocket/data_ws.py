"""Stand-in for Fyers' fyers_apiv3 data socket, used ONLY by tests of fyers_bridge.py.

It mimics the parts of the real SDK's behaviour the bridge relies on: callbacks passed to the
constructor, connect() blocking briefly then calling on_connect, subscribe()/unsubscribe() taking
symbol lists, ticks delivered on a background thread, and (importantly) the real SDK's habit of
print()ing to stdout, which must not corrupt the bridge's protocol stream.
"""

from __future__ import annotations

import threading
import time


class FyersDataSocket:
    def __init__(
        self,
        access_token,
        log_path=None,
        litemode=False,
        write_to_file=False,
        reconnect=True,
        on_message=None,
        on_error=None,
        on_connect=None,
        on_close=None,
        **_ignored,
    ):
        self.token = access_token
        self.on_message, self.on_error = on_message, on_error
        self.on_connect, self.on_close = on_connect, on_close
        self._subs: set[str] = set()
        self._closed = False

    def connect(self):
        print("SDK banner: connecting...")  # real SDK prints; must not reach the protocol stream
        if self.token.endswith(":EXPIRED"):
            self.on_error({"type": "cn", "code": -99, "message": "Token is expired", "s": "error"})
            self.on_connect()  # the real SDK still calls on_connect after a failed login
            return
        if self.token.endswith(":INVALID"):  # what the real SDK sent for a bad token (observed)
            self.on_error(
                {"type": "cn", "code": -300, "message": "Please provide valid token", "s": "error"}
            )
            self.on_connect()
            return
        if self.token.endswith(":REJECTED"):
            self.on_error(
                {"type": "cn", "code": 11001, "message": "Authentication failed", "s": "error"}
            )
            self.on_connect()
            return
        if self.token.endswith(":CRASH"):
            raise SystemExit(7)
        time.sleep(0.05)
        self.on_connect()
        self.on_message(
            {"type": "cn", "code": 200, "message": "Authentication done", "s": "ok"}
        )  # real SDK's success ack
        threading.Thread(target=self._pump, daemon=True).start()

    def subscribe(self, symbols, data_type="SymbolUpdate", channel=11):
        print(f"SDK noise: subscribe {symbols}")
        self._subs.update(symbols)
        self.on_message({"type": "sub", "code": 200, "message": "Subscribed", "s": "ok"})

    def unsubscribe(self, symbols, data_type="SymbolUpdate", channel=11):
        print(f"SDK noise: unsubscribe {symbols}")
        self._subs.difference_update(symbols)

    def close_connection(self):
        self._closed = True

    def _pump(self):
        n = 0
        while not self._closed:
            n += 1
            for sym in sorted(self._subs):
                self.on_message(
                    {
                        "symbol": sym,
                        "ltp": 1000.0 + n,
                        "open_price": 990.0,
                        "high_price": 1010.0 + n,
                        "low_price": 985.0,
                        "prev_close_price": 1000.0,
                        "ch": n,
                        "chp": round(n / 10, 2),
                        "vol_traded_today": 1000 * n,
                        "last_traded_time": int(time.time()),
                        "type": "sf",
                    }
                )
            time.sleep(0.05)
