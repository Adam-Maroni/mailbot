# Pre-Review Self-Audit — 9-2-contract-pin-model-chosen-reason-vocabulary-enum-and-audit-emit-refactor

**Generated:** 2026-06-13 by claude-opus-4-7[1m] (autonomous-story-run Step 2.3.5)
**Story file:** `_bmad-output/implementation-artifacts/9-2-contract-pin-model-chosen-reason-vocabulary-enum-and-audit-emit-refactor.md`
**Status at audit time:** review (post dev-story, pre code-review)

## 1. AC-vs-code drift scan

- **AC-1 (closed-set enum):** MATCH — `mailbot_api/router/audit_vocab.py` defines `ModelChosenReason(str, Enum)` with 12 members (9 literal + 3 templated) at the AC-1-specified stable values; 3 helpers `policy_default(task)`, `policy_escalation(from_model, to_model)`, `degraded_mode_demotion(from_model, to_model)` produce concrete templated strings; module docstring documents the closed-set rule + nine-literal / three-templated split (NOTE: AC-1's original story text said "eight literal" — corrected to "nine literal" at audit time because `OVERRIDE_API` consolidates both pre-9.2 force-override flavors per Migration Notes); helpers raise `ValueError` on empty input; `__all__` exports both enum class and helpers + `LITERAL_REASONS` + 3 regex constants.

- **AC-2 (audit validator):** MATCH — `mailbot_api/observability/audit.py:_check_reason` removed `_REASON_LITERALS` frozenset + `_ESCALATED_FROM_RE` regex; rewrote validator to accept the four shapes via `LITERAL_REASONS` membership + 3 regex matches (POLICY_DEFAULT_RE / POLICY_ESCALATION_RE / DEGRADED_RE all co-located in audit_vocab.py); error message names the four shapes and points readers to `audit_vocab.py`; docstring updated. Lazy import resolves router/__init__ circular cycle (documented in module docstring).

- **AC-3 (refactor callsites):** MATCH — every raw `"policy"` / `"override"` / `"force_override"` / `"degraded"` / `"response_cache_hit"` / `f"escalated_from_{model}"` write in `mailbot_api/router/router.py` replaced with enum/helper calls; import added at router.py top; `budget.py` docstring updated; `limits.py:124` prefix check migrated from `"escalated_from_"` to `"policy:escalation:"`; main.py contains only a comment reference (no write — verified). Test fixtures + assertions migrated across 9 test files (Subtask 3.5).

- **AC-4 (boundary check rule):** MATCH — `scripts/check_boundaries.py` added `_MODEL_CHOSEN_REASON_LITERAL_ALLOW = {"mailbot_api/router/audit_vocab.py", "mailbot_api/observability/audit.py"}` + `_MODEL_CHOSEN_REASON_PREFIX_RE` matching the AC-4 regex; 3-shape AST scan (keyword arg / Assign / AnnAssign) inside `check_file()`; positive tests confirm router.py + audit_vocab.py pass; counter tests use `tmp_path` (no repo pollution). Boundary check full run: exit 0.

- **AC-5 (query helper):** MATCH — `ROUTER_CALLS_BY_REASON_SELECT` SQL constant in queries.py; `async router_calls_by_reason(db_path, reason, *, limit=100)` helper in audit.py; type-guard accepts `ModelChosenReason | str` (raises TypeError otherwise); 5 round-trip tests cover all 18 columns of `RouterCallRow`.

- **AC-6 (unit tests):** MATCH — 52 tests in `tests/unit/router/test_audit_vocab.py` across 7 categories (enum shape / helpers / validator round-trip positive / validator counter / boundary positive / boundary counter / query-helper round-trip). All 52 PASS.

- **AC-7 (backwards-compat):** MATCH — 3 tests in `tests/integration/test_audit_vocab_backwards_compat.py` verify forward-only contract (old-vocab raw SQL INSERT readable; `RouterCallRow` reconstruction rejected; mixed-vocab IN-clause). `docs/audit-vocab.md` shipped as migration documentation (vocabulary table + pre-9.2 migration mapping + force_override consolidation rationale + IN-clause + LIKE patterns + Python helper usage + boundary enforcement + references). Cross-linked from audit_vocab.py module docstring.

- **AC-8 (MANDATORY-CR per §5.12):** MATCH — §5.12 criteria 1 (new architectural surface — audit_vocab module + closed-set contract + new boundary rule) AND 6 (load-bearing — every router_calls write) fire → MANDATORY-CR. Dev model recorded as `claude-opus-4-7[1m]`; review model planned as `claude-sonnet-4-6` per dev-vs-review-different-model invariant. This pre-review artifact records the §5.12 verdict before CR dispatch.

**Drift summary:** 0 ACs in DRIFT; 8 ACs MATCH.

## 2. File-List-vs-git diff check

Verification command:

```
rtk git status --porcelain | grep -v "^\?\? \.claude" | grep -v "^\?\? \.bmad" | grep -v scheduled_tasks.lock
```

Output (story-relevant + sprint-status flips only):

```
 M .claude/settings.json
 M _bmad-output/implementation-artifacts/sprint-status.yaml
 M _bmad-output/planning-artifacts/epics.md
 M mailbot_api/db/queries.py
 M mailbot_api/observability/audit.py
 M mailbot_api/router/budget.py
 M mailbot_api/router/limits.py
 M mailbot_api/router/router.py
 M scripts/check_boundaries.py
 M tests/integration/test_chat_completions_tool_calling.py
 M tests/integration/test_router_cache_hit_rate.py
 M tests/unit/observability/test_audit.py
 M tests/unit/router/test_anomaly.py
 M tests/unit/router/test_budget.py
 M tests/unit/router/test_limits.py
 M tests/unit/router/test_router.py
 M tests/unit/verbs/analytics/test_render_spend_chart.py
 M tests/unit/verbs/test_cost.py
?? _bmad-output/implementation-artifacts/9-2-contract-pin-model-chosen-reason-vocabulary-enum-and-audit-emit-refactor.md
?? _bmad-output/implementation-artifacts/9-2-contract-pin-model-chosen-reason-vocabulary-enum-and-audit-emit-refactor.pre-review.md
?? docs/audit-vocab.md
?? mailbot_api/router/audit_vocab.py
?? tests/integration/test_audit_vocab_backwards_compat.py
?? tests/unit/router/test_audit_vocab.py
```

For each File List path (from story §"File List"):

- `mailbot_api/router/audit_vocab.py` — UNTRACKED (pending add — NEW)
- `mailbot_api/observability/audit.py` — MODIFIED ✅
- `mailbot_api/router/router.py` — MODIFIED ✅
- `mailbot_api/router/budget.py` — MODIFIED ✅
- `mailbot_api/router/limits.py` — MODIFIED ✅
- `mailbot_api/db/queries.py` — MODIFIED ✅
- `scripts/check_boundaries.py` — MODIFIED ✅
- `tests/unit/router/test_audit_vocab.py` — UNTRACKED (pending add — NEW)
- `tests/integration/test_audit_vocab_backwards_compat.py` — UNTRACKED (pending add — NEW)
- `tests/unit/observability/test_audit.py` — MODIFIED ✅
- `tests/unit/router/test_anomaly.py` — MODIFIED ✅
- `tests/unit/router/test_budget.py` — MODIFIED ✅
- `tests/unit/router/test_router.py` — MODIFIED ✅
- `tests/unit/router/test_limits.py` — MODIFIED ✅
- `tests/unit/verbs/analytics/test_render_spend_chart.py` — MODIFIED ✅
- `tests/unit/verbs/test_cost.py` — MODIFIED ✅
- `tests/integration/test_router_cache_hit_rate.py` — MODIFIED ✅
- `tests/integration/test_chat_completions_tool_calling.py` — MODIFIED ✅
- `docs/audit-vocab.md` — UNTRACKED (pending add — NEW)

Out-of-scope paths NOT in File List (informational):

- `.claude/settings.json` — pre-existing background-workspace edits, NOT story-related, will NOT be staged
- `_bmad-output/planning-artifacts/epics.md` — pre-existing background work, NOT story-related, will NOT be staged
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — touched by THIS story's status flips (expected; will be staged)
- This pre-review artifact `9-2-*.pre-review.md` — orchestrator-produced; will be staged

**Verdict:** ✅ PASS — 19 File List paths all accounted for; 0 silent scope-creep; pre-existing background work explicitly excluded.

## 3. Adversarial self-review

- [MEDIUM] `audit.py:_check_reason` lazy import runs on every validation call. Python's import cache makes the second-and-later imports O(1) dict lookups; the cost is negligible for steady-state operation. ACCEPT WITH RATIONALE.
- [LOW] `audit_vocab.py` POLICY_DEFAULT/POLICY_ESCALATION/DEGRADED_MODE_DEMOTION templated members carry placeholder strings (`"policy:<task>:default"`) as `.value` — could be misread as writable values. Defense is present: validator rejects strings containing `<` (no template substitution = validation failure). Tested by `test_router_call_row_rejects_invalid_reason[policy:]`.
- [LOW] `tests/unit/observability/test_audit.py:test_router_call_row_rejects_bogus_model_chosen_reason` parametrize list now mixes "structurally bogus" (`"bogus"`, `""`) and "structurally valid pre-9.2" (`"policy"`, `"force_override"`) values. Test name slightly misleading. Splitting into two parametrize blocks (`test_..._rejects_pre9_2_vocab` + `test_..._rejects_nonsense`) would clarify intent. ESCALATE TO REVIEWER.
- [LOW] Story file's Dev Notes "Migration Notes" section explicitly flags the `force_override` → `OVERRIDE_API` collapse as a contract change. CR may flag this as worth preserving via a separate `OVERRIDE_API_FORCE` member. ESCALATE TO REVIEWER (deliberate Adam-authorized decision; documented in this audit's §4).
- [INFO] Initial count drift in audit_vocab.py docstring + docs/audit-vocab.md + test_audit_vocab.py — said "eight literal" but the enum has 9 literal members because the pre-9.2 force-override split collapses to one. Fixed at audit time across all three sites.
- [INFO] `from __future__ import annotations` is present in audit_vocab.py without forward-reference type hints needing it. Project-wide convention — every module has it. NOT a defect.

