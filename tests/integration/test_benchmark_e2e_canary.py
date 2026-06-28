"""Story 9-8: end-to-end canary join — runner → scorer → report renderer.

Two integration tests verify the full pipe is connected on the 5-item canary
fixture from Story 9-5 (``evals/fixtures/canary_5.jsonl``):

1. Happy path — runner produces 10 ``benchmark_runs`` rows (5 items × 1 task
   × 2 models for ``coarse_class``), scorer produces ``benchmark_scores``
   rows, the report renderer writes ``benchmark/reports/<run_id>.md`` with
   the empty-state ``INSUFFICIENT DATA — n=<count>, gate=15`` literal
   (n < 15 sample gate). Scope is intentionally objective-only (no anchors
   required); the subjective ``summary_short`` task is covered by
   ``test_scorer.py::test_scenario_2_happy_path_subjective``.

2. Partial-state + resume — first invocation uses ``--max-items 3`` to
   write a 3-item partial state (6 rows), then a second invocation with
   ``--resume`` and the full corpus completes the remaining 4 rows. Final
   count = 10 with no duplicates (UNIQUE constraint enforced).

All dispatches go through ``register_adapter(...)`` + ``runner_main(...)`` +
``scorer_main(...)`` programmatic CLI invocation per Rule I — the Router
runs end-to-end (precondition layer, lane semaphore, cost computation,
audit write). Only the adapter is faked.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from benchmark.report import render_report
from benchmark.runner import main as runner_main
from benchmark.scorer import main as scorer_main
from benchmark.scorer_db import read_run_scores
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

_QWEN: str = "qwen2.5:3b-instruct-q4_K_M"
_HAIKU: str = "claude-haiku-4-5-20251001"

_POLICY_YAML_TEMPLATE = """\
version: "test-policy-9-8"

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
    """Task-keyed scripted adapter (Story 9-6/9-7 pattern).

    Inspects the SYSTEM prompt prefix at call time and returns the matching
    response from ``task_responses``.
    """

    def __init__(
        self,
        task_responses: dict[str, Any],
        model_id: str = "scripted",
    ) -> None:
        self.task_responses = task_responses
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
            {"system": system[:60], "user": user[:60], "max_tokens_out": max_tokens_out}
        )
        for prefix, factory in self.task_responses.items():
            if prefix in system:
                return factory()
        raise RuntimeError(
            f"ScriptedAdapter: no task_responses match for system prefix {system[:60]!r}"
        )


def _good_coarse_class_response() -> AdapterResponse:
    return AdapterResponse(
        text=json.dumps({"class_coarse": "newsletter", "confidence": 0.9}),
        tokens_in=10,
        tokens_out=5,
        cached_tokens_in=0,
        latency_ms=42,
        raw={"mock": True},
    )


def _task_responses() -> dict[str, Any]:
    return {
        "classify the broad kind": _good_coarse_class_response,
    }


def _setup_test_env(tmp_path: Path) -> tuple[str, Path, Path]:
    """Initialize DB + policy + canary corpus + anchors VERSION.

    Copies ``evals/fixtures/canary_5.jsonl`` into ``tmp_path`` so the
    runner reads the canonical Story 9-5 fixture verbatim.

    Returns (db_path, corpus_path, anchors_dir).
    """
    db_path = str(tmp_path / "test.db")
    apply_pending_migrations(db_path)

    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_POLICY_YAML_TEMPLATE, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml))

    # Copy the canonical 5-item canary into tmp so the runner finds it.
    src_canary = Path("evals/fixtures/canary_5.jsonl")
    corpus_path = tmp_path / "canary_5.jsonl"
    shutil.copyfile(src_canary, corpus_path)

    anchors_dir = tmp_path / "anchors"
    anchors_dir.mkdir()
    (anchors_dir / "VERSION").write_text("anchors-v9-8-test", encoding="utf-8")

    return db_path, corpus_path, anchors_dir


_COST_MOCK_ENV: str = "BENCHMARK_COST_MOCK"


@pytest.fixture
def _clean_state() -> Iterator[None]:
    """Reset module-level singletons + the BENCHMARK_COST_MOCK env var
    between tests (Story 9-6/9-7 pattern, extended for CR-F1+F2).

    The runner's ``_run_async`` sets ``os.environ[BENCHMARK_COST_MOCK]="1"``
    directly when ``--cost-mock`` is passed (benchmark/runner.py:438). Without
    explicit pre+post cleanup, the env var leaks across tests in the same
    process — a downstream test that later asserts the var's absence (or that
    sets it conditionally based on prior absence) would see a stale value.
    """
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()
    _reset_registry_for_test()
    _reset_policy_snapshot_for_test()
    os.environ.pop(_COST_MOCK_ENV, None)
    yield
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    _reset_oneshot_override_for_test()
    os.environ.pop(_COST_MOCK_ENV, None)


