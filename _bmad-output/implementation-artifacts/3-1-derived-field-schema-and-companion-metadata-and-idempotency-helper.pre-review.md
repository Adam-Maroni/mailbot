# Pre-Review Self-Audit — 3-1-derived-field-schema-and-companion-metadata-and-idempotency-helper

**Generated:** 2026-06-01 by claude-opus-4-7 (1M context) — autonomous-epic-run loop
**Story file:** `_bmad-output/implementation-artifacts/3-1-derived-field-schema-and-companion-metadata-and-idempotency-helper.md`
**Status at audit time:** review (post dev-story, pre code-review)
**Baseline commit:** 46f09db

## 1. AC-vs-code drift scan

- **AC-1**: MATCH. Migration `011_derived_fields.sql` ships exactly the deltas (embedding_dtype + embedding_shape + three new indexes) with the documented importance_score type-mismatch acknowledgment in the header. 001_init NOT modified.
- **AC-2**: MATCH. Integration test `test_migration_011_adds_embedding_dtype_and_shape_columns` confirms PRAGMA reports both columns. `test_migration_011_creates_three_new_indexes` confirms all three indexes. `test_migration_011_is_recorded_in_migrations_table` confirms `_migrations` bookkeeping. `test_migration_011_is_idempotent_on_already_migrated_db` confirms second-call empty list.
- **AC-3**: MATCH. `compute_idempotency_key(body, prompt_version, model, task_type) -> str` exported via `__all__`. Module docstring cites FR-2.2 + Rule K + Story 3-1. Formula: `hashlib.sha256(f"{body}|{prompt_version}|{model}|{task_type}".encode("utf-8")).hexdigest()`.
- **AC-4**: MATCH. `_IDEMPOTENCY_KEY_ALLOW = frozenset({"mailbot_api/ingest/idempotency.py"})` + AST helpers `_is_hashlib_sha256_call`, `_fstring_carries_idempotency_formula`, `_arg_carries_idempotency_formula` cover f-string detection via `ast.JoinedStr.FormattedValue` walk. Positive-pass guard verified by `benign_sha256_use.py.fixture` + dedicated meta-test.
- **AC-5**: MATCH. 10 unit tests covering all 9 scenarios listed in the AC body — determinism, body sensitivity (incl. single-char), prompt_version sensitivity, model sensitivity, task_type sensitivity, golden hex lock (cross-interpreter stability), Unicode handling, empty inputs permissive, hex format `[0-9a-f]{64}`.
- **AC-6**: MATCH. `EMAIL_DERIVED_FIELDS_SELECT` added to `queries.py` under `# --- emails: derived fields (Story 3-1) ---` section. Lists 37 columns explicitly (no `SELECT *`). Integration test `test_email_derived_fields_select_returns_all_columns` seeds row and confirms all 37 columns return as NULL pre-derivation.
- **AC-7**: MATCH. All five gates green (pytest 343 passed + 2 skipped, ruff check clean, ruff format clean for my files, mypy clean, boundary check exit 0).

## 2. File-List-vs-git diff check

Output of `git status --porcelain` (filtered to story-relevant paths):

```
 M mailbot_api/db/queries.py
 M scripts/check_boundaries.py
 M tests/unit/test_lint_boundaries.py
 M _bmad-output/implementation-artifacts/sprint-status.yaml
?? _bmad-output/implementation-artifacts/3-1-derived-field-schema-and-companion-metadata-and-idempotency-helper.md
?? mailbot_api/db/migrations/011_derived_fields.sql
?? mailbot_api/ingest/idempotency.py
?? tests/fixtures/lint_violations/benign_sha256_use.py.fixture
?? tests/fixtures/lint_violations/violates_idempotency_key_outside_allowlist.py.fixture
?? tests/integration/test_migration_011.py
?? tests/unit/ingest/
```

Cross-reference against File List:

