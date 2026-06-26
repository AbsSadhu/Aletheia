"""
Multi-provider LLM Chat interface.

Provides:
- OllamaChatLLM    — local Ollama (default)
- OpenAIChatLLM    — OpenAI API
- AnthropicChatLLM — Anthropic API
- LLMRouter        — tries providers in priority order with retry + circuit breaker
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatMessage:
    role: str
    content: str
    tool_calls: list[ToolCall] | None = None


@dataclass
class ChatResponse:
    message: ChatMessage
    finish_reason: str
    provider: str = "unknown"
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------

class ChatLLM:
    """Base interface for LLM Chat Completions with Tool Calling."""

    provider_name: str = "base"

    async def is_available(self) -> bool:
        """Check if this provider is reachable / configured."""
        return True

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Ollama
# ---------------------------------------------------------------------------

class OllamaChatLLM(ChatLLM):
    """Ollama local LLM — tool calling supported (Llama 3.1+, Mistral NeMo, etc.)"""

    provider_name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "mistral:7b"):
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        url = f"{self.base_url}/api/chat"
        payload: dict[str, Any] = {"model": self.model, "messages": messages, "stream": False}
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        resp_msg = data.get("message", {})
        content = resp_msg.get("content", "")
        role = resp_msg.get("role", "assistant")
        tool_calls = _parse_ollama_tool_calls(resp_msg)

        prompt_eval = data.get("prompt_eval_count", 0)
        eval_count = data.get("eval_count", 0)

        return ChatResponse(
            message=ChatMessage(role=role, content=content, tool_calls=tool_calls),
            finish_reason=data.get("done_reason", "stop"),
            provider=self.provider_name,
            input_tokens=prompt_eval,
            output_tokens=eval_count,
        )


def _parse_ollama_tool_calls(resp_msg: dict) -> list[ToolCall] | None:
    raw = resp_msg.get("tool_calls")
    if not raw:
        return None
    result = []
    for tc in raw:
        func = tc.get("function", {})
        args = func.get("arguments", {})
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        result.append(ToolCall(
            id=tc.get("id", f"call_{func.get('name', 'tool')}"),
            name=func.get("name", ""),
            arguments=args,
        ))
    return result or None


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

class OpenAIChatLLM(ChatLLM):
    """OpenAI Chat Completions API with tool calling."""

    provider_name = "openai"

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self._base_url = "https://api.openai.com/v1"

    async def is_available(self) -> bool:
        return bool(self.api_key)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        msg = choice["message"]
        content = msg.get("content") or ""
        role = msg.get("role", "assistant")
        tool_calls = _parse_openai_tool_calls(msg)
        usage = data.get("usage", {})

        return ChatResponse(
            message=ChatMessage(role=role, content=content, tool_calls=tool_calls),
            finish_reason=choice.get("finish_reason", "stop"),
            provider=self.provider_name,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
        )


def _parse_openai_tool_calls(msg: dict) -> list[ToolCall] | None:
    raw = msg.get("tool_calls")
    if not raw:
        return None
    result = []
    for tc in raw:
        func = tc.get("function", {})
        args = func.get("arguments", "{}")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        result.append(ToolCall(id=tc.get("id", ""), name=func.get("name", ""), arguments=args))
    return result or None


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

class AnthropicChatLLM(ChatLLM):
    """Anthropic Messages API with tool use."""

    provider_name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5"):
        self.api_key = api_key
        self.model = model
        self._base_url = "https://api.anthropic.com/v1"

    async def is_available(self) -> bool:
        return bool(self.api_key)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        # Anthropic needs system message extracted separately
        system_content = ""
        filtered_messages = []
        for m in messages:
            if m["role"] == "system":
                system_content = m["content"]
            else:
                filtered_messages.append(m)

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": filtered_messages,
        }
        if system_content:
            payload["system"] = system_content

        # Convert OpenAI-style tool defs to Anthropic format
        if tools:
            anthropic_tools = []
            for t in tools:
                fn = t.get("function", {})
                anthropic_tools.append({
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {}),
                })
            payload["tools"] = anthropic_tools

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self._base_url}/messages",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        # Parse response
        content_blocks = data.get("content", [])
        text_content = ""
        tool_calls: list[ToolCall] | None = None
        tc_list = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tc_list.append(ToolCall(
                    id=block.get("id", ""),
                    name=block.get("name", ""),
                    arguments=block.get("input", {}),
                ))

        if tc_list:
            tool_calls = tc_list

        usage = data.get("usage", {})
        stop_reason = data.get("stop_reason", "end_turn")

        return ChatResponse(
            message=ChatMessage(role="assistant", content=text_content, tool_calls=tool_calls),
            finish_reason=stop_reason,
            provider=self.provider_name,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )


# ---------------------------------------------------------------------------
# LLM Router — tries providers in order, with retry + circuit breaker
# ---------------------------------------------------------------------------

@dataclass
class _CircuitState:
    failures: int = 0
    last_failure_time: float = 0.0
    open_until: float = 0.0  # epoch seconds; 0 means closed (healthy)


class LLMRouter(ChatLLM):
    """
    Tries LLM providers in priority order.

    - Retries each provider up to `max_retries` times on transient errors.
    - Applies a simple circuit breaker: after `failure_threshold` consecutive
      failures, the provider is skipped for `cooldown_secs` seconds.
    - Falls through to the next provider if current one is unavailable or broken.
    - Raises RuntimeError if all providers are exhausted.
    """

    provider_name = "router"

    def __init__(
        self,
        providers: list[ChatLLM],
        max_retries: int = 2,
        retry_delay: float = 1.0,
        failure_threshold: int = 3,
        cooldown_secs: float = 60.0,
    ):
        self.providers = providers
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.failure_threshold = failure_threshold
        self.cooldown_secs = cooldown_secs
        self._circuit: dict[str, _CircuitState] = {
            p.provider_name: _CircuitState() for p in providers
        }

    def _is_open(self, provider: ChatLLM) -> bool:
        state = self._circuit[provider.provider_name]
        if state.open_until > 0 and time.monotonic() < state.open_until:
            return True
        if state.open_until > 0:
            # cooldown expired — reset
            state.failures = 0
            state.open_until = 0.0
        return False

    def _record_failure(self, provider: ChatLLM) -> None:
        state = self._circuit[provider.provider_name]
        state.failures += 1
        state.last_failure_time = time.monotonic()
        if state.failures >= self.failure_threshold:
            state.open_until = time.monotonic() + self.cooldown_secs
            logger.warning(
                "LLMRouter: circuit opened for '%s' for %.0fs",
                provider.provider_name,
                self.cooldown_secs,
            )

    def _record_success(self, provider: ChatLLM) -> None:
        state = self._circuit[provider.provider_name]
        state.failures = 0
        state.open_until = 0.0

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        last_exc: Exception | None = None

        for provider in self.providers:
            if self._is_open(provider):
                logger.debug("LLMRouter: skipping '%s' (circuit open)", provider.provider_name)
                continue

            available = await provider.is_available()
            if not available:
                logger.debug("LLMRouter: '%s' unavailable, skipping", provider.provider_name)
                continue

            for attempt in range(1, self.max_retries + 2):  # +1 for initial try
                try:
                    response = await provider.chat(messages=messages, tools=tools)
                    self._record_success(provider)
                    logger.debug(
                        "LLMRouter: provider='%s' tokens=%d",
                        provider.provider_name,
                        response.total_tokens,
                    )
                    return response
                except Exception as exc:
                    last_exc = exc
                    logger.warning(
                        "LLMRouter: '%s' attempt %d/%d failed: %s",
                        provider.provider_name,
                        attempt,
                        self.max_retries + 1,
                        exc,
                    )
                    self._record_failure(provider)
                    if attempt <= self.max_retries:
                        await asyncio.sleep(self.retry_delay * attempt)
                    else:
                        break  # move to next provider

        raise RuntimeError(
            f"All LLM providers exhausted. Last error: {last_exc}"
        ) from last_exc


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------

def build_llm_router() -> LLMRouter:
    """Build an LLMRouter from current settings."""
    from aletheia.core.config.settings import get_settings
    settings = get_settings()

    provider_map: dict[str, ChatLLM] = {
        "ollama": OllamaChatLLM(
            base_url=settings.ollama_base_url,
            model=settings.default_llm_model,
        ),
    }
    if settings.openai_api_key:
        provider_map["openai"] = OpenAIChatLLM(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )
    if settings.anthropic_api_key:
        provider_map["anthropic"] = AnthropicChatLLM(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )

    ordered: list[ChatLLM] = []
    for name in settings.llm_provider_priority:
        if name in provider_map:
            ordered.append(provider_map[name])

    if not ordered:
        # Fallback — always include Ollama even if not in priority list
        ordered = [provider_map["ollama"]]

    return LLMRouter(
        providers=ordered,
        max_retries=settings.llm_max_retries,
        retry_delay=settings.llm_retry_delay_secs,
    )
