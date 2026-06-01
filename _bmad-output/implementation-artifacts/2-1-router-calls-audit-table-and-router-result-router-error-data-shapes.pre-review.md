# Pre-Review Self-Audit — 2-1-router-calls-audit-table-and-router-result-router-error-data-shapes

**Generated:** 2026-06-01 by claude-opus-4-7
**Story file:** _bmad-output/implementation-artifacts/2-1-router-calls-audit-table-and-router-result-router-error-data-shapes.md
**Status at audit time:** review (post dev-story, pre code-review)

## 1. AC-vs-code drift scan

- **AC-1 (router_calls migration):** `MATCH` — `mailbot_api/db/migrations/006_router_calls.sql` creates the table with all 17 columns from the AC list (`id`, `ts`, `task_type`, `prompt_version`, `model_chosen`, `model_chosen_reason`, `tokens_in`, `tokens_out`, `cached_tokens_in`, `cost_usd_estimated`, `latency_ms`, `outcome`, `caller_verb`, `caller_origin`, `email_id`, `sensitivity_grant_id`, `sensitivity_grant_minted_at`) and the 3 indexes (`ix_router_calls_ts`, `ix_router_calls_task_type_model_chosen`, `ix_router_calls_email_id`). Numbering bumped from 005→006 per Dev Notes "Migration numbering variance" — documented in the story file, runtime-correct.

- **AC-2 (ErrorCode enum):** `MATCH` — `mailbot_api/router/errors.py:ErrorCode` has exactly the 15 members from the spec (parametric assertion in `test_error_code_has_exactly_15_members` is the canonical guarantee). `str`-backed via `class ErrorCode(str, Enum)`. Values are lowercase snake_case.

- **AC-3 (RouterError + RouterResult Pydantic models):** `MATCH` — Both shipped in `errors.py` with the full field set from spec. `RouterError(code: ErrorCode, message: str, model_attempted: list[str], retryable: bool)`. `RouterResult(ok, output, error, cost_usd, latency_ms, tokens_in, tokens_out, cached_tokens_in, model_used)` + `arbitrary_types_allowed=True` for the polymorphic `output: BaseModel | None`. The `(ok, error)` consistency invariant is enforced via `@model_validator(mode="after")`.

- **AC-4 (sanitize_error helper):** `MATCH` — `sanitize_error(exc: BaseException) -> str` in `errors.py` redacts Bearer / sk- / URL query-token / secret file paths, strips Traceback blocks, and collapses to a single line with `"; "` separators. Regex constants imported from `observability/logging` (no circular dep verified at module-import time during pytest collection).

- **AC-5 (RouterCallRow + record_router_call writer):** `MATCH` — `mailbot_api/observability/audit.py` ships `RouterCallRow` Pydantic model (mirrors migration columns 1:1) and `async def record_router_call(row, *, db_path)` that builds the param tuple in column-order and calls `connection.execute_write(...)` with `queries.ROUTER_CALLS_INSERT`. Tested end-to-end against real SQLite in `test_audit.py`.

- **AC-6 (boundary enforcement for router_calls writes):** `MATCH WITH DOCUMENTED VARIANCE` — Enforcement at AST scan in `scripts/check_boundaries.py` (not via ruff config), per Dev Notes "Why boundary checker, not ruff". Story file documents the variance explicitly. Allowlist: `observability/audit.py`, `db/queries.py`, `db/migrations_runner.py`. Migration `.sql` is not Python-AST-scanned, which is fine. Fixture-based test in `test_lint_boundaries.py` confirms a file outside the allowlist fails the check.

- **AC-7 (unit test coverage):** `MATCH` — `tests/unit/observability/test_audit.py` covers write-readback + UTC Z round-trip + caller_origin default + `escalated_from_<X>` reason form + 4 parametric bad-reason + 5 parametric bad-outcome cases. `tests/unit/router/test_errors.py` covers enum membership (1 + 15 parametric) + RouterError code-validation + RouterResult (ok, error) consistency + sanitize_error redaction rules across all 4 categories + traceback collapse + exception-type preservation + stripped-whitespace.

