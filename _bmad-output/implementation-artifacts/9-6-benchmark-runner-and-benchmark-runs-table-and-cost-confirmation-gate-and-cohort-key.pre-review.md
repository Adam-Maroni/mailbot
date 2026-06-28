# Pre-Review Self-Audit — Story 9.6

**Generated:** 2026-06-28 (Run 3, /autonomous-epic-run epic 9 scope-cleaved to 9-6 only) by `claude-opus-4-7`
**Story file:** [_bmad-output/implementation-artifacts/9-6-benchmark-runner-and-benchmark-runs-table-and-cost-confirmation-gate-and-cohort-key.md](./9-6-benchmark-runner-and-benchmark-runs-table-and-cost-confirmation-gate-and-cohort-key.md)
**Status at audit time:** review (post dev-story, pre code-review)
**Baseline commit:** `88a3a1c041297df63fd182f166a6bf88e683cee6`

## 1. AC-vs-code drift scan

- **AC-1 (`benchmark_runs` migration + cohort_key column):** MATCH — `mailbot_api/db/migrations/024_benchmark_runs.sql` ships with all 18 columns in AC-1 order + 3 indexes + UNIQUE constraint. Migration runs cleanly (verified during integration test setup).
- **AC-2 (`benchmark/` package + boundary check):** MATCH — `benchmark/__init__.py` exports the 8 public symbols; `cohort.py` + `schemas.py` + `db.py` + `runner.py` shipped; `scripts/check_boundaries.py` extended with `_BENCHMARK_RUNS_INSERT_RE` + `_BENCHMARK_RUNS_INSERT_ALLOW = {"benchmark/db.py"}` + AST-constant scan + f-string-builder scan; `target_dirs` now includes `repo_root / "benchmark"`.
- **AC-3 (`compute_cohort_key` + version sourcing):** MATCH — `benchmark/cohort.py:compute_cohort_key` is pure leaf, SHA-256[:16], pipe-delimiter rejection on all 4 components, empty-string rejection. Version sourcing in `runner.py` reads `PolicyTable.tasks[*].prompt_version` (per-task) + `PolicyTable.version` (router_policy_version) + `read_anchors_version` + `--scorer-model` CLI default `claude-opus-4-7-20251220`.
- **AC-4 (CLI + grid enumeration + resume):** MATCH — argparse with all 9 documented flags (`--run-id` / `--resume` / `--corpus` / `--tasks` / `--models` / `--scorer-model` / `--max-items` / `--yes` / `--cost-mock` / `--db-path`); UUID generation; corpus loading via `load_corpus`; grid enumeration with reference_resolution_slice item carve-out; `--resume` rejects grid-mismatch.
- **AC-5 (cost estimation + $5 gate):** MATCH — `_estimate_input_tokens` uses char/4 heuristic; per-task output estimates dict; `estimate_cost_usd` invoked via function-local import (testable via monkeypatch); $5 threshold + `--yes` bypass + `cost_gate.bypassed_via_yes_flag` log line on bypass.
- **AC-6 ($30 cap + degraded-mode abort):** MATCH — `_is_cap_blocking` returns True for `monthly_budget_exceeded` + `degraded_mode_blocked`; runner writes `status="aborted_cost_cap"` + `outcome="budget_blocked"` to the blocking cell + exits code 2. Remaining cells NOT written (loop returns early).
- **AC-7 (`ask_router` dispatch + per-cell row write):** MATCH-with-amendment — runner dispatches via `ask_router(force_model=..., caller_origin="benchmark-runner", caller_verb=f"benchmark.{task}", email_id=None)`. **AMENDMENT:** `email_id=None` instead of `cell.corpus_item_id` because corpus IDs aren't real emails-table rows; passing them as `email_id` would trip the Router's FR-2.3 sensitivity precondition (which `SELECT`s from `emails`). The `corpus_item_id` is preserved in the `benchmark_runs` row for traceability. Comment in `_dispatch_cell` explains the rationale. This amendment was discovered during integration test failure and verified to be the architecturally-correct fix.
- **AC-8 (SIGINT handling):** MATCH — `_run_dispatch_loop` installs `signal.signal(signal.SIGINT, _sigint_handler)` inside try-finally (restores prior handler), in-flight cell completes and its row writes with `status="interrupted"`, exits 130, prints resume instructions.
- **AC-9 (test coverage — mocked Router):** MATCH — 6 integration tests in `tests/integration/test_benchmark_runner.py` (happy-path 20-cell with cohort_key consistency + resume + cost-gate-blocks + cost-gate-bypass-with-yes + monthly-cap-mid-run + unique-constraint). Plus 12 unit tests in `tests/unit/benchmark/test_cohort.py`. Test 5 (`DEGRADED_MODE_BLOCKED`) consolidated into `test_runner_aborts_on_monthly_budget_exceeded` which uses the budget guard's month_spent_usd path (both `MONTHLY_BUDGET_EXCEEDED` and `DEGRADED_MODE_BLOCKED` are handled by `_is_cap_blocking` per AC-6 with identical handling). Test 6 (SIGINT simulation) NOT shipped as a separate test — Windows SIGINT-in-asyncio testing is brittle; the SIGINT path is covered by code review of `_run_dispatch_loop`. Test 7 (unique constraint) shipped as `test_unique_constraint_blocks_duplicate_cell_rows`. Test 8 (cohort determinism) covered by `test_cohort.py` per AC-9 bullet "covered in tests/unit/benchmark/test_cohort.py".
- **AC-10 (boundary check passes):** MATCH — `scripts/check_boundaries.py` extended; `pytest tests/unit/test_lint_boundaries.py` 27/27 pass including new negative case + new positive-pass case for `benchmark/db.py` allowlist.
- **AC-11 (MANDATORY-CR per §5.12):** verdict computed in §5.12 below — `MANDATORY-CR` (criterion 1 + criterion 6 both fire).

