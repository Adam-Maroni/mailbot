"""Story 9.6: benchmark runner CLI.

Dispatches every (corpus_item × task × model × prompt_version) cell through
``ask_router(force_model=...)`` per Rule I (even the benchmark uses the Router),
records one ``benchmark_runs`` row per dispatch, and produces a stable
``cohort_key`` per Adam-decision 2026-06-27 (A5 default 4-tuple).

CLI surface (full spec in story file AC-4):

    python -m benchmark.runner \\
        --tasks coarse_class,sensitivity_class,draft_reply \\
        --models qwen2.5:3b-instruct-q4_K_M,claude-haiku-4-5-20251001,claude-opus-4-7 \\
        [--run-id <uuid>] [--resume <run-id>] [--corpus <path>] \\
        [--scorer-model <id>] [--max-items <n>] [--yes] [--cost-mock]

Three load-bearing safety features:

* ``$5 confirmation gate`` (AC-5) — prompts above $5 estimated cost.
* ``$30 monthly cap interaction`` (AC-6) — detects ``MONTHLY_BUDGET_EXCEEDED``
  + ``DEGRADED_MODE_BLOCKED`` from ``RouterError``, marks the blocking cell
  ``status=aborted_cost_cap``, exits code 2.
* ``SIGINT`` (AC-8) — awaits in-flight cell, writes ``status=interrupted``,
  exits 130 with resume instructions.

All test dispatches use a fake adapter at the adapter boundary; this module
never dispatches to real Anthropic during tests (AC-9). The boundary lives
in ``mailbot_api.router.adapter_registry``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from benchmark.cohort import compute_cohort_key
from benchmark.db import (
    read_completed_cells,
    read_run_grid,
    record_benchmark_run,
)
from benchmark.schemas import BenchmarkCell, BenchmarkRunRow, OutcomeLiteral, StatusLiteral
from evals.corpus_schema import CorpusItem, load_corpus, read_anchors_version

_logger = logging.getLogger(__name__)

# Per-task output-token estimates for the cost-gate pre-computation (AC-5).
# These match the production PolicyEntry.max_tokens_out defaults; the actual
# tokens_out is captured per-cell from RouterResult.
_PER_TASK_OUTPUT_TOKEN_ESTIMATE: dict[str, int] = {
    "coarse_class": 100,
    "sensitivity_class": 100,
    "fine_class": 100,
    "summary_short": 200,
    "draft_reply": 500,
    "action_extraction": 300,
    "importance_scoring": 100,
    "reference_resolution": 200,
}
_DEFAULT_OUTPUT_TOKEN_ESTIMATE: int = 256

_DEFAULT_SCORER_MODEL: str = "claude-opus-4-7-20251220"
_DEFAULT_CORPUS_PATH: str = "evals/email_corpus_v1.jsonl"
_DEFAULT_ANCHORS_DIR: str = "evals/anchors"

_COST_GATE_THRESHOLD_USD: float = 5.00

# Story 9-8 hook (env-var carrier; see runner.py docstring AC-4).
_COST_MOCK_ENV: str = "BENCHMARK_COST_MOCK"


def _estimate_input_tokens(item: CorpusItem) -> int:
    """Rough char/4 ratio for English; conservative enough for the cost gate."""
    raw_chars = len(item.raw_subject) + len(item.raw_body)
    return max(1, raw_chars // 4)


def _build_grid(
    items: list[CorpusItem],
    tasks: list[str],
    models: list[str],
    policy_versions: dict[str, str],
    completed: set[tuple[str, str, str, str]],
) -> list[BenchmarkCell]:
    """Enumerate the (item × task × model × prompt_version) grid; skip completed cells."""
    cells: list[BenchmarkCell] = []
    for item in items:
        # Reference-resolution slice items only count for reference_resolution task.
        is_ref_slice = item.labels.reference_resolution_slice
        for task in tasks:
            if is_ref_slice and task != "reference_resolution":
                continue
            if not is_ref_slice and task == "reference_resolution":
                continue
            prompt_version = policy_versions.get(task, "v1")
            for model in models:
                cell_key = (item.id, task, model, prompt_version)
                if cell_key in completed:
                    continue
                cells.append(
                    BenchmarkCell(
                        corpus_item_id=item.id,
                        task_type=task,
                        model=model,
                        prompt_version=prompt_version,
                    )
                )
    return cells


def _estimate_total_cost(
    cells: list[BenchmarkCell],
    items_by_id: dict[str, CorpusItem],
) -> tuple[float, dict[str, tuple[float, int]]]:
    """Sum estimated cost across cells; return (total, per-model-breakdown)."""
    from mailbot_api.router.pricing import estimate_cost_usd

    total = 0.0
    breakdown: dict[str, tuple[float, int]] = {}
    for cell in cells:
        item = items_by_id[cell.corpus_item_id]
        tokens_in = _estimate_input_tokens(item)
        tokens_out = _PER_TASK_OUTPUT_TOKEN_ESTIMATE.get(
            cell.task_type, _DEFAULT_OUTPUT_TOKEN_ESTIMATE
        )
        cost = estimate_cost_usd(cell.model, tokens_in, tokens_out)
        total += cost
        prev_cost, prev_n = breakdown.get(cell.model, (0.0, 0))
        breakdown[cell.model] = (prev_cost + cost, prev_n + 1)
    return total, breakdown


def _format_cost_breakdown(
    total: float, breakdown: dict[str, tuple[float, int]]
) -> str:
    lines = [f"Estimated total: ${total:.2f} across {sum(n for _, n in breakdown.values())} cells"]
    for model, (cost, n) in sorted(breakdown.items()):
        lines.append(f"  {model}: ${cost:.2f} ({n} cells)")
    return "\n".join(lines)


# Tasks whose prompt USER_TEMPLATE consumes the ingest 3-tuple shape
# ``{subject, sender, body_preview}``. Kept explicit so an unknown
# ``task_type`` raises rather than silently defaulting (CR-F4/F6, 2026-07-03).
_INGEST_SHAPE_TASKS: frozenset[str] = frozenset(
    {
        "coarse_class",
        "sensitivity_class",
        "fine_class",
        "summary_short",
        "importance_scoring",
        "action_extraction",
    }
)


def _build_content(item: CorpusItem, task_type: str = "") -> dict[str, str]:
    """Build the ``content`` dict for ``ask_router`` per existing pipeline shape.

    Story 9.5.3 hotfix (2026-07-03): most tasks share the
    ``{subject, sender, body_preview}`` shape used by the ingest pipeline,
    but ``draft_reply`` (Story 5-3) uses ``{source_email, thread_context,
    tone_signals}``. Without task-shape adaptation, draft_reply dispatches
    fail with ``prompt render failed: KeyError: 'source_email'``. The
    benchmark corpus doesn't carry real thread context or tone data, so
    those are stubbed with defender-tone-neutral placeholders.

    CR-F4/F6 (2026-07-03): unknown ``task_type`` values raise
    ``NotImplementedError`` rather than silently returning the ingest
    shape. Tasks the ``_build_grid`` helper opts in (notably
    ``reference_resolution`` via ``labels.reference_resolution_slice``,
    and any future task the CLI accepts) have their own USER_TEMPLATE
    fields and need explicit branches here. Adding a task to
    ``--tasks`` without also adding a branch is a walk-time defect
    that this raise surfaces at cell-dispatch rather than at prompt
    render.
    """
    # The body_preview is the full anonymized raw_body; per Story 9-5 the corpus
    # raw_body is already anonymized and bounded.
    if task_type == "draft_reply":
        source_email = (
            f"Subject: {item.raw_subject}\n"
            f"From: <benchmark-sender>\n\n"
            f"{item.raw_body}"
        )
        return {
            "source_email": source_email,
            "thread_context": "(no thread context — benchmark corpus item)",
            "tone_signals": "(no tone signals — benchmark corpus item, first-contact treatment)",
        }
    if task_type == "" or task_type in _INGEST_SHAPE_TASKS:
        return {
            "subject": item.raw_subject,
            "sender": "<benchmark-sender>",
            "body_preview": item.raw_body,
        }
    raise NotImplementedError(
        f"_build_content: task_type={task_type!r} has no content-shape "
        f"adapter — add an explicit branch before benchmarking this task. "
        f"Known task types: draft_reply + {sorted(_INGEST_SHAPE_TASKS)!r}."
    )


def _map_outcome(result_ok: bool, error_code_value: str | None) -> OutcomeLiteral:
    """Map RouterResult shape to the closed-set OutcomeLiteral.

    CR-F2 (Story 9-6 review): production router emits ``DEGRADED_MODE_BLOCKED``
    + ``PER_CALL_THRESHOLD_EXCEEDED`` for cap-related issues. ``BUDGET_EXCEEDED``
    and ``MONTHLY_BUDGET_EXCEEDED`` are defined in ``errors.py`` but never
    emitted in the current codebase — kept in the mapping as forward-compat
    defense (if a future story wires them in, the runner already handles them)
    but documented as currently-dormant.
    """
    if result_ok:
        return "ok"
    if error_code_value is None:
        return "provider_error"
    if error_code_value == "schema_validation_failed":
        return "schema_failed"
    if error_code_value == "timeout":
        return "timeout"
    if error_code_value in (
        "degraded_mode_blocked",          # production: Story 2-8 Layer 3
        "per_call_threshold_exceeded",    # production: Story 2-8 Layer 4
        "monthly_budget_exceeded",        # forward-compat: not currently emitted
        "budget_exceeded",                # forward-compat: not currently emitted
    ):
        return "budget_blocked"
    return "provider_error"


def _is_cap_blocking(error_code_value: str | None) -> bool:
    """True if the error code should abort the whole run (AC-6).

    CR-F2/CR-F3 (Story 9-6 review): the production router emits
    ``DEGRADED_MODE_BLOCKED`` when the $30 monthly cap demotes a call.
    ``PER_CALL_THRESHOLD_EXCEEDED`` is Layer 4's $0.20/call gate which is
    bypassed in the runner via ``force=True`` (CR-F3 patch) — so the runner
    no longer treats it as cap-blocking (a single expensive call should not
    abort the run; only true cap exhaustion via degraded-mode should).
    ``MONTHLY_BUDGET_EXCEEDED`` / ``BUDGET_EXCEEDED`` kept as forward-compat
    in case a future story wires them in.
    """
    return error_code_value in (
        "degraded_mode_blocked",
        "monthly_budget_exceeded",
        "budget_exceeded",
    )


def _utc_now_z() -> str:
    """UTC ISO-8601 with Z suffix."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _read_policy_versions() -> tuple[dict[str, str], str]:
    """Snapshot (per-task prompt_version, PolicyTable.version) from the in-memory policy.

    Returns (task → prompt_version, router_policy_version).

    Raises RuntimeError via get_policy() if the policy is not loaded.
    """
    from mailbot_api.router.policy import get_policy

    policy = get_policy()
    per_task = {task: entry.prompt_version for task, entry in policy.tasks.items()}
    return per_task, policy.version


