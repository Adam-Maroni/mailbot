"""Story 3-5 AC-2, AC-3, AC-5, AC-6, AC-8: pipeline orchestrator end-to-end.

Uses real SQLite + real migrations + fake adapters registered for each task.
Middleware-Real-Bootstrap discipline per MailBot reframing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from mailbot_api.db.connection import execute_write, fetchall, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.db.queries import EMAIL_DERIVED_FIELDS_SELECT
from mailbot_api.ingest.pipeline import ProcessEmailResult, process_email
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import AdapterResponse, EmbeddingResponse
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter

_QWEN = "qwen2.5:3b-instruct-q4_K_M"
_HAIKU = "claude-haiku-4-5-20251001"
_NOMIC = "nomic-embed-text"


class _FakeAdapter:
    """Returns scripted JSON per call. Supports both call() and embed()."""

    def __init__(self, model_id: str, payloads: dict[str, dict[str, Any]]) -> None:
        self.model_id = model_id
        self._payloads = payloads  # task_type → payload dict
        self._embed_vector = [0.1] * 768
        self.call_log: list[dict[str, Any]] = []

    async def call(self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0) -> AdapterResponse:
        self.call_log.append({"system": system, "user": user})
        # Resolve which payload to return by inspecting the SYSTEM block content.
        # Each Story 3-2 prompt module has distinctive keywords in SYSTEM:
        if "sensitivity" in system.lower() and "normal" in system.lower():
            payload = self._payloads.get("sensitivity_class")
        elif "broad kind" in system.lower():
            payload = self._payloads.get("coarse_class")
        elif "refine the relationship type" in system.lower():
            payload = self._payloads.get("fine_class")
        elif "280 characters" in system.lower():
            payload = self._payloads.get("summary_short")
        elif "0–100 scale" in system.lower():
            payload = self._payloads.get("importance_scoring")
        elif "extract structured action items" in system.lower():
            payload = self._payloads.get("action_extraction")
        else:
            payload = None
        if payload is None:
            raise RuntimeError(f"No scripted payload for system={system[:80]!r}")
        return AdapterResponse(
            text=json.dumps(payload),
            tokens_in=10,
            tokens_out=5,
            cached_tokens_in=0,
            latency_ms=30,
            raw={"mock": True},
        )

    async def embed(self, text: str) -> EmbeddingResponse:
        return EmbeddingResponse(
            vector=self._embed_vector,
            dim=len(self._embed_vector),
            tokens_in=len(text.split()),
            latency_ms=15,
            raw={"mock": True},
        )


# Realistic policy fixture for Story 3-5: full 7-task taxonomy.
_POLICY_YAML = f"""\
version: "test-pipeline-v1"

tasks:
  sensitivity_class:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 128
    lane: "batch"
    sensitivity: "any"
  coarse_class:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
  fine_class:
    model: "{_QWEN}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 128
    lane: "batch"
    sensitivity: "any"
  summary_short:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 384
    lane: "batch"
    sensitivity: "any"
  importance_scoring:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 256
    lane: "batch"
    sensitivity: "any"
  action_extraction:
    model: "{_HAIKU}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 512
    lane: "batch"
    sensitivity: "any"
  embedding:
    model: "{_NOMIC}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 0
    lane: "batch"
    sensitivity: "any"
