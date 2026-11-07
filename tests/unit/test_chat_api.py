"""Chat panel backend: message adapters, model catalog, custom models, threads, multi-turn stream."""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from aletheia.core.api.routers import chat as chat_router
from aletheia.core.db.chat_store import ChatStore
from aletheia.core.llm.chat_llm import (
    ChatMessage,
    ChatResponse,
    _to_anthropic_messages,
    _to_ollama_messages,
    build_chat_llm,
)
from aletheia.core.main import app

CANONICAL = [
    {"role": "system", "content": "sys"},
    {"role": "user", "content": "price of INFY?"},
    {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "market_data", "arguments": json.dumps({"symbol": "INFY"})},
            },
            {
                "id": "c2",
                "type": "function",
                "function": {"name": "technical", "arguments": json.dumps({"symbol": "INFY"})},
            },
        ],
    },
    {"role": "tool", "tool_call_id": "c1", "name": "market_data", "content": '{"p": 1}'},
    {"role": "tool", "tool_call_id": "c2", "name": "technical", "content": '{"rsi": 50}'},
]


def test_ollama_adapter_turns_argument_strings_into_objects() -> None:
    out = _to_ollama_messages(CANONICAL[1:])
    calls = out[1]["tool_calls"]
    assert calls[0]["function"]["arguments"] == {"symbol": "INFY"}
    assert "id" not in calls[0]
    assert out[2] == {"role": "tool", "tool_name": "market_data", "content": '{"p": 1}'}


def test_anthropic_adapter_builds_tool_blocks_and_merges_results() -> None:
    system, out = _to_anthropic_messages(CANONICAL)
    assert system == "sys"
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert [b["type"] for b in out[1]["content"]] == ["tool_use", "tool_use"]
    assert out[1]["content"][0] == {
        "type": "tool_use",
        "id": "c1",
        "name": "market_data",
        "input": {"symbol": "INFY"},
    }
    results = out[2]["content"]
    assert [r["tool_use_id"] for r in results] == ["c1", "c2"]


def test_build_chat_llm_variants() -> None:
    assert build_chat_llm("ollama", "qwen2.5:7b").model == "qwen2.5:7b"
    llm = build_chat_llm("openai_compatible", "m", base_url="http://localhost:1234/v1/")
    assert llm._base_url == "http://localhost:1234/v1"
    with pytest.raises(ValueError):
        build_chat_llm("openai_compatible", "m")
    with pytest.raises(ValueError):
        build_chat_llm("nope", "m")


def test_store_threads_history_and_custom_models(tmp_path) -> None:
    store = ChatStore(tmp_path / "chat.sqlite3")
    tid = store.create_thread("hello", "ollama", "m")
    store.add_message(tid, "user", "hi")
    store.add_message(tid, "assistant", "", steps=[{"type": "error", "content": "x"}])
    store.add_message(tid, "assistant", "hey", steps=[{"type": "tool", "result": "r" * 20000}])
    # Empty (failed) turns are not replayed to the model.
    assert store.history(tid) == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hey"},
    ]
    assert store.get_thread(tid)["messages"][2]["steps"][0]["truncated"] is True
    a = store.add_custom_model("ollama", "qwen2.5:7b")
    assert store.add_custom_model("ollama", "qwen2.5:7b")["id"] == a["id"]
    assert store.delete_thread(tid) and store.get_thread(tid) is None


@pytest.fixture
def client(monkeypatch, tmp_path):
    store = ChatStore(tmp_path / "chat.sqlite3")
    monkeypatch.setattr(chat_router, "get_chat_store", lambda: store)

    async def fake_tags(_base_url):
        return (
            [
                {"model": "mistral:7b", "size_bytes": 4_000_000_000, "parameter_size": "7B"},
                {"model": "qwen2.5:7b", "size_bytes": 4_700_000_000, "parameter_size": "7.6B"},
            ],
            None,
        )

    monkeypatch.setattr(chat_router, "list_ollama_models", fake_tags)
    return TestClient(app)


def test_providers_lists_disk_models_and_marks_uninstalled_custom(client) -> None:
    client.post("/api/v1/chat/models/custom", json={"provider": "ollama", "model": "llama3.2:3b"})
    data = client.get("/api/v1/chat/providers").json()
    ollama = next(p for p in data["providers"] if p["id"] == "ollama")
    by_name = {m["model"]: m for m in ollama["models"]}
    assert by_name["qwen2.5:7b"]["installed"] is True
    assert by_name["llama3.2:3b"]["installed"] is False
    assert by_name["llama3.2:3b"]["custom_id"]
    assert data["default"]["provider"] == "ollama"


