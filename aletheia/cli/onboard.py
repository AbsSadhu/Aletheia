import os
from typing import Sequence
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.text import Text
from rich.panel import Panel

from prompt_toolkit import prompt

CANCEL = object()

@dataclass(frozen=True)
class Provider:
    key: str
    label: str
    default_model: str
    key_env: str | None
    suggested_models: tuple[str, ...]

PROVIDERS = (
    Provider("ollama", "Ollama (Local, Privacy-First)", "llama3", None, ("llama3", "mistral", "phi3")),
    Provider("openai", "OpenAI", "gpt-4o", "OPENAI_API_KEY", ("gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo")),
    Provider("deepseek", "DeepSeek", "deepseek-coder", "DEEPSEEK_API_KEY", ("deepseek-coder", "deepseek-chat")),
)

def _env_path() -> Path:
    return Path(os.getcwd()) / ".env"

def _save_env(values: dict[str, str]) -> None:
    path = _env_path()
    lines = []
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    
    env_dict = {}
    for line in lines:
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env_dict[k.strip()] = v.strip()
            
    env_dict.update(values)
    
    with path.open("w", encoding="utf-8") as f:
        for k, v in env_dict.items():
            f.write(f"{k}={v}\n")

def _select_numeric(choices: Sequence[tuple[str, str]], console: Console) -> str | object:
    """Fallback stdin selector for simplicity."""
    for i, (_, label) in enumerate(choices, start=1):
        console.print(f"  [{i}] {label}", style="dim")
    console.print(Text("  (type number, q=cancel)", style="dim"))
    try:
        raw = prompt("> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return CANCEL
    if raw in {"q", "quit", "cancel"}:
        return CANCEL
    if not raw:
        return choices[0][0]
    try:
        idx = int(raw)
        if 1 <= idx <= len(choices):
            return choices[idx - 1][0]
    except ValueError:
        pass
    console.print(Text("  invalid selection, try again", style="red"))
    return _select_numeric(choices, console)

def _prompt_secret(prompt_text: str, console: Console) -> str | object:
    console.print()
    console.print(Text(f"? {prompt_text}", style="bold cyan"))
    try:
        return prompt("> ", is_password=True).strip()
    except (EOFError, KeyboardInterrupt):
        return CANCEL

def _prompt_text(prompt_text: str, default: str, console: Console) -> str | object:
    console.print()
    console.print(Text(f"? {prompt_text}", style="bold cyan"))
    console.print(Text(f"  (Enter for default: {default})", style="dim"))
    try:
        raw = prompt("> ").strip()
        return raw if raw else default
    except (EOFError, KeyboardInterrupt):
        return CANCEL

def run_onboarding() -> None:
    console = Console()
    console.print(Panel("[bold cyan]Aletheia Interactive Setup[/bold cyan]\n[dim]Configure the default LLM provider and API tokens.[/dim]", border_style="cyan"))

    values: dict[str, str] = {}
    
    # Step 1: Provider
    choices = [(p.key, p.label) for p in PROVIDERS]
    console.print("\n[bold cyan]? Pick an LLM Provider[/bold cyan]")
    provider_key = _select_numeric(choices, console)
    if provider_key is CANCEL:
        return
    provider = next(p for p in PROVIDERS if p.key == provider_key)
    values["ALETHEIA_LLM_PROVIDER"] = provider.key

    # Step 2: Model
    model_choices = [(m, m) for m in provider.suggested_models]
    model_choices.append(("__custom__", "Other (type custom model)"))
    console.print("\n[bold cyan]? Pick a Model[/bold cyan]")
    model_choice = _select_numeric(model_choices, console)
    if model_choice is CANCEL:
        return
    
    if model_choice == "__custom__":
        custom = _prompt_text("Type the model id", provider.default_model, console)
        if custom is CANCEL:
            return
        model = str(custom)
    else:
        model = str(model_choice)
    values["ALETHEIA_LLM_MODEL"] = model

    # Step 3: Key
    if provider.key_env is not None:
        key = _prompt_secret(f"Paste your {provider.label} API key", console)
        if key is CANCEL:
            return
        values[provider.key_env] = str(key)
    else:
        console.print("\n[bold green]  Ollama runs locally — no API key needed.[/bold green]")

    _save_env(values)
    console.print("\n[bold green]✓ Configuration saved to .env[/bold green]")
    console.print("[dim]You are ready to run analysis via `aletheia analyze`[/dim]")