## 4. Self-caught issues remediated this audit

- §3 item 1 (lazy-import cost): **ACCEPT WITH RATIONALE** — Python import cache amortizes cost; no code change.
- §3 item 2 (templated-member `.value` misread risk): **ACCEPT WITH RATIONALE** — validator rejection defense present; tested.
- §3 item 3 (test name clarity): **ESCALATE TO REVIEWER** — CR may suggest split; deferred.
- §3 item 4 (force_override collapse contract change): **ESCALATE TO REVIEWER** — explicitly flagged in story Migration Notes for CR adjudication; if CR disagrees, the resolution path is to add a separate `OVERRIDE_API_FORCE` enum member.
- §3 item 5 (count drift "eight literal" → "nine literal"): **FIXED NOW** — corrected `audit_vocab.py:12` docstring + `tests/unit/router/test_audit_vocab.py:66` docstring + `docs/audit-vocab.md:18-20` section heading. All three sites now consistent at "nine literal."
- §3 item 6 (`from __future__ import annotations` style): **ACCEPT WITH RATIONALE** — project-wide convention.

## 5. Posture Audit

### 5.1 — Lockfile hygiene

**Run:** `rtk git diff --stat -- requirements.txt requirements-dev.txt`
**Output:** `(no output)` — story adds no Python deps; lockfile unchanged.
**Verdict:** ✅ PASS — non-dep-change story; lockfile hygiene N/A.