- **AC-8 (boundary checker tests):** `MATCH` — `tests/unit/test_lint_boundaries.py::test_boundary_violations_caught_by_check_boundaries` extended with the new fixture; the parametric expansion fires the boundary-check binary against a fixture placed in `mailbot_api/verbs/` and asserts the violation message contains `INSERT INTO router_calls`.

- **AC-9 (all gates green):** `MATCH` — `ruff check .` → "All checks passed!"; `mypy --strict mailbot_api/` → "Success: no issues found in 23 source files"; `pytest -q` → 149 passed (102 baseline + 47 new). Standalone `python scripts/check_boundaries.py` → exit 0.

No drift requiring story-file AC text updates.

## 2. File-List-vs-git diff check

Story File List vs `git status --porcelain`:

- `mailbot_api/db/migrations/006_router_calls.sql` — `TRACKED` (??) — new file, untracked but on the create list. Will be `git add`ed at Step 2.6.
- `mailbot_api/router/errors.py` — `TRACKED` (??) — same.
- `mailbot_api/observability/audit.py` — `TRACKED` (??) — same.
- `tests/unit/router/__init__.py` — `TRACKED` (??) — same (under untracked `tests/unit/router/` directory).
- `tests/unit/router/test_errors.py` — `TRACKED` (??) — same.
- `tests/unit/observability/test_audit.py` — `TRACKED` (??) — same.
- `tests/fixtures/lint_violations/violates_router_calls_insert_outside_audit.py.fixture` — `TRACKED` (??) — same.
- `mailbot_api/db/queries.py` — `MODIFIED` (M).
- `scripts/check_boundaries.py` — `MODIFIED` (M).
- `tests/unit/test_lint_boundaries.py` — `MODIFIED` (M).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `MODIFIED` (M) — sprint-state update.

All paths in File List exist on disk per git status. No untracked path is missing from File List. No File List entry is missing on disk. The `??` entries become `git add` candidates at Step 2.6; the Step 2.4.6 gate requires them to be `git ls-files --error-unmatch`-resolvable AFTER staging, not now. Pre-stage state is correct.

Pre-existing untracked items (`.claude/skills/`, `_bmad/`, `_bmad-output/brainstorming/`, `_bmad-output/planning-artifacts/epics.md`, `_bmad-output/planning-artifacts/prds/`, `docs/external/`, `hermes-docs/`, `_eval-outputs/`, `_eval_test.txt`) are out-of-scope for Story 2-1's commit and will not be staged.

## 3. Adversarial self-review

