"""Story 9-4 AC-2 + AC-3 — persistent override audit-reason emission +
cross-task isolation + one-shot precedence regression tests.

Verifies the per-task provenance contract that closes the OQ-2 gap:
when a task's merged policy entry came from `router/policy.user-overrides.yaml`
(Story 9-1 shallow-leaf merge), the `router_calls` audit row carries
`model_chosen_reason=ModelChosenReason.OVERRIDE_SLASH_PERSISTENT.value`
INSTEAD of `policy_default(task)`. Non-overridden sibling tasks remain
unaffected (no provenance bleed).

Also verifies the OQ-4 precedence: when both a one-shot AND a persistent
override are active for the same task, the one-shot wins for the very
next call (and consumes), then the persistent override takes effect on
subsequent calls.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.db.connection import fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router import ask_router
from mailbot_api.router.audit_vocab import ModelChosenReason, policy_default
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
from tests._helpers.fake_adapter import FakeAdapter

_OPUS = "claude-opus-4-7"
_HAIKU = "claude-haiku-4-5-20251001"
_QWEN = "qwen2.5:3b-instruct-q4_K_M"


_BASELINE_POLICY_YAML = f"""\
version: "test-persistent-v1"

tasks:
  draft_reply:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 1024
    lane: "interactive"
    sensitivity: "any"
  summary_short:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 512
    lane: "interactive"
    sensitivity: "any"
  coarse_class:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
"""

# Overrides only `draft_reply` → opus. The other two stay baseline.
_OVERRIDES_YAML = f"""\
tasks:
  draft_reply:
    model: {_OPUS}