"""

_PAYLOADS_HUMAN = {
    "sensitivity_class": {"sensitivity": "normal", "confidence": 0.92, "reason": "ordinary"},
    "coarse_class": {"class_coarse": "human", "confidence": 0.88},
    "fine_class": {"class_fine": "professional", "confidence": 0.80},
    "summary_short": {"summary": "Friday meeting moved to Tuesday 2pm."},
    "importance_scoring": {"importance": 55, "signals": ["known_sender", "explicit_time"]},
    "action_extraction": {
        "actions": [
            {
                "type": "calendar_event",
                "summary": "Tuesday 2pm sync meeting",
                "deadline_at": "2026-06-09T14:00:00Z",
            }
        ]
    },
}

_PAYLOADS_NEWSLETTER = {
    "sensitivity_class": {"sensitivity": "normal", "confidence": 0.95, "reason": "newsletter"},
    "coarse_class": {"class_coarse": "newsletter", "confidence": 0.98},
    "summary_short": {"summary": "Weekly newsletter digest — 5 trending topics."},
    "importance_scoring": {"importance": 15, "signals": ["newsletter", "recurring"]},
    "action_extraction": {"actions": []},
}

_PAYLOADS_SENSITIVE = {
    # Even for sensitive, the classifier sees the body and returns sensitive directly.
    "sensitivity_class": {"sensitivity": "sensitive", "confidence": 0.85, "reason": "private content"},
    "coarse_class": {"class_coarse": "human", "confidence": 0.90},
    "fine_class": {"class_fine": "personal", "confidence": 0.85},
    # summary_short/importance/action are Haiku — blocked by SENSITIVITY_BLOCKS_API,
    # so these payloads are never actually requested.
}


@pytest.fixture
def _clean_state(monkeypatch):
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    # Bypass patterns loading; the orchestrator's _run_sensitivity_step
    # catches the RuntimeError gracefully.
    monkeypatch.setenv("MAILBOT_SKIP_PATTERNS", "1")
    yield
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_POLICY_YAML, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml))
    return db_path


async def _seed_email(db_path: str, *, graph_id: str, body: str = "some body text") -> None:
    await execute_write(
        db_path,
        "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview) VALUES (?, ?, ?, ?, ?)",
        (graph_id, "2026-06-01T00:00:00Z", "Subject", "alice@example.com", body),
    )


def _register_all_adapters(payloads: dict[str, dict[str, Any]]) -> None:
    register_adapter(_QWEN, _FakeAdapter(_QWEN, payloads))
    register_adapter(_HAIKU, _FakeAdapter(_HAIKU, payloads))
    register_adapter(_NOMIC, _FakeAdapter(_NOMIC, payloads))


async def test_pipeline_happy_path_human_email_runs_all_seven_steps(tmp_path: Path, _clean_state: Any) -> None:
    """AC-2, AC-5: human email → all 7 steps run in order."""
    db_path = _setup(tmp_path)
    _register_all_adapters(_PAYLOADS_HUMAN)
    await _seed_email(db_path, graph_id="e-1", body="please confirm the friday meeting time")

    result: ProcessEmailResult = await process_email(email_id="e-1", db_path=db_path)

    assert result.ok is True
    assert result.failed_at is None
    expected_order = [
        "sensitivity_class",
        "coarse_class",
        "fine_class",
        "summary_short",
        "importance_scoring",
        "action_extraction",
        "embedding",
    ]
    assert result.steps_run == expected_order
    assert result.steps_skipped == []
    assert result.steps_inapplicable == []
    assert result.steps_blocked_by_sensitivity == []
    assert result.partial_due_to_sensitivity is False

    # All 7 *_at columns populated on the email row.
    row = await fetchone(db_path, EMAIL_DERIVED_FIELDS_SELECT, ("e-1",))
    assert row is not None
    # Row layout (Story 3-1 EMAIL_DERIVED_FIELDS_SELECT):
    # sensitivity*5, class_coarse*5, class_fine*5, summary_short*5,
    # importance_score*5, action_extraction*5, embedding*5, dtype, shape
    # sensitivity_at is index 4, class_coarse_at is index 9, etc.
    sensitivity_at_idx = 4
    coarse_at_idx = 9
    fine_at_idx = 14
    summary_at_idx = 19
    importance_at_idx = 24
    action_at_idx = 29
    embedding_at_idx = 33
    for idx, name in (
        (sensitivity_at_idx, "sensitivity_at"),
        (coarse_at_idx, "class_coarse_at"),
        (fine_at_idx, "class_fine_at"),
        (summary_at_idx, "summary_short_at"),
        (importance_at_idx, "importance_score_at"),
        (action_at_idx, "action_extraction_at"),
        (embedding_at_idx, "embedding_at"),
    ):
        assert row[idx] is not None, f"{name} should be populated, got NULL at index {idx}"


async def test_pipeline_newsletter_skips_fine_class(tmp_path: Path, _clean_state: Any) -> None:
    """AC-5: newsletter (class_coarse != 'human') skips fine_class as inapplicable."""
    db_path = _setup(tmp_path)
    _register_all_adapters(_PAYLOADS_NEWSLETTER)
    await _seed_email(db_path, graph_id="e-1")

    result = await process_email(email_id="e-1", db_path=db_path)

    assert result.ok is True
    assert "fine_class" in result.steps_inapplicable
    assert "fine_class" not in result.steps_run
    # 6 steps executed (no fine_class).
    assert len(result.steps_run) == 6
    # class_fine_at remains NULL.
    row = await fetchone(db_path, "SELECT class_fine_at FROM emails WHERE graph_id = ?", ("e-1",))
    assert row is not None
    assert row[0] is None


async def test_pipeline_idempotent_second_run_skips_all_steps(tmp_path: Path, _clean_state: Any) -> None:
    """AC-3: a second process_email call with unchanged policy short-circuits all steps."""
    db_path = _setup(tmp_path)
    _register_all_adapters(_PAYLOADS_HUMAN)
    await _seed_email(db_path, graph_id="e-1", body="confirm meeting time")

    # First run.
    first = await process_email(email_id="e-1", db_path=db_path)
    assert first.ok is True
    assert len(first.steps_run) == 7

    # Second run.
    second = await process_email(email_id="e-1", db_path=db_path)
    assert second.ok is True
    # Sensitivity is short-circuited because sensitivity_at is populated.
    assert "sensitivity_class" in second.steps_skipped
    # All 5 ask_router-tracked tasks are in the idempotency table.
    for task in ("coarse_class", "fine_class", "summary_short", "importance_scoring", "action_extraction"):
        assert task in second.steps_skipped
    # Embedding short-circuits via read_embedding != None.
    assert "embedding" in second.steps_skipped
    assert second.steps_run == []


async def test_pipeline_failed_step_aborts_remaining(tmp_path: Path, _clean_state: Any) -> None:
    """AC-2: a step returning ok=False aborts the pipeline; partial row carries."""
    db_path = _setup(tmp_path)
    # Adapter that succeeds on sensitivity but returns invalid JSON on coarse_class.

    class _PartialAdapter:
        model_id = _QWEN
        call_count = 0

        async def call(self, system, user, max_tokens_out, temperature=0.0):
            self.call_count += 1
            if "broad kind" in system.lower():  # coarse_class
                return AdapterResponse(
                    text="not valid json",
                    tokens_in=5,
                    tokens_out=5,
                    cached_tokens_in=0,
                    latency_ms=10,
                    raw={},
                )
            # sensitivity_class
            return AdapterResponse(
                text=json.dumps({"sensitivity": "normal", "confidence": 0.9, "reason": "ok"}),
                tokens_in=5,
                tokens_out=5,
                cached_tokens_in=0,
                latency_ms=10,
                raw={},
            )

        async def embed(self, text):
            raise RuntimeError("not used")

    register_adapter(_QWEN, _PartialAdapter())
    await _seed_email(db_path, graph_id="e-1")

    result = await process_email(email_id="e-1", db_path=db_path)

    assert result.ok is False
    assert result.failed_at == "coarse_class"
    assert "sensitivity_class" in result.steps_run
    assert "coarse_class" not in result.steps_run
    # Sensitivity DID get written (partial derivation permitted).
    row = await fetchone(db_path, "SELECT sensitivity_at, class_coarse_at FROM emails WHERE graph_id = ?", ("e-1",))
    assert row is not None
    assert row[0] is not None  # sensitivity_at populated
    assert row[1] is None  # class_coarse_at NOT populated


async def test_pipeline_sensitive_email_blocks_haiku_steps_but_runs_local(tmp_path: Path, _clean_state: Any) -> None:
    """AC-6: sensitive email + Haiku-bound steps → SENSITIVITY_BLOCKS_API.

    The pipeline continues past blocked steps (not a hard abort), runs the
    local-bound steps, and marks partial_due_to_sensitivity=True.
    """
    db_path = _setup(tmp_path)
    _register_all_adapters(_PAYLOADS_SENSITIVE)
    await _seed_email(db_path, graph_id="e-1", body="private medical content")

    result = await process_email(email_id="e-1", db_path=db_path)

    assert result.ok is True
    assert result.partial_due_to_sensitivity is True

    # Local steps ran (sensitivity, coarse_class, fine_class on Qwen; embedding on nomic).
    assert "sensitivity_class" in result.steps_run
    assert "coarse_class" in result.steps_run
    assert "fine_class" in result.steps_run
    assert "embedding" in result.steps_run

    # The 3 Haiku-bound steps are blocked.
    assert "summary_short" in result.steps_blocked_by_sensitivity
    assert "importance_scoring" in result.steps_blocked_by_sensitivity
    assert "action_extraction" in result.steps_blocked_by_sensitivity

    # Their *_at columns stay NULL.
    row = await fetchone(
        db_path,
        "SELECT summary_short_at, importance_score_at, action_extraction_at FROM emails WHERE graph_id = ?",
        ("e-1",),
    )
    assert row == (None, None, None)


async def test_pipeline_preflight_missing_email_returns_error(tmp_path: Path, _clean_state: Any) -> None:
    """AC-2 preflight: nonexistent email_id returns error before any step."""
    db_path = _setup(tmp_path)
    _register_all_adapters(_PAYLOADS_HUMAN)
    # No seed.

    result = await process_email(email_id="nope", db_path=db_path)

    assert result.ok is False
    assert result.failed_at == "preflight"
    assert result.error is not None
    assert "not found" in result.error.message


async def test_pipeline_records_idempotency_rows(tmp_path: Path, _clean_state: Any) -> None:
    """AC-3: derivations_idempotency table populated for each dispatched step."""
    db_path = _setup(tmp_path)
    _register_all_adapters(_PAYLOADS_HUMAN)
    await _seed_email(db_path, graph_id="e-1")

    await process_email(email_id="e-1", db_path=db_path)

    rows = await fetchall(
        db_path,
        "SELECT task_type FROM derivations_idempotency WHERE email_id = ? ORDER BY task_type",
        ("e-1",),
    )
    task_types = [r[0] for r in rows]
    # 5 ask_router tasks + 1 embedding = 6 idempotency rows.
    # (Sensitivity is tracked via sensitivity_at, not derivations_idempotency.)
    assert "coarse_class" in task_types
    assert "fine_class" in task_types
    assert "summary_short" in task_types
    assert "importance_scoring" in task_types
    assert "action_extraction" in task_types
    assert "embedding" in task_types
    assert len(task_types) == 6


# --------------------------------------------------------------------------- #
# Story 4-0 Finding 4: CLI runtime init must load policy + patterns + adapters
# + budget guard + pause state before process_email is callable, mirroring the
# FastAPI lifespan. Without this, every CLI invocation fails immediately at the
# sensitivity_class step with 'policy not loaded'.
# --------------------------------------------------------------------------- #


async def test_cli_init_runtime_loads_policy_patterns_and_adapters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI helper must load every snapshot/registry process_email reads from."""
    from mailbot_api.ingest.pipeline import _cli_init_runtime
    from mailbot_api.router import policy as policy_module
    from mailbot_api.router import registry as registry_module
    from mailbot_api.sensitivity import patterns as patterns_module

    db_path = str(tmp_path / "cli-init.db")
    apply_pending_migrations(db_path)

    # Reset every snapshot/registry to a clean state.
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_guard_for_test()
    _reset_pause_state_for_test()
    patterns_module._PATTERN_SNAPSHOT = None  # noqa: SLF001 — test-only reset

    # Point at real shipped configs.
    repo_root = Path(__file__).resolve().parents[2]
    monkeypatch.setenv("MAILBOT_POLICY_PATH", str(repo_root / "router" / "policy.yaml"))
    monkeypatch.setenv(
        "MAILBOT_PATTERNS_PATH", str(repo_root / "router" / "sensitivity_patterns.yaml")
    )

    # Pre-conditions: nothing loaded.
    assert policy_module._policy is None  # noqa: SLF001
    assert patterns_module._PATTERN_SNAPSHOT is None  # noqa: SLF001

    await _cli_init_runtime(db_path)

    # Post-conditions: everything that process_email reads is now ready.
    assert policy_module._policy is not None  # noqa: SLF001
    assert patterns_module._PATTERN_SNAPSHOT is not None  # noqa: SLF001
    # Registry has at least one adapter registered (Ollama default).
    assert len(registry_module._ADAPTER_REGISTRY) > 0  # noqa: SLF001