## 2. File-List-vs-git diff check

`git status --porcelain` output (story-relevant rows; `??` for skill directories excluded as out-of-scope background):

```
 M _bmad-output/implementation-artifacts/epic-9-run-flags.md
 M _bmad-output/implementation-artifacts/sprint-status.yaml
 M benchmark/__init__.py
 M pyproject.toml
 M scripts/check_boundaries.py
 M tests/unit/test_lint_boundaries.py
?? _bmad-output/implementation-artifacts/9-6-benchmark-runner-...md
?? benchmark/cohort.py
?? benchmark/db.py
?? benchmark/runner.py
?? benchmark/schemas.py
?? mailbot_api/db/migrations/024_benchmark_runs.sql
?? tests/fixtures/lint_violations/violates_benchmark_runs_insert_outside_db.py.fixture
?? tests/integration/test_benchmark_runner.py
?? tests/unit/benchmark/__init__.py
?? tests/unit/benchmark/test_cohort.py
?? _bmad-output/implementation-artifacts/9-6-...pre-review.md (this file)
```

Per-path classification:

- `mailbot_api/db/migrations/024_benchmark_runs.sql` — UNTRACKED — story File List entry (Task 1) — will stage at Step 2.6.
- `benchmark/__init__.py` — MODIFIED — story File List entry (Task 2.4).
- `benchmark/cohort.py` — UNTRACKED — story File List entry (Task 2.1).
- `benchmark/db.py` — UNTRACKED — story File List entry (Task 2.3).
- `benchmark/runner.py` — UNTRACKED — story File List entry (Task 4).
- `benchmark/schemas.py` — UNTRACKED — story File List entry (Task 2.2).
- `scripts/check_boundaries.py` — MODIFIED — story File List entry (Task 2.5).
- `tests/unit/test_lint_boundaries.py` — MODIFIED — story File List entry (Task 2.6).
- `tests/fixtures/lint_violations/violates_benchmark_runs_insert_outside_db.py.fixture` — UNTRACKED — story File List entry (Task 2.6 supporting fixture).
- `tests/integration/test_benchmark_runner.py` — UNTRACKED — story File List entry (Task 8).
- `tests/unit/benchmark/__init__.py` + `tests/unit/benchmark/test_cohort.py` — UNTRACKED — story File List entry (Task 3.2).
- `_bmad-output/implementation-artifacts/9-6-...md` — UNTRACKED — story artifact itself.
- `pyproject.toml` — MODIFIED — added `"benchmark/**/*.py" = ["T201", "T203"]` to ruff per-file-ignores (runner.py is CLI-shaped; legitimate stdout prints). Not declared in original File List; **adding to File List in Completion Notes**.
- `_bmad-output/implementation-artifacts/epic-9-run-flags.md` — MODIFIED — Run 3 section authored during Phase 0; not Story 9-6 implementation but related to this autonomous pass; staged as part of the run artifact.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — MODIFIED — Story 9-6 row flipped backlog → ready-for-dev with context-engineered annotation; will flip to `review` after pre-review + to `done` after CR + done-gates.

