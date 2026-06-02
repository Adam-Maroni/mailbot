"""GraphWriteAdapter Protocol + test doubles — Story 4-4.

The drainer dispatches via this Protocol. Story 4-5 implements the real
OutlookGraphWriteAdapter that hits Microsoft Graph. For Story 4-4, the
FakeGraphWriteAdapter is the default — happy-path tests run against it.
FailingGraphWriteAdapter is a test helper for failure-path coverage.
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


class GraphWriteAdapter(Protocol):
    """Story 4-5 implements this against real Microsoft Graph endpoints."""

    async def apply(self, row: "PendingActionRow") -> GraphApplyResult: ...


class FakeGraphWriteAdapter:
    """Always returns ok=True. Used by Story 4-4's drainer when no real adapter
    is registered + by happy-path tests."""

    async def apply(self, row: "PendingActionRow") -> GraphApplyResult:
        return GraphApplyResult(ok=True, error=None, retry_count=0)


class FailingGraphWriteAdapter:
    """Always returns ok=False with the configured error message — for
    failure-path tests in `test_drainer.py`."""

    def __init__(self, error: str = "forced_failure", retry_count: int = 0) -> None:
        self._error = error
        self._retry_count = retry_count

    async def apply(self, row: "PendingActionRow") -> GraphApplyResult:
        return GraphApplyResult(ok=False, error=self._error, retry_count=self._retry_count)


__all__ = [
    "FailingGraphWriteAdapter",
    "FakeGraphWriteAdapter",
    "GraphApplyResult",
    "GraphWriteAdapter",
]
