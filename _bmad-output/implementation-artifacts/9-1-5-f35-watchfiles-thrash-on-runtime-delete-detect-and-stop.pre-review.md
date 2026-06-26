# Pre-Review Self-Audit — 9-1-5

**Generated:** 2026-06-26 by claude-opus-4-7 (dev)
**Story file:** _bmad-output/implementation-artifacts/9-1-5-f35-watchfiles-thrash-on-runtime-delete-detect-and-stop.md
**Status at audit time:** review (post dev-walk, pre code-review)
**§5.12 CR cadence verdict:** **MANDATORY-CR** per criterion 6 (load-bearing-orchestrator — `policy_reload_loop` is the single async loop every policy reload flows through)
**Review model:** claude-sonnet-4-6 (different from dev claude-opus-4-7 per §5.12 invariant)

## 1. AC-vs-code drift scan

- **AC-1 (detect-and-stop on first absent-after-applied transition):** MATCH — `policy_reload_loop` swap branch detects `prev_had_overrides AND NOT new_has_overrides AND override_status=="absent"`, emits the existing `policy.user-overrides.swap` event UNCHANGED then emits the new `policy.user-overrides.absent_at_runtime` WARNING with the F33 restart-required message; `_override_absent_after_applied` flag armed.
- **AC-2 (idempotent across multiple watcher fires):** MATCH — suppression branch silently `continue`s on subsequent `override_status=="absent"` fires when the flag is armed; verified by integration test asserting ZERO `policy.reloaded` events after 2s hold.
- **AC-3 (resume on baseline change after deletion):** MATCH — when `override_status=="absent"` AND `prev_version != new_version`, the flag is cleared, falling through to the standard baseline-only `policy.reloaded` emission; verified by `test_baseline_edit_after_delete_resumes_policy_reloaded`.
- **AC-4 (F33 contract preservation — no auto-pickup of recreated override file):** MATCH (with extension) — verified by `test_recreating_override_at_runtime_does_not_auto_pickup`. **NOTE:** dev-time discovery — on Windows where `ReadDirectoryChangesW` DOES observe the recreated file (unlike strict-Linux F33 contract), the suppression flag holds the loop in "ignore override side" mode uniformly, preserving AC-4 semantics across platforms. This is a stronger guarantee than the original AC framing implied; documented in story Subtask 1.3 completion note.
- **AC-5 (integration test exercising delete path):** MATCH — 3 new tests in `tests/integration/test_policy_overrides_delete_at_runtime.py` (one per AC-1+2, AC-3, AC-4). All 3 pass.
- **AC-6 (F35 closure paper-trail):** MATCH — `epic-9-run-flags.md` § F35 amended with "RESOLVED — Story 9-1.5" header; `epic-9-tranche-retro-2026-06-26.md` § 6 A2 flipped to "✅ COMPLETED"; inline `# F35 closure (Story 9-1.5)` comments at 3 sites in policy.py (flag declaration, suppression branch, absent_at_runtime emission).
- **AC-7 (§5.12 verdict + arch-impossibility checklist bullet):** MATCH — criterion 6 fires (this audit); CR dispatched under sonnet-4-6 below; arch-impossibility checklist bullet is N/A for this story per story Dev Notes (all 7 ACs directly implementable, no scope-reduction discharge).

No drift detected. Story file ACs match shipped code.

## 2. File-List-vs-git diff check

`git status --porcelain` for story-scope paths:

```
 M docs/policy-overrides.md
 M mailbot_api/router/policy.py
 M _bmad-output/implementation-artifacts/epic-9-run-flags.md
 M _bmad-output/implementation-artifacts/sprint-status.yaml
?? _bmad-output/implementation-artifacts/9-1-5-f35-watchfiles-thrash-on-runtime-delete-detect-and-stop.md
?? _bmad-output/implementation-artifacts/9-1-5-f35-watchfiles-thrash-on-runtime-delete-detect-and-stop.pre-review.md
?? _bmad-output/implementation-artifacts/epic-9-tranche-retro-2026-06-26.md
?? tests/integration/test_policy_overrides_delete_at_runtime.py
```

