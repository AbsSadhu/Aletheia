import httpx
import json
import logging
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class ChatMessage:
    role: str
    content: str
    tool_calls: Optional[List[ToolCall]] = None


@dataclass
class ChatResponse:
    message: ChatMessage
    finish_reason: str


class ChatLLM:
    """Base interface for LLM Chat Completions with Tool Calling."""

    async def chat(
        self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None
    ) -> ChatResponse:
        raise NotImplementedError


class OllamaChatLLM(ChatLLM):
    """Ollama implementation for local Chat with Tool Calling."""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.1"):
        self.base_url = base_url
        self.model = model

    async def chat(
        self, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None
    ) -> ChatResponse:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if tools:
            payload["tools"] = tools

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload, timeout=120.0)
                response.raise_for_status()
                data = response.json()

                resp_msg = data.get("message", {})
                content = resp_msg.get("content", "")
                role = resp_msg.get("role", "assistant")

                tool_calls = None
                if "tool_calls" in resp_msg:
                    tool_calls = []
                    for tc in resp_msg["tool_calls"]:
                        func = tc.get("function", {})
                        args = func.get("arguments", {})
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except Exception:
                                args = {}
                        tool_calls.append(
                            ToolCall(
                                id=tc.get("id", f"call_{func.get('name')}"),
                                name=func.get("name"),
                                arguments=args,
                            )
                        )

                return ChatResponse(
                    message=ChatMessage(role=role, content=content, tool_calls=tool_calls),
                    finish_reason=data.get("done_reason", "stop"),
                )

            except Exception as e:
                logger.error(f"Ollama chat failed: {str(e)}")
                return ChatResponse(
                    message=ChatMessage(
                        role="assistant", content=f"Error: {str(e)}", tool_calls=None
                    ),
                    finish_reason="error",
                )
