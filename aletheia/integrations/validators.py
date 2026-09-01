from __future__ import annotations

import httpx
from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    provider: str
    is_valid: bool = False
    error_message: str | None = None
    available_models: list[str] = Field(default_factory=list)
    is_running: bool | None = None
    model_downloaded: bool | None = None
    context_length: int | None = None
    account_id: str | None = None
    username: str | None = None
    available_segments: list[str] = Field(default_factory=list)
    available_data_types: list[str] = Field(default_factory=list)


async def validate_frontier_api(provider: str, api_key: str) -> ValidationResult:
    provider = provider.lower()
    try:
        if provider == "openai":
            return await _validate_openai(api_key)
        if provider == "anthropic":
            return await _validate_anthropic(api_key)
        if provider == "gemini":
            return await _validate_gemini(api_key)
        return ValidationResult(provider=provider, error_message="Unsupported provider.")
    except httpx.HTTPError as exc:
        return ValidationResult(provider=provider, error_message=str(exc))


async def validate_local_model(host: str, model: str) -> ValidationResult:
    endpoint = host.rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{endpoint}/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
            names = [item.get("name", "") for item in models if item.get("name")]
            selected = next((item for item in models if item.get("name") == model), None)
            details = selected.get("details", {}) if isinstance(selected, dict) else {}
            return ValidationResult(
                provider="local",
                is_valid=model in names,
                is_running=True,
                model_downloaded=model in names,
                context_length=details.get("context_length"),
                available_models=names,
                error_message=None if model in names else f"Model '{model}' is not installed.",
            )
    except httpx.HTTPError as exc:
        return ValidationResult(
            provider="local",
            is_valid=False,
            is_running=False,
            model_downloaded=False,
            error_message=str(exc),
        )


async def validate_zerodha(api_key: str, api_secret: str) -> ValidationResult:
    headers = {"X-Kite-Version": "3", "Authorization": f"token {api_key}:{api_secret}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://api.kite.trade/user/profile", headers=headers)
            response.raise_for_status()
            data = response.json().get("data", {})
            return ValidationResult(
                provider="zerodha",
                is_valid=True,
                account_id=data.get("user_id"),
                available_segments=list(data.get("products", [])),
            )
    except httpx.HTTPError as exc:
        return ValidationResult(provider="zerodha", error_message=str(exc))


async def validate_tradingview(session_token: str) -> ValidationResult:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://www.tradingview.com/accounts/signin/",
                cookies={"sessionid": session_token},
            )
            response.raise_for_status()
            username = _extract_tradingview_username(response.text)
            return ValidationResult(
                provider="tradingview",
                is_valid=bool(username),
                username=username,
                available_data_types=["charts", "watchlists"] if username else [],
                error_message=None if username else "TradingView session appears invalid.",
            )
    except httpx.HTTPError as exc:
        return ValidationResult(provider="tradingview", error_message=str(exc))


async def _validate_openai(api_key: str) -> ValidationResult:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        response.raise_for_status()
        models = sorted(item.get("id", "") for item in response.json().get("data", []))
        return ValidationResult(provider="openai", is_valid=True, available_models=models)


async def _validate_anthropic(api_key: str) -> ValidationResult:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        )
        response.raise_for_status()
        models = sorted(item.get("id", "") for item in response.json().get("data", []))
        return ValidationResult(provider="anthropic", is_valid=True, available_models=models)


async def _validate_gemini(api_key: str) -> ValidationResult:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key},
        )
        response.raise_for_status()
        models = sorted(item.get("name", "") for item in response.json().get("models", []))
        return ValidationResult(provider="gemini", is_valid=True, available_models=models)


def _extract_tradingview_username(html: str) -> str | None:
    marker = '"username":"'
    if marker not in html:
        return None
    return html.split(marker, 1)[1].split('"', 1)[0] or None