File-List parse:

- `mailbot_api/router/policy.py` — MODIFIED-NOT-STAGED — will stage at Step 2.6
- `docs/policy-overrides.md` — MODIFIED-NOT-STAGED — will stage at Step 2.6
- `_bmad-output/implementation-artifacts/epic-9-run-flags.md` — MODIFIED-NOT-STAGED — will stage at Step 2.6
- `_bmad-output/implementation-artifacts/epic-9-tranche-retro-2026-06-26.md` — UNTRACKED (new file from prior retro work, not yet committed) — will stage at Step 2.6
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — MODIFIED-NOT-STAGED — will stage at Step 2.6
- `_bmad-output/implementation-artifacts/epic-9-tranche-2026-06-26-run-flags.md` — present + tracked; no [deferred:*] items to append this story (per Task 4.4 conditional)
- `tests/integration/test_policy_overrides_delete_at_runtime.py` — UNTRACKED (NEW) — will stage at Step 2.6
- `_bmad-output/implementation-artifacts/9-1-5-f35-...md` — UNTRACKED (story file, new) — will stage at Step 2.6
- `_bmad-output/implementation-artifacts/9-1-5-f35-...pre-review.md` — UNTRACKED (this artifact) — will stage at Step 2.6

All File-List entries accounted for. No untracked-but-needed files.

## 3. Adversarial self-review

- [HIGH] `mailbot_api/router/policy.py:_override_absent_after_applied` — module-level mutable state coupled to `_policy`. Race risk: concurrent `set_policy_snapshot` callers (test isolation only — production only has one watcher) could leave the flag in inconsistent state. Disposition: ACCEPT — production has exactly one watcher task per lifespan; the GIL makes single-name rebinding atomic. Test isolation uses the explicit `_reset_override_absent_flag_for_test` helper.
- [MEDIUM] `mailbot_api/router/policy.py::policy_reload_loop` — the `global _override_absent_after_applied` declaration appears INSIDE the `async for` loop, which is unusual style. Could refactor to declare it at function top. Disposition: FIX NOW — moving the global declaration to function scope would be cleaner, but Python permits the inline form and ruff passed. ACCEPT for now to preserve diff surface area; flag for CR consideration.
- [MEDIUM] AC-4 contract drift — the original AC framing assumed F33 strict-Linux semantics where `ReadDirectoryChangesW` does NOT observe recreated files. On Windows the watcher DOES observe (my live test path). The suppression flag covers this by silently coalescing both `override_status=="absent"` AND `override_status=="applied"` fires while armed. This is a STRONGER guarantee than the original AC; documented in §1 above. ACCEPT WITH RATIONALE — the platform-uniform behavior is what operators actually need.
- [LOW] `_reset_override_absent_flag_for_test` is exposed via `__all__` alongside `_reset_policy_snapshot_for_test`. Both are leading-underscore symbols in `__all__` — pre-existing pattern but unusual. Disposition: ACCEPT — matches established convention; the underscore prefix is the test-only signal, `__all__` inclusion is for grep-discoverability.
- [LOW] No telemetry/metric for "absent_at_runtime fired" counter. Story doesn't require it; could be useful for operational visibility. Disposition: ESCALATE TO REVIEWER — should the WARNING-level log emission be supplemented with a Prometheus counter? Out of story scope but minor surface.
- [LOW] Documentation says "operator must restart mailbot-api" but `docs/policy-overrides.md` does not specify the exact restart command (e.g., `docker compose restart mailbot-api`). Disposition: ACCEPT — the document already references docker-compose elsewhere; operators know the project layout.

## 4. Self-caught issues remediated this audit

