"""Token streaming, the tool display contract, symbol resolution and technical_analysis."""

import json

import httpx
import pytest

from aletheia.core.agent.context import AgentContext
from aletheia.core.agent.loop import ReActLoop
from aletheia.core.db.chat_store import ChatStore
from aletheia.core.llm.chat_llm import ChatMessage, ChatResponse, ToolCall, build_chat_llm
from aletheia.core.tools import market_data_tool, technical_tool
from aletheia.core.tools.market_data_tool import resolve_candidates
from aletheia.core.tools.registry import BaseTool, ToolRegistry, split_display


def _ndjson(*chunks: dict) -> bytes:
    return "".join(json.dumps(c) + "\n" for c in chunks).encode()


_REAL_CLIENT = httpx.AsyncClient  # captured once so re-patching never wraps a patched class


def _patch_ollama(monkeypatch, handler):
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kw: _REAL_CLIENT(transport=httpx.MockTransport(handler), **kw),
    )


async def test_ollama_stream_yields_deltas_then_response_and_drops_thinking(monkeypatch) -> None:
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            content=_ndjson(
                {"message": {"role": "assistant", "content": "", "thinking": "hmm"}},
                {"message": {"role": "assistant", "content": "Hel"}},
                {"message": {"role": "assistant", "content": "lo"}},
                {
                    "message": {"role": "assistant", "content": ""},
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 7,
                    "eval_count": 3,
                },
            ),
        )

    _patch_ollama(monkeypatch, handler)
    llm = build_chat_llm("ollama", "m")
    parts = [p async for p in llm.chat_stream([{"role": "user", "content": "hi"}])]
    assert parts[:2] == ["Hel", "lo"]
    final = parts[-1]
    assert isinstance(final, ChatResponse) and final.message.content == "Hello"
    assert (final.input_tokens, final.output_tokens) == (7, 3)
    assert seen[0]["stream"] is True and seen[0]["options"]["num_ctx"] > 0


async def test_ollama_stream_collects_tool_calls_and_retries_without_tools(monkeypatch) -> None:
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        if "tools" in body:
            return httpx.Response(400, text='{"error": "model does not support tools"}')
        return httpx.Response(
            200,
            content=_ndjson(
                {"message": {"content": "plain"}},
                {"message": {"content": ""}, "done": True},
            ),
        )

    _patch_ollama(monkeypatch, handler)
    llm = build_chat_llm("ollama", "m")
    parts = [p async for p in llm.chat_stream([{"role": "user", "content": "x"}], tools=[{}])]
    assert parts[0] == "plain" and "tools" not in calls[1]

    def tool_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=_ndjson(
                {
                    "message": {
                        "tool_calls": [
                            {"function": {"name": "market_data", "arguments": {"symbol": "X"}}}
                        ]
                    }
                },
                {"message": {"content": ""}, "done": True},
            ),
        )

    _patch_ollama(monkeypatch, tool_handler)
    parts = [p async for p in llm.chat_stream([{"role": "user", "content": "x"}], tools=[{}])]
    call = parts[-1].message.tool_calls[0]
    assert call.name == "market_data" and call.arguments == {"symbol": "X"} and call.id


class _ChartTool(BaseTool):
    name = "chart_tool"
    description = "returns a summary plus a chart payload"

    async def execute(self, **kwargs):
        return {"last_close": 10, "_display": {"type": "ohlcv", "bars": [[1, 1, 2, 0, 1, 5]] * 500}}


class _StreamingLLM:
    def __init__(self) -> None:
        self.seen: list[list[dict]] = []
        self.turn = 0

    async def chat_stream(self, messages, tools=None):
        self.seen.append(json.loads(json.dumps(messages)))
        self.turn += 1
        if self.turn == 1:
            yield "let me look"
            yield ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    content="let me look",
                    tool_calls=[ToolCall(id="c1", name="chart_tool", arguments={})],
                ),
                finish_reason="tool_calls",
            )
        else:
            yield "All "
            yield "done"
            yield ChatResponse(
                message=ChatMessage(role="assistant", content="All done"), finish_reason="stop"
            )


