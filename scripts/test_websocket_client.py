"""
Standalone WebSocket Client Verification Script.

Usage:
  1. Start the FastAPI server first in one terminal:
     .venv\Scripts\python.exe -m uvicorn aletheia.core.main:app --port 8899
  2. Run this script in another terminal:
     .venv\Scripts\python.exe scripts/test_websocket_client.py
"""

from __future__ import annotations

import asyncio
import json
import httpx
import websockets
from rich.console import Console
from rich.panel import Panel

console = Console()


async def run_client():
    backend_url = "http://127.0.0.1:8900"
    ws_url = "ws://127.0.0.1:8900"

    console.print(
        Panel(
            "[bold cyan]Aletheia WebSocket Verification Client[/bold cyan]\n"
            "[dim]Verifies REST run spawning, DB event logging, and WS progress streaming.[/dim]",
            border_style="cyan",
        )
    )

    # 1. Trigger run in background
    console.print("[bold yellow]1. Spawning background run via POST /api/v1/runs...[/bold yellow]")
    payload = {
        "prompt": "Run comprehensive analysis on RELIANCE and BTC/USDT",
        "portfolio": {
            "name": "VerificationPortfolio",
            "base_currency": "INR",
            "holdings": [
                {
                    "symbol": "RELIANCE",
                    "quantity": 10,
                    "average_price": 2900,
                    "asset_type": "equity",
                    "exchange": "NSE",
                    "tax_profile": "equity",
                },
                {
                    "symbol": "BTC/USDT",
                    "quantity": 0.5,
                    "average_price": 65000,
                    "asset_type": "crypto",
                    "exchange": "BINANCE",
                    "tax_profile": "crypto",
                },
            ],
        },
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{backend_url}/api/v1/runs?background=true",
                json=payload,
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()
            run_id = data["summary"]["run_id"]
            console.print(
                f"[green][OK] Run successfully spawned! Run ID: [bold]{run_id}[/bold][/green]\n"
            )
    except Exception as exc:
        console.print(
            f"[bold red][ERROR] Failed to spawn run. Make sure the server is running on port 8899. Error: {exc}[/bold red]"
        )
        return

    # 2. Connect via WebSockets and stream events
    socket_uri = f"{ws_url}/api/v1/ws/runs/{run_id}"
    console.print(
        f"[bold yellow]2. Connecting to WebSocket endpoint: {socket_uri}...[/bold yellow]"
    )

    try:
        async with websockets.connect(socket_uri) as ws:
            console.print(
                "[green][OK] WebSocket Connection Established! Listening for agent progress...[/green]\n"
            )

            while True:
                try:
                    message = await ws.recv()
                    event = json.loads(message)

                    # Handle stream completion
                    if event.get("message") == "stream_complete":
                        console.print(
                            "\n[bold green][OK] Received 'stream_complete' signal. Closing connection.[/bold green]"
                        )
                        break

                    # Format and print agent events
                    agent = event.get("agent", "system")
                    msg_text = event.get("message", "")
                    timestamp = event.get("timestamp", "")
                    payload_data = event.get("payload")

                    status_indicator = "*"
                    if payload_data:
                        status_indicator = "+"

                    color = "magenta"
                    if agent == "collector":
                        color = "blue"
                    elif agent == "oracle":
                        color = "cyan"
                    elif agent == "sentinel":
                        color = "red"
                    elif agent == "sage":
                        color = "yellow"
                    elif agent == "scribe":
                        color = "green"

                    console.print(
                        f"[{timestamp}] [bold {color}]{agent.upper():<10}[/bold {color}] "
                        f"{status_indicator} {msg_text}"
                    )
                    if payload_data:
                        # Print truncated payload for readability
                        payload_str = json.dumps(payload_data)
                        if len(payload_str) > 100:
                            payload_str = payload_str[:97] + "..."
                        console.print(f"           [dim]Payload: {payload_str}[/dim]")
                except websockets.ConnectionClosed:
                    console.print("[yellow]! WebSocket connection closed by server.[/yellow]")
                    break
    except Exception as exc:
        console.print(f"[bold red][ERROR] WebSocket connection failed: {exc}[/bold red]")


if __name__ == "__main__":
    asyncio.run(run_client())
