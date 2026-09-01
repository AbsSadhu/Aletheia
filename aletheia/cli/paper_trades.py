"""
Paper Trades CLI subcommand.

Commands:
    aletheia paper-trades show      — tabulated recent trades
    aletheia paper-trades positions — open positions
    aletheia paper-trades settle    — settle trades with actual closes
    aletheia paper-trades summary   — summary statistics (PnL, win rate)
"""

from __future__ import annotations

from datetime import UTC, datetime, date, timedelta
from typing import Optional
import asyncio

import typer
from rich.console import Console
from rich.table import Table
from rich import box

app = typer.Typer(
    name="paper-trades",
    help="Paper trading history and settlement commands.",
    no_args_is_help=True,
)
console = Console()


def _get_paper_trader():
    from aletheia.core.api.dependencies import get_paper_trader
    return get_paper_trader()


@app.command(name="show")
def show_trades(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of trades to show"),
):
    """Show recent paper trading history."""
    trader = _get_paper_trader()
    trades = trader.list_trades(limit=limit)

    if not trades:
        console.print("[yellow]No paper trades recorded yet.[/yellow]")
        return

    table = Table(
        title=f"[bold cyan]Paper Trading History (last {len(trades)})[/bold cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Trade ID", style="dim", max_width=14)
    table.add_column("Symbol", style="bold white")
    table.add_column("Side", justify="center")
    table.add_column("Qty", justify="right")
    table.add_column("Fill Price", justify="right")
    table.add_column("Actual Close", justify="right")
    table.add_column("P&L", justify="right")
    table.add_column("Status")
    table.add_column("Timestamp", style="dim")

    for trade in trades:
        side_style = "[bold green]BUY[/bold green]" if trade.side == "BUY" else "[bold red]SELL[/bold red]"
        pnl = trade.simulated_pnl
        pnl_style = f"[green]+{pnl:.2f}[/green]" if pnl > 0 else (
            f"[red]{pnl:.2f}[/red]" if pnl < 0 else f"[dim]{pnl:.2f}[/dim]"
        )
        actual = getattr(trade, "actual_close", None)
        actual_str = f"{actual:.2f}" if actual is not None else "[dim]–[/dim]"

        table.add_row(
            trade.trade_id[:12] + "…",
            trade.symbol,
            side_style,
            f"{trade.simulated_qty:.0f}",
            f"₹{trade.simulated_fill_price:.2f}",
            actual_str,
            pnl_style,
            getattr(trade, "status", "filled"),
            trade.timestamp.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)


@app.command(name="positions")
def show_positions():
    """Show currently open paper positions."""
    trader = _get_paper_trader()
    positions = trader.list_positions()

    if not positions:
        console.print("[yellow]No open paper positions.[/yellow]")
        return

    table = Table(
        title="[bold cyan]Open Paper Positions[/bold cyan]",
        box=box.ROUNDED,
        header_style="bold magenta",
    )
    table.add_column("Symbol", style="bold white")
    table.add_column("Exchange", style="dim")
    table.add_column("Qty", justify="right")
    table.add_column("Avg Price", justify="right")
    table.add_column("Realized P&L", justify="right")
    table.add_column("Updated")

    for pos in positions:
        rpnl = pos.realized_pnl
        rpnl_str = f"[green]+{rpnl:.2f}[/green]" if rpnl > 0 else (
            f"[red]{rpnl:.2f}[/red]" if rpnl < 0 else f"{rpnl:.2f}"
        )
        table.add_row(
            pos.symbol,
            pos.exchange,
            f"{pos.quantity:.2f}",
            f"₹{pos.average_price:.2f}",
            rpnl_str,
            pos.updated_at.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)
    console.print(f"\n[dim]Total positions: {len(positions)}[/dim]")