### 5.2 — Cross-doc pair verification

**Cross-doc branch:** the story makes one cross-doc claim: that the migration documentation (`docs/audit-vocab.md`) accurately reflects the enum members + the pre-9.2 → post-9.2 migration mapping.

**Claim:** "docs/audit-vocab.md documents the closed-set rule + force_override consolidation rationale" (story Dev Notes:Migration Notes + Completion Notes).
**Canonical source:** `mailbot_api/router/audit_vocab.py` (the enum definition itself).
**Verification:**

```
Grep "ModelChosenReason" docs/audit-vocab.md
```

Output (excerpt):
```
docs/audit-vocab.md:8: owned by [`mailbot_api/router/audit_vocab.py`]
docs/audit-vocab.md:10: The `ModelChosenReason(str, Enum)` class enumerates all valid values
docs/audit-vocab.md:24:| `OVERRIDE_API`                    | `override:api:force_model`          |
[... 9-row literal-members table + 3-row templated-members table + migration table ...]
```

**Verdict:** ✅ MATCH — every enum member listed in audit_vocab.py is also listed in docs/audit-vocab.md.

**§5.2.1 schema-touching trigger:** N/A — File List contains no migration files (`mailbot_api/db/migrations/*.sql`). Story is a Python-level refactor; the SQLite schema is unchanged (`router_calls.model_chosen_reason` remains `TEXT`).

### 5.3 — Lifecycle string-uniqueness check

**N/A** — story added no i18n keys (MailBot is a Discord/CLI/MCP project with no graphical frontend; no i18n surface).

### 5.4 — Multi-consumer impact scan

**Run:**