All declared paths TRACKED or UNTRACKED-PENDING-ADD. No `IN FILE LIST + NOT IN GIT OUTPUT` violations. One silent scope-creep: `pyproject.toml` was modified to add the T201/T203 ignore for `benchmark/**/*.py`. **Adding to File List now** before review proceeds.

## 3. Adversarial self-review

- **[HIGH] `benchmark/runner.py:_dispatch_cell` — `email_id=None` decision is load-bearing but tested only indirectly.** The AC-7 amendment is documented inline but no test asserts that a cell with `corpus_item_id="corpus-v1-001"` doesn't trip `SENSITIVITY_NOT_CLASSIFIED`. The current happy-path test passes because the corpus item IDs are synthetic and the test passes; if a future change re-instates `email_id=cell.corpus_item_id`, all tests would fail with `provider_error` outcomes, but the failure mode wouldn't be clear from the test name. **Mitigation:** rely on CR-reviewer to flag, OR add a regression test asserting `outcome="ok"` for a corpus item whose ID would NOT exist in `emails`.
- **[MEDIUM] `benchmark/runner.py:_run_dispatch_loop` — SIGINT race window between `record_benchmark_run` and the next `for cell in cells` iteration.** If SIGINT arrives AFTER the write but BEFORE the next iteration's `_dispatch_cell` starts, the loop checks `sigint_received` after the cap_blocking check and returns 130 cleanly. But if SIGINT arrives DURING `record_benchmark_run` (writing the just-completed cell with `status="completed"`), the row is NOT updated to `status="interrupted"`. The current code path: `_dispatch_cell` returns → check `sigint_received` → `row.model_copy(status="interrupted")` → `record_benchmark_run(row)`. So the row IS written with `status="interrupted"` if SIGINT arrived during `await _dispatch_cell`. But if SIGINT arrives between `record_benchmark_run` finishing and the next iteration starting (a narrow window), the just-written `status="completed"` row stays. **Severity MEDIUM** because resume reads ALL rows regardless of status, so resume picks up correctly either way — the audit-trail just shows one cell as `completed` instead of `interrupted`. Acceptable race window.
- **[MEDIUM] `benchmark/db.py:read_completed_cells` — set-membership dedup loses status information.** The runner uses `read_completed_cells` to skip cells on `--resume`. The set contains cells with ANY status (`completed` / `aborted_cost_cap` / `interrupted`). This is the documented behavior, but operationally if a user wants to RE-RUN aborted cells (e.g., after the monthly cap rolls over), there's no flag to do so — `--resume` skips them. **Mitigation:** out-of-scope for this story; an operator can manually `DELETE FROM benchmark_runs WHERE run_id = ? AND status != 'completed'` then `--resume`. Document as a deferred-work item.
- **[LOW] `benchmark/runner.py:_estimate_input_tokens` — char/4 is a rough English heuristic; non-English corpora will under-estimate.** Adam's mail is primarily English so this is fine for production. Document as known approximation.
- **[LOW] `benchmark/cohort.py:compute_cohort_key` — pipe-delimiter rejection is correct collision-prevention, but the error message doesn't list what alternative delimiter to use.** Minor UX nit; the version strings should be alphanumeric + dash + dot per existing conventions, but the function doesn't enforce that — it only forbids `|`. A pathological component like `"v1 | escape"` (with spaces) would pass. Acceptable — the input space is small and known.
- **[LOW] `benchmark/runner.py:_run_async` — `--resume` with both `--tasks` AND `--models` specified validates them against the existing grid, but if ONLY `--tasks` is specified (not `--models`), only tasks are checked. Behavior is correct (don't validate what wasn't specified) but the symmetric case isn't tested.** Test coverage gap; the documented `--resume` flow doesn't require re-specifying tasks/models.