"""


@pytest.fixture
def _clean_state() -> Any:
    _reset_policy_snapshot_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()
    yield
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()


def _setup(tmp_path: Path, *, with_overrides: bool) -> str:
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_BASELINE_POLICY_YAML, encoding="utf-8")
    if with_overrides:
        (tmp_path / "policy.user-overrides.yaml").write_text(
            _OVERRIDES_YAML, encoding="utf-8"
        )
        set_policy_snapshot(
            load_policy(policy_yaml, overrides_path=tmp_path / "policy.user-overrides.yaml")
        )
    else:
        set_policy_snapshot(load_policy(policy_yaml))
    return db_path


def _content_for_draft_reply() -> dict[str, Any]:
    return {
        "subject": "test",
        "sender": "x@y.com",
        "body_preview": "preview",
        "body": "body content",
        "thread_excerpt": "prior",
        "user_intent": "concise reply",
        "source_email": "From: x@y.com\nSubject: test\nBody: preview",
        "thread_context": "(empty thread)",
        "tone_signals": "(none)",
    }


def _content_for_coarse_class() -> dict[str, Any]:
    return {
        "subject": "test",
        "sender": "x@y.com",
        "body_preview": "preview",
        "body": "body content",
    }


_RESP_DRAFT_REPLY = AdapterResponse(
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

_RESP_COARSE_CLASS = AdapterResponse(
    text=json.dumps({"class_coarse": "newsletter", "confidence": 0.9}),
    tokens_in=10,
    tokens_out=5,
    cached_tokens_in=0,
    latency_ms=12,
    raw={"mock": True},
)


async def _last_audit_reason(db_path: str) -> str:
    """Read the `model_chosen_reason` from the most-recent router_calls row.
    Returns the string verbatim so the test can assert against enum .value."""
    row = await fetchone(
        db_path,
        "SELECT model_chosen_reason FROM router_calls ORDER BY id DESC LIMIT 1",
    )
    assert row is not None, "no router_calls rows recorded"
    reason = row[0]
    assert isinstance(reason, str)
    return reason


async def _last_model_used(db_path: str) -> str:
    row = await fetchone(
        db_path,
        "SELECT model_chosen FROM router_calls ORDER BY id DESC LIMIT 1",
    )
    assert row is not None
    model = row[0]
    assert isinstance(model, str)
    return model


# ---------------------------------------------------------------------------
# AC-2 — persistent override emits OVERRIDE_SLASH_PERSISTENT in audit log
# ---------------------------------------------------------------------------


async def test_overridden_task_emits_override_slash_persistent(
    tmp_path: Path, _clean_state: None
) -> None:
    """AC-2: a task in `policy.overrides_applied` writes
    OVERRIDE_SLASH_PERSISTENT to router_calls.model_chosen_reason."""
    db_path = _setup(tmp_path, with_overrides=True)
    register_adapter(_OPUS, FakeAdapter(responses=[_RESP_DRAFT_REPLY], model_id=_OPUS))
    register_adapter(_HAIKU, FakeAdapter(responses=[_RESP_DRAFT_REPLY], model_id=_HAIKU))

    result = await ask_router(
        task_type="draft_reply",
        content=_content_for_draft_reply(),
        db_path=db_path,
        caller_origin="test",
    )
    assert result.ok, f"unexpected failure: {result.error}"
    # Effective model came from the overrides file: opus, not baseline haiku.
    assert await _last_model_used(db_path) == _OPUS
    # Audit reason reflects Adam's persistent override, not policy_default.
    assert (
        await _last_audit_reason(db_path)
        == ModelChosenReason.OVERRIDE_SLASH_PERSISTENT.value
    )


async def test_non_overridden_sibling_emits_policy_default(
    tmp_path: Path, _clean_state: None
) -> None:
    """AC-3 isolation: a NON-overridden task keeps the `policy_default`
    audit reason even when a sibling task is overridden — no provenance
    bleed across tasks."""
    db_path = _setup(tmp_path, with_overrides=True)
    register_adapter(_QWEN, FakeAdapter(responses=[_RESP_COARSE_CLASS], model_id=_QWEN))

    result = await ask_router(
        task_type="coarse_class",
        content=_content_for_coarse_class(),
        db_path=db_path,
        caller_origin="test",
    )
    assert result.ok, f"unexpected failure: {result.error}"
    assert await _last_model_used(db_path) == _QWEN
    # NOT OVERRIDE_SLASH_PERSISTENT — coarse_class is not in overrides_applied.
    assert await _last_audit_reason(db_path) == policy_default("coarse_class")


async def test_baseline_only_emits_policy_default(
    tmp_path: Path, _clean_state: None
) -> None:
    """AC-3 baseline: without ANY override file, every task emits
    `policy_default` — confirms the new audit-reason branch does not fire
    when `policy.overrides_applied` is empty."""
    db_path = _setup(tmp_path, with_overrides=False)
    register_adapter(_HAIKU, FakeAdapter(responses=[_RESP_DRAFT_REPLY], model_id=_HAIKU))

    result = await ask_router(
        task_type="draft_reply",
        content=_content_for_draft_reply(),
        db_path=db_path,
        caller_origin="test",
    )
    assert result.ok, f"unexpected failure: {result.error}"
    assert await _last_audit_reason(db_path) == policy_default("draft_reply")


# ---------------------------------------------------------------------------
# OQ-4 / AC-3 — one-shot wins over persistent on the very next call
# ---------------------------------------------------------------------------


async def test_oneshot_wins_over_persistent_for_next_call_then_consumes(
    tmp_path: Path, _clean_state: None
) -> None:
    """OQ-4: a one-shot override consumed on the first call wins over
    the persistent override. After consumption, subsequent calls fall
    through to the persistent override.

    Sequence:
      1) /model haiku                           (one-shot armed)
      2) /model draft_reply opus  (persistent override applied to file)
      3) First ask_router(draft_reply) → uses HAIKU, audit OVERRIDE_SLASH_ONE_SHOT,
         one-shot consumed
      4) Second ask_router(draft_reply) → uses OPUS (from persistent),
         audit OVERRIDE_SLASH_PERSISTENT
    """
    db_path = _setup(tmp_path, with_overrides=True)
    # Three responses across two adapters: haiku for the one-shot call,
    # opus for the persistent-override call. (The third haiku response is
    # never used; safety against an unexpected fallback.)
    register_adapter(
        _HAIKU, FakeAdapter(responses=[_RESP_DRAFT_REPLY, _RESP_DRAFT_REPLY], model_id=_HAIKU)
    )
    register_adapter(_OPUS, FakeAdapter(responses=[_RESP_DRAFT_REPLY], model_id=_OPUS))

    # Arm one-shot to HAIKU.
    _set_oneshot_override(model=_HAIKU, session_id=None)

    # First call: one-shot wins, consumes.
    r1 = await ask_router(
        task_type="draft_reply",
        content=_content_for_draft_reply(),
        db_path=db_path,
        caller_origin="test",
    )
    assert r1.ok
    assert await _last_model_used(db_path) == _HAIKU
    assert (
        await _last_audit_reason(db_path) == ModelChosenReason.OVERRIDE_SLASH_ONE_SHOT.value
    )

    # Second call: one-shot consumed, persistent override fires.
    r2 = await ask_router(
        task_type="draft_reply",
        content=_content_for_draft_reply(),
        db_path=db_path,
        caller_origin="test",
    )
    assert r2.ok
    assert await _last_model_used(db_path) == _OPUS
    assert (
        await _last_audit_reason(db_path)
        == ModelChosenReason.OVERRIDE_SLASH_PERSISTENT.value
    )


# ---------------------------------------------------------------------------
# AC-2 sibling carve-out — cache-hit on overridden task preserves audit reason
# ---------------------------------------------------------------------------


_BASELINE_POLICY_YAML_WITH_CACHE = f"""\
version: "test-persistent-cache-v1"

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

