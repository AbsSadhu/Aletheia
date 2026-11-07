"""A run is over once it is completed, partial or failed; the socket must say so for all three."""

import pytest
from fastapi.testclient import TestClient

from aletheia.core.api.dependencies import get_run_service
from aletheia.core.main import app
from aletheia.core.models import RunResult, RunStatus, RunSummary


@pytest.mark.parametrize(
    ("status", "terminal"),
    [
        (RunStatus.PENDING, False),
        (RunStatus.RUNNING, False),
        (RunStatus.PARTIAL, True),
        (RunStatus.COMPLETED, True),
        (RunStatus.FAILED, True),
    ],
)
def test_is_terminal(status: RunStatus, terminal: bool) -> None:
    assert status.is_terminal is terminal


def test_socket_opened_after_a_partial_run_finishes_reports_stream_complete() -> None:
    summary = RunSummary(status=RunStatus.PARTIAL, prompt="partial run")
    get_run_service().sqlite_store.upsert_run(summary, RunResult(summary=summary))

    with (
        TestClient(app) as client,
        client.websocket_connect(f"/api/v1/ws/runs/{summary.run_id}") as ws,
    ):
        assert ws.receive_json()["message"] == "stream_complete"
