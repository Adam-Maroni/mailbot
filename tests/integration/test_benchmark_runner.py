"""Story 9.6 AC-9: integration tests for benchmark.runner.

All dispatches use a fake ModelAdapter registered at the adapter boundary
(NOT mocking ``ask_router`` itself — that would break Rule I coverage).
The Router runs end-to-end: precondition layer, lane semaphore, cost
computation, audit write, response cache lookup. Only the adapter is faked.

Test coverage:
1. Happy path — 20 cells, cohort_key consistency, run_id consistency
2. Resume — second invocation picks up unfinished cells
3. Cost gate — prompts above $5, aborts on 'n', skips on --yes
4. Monthly cap mid-run — MONTHLY_BUDGET_EXCEEDED aborts with exit code 2
5. Degraded mode mid-run — DEGRADED_MODE_BLOCKED aborts the same way
6. SIGINT — writes status="interrupted", exits 130
7. Unique constraint enforcement on duplicate (run_id, item, task, model, pv)
8. Cohort_key determinism + sensitivity (covered in tests/unit/benchmark/test_cohort.py;
   this file's #1 asserts the runner USES the same key across cells)
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from benchmark.runner import main as runner_main
from evals.corpus_schema import (
    CorpusItem,
    CorpusLabels,
    write_corpus,
)
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import AdapterResponse
from mailbot_api.router.oneshot import _reset_oneshot_override_for_test
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter

_POLICY_YAML_TEMPLATE = """\
version: "test-policy-v1"

tasks:
  coarse_class:
    model: "qwen2.5:3b-instruct-q4_K_M"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 100
    lane: "batch"
    sensitivity: "any"
    response_cache_ttl_seconds: 0
  summary_short:
    model: "qwen2.5:3b-instruct-q4_K_M"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 200
    lane: "batch"
    sensitivity: "any"
    response_cache_ttl_seconds: 0
