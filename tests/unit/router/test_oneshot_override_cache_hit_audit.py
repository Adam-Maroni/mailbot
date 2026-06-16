"""Story 9-3 CR-F1 regression — cache-hit on oneshot-engaged path preserves
OVERRIDE_SLASH_ONE_SHOT audit reason.

The bug CR-F1 caught: when `/model qwen` is armed and the next `ask_router`
call hits the response cache, the cache-hit path overwrote
`model_chosen_reason = CACHE_HIT`, clobbering `OVERRIDE_SLASH_ONE_SHOT` and
making Adam's `/model` intent invisible in the audit log. AC-2 mandates the
row carry `OVERRIDE_SLASH_ONE_SHOT.value`.

Fix: only overwrite to `CACHE_HIT` when `_oneshot_engaged is False`. When
engaged, the audit reason stays `OVERRIDE_SLASH_ONE_SHOT` — the row
reflects WHY (Adam's override) not HOW (cache served).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.actions.sensitivity_tokens import _clear_registry_for_tests
from mailbot_api.db.connection import fetchall
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router import ask_router
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import AdapterResponse
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter
from mailbot_api.verbs.router_control import (
    _reset_oneshot_override_for_test,
    _set_oneshot_override,
)

_HAIKU = "claude-haiku-4-5-20251001"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"


_POLICY_YAML = f"""\
version: "test-cr-f1-v1"

tasks:
  draft_reply:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 1024
    lane: "interactive"
    sensitivity: "any"
    response_cache_ttl_seconds: 300
"""


@pytest.fixture
def _clean_state() -> Any:
    _clear_registry_for_tests()
    _reset_registry_for_test()
    _reset_policy_snapshot_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()
    yield
    _clear_registry_for_tests()
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(_POLICY_YAML, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_path))
    return db_path


def _content() -> dict[str, Any]:
    return {
        "source_email": "From: x@y.com\nSubject: test\nBody: preview",
        "thread_context": "(empty)",
        "tone_signals": "(none)",
    }


def _good_response() -> AdapterResponse:
    return AdapterResponse(
        text=json.dumps(
            {
                "draft_body": "ok",
                "suggested_subject": "re: test",
                "tone_signals_used": [],
                "defender_warnings": [],
            }
        ),
        tokens_in=10,
        tokens_out=5,
        cached_tokens_in=0,
        latency_ms=12,
        raw={"mock": True},
    )


async def test_cache_hit_on_oneshot_engaged_preserves_override_slash_one_shot(
    tmp_path: Path,
    _clean_state: None,
) -> None:
    """CR-F1 regression: a cache-hit on a one-shot-engaged call must write
    `OVERRIDE_SLASH_ONE_SHOT` (NOT `CACHE_HIT`) to make Adam's `/model`
    intent visible in the audit log."""
    db_path = _setup(tmp_path)
    from tests._helpers.fake_adapter import FakeAdapter

    register_adapter(_HAIKU, FakeAdapter([_good_response()], model_id=_HAIKU))

    # First call (no override) — populates the cache.
    result1 = await ask_router("draft_reply", _content(), db_path=db_path)
    assert result1.ok is True

    # Arm the override and re-call with identical content — should hit cache.
    _set_oneshot_override(model=_HAIKU, ttl_seconds=300, session_id="test")
    result2 = await ask_router("draft_reply", _content(), db_path=db_path)
    assert result2.ok is True
    # Confirm we actually hit the cache (model_used has the +response_cache suffix).
    assert "response_cache" in result2.model_used

    # Two router_calls rows. The second is the cache-hit AND was on
    # `_oneshot_engaged=True` → must carry OVERRIDE_SLASH_ONE_SHOT, not CACHE_HIT.
    rows = await fetchall(
        db_path,
        "SELECT model_chosen, model_chosen_reason FROM router_calls ORDER BY ts ASC",
        (),
    )
    assert len(rows) == 2, f"expected 2 rows; got {len(rows)}"
    # Row 1 — first call, no override → policy_default
    assert rows[0][1] == "policy:draft_reply:default"
    # Row 2 — cache hit on engaged override → OVERRIDE_SLASH_ONE_SHOT (NOT cache:response_cache_hit)
    assert rows[1][1] == "slash_command:one_shot:adam", (
        f"CR-F1 regression: row 2 reason should be OVERRIDE_SLASH_ONE_SHOT "
        f"(Adam's intent), not CACHE_HIT (how cache served it); got {rows[1][1]!r}"
    )


async def test_cache_hit_without_oneshot_writes_cache_hit_audit_reason(
    tmp_path: Path,
    _clean_state: None,
) -> None:
    """Sibling test: a cache-hit on a NON-engaged call writes CACHE_HIT
    (the existing Story 2-7 contract — confirms the CR-F1 fix only narrows
    the carve-out)."""
    db_path = _setup(tmp_path)
    from tests._helpers.fake_adapter import FakeAdapter

    register_adapter(_HAIKU, FakeAdapter([_good_response()], model_id=_HAIKU))

    # Two back-to-back calls without override — second hits cache.
    result1 = await ask_router("draft_reply", _content(), db_path=db_path)
    assert result1.ok is True
    result2 = await ask_router("draft_reply", _content(), db_path=db_path)
    assert result2.ok is True
    assert "response_cache" in result2.model_used

    rows = await fetchall(
        db_path,
        "SELECT model_chosen_reason FROM router_calls ORDER BY ts ASC",
        (),
    )
    assert len(rows) == 2
    assert rows[0][0] == "policy:draft_reply:default"
    # No override engaged → cache-hit row carries CACHE_HIT (Story 2-7 behavior)
    assert rows[1][0] == "cache:response_cache_hit"