def _fetchall(db_path: str, query: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(query, params)
        return list(cur.fetchall())
    finally:
        conn.close()


# ---------- Test 1: Happy path ----------


def test_e2e_canary_happy_path_runner_scorer_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """5 canary items × 1 task × 2 models = 10 cells; runner → scorer → report
    chain produces a report file with the empty-state INSUFFICIENT DATA literal.

    Scope: objective-only (``coarse_class``). The subjective path is covered
    in ``test_scorer.py::test_scenario_2_happy_path_subjective`` — adding it
    here would require authoring a parallel anchor fixture, which duplicates
    the Story 9-5 corpus-build surface without adding integration coverage.
    """
    db_path, corpus_path, anchors_dir = _setup_test_env(tmp_path)

    qwen_adapter = _ScriptedAdapter(task_responses=_task_responses(), model_id=_QWEN)
    haiku_adapter = _ScriptedAdapter(task_responses=_task_responses(), model_id=_HAIKU)
    register_adapter(_QWEN, qwen_adapter)
    register_adapter(_HAIKU, haiku_adapter)

    monkeypatch.setenv("MAILBOT_DB_PATH", db_path)
    monkeypatch.setattr("benchmark.runner._DEFAULT_ANCHORS_DIR", str(anchors_dir))

    run_id = "e2e-canary-9-8-happy"

    # Runner.
    rc_runner = runner_main(
        [
            "--run-id", run_id,
            "--corpus", str(corpus_path),
            "--db-path", db_path,
            "--tasks", "coarse_class",
            "--models", f"{_QWEN},{_HAIKU}",
            "--cost-mock",
            "--yes",
        ]
    )
    assert rc_runner == 0, f"runner exit code expected 0; got {rc_runner}"

    runs_rows = _fetchall(
        db_path,
        "SELECT cohort_key, status, outcome FROM benchmark_runs WHERE run_id = ?",
        (run_id,),
    )
    assert len(runs_rows) == 10, (
        f"E2E AC-1: expected 10 benchmark_runs rows (5 items × 1 task × 2 models); "
        f"got {len(runs_rows)}"
    )
    assert all(r[1] == "completed" for r in runs_rows)
    assert all(r[2] == "ok" for r in runs_rows)
    cohort_keys = {r[0] for r in runs_rows}
    assert len(cohort_keys) == 1, (
        f"cohort_key must be identical across all canary cells; got {cohort_keys}"
    )

    # Scorer — coarse_class is an objective task; no anchors needed.
    rc_scorer = scorer_main(
        [
            "--run-id", run_id,
            "--db-path", db_path,
            "--corpus", str(corpus_path),
            "--anchors-dir", str(anchors_dir),
            "--tasks", "coarse_class",
            "--cost-mock",
            "--yes",
        ]
    )
    assert rc_scorer == 0, f"scorer exit code expected 0; got {rc_scorer}"

    scores = asyncio.run(read_run_scores(db_path, run_id))
    assert len(scores) > 0, "scorer must emit at least one benchmark_scores row"
    assert any(s.task_type == "coarse_class" for s in scores), (
        "E2E AC-2: scorer must produce coarse_class scores"
    )
    # Every score row carries the same cohort_key as its source run row.
    score_cohort_keys = {s.cohort_key for s in scores}
    assert score_cohort_keys == cohort_keys, (
        "E2E AC-3: scorer must propagate cohort_key from benchmark_runs"
    )

    # Report renderer — produces the markdown stub with empty-state literals.
    output_dir = tmp_path / "reports"
    report_path = render_report(db_path, run_id, output_dir)
    assert report_path.exists(), f"E2E AC-4: report file must exist at {report_path}"
    assert report_path.name == f"{run_id}.md"

    report_text = report_path.read_text(encoding="utf-8")
    # Story 9-9 sample-size-gate contract — total scored rows is well below 15.
    assert "INSUFFICIENT DATA" in report_text, (
        "E2E AC-5: report must contain the literal INSUFFICIENT DATA empty-state marker"
    )
    assert "gate=15" in report_text, (
        "E2E AC-5: report must surface the sample-size gate value (15)"
    )
    # Sanity: report references the run_id and the cohort_key.
    assert run_id in report_text
    sole_cohort_key = next(iter(cohort_keys))
    assert sole_cohort_key in report_text, (
        "E2E AC-6: report must surface the cohort_key from the scored rows"
    )
    # Pareto + DEMOTE/PROMOTE sections always render.
    assert "## Pareto Frontier" in report_text
    assert "## DEMOTE/PROMOTE Suggestions" in report_text


# ---------- Test 2: Failure-mid-run + resume ----------


def test_e2e_canary_partial_state_then_resume_completes_all_cells(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _clean_state: None,
) -> None:
    """First invocation with ``--max-items 3`` writes 6 rows (3 items × 1 task
    × 2 models); a second invocation with ``--resume`` and the full 5-item
    corpus completes the remaining 4 rows. Final count = 10 with no
    duplicates (UNIQUE constraint enforced — no IntegrityError).

    This exercises the runner's resume contract end-to-end (the same surface
    Story 9-6 ``test_runner_resume_picks_up_remaining_cells`` covers at the
    unit level, but here through the full E2E join with the canonical canary
    fixture).
    """
    db_path, corpus_path, anchors_dir = _setup_test_env(tmp_path)

    qwen_adapter = _ScriptedAdapter(task_responses=_task_responses(), model_id=_QWEN)
    haiku_adapter = _ScriptedAdapter(task_responses=_task_responses(), model_id=_HAIKU)
    register_adapter(_QWEN, qwen_adapter)
    register_adapter(_HAIKU, haiku_adapter)

    monkeypatch.setenv("MAILBOT_DB_PATH", db_path)
    monkeypatch.setattr("benchmark.runner._DEFAULT_ANCHORS_DIR", str(anchors_dir))

    run_id = "e2e-canary-9-8-resume"

    # First invocation — --max-items 3 → 6 rows (3 items × 1 task × 2 models).
    rc_first = runner_main(
        [
            "--run-id", run_id,
            "--corpus", str(corpus_path),
            "--db-path", db_path,
            "--tasks", "coarse_class",
            "--models", f"{_QWEN},{_HAIKU}",
            "--max-items", "3",
            "--cost-mock",
            "--yes",
        ]
    )
    assert rc_first == 0, f"first invocation exit code expected 0; got {rc_first}"

    rows_round1 = _fetchall(
        db_path,
        "SELECT COUNT(*) FROM benchmark_runs WHERE run_id = ?",
        (run_id,),
    )
    assert rows_round1[0][0] == 6, (
        f"E2E AC-7: partial state expected 6 rows (3 items × 1 task × 2 models); "
        f"got {rows_round1[0][0]}"
    )

    # CR-F2 (sonnet-4-6 review): clear BENCHMARK_COST_MOCK between the two
    # runner invocations so the resume path explicitly chooses (or omits)
    # cost-mock via its own --cost-mock flag, rather than silently inheriting
    # the first invocation's env-var state.
    os.environ.pop(_COST_MOCK_ENV, None)

    # Second invocation — --resume on the full 5-item corpus picks up the
    # remaining 4 cells (items 4-5 × 2 models). Note: no --cost-mock flag;
    # the adapter is faked at the registry boundary so cost-mock is moot
    # for hermetic purposes — this asserts the resume path does NOT depend
    # on BENCHMARK_COST_MOCK env-var inheritance.
    rc_resume = runner_main(
        [
            "--resume", run_id,
            "--corpus", str(corpus_path),
            "--db-path", db_path,
            "--yes",
        ]
    )
    assert rc_resume == 0, f"resume exit code expected 0; got {rc_resume}"
    # CR-F2 sanity: env-var stayed absent across the resume invocation
    # (resume did NOT pass --cost-mock; runner did NOT set the env-var).
    assert _COST_MOCK_ENV not in os.environ, (
        "CR-F2: resume invocation without --cost-mock must not set BENCHMARK_COST_MOCK"
    )

    rows_round2 = _fetchall(
        db_path,
        "SELECT COUNT(*) FROM benchmark_runs WHERE run_id = ?",
        (run_id,),
    )
    final_count = rows_round2[0][0]
    assert final_count == 10, (
        f"E2E AC-8: post-resume count expected 10 (5 items × 1 task × 2 models); "
        f"got {final_count}"
    )

    # UNIQUE-constraint sanity — count distinct (item, task, model, pv) tuples
    # equals the row count (no duplicates introduced by resume).
    distinct_rows = _fetchall(
        db_path,
        "SELECT COUNT(DISTINCT corpus_item_id || ':' || task_type || ':' || model || ':' || prompt_version) "
        "FROM benchmark_runs WHERE run_id = ?",
        (run_id,),
    )
    assert distinct_rows[0][0] == 10, (
        f"E2E AC-9: no duplicates in (item, task, model, pv); "
        f"distinct={distinct_rows[0][0]}, total={final_count}"
    )


# ---------- Test 3: CR-F3 path-traversal guard ----------


@pytest.mark.parametrize(
    "unsafe_run_id",
    [
        "../etc/passwd",
        "..",
        "../../tmp/x",
        "foo/bar",
        "foo\\bar",
        "with space",
        "with.dot",
        "",
    ],
)
def test_render_report_rejects_unsafe_run_id(
    tmp_path: Path, unsafe_run_id: str
) -> None:
    """CR-F3 (sonnet-4-6 review): render_report MUST refuse run_ids that could
    escape output_dir or contain characters outside [A-Za-z0-9_-].
    """
    with pytest.raises(ValueError, match="unsafe characters"):
        render_report(
            db_path=str(tmp_path / "irrelevant.db"),
            run_id=unsafe_run_id,
            output_dir=tmp_path / "reports",
        )