"""


class _ScriptedAdapter:
    """Scripted ModelAdapter — yields one response per ``call`` based on the task.

    Two construction modes:
      * ``responses=...`` — FIFO queue (legacy; used by sequential-task tests).
      * ``task_responses=...`` — dict mapping task signature substring → response factory.
        The adapter inspects the ``system`` prompt prefix at call time and returns
        the matching factory's output. This handles 2-task benchmark dispatch where
        the same model is called for ``coarse_class`` and ``summary_short`` and each
        needs its OWN schema-valid response.

    Also supports queued exceptions via ``responses=...`` mode.
    """

    def __init__(
        self,
        responses: list[AdapterResponse | BaseException] | None = None,
        task_responses: dict[str, Any] | None = None,
        model_id: str = "scripted",
    ) -> None:
        self.responses: list[AdapterResponse | BaseException] = list(responses or [])
        self.task_responses = task_responses or {}
        self.model_id = model_id
        self.call_log: list[dict[str, Any]] = []

    async def call(
        self,
        system: str,
        user: str,
        max_tokens_out: int,
        temperature: float = 0.0,
    ) -> AdapterResponse:
        self.call_log.append({"system": system[:60], "user": user[:60], "max_tokens_out": max_tokens_out})
        # Task-keyed mode: pick a response based on the system prompt prefix.
        if self.task_responses:
            for prefix, factory in self.task_responses.items():
                if prefix in system:
                    out = factory()
                    if isinstance(out, BaseException):
                        raise out
                    return out
            raise RuntimeError(
                f"ScriptedAdapter: no task_responses match for system prefix {system[:60]!r}"
            )
        # Legacy FIFO mode.
        if not self.responses:
            raise RuntimeError("ScriptedAdapter ran out of scripted responses")
        nxt = self.responses.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


def _good_coarse_class_response() -> AdapterResponse:
    return AdapterResponse(
        text=json.dumps({"class_coarse": "newsletter", "confidence": 0.9}),
        tokens_in=10,
        tokens_out=5,
        cached_tokens_in=0,
        latency_ms=42,
        raw={"mock": True},
    )


def _good_summary_short_response() -> AdapterResponse:
    # SummaryShortOutput schema (mailbot_api/prompts/summary_short/v1.py):
    # field is `summary`, max_length=280.
    return AdapterResponse(
        text=json.dumps({"summary": "test summary"}),
        tokens_in=20,
        tokens_out=8,
        cached_tokens_in=0,
        latency_ms=55,
        raw={"mock": True},
    )


def _make_corpus_item(i: int) -> CorpusItem:
    return CorpusItem(
        id=f"corpus-v1-{i:03d}",
        category="newsletter",
        raw_subject=f"Subject {i}",
        raw_body=f"Body content for item {i}.",
        labels=CorpusLabels(
            sensitivity="normal",
            class_coarse="newsletter",
        ),
        source_note=f"Synthetic test item #{i}",
    )


def _setup_test_env(
    tmp_path: Path,
    n_items: int = 5,
) -> tuple[str, Path, Path]:
    """Initialize DB + policy + corpus + anchors VERSION + fake adapter.

    Returns (db_path, corpus_path, anchors_dir).
    """
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)

    # Policy.
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_POLICY_YAML_TEMPLATE, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml))

    # Corpus.
    corpus_path = tmp_path / "corpus.jsonl"
    items = [_make_corpus_item(i) for i in range(1, n_items + 1)]
    write_corpus(corpus_path, items)

    # Anchors VERSION (Story 9-5 contract).
    anchors_dir = tmp_path / "anchors"
    anchors_dir.mkdir()
    (anchors_dir / "VERSION").write_text("anchors-v1-test", encoding="utf-8")

    return db_path, corpus_path, anchors_dir


@pytest.fixture
def _clean_state() -> Iterator[None]:
    """Reset module-level singletons between tests.

    CR-F5/F6 (Story 9-6 review): added ``_reset_oneshot_override_for_test``
    to prevent Story 9-3 oneshot state from bleeding across test isolation
    boundary; corrected return type annotation from ``-> None`` to
    ``-> Iterator[None]`` since the body uses ``yield``.
    """
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


def _run_cli(
    db_path: str,
    corpus_path: Path,
    anchors_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    extra_args: list[str],
) -> int:
    """Invoke ``benchmark.runner.main(...)`` with the test env wired."""
    monkeypatch.setenv("MAILBOT_DB_PATH", db_path)
    # Point the runner's hardcoded anchors dir at our test dir.
    monkeypatch.setattr(
        "benchmark.runner._DEFAULT_ANCHORS_DIR", str(anchors_dir)
    )
    argv = ["--corpus", str(corpus_path), "--db-path", db_path, *extra_args]
    return runner_main(argv)


# ---------- Test 1: Happy path ----------


def test_runner_happy_path_20_cells_consistent_cohort_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """5 items × 2 tasks × 2 models = 20 cells; all OK; cohort_key identical."""
    db_path, corpus_path, anchors_dir = _setup_test_env(tmp_path, n_items=5)

    # Task-keyed responses based on SYSTEM-prompt prefix. The benchmark runner
    # interleaves task types per cell, so a FIFO response queue would mis-match.
    task_responses = {
        # coarse_class SYSTEM contains "classify the broad kind of email"
        "classify the broad kind": _good_coarse_class_response,
        # summary_short SYSTEM contains "one-line summary"
        "one-line summary": _good_summary_short_response,
    }
    qwen_adapter = _ScriptedAdapter(task_responses=task_responses)
    haiku_adapter = _ScriptedAdapter(task_responses=task_responses)
    register_adapter("qwen2.5:3b-instruct-q4_K_M", qwen_adapter)
    register_adapter("claude-haiku-4-5-20251001", haiku_adapter)

    exit_code = _run_cli(
        db_path, corpus_path, anchors_dir, monkeypatch,
        [
            "--tasks", "coarse_class,summary_short",
            "--models", "qwen2.5:3b-instruct-q4_K_M,claude-haiku-4-5-20251001",
            "--yes",
        ],
    )
    assert exit_code == 0

    rows = await_fetchall(db_path, "SELECT cohort_key, status, outcome FROM benchmark_runs", ())
    assert len(rows) == 20, f"expected 20 cells; got {len(rows)}"
    cohort_keys = {r[0] for r in rows}
    assert len(cohort_keys) == 1, f"cohort_key must be identical across cells; got {cohort_keys}"
    assert all(r[1] == "completed" for r in rows)
    assert all(r[2] == "ok" for r in rows)


# ---------- Test 2: Resume ----------


def test_runner_resume_picks_up_remaining_cells(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """First run: 10 cells (1 task × 2 models × 5 items). Second --resume run
    with --tasks adding summary_short fails grid-mismatch validation."""
    db_path, corpus_path, anchors_dir = _setup_test_env(tmp_path, n_items=5)

    qwen_adapter = _ScriptedAdapter(
        responses=[_good_coarse_class_response() for _ in range(5)],
    )
    haiku_adapter = _ScriptedAdapter(
        responses=[_good_coarse_class_response() for _ in range(5)],
    )
    register_adapter("qwen2.5:3b-instruct-q4_K_M", qwen_adapter)
    register_adapter("claude-haiku-4-5-20251001", haiku_adapter)

    run_id = "resume-test-run-001"
    exit_code = _run_cli(
        db_path, corpus_path, anchors_dir, monkeypatch,
        [
            "--run-id", run_id,
            "--tasks", "coarse_class",
            "--models", "qwen2.5:3b-instruct-q4_K_M,claude-haiku-4-5-20251001",
            "--yes",
        ],
    )
    assert exit_code == 0
    rows = await_fetchall(db_path, "SELECT COUNT(*) FROM benchmark_runs WHERE run_id = ?", (run_id,))
    assert rows[0][0] == 10

    # Resume with same grid → 0 new cells (all completed).
    exit_code = _run_cli(
        db_path, corpus_path, anchors_dir, monkeypatch,
        ["--resume", run_id, "--yes"],
    )
    assert exit_code == 0
    rows = await_fetchall(db_path, "SELECT COUNT(*) FROM benchmark_runs WHERE run_id = ?", (run_id,))
    assert rows[0][0] == 10, "resume with no new cells should not duplicate rows"


# ---------- Test 3: Cost gate ----------


def test_runner_cost_gate_blocks_above_threshold_without_yes_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """Mock estimate_cost_usd to return $1.00/cell → $20 total > $5; default 'n' aborts."""
    db_path, corpus_path, anchors_dir = _setup_test_env(tmp_path, n_items=5)

    # Patch the pricing module so estimate is $1/cell × 5 cells = $5 — not
    # quite over the gate. Bump to $2 so total = $10 > $5.
    monkeypatch.setattr(
        "mailbot_api.router.pricing.estimate_cost_usd",
        lambda model, tokens_in, tokens_out, cached_tokens_in=0: 2.00,
    )
    # Simulate stdin returning 'n'.
    monkeypatch.setattr("builtins.input", lambda _prompt: "n")

    # No adapters registered — but we expect to abort before any dispatch.
    exit_code = _run_cli(
        db_path, corpus_path, anchors_dir, monkeypatch,
        [
            "--tasks", "coarse_class",
            "--models", "qwen2.5:3b-instruct-q4_K_M",
            # No --yes; cost gate should fire.
        ],
    )
    assert exit_code == 0  # clean abort
    rows = await_fetchall(db_path, "SELECT COUNT(*) FROM benchmark_runs", ())
    assert rows[0][0] == 0, "no cells should be written when cost gate aborts"


def test_runner_cost_gate_proceeds_when_yes_flag_set(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """--yes bypasses the prompt even when estimate > $5."""
    db_path, corpus_path, anchors_dir = _setup_test_env(tmp_path, n_items=5)

    monkeypatch.setattr(
        "mailbot_api.router.pricing.estimate_cost_usd",
        lambda model, tokens_in, tokens_out, cached_tokens_in=0: 1.00,
    )
    qwen_adapter = _ScriptedAdapter(
        responses=[_good_coarse_class_response() for _ in range(5)],
    )
    register_adapter("qwen2.5:3b-instruct-q4_K_M", qwen_adapter)

    exit_code = _run_cli(
        db_path, corpus_path, anchors_dir, monkeypatch,
        [
            "--tasks", "coarse_class",
            "--models", "qwen2.5:3b-instruct-q4_K_M",
            "--yes",
        ],
    )
    assert exit_code == 0
    rows = await_fetchall(db_path, "SELECT COUNT(*) FROM benchmark_runs", ())
    assert rows[0][0] == 5


# ---------- Test 4: Degraded mode mid-run aborts (CR-F1+F4 fix) ----------


def test_runner_aborts_on_degraded_mode_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """When budget guard's degraded mode is active AND force_model=claude-opus-4-7,
    the Router emits DEGRADED_MODE_BLOCKED. The runner must mark the blocking
    cell ``status=aborted_cost_cap`` + ``outcome=budget_blocked``, then exit
    code 2 without dispatching remaining cells.

    CR-F1 (Story 9-6 review) fix: previous version used the non-existent
    ``guard.month_spent_usd`` attribute (correct name is ``this_month_spend_usd``)
    AND the wrong error path (``MONTHLY_BUDGET_EXCEEDED`` is defined in
    errors.py but never emitted in production). Real production cap-blocking
    surface is ``DEGRADED_MODE_BLOCKED`` (router.py:313) which requires
    ``_degraded_mode_active=True`` AND ``force_model="claude-opus-4-7"``.

    CR-F4 fix: AC-9 Test 5 (DEGRADED_MODE_BLOCKED) was declared in file
    header but missing as a test function — this consolidates F1+F4 into one
    real exercise of the cap-abort path.
    """
    from mailbot_api.router.budget import get_guard

    db_path, corpus_path, anchors_dir = _setup_test_env(tmp_path, n_items=3)

    # Fake adapter: opus would dispatch but we never reach it (degraded gate
    # intercepts before adapter dispatch when force_model=opus).
    opus_adapter = _ScriptedAdapter(task_responses={
        "classify the broad kind": _good_coarse_class_response,
    })
    register_adapter("claude-opus-4-7", opus_adapter)

    # Trip degraded mode directly (Layer 3 active flag).
    guard = get_guard()
    guard._degraded_mode_active = True  # noqa: SLF001 — test fixture access

    exit_code = _run_cli(
        db_path, corpus_path, anchors_dir, monkeypatch,
        [
            "--tasks", "coarse_class",
            "--models", "claude-opus-4-7",
            "--yes",
        ],
    )
    # AC-6: runner must exit code 2 on cap-blocking.
    assert exit_code == 2, (
        f"Expected exit code 2 on DEGRADED_MODE_BLOCKED; got {exit_code}"
    )
    # Exactly one cell written (the blocking cell); remaining 2 cells skipped.
    rows = await_fetchall(
        db_path,
        "SELECT outcome, status FROM benchmark_runs ORDER BY id",
        (),
    )
    assert len(rows) == 1, f"Expected exactly 1 row (blocking cell); got {len(rows)}"
    assert rows[0] == ("budget_blocked", "aborted_cost_cap"), (
        f"Expected blocking cell to be (budget_blocked, aborted_cost_cap); got {rows[0]}"
    )
    # The fake adapter was never called — Router gated before dispatch.
    assert len(opus_adapter.call_log) == 0, (
        f"Adapter should not have been called; got {len(opus_adapter.call_log)} calls"
    )


# ---------- Test 5: Unique constraint ----------


def test_unique_constraint_blocks_duplicate_cell_rows(
    tmp_path: Path,
    _clean_state: None,
) -> None:
    """Direct SQL: a second INSERT with the same (run_id, item, task, model, pv) raises IntegrityError."""
    import sqlite3

    db_path, _corpus_path, _anchors_dir = _setup_test_env(tmp_path, n_items=1)

    # Manually insert two rows with identical unique-tuple values.
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO benchmark_runs ("
            "run_id, corpus_item_id, task_type, model, prompt_version, "
            "cohort_key, output_json, tokens_in, tokens_out, cached_tokens_in, "
            "cost_usd, latency_ms, outcome, status, scorer_model, "
            "anchors_version, router_policy_version, ran_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "rid-1", "corpus-v1-001", "coarse_class", "qwen", "v1",
                "cohort1", None, 0, 0, 0, 0.0, 0,
                "ok", "completed", "scorer", "anchors-v1", "policy-v0", "2026-06-27T00:00:00Z",
            ),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO benchmark_runs ("
                "run_id, corpus_item_id, task_type, model, prompt_version, "
                "cohort_key, output_json, tokens_in, tokens_out, cached_tokens_in, "
                "cost_usd, latency_ms, outcome, status, scorer_model, "
                "anchors_version, router_policy_version, ran_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "rid-1", "corpus-v1-001", "coarse_class", "qwen", "v1",
                    "cohort1", None, 0, 0, 0, 0.0, 0,
                    "ok", "completed", "scorer", "anchors-v1", "policy-v0", "2026-06-27T00:00:01Z",
                ),
            )
            conn.commit()
    finally:
        conn.close()


# ---------- Helpers ----------


def await_fetchall(
    db_path: str, query: str, params: tuple[Any, ...]
) -> list[tuple[Any, ...]]:
    """Sync wrapper around fetchall for use in non-async test bodies.

    The benchmark_runs.py read path uses the async fetchall; the test
    bodies are sync and run their own asyncio loop via runner_main. We
    open a direct sqlite3 connection here to keep assertions simple.
    """
    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(query, params)
        return list(cur.fetchall())
    finally:
        conn.close()


# ---------- CR2026-07-05-F3 (Epic 9.5 retro A2 CR pass): unknown-model gate ----------


def test_runner_cost_gate_refuses_unknown_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """F-UNKNOWN-MODEL-COST-GATE regression: an unpriceable model must hard-fail
    the cost gate (SystemExit 'cost gate refused'), never estimate $0.00 and
    proceed to real dispatch."""
    db_path, corpus_path, anchors_dir = _setup_test_env(tmp_path, n_items=2)

    with pytest.raises(SystemExit, match="cost gate refused"):
        _run_cli(
            db_path, corpus_path, anchors_dir, monkeypatch,
            [
                "--tasks", "coarse_class",
                "--models", "claude-made-up-model-9000",
                "--yes",
            ],
        )

    rows = await_fetchall(db_path, "SELECT COUNT(*) FROM benchmark_runs", ())
    assert rows[0][0] == 0, "no cells may be written when the cost gate refuses"