def _confirm_proceed(prompt: str) -> bool:
    """Read a Y/n answer from stdin. Any non-'y'/'Y' aborts."""
    try:
        answer = input(prompt)
    except EOFError:
        return False
    return answer.strip().lower() == "y"


class _SigintHandled(Exception):
    """Raised by the SIGINT handler to break out of the dispatch loop cleanly."""


async def _dispatch_cell(
    cell: BenchmarkCell,
    item: CorpusItem,
    db_path: str,
    scorer_model: str,
    anchors_version: str,
    router_policy_version: str,
    run_id: str,
) -> tuple[BenchmarkRunRow, bool]:
    """Dispatch a single cell through ask_router; build the row.

    Returns (row, is_cap_blocking). When ``is_cap_blocking=True``, the caller
    must persist the row AND abort the loop with exit code 2 (AC-6).
    """
    import time

    from mailbot_api.router.router import ask_router

    t0 = time.perf_counter()
    # email_id=None: the corpus_item_id is NOT a real emails-table row id —
    # it's a synthetic corpus identifier. Passing it as email_id would trip
    # the Router's FR-2.3 sensitivity precondition (which selects from
    # `emails`). The corpus item carries its OWN labels.sensitivity ground
    # truth (Adam-labeled in Story 9-5); the benchmark's purpose is to
    # measure routing decisions against that ground truth, not to enforce
    # the production sensitivity invariant on synthetic test items.
    # corpus_item_id is preserved in the benchmark_runs row for traceability.
    #
    # force=True (CR-F3): bypass Layer 4 per-call refusal threshold ($0.20).
    # The benchmark needs to measure the FULL distribution of model behaviors
    # including expensive Opus calls on long content. The aggregate cap that
    # matters for the runner is the $30 monthly cap (Layer 3, degraded mode);
    # individual expensive calls should dispatch and contribute to that
    # aggregate, not be silently refused per-call. The $5 cost-confirmation
    # gate at AC-5 is the runner's per-batch protection against runaway cost.
    result = await ask_router(
        task_type=cell.task_type,
        content=_build_content(item, task_type=cell.task_type),
        db_path=db_path,
        force_model=cell.model,
        force=True,
        caller_origin="benchmark-runner",
        caller_verb=f"benchmark.{cell.task_type}",
        email_id=None,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)

    error_code_value: str | None = None
    if not result.ok and result.error is not None:
        error_code_value = result.error.code.value

    outcome = _map_outcome(result.ok, error_code_value)
    cap_blocking = _is_cap_blocking(error_code_value)
    status: StatusLiteral = "aborted_cost_cap" if cap_blocking else "completed"

    output_json: str | None = None
    if result.ok and result.output is not None:
        output_json = result.output.model_dump_json()

    cohort_key = compute_cohort_key(
        prompt_version=cell.prompt_version,
        scorer_model=scorer_model,
        anchors_version=anchors_version,
        router_policy_version=router_policy_version,
    )

    row = BenchmarkRunRow(
        run_id=run_id,
        corpus_item_id=cell.corpus_item_id,
        task_type=cell.task_type,
        model=cell.model,
        prompt_version=cell.prompt_version,
        cohort_key=cohort_key,
        output_json=output_json,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        cached_tokens_in=result.cached_tokens_in,
        cost_usd=result.cost_usd,
        latency_ms=latency_ms,
        outcome=outcome,
        status=status,
        scorer_model=scorer_model,
        anchors_version=anchors_version,
        router_policy_version=router_policy_version,
        ran_at=_utc_now_z(),
    )
    return row, cap_blocking


