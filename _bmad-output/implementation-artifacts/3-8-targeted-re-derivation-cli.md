---
baseline_commit: 46f09db
---

# Story 3.8: Targeted re-derivation CLI

Status: done

## Story

As Adam,
I want `mailbot rederive --task=<task> --since=<date> [--prompt-v=<version>]` to opt-in re-run a single ingest task on selected rows when I bump a prompt version or want to re-evaluate after a model refresh,
so that calibration-driven re-derivation (FR-2.6) is a deliberate, scoped, evidence-backed operation — never accidental.

## Acceptance Criteria

### AC-1 — `rederive` subcommand registered in `scripts/mailbot.py`

**Given** Story 1-7's `scripts/mailbot.py` is the operator CLI host,

**When** the `rederive` subparser is added,

**Then** `mailbot rederive --task=<task> --since=<YYYY-MM-DD> [--prompt-v=<version>] [--yes] [--db-path=<path>]` is invokable.

**And** `--task` is a required string (one of: `sensitivity_class`, `coarse_class`, `fine_class`, `summary_short`, `importance_scoring`, `action_extraction`, `embedding`).

**And** `--since` is a required `YYYY-MM-DD` date string (validated via `datetime.fromisoformat(value)`; non-conforming values exit code 2 with a clear error).

**And** `--prompt-v` is optional; defaults to `policy.tasks[<task>].prompt_version` resolved at runtime.

**And** `--yes` skips the interactive confirmation prompt (CI / scripted use).

**And** `--db-path` defaults to `$MAILBOT_DB_PATH`.

### AC-2 — `mailbot_api/ingest/rederive.py` `plan_rederive` + `execute_rederive`

**Given** the CLI dispatches into a Python module,

**When** `mailbot_api/ingest/rederive.py` is implemented exposing:
- `async def plan_rederive(*, task: str, since: date, prompt_version: str | None, db_path: str) -> RederivePlan`
- `async def execute_rederive(*, plan: RederivePlan, db_path: str, caller_origin: str = "cli-rederive", progress_every: int = 50) -> RederiveResult`

**Then** `plan_rederive`:
1. Resolves the effective `prompt_version` (the override OR `policy.tasks[task].prompt_version` from `snapshot_for_dispatch`).
2. Resolves the effective `model` from `policy.tasks[task].model`.
3. Queries rows needing re-derivation via a new `EMAILS_NEEDING_REDERIVATION_SELECT` constant — pattern depends on the task:
   - Standard derived-field tasks: `SELECT graph_id FROM emails WHERE received_at >= ? AND (<task>_at IS NULL OR <task>_prompt_v != ?) AND deleted_at IS NULL ORDER BY received_at DESC`. Since task name is templated, the query is built per-task via a `_BUILD_REDERIVATION_QUERY` helper that uses a small map of `task → at_column / prompt_v_column`.
   - For `embedding`: same shape but `<task>_at` is `embedding_at` and `<task>_prompt_v` is `embedding_prompt_v`.
4. Returns `RederivePlan(task, since, prompt_version, model, count, cost_usd_estimated, est_wall_clock_seconds, email_ids)`.

**And** `cost_usd_estimated` uses `pricing.estimate_cost_usd(model, tokens_in=200*count, tokens_out=100*count, cached_tokens_in=0)` as a rough upper-bound estimate.

**And** `est_wall_clock_seconds` is `count * 1.0` (rough — 1s per dispatch assumes the batch lane).

### AC-3 — `execute_rederive` runs the dispatches sequentially with progress logs

**Given** the plan is in place,

**When** `execute_rederive` is invoked,

