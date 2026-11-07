import json
from typing import Any, Dict


class StreamEvent:
    def __init__(self, event_type: str, data: Dict[str, Any]):
        self.event_type = event_type
        self.data = data

    def to_sse(self) -> str:
        return f"event: {self.event_type}\ndata: {json.dumps(self.data)}\n\n"
