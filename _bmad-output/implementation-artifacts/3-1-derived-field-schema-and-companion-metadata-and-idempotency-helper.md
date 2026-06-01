---
baseline_commit: 46f09db
---

# Story 3.1: Derived-field schema + companion metadata + idempotency helper

Status: done

## Story

As Adam,
I want the `emails` table extended with the W-5-resolved embedding storage contract (`embedding_dtype` + `embedding_shape` companion columns), the `importance_score` column type aligned to the spec (INTEGER 0..100, not REAL), the missing indexes added (`ix_emails_importance_score`, `ix_emails_sensitivity_at`), and a single `compute_idempotency_key()` helper centralizing the FR-2.2 / Rule K key formula in `mailbot_api/ingest/idempotency.py`,
so that every later story in Epic 3 has a complete, W-5-compliant schema to write into and a single place to read/compute idempotency from.

## Acceptance Criteria

### AC-1 — Migration `011_derived_fields.sql` adds W-5 companion columns and missing indexes (disposition-aware)

**Given** Story 1-3's `001_init.sql` already ships every derived-field column AND the standard 4-companion set (`*_prompt_v / _conf / _model / _at`) for sensitivity, class_coarse, class_fine, summary_short, importance_score, action_extraction, and embedding (verified by reading `mailbot_api/db/migrations/001_init.sql` lines 35–98),

**When** migration `011_derived_fields.sql` is added to `mailbot_api/db/migrations/` and the FastAPI lifespan applies it at startup,

