from __future__ import annotations

from datetime import UTC, datetime

from aletheia.core.execution.models import ExecutionMode, ExecutionState
from aletheia.core.execution.storage import ExecutionStorage


class LiveExecutionGate:
    def __init__(self, storage: ExecutionStorage) -> None:
        self.storage = storage

    def get_state(self) -> ExecutionState:
        return self.storage.get_state()

    def set_mode(
        self,
        mode: ExecutionMode,
        *,
        confirm: bool = False,
        paper_observation_days: int = 0,
    ) -> ExecutionState:
        state = self.storage.get_state()
        if mode == ExecutionMode.LIVE:
            if not confirm:
                raise PermissionError("Live mode requires explicit confirmation.")
            if paper_observation_days < state.observation_days_required:
                raise PermissionError(
                    f"Live mode requires at least {state.observation_days_required} paper-trading days."
                )
            state.live_approved_at = datetime.now(UTC)

        state.mode = mode
        self.storage.save_state(state)
        return state

    def pause(self) -> ExecutionState:
        state = self.storage.get_state()
        state.paused = True
        self.storage.save_state(state)
        return state

    def resume(self) -> ExecutionState:
        state = self.storage.get_state()
        state.paused = False
        self.storage.save_state(state)
        return state

    def assert_order_allowed(self, target_mode: ExecutionMode | None = None) -> ExecutionState:
        state = self.storage.get_state()
        if state.paused:
            raise PermissionError("Execution is paused.")
        if target_mode == ExecutionMode.LIVE and state.mode != ExecutionMode.LIVE:
            raise PermissionError("Live execution is not enabled.")
        return state