@app.command(name="settle")
def settle_trades(
    trade_date: Optional[str] = typer.Option(
        None, "--date", "-d",
        help="Date to settle trades (YYYY-MM-DD). Defaults to yesterday.",
    ),
):
    """
    Fetch actual closing prices and settle paper trades.

    Looks up actual market closes for the given date and computes
    realized P&L for all trades that were filled on that date.
    """
    if trade_date is None:
        settle_date = (datetime.now(UTC) - timedelta(days=1)).date()
    else:
        try:
            settle_date = date.fromisoformat(trade_date)
        except ValueError:
            console.print(f"[red]Invalid date format: {trade_date}. Use YYYY-MM-DD.[/red]")
            raise typer.Exit(code=1)

    trader = _get_paper_trader()
    trades = trader.list_trades(limit=200)
    date_str = settle_date.isoformat()

    to_settle = [
        t for t in trades
        if t.timestamp.date() <= settle_date and t.side == "BUY"
        and getattr(t, "actual_close", None) is None
    ]

    if not to_settle:
        console.print(f"[yellow]No unsettled trades found for {date_str}.[/yellow]")
        return

    console.print(f"[bold blue]Settling {len(to_settle)} trade(s) for {date_str}...[/bold blue]")

    settled = 0
    for trade in to_settle:
        try:
            actual_close = asyncio.run(
                _fetch_close_price(trader, trade.symbol, trade.exchange)
            )
            if actual_close is not None:
                asyncio.run(trader.settle_trade(trade.trade_id, actual_close))
                pnl = (actual_close - trade.simulated_fill_price) * trade.simulated_qty
                pnl_str = f"[green]+{pnl:.2f}[/green]" if pnl > 0 else f"[red]{pnl:.2f}[/red]"
                console.print(
                    f"  {trade.symbol}: fill=₹{trade.simulated_fill_price:.2f} "
                    f"close=₹{actual_close:.2f} P&L={pnl_str}"
                )
                settled += 1
        except Exception as exc:
            console.print(f"  [yellow]Could not settle {trade.symbol}: {exc}[/yellow]")

    console.print(f"\n[bold green]✓ Settled {settled}/{len(to_settle)} trades.[/bold green]")


@app.command(name="summary")
def summary():
    """Show aggregate paper trading statistics."""
    trader = _get_paper_trader()
    trades = trader.list_trades(limit=500)

    if not trades:
        console.print("[yellow]No trades to summarize.[/yellow]")
        return

    sell_trades = [t for t in trades if t.side == "SELL"]
    total_pnl = sum(t.simulated_pnl for t in sell_trades)
    wins = sum(1 for t in sell_trades if t.simulated_pnl > 0)
    losses = sum(1 for t in sell_trades if t.simulated_pnl < 0)
    win_rate = wins / len(sell_trades) * 100 if sell_trades else 0.0
    gross_profit = sum(t.simulated_pnl for t in sell_trades if t.simulated_pnl > 0)
    gross_loss = abs(sum(t.simulated_pnl for t in sell_trades if t.simulated_pnl < 0))
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    console.print("\n[bold cyan]📊 Paper Trading Summary[/bold cyan]")
    console.print(f"  Total trades:     {len(trades)}")
    console.print(f"  Closed trades:    {len(sell_trades)}")
    pnl_colored = f"[green]+₹{total_pnl:.2f}[/green]" if total_pnl >= 0 else f"[red]₹{total_pnl:.2f}[/red]"
    console.print(f"  Total P&L:        {pnl_colored}")
    console.print(f"  Win rate:         {win_rate:.1f}% ({wins}W / {losses}L)")
    console.print(f"  Profit factor:    {pf:.2f}")
    console.print(f"  Gross profit:     [green]₹{gross_profit:.2f}[/green]")
    console.print(f"  Gross loss:       [red]₹{gross_loss:.2f}[/red]")


async def _fetch_close_price(trader, symbol: str, exchange: str) -> float | None:
    from aletheia.core.marketdata.models import MarketDataRequest
    try:
        quote = await trader.market_data.get_quote(
            MarketDataRequest(symbol=symbol, exchange=exchange)
        )
        return quote.close
    except Exception:
        return None