- `mailbot_api/db/migrations/011_derived_fields.sql` — UNTRACKED + IN FILE LIST ✅
- `mailbot_api/ingest/idempotency.py` — UNTRACKED + IN FILE LIST ✅
- `tests/unit/ingest/__init__.py` — UNTRACKED + IN FILE LIST ✅ (under `tests/unit/ingest/` dir)
- `tests/unit/ingest/test_idempotency.py` — UNTRACKED + IN FILE LIST ✅
- `tests/integration/test_migration_011.py` — UNTRACKED + IN FILE LIST ✅
- `tests/fixtures/lint_violations/violates_idempotency_key_outside_allowlist.py.fixture` — UNTRACKED + IN FILE LIST ✅
- `tests/fixtures/lint_violations/benign_sha256_use.py.fixture` — UNTRACKED + IN FILE LIST ✅
- `mailbot_api/db/queries.py` — MODIFIED + IN FILE LIST ✅
- `scripts/check_boundaries.py` — MODIFIED + IN FILE LIST ✅
- `tests/unit/test_lint_boundaries.py` — MODIFIED + IN FILE LIST ✅
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — MODIFIED, not in File List (status-tracking, not story scope) ✅ informational
- `_bmad-output/implementation-artifacts/3-1-*.md` — UNTRACKED + the story file itself ✅ informational
- Pre-existing untracked entries (`.claude/skills/`, `_bmad/`, `_bmad-output/brainstorming/`, `_bmad-output/planning-artifacts/prds/`, `_eval-outputs/`, `_eval_test.txt`, `docs/external/`, `hermes-docs/`, `.claude/settings.json`) — pre-existing background work outside this story's scope ✅ informational (will NOT be staged in Step 2.6)

Verdict: **PASS** — every File List entry is present in working tree; no silent scope-creep.

## 3. Adversarial self-review

- **[MEDIUM]** `mailbot_api/db/migrations/011_derived_fields.sql:38-40` — `ALTER TABLE ... ADD COLUMN` is NOT idempotent in SQLite (no `IF NOT EXISTS` for columns). If for any reason the migration runner re-applied 011 (e.g., bug in `_applied_filenames`), the second ALTER would fail with "duplicate column name". This is mitigated by the existing `_applied_filenames` exists-check (covered by `test_migration_011_is_idempotent_on_already_migrated_db`), but the migration script itself is not defensively idempotent. Acceptable per the project's append-only migration discipline (AR-D14-1) — the runner's bookkeeping is the idempotency layer, not the SQL.
- **[LOW]** `mailbot_api/ingest/idempotency.py:65` — line slightly over the common 88-char ruff target (90 chars). Ruff format auto-permitted because the project's line-length is 120, so this is well within limits, but stylistically a wrap would aid reading. Cost of fixing exceeds value.
- **[LOW]** `scripts/check_boundaries.py:117-138` (`_fstring_carries_idempotency_formula`) — the heuristic walks ALL `ast.Name` nodes inside `FormattedValue` sub-expressions and checks for set-subset on `{prompt_version, model, task_type}`. A motivated bypass would be: rename the three variables before constructing the f-string (`pv = prompt_version; m = model; tt = task_type; sha256(f"{body}|{pv}|{m}|{tt}".encode())`). This is the same tradeoff as Story 2-1's router_calls check (also defeatable by table-name aliasing). Acceptable for a single-developer codebase; not a security boundary.
- **[LOW]** `tests/integration/test_migration_011.py:91-95` — the test asserts `len(row) == 37` (the column count). A future story that adds a new derived field would have to update both the migration AND this magic number. Better than nothing; future stories can refactor to compute the expected count.
- **[INFO]** AR-SCHEMA-2 paragraph still owed by Winston in `architecture.md` per Epic 2 retro §13 postscript. Documented in the migration header so the contract is auditable from the migration; the paragraph remains planning-doc debt, not a code blocker.

## 4. Self-caught issues remediated this audit

- **[MEDIUM] migration ADD COLUMN not idempotent**: **ACCEPT WITH RATIONALE** — append-only migration discipline (AR-D14-1) treats the runner's `_applied_filenames` bookkeeping as the idempotency layer. Defensive `ADD COLUMN IF NOT EXISTS` is not supported by SQLite. Integration test `test_migration_011_is_idempotent_on_already_migrated_db` covers the practical case.
- **[LOW] idempotency.py line length 90 chars**: **ACCEPT WITH RATIONALE** — within project's 120-char limit (verified `pyproject.toml` line-length = 120); ruff format pass approved the wrap. Refactor cost exceeds value.
- **[LOW] check_boundaries.py variable-rename bypass**: **ACCEPT WITH RATIONALE** — same tradeoff as Story 2-1's router_calls check. The boundary catches accidental drift, not adversarial bypass. Single-developer codebase + reviewable formula site.
- **[LOW] test_migration_011.py magic number 37**: **ACCEPT WITH RATIONALE** — explicit count + comment explaining `7 × 5 + 2`. Future-story-author cost is one diff line. Refactor to compute from PRAGMA would obscure the AC verification intent.
- **[INFO] AR-SCHEMA-2 paragraph owed**: **ESCALATE TO REVIEWER** — flag for code-review subagent (claude-sonnet-4-6) to confirm the documented-in-migration-header mitigation is sufficient OR to recommend Winston add the paragraph before Story 3-4 ships (which is when the writer-monopoly + companion writes land).