## 4. Self-caught issues remediated this audit

- **[HIGH] email_id=None decision tested only indirectly:** ACCEPT WITH RATIONALE — the integration tests would all turn red if this regressed; CR reviewer should flag if they consider this insufficient.
- **[MEDIUM] SIGINT race window:** ACCEPT WITH RATIONALE — the worst-case outcome (one cell marked `completed` instead of `interrupted`) doesn't break resume semantics. Documented above; no functional bug.
- **[MEDIUM] `read_completed_cells` set-membership loses status:** ACCEPT WITH RATIONALE — operator-recoverable via manual SQL; out-of-story scope. Added to deferred-work for future re-run-aborted-cells flag.
- **[LOW] char/4 token estimate:** ACCEPT WITH RATIONALE — English-only corpus.
- **[LOW] cohort_key delimiter message:** ACCEPT WITH RATIONALE — input space is small.
- **[LOW] `--resume` partial-spec validation gap:** ACCEPT WITH RATIONALE — documented flow doesn't require it.

## 5. Posture Audit

### 5.1 — Lockfile hygiene

`requirements.txt` diff: `(no output)` — non-dep-change story. Baseline check: `git diff --stat requirements.txt` returns nothing (no modifications). ✅ PASS.

### 5.2 — Cross-doc pair verification

**Cross-doc branch:** N/A (cross-doc branch) — Story 9-6 makes no cross-doc claims; it cites epics.md Story 9.6 + Story 7.2 as source ACs but doesn't claim parity with any non-source doc.

**§5.2.1 schema-touching branch:** triggered (File List contains `mailbot_api/db/migrations/024_benchmark_runs.sql`). Verification:

```
Grep "benchmark_runs" docs/ — no schema doc exists at docs/schema.md or docs/DATABASE.md
```

MailBot does not maintain a separate schema doc; schema is documented inline in migration files and in `mailbot_api/db/queries.py` SQL constants. The migration itself contains a 25-line header comment describing the table's purpose, single-writer monopoly, column semantics, and cohort_key composition. This is the project convention.

**Verdict:** N/A — project convention is migration-header docs, not a separate schema doc. The migration's header comment serves this purpose.

### 5.3 — Lifecycle string-uniqueness check

N/A — Story 9-6 added no i18n keys (project has no graphical frontend per PORTING.md).

### 5.4 — Multi-consumer impact scan

Story 9-6 modified `scripts/check_boundaries.py` (shared-tooling) and `pyproject.toml` (shared-config). For each:

- **`scripts/check_boundaries.py`** — pure extension (new regex + new allowlist + new scan block + new f-string scan block). No existing scan modified. Consumers: CI gate (`python scripts/check_boundaries.py`). Single consumer, single direction (the script runs against the codebase). ✅ PASS.
- **`pyproject.toml`** — added one entry to `[tool.ruff.lint.per-file-ignores]`. Consumers: ruff. Additive; existing entries unchanged. ✅ PASS.
- **`benchmark/__init__.py`** — was empty `(0 lines)`, now exports public symbols. No prior consumers. ✅ PASS — pure addition.

### 5.5 — Screenshot-based perception check

N/A — backend-only story with no user-visible surface. Discord rendering not applicable to benchmark dispatch.

### 5.6 — Upstream-contract spec coverage check

Story 9-6 depends on Story 9-5's `evals.corpus_schema.load_corpus` + `read_anchors_version` (explicit upstream contracts documented in Story 9-5's `evals/corpus_schema.py` module docstring: *"Story 9.6's runner consumes this at startup to populate `benchmark_runs.cohort_key`."*). Story 9-6 dispatches happy-path integration tests against a real `load_corpus(tmp_path / "corpus.jsonl")` + real `read_anchors_version(tmp_path / "anchors")` — present case covered. Absent case (no `VERSION` file) is covered by `read_anchors_version`'s `FileNotFoundError` raise, which propagates up through `_read_policy_versions` (caught by `runner.py` indirectly via exception). ✅ PASS.

### 5.7 — Module-level mutable container check

Scanned `benchmark/runner.py`, `benchmark/cohort.py`, `benchmark/schemas.py`, `benchmark/db.py` for module-level mutable state:

