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
    console.print(f"[bold blue]Starting Aletheia Analysis Pipeline[/bold blue]")
    console.print(f"Target: [bold green]{symbol}[/bold green]")
    console.print(f"Provider: [yellow]{provider}[/yellow]")
    
    # We will wire up the actual orchestration engine here
    console.print("\n[dim]Analysis complete. Agent orchestration to be wired.[/dim]")

@app.command()
def info():
    """
    Display framework information and loaded extensions.
    """
    console.print("[bold cyan]Aletheia Framework v0.1.0[/bold cyan]")
    console.print("Architecture: Terminal-First / Agentic")
    console.print("\nLoaded Extensions:")
    console.print("- Providers: [green]ccxt[/green], [green]yfinance[/green], [green]static_seed[/green]")
    console.print("- Agents: [blue]collector[/blue], [blue]oracle[/blue], [blue]sentinel[/blue], [blue]sage[/blue], [blue]scribe[/blue]")

if __name__ == "__main__":
    app()
