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
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx

logger = logging.getLogger(__name__)


# Data classes


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
    latency_secs: float = 0.0
    cost_usd: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


def calculate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> float:
    p = provider.lower()
    m = model.lower()
    input_rate = 0.0
    output_rate = 0.0

    if "openai" in p:
        if "gpt-4o-mini" in m:
            input_rate = 0.15 / 1_000_000
            output_rate = 0.60 / 1_000_000
        else:  # default gpt-4o
            input_rate = 2.50 / 1_000_000
            output_rate = 10.00 / 1_000_000
    elif "anthropic" in p:
        if "haiku" in m:
            input_rate = 0.25 / 1_000_000
            output_rate = 1.25 / 1_000_000
        else:  # default sonnet 3.5
            input_rate = 3.00 / 1_000_000
            output_rate = 15.00 / 1_000_000

    return (input_tokens * input_rate) + (output_tokens * output_rate)


# Base class


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

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str | ChatResponse]:
        """Yield text deltas (str) as they arrive, then the complete ChatResponse last.

        Providers that cannot stream just yield the finished response.
        """
        yield await self.chat(messages=messages, tools=tools)


# Message adapters
#
# The agent loop keeps history in one canonical, OpenAI-style shape: assistant messages carry
# `tool_calls` with an `id` and JSON-string `arguments`, and tool results are `role: "tool"`
# messages with a matching `tool_call_id`. Each provider translates that on the way out.


