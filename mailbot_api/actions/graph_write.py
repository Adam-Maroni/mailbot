"""GraphWriteAdapter Protocol + test doubles — Story 4-4 (+ Story 10-2).

The drainer dispatches via this Protocol. Story 4-5 implements the real
OutlookGraphWriteAdapter that hits Microsoft Graph. For Story 4-4, the
FakeGraphWriteAdapter is the default — happy-path tests run against it.
FailingGraphWriteAdapter is a test helper for failure-path coverage.

Story 10-2 extends the Protocol with `read_move_pre_state`: a read-only
Graph lookup of the message's current parentFolderId, called by the drainer
for move-family rows immediately before dispatch so the revert path has a
real source folder to move back to. Fail-closed contract: if the read fails,
the drainer marks the row failed (`pre_state_capture_failed:*`) and never
dispatches — a move without pre_state is irreversible-by-construction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from mailbot_api.actions.drainer import PendingActionRow


class GraphApplyResult(BaseModel):
    """Outcome of a single Graph dispatch attempt."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    error: str | None = None
    retry_count: int = 0


class GraphReadResult(BaseModel):
    """Outcome of a pre-state read (Story 10-2).

    `source_folder_id` is Graph's `parentFolderId` for the message — the only
    viable capture point per the 10-1 walk (the local emails table has no
    folder column).
    """

    model_config = ConfigDict(frozen=True)

    ok: bool
    source_folder_id: str | None = None
    error: str | None = None


class GraphWriteAdapter(Protocol):
    """Story 4-5 implements this against real Microsoft Graph endpoints."""

    async def apply(self, row: "PendingActionRow") -> GraphApplyResult: ...

    async def read_move_pre_state(self, email_id: str) -> GraphReadResult: ...


class FakeGraphWriteAdapter:
    """Always returns ok=True. Used by Story 4-4's drainer when no real adapter
    is registered + by happy-path tests.

    Story 10-2: `source_folder_id` configures the stubbed pre-state read for
    move-family drains (default is an obviously-fake marker value).
    """

    def __init__(self, source_folder_id: str = "fake-source-folder") -> None:
        self._source_folder_id = source_folder_id

    async def apply(self, row: "PendingActionRow") -> GraphApplyResult:
        return GraphApplyResult(ok=True, error=None, retry_count=0)

    async def read_move_pre_state(self, email_id: str) -> GraphReadResult:
        return GraphReadResult(ok=True, source_folder_id=self._source_folder_id)


class FailingGraphWriteAdapter:
    """Always returns ok=False with the configured error message — for
    failure-path tests in `test_drainer.py`.

    The pre-state read SUCCEEDS by default so dispatch-failure tests still
    reach `apply()`; pass `fail_pre_state_read=True` to fail the read instead
    (fail-closed path coverage).
    """

    def __init__(
        self,
        error: str = "forced_failure",
        retry_count: int = 0,
        *,
        fail_pre_state_read: bool = False,
        source_folder_id: str = "fake-source-folder",
    ) -> None:
        self._error = error
        self._retry_count = retry_count
        self._fail_pre_state_read = fail_pre_state_read
        self._source_folder_id = source_folder_id

    async def apply(self, row: "PendingActionRow") -> GraphApplyResult:
        return GraphApplyResult(ok=False, error=self._error, retry_count=self._retry_count)

    async def read_move_pre_state(self, email_id: str) -> GraphReadResult:
        if self._fail_pre_state_read:
            return GraphReadResult(ok=False, error=self._error)
        return GraphReadResult(ok=True, source_folder_id=self._source_folder_id)


__all__ = [
    "FailingGraphWriteAdapter",
    "FakeGraphWriteAdapter",
    "GraphApplyResult",
    "GraphReadResult",
    "GraphWriteAdapter",
]
