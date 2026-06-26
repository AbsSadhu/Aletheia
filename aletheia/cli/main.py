import typer
from rich.console import Console
from aletheia.cli.onboard import run_onboarding

app = typer.Typer(
    name="aletheia",
    help="Aletheia Terminal-First Agentic Trading Framework",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


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
    asyncio.run(_async_run(f"Perform a comprehensive analysis on stock symbol {symbol} using provider {provider}."))


async def _async_run(prompt_text: str) -> None:
    from aletheia.core.config.settings import get_settings
    from aletheia.core.llm.chat_llm import build_llm_router
    from aletheia.core.tools.registry import build_registry
    from aletheia.core.agent.context import AgentContext
    from aletheia.core.agent.loop import ReActLoop
    from rich.markdown import Markdown
    from rich.panel import Panel

    settings = get_settings()
    llm = build_llm_router()
    registry = build_registry()
    context = AgentContext.from_query(prompt_text)
    react = ReActLoop(llm=llm, tool_registry=registry)

    async for event in react.run(prompt_text, context):
        if event.type == "thought":
            console.print(f"[dim italic]Thought: {event.data.get('content')}[/dim italic]")
        elif event.type == "tool_call":
            args_str = ", ".join(f"{k}={v}" for k, v in event.data.get("arguments", {}).items())
            console.print(f"[bold magenta]➔ Tool Call: {event.data.get('tool')}({args_str})[/bold magenta]")
        elif event.type == "tool_result":
            res = str(event.data.get("result"))
            if len(res) > 300:
                res = res[:297] + "..."
            console.print(f"[bold green]✔ Tool Result: {event.data.get('tool')} -> {res}[/bold green]\n")
        elif event.type == "error":
            console.print(f"[bold red]✖ Error: {event.data.get('message')}[/bold red]")
        elif event.type == "final_answer":
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
    symbol: str = typer.Option(..., "--symbol", "-s", help="The symbol name to assign to the imported data"),
    path: str = typer.Option(..., "--file", "-f", help="Path to the CSV, Parquet, or DuckDB file"),
    date_format: str = typer.Option(None, "--date-format", "-d", help="Optional date parsing format, e.g. %Y-%m-%d"),
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
        console.print(f"[bold green]✔ Successfully imported {rows} rows![/bold green]")
    except Exception as exc:
        console.print(f"[bold red]✖ Import failed: {exc}[/bold red]")


@app.command()
def info():
    """
    Display framework information and loaded extensions.
    """
    console.print("[bold cyan]Aletheia Framework v0.1.0[/bold cyan]")
    console.print("Architecture: Terminal-First / Agentic")
    console.print("\nLoaded Extensions:")
    console.print(
        "- Providers: [green]ccxt[/green], [green]yfinance[/green], [green]static_seed[/green]"
    )
    console.print(
        "- Agents: [blue]collector[/blue], [blue]oracle[/blue], [blue]sentinel[/blue], [blue]sage[/blue], [blue]scribe[/blue]"
    )


if __name__ == "__main__":
    app()

