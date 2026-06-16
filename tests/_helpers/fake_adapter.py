"""Scripted ``ModelAdapter`` test double (extracted from
``tests/unit/router/test_router.py`` per Story 9-3 CR-F6).

Yields one response (or raises one exception) per ``call`` from a
pre-loaded list. When the list is empty, raises RuntimeError so a test
that exhausted the script fails LOUDLY rather than silently retrying
under the failure chain.

Story 9-3 tests `test_oneshot_override_sensitivity_gate.py`,
`test_oneshot_override_budget_gate.py`, `test_oneshot_yaml_equivalence.py`,
and `test_oneshot_override_cache_hit_audit.py` import this directly
rather than reach into another test module.
"""

from __future__ import annotations

from typing import Any

from mailbot_api.router.models import AdapterResponse


class FakeAdapter:
    """Scripted ModelAdapter — yields one response (or raises) per ``call``."""

    def __init__(
        self,
        responses: list[AdapterResponse | BaseException] | None = None,
        model_id: str = "fake-model",
    ) -> None:
        self.responses: list[AdapterResponse | BaseException] = responses or []
        self.model_id = model_id
        self.call_log: list[dict[str, Any]] = []

    async def call(
        self,
        system: str,
        user: str,
        max_tokens_out: int,
        temperature: float = 0.0,
    ) -> AdapterResponse:
        self.call_log.append(
            {
                "system": system,
                "user": user,
                "max_tokens_out": max_tokens_out,
                "temperature": temperature,
            }
        )
        if not self.responses:
            raise RuntimeError("FakeAdapter ran out of scripted responses")
        nxt = self.responses.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt
