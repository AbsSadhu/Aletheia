"""aletheia/core/events/__init__.py"""

from aletheia.core.events.bus import Event, EventBus, Topics, get_event_bus, reset_event_bus

# Legacy aliases for any code that imported the old names
AletheiaEvent = Event
EventType = Topics

__all__ = [
    "Event",
    "EventBus",
    "Topics",
    "get_event_bus",
    "reset_event_bus",
    # legacy aliases
    "AletheiaEvent",
    "EventType",
]