async def _run_dispatch_loop(
    cells: list[BenchmarkCell],
    items_by_id: dict[str, CorpusItem],
    db_path: str,
    scorer_model: str,
    anchors_version: str,
    router_policy_version: str,
    run_id: str,
) -> int:
    """Drive the dispatch loop. Returns exit code (0 / 2 / 130)."""
    sigint_received = False

    def _sigint_handler(_signum: int, _frame: object) -> None:
        nonlocal sigint_received
        sigint_received = True

    # Install SIGINT handler ONLY for the dispatch loop (AC-8).
    prior_handler = signal.signal(signal.SIGINT, _sigint_handler)
    try:
        cells_completed = 0
        for cell in cells:
            item = items_by_id[cell.corpus_item_id]
            row, cap_blocking = await _dispatch_cell(
                cell=cell,
                item=item,
                db_path=db_path,
                scorer_model=scorer_model,
                anchors_version=anchors_version,
                router_policy_version=router_policy_version,
                run_id=run_id,
            )
            # If SIGINT was received during the await, mark the just-completed
            # cell as interrupted (the user wanted to stop; we honored the
            # in-flight contract by awaiting it).
            if sigint_received:
                row = row.model_copy(update={"status": "interrupted"})
            await record_benchmark_run(db_path, row)
            cells_completed += 1

            if cap_blocking:
                _logger.warning(
                    "benchmark.aborted_cost_cap run_id=%s cells_completed=%d "
                    "cells_aborted=%d cell=%s:%s:%s",
                    run_id,
                    cells_completed,
                    len(cells) - cells_completed,
                    cell.corpus_item_id,
                    cell.task_type,
                    cell.model,
                )
                return 2

            if sigint_received:
                _logger.warning(
                    "benchmark.sigint_received run_id=%s cells_completed=%d "
                    "last_cell=%s:%s:%s",
                    run_id,
                    cells_completed,
                    cell.corpus_item_id,
                    cell.task_type,
                    cell.model,
                )
                print(f"To resume: python -m benchmark.runner --resume {run_id}")
                return 130
        return 0
    finally:
        signal.signal(signal.SIGINT, prior_handler)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="benchmark.runner",
        description="Story 9.6: benchmark runner (Rule I — dispatches via ask_router force_model)",
    )
    parser.add_argument("--run-id", type=str, default=None, help="UUID per run; auto-generated if absent")
    parser.add_argument("--resume", type=str, default=None, metavar="RUN_ID", help="Resume an existing run by id")
    parser.add_argument("--corpus", type=str, default=_DEFAULT_CORPUS_PATH, help="Path to email_corpus_v1.jsonl")
    parser.add_argument("--tasks", type=str, default=None, help="Comma-separated task list (required for new runs)")
    parser.add_argument("--models", type=str, default=None, help="Comma-separated model list (required for new runs)")
    parser.add_argument(
        "--scorer-model",
        type=str,
        default=_DEFAULT_SCORER_MODEL,
        help="Frozen scorer model id for cohort_key",
    )
    parser.add_argument("--max-items", type=int, default=None, help="Cap corpus item count for quick runs")
    parser.add_argument("--yes", action="store_true", help="Auto-confirm cost gate (non-TTY contexts)")
    parser.add_argument(
        "--cost-mock",
        action="store_true",
        help=f"Set ${_COST_MOCK_ENV}=1 for the adapter layer (Story 9-8 hook)",
    )
    parser.add_argument("--db-path", type=str, default=None, help="SQLite path; defaults to $MAILBOT_DB_PATH")
    return parser.parse_args(argv)