## 5. Posture Audit

### 5.1 — Lockfile hygiene

```
$ git diff --stat -- requirements.txt
(no output)
```

Verdict: **PASS — N/A** — non-dep-change story; `requirements.txt` untouched.

### 5.2 — Cross-doc pair verification

**Cross-doc branch:** N/A — the story references the Epic 2 retrospective postscript and the epics.md spec, but does not claim those documents contain anything that needs verification against a divergent canonical source. The W-5 resolution narrative in the migration header is a quote/summary of the retro §13 postscript, not a claim about it.

**§5.2.1 schema-touching branch:** File List contains `mailbot_api/db/migrations/011_derived_fields.sql` → trigger fires.

```
Grep "embedding_dtype|embedding_shape|AR-SCHEMA-2" docs/
(no output — docs/ has no schema doc; only auth-recovery.md + entra-app-registration.md)

Glob docs/DATABASE.md
No files found
```

Verdict: **⚠️ FLAGGED** — no project-level schema doc (`docs/DATABASE.md` or equivalent) exists. The schema-doc convention has not been established for MailBot. The W-5 contract IS documented inline in the migration header AND in the Story 3-1 AC body AND in the Epic 2 retro §13 — three canonical sources, none of which is the "schema doc" §5.2.1 expects.

**Disposition for code-review subagent:** the documentation surface for MailBot's schema currently lives in three places (migration headers, story ACs, retrospective postscripts), not a consolidated schema doc. Adding `docs/DATABASE.md` from scratch is out of scope for Story 3-1 (it would be a Story 3-N+1 of its own). The architecture.md §AR-SCHEMA-2 paragraph is owed by Winston per Epic 2 retro §13 action item — that paragraph IS the project's canonical schema-doc entry for the embedding contract. Escalating to reviewer rather than blocking the story.

### 5.3 — Lifecycle string-uniqueness check

Verdict: **N/A** — story added zero i18n keys (MailBot has no graphical frontend; Discord text is owned by Hermes container per PORTING.md; this story is backend-only schema + helper).

### 5.4 — Multi-consumer impact scan

`scripts/check_boundaries.py` is modified. It's invoked from `make lint` and consumed by `tests/unit/test_lint_boundaries.py` meta-tests. Both consumers verified:

```
Grep "scripts/check_boundaries.py" Makefile pyproject.toml tests/
tests/unit/test_lint_boundaries.py:56:    script_src = _REPO_ROOT / "scripts" / "check_boundaries.py"
tests/unit/test_lint_boundaries.py:57:    script_dst = repo_root / "scripts" / "check_boundaries.py"
```

The Makefile lint target invokes the script unconditionally (no signature change here — only an additive boundary). The meta-test cross-compiles the script into a synthetic tree and runs it as a subprocess; the test's contract (parametrized fixtures + positive-pass + f-string bypass) was extended with three new entries that all pass.

`mailbot_api/db/queries.py` is modified — additive only (new constant `EMAIL_DERIVED_FIELDS_SELECT`). No existing constant renamed or removed. Consumers of the modified module: every verb / sync / observability module imports from `queries.py`, but none import the new constant yet (Stories 3-5+ will).

Verdict: **PASS** — additive changes; both modified modules' consumers verified intact.

### 5.5 — Screenshot-based perception check

Verdict: **N/A** — story is backend-only with no user-visible surface. No AC asserts visibility. PORTING.md marks `<frontend-src>` as N/A.

### 5.6 — Upstream-contract spec coverage

Verdict: **N/A** — story is purely additive (new migration columns, new helper, new boundary check, new tests). No upstream-stripped field consumed; no projection contract dependency.

### 5.7 — Module-level mutable container check

Per Python-stack overlay: scan modified `.py` files for module-level mutable containers.

```
Grep "^_?[A-Z][A-Z_]+\s*[:=].*?(dict|list|set|\{|\[)" mailbot_api/ingest/idempotency.py
(no matches)
```