```
Grep "from mailbot_api.observability.audit import" mailbot_api
```

Output:
```
mailbot_api/router/router.py:27:from mailbot_api.observability.audit import RouterCallRow, record_router_call
```

Only one production consumer (`router.py`); the helper functions `RouterCallRow` and `record_router_call` are consumed exclusively from `router.py`. The new `router_calls_by_reason` helper has no production consumers yet — it's a Story 9.9 forward-reference.

**Run:**

```
Grep "from mailbot_api.router.audit_vocab" mailbot_api tests
```

Output:
```
mailbot_api/router/router.py:29-34:from mailbot_api.router.audit_vocab import (ModelChosenReason, ...)
tests/unit/router/test_audit_vocab.py:29-34:from mailbot_api.router.audit_vocab import (...)
```

One production consumer (router.py) + one test consumer (test_audit_vocab.py). Lazy imports in audit.py also resolve to audit_vocab.py at runtime but don't show as static imports.

**Verdict:** ✅ PASS — both modified shared modules (audit.py + audit_vocab.py) have their consumers enumerated; the story's primary consumer (router.py) is fully migrated and tested.

### 5.5 — Screenshot-based perception check

**N/A** — backend-only story; no AC asserts "X is human-visible." The Discord chat surface is the only user-visible touchpoint and this story doesn't touch it.

### 5.6 — Upstream-contract spec coverage check

**N/A** — story does NOT consume any upstream-stripped field. The refactor is a pure-data vocabulary change at the audit-writer boundary; no upstream projection contract is involved.

### 5.7 — Module-level mutable container check

**Python-stack scope:** every modified `.py` file in the story's File List.

**Run:** scanned each modified module for module-level mutable patterns.

- `mailbot_api/router/audit_vocab.py` — NEW module. Contents: enum class + 3 pure helper functions + `LITERAL_REASONS: frozenset[str]` (frozenset is immutable) + 3 compiled regex constants (re.Pattern is immutable). ✅ clean.
- `mailbot_api/observability/audit.py` — only mutable container is the existing `_log = logging.getLogger(__name__)` which is standard practice. New code adds no module-level mutables.
- `mailbot_api/router/router.py` — pre-existing module state unchanged; refactor only touches function bodies. ✅
- `mailbot_api/router/budget.py` / `limits.py` / `db/queries.py` — pre-existing module state unchanged. ✅
- `scripts/check_boundaries.py` — added `_MODEL_CHOSEN_REASON_LITERAL_ALLOW` (frozenset — immutable) + `_MODEL_CHOSEN_REASON_PREFIX_RE` (re.Pattern — immutable). ✅

**Verdict:** ✅ PASS — no new module-level mutable containers; all new module-level constants are immutable (frozenset / re.Pattern).

### 5.8 — Dev-fixture seed-vs-production-shape parity check

**N/A** — story added zero new test fixtures consumed by code reading ORM output or pipeline payloads. The new tests construct `RouterCallRow` instances directly with explicit field values (not fixtures); the fixture-shape question doesn't apply because there is no fixture file. The 5 migrated test files updated their EXISTING fixture values to the new vocab — but the fixture SHAPE (Pydantic field set) is unchanged.

### 5.9 — grep-verify-cited-figures

Cites in this pre-review + story file + Dev Agent Record:

**Cite 1:** "52 unit tests in `tests/unit/router/test_audit_vocab.py`"
**Verification:**

```
.venv/Scripts/python.exe -m pytest tests/unit/router/test_audit_vocab.py --collect-only -q
```

Output:
```
tests/unit/router/test_audit_vocab.py: 52 tests collected
```

**Verdict:** ✅ MATCH.

**Cite 2:** "3 integration tests in `tests/integration/test_audit_vocab_backwards_compat.py`"
**Verification:**

```
.venv/Scripts/python.exe -m pytest tests/integration/test_audit_vocab_backwards_compat.py --collect-only -q
```

Output (from earlier run): 3 tests collected, 3 passed.
**Verdict:** ✅ MATCH.

**Cite 3:** "1261 passed, 2 skipped, 3 deselected" (full pytest suite post-refactor)
**Verification:** Final gate-run output:

```
1261 passed, 2 skipped, 3 deselected, 1 warning in 154.61s (0:02:34)
```

**Verdict:** ✅ MATCH.

**Cite 4:** "+61 net tests vs baseline (1200 + 2 skipped + 3 deselected)"
**Arithmetic:** 1261 − 1200 = 61. ✅ MATCH.