_OVERRIDES_YAML_DRAFT_OPUS = f"""\
tasks:
  draft_reply:
    model: {_OPUS}
"""


async def test_cache_hit_on_overridden_task_preserves_persistent_reason(
    tmp_path: Path, _clean_state: None
) -> None:
    """Story 9-4 sibling carve-out (mirrors Story 9-3 CR-F1): when a task
    is in `policy.overrides_applied` AND the call hits the response
    cache, the audit row MUST preserve OVERRIDE_SLASH_PERSISTENT — the
    cache-hit branch is narrowed via the threaded _persistent_engaged
    flag so Adam's intent is not hidden behind CACHE_HIT."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_BASELINE_POLICY_YAML_WITH_CACHE, encoding="utf-8")
    overrides_path = tmp_path / "policy.user-overrides.yaml"
    overrides_path.write_text(_OVERRIDES_YAML_DRAFT_OPUS, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml, overrides_path=overrides_path))

    register_adapter(_OPUS, FakeAdapter(responses=[_RESP_DRAFT_REPLY], model_id=_OPUS))

    content = _content_for_draft_reply()

    # First call: real dispatch, populates the cache, writes
    # OVERRIDE_SLASH_PERSISTENT.
    r1 = await ask_router(
        task_type="draft_reply",
        content=content,
        db_path=db_path,
        caller_origin="test",
    )
    assert r1.ok
    assert (
        await _last_audit_reason(db_path)
        == ModelChosenReason.OVERRIDE_SLASH_PERSISTENT.value
    )

    # Second call: same input → cache hit. The narrowed carve-out keeps
    # OVERRIDE_SLASH_PERSISTENT on the audit row (NOT CACHE_HIT).
    r2 = await ask_router(
        task_type="draft_reply",
        content=content,
        db_path=db_path,
        caller_origin="test",
    )
    assert r2.ok
    assert (
        await _last_audit_reason(db_path)
        == ModelChosenReason.OVERRIDE_SLASH_PERSISTENT.value
    ), "cache-hit branch clobbered Adam's persistent override audit trail"


async def test_cache_hit_on_non_overridden_task_writes_cache_hit(
    tmp_path: Path, _clean_state: None
) -> None:
    """Sibling control test: without any persistent override (or with the
    override on a different task), cache-hit DOES write CACHE_HIT — the
    narrowed carve-out is correctly scoped."""
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_BASELINE_POLICY_YAML_WITH_CACHE, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml))

    register_adapter(_HAIKU, FakeAdapter(responses=[_RESP_DRAFT_REPLY], model_id=_HAIKU))

    content = _content_for_draft_reply()

    # Populate cache.
    r1 = await ask_router(
        task_type="draft_reply",
        content=content,
        db_path=db_path,
        caller_origin="test",
    )
    assert r1.ok
    assert await _last_audit_reason(db_path) == policy_default("draft_reply")

    # Cache hit on second call writes CACHE_HIT (the default clobber path).
    r2 = await ask_router(
        task_type="draft_reply",
        content=content,
        db_path=db_path,
        caller_origin="test",
    )
    assert r2.ok
    assert await _last_audit_reason(db_path) == ModelChosenReason.CACHE_HIT.value


# ---------------------------------------------------------------------------
# CR-F5 — 3-way regression: degraded mode + persistent override + cache hit
# ---------------------------------------------------------------------------


_BASELINE_POLICY_YAML_WITH_CACHE_HAIKU_BASE = f"""\
version: "test-3way-v1"

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