- **[MEDIUM] `mailbot_api/router/errors.py:sanitize_error` — order-sensitivity of regex substitutions.** `_BEARER_TOKEN_RE` and `_SK_KEY_RE` both replace fragments with placeholder tokens (`[REDACTED_BEARER]`, `[REDACTED_SK_KEY]`). The substitution placeholder text contains underscores, which is a valid path component — if a downstream check ever runs `_SECRET_FILE_RE` against a string already containing `[REDACTED_BEARER]`, no real match exists today (`[REDACTED_BEARER]` doesn't end in `.env`/`.key`/`.pem`) but a future contributor changing the placeholder format could cascade. Defensive but not actionable now.

- **[MEDIUM] `RouterCallRow.outcome: Literal[...]` constraint via Pydantic doesn't propagate to SQL CHECK.** The migration ships `outcome TEXT NOT NULL` without a CHECK constraint. A future code path bypassing the Pydantic model (direct `execute_write` with a raw tuple — boundary-forbidden but technically reachable via boundary-check bypass) could write `outcome='gibberish'`. Trade-off accepted per Dev Notes "Why we enumerate all model_chosen_reason values now" — same rationale applies to `outcome`. Flag for reviewer to confirm the layered enforcement (Pydantic + boundary check) is acceptable in lieu of SQL CHECK.

- **[LOW] `sanitize_error` traceback-block regex (`_TRACEBACK_BLOCK_RE`) uses non-greedy lookahead `(?=\n[A-Za-z_][\w.]*(?::\s|$))` — works for stdlib-style tracebacks, but a custom exception whose name contains `.` (a fully-qualified module path appearing on the leaf line) could match unexpectedly.** Mitigation: the leaf line regex allows `[A-Za-z_][\w.]*` so `mymodule.MyError: oops` would match. Tested implicitly via `test_sanitize_error_collapses_to_single_line` (which uses simple `RuntimeError`); a more exotic exception type isn't covered. Minor; reviewer may want a test for fully-qualified exception types.

- **[LOW] `_param_tuple` in `audit.py` is positional and order-sensitive.** Column-reorder in the migration silently corrupts data because there's no compile-time check. Mitigated by: (a) the docstring banner ("Adding a column means synchronizing all four sites in one commit"), (b) the integration test (write-then-readback by column-name in `SELECT` would catch reorder mismatch). Reviewer may suggest a defensive assert (`assert len(_param_tuple(row)) == ROUTER_CALLS_INSERT.count("?")` at module-import time) but that's gold-plating.

- **[LOW] `RouterResult.output: BaseModel | None` accepts ANY Pydantic model.** No runtime check that the `output` matches the expected `prompt.OUTPUT_SCHEMA` for the task. Story 2-4 (`ask_router`) is where that schema validation lives; Story 2-1 just defines the carrier shape. Reviewer should confirm this is intentional and not a missed gate.

- **[INFO] No explicit test for the unused `Field` import in `errors.py`.** The `Field` symbol is imported and used in `model_attempted: list[str] = Field(default_factory=list)`. Ruff `F401` would catch a truly unused import; mypy `--strict` is clean. No bug, just noting that `Field` is critical for the `default_factory` because plain `= []` is a Pydantic v2 anti-pattern (mutable default).

## 4. Self-caught issues remediated this audit

- **[MEDIUM] order-sensitivity of regex substitutions:** **ACCEPT WITH RATIONALE** — current behavior is correct; the concern is future-contributor cascading, not a present bug.
- **[MEDIUM] `outcome` Literal not in SQL CHECK:** **ESCALATE TO REVIEWER** — design choice consistent with `model_chosen_reason`; reviewer should confirm.
- **[LOW] Traceback regex may not handle fully-qualified exception names:** **ESCALATE TO REVIEWER** — add a test if reviewer agrees worth covering.
- **[LOW] `_param_tuple` is positional / order-sensitive:** **ACCEPT WITH RATIONALE** — defensive assert would be gold-plating; the docstring + the integration test catch any reorder.
- **[LOW] `RouterResult.output` accepts any BaseModel:** **ACCEPT WITH RATIONALE** — this is intentional Story-2-1 scope (carrier-only); Story 2-4 wires the schema check.
- **[INFO] `Field` import is mutable-default guard:** **ACCEPT** — no action needed.

## 5. Posture Audit

### 5.1 Lockfile hygiene

`requirements.txt` was not modified by Story 2-1 (no new third-party dependencies — only stdlib `re`, `enum`, `datetime`, `typing.Literal`, plus existing `pydantic` and the internal `mailbot_api.db.*` / `mailbot_api.observability.logging` modules).

```
git diff requirements.txt   # → no output (no changes)
```

Verified: no `pip install` was needed during dev; the .venv already had `pydantic`, `pytest`, `ruff`, `mypy` from Story 1-1. **PASS** — no lockfile drift.

### 5.2 Cross-doc / cross-architecture references

The story spec referenced `005_router_calls.sql` (epic-2 plan), but actual ship is `006_router_calls.sql` (numbering variance). The story file documents this in Dev Notes and the migration's own banner comment. **Action item for downstream stories 2-7, 2-8, 2-9 (and possibly 2-10 if it ships a migration):** their migration prefixes will need to shift accordingly. This is flagged in `epic-run-flags.md` at end-of-epic (per orchestrator Phase 3.3).

Architecture document (`_bmad-output/planning-artifacts/architecture.md`) line ~831 mentions `001_init.sql # emails, threads, senders, router_calls, response_cache, derivations, sync_state` — this was historical (Story 1-3 reduced 001 scope). No architecture patch needed because the file already documents (line ~836) `006_caller_origin.sql` placeholder which is itself out-of-date but architecture is read as a snapshot, not the authoritative numbering source.

```
grep -rn "005_router_calls\|005_router\|005 router" mailbot_api/ tests/ scripts/   # → no matches
```

**PASS — no dangling cross-doc references to the wrong prefix.**

### 5.3 Lifecycle-string check

N/A — Story 2-1 does not modify any lifecycle string surface (no `event=` change, no FastAPI lifespan handler change, no Docker entrypoint change). The `record_router_call` writer will *be called from* `ask_router` 's `finally` block in Story 2-4 (lifecycle event `router.call.{ok,failed,...}` per architecture line ~660), but Story 2-1 ships only the carrier function. **N/A — no lifecycle strings touched.**

### 5.4 Multi-consumer check

The migration `006_router_calls.sql` is consumed by exactly one production path: `db.migrations_runner.apply_pending_migrations(...)` invoked at FastAPI lifespan startup. Integration tests `test_db_connection.py::test_lifespan_runs_migrations_on_startup_via_testclient` confirm it runs. The `ROUTER_CALLS_INSERT` constant is consumed by `observability/audit.py::record_router_call` (the only writer). The `RouterCallRow` model is consumed by tests today (Story 2-1) and by `ask_router` later (Story 2-4).

```
grep -rn "RouterCallRow\|record_router_call\|ROUTER_CALLS_INSERT" mailbot_api/ tests/ 2>&1 | head -10
```

**PASS — single-writer monopoly verified.**

### 5.5 Screenshot-perception (SSR)

N/A — MailBot has no graphical frontend per PORTING.md. Story 2-1 is backend-only data shapes + audit table + boundary enforcement.

### 5.6 Upstream-contract / API-evolution

`ErrorCode` enum is the upstream contract: every downstream consumer (verbs, prompts, observability dashboards, eval rubric, Hermes adapter) keys on these stable string values. Adding a member is backward-compatible; renaming or removing is a breaking change. Module docstring documents this contract explicitly.

`RouterError` and `RouterResult` are the upstream Pydantic contracts: every Router call returns one of these. Adding optional fields is non-breaking; making `ok` non-bool or changing the `(ok, error)` invariant is breaking. The `@model_validator` enforces the invariant runtime-side; tests `test_router_result_ok_true_with_error_raises` / `test_router_result_ok_false_without_error_raises` are the regression suite.

`ROUTER_CALLS_INSERT` column order is the upstream SQL contract: any addition requires synchronized edits to (migration, INSERT, `_param_tuple`, `RouterCallRow`). Docstring documents this.

**PASS — upstream contracts are documented and tested.**

### 5.7 Module-mutable-state check

Per PORTING.md Python overlay: scan for module-level `dict`/`list`/`set`, `lru_cache` on unhashable args, global counters.

- `mailbot_api/router/errors.py`:
  - `_TRACEBACK_BLOCK_RE` is a compiled regex at module-load time. **Immutable; safe.**
  - No module-level mutable containers.
- `mailbot_api/observability/audit.py`:
  - `_REASON_LITERALS = frozenset({...})` — explicit `frozenset`. **Immutable; safe.**
  - `_ESCALATED_FROM_RE` is a compiled regex. **Immutable; safe.**
  - No module-level mutable containers.

```
grep -nE "^[a-z_]+ *= *(\[|\{|dict\(|list\(|set\()" mailbot_api/router/errors.py mailbot_api/observability/audit.py   # → no matches
```

**PASS — no module-mutable-state risk.** None of the high-risk files PORTING.md flagged (`router/router.py`, `budget.py`, `cache_warmer.py`, `config.py`) are touched in this story.

### 5.8 Dev-fixture seed-vs-production-shape parity

N/A — no seed / fixture data introduced. The `RouterCallRow` test fixtures in `test_audit.py` are constructed inline per-test; they exercise the *same* path production code will use (Pydantic model → param tuple → execute_write). No diverging fixture shape exists. **N/A.**

### 5.9 Grep-verify cited figures

The story's Completion Notes cite "149 passed, 47 new tests" — verified directly:

```
.venv/Scripts/python.exe -m pytest -q 2>&1 | tail -3
# → "149 passed, 1 warning in 5.15s"
```

102 was the prior baseline (story 1-10 final state per sprint-status.yaml). 149 - 102 = 47. **PASS — figure cite matches reality.**

The story cites "23 source files" mypy-checked — verified:

```
.venv/Scripts/python.exe -m mypy --strict mailbot_api/ 2>&1
# → "Success: no issues found in 23 source files"
```

**PASS.**

### 5.10 Producer-boundary contract

The `record_router_call` writer is the producer; the `router_calls` SQLite table is the consumer. Defense-in-depth at the boundary:

- **Application layer (Pydantic):** `RouterCallRow` enforces `model_chosen_reason ∈ closed-set | escalated_from_<X>` and `outcome ∈ Literal[...]` via validators. Construction with bogus values raises `ValidationError`.
- **SQL layer:** plain `TEXT NOT NULL` on the constrained columns — no CHECK constraint. Trade-off documented; reviewer to confirm.
- **Type coercion at the boundary:** Python `str`/`int`/`float`/`None` map cleanly to SQLite's TEXT/INTEGER/REAL/NULL. The Pydantic field types (`int`, `float`, `str`, `str | None`) match. No `Decimal` involvement (no money values held with full precision — `cost_usd_estimated REAL` is acceptable per architecture choice).
- **No `SELECT *`:** the INSERT enumerates all 16 inserted columns explicitly (`id` is AUTOINCREMENT); the test SELECT also enumerates explicitly.

**PASS — producer-boundary contract is layered (Pydantic + explicit column list).**

### 5.11 Git-evidence consistency

```
git status --porcelain | wc -l   # → 20
```

11 of those are story-scoped (story file + pre-review + 7 new + 4 modified per File List). 9 are pre-existing untracked context (`.claude/skills/`, `_bmad/`, `_bmad-output/brainstorming/`, `_bmad-output/planning-artifacts/epics.md`, `_bmad-output/planning-artifacts/prds/`, `_eval-outputs/`, `_eval_test.txt`, `docs/external/`, `hermes-docs/`). These pre-existing entries are not Story 2-1's responsibility and will be excluded from the Step 2.6 staging.

Test-to-code ratio for Story 2-1:

- Production code added: `errors.py` (~150 lines), `audit.py` (~120 lines), `006_router_calls.sql` (~50 lines), edits to `queries.py` (~25 added lines), edits to `check_boundaries.py` (~35 added lines). Total: ~380 net new lines.
- Test code added: `test_errors.py` (~190 lines), `test_audit.py` (~190 lines), fixture (~15 lines), 1 parametric entry in `test_lint_boundaries.py` (~10 lines). Total: ~405 net new test lines.
- Ratio: **~1.07 test lines per production line.** Healthy.

The migration `.sql` and `__init__.py` package marker are excluded from the test-ratio numerator per PORTING.md guidance ("`*.sql` under `mailbot_api/db/migrations/` in the docs bucket so pure-schema stories don't trip the gate").

**PASS.**

### Posture Audit summary

| Check | Status |
|---|---|
| 5.1 lockfile hygiene | PASS |
| 5.2 cross-doc | PASS (variance documented + flagged for next stories) |
| 5.3 lifecycle-string | N/A |
| 5.4 multi-consumer | PASS |
| 5.5 screenshot-perception | N/A (no graphical frontend) |
| 5.6 upstream-contract | PASS |
| 5.7 module-mutable-state | PASS |
| 5.8 seed-vs-production parity | N/A (no fixtures) |
| 5.9 grep-verify cited figures | PASS |
| 5.10 producer-boundary contract | PASS |
| 5.11 git-evidence consistency | PASS |