async def test_loop_streams_tokens_and_keeps_display_out_of_the_model_context() -> None:
    registry = ToolRegistry()
    registry.register(_ChartTool())
    llm = _StreamingLLM()
    events = [e async for e in ReActLoop(llm=llm, tool_registry=registry).run("go", AgentContext())]

    kinds = [e.event_type for e in events]
    assert kinds == [
        "token",
        "thought",
        "tool_call",
        "tool_result",
        "token",
        "token",
        "final_answer",
    ]
    result = next(e for e in events if e.event_type == "tool_result")
    assert result.data["id"] == "c1" and result.data["display"]["type"] == "ohlcv"
    assert "display" not in result.data["result"] and "_display" not in result.data["result"]
    # What the model reads on its second turn is the summary only, with the call id attached.
    tool_msg = next(m for m in llm.seen[1] if m["role"] == "tool")
    assert tool_msg["tool_call_id"] == "c1"
    assert "ohlcv" not in tool_msg["content"] and len(tool_msg["content"]) < 200
    assert events[-1].data["content"] == "All done"


def test_split_display() -> None:
    assert split_display({"a": 1, "_display": {"x": 2}}) == ({"a": 1}, {"x": 2})
    assert split_display("plain") == ("plain", None)


def test_store_keeps_display_whole_and_drops_it_when_huge(tmp_path) -> None:
    store = ChatStore(tmp_path / "c.sqlite3")
    tid = store.create_thread("t", None, None)
    bars = [
        [i, 1.0, 2.0, 0.5, 1.5, 100.0] for i in range(2000)
    ]  # far over the 8000-char result cap
    step = {"type": "tool", "id": "c1", "tool": "market_data", "result": {"a": 1}}
    store.add_message(
        tid, "assistant", "ok", steps=[{**step, "display": {"type": "ohlcv", "bars": bars}}]
    )
    got = store.get_thread(tid)["messages"][0]["steps"][0]
    assert len(got["display"]["bars"]) == 2000 and "truncated" not in got

    huge = [[i, 1.0, 2.0, 0.5, 1.5, 100.0] for i in range(40000)]
    store.add_message(tid, "assistant", "ok", steps=[{**step, "display": {"bars": huge}}])
    got = store.get_thread(tid)["messages"][1]["steps"][0]
    assert "display" not in got and got["display_dropped"] is True


@pytest.mark.parametrize(
    ("symbol", "exchange", "expected"),
    [
        ("INFY", "NSE", ["INFY.NS", "INFY"]),
        ("infy", "BSE", ["INFY.BO", "INFY"]),
        ("AAPL", "US", ["AAPL"]),
        ("TCS.NS", "NSE", ["TCS.NS"]),
        ("^NSEI", "NSE", ["^NSEI"]),
        ("BTC/USDT", "NSE", ["BTC-USD"]),
        ("BRK-B", "US", ["BRK-B"]),
        ("ZOMATO", "NSE", ["ETERNAL.NS", "ETERNAL"]),  # renamed listing
        ("BAJAJ-AUTO", "NSE", ["BAJAJ-AUTO.NS", "BAJAJ-AUTO"]),  # a dash is not crypto
        ("SOL-USD", "NSE", ["SOL-USD"]),
        ("RELIANCE.BO", "NSE", ["RELIANCE.BO"]),
    ],
)
def test_symbol_resolution(symbol: str, exchange: str, expected: list[str]) -> None:
    assert resolve_candidates(symbol, exchange) == expected


async def test_technical_analysis_from_bars(monkeypatch) -> None:
    n = 120
    bars = [
        {
            "time": 1_700_000_000 + i * 86400,
            "open": 100 + i * 0.5,
            "high": 101 + i * 0.5,
            "low": 99 + i * 0.5,
            "close": 100 + i * 0.5 + (1 if i % 2 else -1),
            "volume": 1000.0,
        }
        for i in range(n)
    ]
    monkeypatch.setattr(
        technical_tool,
        "load_bars",
        lambda *a, **k: {
            "symbol": "X.NS",
            "currency": "INR",
            "bars": bars,
            "daily": True,
            "tz_offset_secs": 0,
        },
    )
    out = await technical_tool.TechnicalAnalysisTool().execute(symbol="X")
    result, display = split_display(out)
    assert result["resolved_symbol"] == "X.NS" and result["not_enough_history_for"] == []
    assert result["latest"]["rsi_14"] > 55  # a steady (if jagged) uptrend
    assert result["readout"]["price_vs_sma_50"] == "above"
    assert len(display["bars"]) == n and set(display["panes"]) == {"RSI 14", "MACD"}
    # Warm-up rows are omitted rather than sent as NaN: SMA 50 starts at the 50th bar.
    assert len(display["overlays"]["SMA 50"]) == n - 49
    assert "mock" not in json.dumps(result)


async def test_market_data_reports_bad_arguments_without_network() -> None:
    tool = market_data_tool.MarketDataTool()
    assert "period must be" in (await tool.execute(symbol="X", period="9y"))["error"]
    assert "interval must be" in (await tool.execute(symbol="X", interval="2s"))["error"]
