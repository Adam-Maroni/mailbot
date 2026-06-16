"""Story 9-3 AC-5 — one-shot vs direct force_model equivalence.

The same (email, task, model) triple dispatched via:
  (a) one-shot override + ask_router(force_model=None)
  (b) direct ask_router(force_model=<model>)

…must produce equivalent `router_calls` rows EXCEPT for:
  - `model_chosen_reason` ("slash_command:one_shot:adam" vs "override:api:force_model")
  - `ts` (microsecond-precision timestamps differ across calls)

Other 16 columns (model_chosen, task_type, tokens_in/out, cost, outcome,
caller_origin, etc.) must match. Confirms the override path produces an
audit row indistinguishable from a direct API force_model except in the
intent-distinguishing fields.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.actions.sensitivity_tokens import _clear_registry_for_tests
from mailbot_api.db.connection import execute_write, fetchall
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
version: "test-equiv-v1"

tasks:
  draft_reply:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 1024
    lane: "interactive"
    sensitivity: "any"
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


async def _seed_email(db_path: str, *, graph_id: str) -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview, "
        "sensitivity, sensitivity_at, sensitivity_prompt_v, sensitivity_conf, sensitivity_model) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            graph_id,
            "2026-06-15T00:00:00Z",
            "test",
            "x@y.com",
            "preview",
            "normal",
            "2026-06-15T00:01:00Z",
            "v1",
            0.9,
            _QWEN,
        ),
    )


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


async def test_oneshot_vs_direct_force_model_audit_row_equivalence(
    tmp_path: Path,
    _clean_state: None,
) -> None:
    """AC-5: equivalent (email, task, model) triple dispatched via
    one-shot vs direct force_model produces equivalent router_calls rows
    EXCEPT for model_chosen_reason + ts."""
    db_path = _setup(tmp_path)
    await _seed_email(db_path, graph_id="email-equiv-1")

    from tests._helpers.fake_adapter import FakeAdapter

    register_adapter(_HAIKU, FakeAdapter([_good_response()], model_id=_HAIKU))

    # --- Path A: one-shot override + ask_router(force_model=None) ---
    _set_oneshot_override(model=_HAIKU, ttl_seconds=300, session_id="test")
    result_a = await ask_router(
        "draft_reply", _content(), db_path=db_path, email_id="email-equiv-1"
    )
    assert result_a.ok is True, f"path A failed: {result_a}"

    # Reset adapter scripted responses for path B
    register_adapter(_HAIKU, FakeAdapter([_good_response()], model_id=_HAIKU))

    # --- Path B: direct ask_router(force_model=<haiku>) ---
    result_b = await ask_router(
        "draft_reply",
        _content(),
        db_path=db_path,
        email_id="email-equiv-1",
        force_model=_HAIKU,
    )
    assert result_b.ok is True, f"path B failed: {result_b}"

    # --- Compare the two router_calls rows ---
    rows = await fetchall(
        db_path,
        "SELECT ts, task_type, prompt_version, model_chosen, model_chosen_reason, "
        "  tokens_in, tokens_out, cached_tokens_in, cost_usd_estimated, latency_ms, "
        "  outcome, caller_verb, caller_origin, email_id, "
        "  sensitivity_grant_id, sensitivity_grant_minted_at, "
        "  tool_calls_count, tool_calls_summary "
        "FROM router_calls ORDER BY ts ASC",
        (),
    )
    assert len(rows) == 2, f"expected 2 rows; got {len(rows)}"

    row_a = rows[0]
    row_b = rows[1]

    # CR-F5: 15 columns checked, 2 differ by design, 1 excluded by design = 18 total.
    # Excluded indices:
    #   - Column 0 = ts: differs (microsecond-precision timestamps from two live calls)
    #   - Column 4 = model_chosen_reason: differs by design (one-shot vs OVERRIDE_API)
    #   - Column 9 = latency_ms: excluded by design (genuinely varies per dispatch
    #     even on equivalent inputs; this is a "skip" not a "must match")
    # The 15 checked columns are everything else: task_type / prompt_version /
    # model_chosen / tokens_in/out / cached_tokens_in / cost / outcome /
    # caller_verb / caller_origin / email_id / sensitivity_grant_* / tool_calls_*
    for col_idx in (1, 2, 3, 5, 6, 7, 8, 10, 11, 12, 13, 14, 15, 16, 17):
        assert row_a[col_idx] == row_b[col_idx], (
            f"column {col_idx} differs: row_a={row_a[col_idx]!r}, row_b={row_b[col_idx]!r}"
        )

    # Verify the two distinguishing columns differ in the EXPECTED way:
    assert row_a[4] == "slash_command:one_shot:adam"
    assert row_b[4] == "override:api:force_model"
    # ts may differ in microseconds; they're both valid Z-suffixed ISO timestamps.
    assert row_a[0].endswith("Z")
    assert row_b[0].endswith("Z")
    # And both rows recorded the SAME model_chosen
    assert row_a[3] == _HAIKU
    assert row_b[3] == _HAIKU