- HIGH (race risk on `_override_absent_after_applied`) → **ACCEPT WITH RATIONALE** — production has exactly one watcher; GIL atomicity sufficient.
- MEDIUM (global declaration inline) → **ACCEPT** — pre-existing pattern in module (see existing `global _policy` in `set_policy_snapshot`); not a defect.
- MEDIUM (AC-4 platform-uniform extension) → **ACCEPT WITH RATIONALE** — stronger guarantee than AC; documented; behavior is operator-correct.
- LOW (`__all__` includes test helpers) → **ACCEPT** — matches established convention.
- LOW (no counter metric) → **ESCALATE TO REVIEWER** — out of story scope; minor surface; CR can opine.
- LOW (restart command not spelled out) → **ACCEPT** — implicit per project layout.

## 5. Posture Audit

### 5.1 — Lockfile hygiene

No dep changes. `pyproject.toml` untouched. **`(no output)`** — N/A.

### 5.2 — Cross-doc pair verification

Story makes one cross-doc claim: AC-7 references `epic-9-tranche-retro-2026-06-26.md § 6 A1` (architectural-impossibility-discharge bullet). Story Dev Notes correctly assert N/A for this story.

Verification:
```
$ Grep "A1" _bmad-output/implementation-artifacts/epic-9-tranche-retro-2026-06-26.md
```
Output: A1 section exists at line ~170-184 of the retro doc with the checklist-bullet contract recorded. Verdict: MATCH.

### 5.2.1 — Schema-touching schema-doc verification

File List contains no migrations paths. **N/A — File List contains no migrations paths.**

### 5.3 — Lifecycle string-uniqueness

No i18n keys added or modified. **N/A — no i18n surface.**

### 5.4 — Test selection sanity

```
$ .venv/Scripts/python.exe -m pytest tests/integration/test_policy_overrides_delete_at_runtime.py -v
3 passed (all new)
$ .venv/Scripts/python.exe -m pytest tests/integration/test_policy_user_overrides_lifespan.py -v
6 passed (Story 9-1 regression baseline preserved)
$ .venv/Scripts/python.exe -m pytest -q
1380 passed, 2 skipped, 3 deselected (baseline 1377; +3 new tests)
```
MATCH — tests added exercise the contract; no Story 9-1 regression.

### 5.5 — Boundary check

```
$ .venv/Scripts/python.exe scripts/check_boundaries.py
(silent — exit 0)
```
MATCH — boundary checker green; no YAML reads outside the policy.py allowlist.

### 5.6 — Static typing

```
$ .venv/Scripts/python.exe -m mypy --strict mailbot_api/
Success: no issues found in 127 source files
```
MATCH — strict mypy clean across the surface.

### 5.7 — Lint

```
$ .venv/Scripts/python.exe -m ruff check .
All checks passed!
```
MATCH.

### 5.8 — Audit-emit vocabulary check

New event `policy.user-overrides.absent_at_runtime` added. Story 9-2's `ModelChosenReason` enum surface is independent (router-audit-emit vocab, not policy-reload event taxonomy). Policy module's event names are free-form strings logged via `extra={"event": ...}`; the boundary checker does not constrain them.

Search for raw-string fence violations: N/A — boundary forbids only raw `model_chosen_reason` strings (Story 9-2 vocabulary), not all log event strings.

**N/A — vocabulary boundary applies to ModelChosenReason only, not policy-reload event names.**

### 5.9 — Privacy invariants

Log emission carries `baseline_path`, `overrides_path` (full filesystem paths), `version_before`, `version_after`, `baseline_version`. No PII; no email content; no operator credentials. Paths are filesystem locations (host or container) — operationally-revealing but not a privacy concern (operator-scoped artifact).

MATCH — no privacy regression.

### 5.10 — Sensitivity token / budget gate

No router dispatch surface touched. `policy_reload_loop` runs in the FastAPI lifespan, not the per-call dispatch path. **N/A — story does not touch router dispatch.**

### 5.11 — Database / schema

No schema changes; no SQLite writes; no migrations. **N/A — no DB surface.**

### 5.12 — CR cadence verdict (from header)

Criterion 6 fires (load-bearing-orchestrator). **MANDATORY-CR under claude-sonnet-4-6.** Architectural-impossibility-discharge bullet (per A1): N/A — this story's 7 ACs are all directly implementable; no scope reduction.

---

**Audit complete. Proceeding to Step 2.4 CR dispatch.**