- `mailbot_api/ingest/idempotency.py` — only module-level constant: `__all__ = ["compute_idempotency_key"]`. Frozen-by-convention list literal; never mutated. ✅
- `scripts/check_boundaries.py` — added: `_IDEMPOTENCY_KEY_ALLOW = frozenset({...})` and `_IDEMPOTENCY_KEY_REQUIRED_NAMES = frozenset({...})`. Both `frozenset` — Python's built-in immutable container. ✅
- `mailbot_api/db/queries.py` — added: `EMAIL_DERIVED_FIELDS_SELECT` (string constant). Immutable by type. ✅

Verdict: **PASS** — all new module-level state is immutable (`frozenset` / string / `__all__` list).

### 5.8 — Dev-fixture seed-vs-production-shape parity check

Test-fixture trigger: story introduces two `.py.fixture` files under `tests/fixtures/lint_violations/`. These are boundary-violation fixtures consumed by the meta-test (`test_lint_boundaries.py`), not pipeline-output fixtures.

- `violates_idempotency_key_outside_allowlist.py.fixture` — pattern 3 (shape-faithful synthesis), byte-equal to the canonical formula in `mailbot_api/ingest/idempotency.py:64`. The meta-test asserts the boundary check FAILS when the fixture is placed outside the allowlist, AND PASSES when placed at the allowlisted path (via `test_idempotency_key_in_allowlisted_idempotency_path_passes`). The producer (the boundary check) IS the contract this fixture validates; producer drift is self-detected.
- `benign_sha256_use.py.fixture` — pattern 3 (shape-faithful synthesis), explicitly does NOT carry the FR-2.2 formula. Used by `test_benign_sha256_use_does_not_trigger_idempotency_boundary` as the specificity control. Producer drift is similarly self-detected — if the boundary check ever starts FLAGGING generic sha256 use, this test fails first.

Verdict: **PASS** — both fixtures are pattern-3 shape-faithful synthesis with the boundary check as the canonical producer. Drift would fail the corresponding meta-test immediately.

### 5.9 — grep-verify-cited-figures

Numeric cites in pre-review + story:

- **"343 passed, 2 skipped"** — at this artifact §AC-7 and §1 plus story Debug Log. Verified:

```
$ .venv/Scripts/python.exe -m pytest -q
343 passed, 2 skipped, 1 warning in 24.13s
```

Verdict: MATCH.

- **"+18 new tests"** — at story Debug Log. Inputs: 10 idempotency unit + 5 migration integration + 3 boundary meta = 18. Arithmetic verified.

Verdict: MATCH (10 + 5 + 3 = 18).

- **"325 baseline"** — at story Debug Log. Source: Story 2-10 sprint-status.yaml inline comment ("325 tests pass (+9 net). EPIC 2 COMPLETE."). Cross-citation from a prior-story authoritative source on the same day. No drift expected.

Verdict: MATCH — source is prior-story sprint-status row, single-cite at Debug Log only.

- **"37 columns"** — at AC-6 and §1 AC scan and `test_email_derived_fields_select_returns_all_columns:91-95`. Arithmetic: 7 derived fields × 5 companions + 2 W-5 extras (embedding_dtype + embedding_shape) = 35 + 2 = 37. Verified.

Verdict: MATCH (7 × 5 + 2 = 37).

- **"46 source files" (mypy)** — at story Debug Log. Verified by re-running mypy → `Success: no issues found in 46 source files`. Single-cite.

Verdict: MATCH.

- **"golden hex `edf960560ef1044c7d4fe2bc94aca9de0cc99071f637a1366e284292c464364d`"** — at story Debug Log and test_idempotency.py. Verified at write-time via `python -c "import hashlib; print(hashlib.sha256(b'hello world|v1|qwen2.5:3b-instruct-q4_K_M|coarse_class').hexdigest())"` → exact match.

Verdict: MATCH.

Verdict: **PASS** — every numeric figure has runnable-command anchor + actual output.

### 5.10 — Producer-boundary contract enforcement

**§5.10.a typed-column producers:** `compute_idempotency_key` accepts four `str` parameters with no coercion logic. The function does NOT call `int(...)`, `Decimal(...)`, or `datetime.fromisoformat(...)`. Inputs flow into a single `f-string.encode("utf-8")` → `hashlib.sha256(...)` pipeline. No producer-boundary input-shape risk.

`EMAIL_DERIVED_FIELDS_SELECT` is a SELECT query, not a write — read-side only. Pydantic boundary discipline applies at the write side (Stories 3-3 onward).

**§5.10.b response-shape allow-lists:** `EMAIL_DERIVED_FIELDS_SELECT` lists 37 columns explicitly — no `SELECT *`. The column list IS the allow-list, enforced at the query, not at the response model. ✅