def _resolve_db_path(cli_db_path: str | None) -> str:
    if cli_db_path:
        return cli_db_path
    env_path = os.environ.get("MAILBOT_DB_PATH", "")
    if not env_path:
        raise SystemExit(
            "MAILBOT_DB_PATH unset and --db-path not provided; refusing to dispatch"
        )
    return env_path


async def _run_async(args: argparse.Namespace) -> int:
    db_path = _resolve_db_path(args.db_path)

    if args.cost_mock:
        os.environ[_COST_MOCK_ENV] = "1"
        _logger.info("cost-mock mode requested; %s=1", _COST_MOCK_ENV)

    # Load corpus + anchors version + policy snapshot (all run-start frozen
    # values).
    corpus_path = Path(args.corpus)
    items = load_corpus(corpus_path)
    if args.max_items is not None:
        items = items[: args.max_items]
    items_by_id = {item.id: item for item in items}

    anchors_version = read_anchors_version(Path(_DEFAULT_ANCHORS_DIR))
    policy_versions, router_policy_version = _read_policy_versions()

    # Resume vs new-run pathway.
    if args.resume:
        run_id = args.resume
        completed = await read_completed_cells(db_path, run_id)
        if not completed:
            raise SystemExit(f"--resume specified but no rows found for run_id={run_id}")
        # Cross-check tasks/models against the existing run's grid (AC-4).
        existing_grid = await read_run_grid(db_path, run_id)
        existing_tasks = {t for t, _ in existing_grid}
        existing_models = {m for _, m in existing_grid}
        if args.tasks:
            requested = set(args.tasks.split(","))
            if requested != existing_tasks:
                raise SystemExit(
                    f"--resume grid mismatch: existing tasks={sorted(existing_tasks)} "
                    f"vs requested={sorted(requested)}"
                )
        if args.models:
            requested_models = set(args.models.split(","))
            if requested_models != existing_models:
                raise SystemExit(
                    f"--resume grid mismatch: existing models={sorted(existing_models)} "
                    f"vs requested={sorted(requested_models)}"
                )
        tasks = sorted(existing_tasks)
        models = sorted(existing_models)
    else:
        if not args.tasks or not args.models:
            raise SystemExit("New runs require both --tasks and --models")
        tasks = args.tasks.split(",")
        models = args.models.split(",")
        run_id = args.run_id or str(uuid.uuid4())
        completed = set()

    print(f"run_id={run_id}")

    cells = _build_grid(items, tasks, models, policy_versions, completed)
    if not cells:
        print("All cells already completed; nothing to do.")
        return 0

    # Cost gate (AC-5).
    total_cost, breakdown = _estimate_total_cost(cells, items_by_id)
    print(_format_cost_breakdown(total_cost, breakdown))

    if total_cost > _COST_GATE_THRESHOLD_USD and not args.yes:
        if not _confirm_proceed("Proceed? [y/N]: "):
            print("Aborted by user; no rows written.")
            return 0
    elif args.yes and total_cost > _COST_GATE_THRESHOLD_USD:
        _logger.info(
            "cost_gate.bypassed_via_yes_flag run_id=%s estimated_total_usd=%.2f",
            run_id,
            total_cost,
        )

    return await _run_dispatch_loop(
        cells=cells,
        items_by_id=items_by_id,
        db_path=db_path,
        scorer_model=args.scorer_model,
        anchors_version=anchors_version,
        router_policy_version=router_policy_version,
        run_id=run_id,
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO)
    args = _parse_args(argv)
    return asyncio.run(_run_async(args))


if __name__ == "__main__":
    sys.exit(main())
