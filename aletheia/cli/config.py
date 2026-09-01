from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from aletheia.config.config_manager import AletheiaConfig, ConfigManager
from aletheia.integrations.validators import (
    ValidationResult,
    validate_frontier_api,
    validate_local_model,
    validate_tradingview,
    validate_zerodha,
)

console = Console()
app = typer.Typer(name="config", help="Manage Aletheia configuration.", no_args_is_help=True)


def _render_validation(results: list[ValidationResult]) -> None:
    table = Table(title="Aletheia Validation")
    table.add_column("Provider")
    table.add_column("Status")
    table.add_column("Details")
    for result in results:
        status = "OK" if result.is_valid else "FAIL"
        details = result.error_message or ", ".join(result.available_models[:5]) or "-"
        table.add_row(result.provider, status, details)
    console.print(table)


def run_config_wizard(manager: ConfigManager | None = None) -> AletheiaConfig:
    manager = manager or ConfigManager()
    base = manager.load() if manager.config_path.exists() else AletheiaConfig()
    provider = typer.prompt(
        "Choose LLM provider [ollama/openai/anthropic/gemini]",
        default=base.default_llm_provider,
    ).strip()

    config = base.model_copy(update={"default_llm_provider": provider})
    if provider == "ollama":
        config = config.model_copy(
            update={
                "ollama_base_url": typer.prompt("Ollama host", default=base.ollama_base_url),
                "default_llm_model": typer.prompt("Ollama model", default=base.default_llm_model),
            }
        )
    elif provider == "openai":
        config = config.model_copy(
            update={
                "default_llm_model": typer.prompt("Default GPT model", default="gpt-4o-mini"),
                "openai_api_key": typer.prompt("OpenAI API key", hide_input=True).strip(),
            }
        )
    elif provider == "anthropic":
        config = config.model_copy(
            update={
                "default_llm_model": typer.prompt(
                    "Default Claude model",
                    default="claude-3-5-haiku-latest",
                ),
                "anthropic_api_key": typer.prompt("Anthropic API key", hide_input=True).strip(),
            }
        )
    elif provider == "gemini":
        config = config.model_copy(
            update={
                "default_llm_model": typer.prompt("Default Gemini model", default="gemini-1.5-pro"),
                "gemini_api_key": typer.prompt("Gemini API key", hide_input=True).strip(),
            }
        )
    else:
        raise typer.BadParameter("Provider must be one of: ollama, openai, anthropic, gemini")

    config = config.model_copy(
        update={
            "yfinance_enabled": typer.confirm(
                "Enable yfinance market data?",
                default=base.yfinance_enabled,
            ),
            "ccxt_enabled": typer.confirm("Enable CCXT market data?", default=base.ccxt_enabled),
        }
    )

    if typer.confirm("Add Zerodha credentials?", default=bool(base.zerodha_api_key)):
        config = config.model_copy(
            update={
                "zerodha_api_key": typer.prompt(
                    "Zerodha API key",
                    default=base.zerodha_api_key or "",
                ).strip(),
                "zerodha_api_secret": typer.prompt(
                    "Zerodha API secret",
                    default=base.zerodha_api_secret or "",
                    hide_input=True,
                ).strip(),
            }
        )

    if typer.confirm("Add TradingView session token?", default=bool(base.tradingview_session)):
        config = config.model_copy(
            update={
                "tradingview_session": typer.prompt(
                    "TradingView session token",
                    default=base.tradingview_session or "",
                    hide_input=True,
                ).strip()
            }
        )

    if typer.confirm(
        "Set or update database encryption key?",
        default=bool(base.db_encryption_key),
    ):
        config = config.model_copy(
            update={
                "db_encryption_key": typer.prompt(
                    "Database encryption key",
                    default=base.db_encryption_key or "",
                    hide_input=True,
                ).strip()
            }
        )

    saved = manager.save(config)
    console.print("[green]Configuration saved.[/green]")
    return saved


async def _validate_config(config: AletheiaConfig) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    if config.default_llm_provider == "ollama":
        results.append(await validate_local_model(config.ollama_base_url, config.default_llm_model))
    else:
        key_name = {
            "openai": "openai_api_key",
            "anthropic": "anthropic_api_key",
            "gemini": "gemini_api_key",
        }[config.default_llm_provider]
        api_key = getattr(config, key_name)
        if api_key:
            results.append(await validate_frontier_api(config.default_llm_provider, api_key))

    if config.zerodha_api_key and config.zerodha_api_secret:
        results.append(await validate_zerodha(config.zerodha_api_key, config.zerodha_api_secret))
    if config.tradingview_session:
        results.append(await validate_tradingview(config.tradingview_session))
    return results


@app.command("init")
def init_config(
    validate: bool = typer.Option(True, help="Validate integrations after setup."),
) -> None:
    config = run_config_wizard(ConfigManager())
    if validate:
        _render_validation(asyncio.run(_validate_config(config)))


@app.command("show")
def show_config() -> None:
    config = ConfigManager().load()
    table = Table(title="Aletheia Config")
    table.add_column("Key")
    table.add_column("Value")
    for key, value in config.masked_dict().items():
        table.add_row(key, str(value))
    console.print(table)


@app.command("set")
def set_config(
    key: str = typer.Argument(..., help="Config key to update"),
    value: str = typer.Argument(..., help="New value"),
) -> None:
    updated = ConfigManager().set_value(key, value)
    console.print(f"[green]Updated {key}[/green]")
    console.print(str(updated.masked_dict()[key]))


@app.command("validate")
def validate_config() -> None:
    results = asyncio.run(_validate_config(ConfigManager().load()))
    _render_validation(results)
    if any(not result.is_valid for result in results):
        raise typer.Exit(code=1)


@app.command("reset")
def reset_config(force: bool = typer.Option(False, "--force", help="Skip confirmation.")) -> None:
    if not force and not typer.confirm("Delete local Aletheia config and synced .env?"):
        raise typer.Exit(code=1)
    ConfigManager().reset()
    console.print("[green]Configuration reset.[/green]")