def test_custom_model_validation_and_secret_not_returned(client) -> None:
    bad = client.post("/api/v1/chat/models/custom", json={"provider": "x", "model": "m"})
    assert bad.status_code == 422
    no_url = client.post(
        "/api/v1/chat/models/custom", json={"provider": "openai_compatible", "model": "m"}
    )
    assert no_url.status_code == 422
    ok = client.post(
        "/api/v1/chat/models/custom",
        json={
            "provider": "openai_compatible",
            "model": "gpt-oss",
            "base_url": "http://localhost:1234/v1",
            "api_key": "sk-secret",  # pragma: allowlist secret
        },
    )
    assert ok.status_code == 201
    body = ok.json()
    assert body["has_api_key"] is True and "sk-secret" not in json.dumps(body)
    assert "sk-secret" not in json.dumps(client.get("/api/v1/chat/providers").json())
    assert client.delete(f"/api/v1/chat/models/custom/{body['id']}").status_code == 204
    assert client.delete(f"/api/v1/chat/models/custom/{body['id']}").status_code == 404


class _ScriptedLLM:
    provider_name = "ollama"

    def __init__(self):
        self.seen: list[list[dict]] = []
        self.replies = [
            ChatResponse(
                message=ChatMessage(role="assistant", content="first"), finish_reason="stop"
            ),
            ChatResponse(
                message=ChatMessage(role="assistant", content="second"), finish_reason="stop"
            ),
        ]

    async def is_available(self):
        return True

    async def chat(self, messages, tools=None):
        self.seen.append(messages)
        return self.replies.pop(0)


def _events(resp) -> list[tuple[str, dict]]:
    out, ev = [], None
    for line in resp.text.splitlines():
        if line.startswith("event: "):
            ev = line[7:]
        elif line.startswith("data: ") and ev:
            out.append((ev, json.loads(line[6:])))
    return out


def test_stream_is_multi_turn_and_reports_model(client, monkeypatch) -> None:
    llm = _ScriptedLLM()
    monkeypatch.setattr(chat_router, "build_chat_llm", lambda *a, **k: llm)

    r1 = client.post(
        "/api/v1/chat/stream",
        json={"prompt": "hello", "provider": "ollama", "model": "qwen2.5:7b"},
    )
    ev1 = _events(r1)
    assert ev1[0] == (
        "thread",
        {"thread_id": ev1[0][1]["thread_id"], "provider": "ollama", "model": "qwen2.5:7b"},
    )
    assert ("final_answer", {"content": "first"}) in ev1 and ev1[-1][0] == "done"

    tid = ev1[0][1]["thread_id"]
    r2 = client.post(
        "/api/v1/chat/stream",
        json={"prompt": "and again", "thread_id": tid, "provider": "ollama", "model": "qwen2.5:7b"},
    )
    assert ("final_answer", {"content": "second"}) in _events(r2)
    # The second call replays turn one, and the system prompt carries the chat rules.
    sent = llm.seen[1]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert "Oracle BUY/REDUCE signal failed" in sent[0]["content"]

    thread = client.get(f"/api/v1/chat/threads/{tid}").json()
    assert [m["role"] for m in thread["messages"]] == ["user", "assistant", "user", "assistant"]
    assert thread["messages"][1]["model"] == "qwen2.5:7b"
    assert client.get("/api/v1/chat/threads").json()[0]["id"] == tid
    assert client.delete(f"/api/v1/chat/threads/{tid}").status_code == 204


def test_stream_explains_uninstalled_ollama_model(client) -> None:
    resp = client.post(
        "/api/v1/chat/stream",
        json={"prompt": "hi", "provider": "ollama", "model": "not-pulled:1b"},
    )
    errors = [d for e, d in _events(resp) if e == "error"]
    assert errors and "isn't installed" in errors[0]["message"]


def test_stream_unknown_thread_is_404(client) -> None:
    resp = client.post("/api/v1/chat/stream", json={"prompt": "x", "thread_id": "nope"})
    assert resp.status_code == 404


async def test_ollama_retries_without_tools_when_model_rejects_them(monkeypatch) -> None:
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        if "tools" in body:
            return httpx.Response(400, text='{"error": "model does not support tools"}')
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "ok"}})

    real = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(handler), **kw),
    )
    llm = build_chat_llm("ollama", "gemma:2b")
    resp = await llm.chat([{"role": "user", "content": "hi"}], tools=[{"type": "function"}])
    assert resp.message.content == "ok"
    assert "tools" in calls[0] and "tools" not in calls[1]


def test_chat_registry_hides_stub_tools() -> None:
    from aletheia.core.tools.registry import build_registry

    names = {t.name for t in build_registry().list_tools()}
    assert "sec_filings" not in names and "market_data" in names and "backtest" in names
    assert "sec_filings" in {t.name for t in build_registry(include_stubs=True).list_tools()}
