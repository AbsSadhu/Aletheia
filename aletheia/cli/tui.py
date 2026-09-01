"""
aletheia tui — terminal dashboard for the Aletheia backend.

A Textual app covering a deliberate subset of the React GUI: view
portfolios, trigger an analysis run and watch the agent pipeline stream
live, review paper trades, and browse recent runs. Talks to the same
FastAPI backend the desktop app uses (REST via httpx, live events via the
`/api/v1/ws/runs/{run_id}` WebSocket) — it does not spawn or embed a
backend itself, matching `aletheia serve`/the desktop app's process model.
"""

from __future__ import annotations

import json
from typing import Any

PIPELINE_AGENTS = ["collector", "oracle", "sentinel", "sage", "scribe", "critic"]

# ASCII-only: Windows terminals not running in UTF-8 mode (the default
# `cp1252` console codepage) raise UnicodeEncodeError on box-drawing/emoji
# glyphs and crash the whole app — verified via a headless run_test().
STATUS_GLYPH = {
    "pending": "o",
    "running": "*",
    "completed": "v",
    "done": "v",
    "failed": "x",
    "skipped": "-",
}


def _fmt_status(status: str | None) -> str:
    glyph = STATUS_GLYPH.get((status or "pending").lower(), "o")
    return glyph


def run_tui(base_url: str | None, api_key: str) -> None:
    """Launch the Aletheia terminal dashboard. Called from `cli/main.py`'s `tui` command."""
    from aletheia.core.config.settings import get_settings

    settings = get_settings()
    resolved_url = base_url or f"http://{settings.host}:{settings.port}"

    tui_app = AletheiaApp(base_url=resolved_url, api_key=api_key)
    tui_app.run()


# ---------------------------------------------------------------------------
# Textual app (imports deferred to module scope only when this file is
# actually imported, which only happens on `aletheia tui`)
# ---------------------------------------------------------------------------

from textual.app import App, ComposeResult  # noqa: E402
from textual.containers import Horizontal, VerticalScroll  # noqa: E402
from textual.widgets import (  # noqa: E402
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)
from textual.reactive import reactive  # noqa: E402


class BackendClient:
    """Thin async REST client — mirrors frontend/src/lib/api.ts's shape."""

    def __init__(self, base_url: str, api_key: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key} if self.api_key else {}

    async def get(self, path: str, **params: Any) -> Any:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self.base_url}{path}", headers=self._headers(), params=params)
            resp.raise_for_status()
            return resp.json()

    async def post(self, path: str, json_body: dict | None = None, **params: Any) -> Any:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{self.base_url}{path}", headers=self._headers(), params=params, json=json_body or {}
            )
            resp.raise_for_status()
            return resp.json()

    def ws_url(self, run_id: str) -> str:
        ws_base = self.base_url.replace("http://", "ws://").replace("https://", "wss://")
        qs = f"?api_key={self.api_key}" if self.api_key else ""
        return f"{ws_base}/api/v1/ws/runs/{run_id}{qs}"


class PipelineStrip(Static):
    """Horizontal row of agent-status glyphs, e.g. collector✓ oracle✓ sentinel● sage○ ..."""

    statuses: reactive[dict[str, str]] = reactive(dict)

    def render(self) -> str:
        parts = []
        for agent in PIPELINE_AGENTS:
            glyph = _fmt_status(self.statuses.get(agent))
            parts.append(f"{agent} {glyph}")
        return "  ->  ".join(parts)


