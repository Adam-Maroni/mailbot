"""Story 6-11 (F17 closure): worker-process pipeline-runtime init regression test.

The bug: Story 6-6 moved ingest-tick dispatch from the api process (FastAPI
lifespan) into the worker process (`mailbot_api/worker.py`) but did NOT port
the per-process module-state init (policy snapshot, sensitivity patterns,
adapter registry, budget guard, pause state). Every ingest tick then crashed
at `_assert_qwen_only_per_call` because `snapshot_for_dispatch()` returned
RuntimeError("policy not loaded") in the worker's Python interpreter.

This test guards against re-introduction by booting a worker-shaped runtime
init AND running `process_email` against a real adapter at the SDK boundary
(Middleware-Real-Bootstrap rule per architecture §2.4.7). If the init fails
to populate the policy snapshot or the adapter registry, `process_email` will
short-circuit at the sensitivity step with the F17 signature — and this test
will fail before the regression ships.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.db.connection import execute_write, fetchall, fetchone
from mailbot_api.db.queries import EMAIL_DERIVED_FIELDS_SELECT
from mailbot_api.ingest.pipeline import init_pipeline_runtime, process_email
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
    snapshot_for_dispatch,
)
from mailbot_api.router.registry import (
    _reset_registry_for_test,
    get_adapter,
    register_adapter,
)

_QWEN = "qwen2.5:3b-instruct-q4_K_M"


@pytest.fixture
def _clean_state():
    """Reset module-level singletons between tests (mirrors other e2e tests)."""
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    yield
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()


class _FakeQwenSensitivityAdapter:
    """Minimal real-shape adapter for the sensitivity_class path.

    Returns a scripted JSON payload matching `SensitivityClassOutput` so the
    Router's `model_validate_json` step succeeds. Registered at the SDK
    boundary via `register_adapter` — Middleware-Real-Bootstrap pattern, the
    Router itself is NOT mocked.
    """

    def __init__(self) -> None:
        self.model_id = _QWEN
        self.call_count = 0

    async def call(
        self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0
    ) -> AdapterResponse:
        self.call_count += 1
        payload = {
            "sensitivity": "normal",
            "confidence": 0.92,
            "reason": "ordinary correspondence",
        }
        return AdapterResponse(
            text=json.dumps(payload),
            tokens_in=10,
            tokens_out=5,
            cached_tokens_in=0,
            latency_ms=15,
            raw={"mock": True},
        )


def _point_env_at_repo_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point MAILBOT_POLICY_PATH + MAILBOT_PATTERNS_PATH at the in-repo YAMLs.

    Mirrors the env-setup pattern in `test_chat_completions_endpoint.py` and
    `test_db_connection.py`. The default `/app/router/*.yaml` paths only exist
    inside the container; tests need the repo-root paths.
    """
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("MAILBOT_POLICY_PATH", str(repo_root / "router" / "policy.yaml"))
    monkeypatch.setenv(
        "MAILBOT_PATTERNS_PATH",
        str(repo_root / "router" / "sensitivity_patterns.yaml"),
    )


async def test_init_pipeline_runtime_populates_per_process_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: Any,
) -> None:
    """AC-3: `init_pipeline_runtime` populates the per-process module-state
    that `process_email` → `classify_sensitivity` → `snapshot_for_dispatch`
    depends on.

    Regression guard for F17: pre-Story-6-11 worker.main only called
    `apply_pending_migrations` and left the policy snapshot, adapter registry,
    sensitivity patterns, budget guard, and pause state uninitialized. Every
    ingest tick then crashed at the FR-2.5 per-call safeguard. This assertion
    set catches that exact gap.
    """
    db_path = str(tmp_path / "test.db")
    _point_env_at_repo_yaml(monkeypatch)

    await init_pipeline_runtime(db_path)

    # Policy snapshot must be readable + `sensitivity_class` entry present.
    policy = snapshot_for_dispatch()
    assert (
        policy.tasks.get("sensitivity_class") is not None
    ), "init_pipeline_runtime must load policy.yaml with sensitivity_class entry"
    assert policy.tasks["sensitivity_class"].model == _QWEN

    # Adapter registry must be populated for the Qwen model id.
    adapter = get_adapter(_QWEN)
    assert adapter.model_id == _QWEN, "init_pipeline_runtime must register Ollama Qwen adapter"

    # nomic-embed-text (Story 3-4 — Finding 6) must also be registered;
    # ingest pipeline embedding step depends on it.
    embed_adapter = get_adapter("nomic-embed-text")
    assert embed_adapter.model_id == "nomic-embed-text"