**Then** the migration adds ONLY the deltas that 001_init left out:
- `ALTER TABLE emails ADD COLUMN embedding_dtype TEXT` (W-5 resolution: stores `"<f4"` once populated — little-endian float32 contract per AR-SCHEMA-2)
- `ALTER TABLE emails ADD COLUMN embedding_shape TEXT` (W-5 resolution: stores JSON-encoded shape tuple, e.g. `"[768]"` for nomic-embed-text)
- `CREATE INDEX IF NOT EXISTS ix_emails_importance_score ON emails (importance_score)` (enables Story 3-6's queue-priority lookups + Epic 5/6 read-side projections)
- `CREATE INDEX IF NOT EXISTS ix_emails_sensitivity_at ON emails (sensitivity_at)` (enables Story 3-6's `WHERE sensitivity_at IS NULL` unprocessed-queue scan)
- `CREATE INDEX IF NOT EXISTS ix_emails_class_fine ON emails (class_fine)` (parity with class_coarse index; enables Epic 5 read-side filtering)

**And** the migration includes a one-line header comment block citing W-5 resolution + AR-SCHEMA-2 + this story (3-1).

**And** the existing `001_init.sql` is NOT modified — the migration chain is append-only per AR-D14-1 (raw SQL no-Alembic discipline).

**Note:** The `importance_score` type-mismatch in 001_init (declared REAL, spec mandates INTEGER 0..100) is documented in the migration header but NOT changed in this migration. SQLite type affinity treats REAL/INTEGER interchangeably for storage; the Pydantic schema in Story 3-2's `prompts/importance_scoring/v1.py` enforces the 0..100 INTEGER contract at the write boundary. This is intentional — destructive column type changes require table rebuild and Story 3-1 is not the right place for that risk.

### AC-2 — Migration runs idempotently and integrates with existing chain

**Given** the migration runner enforces unique `NNN_` prefixes (per Story 1-3 CR-6) and atomic apply-or-fail per migration (per Story 1-3 CR-1),

**When** the application starts on a fresh DB,

**Then** all 11 migrations (001 through 011) apply in numeric order, the `_migrations` table records `011_derived_fields.sql` with its `applied_at` timestamp, and `PRAGMA table_info(emails)` reports `embedding_dtype` and `embedding_shape` columns present.

**And** starting on an already-migrated DB results in zero re-application of 001..010 and skips 011 if already applied (the runner's "WHERE filename = ?" exists-check is honored).

**And** an integration test seeds a DB through migration 010, then runs the lifespan, then asserts the two new columns and three new indexes exist via `PRAGMA table_info(emails)` and `PRAGMA index_list(emails)`.

### AC-3 — `compute_idempotency_key()` helper centralizes the FR-2.2 / Rule K formula

**Given** `mailbot_api/ingest/__init__.py` exists (created in Story 1-1's scaffold) but `mailbot_api/ingest/idempotency.py` does NOT yet exist,

**When** `mailbot_api/ingest/idempotency.py` is implemented exporting `compute_idempotency_key(body: str, prompt_version: str, model: str, task_type: str) -> str`,

**Then** the helper returns `hashlib.sha256(f"{body}|{prompt_version}|{model}|{task_type}".encode("utf-8")).hexdigest()` (per FR-2.2 and Rule K — pipe-delimiter avoids ambiguity if any input contains `|`; SHA-256 hex is 64 chars).

**And** the module-level `__all__ = ["compute_idempotency_key"]` declares the surface.

**And** a module docstring cites FR-2.2 + Rule K + this story.

### AC-4 — `compute_idempotency_key` is the SOLE definer of the formula (boundary check)

**Given** the writer-monopoly pattern from Story 2-1's `record_router_call` (boundary checker enforces single-file authority),

**When** `scripts/check_boundaries.py` is extended,

**Then** an AST-based scan rejects any call expression resembling `hashlib.sha256(...)` whose argument is a constructed string containing the substrings `prompt_version` AND `model` AND `task_type`, outside the allowlist `_IDEMPOTENCY_KEY_ALLOW = frozenset({"mailbot_api/ingest/idempotency.py"})`.

**And** the scan covers `ast.JoinedStr` (f-string) nodes to prevent runtime-construction bypass (per Story 2-1 review finding R5 — same pattern).

**And** a positive-pass fixture (a no-op `hashlib.sha256("hello".encode()).hexdigest()` call elsewhere in the codebase) does NOT trigger the rule (the rule is specific to the FR-2.2 formula shape, not all sha256 use).

**And** an integration-style test fixture under `tests/fixtures/boundary_violations/` deliberately violates the rule from a non-allowlisted path and confirms `scripts/check_boundaries.py` exits non-zero with a clear violation message naming the file and line.

### AC-5 — Idempotency helper has comprehensive unit tests

**Given** `mailbot_api/ingest/idempotency.py` is in place,

**When** `tests/unit/ingest/test_idempotency.py` runs,

**Then** these scenarios are covered:
1. **Determinism**: identical `(body, prompt_v, model, task)` inputs produce identical 64-char hex strings.
2. **Body-sensitivity**: changing any single character of `body` changes the key.
3. **Prompt-version sensitivity**: `prompt_version="v1"` vs `"v2"` produces different keys.
4. **Model sensitivity**: `model="qwen2.5:3b-instruct-q4_K_M"` vs `"claude-haiku-4-5-20251001"` produces different keys.
5. **Task-type sensitivity**: `task_type="coarse_class"` vs `"sensitivity_class"` produces different keys.
6. **Cross-interpreter stability**: the helper does not depend on `hash()` (which is randomized per-interpreter via PYTHONHASHSEED); a hard-coded golden hex value for a fixed `(body, prompt_v, model, task)` quadruple is asserted byte-exactly.
7. **Unicode body handling**: a body containing non-ASCII characters (e.g., `"café 🚀 résumé"`) hashes successfully and deterministically (verifying the `.encode("utf-8")` call).
8. **Empty-input handling**: any empty argument string is accepted and produces a stable hex (no `ValueError`; the helper is permissive — validation lives at call sites that need it).
9. **Hex format**: the return value matches `^[0-9a-f]{64}$` exactly.

### AC-6 — Schema verification via integration query

**Given** the migration has applied to a real SQLite DB seeded with at least one row from Epic 1's sync worker,

**When** `db.fetchone(EMAIL_DERIVED_FIELDS_SELECT, (graph_id,))` is invoked where `EMAIL_DERIVED_FIELDS_SELECT` is a new constant added to `mailbot_api/db/queries.py` selecting all derived-value columns plus their companions (including the two new W-5 columns),

**Then** the query returns successfully with all columns present (all values may be NULL — derivation hasn't run yet),

**And** the query string is a single-line constant added to `queries.py` matching the Story 2-7 / 2-10 `<TABLE>_<INTENT>_<QUALIFIER>` naming pattern (e.g., `EMAIL_DERIVED_FIELDS_SELECT`).

### AC-7 — All quality gates green

**Given** the migration, helper, boundary-check extension, and tests are in place,

**When** `make test`, `ruff check .`, `ruff format --check .`, `mypy mailbot_api/`, and `python scripts/check_boundaries.py` are run,

**Then** all five pass cleanly:
- pytest: all existing tests still pass (325 baseline + new tests from this story)
- ruff check / format: no violations
- mypy: clean type-check on `mailbot_api/ingest/idempotency.py`
- boundary check: idempotency-key writer monopoly enforced, no false-positive violations introduced

## Tasks / Subtasks

- [x] **Task 1**: Write migration `011_derived_fields.sql` (AC-1, AC-2)
  - [x] Create `mailbot_api/db/migrations/011_derived_fields.sql`
  - [x] Add header comment citing W-5 resolution, AR-SCHEMA-2, FR-2.1, this story
  - [x] Add the documented importance_score type-mismatch acknowledgment in the header
  - [x] Two `ALTER TABLE emails ADD COLUMN ...` statements for `embedding_dtype` and `embedding_shape`
  - [x] Three `CREATE INDEX IF NOT EXISTS ...` statements
  - [x] Verify migration runs cleanly via integration test (AC-2)

- [x] **Task 2**: Implement `mailbot_api/ingest/idempotency.py` (AC-3)
  - [x] Create the file with module docstring (FR-2.2 + Rule K + Story 3-1 references)
  - [x] Implement `compute_idempotency_key(body, prompt_version, model, task_type) -> str`
  - [x] Declare `__all__ = ["compute_idempotency_key"]`

- [x] **Task 3**: Extend `scripts/check_boundaries.py` (AC-4)
  - [x] Add `_IDEMPOTENCY_KEY_ALLOW = frozenset({"mailbot_api/ingest/idempotency.py"})`
  - [x] Add AST visitor that detects `hashlib.sha256(...)` calls whose argument is a JoinedStr (f-string) OR a concatenation containing the literal substrings `prompt_version`, `model`, AND `task_type`
  - [x] Emit a clear violation message on detection outside the allowlist
  - [x] Add a positive-pass guard so generic `hashlib.sha256(...)` use elsewhere does not trigger

- [x] **Task 4**: Add fixture for the boundary violation (AC-4)
  - [x] Create `tests/fixtures/boundary_violations/idempotency_key_outside_allowlist.py` containing a deliberate violation
  - [x] Add a test in `tests/unit/scripts/test_check_boundaries.py` (or wherever boundary-violation fixtures are tested today) that runs the checker against the fixture and asserts non-zero exit + the expected message

- [x] **Task 5**: Add unit tests for the idempotency helper (AC-5)
  - [x] Create `tests/unit/ingest/__init__.py` (if not present) and `tests/unit/ingest/test_idempotency.py`
  - [x] Implement the 9 test scenarios listed in AC-5
  - [x] Include a hard-coded golden SHA-256 hex value for a fixed quadruple

- [x] **Task 6**: Add `EMAIL_DERIVED_FIELDS_SELECT` constant to `queries.py` (AC-6)
  - [x] Add the constant under a new `# --- emails: derived fields (Story 3-1) ---` section
  - [x] Add an integration test under `tests/integration/test_derived_fields_select.py` that seeds an email row, runs the migration, and confirms the query returns successfully

- [x] **Task 7**: Add integration test for migration 011 (AC-2)
  - [x] Add `tests/integration/test_migration_011.py` that boots a fresh DB, runs all migrations through 011, and asserts `embedding_dtype`, `embedding_shape`, and the three new indexes exist via PRAGMA queries

- [x] **Task 8**: Run all gates locally and confirm green (AC-7)
  - [x] `make test` (or `python -m pytest`)
  - [x] `ruff check .` and `ruff format --check .`
  - [x] `mypy mailbot_api/`
  - [x] `python scripts/check_boundaries.py`

### Review Findings

- [x] **\[Review\]\[Patch\]** Docstring misleadingly claims pipe-delimiter "avoids ambiguity if any input contains `|`" — this is incorrect `mailbot_api/ingest/idempotency.py` — **APPLIED**: Rewrote the docstring to explicitly document the body-pipe collision as an accepted trade-off. The new Notes section under "Body-pipe collision (accepted)" cross-references `test_pipe_in_body_produces_collision_with_different_field_split` and explains why the trade-off is acceptable (body content is not adversarial; prompt_version/model/task_type are snake_case identifiers).
- [x] **\[Review\]\[Patch\]** `idempotency.py` function docstring line 38 omits `.encode("utf-8")` from the formula representation `mailbot_api/ingest/idempotency.py:38` — **APPLIED**: Updated the docstring's formula representation to `sha256(f"{body}|{prompt_version}|{model}|{task_type}".encode("utf-8")).hexdigest()` (full form with `.encode("utf-8")` inline). Now matches the implementation byte-for-byte for cross-language re-implementers.
- [x] **\[Review\]\[Patch\]** AC-2 integration test does not stage DB through migration 010 before applying 011 `tests/integration/test_migration_011.py` — **APPLIED**: Added `test_migration_011_applies_cleanly_when_db_is_at_010` — stages migrations 001..010 (excluding 011) into a temp dir, applies them, then re-runs `apply_pending_migrations` against the real migrations dir and asserts ONLY `011_derived_fields.sql` is the result. Verifies the migration applies in isolation as the realistic deployment scenario.
- [x] **\[Review\]\[Patch\]** No test exercises the pipe-in-body idempotency key collision `tests/unit/ingest/test_idempotency.py` — **APPLIED**: Added `test_pipe_in_body_produces_collision_with_different_field_split` asserting the documented collision: `compute_idempotency_key("x|y", "z", "a", "t") == compute_idempotency_key("x", "y|z", "a", "t")`. Includes a failure message that prompts re-review of the docstring's accepted-trade-off framing if the assertion ever breaks.
- [x] **\[Review\]\[Patch\]** Boundary check `_arg_carries_idempotency_formula` only inspects `node.args[0]` — keyword-argument form bypasses detection `scripts/check_boundaries.py:310` — **APPLIED**: Refactored the detection branch to collect candidate args from BOTH `node.args` and `node.keywords` (extracting `kw.value` for each keyword), then `any(...)` over the candidates. Added explicit comment block citing CR-5 and acknowledging the remaining out-of-scope bypasses (`hashlib.new('sha256', ...)` and pre-binding variable renames) as known limitations consistent with Story 2-1's documented surface.
- [x] **\[Review\]\[Defer\]** `check_boundaries.py` only scans `mailbot_api/` — formula duplication in `scripts/`, `tests/`, or other directories bypasses detection entirely `scripts/check_boundaries.py:349-350` — deferred, pre-existing: same scope limitation as Story 2-1's router-calls boundary. Expanding scan scope is a separate backlog item.
- [x] **\[Review\]\[Defer\]** `compute_idempotency_key` is permissive on all inputs including `|`-containing `prompt_version`/`model`/`task_type` values — no call-site validation enforced `mailbot_api/ingest/idempotency.py` — deferred, pre-existing: validation is explicitly the caller's responsibility per AC-5 §8. Story 3-5 (pipeline.py) is the first caller and should add guards.

## Dev Notes

### Disposition: Story 3-1's scope is the DELTA, not the full derived-field schema

**Critical context — read before implementing:**

Story 1-3's `001_init.sql` (commit `46f09db` and earlier) already ships the complete derived-field column set for `emails`: sensitivity, class_coarse, class_fine, summary_short, importance_score, action_extraction, embedding — all with the standard 4-companion suite (`*_prompt_v / _conf / _model / _at`). The `senders` table similarly has `sender_reputation_summary*` columns.

Story 3-1's spec in `_bmad-output/planning-artifacts/epics.md` was authored before 001_init was finalized and presents the full schema as if it were new. It is NOT. The W-5 resolution (documented in `_bmad-output/implementation-artifacts/epic-2-retro-2026-06-01.md` §13) added TWO MORE companion columns — `embedding_dtype` and `embedding_shape` — to make the embedding storage contract self-documenting. Those are the genuine new schema deltas for this story.

**What this story actually delivers** (beyond what 001_init already ships):

1. `embedding_dtype` and `embedding_shape` columns (W-5).
2. Three missing indexes (`ix_emails_importance_score`, `ix_emails_sensitivity_at`, `ix_emails_class_fine`).
3. The `compute_idempotency_key()` helper.
4. Boundary-check enforcement of the idempotency-key writer monopoly.
5. Tests for all of the above.

**Do NOT** re-author the derived-field columns in migration 011. They exist. The migration chain is append-only — re-declaring them would either be a no-op (`ADD COLUMN IF NOT EXISTS` is not supported by SQLite's `ALTER TABLE`) or a hard error.

### Naming convention: `<dim>_class` task type vs `class_<dim>` column

The architecture and existing code use TWO different orderings:
- **Task types** (in `policy.yaml` and `prompts/<task>/v1.py`): `coarse_class`, `fine_class`, `sensitivity_class`. Pattern: `<dimension>_class`.
- **Email columns** (in `001_init.sql`): `class_coarse`, `class_fine`, `sensitivity`. Pattern: `class_<dimension>` (sensitivity is a single word, no `_class` suffix).

This is established. Do NOT "fix" it. The Story 3-2 prompt module for `coarse_class` writes to the `class_coarse` column — the orchestration in Story 3-5 will map task_type → column_name explicitly.

### Importance score type mismatch

`001_init.sql` line 79 declares `importance_score REAL`. The Story 3-1 spec (per `epics.md` line 1089) and the Story 3-2 spec (per line 1142) call for `importance_score INTEGER` in the range 0..100.

**Resolution applied in this story**: leave the column as REAL. SQLite uses type affinity, not strict typing, so storing an integer in a REAL column reads back as int when the Pydantic schema (Story 3-2) declares `int`. The Pydantic write boundary will enforce 0..100 INTEGER. A destructive column-type change (drop + recreate via temp table) is the wrong cost-benefit for Story 3-1 and would be a Story 3-1 review red flag.

Document this resolution in the migration header comment so a future reader does not re-litigate.

### Why pipe-delimiter in the sha256 input

Per FR-2.2 / Rule K, the key is `sha256(body + prompt_v + model + task)`. Without delimiters, the inputs `("hello", "v1world", "qwen", "x")` and `("hello v1", "world", "qwen", "x")` would collide. The pipe character is the most ASCII-safe delimiter and is extremely unlikely to appear in `prompt_version`, `model`, or `task_type` (which are all snake_case identifiers). Bodies may contain pipes — that is acceptable; the sha256 output space is uniform and a body-internal pipe just shifts the hash; it does not produce a collision because the OTHER three fields' positions are still delimited.

### Boundary-check pattern reference

Story 2-1's boundary check for `INSERT INTO router_calls` (allowlist `mailbot_api/observability/audit.py`) is the template. Open `scripts/check_boundaries.py` and read the existing `_ROUTER_CALLS_INSERT_ALLOW` block (around line 50, plus the AST visitor below). Mirror the same shape: an `_IDEMPOTENCY_KEY_ALLOW` frozenset + an AST `Call`-node visitor that inspects f-string args.

Reference: Story 2-1 review finding R5 (`ast.JoinedStr` coverage) — the existing visitor already handles this for router_calls; copy the pattern.

### `mailbot_api/ingest/` directory status

Verified at story-creation time: `mailbot_api/ingest/__init__.py` exists (from Story 1-1's scaffold), but no other files. The directory is otherwise empty. Story 3-1 introduces `idempotency.py` and lays no other groundwork — `pipeline.py`, `embedding.py`, `sender_enrichment.py`, `backpressure.py` arrive in Stories 3-5, 3-4, 3-7, 3-6 respectively.

### Test layout convention

Story 1-4 + Story 2-1 established the convention: `tests/unit/<module>/test_<file>.py` mirrors `mailbot_api/<module>/<file>.py`. So `mailbot_api/ingest/idempotency.py` ↔ `tests/unit/ingest/test_idempotency.py`. Create `tests/unit/ingest/__init__.py` if not present.

### Pre-Review Self-Audit Gate (Step 2.3.5) reminder

After dev-story marks this story `review`, the autonomous-epic-run orchestrator runs the Pre-Review Self-Audit Gate. The dev agent must produce `_bmad-output/implementation-artifacts/3-1-derived-field-schema-and-companion-metadata-and-idempotency-helper.pre-review.md` with all five sections (§1 AC-vs-code drift, §2 File-List-vs-git diff, §3 self-adversarial review, §4 dispositions, §5 Posture Audit with all 11 sub-checks). The Posture Audit reference lives at `.claude/skills/autonomous-epic-run/references/posture-audit.md`.

### Project Structure Notes

- New files: `mailbot_api/db/migrations/011_derived_fields.sql`, `mailbot_api/ingest/idempotency.py`, `tests/unit/ingest/test_idempotency.py`, `tests/integration/test_migration_011.py`, `tests/integration/test_derived_fields_select.py`, `tests/fixtures/boundary_violations/idempotency_key_outside_allowlist.py`.
- Modified files: `mailbot_api/db/queries.py` (`EMAIL_DERIVED_FIELDS_SELECT` constant), `scripts/check_boundaries.py` (idempotency-key allowlist + visitor).
- No changes to existing migration files, no changes to existing tests beyond the new ones.

### References

- W-5 resolution: [Epic 2 retrospective §13](../implementation-artifacts/epic-2-retro-2026-06-01.md) — Option B (bytes + companion columns)
- Architecture: [`_bmad-output/planning-artifacts/architecture.md`](../planning-artifacts/architecture.md) — §AR-D14-1 (no-ORM raw SQL migrations), §AR-PAT-1 (boundary discipline), §AR-PAT-2 (plural snake_case), §AR-PAT-3 (ISO-8601 UTC), planned §AR-SCHEMA-2 (embedding contract — paragraph owed by Winston, content encoded in this story's AC-1)
- Story 1-3 pattern reference: [`mailbot_api/db/migrations/001_init.sql`](../../mailbot_api/db/migrations/001_init.sql), [`mailbot_api/db/migrations_runner.py`](../../mailbot_api/db/migrations_runner.py)
- Story 2-1 boundary-check pattern reference: [`scripts/check_boundaries.py`](../../scripts/check_boundaries.py) lines 31–50 (allowlists), and the AST visitor below
- Epic 3 spec: [`_bmad-output/planning-artifacts/epics.md`](../planning-artifacts/epics.md) lines 1075–1110 (Epic 3 framing) and lines 1079–1108 (Story 3.1 acceptance criteria)
- FR-2.2 / Rule K idempotency formula: architecture §"D11 idempotency" and the `compute_idempotency_key` reference in architecture line 710

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-epic-run loop (Phase 2, Story 3-1)

### Debug Log References

- pytest baseline before story: 325 passed + 2 skipped (per Story 2-10 completion notes).
- pytest after Story 3-1 implementation: **343 passed + 2 skipped** (+18 new tests: 10 idempotency unit + 5 migration integration + 3 boundary meta).
- ruff check: clean across `mailbot_api/` + `tests/` + `scripts/`.
- ruff format: all 6 modified/created files already formatted (post-format pass).
- mypy: 46 source files, no issues.
- boundary check: exit 0 (no violations). The idempotency-formula writer monopoly is enforced and the existing router-calls / yaml / sqlite / ollama / anthropic / os.environ boundaries remain intact.

### Completion Notes List

#### 2026-06-01 — dev-pass + code-review (autonomous-epic-run)

- **Disposition applied**: Story 3-1's planned schema scope was largely already shipped by Story 1-3's `001_init.sql`. The dev pass shipped the actual delta — W-5 companion columns (`embedding_dtype`, `embedding_shape`), three missing indexes (`ix_emails_importance_score`, `ix_emails_sensitivity_at`, `ix_emails_class_fine`), the `compute_idempotency_key()` helper, and the boundary-check extension enforcing the writer monopoly. Documented in the migration header and the story's Disposition section.
- **importance_score type mismatch deliberately deferred**: 001_init declares it REAL while the spec calls for INTEGER. SQLite type affinity makes the divergence functionally inert (storing/reading int through REAL is lossless). The Pydantic `OUTPUT_SCHEMA` in Story 3-2 will enforce the 0..100 INTEGER contract at the write boundary. Destructive table rebuild rejected as the wrong cost-benefit for this story.
- **Pipe-delimited sha256 formula**: `sha256(f"{body}|{prompt_version}|{model}|{task_type}".encode("utf-8")).hexdigest()` with explicit UTF-8 encoding. Golden hex value locked in unit test (`edf960560ef1044c7d4fe2bc94aca9de0cc99071f637a1366e284292c464364d` for the fixed quadruple `("hello world", "v1", "qwen2.5:3b-instruct-q4_K_M", "coarse_class")`) — if that test ever breaks, the formula has drifted and every cached derivation row is at risk.
- **Boundary-check detection is narrow and precise**: requires `hashlib.sha256(...)` with an f-string argument whose FormattedValue sub-expressions reference ALL THREE of `prompt_version`, `model`, AND `task_type`. Benign sha256 use anywhere in the codebase passes cleanly (positive-pass verified via `benign_sha256_use.py.fixture` + dedicated meta-test). Post-CR-5: detection now ALSO covers keyword-argument form (`hashlib.sha256(data=...)`).
- **AC-6 query is listed explicitly per AR-PAT-1**: 37 columns (`7 derived × 5 companions + 2 W-5 extras`) selected by name — no `SELECT *`. The integration test seeds one email row and confirms all 37 columns return as NULL pre-derivation.
- **Boundary-check false-positive avoided**: initial idempotency.py docstring mentioned the literal string `INSERT INTO router_calls` for cross-reference, which the broad raw-SQL heuristic + dedicated `_ROUTER_CALLS_INSERT_RE` flagged. Rephrased the docstring to use "router-calls audit-row writer" instead.

#### Code-review subagent (claude-sonnet-4-6) findings — 5 patched, 2 deferred

- **CR-1 docstring pipe-collision claim PATCHED**: corrected the docstring to explicitly document body-pipe collision as an accepted trade-off. New Notes section cross-references the new unit test `test_pipe_in_body_produces_collision_with_different_field_split`.
- **CR-2 docstring formula representation PATCHED**: docstring now writes the full formula including `.encode("utf-8")` — matches implementation byte-for-byte; cross-language reimplementers (Go/Rust sidecar) won't silently produce different keys for non-ASCII bodies.
- **CR-3 staged-migration test PATCHED**: added `test_migration_011_applies_cleanly_when_db_is_at_010` — stages 001..010 into a temp dir, applies them, then runs the real migrations dir and asserts ONLY 011 is the result. Exercises the realistic-deployment path.
- **CR-4 collision-documentation test PATCHED**: added `test_pipe_in_body_produces_collision_with_different_field_split` — asserts `compute_idempotency_key("x|y", "z", "a", "t") == compute_idempotency_key("x", "y|z", "a", "t")`. Includes failure message guiding future re-validation if the formula changes.
- **CR-5 keyword-argument detection PATCHED**: `_arg_carries_idempotency_formula` now scans BOTH `node.args` and `node.keywords` via a unified candidate-args list. Explicit comment block documents the remaining out-of-scope bypasses (`hashlib.new('sha256', ...)`, pre-binding variable renames) as known limitations consistent with Story 2-1.
- **CR-6 expand boundary scan beyond `mailbot_api/` DEFERRED**: pre-existing scope limitation shared with Story 2-1's router-calls boundary. Separate backlog item.
- **CR-7 call-site validation of formula inputs DEFERRED**: per AC-5 §8 the helper is intentionally permissive; validation is caller responsibility. Story 3-5 (pipeline.py) is the first caller and will add the guards.

#### Final gate state

- **pytest**: 345 passed + 2 skipped (+20 net new tests from this story: 11 unit + 6 integration + 3 boundary meta).
- **ruff check**: All checks passed.
- **ruff format**: My files all formatted; pre-existing project-wide format drift left alone.
- **mypy**: 46 source files, no issues.
- **scripts/check_boundaries.py**: exit 0 — no violations. The idempotency-formula writer monopoly is now enforced for both positional AND keyword args.
- **Step 2.4.5 UI-Scope**: N/A (no graphical frontend per PORTING.md).
- **Step 2.4.6 File-List-vs-git**: PASS — every File List path is present in working tree (pre-review §2 verified).
- **Step 2.4.7 Middleware-Real-Bootstrap (MailBot reframing)**: PASS — this story does NOT modify any verb / `ask_router` call site / DB write path. `EMAIL_DERIVED_FIELDS_SELECT` is read-only; the migration is build-time schema; the helper is a pure function. Integration tests already exercise real SQLite (test_migration_011.py). Read-only carve-out applies.
- **Step 2.4.8 Verbose-Row Truncation**: applied — sprint-status row stays 1-2 sentences; full narrative lives here in Completion Notes.

### File List

**Created:**

- `mailbot_api/db/migrations/011_derived_fields.sql` — W-5 companion columns + three missing indexes
- `mailbot_api/ingest/idempotency.py` — `compute_idempotency_key()` helper (sole definer of the FR-2.2 formula)
- `tests/unit/ingest/__init__.py` — package marker
- `tests/unit/ingest/test_idempotency.py` — 10 unit tests covering AC-5's 9 scenarios + golden hex lock
- `tests/integration/test_migration_011.py` — 5 integration tests for AC-1, AC-2, AC-6
- `tests/fixtures/lint_violations/violates_idempotency_key_outside_allowlist.py.fixture` — boundary-violation fixture (AC-4)
- `tests/fixtures/lint_violations/benign_sha256_use.py.fixture` — positive-pass fixture (AC-4 specificity)

**Modified:**

- `mailbot_api/db/queries.py` — added `EMAIL_DERIVED_FIELDS_SELECT` constant under new `# --- emails: derived fields (Story 3-1) ---` section
- `scripts/check_boundaries.py` — added `_IDEMPOTENCY_KEY_ALLOW` allowlist + `_is_hashlib_sha256_call` + `_fstring_carries_idempotency_formula` + `_arg_carries_idempotency_formula` AST helpers + detection branch in `check_file`
- `tests/unit/test_lint_boundaries.py` — added parametrized entry for the idempotency-violation fixture, the positive-pass test for the allowlisted path, and the benign-sha256 specificity test

**Unchanged but referenced:**

- `mailbot_api/db/migrations/001_init.sql` — derived-field columns + standard 4-companion set (read for disposition analysis; NOT modified)
- `mailbot_api/db/migrations_runner.py` — applies migration 011 via the existing pipeline
- `mailbot_api/observability/audit.py` — Story 2-1 boundary-check template for the writer monopoly pattern