def _to_ollama_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ollama wants tool-call arguments as objects (not JSON strings) and `tool_name` on results."""
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            calls = []
            for tc in m["tool_calls"]:
                fn = dict(tc.get("function", {}))
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                fn["arguments"] = args
                calls.append({"type": "function", "function": fn})
            out.append(
                {"role": "assistant", "content": m.get("content") or "", "tool_calls": calls}
            )
        elif m.get("role") == "tool":
            out.append(
                {"role": "tool", "tool_name": m.get("name", ""), "content": m.get("content", "")}
            )
        else:
            out.append({"role": m["role"], "content": m.get("content") or ""})
    return out


def _to_anthropic_messages(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    """Split out the system prompt and convert tool calls/results to Anthropic content blocks."""
    system = ""
    out: list[dict[str, Any]] = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            system = m.get("content") or ""
        elif role == "assistant" and m.get("tool_calls"):
            blocks: list[dict[str, Any]] = []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for tc in m["tool_calls"]:
                fn = tc.get("function", {})
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                blocks.append(
                    {
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": args,
                    }
                )
            out.append({"role": "assistant", "content": blocks})
        elif role == "tool":
            result = {
                "type": "tool_result",
                "tool_use_id": m.get("tool_call_id", ""),
                "content": m.get("content", ""),
            }
            # Consecutive tool results must share one user turn.
            prev = out[-1] if out else None
            if (
                prev
                and prev["role"] == "user"
                and isinstance(prev["content"], list)
                and prev["content"]
                and prev["content"][0].get("type") == "tool_result"
            ):
                prev["content"].append(result)
            else:
                out.append({"role": "user", "content": [result]})
        else:
            out.append({"role": role, "content": m.get("content") or ""})
    return system, out


# Ollama


class OllamaChatLLM(ChatLLM):
    """Ollama local LLM — tool calling supported (Llama 3.1+, Mistral NeMo, etc.)"""

    provider_name = "ollama"

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "mistral:7b",
        num_ctx: int | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except Exception:
            return False

    def _payload(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, stream: bool
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": _to_ollama_messages(messages),
            "stream": stream,
        }
        if self.num_ctx:
            payload["options"] = {"num_ctx": self.num_ctx}
        if tools:
            payload["tools"] = tools
        return payload

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str | ChatResponse]:
        """Stream `message.content` deltas; the model's separate `thinking` stream is dropped.

        Closing this generator (e.g. the user pressed Stop) closes the HTTP connection, which
        makes Ollama stop generating.
        """
        url = f"{self.base_url}/api/chat"
        start_time = time.monotonic()
        content: list[str] = []
        tool_calls: list[ToolCall] = []
        final: dict[str, Any] = {}
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=5.0)) as client:
            for use_tools in (tools, None) if tools else (None,):
                payload = self._payload(messages, use_tools, stream=True)
                async with client.stream("POST", url, json=payload) as resp:
                    if resp.status_code == 400 and use_tools:
                        body = (await resp.aread()).decode(errors="replace")
                        if "tool" in body.lower():
                            logger.warning(
                                "Ollama '%s' rejected tools; retrying without", self.model
                            )
                            continue
                    if resp.status_code >= 400:
                        await resp.aread()
                        resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        chunk = json.loads(line)
                        if chunk.get("error"):
                            raise RuntimeError(str(chunk["error"]))
                        msg = chunk.get("message") or {}
                        if msg.get("content"):
                            content.append(msg["content"])
                            yield msg["content"]
                        tool_calls.extend(_parse_ollama_tool_calls(msg) or [])
                        if chunk.get("done"):
                            final = chunk
                break
        prompt_eval = final.get("prompt_eval_count", 0)
        eval_count = final.get("eval_count", 0)
        yield ChatResponse(
            message=ChatMessage(
                role="assistant", content="".join(content), tool_calls=tool_calls or None
            ),
            finish_reason=final.get("done_reason", "stop"),
            provider=self.provider_name,
            input_tokens=prompt_eval,
            output_tokens=eval_count,
            latency_secs=time.monotonic() - start_time,
            cost_usd=calculate_cost(self.provider_name, self.model, prompt_eval, eval_count),
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        url = f"{self.base_url}/api/chat"
        payload = self._payload(messages, tools, stream=False)

        start_time = time.monotonic()
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 400 and tools and "tool" in response.text.lower():
                # Not every model can call tools (e.g. some reasoning/vision builds); answer
                # without them rather than failing the whole chat.
                logger.warning("Ollama model '%s' rejected tools; retrying without", self.model)
                payload.pop("tools", None)
                response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
        latency_secs = time.monotonic() - start_time

        resp_msg = data.get("message", {})
        content = resp_msg.get("content", "")
        role = resp_msg.get("role", "assistant")
        tool_calls = _parse_ollama_tool_calls(resp_msg)

        prompt_eval = data.get("prompt_eval_count", 0)
        eval_count = data.get("eval_count", 0)

        cost_usd = calculate_cost(self.provider_name, self.model, prompt_eval, eval_count)

        return ChatResponse(
            message=ChatMessage(role=role, content=content, tool_calls=tool_calls),
            finish_reason=data.get("done_reason", "stop"),
            provider=self.provider_name,
            input_tokens=prompt_eval,
            output_tokens=eval_count,
            latency_secs=latency_secs,
            cost_usd=cost_usd,
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
        result.append(
            ToolCall(
                id=tc.get("id") or f"call_{uuid.uuid4().hex[:10]}",
                name=func.get("name", ""),
                arguments=args,
            )
        )
    return result or None


# OpenAI


class OpenAIChatLLM(ChatLLM):
    """OpenAI Chat Completions API with tool calling."""

    provider_name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1",
        require_key: bool = True,
    ):
        self.api_key = api_key
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._require_key = require_key

    async def is_available(self) -> bool:
        return bool(self.api_key) or not self._require_key

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        url = f"{self._base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload: dict[str, Any] = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        start_time = time.monotonic()
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        latency_secs = time.monotonic() - start_time

        choice = data["choices"][0]
        msg = choice["message"]
        content = msg.get("content") or ""
        role = msg.get("role", "assistant")
        tool_calls = _parse_openai_tool_calls(msg)
        usage = data.get("usage", {})

        in_t = usage.get("prompt_tokens", 0)
        out_t = usage.get("completion_tokens", 0)
        cost_usd = calculate_cost(self.provider_name, self.model, in_t, out_t)

        return ChatResponse(
            message=ChatMessage(role=role, content=content, tool_calls=tool_calls),
            finish_reason=choice.get("finish_reason", "stop"),
            provider=self.provider_name,
            input_tokens=in_t,
            output_tokens=out_t,
            latency_secs=latency_secs,
            cost_usd=cost_usd,
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


# Anthropic


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
        system_content, filtered_messages = _to_anthropic_messages(messages)

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
                anthropic_tools.append(
                    {
                        "name": fn.get("name", ""),
                        "description": fn.get("description", ""),
                        "input_schema": fn.get("parameters", {}),
                    }
                )
            payload["tools"] = anthropic_tools

        start_time = time.monotonic()
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self._base_url}/messages",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        latency_secs = time.monotonic() - start_time

        # Parse response
        content_blocks = data.get("content", [])
        text_content = ""
        tool_calls: list[ToolCall] | None = None
        tc_list = []

        for block in content_blocks:
            if block.get("type") == "text":
                text_content += block.get("text", "")
            elif block.get("type") == "tool_use":
                tc_list.append(
                    ToolCall(
                        id=block.get("id", ""),
                        name=block.get("name", ""),
                        arguments=block.get("input", {}),
                    )
                )

        if tc_list:
            tool_calls = tc_list

        usage = data.get("usage", {})
        stop_reason = data.get("stop_reason", "end_turn")

        in_t = usage.get("input_tokens", 0)
        out_t = usage.get("output_tokens", 0)
        cost_usd = calculate_cost(self.provider_name, self.model, in_t, out_t)

        return ChatResponse(
            message=ChatMessage(role="assistant", content=text_content, tool_calls=tool_calls),
            finish_reason=stop_reason,
            provider=self.provider_name,
            input_tokens=in_t,
            output_tokens=out_t,
            latency_secs=latency_secs,
            cost_usd=cost_usd,
        )


# LLM Router — tries providers in order, with retry + circuit breaker


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
    _call_history: list[dict[str, Any]] = []

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
                        "LLMRouter: provider='%s' tokens=%d latency=%.2fs cost=$%.6f",
                        provider.provider_name,
                        response.total_tokens,
                        response.latency_secs,
                        response.cost_usd,
                    )
                    LLMRouter._call_history.append(
                        {
                            "provider": provider.provider_name,
                            "model": provider.model,
                            "input_tokens": response.input_tokens,
                            "output_tokens": response.output_tokens,
                            "latency_secs": response.latency_secs,
                            "cost_usd": response.cost_usd,
                            "timestamp": time.time(),
                        }
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

        raise RuntimeError(f"All LLM providers exhausted. Last error: {last_exc}") from last_exc


# Factory helper


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


def build_chat_llm(
    provider: str,
    model: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
) -> ChatLLM:
    """Build ONE provider for a user-picked model (no silent fallback to a different model).

    `provider` is "ollama", "openai", "anthropic" or "openai_compatible" (LM Studio, vLLM,
    OpenRouter, ... — anything speaking the OpenAI chat API at `base_url`). Keys not passed in
    come from settings.
    """
    from aletheia.core.config.settings import get_settings

    settings = get_settings()
    if provider == "ollama":
        return OllamaChatLLM(
            base_url=base_url or settings.ollama_base_url,
            model=model,
            num_ctx=settings.ollama_num_ctx,
        )
    if provider == "openai":
        return OpenAIChatLLM(api_key=api_key or settings.openai_api_key or "", model=model)
    if provider == "anthropic":
        return AnthropicChatLLM(api_key=api_key or settings.anthropic_api_key or "", model=model)
    if provider == "openai_compatible":
        if not base_url:
            raise ValueError("openai_compatible models need a base_url")
        llm = OpenAIChatLLM(
            api_key=api_key or "", model=model, base_url=base_url, require_key=False
        )
        llm.provider_name = "openai_compatible"
        return llm
    raise ValueError(f"Unknown provider '{provider}'")