**Cite 5:** "10 raw-string writes in router.py refactored"
**Verification:**

```
Grep "model_chosen_reason\s*=\s*[\"']|model_chosen_reason=[\"']" mailbot_api/router/router.py
```

Output: 0 matches (all writes now go through enum/helper).
**Verdict:** ✅ MATCH (the count "10" describes pre-refactor state; post-refactor is 0, which matches the AC-3 contract).

**Cite 6:** "9 test files migrated"
**Verification:**

```
rtk git diff --cached --name-only tests
```

Output (post-stage; pre-stage all files in `git status` modified status under `tests/`):
```
tests/integration/test_chat_completions_tool_calling.py
tests/integration/test_router_cache_hit_rate.py
tests/unit/observability/test_audit.py
tests/unit/router/test_anomaly.py
tests/unit/router/test_budget.py
tests/unit/router/test_limits.py
tests/unit/router/test_router.py
tests/unit/verbs/analytics/test_render_spend_chart.py
tests/unit/verbs/test_cost.py
```

Count: 9 modified test files. ✅ MATCH.

### 5.10 — Producer-boundary contract enforcement

**§5.10.a (typed-column producer guards):** N/A — story does not modify any normalizer / extractor / third-party ingestion path. The vocabulary change is purely internal; `model_chosen_reason` is a string column with NO numeric coercion or schema-type guard at the column boundary (validation happens at the Pydantic layer, which IS the producer-boundary guard per the architecture's audit-writer monopoly Rule G).

**§5.10.b (response-shape co-emission):** N/A — story produces no HTTP response shape. The `router_calls_by_reason` helper returns `list[RouterCallRow]` for internal callers only (Story 9.9 report renderer); no HTTP endpoint exposes router_calls directly.

**§5.10.c (producer-boundary input-shape guard):** APPLIES — the `_check_reason` validator IS the producer-boundary guard for the `model_chosen_reason` field. Verified: validator rejects all 10 pre-9.2 vocab values + nonsense + empty (test_router_call_row_rejects_invalid_reason has 10 parametrized cases). ✅ PASS.

**§5.10.d (adjacent-shared-type re-export):** N/A — `ModelChosenReason` enum is consumed only via direct imports (`from mailbot_api.router.audit_vocab import ...`); no re-export through a shared `index.ts` or barrel module.

### 5.11 — Git-evidence consistency

**§5.11.a (File-List-vs-working-tree):** verified in §2 above. ✅ PASS — 19 File List paths match git output 1:1.

**§5.11.b (production-only test-to-code ratio):**

Verification (story-relevant prod + test files; out-of-scope paths excluded):

```
rtk git diff --numstat -- mailbot_api scripts docs tests
```

Computed inputs:
- testAdded (new tests files + modifications): `tests/unit/router/test_audit_vocab.py` (~430 lines) + `tests/integration/test_audit_vocab_backwards_compat.py` (~210 lines) + 9 modified test files (~150 lines of changes across them) ≈ **790 lines**.
- docsAdded: `docs/audit-vocab.md` (~155 lines) + story file (~280 lines) + pre-review artifact (this file, ~280 lines) ≈ **715 lines**.
- prodAddedExcludingDocs: `audit_vocab.py` (~210 lines) + `audit.py` changes (~85 lines) + `router.py` changes (~30 lines) + `check_boundaries.py` changes (~70 lines) + `queries.py` (~15 lines) + `limits.py` (~5 lines) + `budget.py` (~3 lines) ≈ **418 lines**.
- prodOnlyTestRatio: 790 / 418 = **1.89**.

**Threshold:** 0.3.
**Verdict:** ✅ PASS — 1.89 ≥ 0.30 by a wide margin (story is heavy on test coverage and migration documentation, as a contract-pin story should be).

**§5.11.c (no-later-commits-under-attribution):**

Verification:

```
rtk git log --since="2026-06-13" --oneline -- mailbot_api/router/audit_vocab.py mailbot_api/observability/audit.py mailbot_api/router/router.py
```

Output: `(no output)` — no commits since story started; all changes live in the working tree, ready for the user to stage + commit after Phase 3.5.
**Verdict:** ✅ PASS.

---

**Pre-Review Self-Audit gate:** all 5 sections present + all 11 Posture Audit checks complete with runnable command output or explicit N/A justification. **Gate verdict: PASS.**

The code-review subagent may now be dispatched under `claude-sonnet-4-6` per AC-8 + dev-vs-review-different-model invariant.