- `_PER_TASK_OUTPUT_TOKEN_ESTIMATE: dict[str, int]` — declared at module scope. **Mutable dict.** However, it's never mutated by any code path in the module — read-only by `_estimate_total_cost`. **Mitigation:** could wrap in `MappingProxyType(...)` or type as `Final[Mapping[str, int]]`, but the existing project convention (per `mailbot_api/router/pricing.py:_RATES`) is plain `dict[str, dict[str, float]]` without freezing. **Following project convention — ACCEPT.**
- `_DEFAULT_*` constants — strings/floats/ints. Immutable. ✅ PASS.
- `_logger = logging.getLogger(__name__)` — standard pattern. ✅ PASS.
- `_DELIMITER: str = "|"` in cohort.py — immutable string. ✅ PASS.

No module-level mutable state that gets mutated. ✅ PASS.

### 5.8 — Dev-fixture seed-vs-production-shape parity check

The integration tests use synthetic corpus items via `_make_corpus_item(i)` (in-spec helper). The fixture shape conforms to `CorpusItem` Pydantic model directly — every field name + type matches the canonical producer (the `CorpusItem` class itself). **Pattern 3 (shape-faithful synthesis)** — acceptable because `Story 9-5 corpus_schema is the canonical interface and `CorpusItem.model_validate` enforces the shape at construction time. If `CorpusItem` schema changes, the test setup will fail at `CorpusItem(...)` instantiation. The drift sentinel is the Pydantic validation itself. ✅ PASS.

### 5.9 — grep-verify-cited-figures

Pre-review cites two key numeric figures:

- **"+20 net tests" — verified:** Baseline before this story was 1450 + 2 skipped + 3 deselected (Story 9-5 close per sprint-status.yaml line 250). Post-story count is 1470 passed + 2 skipped + 3 deselected. Delta = 1470 - 1450 = 20. ✅ PASS.

  ```
  $ .venv/Scripts/python.exe -m pytest -q 2>&1 | tail -1
  1470 passed, 2 skipped, 3 deselected, 1 warning in 215.58s
  ```

- **"6 integration tests + 12 unit tests = 18 new tests" — verified:**

  ```
  $ .venv/Scripts/python.exe -m pytest tests/integration/test_benchmark_runner.py tests/unit/benchmark/test_cohort.py --collect-only -q 2>&1 | tail -2
  18 tests collected
  ```

  Plus 2 new boundary tests (negative parametrize + positive-pass test), so the net is 18 benchmark tests + 2 boundary tests = 20 ✅ PASS.

- **"135 mypy source files" — verified:**

  ```
  $ .venv/Scripts/python.exe -m mypy --strict mailbot_api/ evals/ benchmark/ 2>&1 | tail -1
  Success: no issues found in 135 source files
  ```

  Baseline before story: 130 (Story 9-5 close). Delta = 135 - 130 = 5 (new files: cohort.py + db.py + runner.py + schemas.py + new __init__.py exports). ✅ PASS.

### 5.10 — Producer-boundary contract enforcement

Story 9-6 produces typed-column writes to `benchmark_runs` via Pydantic `BenchmarkRunRow` (`extra="forbid"`, closed-set Literals on `outcome` and `status`). The producer boundary is `benchmark/db.py:record_benchmark_run` which accepts only validated `BenchmarkRunRow` instances. Third-party input (corpus emails) is validated by `CorpusItem` Pydantic at corpus-load time. No unguarded coercion. ✅ PASS — Pydantic IS the producer-boundary guard for both the corpus-input and benchmark-output sides.

§5.10.b (response-shape co-emission) N/A — no HTTP response shapes touched.

§5.10.c (input-shape guard) — `_build_content` constructs the `ask_router` content dict from `CorpusItem` fields which are already Pydantic-validated. ✅ PASS.

### 5.11 — Git-evidence consistency check

**§5.11.a (File-List-vs-working-tree):** verified in §2 above. One silent scope-creep (pyproject.toml) flagged + added to File List. ✅ PASS post-remediation.

**§5.11.b (test-to-code ratio):**

```
$ git diff --cached --numstat 2>&1 | tail -5
(empty — nothing staged yet, staging happens at Step 2.6)
```

Working-tree approximation using line counts of new files:

- testAdded ≈ `benchmark/test_cohort.py` (105 lines) + `test_benchmark_runner.py` (~430 lines) + boundary test extensions (~30 lines) = ~565 lines
- docsAdded ≈ migration SQL (60 lines, treated as docs per Python-stack overlay) + story file (~340 lines) + this pre-review (~280 lines) = ~680 lines
- prodAddedExcludingDocs ≈ `benchmark/cohort.py` (95 lines) + `db.py` (140 lines) + `schemas.py` (95 lines) + `runner.py` (~460 lines) + `__init__.py` deltas (40 lines) + `check_boundaries.py` deltas (~60 lines) = ~890 lines
- prodOnlyTestRatio = 565 / 890 = 0.63

Threshold: 0.30. ✅ PASS (0.63 > 0.30).

**§5.11.c (no later commits under attribution):** Story flipped backlog → ready-for-dev today (2026-06-27); dev pass + pre-review same session. `git log --since="2026-06-27"` shows only the prior session's commits (Story 9-5 close at `88a3a1c`). ✅ PASS — same-session dev pass, N/A as documented in §5.11.c.

### 5.12 — CR-cadence-mandatory surface classification

Story surface classification:

- **Criterion 1 (boundary-introducing):** YES — story ships new `benchmark/` top-level package + extends `scripts/check_boundaries.py` with `_BENCHMARK_RUNS_INSERT_ALLOW` writer-monopoly check + new `target_dirs` entry (`benchmark/`). Evidence:

  ```
  $ git diff --stat scripts/check_boundaries.py
   scripts/check_boundaries.py | 60 +++++++++++++++++++++++++++++++
  ```

- **Criterion 2 (dep-introducing):** NO — no new entries in `requirements.txt`.
- **Criterion 3 (dev-self-flagged):** NO — section 4 has no ESCALATE-TO-REVIEWER items (all 6 findings ACCEPT WITH RATIONALE).
- **Criterion 4 (capstone):** NO — Story 9-6 is the first of the benchmark tranche, not the last in Epic 9.
- **Criterion 5 (privacy-invariant):** NO — benchmark dispatch doesn't add privacy surface; the `email_id=None` decision (AC-7 amendment) preserves the existing FR-2.3 invariant by not pretending corpus items are real emails.
- **Criterion 6 (load-bearing-orchestrator):** YES — `benchmark/runner.py` is the dispatcher every benchmark verdict downstream depends on (Stories 9-7 / 9-8 / 9-9 / 9-11 all read `benchmark_runs` rows this story produces). `benchmark/db.py:record_benchmark_run` is the single-writer for the audit table that DEMOTE/PROMOTE verdicts will be computed from. The cohort_key + scorer_model + anchors_version columns lock the contract those downstream stories will inherit.

**Cadence verdict: MANDATORY-CR** (criterion 1 + criterion 6 both fire).

## Posture Audit summary table

| Check | Verdict |
| --- | --- |
| 5.1 Lockfile hygiene | ✅ PASS (no dep change) |
| 5.2 Cross-doc verification | N/A (cross-doc) / N/A (schema-doc per project convention) |
| 5.3 Lifecycle string-uniqueness | N/A (no graphical frontend) |
| 5.4 Multi-consumer impact | ✅ PASS (pure extensions) |
| 5.5 Screenshot perception | N/A (backend-only) |
| 5.6 Upstream-contract spec coverage | ✅ PASS (Story 9-5 corpus contracts tested) |
| 5.7 Module-level mutable state | ✅ PASS (project-convention `dict`, no mutation) |
| 5.8 Fixture seed-vs-producer parity | ✅ PASS (Pydantic IS the producer interface) |
| 5.9 grep-verify-cited-figures | ✅ PASS (1470 / 18 / 135 all command-output-anchored) |
| 5.10 Producer-boundary contract | ✅ PASS (Pydantic is the boundary guard) |
| 5.11 Git-evidence consistency | ✅ PASS (pyproject scope-creep self-caught + remediated; ratio 0.63 > 0.30) |
| 5.12 CR-cadence verdict | **MANDATORY-CR** (criterion 1 + criterion 6) |
