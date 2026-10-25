"""Runs Fyers' official data WebSocket SDK in its own process and relays ticks as JSON lines.

WHY A SEPARATE PROCESS: Fyers' binary stream protocol (their "HSM" feed) is implemented by their
`fyers-apiv3` SDK. Re-implementing it here without a live account to test against risks decoding
prices wrongly, so we use the official decoder. But that SDK drags in boto3 and AWS packages and
pins older `requests`/`aiohttp`, which would break the main app. So it lives in its own virtualenv
(`scripts/fyers_setup.py` creates it) and this file runs under THAT interpreter.

This module must stay standalone: standard library + `fyers_apiv3` only, no `aletheia` imports.

Protocol (one JSON object per line)
  stdin  -> {"cmd": "start", "token": "APPID:ACCESS_TOKEN", "symbols": ["NSE:SBIN-EQ"], "log_dir": "..."}
            {"cmd": "set",  "symbols": [...]}        replace the subscribed symbols
            {"cmd": "stop"}                          (or close stdin) shut down
  stdout <- {"ev": "connected"} | {"ev": "tick", "data": {...}} | {"ev": "info", "data": {...}}
            {"ev": "error", "data": ...} | {"ev": "closed", "data": ...} | {"ev": "fatal", "message": "..."}

The access token arrives on stdin, never argv, so it doesn't show up in process listings.
"""

from __future__ import annotations

import json
import os
import sys
import threading

DATA_TYPE = "SymbolUpdate"


def main() -> int:
    proto = sys.stdout
    sys.stdout = sys.stderr  # anything the SDK print()s must not corrupt the protocol stream
    lock = threading.Lock()

    def emit(ev: str, **fields: object) -> None:
        with lock:
            proto.write(json.dumps({"ev": ev, **fields}, default=str) + "\n")
            proto.flush()

    try:
        from fyers_apiv3.FyersWebsocket import data_ws  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001
        emit("fatal", message=f"fyers_apiv3 is not installed in this environment: {exc}")
        return 2

    first = sys.stdin.readline()
    try:
        start = json.loads(first)
        assert start.get("cmd") == "start" and start.get("token")
    except Exception:  # noqa: BLE001
        emit("fatal", message="first stdin line must be a 'start' command with a token")
        return 2

    state: dict[str, list[str]] = {"symbols": list(start.get("symbols") or []), "subscribed": []}
    auth = {"failed": False}
    sock_ref: dict[str, object] = {}

    def resubscribe(new: list[str]) -> None:
        sock = sock_ref["sock"]
        old = state["subscribed"]
        # The SDK tracks one subscription set per channel, so change it as their docs advise:
        # unsubscribe the old list, then subscribe the new one.
        if old:
            sock.unsubscribe(symbols=old, data_type=DATA_TYPE)  # type: ignore[attr-defined]
        if new:
            sock.subscribe(symbols=new, data_type=DATA_TYPE)  # type: ignore[attr-defined]
        state["subscribed"] = list(new)

    def on_message(msg: object) -> None:
        if isinstance(msg, dict) and msg.get("ltp") is not None:
            emit("tick", data=msg)
        else:
            emit("info", data=msg)  # connection / subscription acknowledgements

    def on_error(msg: object) -> None:
        if isinstance(msg, dict) and msg.get("type") == "cn":
            auth["failed"] = True  # login failed; the SDK still calls on_connect afterwards
        emit("error", data=msg)

    def on_close(msg: object) -> None:
        emit("closed", data=msg)

    def on_open() -> None:
        emit("connected")
        if auth["failed"]:
            return  # nothing to subscribe to without a valid login
        try:
            resubscribe(list(state["symbols"]))
        except Exception as exc:  # noqa: BLE001
            emit("error", data=f"subscribe failed: {exc}")

    sock = data_ws.FyersDataSocket(
        access_token=start["token"],
        log_path=start.get("log_dir") or "",
        litemode=False,
        write_to_file=False,
        reconnect=True,
        on_connect=on_open,
        on_close=on_close,
        on_error=on_error,
        on_message=on_message,
    )
    sock_ref["sock"] = sock
    try:
        sock.connect()  # starts the SDK's own threads, then calls on_open
    except Exception as exc:  # noqa: BLE001
        emit("fatal", message=f"connect failed: {exc}")
        return 3

    for line in sys.stdin:  # blocks; EOF means the parent died, so we shut down too
        try:
            cmd = json.loads(line)
        except ValueError:
            continue
        if cmd.get("cmd") == "set":
            state["symbols"] = list(cmd.get("symbols") or [])
            try:
                resubscribe(state["symbols"])
            except Exception as exc:  # noqa: BLE001
                emit("error", data=f"resubscribe failed: {exc}")
        elif cmd.get("cmd") == "stop":
            break

    try:
        sock.close_connection()
    except Exception:  # noqa: BLE001
        pass
    proto.flush()
    os._exit(0)  # the SDK leaves non-daemon threads running; don't wait for them


if __name__ == "__main__":
    sys.exit(main())