_OVERRIDES_YAML_DRAFT_OPUS_3WAY = f"""\
tasks:
  draft_reply:
    model: {_OPUS}
"""


async def test_degraded_demotes_persistently_overridden_task_reason_preserved_on_cache_hit(
    tmp_path: Path, _clean_state: None
) -> None:
    """CR-F5 LOW (sonnet-4-6 reviewer): the 3-way interaction —
    persistent override sets draft_reply to opus; degraded mode fires and
    demotes opus→haiku; the resulting audit reason is
    `degraded:opus→haiku` (NOT OVERRIDE_SLASH_PERSISTENT, because the
    degraded-demotion clobber at router.py:~322 is the LAST writer before
    dispatch). A subsequent cache-hit on the same input preserves the
    demotion reason (NOT CACHE_HIT) because `_persistent_engaged=True`
    is still threaded and the narrowed clobber-carve-out respects it.

    This pins the audit-row provenance through the full 3-way layering
    without leaving Adam guessing why a previously-overridden task
    silently became a CACHE_HIT row after the budget guard tripped.
    """
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_BASELINE_POLICY_YAML_WITH_CACHE_HAIKU_BASE, encoding="utf-8")
    overrides_path = tmp_path / "policy.user-overrides.yaml"
    overrides_path.write_text(_OVERRIDES_YAML_DRAFT_OPUS_3WAY, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml, overrides_path=overrides_path))

    # Trigger degraded mode BEFORE the first call. After the override,
    # effective model = opus → degraded demotes to haiku → adapter called
    # is haiku.
    from mailbot_api.router.budget import get_guard

    await get_guard()._enter_degraded_mode(db_path)
    assert get_guard().is_degraded()

    register_adapter(_HAIKU, FakeAdapter(responses=[_RESP_DRAFT_REPLY], model_id=_HAIKU))

    content = _content_for_draft_reply()

    # Call 1: populates the cache. Effective model is opus per persistent
    # override, then degraded demotes to haiku. Audit reason is the
    # degraded-demotion string.
    r1 = await ask_router(
        task_type="draft_reply",
        content=content,
        db_path=db_path,
        caller_origin="test",
    )
    assert r1.ok
    assert await _last_model_used(db_path) == _HAIKU  # demoted target
    reason_1 = await _last_audit_reason(db_path)
    assert reason_1 == f"degraded:{_OPUS}→{_HAIKU}", (
        f"expected degraded-demotion reason, got {reason_1!r}"
    )

    # Call 2: same input → cache hit. The carve-out preserves the
    # degraded-demotion reason (NOT CACHE_HIT) because the persistent
    # override is still in force.
    r2 = await ask_router(
        task_type="draft_reply",
        content=content,
        db_path=db_path,
        caller_origin="test",
    )
    assert r2.ok
    reason_2 = await _last_audit_reason(db_path)
    assert reason_2 == f"degraded:{_OPUS}→{_HAIKU}", (
        f"cache-hit clobbered the degraded-demotion audit reason: got {reason_2!r}"
    )