async def test_process_email_sensitivity_class_dispatches_through_real_router(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: Any,
) -> None:
    """AC-3: `process_email` end-to-end against a real `ModelAdapter` boundary.

    Mocks ONLY the OllamaAdapter at the SDK boundary (Middleware-Real-Bootstrap
    per architecture §2.4.7). The Router itself, sensitivity classifier,
    pattern overrides, audit writer, and SQLite writes are all real.

    This test would FAIL pre-Story-6-11 because the worker (here simulated by
    calling `init_pipeline_runtime` then `process_email` in the same loop)
    didn't initialize the policy snapshot. It now PASSES because the structural
    init gap is closed.
    """
    db_path = str(tmp_path / "test.db")
    _point_env_at_repo_yaml(monkeypatch)

    # Boot the per-process runtime — the load-bearing step Story 6-6 missed
    # in the worker.
    await init_pipeline_runtime(db_path)

    # Override the registered Qwen adapter with our scripted shape. The real
    # registry init happens inside `init_pipeline_runtime`, but `register_adapter`
    # is idempotent + replaces — this is the Middleware-Real-Bootstrap rule:
    # the SDK boundary is fake, everything else is real.
    fake_qwen = _FakeQwenSensitivityAdapter()
    register_adapter(_QWEN, fake_qwen)

    # Also override nomic-embed-text so the pipeline's embedding step doesn't
    # try to hit a real Ollama server. The remaining ingest steps (coarse,
    # summary, importance, action_extraction) need Anthropic — which we don't
    # care about for this regression test; we assert ONLY on the sensitivity
    # step's success (which is where F17 broke). The pipeline will fail at a
    # downstream step due to no Anthropic adapter; that's expected here.

    # Seed one email row.
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview) "
        "VALUES (?, ?, ?, ?, ?)",
        (
            "f17-regression-seed",
            "2026-06-04T00:00:00Z",
            "Regression test email",
            "test@example.com",
            "Body for regression test of F17 closure.",
        ),
    )

    result = await process_email(email_id="f17-regression-seed", db_path=db_path)

    # The sensitivity step MUST have completed (the F17 failure point). The
    # fake Qwen adapter is bound to multiple Qwen-pinned tasks in policy.yaml
    # (sensitivity_class + coarse_class + fine_class), so call_count >= 1 is
    # the regression signal — F17 had ALL sensitivity calls fail with 0 hits
    # at this adapter.
    assert fake_qwen.call_count >= 1, (
        "sensitivity_class adapter must have been invoked; "
        f"got call_count={fake_qwen.call_count}. If 0, the worker-process init "
        "regression has returned — policy snapshot is unpopulated."
    )

    # The emails row MUST have sensitivity + sensitivity_at populated post-tick.
    row = await fetchone(db_path, EMAIL_DERIVED_FIELDS_SELECT, ("f17-regression-seed",))
    assert row is not None
    sensitivity, sensitivity_prompt_v, sensitivity_conf, sensitivity_model, sensitivity_at = row[:5]
    assert sensitivity == "normal"
    assert sensitivity_at is not None
    assert sensitivity_conf == pytest.approx(0.92)
    assert sensitivity_model == _QWEN

    # A successful router_calls audit row MUST have been written with the
    # F17-canary signature: task_type='sensitivity_class' AND
    # outcome IN ('ok', 'retry_recovered'). This is the AC-2 audit-trail
    # assertion lifted into the test harness.
    audit_rows = await fetchall(
        db_path,
        "SELECT task_type, outcome FROM router_calls WHERE task_type = ?",
        ("sensitivity_class",),
    )
    assert len(audit_rows) >= 1, "no router_calls row written for sensitivity_class"
    outcomes = {row[1] for row in audit_rows}
    assert outcomes & {"ok", "retry_recovered"}, (
        f"sensitivity_class router_calls outcomes={outcomes}; "
        "expected at least one ok or retry_recovered (the F17 failure had ALL 'failed')"
    )

    # process_email's `result.failed_at` MAY be a downstream step (coarse_class,
    # summary, etc.) because we didn't register Anthropic adapters — but it
    # MUST NOT be 'sensitivity_class' (the F17 failure point).
    assert result.failed_at != "sensitivity_class", (
        f"process_email failed at sensitivity_class — F17 regression! "
        f"error={result.error}"
    )