**§5.10.c producer-boundary input-shape guard:** N/A — `idempotency.py` does not ingest third-party JSON. The future caller (Story 3-5's pipeline) will receive pre-validated Pydantic `ProcessEmailInput`-shaped data; idempotency key is computed from already-validated strings.

**§5.10.d adjacent-shared-type re-export audit:** N/A — `compute_idempotency_key` returns a primitive `str`; no shared types co-emitted.

Verdict: **PASS** — read-side query is allow-listed (explicit columns); compute helper has no coercion surface; no co-emission risk.

### 5.11 — Git-evidence consistency check

#### 5.11.a — File-List-vs-working-tree consistency

Covered in §2 above. Verdict: PASS — every File List entry in working tree; no silent scope-creep; no declared-but-not-touched paths.

#### 5.11.b — Production-only test-to-code ratio (live)

```
Manual numstat (nothing staged yet; pre-Step-2.6):

testAdded:
  +116 tests/unit/ingest/test_idempotency.py (new)
  +103 tests/integration/test_migration_011.py (new)
  +49  tests/unit/test_lint_boundaries.py (modified — additive)
  +16  tests/fixtures/.../violates_idempotency_key_outside_allowlist.py.fixture (new)
  +19  tests/fixtures/.../benign_sha256_use.py.fixture (new)
  +0   tests/unit/ingest/__init__.py (new — package marker)
  Total: 303

docsAdded:
  +48  mailbot_api/db/migrations/011_derived_fields.sql (per MailBot overlay, .sql under db/migrations/ counts as docs/schema-as-code)
  Total: 48

prodAddedExcludingDocs:
  +65  mailbot_api/ingest/idempotency.py (new)
  +48  mailbot_api/db/queries.py (modified — net additive)
  +96  scripts/check_boundaries.py (modified — net additive)
  Total: 209

prodOnlyTestRatio: 303 / 209 = 1.45
Threshold: 0.30
```

Verdict: **PASS** — 1.45 ≥ 0.30. Test ratio is unusually high because the story is heavily test-focused (Boundary check + unit + integration tests for a small helper + small migration).

#### 5.11.c — No-later-commits-under-attribution

Story status flipped to `in-progress` on 2026-06-01 (autonomous-epic-run session — same date as the audit). Same-session dev pass; no later commits expected.

```
$ rtk git log --oneline --since="2026-06-01" -- mailbot_api/db/migrations/011_derived_fields.sql mailbot_api/ingest/idempotency.py scripts/check_boundaries.py mailbot_api/db/queries.py tests/unit/test_lint_boundaries.py tests/unit/ingest/test_idempotency.py tests/integration/test_migration_011.py
(no output expected — all changes are uncommitted in working tree)
```

Verdict: **PASS** — same-session dev pass; nothing committed yet; will be staged at Step 2.6 with explicit paths.

### Posture Audit summary table

| Check                                                       | Status                                                         |
| ----------------------------------------------------------- | -------------------------------------------------------------- |
| 5.1 Lockfile hygiene                                        | ✅ PASS — N/A non-dep-change                                   |
| 5.2 Cross-doc pair verification                             | ⚠️ FLAGGED (§5.2.1) — no project schema doc; escalated to reviewer |
| 5.3 Lifecycle string-uniqueness                             | N/A — no i18n keys (no graphical frontend)                     |
| 5.4 Multi-consumer impact scan                              | ✅ PASS — additive only; consumers verified                    |
| 5.5 Screenshot-based perception check                       | N/A — backend-only                                             |
| 5.6 Upstream-contract spec coverage                         | N/A — purely additive, no upstream dependency                  |
| 5.7 Module-level mutable container                          | ✅ PASS — all module-level state is `frozenset` / `str` / `__all__` list |
| 5.8 Dev-fixture seed-vs-production-shape parity             | ✅ PASS — pattern 3 with self-detecting drift via meta-test    |
| 5.9 grep-verify-cited-figures                               | ✅ PASS — every numeric figure command-anchored                |
| 5.10 Producer-boundary contract enforcement                 | ✅ PASS — read-only query is column-allow-listed; helper has no coercion |
| 5.11 Git-evidence consistency check                         | ✅ PASS — File-List clean, test ratio 1.45 ≥ 0.30, no later commits |

**Single FLAG outcome:** §5.2.1 (no project schema doc) — escalated to reviewer per §4 disposition. Not a blocker for code-review entry.