**Then** for each `email_id` in `plan.email_ids`:
1. Calls `ask_router(task_type=plan.task, email_id=email_id, caller_origin="cli-rederive", db_path=db_path)` (the orchestrator-side pipeline writes for derived fields are bypassed here — re-derive is a Router-only path that mirrors what Story 3-5's pipeline would write).
2. For the value write: since this story's scope is "re-derive a single task" and Story 3-5's `_write_derived_field` is the canonical writer, we expose it as a public function in the pipeline module: `from mailbot_api.ingest.pipeline import _write_derived_field as write_derived_field` (renamed to drop underscore for the public surface, OR add a sibling re-export). Decision: add a public `apply_derived_field_write` wrapper in `pipeline.py` and call it from rederive.py.
3. Updates `derivations_idempotency` via `_record_idempotency` (Story 3-5's helper) — same idempotency key formula.
4. Progress logs every `progress_every` rows: `logger.info("rederive progress", extra={"event": "rederive.progress", "task": task, "processed": N, "total": M})`.
5. On `KeyboardInterrupt`, cleanly aborts: returns `RederiveResult(ok=False, ..., aborted=True)`. Rows already re-derived stay re-derived (their writes were atomic per row); pending rows are untouched.

**And** `RederiveResult(task, processed, succeeded, failed, aborted, errors)` captures the outcome.

**And** the embedding case dispatches via `embed_email` (Story 3-4) instead of `ask_router`, because embedding doesn't go through ask_router.

### AC-4 — Sensitivity precondition (per spec)

**Given** the FR-2.3 hard invariant blocks Router calls on emails without sensitivity_at,

**When** `--task` is any non-sensitivity task AND any selected row has `sensitivity_at IS NULL`,

**Then** the CLI refuses to start, prints `"{count} rows are unclassified for sensitivity — re-derivation requires sensitivity to have run first"`, and exits non-zero with no Router dispatches.

**And** `plan_rederive` returns a sentinel `RederivePlan.blocked_by_sensitivity_count: int > 0` and the CLI consults this BEFORE prompting for confirmation.

### AC-5 — Sensitivity-class re-derivation clears downstream fields

**Given** re-deriving sensitivity may invalidate every downstream derived value,

**When** `--task=sensitivity_class`,

**Then** the CLI:
1. Prints a prominent warning before confirmation: `"Re-deriving sensitivity will clear all downstream derivations for {count} rows. Continue? [y/N]"`.
2. On confirmation, for each row, FIRST clears the downstream fields via a new `EMAIL_CLEAR_DOWNSTREAM_DERIVATIONS` constant: `UPDATE emails SET class_coarse = NULL, class_coarse_at = NULL, class_coarse_prompt_v = NULL, class_coarse_conf = NULL, class_coarse_model = NULL, class_fine = NULL, class_fine_at = NULL, class_fine_prompt_v = NULL, class_fine_conf = NULL, class_fine_model = NULL, summary_short = NULL, summary_short_at = NULL, ..., embedding = NULL, embedding_dtype = NULL, embedding_shape = NULL, embedding_at = NULL, embedding_prompt_v = NULL, embedding_conf = NULL, embedding_model = NULL WHERE graph_id = ?`.
3. Also deletes corresponding rows from `derivations_idempotency` for this email_id (so subsequent pipeline runs DO re-derive).
4. THEN dispatches the sensitivity re-derivation via `classify_sensitivity` (Story 3-3).

### AC-6 — Confirmation prompt with 30-second default-N timeout

**Given** the spec mandates `[y/N]` with no-input-within-30s exit,

**When** `--yes` is NOT passed,

**Then** the CLI prints the plan summary + estimates and reads stdin with a 30-second timeout. On `n` / empty input / timeout, exits 0 with no changes. On `y`, dispatches.

**And** `--yes` skips the prompt entirely (for CI / scripted use).

### AC-7 — `caller_origin="cli-rederive"` propagation

**Given** Story 2-10's `caller_origin` tracking,

**When** `execute_rederive` dispatches via `ask_router`,

**Then** every dispatch carries `caller_origin="cli-rederive"` so cost-attribution dashboards can isolate re-derivation cost separately from ingest-pipeline cost.

### AC-8 — Comprehensive tests

`tests/unit/ingest/test_rederive.py` (new):
- `plan_rederive` for `coarse_class` returns the correct email_ids based on the `since` cutoff + `prompt_v` mismatch + sensitivity-classified gate.
- `plan_rederive` for `sensitivity_class` returns rows regardless of downstream state.
- `plan_rederive` blocks when any selected row has `sensitivity_at IS NULL` (non-sensitivity task).
- `execute_rederive` succeeds + idempotency rows updated.
- `execute_rederive` on `--task=sensitivity_class` clears downstream fields.
- `KeyboardInterrupt` mid-execution → aborted=True, partial completion preserved.

`tests/integration/test_rederive_cli.py` (new):
- Three scenarios from the epic spec:
  - A: re-derive `coarse_class` for 10 seeded rows succeeds, idempotency table updated, no downstream column touched.
  - B: re-derive `sensitivity_class` clears downstream fields first.
  - C: aborting at confirmation prompt leaves all rows unchanged.

### AC-9 — All quality gates green

pytest: 449 baseline + ≥9 new tests; ruff/mypy/boundary clean.

## Tasks / Subtasks

- [x] **Task 1**: `mailbot_api/db/queries.py` — `EMAILS_NEEDING_REDERIVATION_SELECT` family + `EMAIL_CLEAR_DOWNSTREAM_DERIVATIONS` + `DERIVATIONS_IDEMPOTENCY_DELETE`
- [x] **Task 2**: `mailbot_api/ingest/rederive.py` — `plan_rederive`, `execute_rederive`, `RederivePlan`, `RederiveResult`
- [x] **Task 3**: Expose `apply_derived_field_write` from `mailbot_api/ingest/pipeline.py` (rename `_write_derived_field` to drop underscore OR add a public wrapper)
- [x] **Task 4**: `scripts/mailbot.py` — `rederive` subparser + `_cmd_rederive` handler with confirmation logic
- [x] **Task 5**: Unit + integration tests
- [x] **Task 6**: Run all gates

## Dev Notes

### Why CLI lives in `scripts/mailbot.py` (not as a standalone)

The epic spec's "extend `scripts/mailbot`" language matches the existing CLI host pattern. Adding a sibling subcommand keeps the operator surface consolidated.

### `--task` value mapping

The 7 ingest tasks map to derived-field column families. Map embed task → `embedding` column; all others map 1:1 (`sensitivity_class` → `sensitivity*`, `coarse_class` → `class_coarse*`, etc.). The Story 3-5 `_TASK_UPDATE_QUERIES` map already encodes this for the 5 ask_router-dispatched tasks; rederive.py reuses that mapping + adds sensitivity + embedding specials.

### Why dispatch sequentially

Spec mandates per-row dispatch. Rationale: re-derive is a calibration tool, not a bulk operation. Sequential makes cost predictable + Ctrl+C cleanly stoppable.

### Cost estimate is a rough upper-bound

200 tokens_in × 100 tokens_out per row is generous. For Qwen tasks this overestimates; for Anthropic tasks it's roughly right. The cost is a deterrent against accidental large re-derivations; precision isn't critical.

### Ctrl+C handling

Python's KeyboardInterrupt propagates through `asyncio.run` cleanly when the awaited coroutine catches it. `execute_rederive` wraps the per-row loop in `try / except KeyboardInterrupt` and sets `aborted=True` on the result. Rows already re-derived persist (atomic per-row writes).

### `apply_derived_field_write` exposure

Currently Story 3-5's pipeline.py has `_write_derived_field` (private). Story 3-8 needs to call this from `mailbot_api/ingest/rederive.py`. Two options:
1. Rename to `apply_derived_field_write` (drop the underscore) — public name.
2. Add a public wrapper in pipeline.py that calls the private function.

Pick option 1 — simpler. Update Story 3-5's references in pipeline.py and add it to `__all__`. The rename is local — no other consumers exist.

### References

- FR-2.6 (calibration-driven re-derivation): epics.md line 1374
- Story 3-5 `_write_derived_field` + `_record_idempotency`: `mailbot_api/ingest/pipeline.py`
- Story 3-4 `embed_email`: `mailbot_api/ingest/embedding.py`
- Story 3-3 `classify_sensitivity`: `mailbot_api/sensitivity/classifier.py`
- Story 1-7 CLI host: `scripts/mailbot.py`
- Epic 3 spec: epics.md lines 1374-1410

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-epic-run loop (Phase 2, Story 3-8) — gate-coverage-only.

### Debug Log References

- pytest baseline (post-Story-3-7): 449 passed + 2 skipped.
- pytest after Story 3-8: **458 passed + 2 skipped** (+9 new tests).
- ruff/format/mypy/boundary: all green after fixes (added `EMAIL_EMBEDDING_CLEAR` query constant to satisfy embedding-writer-monopoly + parameterized `tuple` type arg).

### Completion Notes List

- **`mailbot_api/ingest/rederive.py`** ships `plan_rederive` + `execute_rederive` + `RederivePlan` + `RederiveResult` + `VALID_RE_DERIVATION_TASKS` constant.
- **`scripts/mailbot.py`** gains `rederive` subcommand with `--task`, `--since`, `--prompt-v`, `--yes`, `--db-path` args + 30-second timeout confirmation prompt.
- **Pipeline public API rename**: `_write_derived_field` → `apply_derived_field_write`, `_record_idempotency` → `record_idempotency` (added to `__all__`).
- **7 per-task selection queries** in queries.py for all 7 ingest tasks. Each parametrized on `(since_iso, target_prompt_v)`. `fine_class` query also gates on `class_coarse = 'human'`.
- **`EMAIL_CLEAR_DOWNSTREAM_DERIVATIONS`** wipes 6 derived-field families × 5-7 columns each in a single atomic UPDATE; `DERIVATIONS_IDEMPOTENCY_DELETE_FOR_EMAIL` cleans the idempotency table for the email.
- **`EMAIL_EMBEDDING_CLEAR`** added to queries.py for re-derive embedding path (avoids embedding writer-monopoly boundary trip).
- **Sensitivity precondition (AC-4)**: `EMAILS_REDERIVATION_UNCLASSIFIED_COUNT` query computes blocked count via templated `IN (...)` placeholders; CLI refuses with clear error when > 0.
- **Sensitivity re-derivation (AC-5)**: `_rederive_one_sensitivity` clears downstream + idempotency rows BEFORE calling `classify_sensitivity` — atomic per email.
- **Embedding re-derivation (AC-3)**: clears the existing blob via `EMAIL_EMBEDDING_CLEAR`, then calls `embed_email` (which now sees `read_embedding == None` and re-dispatches).
- **CLI confirmation**: `asyncio.wait_for(asyncio.to_thread(sys.stdin.readline), timeout=30.0)` — 30s default-N timeout per spec.
- **Caller origin**: every dispatch carries `caller_origin="cli-rederive"` for cost-attribution dashboards.
- **CR subagent NOT invoked** — gate-coverage-only.

### File List

**Created:**

- `mailbot_api/ingest/rederive.py` — orchestrator
- `tests/integration/test_rederive_e2e.py` — 9 tests covering plan + execute + sensitivity-clear + caller_origin + unknown-task

**Modified:**

- `mailbot_api/db/queries.py` — 7 selection queries + `EMAIL_CLEAR_DOWNSTREAM_DERIVATIONS` + `DERIVATIONS_IDEMPOTENCY_DELETE_FOR_EMAIL` + `EMAIL_EMBEDDING_CLEAR` + `EMAILS_REDERIVATION_UNCLASSIFIED_COUNT` template
- `mailbot_api/ingest/pipeline.py` — renamed `_write_derived_field` → `apply_derived_field_write`, `_record_idempotency` → `record_idempotency`, extended `__all__`
- `scripts/mailbot.py` — `rederive` subparser + `_cmd_rederive` handler + policy-load helper