class PortfolioTab(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Label("Portfolios", classes="tab-title")
        yield DataTable(id="portfolio-table")
        yield Label("", id="portfolio-status")

    async def on_mount(self) -> None:
        table = self.query_one("#portfolio-table", DataTable)
        table.add_columns("Portfolio", "Symbol", "Qty", "Avg Price", "Exchange")
        await self.refresh_data()

    async def refresh_data(self) -> None:
        app: AletheiaApp = self.app  # type: ignore[assignment]
        table = self.query_one("#portfolio-table", DataTable)
        table.clear()
        status = self.query_one("#portfolio-status", Label)
        try:
            data = await app.client.get("/api/v1/portfolios")
            portfolios = data.get("portfolios", [])
            for p in portfolios:
                for h in p.get("holdings", []):
                    table.add_row(
                        p["name"], h["symbol"], str(h["quantity"]),
                        f"{h['average_price']:.2f}", h.get("exchange", "-"),
                    )
            status.update(f"{len(portfolios)} portfolio(s) loaded.")
        except Exception as exc:
            status.update(f"[red]Failed to load portfolios: {exc}[/red]")


class RunTab(VerticalScroll):
    current_run_id: reactive[str | None] = reactive(None)

    def compose(self) -> ComposeResult:
        yield Label("Trigger / Watch a Run", classes="tab-title")
        with Horizontal(id="run-controls"):
            yield Input(placeholder="Prompt, e.g. Analyze RELIANCE", id="run-prompt")
            yield Button("Start Run", id="start-run", variant="primary")
        yield PipelineStrip(id="pipeline-strip")
        yield RichLog(id="run-log", wrap=True, highlight=True, markup=True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "start-run":
            self.run_worker(self.start_run(), exclusive=True, group="run")

    async def start_run(self) -> None:
        app: AletheiaApp = self.app  # type: ignore[assignment]
        prompt_input = self.query_one("#run-prompt", Input)
        log = self.query_one("#run-log", RichLog)
        strip = self.query_one("#pipeline-strip", PipelineStrip)
        prompt = prompt_input.value.strip() or "Analyze an India-first starter portfolio"

        log.clear()
        strip.statuses = {}
        log.write(f"[bold cyan]Submitting run:[/bold cyan] {prompt}")

        try:
            result = await app.client.post("/api/v1/runs", json_body={"prompt": prompt}, background=True)
        except Exception as exc:
            log.write(f"[red]Failed to submit run: {exc}[/red]")
            return

        run_id = result.get("summary", {}).get("run_id")
        if not run_id:
            log.write("[red]No run_id returned.[/red]")
            return

        self.current_run_id = run_id
        log.write(f"[dim]run_id={run_id} - streaming live events...[/dim]")
        await self.watch_run(run_id)

    async def watch_run(self, run_id: str) -> None:
        import websockets

        app: AletheiaApp = self.app  # type: ignore[assignment]
        log = self.query_one("#run-log", RichLog)
        strip = self.query_one("#pipeline-strip", PipelineStrip)
        url = app.client.ws_url(run_id)

        try:
            async with websockets.connect(url) as ws:
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("message") == "stream_complete":
                        log.write("[bold green]Run complete.[/bold green]")
                        return
                    agent = msg.get("agent", "?")
                    text = msg.get("message", "")
                    ts = msg.get("timestamp", "")[:19]
                    log.write(f"[dim]{ts}[/dim] [bold]{agent}[/bold]: {text}")
                    statuses = dict(strip.statuses)
                    statuses[agent] = "completed"
                    strip.statuses = statuses
        except Exception as exc:
            log.write(f"[red]WebSocket stream ended: {exc}[/red]")

    def load_existing_run(self, run_id: str) -> None:
        """Called from RecentRunsTab to replay a past run's events."""
        self.current_run_id = run_id
        log = self.query_one("#run-log", RichLog)
        log.clear()
        log.write(f"[dim]Replaying run {run_id}...[/dim]")
        self.run_worker(self.watch_run(run_id), exclusive=True, group="run")


class PaperTradesTab(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Label("Paper Trades", classes="tab-title")
        yield DataTable(id="trades-table")
        yield Label("Open Positions", classes="tab-title")
        yield DataTable(id="positions-table")

    async def on_mount(self) -> None:
        trades = self.query_one("#trades-table", DataTable)
        trades.add_columns("Symbol", "Side", "Qty", "Fill Price", "P&L", "Status")
        positions = self.query_one("#positions-table", DataTable)
        positions.add_columns("Symbol", "Exchange", "Qty", "Avg Price", "Realized P&L")
        await self.refresh_data()

    async def refresh_data(self) -> None:
        app: AletheiaApp = self.app  # type: ignore[assignment]
        trades_table = self.query_one("#trades-table", DataTable)
        positions_table = self.query_one("#positions-table", DataTable)
        trades_table.clear()
        positions_table.clear()
        try:
            trades = await app.client.get("/api/v1/execution/paper-trades", limit=30)
            for t in trades.get("trades", []):
                trades_table.add_row(
                    t["symbol"], t["side"], f"{t['simulated_qty']:.0f}",
                    f"{t['simulated_fill_price']:.2f}", f"{t['simulated_pnl']:.2f}",
                    t.get("status", "filled"),
                )
        except Exception as exc:
            trades_table.add_row(f"[red]error: {exc}[/red]", "-", "-", "-", "-", "-")

        try:
            positions = await app.client.get("/api/v1/execution/positions")
            for p in positions.get("positions", []):
                positions_table.add_row(
                    p["symbol"], p["exchange"], f"{p['quantity']:.2f}",
                    f"{p['average_price']:.2f}", f"{p['realized_pnl']:.2f}",
                )
        except Exception as exc:
            positions_table.add_row(f"[red]error: {exc}[/red]", "-", "-", "-", "-")


class RecentRunsTab(VerticalScroll):
    def compose(self) -> ComposeResult:
        yield Label("Recent Runs (Enter to replay in the Run tab)", classes="tab-title")
        yield DataTable(id="runs-table")

    async def on_mount(self) -> None:
        table = self.query_one("#runs-table", DataTable)
        table.add_columns("Run ID", "Status", "Prompt", "Created")
        table.cursor_type = "row"
        await self.refresh_data()

    async def refresh_data(self) -> None:
        app: AletheiaApp = self.app  # type: ignore[assignment]
        table = self.query_one("#runs-table", DataTable)
        table.clear()
        try:
            data = await app.client.get("/api/v1/runs", limit=20)
            for r in data.get("runs", []):
                table.add_row(
                    r["run_id"][:12] + "...", r["status"], r["prompt"][:50], r["created_at"][:19],
                    key=r["run_id"],
                )
        except Exception as exc:
            table.add_row(f"[red]error: {exc}[/red]", "-", "-", "-")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        run_id = event.row_key.value
        if not run_id:
            return
        app: AletheiaApp = self.app  # type: ignore[assignment]
        run_tab = app.query_one(RunTab)
        app.query_one(TabbedContent).active = "tab-run"
        run_tab.load_existing_run(run_id)


class AletheiaApp(App):
    """Aletheia terminal dashboard."""

    CSS = """
    .tab-title { text-style: bold; color: cyan; margin-top: 1; }
    #run-controls { height: 3; }
    #run-prompt { width: 1fr; }
    #pipeline-strip { height: 1; margin: 1 0; color: yellow; }
    #run-log { height: 1fr; border: solid gray; }
    DataTable { height: auto; max-height: 12; margin-bottom: 1; }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh_active", "Refresh"),
    ]

    backend_status: reactive[str] = reactive("checking...")

    def __init__(self, base_url: str = "http://127.0.0.1:8899", api_key: str = "") -> None:
        super().__init__()
        self.client = BackendClient(base_url, api_key)

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="tab-portfolio"):
            with TabPane("Portfolio", id="tab-portfolio"):
                yield PortfolioTab()
            with TabPane("Run", id="tab-run"):
                yield RunTab()
            with TabPane("Paper Trades", id="tab-paper"):
                yield PaperTradesTab()
            with TabPane("Recent Runs", id="tab-recent"):
                yield RecentRunsTab()
        yield Footer()

    async def on_mount(self) -> None:
        self.set_interval(15.0, self.check_backend)
        await self.check_backend()

    async def check_backend(self) -> None:
        try:
            await self.client.get("/api/v1/health")
            self.sub_title = f"[online] backend at {self.client.base_url}"
        except Exception:
            self.sub_title = f"[OFFLINE] backend at {self.client.base_url}"

    async def action_refresh_active(self) -> None:
        tabs = self.query_one(TabbedContent)
        active_id = tabs.active
        for tab_cls, tab_id in (
            (PortfolioTab, "tab-portfolio"),
            (PaperTradesTab, "tab-paper"),
            (RecentRunsTab, "tab-recent"),
        ):
            if active_id == tab_id:
                widget = self.query_one(tab_cls)
                await widget.refresh_data()
