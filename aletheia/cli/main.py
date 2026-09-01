import typer
from rich.console import Console
from aletheia.cli.config import app as config_app
from aletheia.cli.onboard import run_onboarding
from aletheia.cli.paper_trades import app as paper_trades_app
from aletheia.cli.benchmark import app as benchmark_app
from aletheia.cli.compare import app as compare_app

app = typer.Typer(
    name="aletheia",
    help="Aletheia Terminal-First Agentic Trading Framework",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
app.add_typer(config_app)
app.add_typer(paper_trades_app)
app.add_typer(benchmark_app)
app.add_typer(compare_app)


@app.command()
def setup():
    """
    Run the interactive setup wizard to configure LLMs and API keys.
    """
    run_onboarding()


@app.command()
def analyze(
    symbol: str = typer.Option(..., "--symbol", "-s", help="The stock symbol to analyze"),
    provider: str = typer.Option("yfinance", "--provider", "-p", help="Data provider to use"),
):
    """
    Run an agentic analysis pipeline on a given symbol.
    """
    console.print("[bold blue]Starting Aletheia Analysis Pipeline[/bold blue]")
    console.print(f"Target: [bold green]{symbol}[/bold green]")
    console.print(f"Provider: [yellow]{provider}[/yellow]")

    # Wire up the actual orchestration engine via our async agent loop
    import asyncio

    asyncio.run(
        _async_run(
            f"Perform a comprehensive analysis on stock symbol {symbol} using provider {provider}."
        )
    )


async def _async_run(prompt_text: str) -> None:
    from aletheia.core.config.settings import get_settings
    from aletheia.core.llm.chat_llm import build_llm_router
    from aletheia.core.tools.registry import build_registry
    from aletheia.core.agent.context import AgentContext
    from aletheia.core.agent.loop import ReActLoop
    from rich.markdown import Markdown
    from rich.panel import Panel

    get_settings()
    llm = build_llm_router()
    registry = build_registry()
    context = AgentContext.from_query(prompt_text)
    react = ReActLoop(llm=llm, tool_registry=registry)

    async for event in react.run(prompt_text, context):
        if event.event_type == "thought":
            console.print(f"[dim italic]Thought: {event.data.get('content')}[/dim italic]")
        elif event.event_type == "tool_call":
            args_str = ", ".join(f"{k}={v}" for k, v in event.data.get("arguments", {}).items())
            console.print(
                f"[bold magenta]-> Tool Call: {event.data.get('tool')}({args_str})[/bold magenta]"
            )
        elif event.event_type == "tool_result":
            res = str(event.data.get("result"))
            if len(res) > 300:
                res = res[:297] + "..."
            console.print(
                f"[bold green][OK] Tool Result: {event.data.get('tool')} -> {res}[/bold green]\n"
            )
        elif event.event_type == "error":
            console.print(f"[bold red][ERROR] Error: {event.data.get('message')}[/bold red]")
        elif event.event_type == "final_answer":
            console.print()
            console.print(
                Panel(
                    Markdown(event.data.get("content", "")),
                    title="[bold green]Final Synthesis[/bold green]",
                    border_style="green",
                )
            )


@app.command(name="run")
def run_prompt(
    prompt: str = typer.Argument(..., help="The natural language query/task to execute"),
):
    """
    Run an agentic task using natural language in the terminal.
    """
    import asyncio

    asyncio.run(_async_run(prompt))


@app.command(name="import-data")
def import_data(
    symbol: str = typer.Option(
        ..., "--symbol", "-s", help="The symbol name to assign to the imported data"
    ),
    path: str = typer.Option(..., "--file", "-f", help="Path to the CSV, Parquet, or DuckDB file"),
    date_format: str = typer.Option(
        None, "--date-format", "-d", help="Optional date parsing format, e.g. %Y-%m-%d"
    ),
    query: str = typer.Option(None, "--query", "-q", help="Optional SQL query for DuckDB files"),
):
    """
    Import local CSV, Parquet, or DuckDB data into Aletheia's unified DuckDB store.
    """
    from aletheia.extensions.backtest.local_importer import import_local_file
    from aletheia.core.config.settings import get_settings

    settings = get_settings()
    console.print(f"[bold blue]Importing {path} as symbol {symbol}...[/bold blue]")
    try:
        rows = import_local_file(
            symbol=symbol,
            file_path=path,
            duckdb_path=str(settings.duckdb_path),
            date_format=date_format,
            query=query,
        )
        console.print(f"[bold green][OK] Successfully imported {rows} rows![/bold green]")
    except Exception as exc:
        console.print(f"[bold red][ERROR] Import failed: {exc}[/bold red]")


@app.command()
def info():
    """
    Display framework information and loaded extensions.
    """
    console.print("[bold cyan]Aletheia Framework v0.1.0[/bold cyan]")
    console.print("Architecture: Terminal-First / Agentic / Multi-Agent")
    console.print("\nLoaded Extensions:")
    console.print(
        "- Providers: [green]ccxt[/green], [green]yfinance[/green], [green]static_seed[/green]"
    )
    console.print(
        "- Agents: [blue]collector[/blue], [blue]oracle[/blue], [blue]sentinel[/blue], [blue]sage[/blue], [blue]scribe[/blue]"
    )
    console.print(
        "- Factors: [magenta]rsi[/magenta], [magenta]macd[/magenta], [magenta]bollinger[/magenta], [magenta]vwap[/magenta], [magenta]obv[/magenta], [magenta]ma_cross[/magenta]"
    )
    console.print(
        "- Execution: [yellow]paper[/yellow], [yellow]live_gate[/yellow], [yellow]portfolio_constraints[/yellow]"
    )


@app.command(name="tui")
def tui_cmd(
    url: str = typer.Option(
        None, "--url", help="Backend base URL (defaults to http://<settings.host>:<settings.port>)"
    ),
    api_key: str = typer.Option(
        "",
        "--api-key",
        envvar="ALETHEIA_TUI_API_KEY",
        help="X-API-Key to send if the backend has ALETHEIA_API_KEYS configured",
    ),
) -> None:
    """
    Launch the terminal dashboard: portfolios, live run streaming, paper
    trades, and recent runs. Connects to an already-running backend
    (start one first with `aletheia serve`, or use the desktop app).
    """
    from aletheia.cli.tui import run_tui

    run_tui(url, api_key)


@app.command(name="mcp")
def mcp_cmd() -> None:
    """
    Start the Aletheia MCP server over stdio, exposing the same tool
    registry the ReAct chat agent uses (market data, backtests, fundamentals,
    news, portfolio analytics, etc.) to any MCP-compatible client (Claude
    Desktop, Cursor). Point the client's MCP config at this command directly
    (e.g. `.venv\\Scripts\\aletheia.cmd mcp`) rather than spawning it manually.
    """
    from aletheia.mcp_server import mcp

    mcp.run()


@app.command(name="serve")
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-H", help="Bind host"),
    port: int = typer.Option(8899, "--port", "-p", help="Bind port"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload (dev mode)"),
):
    """
    Start the Aletheia FastAPI backend server.
    Used by the desktop app as a sidecar process.
    """
    import uvicorn

    console.print(f"[bold blue]Starting Aletheia API on http://{host}:{port}[/bold blue]")
    uvicorn.run(
        "aletheia.core.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


@app.command(name="memory")
def memory_cmd(
    agent: str = typer.Argument(
        "oracle", help="Agent name (oracle, sentinel, sage, collector, scribe)"
    ),
    critique: bool = typer.Option(
        False, "--critique", "-c", help="Show self-critique instead of observations"
    ),
    ticker: str = typer.Option(None, "--ticker", "-t", help="Filter observations by ticker"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of records to show"),
):
    """
    View an agent's working memory observations and self-critiques.
    """
    from aletheia.memory.working_memory import WorkingMemory
    from rich.table import Table
    from rich import box

    wm = WorkingMemory()

    if critique:
        critiques = wm.get_critiques(agent, limit=limit)
        if not critiques:
            console.print(f"[yellow]No critiques found for agent '{agent}'.[/yellow]")
            return
        for c in critiques:
            console.print(
                f"\n[bold cyan]{agent.upper()} Self-Critique — {c['timestamp'][:10]}[/bold cyan]"
            )
            console.print(c["critique"])
        return

    observations = wm.list_all_observations(agent_name=agent, ticker=ticker, limit=limit)
    if not observations:
        console.print(
            f"[yellow]No observations found for agent '{agent}'{' on ' + ticker if ticker else ''}.[/yellow]"
        )
        return

    table = Table(
        title=f"[bold cyan]{agent.upper()} Memory[/bold cyan]",
        box=box.ROUNDED,
        header_style="bold magenta",
    )
    table.add_column("Ticker", style="bold white")
    table.add_column("Confidence", justify="right")
    table.add_column("Observation", max_width=70)
    table.add_column("Run ID", style="dim", max_width=14)
    table.add_column("Timestamp", style="dim")

    for obs in observations:
        conf = obs["confidence"]
        conf_str = (
            f"[green]{conf:.2f}[/green]"
            if conf >= 0.7
            else (f"[yellow]{conf:.2f}[/yellow]" if conf >= 0.5 else f"[red]{conf:.2f}[/red]")
        )
        table.add_row(
            obs["ticker"],
            conf_str,
            obs["observation"][:200],
            (obs["run_id"] or "–")[:12] + "…",
            obs["timestamp"][:16],
        )

    console.print(table)


db_app = typer.Typer(
    name="db",
    help="Database maintenance utilities (backup, restore, prune)",
    no_args_is_help=True,
)
app.add_typer(db_app)


@db_app.command(name="backup")
def db_backup(
    backup_dir: str = typer.Option(
        "./backups", "--dir", "-d", help="Directory where database snapshots will be stored"
    ),
):
    """
    Safely snapshot both SQLite and DuckDB databases.
    """
    import shutil
    import datetime
    import sqlite3
    from pathlib import Path
    from aletheia.core.config.settings import get_settings

    settings = get_settings()
    console.print("[bold blue]Starting Aletheia Database Backup[/bold blue]")

    # Create timestamped folder name
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    target_folder = Path(backup_dir) / f"backup_{timestamp}"

    try:
        target_folder.mkdir(parents=True, exist_ok=True)

        # 1. SQLite Safe Online Backup
        sqlite_src = settings.sqlite_path
        sqlite_dest = target_folder / sqlite_src.name

        console.print(
            f"Backing up SQLite database: [yellow]{sqlite_src}[/yellow] -> [green]{sqlite_dest}[/green]"
        )
        if sqlite_src.exists():
            with sqlite3.connect(sqlite_src) as src_conn:
                with sqlite3.connect(sqlite_dest) as dest_conn:
                    src_conn.backup(dest_conn)
            console.print("[OK] SQLite backup completed successfully.")
        else:
            console.print("[yellow]SQLite file not found; skipping SQLite backup.[/yellow]")

        # 2. DuckDB safe file copy
        duckdb_src = settings.duckdb_path
        duckdb_dest = target_folder / duckdb_src.name

        console.print(
            f"Backing up DuckDB database: [yellow]{duckdb_src}[/yellow] -> [green]{duckdb_dest}[/green]"
        )
        if duckdb_src.exists():
            shutil.copy2(duckdb_src, duckdb_dest)
            console.print("[OK] DuckDB backup completed successfully.")
        else:
            console.print("[yellow]DuckDB file not found; skipping DuckDB backup.[/yellow]")

        console.print(
            f"\n[bold green][OK] Database backup completed! Saved at: {target_folder.resolve()}[/bold green]"
        )

    except Exception as exc:
        console.print(f"[bold red][ERROR] Database backup failed: {exc}[/bold red]")
        raise typer.Exit(code=1)


@db_app.command(name="restore")
def db_restore(
    backup_path: str = typer.Option(
        ..., "--path", "-p", help="Path to the timestamped backup directory"
    ),
):
    """
    Restore SQLite and DuckDB databases from a backup snapshot.
    """
    import shutil
    from pathlib import Path
    from aletheia.core.config.settings import get_settings

    settings = get_settings()
    backup_dir = Path(backup_path)
    console.print(
        f"[bold blue]Restoring Database from Snapshot:[/bold blue] [yellow]{backup_dir.resolve()}[/yellow]"
    )

    if not backup_dir.exists() or not backup_dir.is_dir():
        console.print(f"[bold red][ERROR] Backup directory does not exist: {backup_dir}[/bold red]")
        raise typer.Exit(code=1)

    sqlite_backup = backup_dir / settings.sqlite_path.name
    duckdb_backup = backup_dir / settings.duckdb_path.name

    if not sqlite_backup.exists() and not duckdb_backup.exists():
        console.print("[bold red][ERROR] Backup directory contains no database files.[/bold red]")
        raise typer.Exit(code=1)

    # Perform temporary backup before overwriting (for rollback)
    console.print("Performing rollback safety snapshot of current databases...")
    temp_dir = Path("./data/restore_temp_safety")
    try:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        sqlite_temp = temp_dir / settings.sqlite_path.name
        duckdb_temp = temp_dir / settings.duckdb_path.name

        if settings.sqlite_path.exists():
            shutil.copy2(settings.sqlite_path, sqlite_temp)
        if settings.duckdb_path.exists():
            shutil.copy2(settings.duckdb_path, duckdb_temp)

        # Overwrite active database files
        if sqlite_backup.exists():
            console.print(f"Restoring [green]{settings.sqlite_path}[/green]...")
            settings.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(sqlite_backup, settings.sqlite_path)

        if duckdb_backup.exists():
            console.print(f"Restoring [green]{settings.duckdb_path}[/green]...")
            settings.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(duckdb_backup, settings.duckdb_path)

        # Cleanup temp safety folder
        shutil.rmtree(temp_dir)
        console.print("[bold green][OK] Databases successfully restored![/bold green]")

    except Exception as exc:
        console.print(
            f"[bold red][ERROR] Restore failed! Attempting rollback... Error: {exc}[/bold red]"
        )
        # Rollback
        try:
            if temp_dir.exists():
                if (
                    temp_dir / settings.sqlite_path.name
                ).exists() and settings.sqlite_path.exists():
                    shutil.copy2(temp_dir / settings.sqlite_path.name, settings.sqlite_path)
                if (
                    temp_dir / settings.duckdb_path.name
                ).exists() and settings.duckdb_path.exists():
                    shutil.copy2(temp_dir / settings.duckdb_path.name, settings.duckdb_path)
                shutil.rmtree(temp_dir)
                console.print(
                    "[yellow][OK] Rollback succeeded. Active databases restored to original state.[/yellow]"
                )
        except Exception as roll_exc:
            console.print(
                f"[bold red]CRITICAL: Rollback failed! Original databases might be corrupted. Error: {roll_exc}[/bold red]"
            )
        raise typer.Exit(code=1)


@db_app.command(name="prune")
def db_prune(
    days: int = typer.Option(
        None, "--days", "-d", help="Number of days of data to retain. Overrides .env"
    ),
):
    """
    Manually prune SQLite run traces and DuckDB market quotes.
    """
    from aletheia.core.config.settings import get_settings
    from aletheia.core.db.sqlite_store import SQLiteStore
    from aletheia.core.db.duckdb_store import DuckDBStore

    settings = get_settings()
    retention = days if days is not None else settings.retention_days

    if retention is None or retention <= 0:
        console.print(
            "[bold red][ERROR] Retention days not configured. Specify --days or set ALETHEIA_RETENTION_DAYS in .env[/bold red]"
        )
        raise typer.Exit(code=1)

    console.print("[bold blue]Applying Database Retention Policy[/bold blue]")
    console.print(f"Retaining last [yellow]{retention}[/yellow] days of data...")

    try:
        sqlite_store = SQLiteStore(settings.sqlite_path)
        duckdb_store = DuckDBStore(settings.duckdb_path)

        pruned_events = sqlite_store.prune_old_events(retention)
        pruned_quotes = duckdb_store.prune_old_quotes(retention)

        console.print(f"[OK] SQLite events pruned: [green]{pruned_events}[/green]")
        console.print(f"[OK] DuckDB quotes pruned: [green]{pruned_quotes}[/green]")
        console.print("[bold green][OK] Database pruning completed successfully![/bold green]")
    except Exception as exc:
        console.print(f"[bold red][ERROR] Database pruning failed: {exc}[/bold red]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
