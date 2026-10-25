from aletheia.core.events.bus import Event, Topics
from aletheia.core.models import AgentEvent, AgentName


class _Socket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


async def test_record_event_persists_broadcasts_and_is_observable(run_service) -> None:
    sock = _Socket()
    run_service.register_socket("r1", sock)
    seen: list[Event] = []

    async def spy(e: Event) -> None:
        seen.append(e)

    run_service.bus.subscribe(Topics.RUN_EVENT, spy)

    saved: list[AgentEvent] = []
    run_service.sqlite_store.save_agent_event = saved.append  # type: ignore[method-assign]

    await run_service.record_event(AgentEvent(run_id="r1", agent=AgentName.ORACLE, message="hi"))

    assert [e.message for e in saved] == ["hi"]  # persisted
    assert sock.sent and sock.sent[0]["message"] == "hi"  # fanned out to the socket
    assert seen and seen[0].payload.message == "hi"  # and visible to any other subscriber


async def test_a_failing_subscriber_does_not_block_persistence(run_service) -> None:
    async def boom(e: Event) -> None:
        raise RuntimeError("subscriber bug")

    saved: list[AgentEvent] = []
    run_service.sqlite_store.save_agent_event = saved.append  # type: ignore[method-assign]
    run_service.bus.subscribe(Topics.RUN_EVENT, boom)
    await run_service.record_event(AgentEvent(run_id="r2", agent=AgentName.ORACLE, message="ok"))

    assert [e.message for e in saved] == ["ok"]
