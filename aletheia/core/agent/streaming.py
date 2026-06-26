import json
from typing import Any, Dict

class StreamEvent:
    def __init__(self, event_type: str, data: Dict[str, Any]):
        self.event_type = event_type
        self.data = data

    def to_sse(self) -> str:
        return f"event: {self.event_type}\ndata: {json.dumps(self.data)}\n\n"

class AgentStreamer:
    """Helper to yield SSE events during the ReAct loop."""
    
    def __init__(self):
        self.queue = []

    def push_thought(self, content: str):
        self.queue.append(StreamEvent("thought", {"content": content}))

    def push_tool_call(self, tool_name: str, arguments: dict):
        self.queue.append(StreamEvent("tool_call", {"tool": tool_name, "arguments": arguments}))

    def push_tool_result(self, tool_name: str, result: Any):
        self.queue.append(StreamEvent("tool_result", {"tool": tool_name, "result": result}))

    def push_final_answer(self, content: str):
        self.queue.append(StreamEvent("final_answer", {"content": content}))

    def push_error(self, message: str):
        self.queue.append(StreamEvent("error", {"message": message}))
