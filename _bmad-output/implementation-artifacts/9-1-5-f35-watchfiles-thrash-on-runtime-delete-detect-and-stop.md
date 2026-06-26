---
baseline_commit: 5ff0ff4f7a04e67c78301f6065316bb7e17f5670
---

# Story 9.1.5: F35 watchfiles thrash on runtime override-file deletion — detect-and-stop-watching + restart-required warning

Status: done

**Origin:** filed during Epic 9 `/model` surface tranche retrospective 2026-06-26 ([epic-9-tranche-retro-2026-06-26.md § 6 A2](./epic-9-tranche-retro-2026-06-26.md)). F35 HIGH was originally discovered during Story 9-1 Phase 3.5 manual-verification live walk 2026-06-13 ([epic-9-run-flags.md § F35](./epic-9-run-flags.md)). The fix shape was deferred from Story 9-1 because the workaround ("don't `rm` the override file at runtime") is operationally sufficient: `/model persistent` (Story 9-4) atomically rewrites the file via `os.replace()` and never deletes it, so the bug only fires on direct operator `rm`. The Epic 9 tranche retro filed it as A2 with priority P0 to land before the benchmark tranche reactivates, because the same `policy_reload_loop` watchfiles surface may be touched by Story 9-6 runner or Story 9-9 report.

## Story

As Adam,
I want `mailbot_api/router/policy.py::policy_reload_loop` to detect when the override file `router/policy.user-overrides.yaml` has transitioned from "present + applied" to "absent at runtime" and STOP firing redundant `policy.reloaded` events against the now-deleted path,
So that direct operator `rm router/policy.user-overrides.yaml` at runtime no longer floods the audit log with ~60+ identical `policy.reloaded` events over 20 seconds (one fire every ~310ms from watchfiles thrashing against the nonexistent path), and so the audit log stays useful for catching real `policy.reloaded` events from baseline `policy.yaml` edits.

## Acceptance Criteria

**AC-1 — Detect-and-stop-watching on first absent-after-applied transition.**

**Given** `mailbot_api/router/policy.py::policy_reload_loop` watches both `path` (baseline) and `overrides_path` (companion) per Story 9-1 contract
**When** the overrides file is DELETED at runtime (transitioning the override status from `applied` to `absent` while the watcher was active)
**Then** the loop emits the existing `event="policy.user-overrides.swap"` ONCE with `version_before="<baseline>+overrides:<hash>"` → `version_after="<baseline>"` (this fire is correct per Story 9-1 CR-F1 semantics and stays unchanged)
**And** the loop emits ONE NEW `event="policy.user-overrides.absent_at_runtime"` log line at WARNING level with the message `"override file deleted at runtime; subsequent edits will require mailbot-api restart to re-arm watcher (watchfiles cannot watch newly-appeared paths per F33 upstream contract)"`
**And** the loop EXITS the absent-after-applied watch cycle cleanly — subsequent watchfiles fires against the nonexistent path are silently coalesced (NOT logged, NOT acted on) until either the watcher is restarted or a NEW change to the baseline `policy.yaml` is observed
**And** the existing `event="policy.reloaded"` log is preserved when the baseline `policy.yaml` is edited after the override was deleted (no behavior regression for the baseline-only path; the loop is allowed to wake on baseline edits even though the override path is now silently coalesced)

**AC-2 — Idempotent across multiple watcher fires after deletion.**

**Given** watchfiles continues firing change events at ~310ms cadence after the override file is `rm`'d (because the watch descriptor was bound to the now-nonexistent path — upstream behavior per F35 evidence)
**When** the loop receives the 2nd, 3rd, ... Nth fire after the absent-at-runtime transition
**Then** the loop calls `load_policy_with_status(path, overrides_path=overrides_path)` per usual
**And** the returned `override_status == "absent"` (per Story 9-1 `OverrideLoadStatus` discriminator)
**And** the loop computes `prev_version == new_version` (both are `f"{baseline.version}"` with no `+overrides:` suffix) and the override-suffix-presence comparison is `prev_had_overrides=False AND new_has_overrides=False`
**And** the loop SKIPS emitting `policy.reloaded` for these spurious fires (a new branch in the existing `if new_has_overrides or prev_had_overrides:` / `else` logic detects "absent post-transition" and short-circuits)
**And** the audit log shows AT MOST ONE `policy.user-overrides.swap` + ONE `policy.user-overrides.absent_at_runtime` line per deletion event (vs the F35-observed flood of ~60+ `policy.reloaded` events over 20 seconds)

**AC-3 — Resume on baseline change after deletion.**

**Given** the override file has been deleted and the absent-at-runtime warning has fired
**When** the baseline `policy.yaml` is subsequently edited (e.g., `vim router/policy.yaml` to bump a model assignment)
**Then** the loop wakes per usual via the still-active baseline watch descriptor
**And** the loop loads the new baseline + sees `override_status == "absent"` and emits the standard `event="policy.reloaded"` log line with the new baseline version (no `+overrides:` suffix, since override is absent)
**And** the absent-at-runtime suppression state DOES NOT persist across this baseline-edit event — the next override-related transition (e.g., operator re-creates the override file via the bootstrap path, restarts mailbot-api per F33 contract, then mutates the override) is handled per the standard Story 9-1 flow

**AC-4 — F33 contract preservation: still no auto-pickup of recreated override file.**

**Given** F33 is the documented upstream watchfiles contract: `awatch` cannot watch a path that did not exist at watcher-start time
**When** the override file is deleted at runtime, then later RE-CREATED at runtime (e.g., operator runs `cp router/policy.user-overrides.yaml.example router/policy.user-overrides.yaml` without restarting mailbot-api)
**Then** the watcher does NOT pick up the re-created file (this is the F33 contract — no change)
**And** the absent-at-runtime warning (AC-1) explicitly references the F33 restart-required limitation in its log message so operators have the recovery path inline
**And** the existing `docs/policy-overrides.md` "Hot-reload contract limitation — file-must-exist-at-startup" section is amended with the new absent-at-runtime detection behavior (1-2 sentences referencing this story's `policy.user-overrides.absent_at_runtime` event)

**AC-5 — Integration test exercising the delete path.**

**Given** Story 9-1's integration test `tests/integration/test_policy_user_overrides_lifespan.py` uses `tmp_path` fixtures that NEVER delete files mid-test (the gap that allowed F35 to escape to live walk)
**When** a new integration test `tests/integration/test_policy_overrides_delete_at_runtime.py` is added
**Then** the test starts a FastAPI lifespan with a populated override file via the Story 9-1 fixture pattern
**And** the test asserts the initial `version` carries the `+overrides:<hash>` suffix
**And** the test `os.unlink`'s the override file mid-lifespan
**And** the test asserts EXACTLY ONE `policy.user-overrides.swap` event fires (capturing with a structured-log capture fixture per Story 9-1 pattern)
**And** the test asserts EXACTLY ONE `policy.user-overrides.absent_at_runtime` event fires
**And** the test asserts that after holding for 2 seconds (long enough for watchfiles to thrash ~6 times at the observed 310ms cadence), the captured log contains NO additional `policy.reloaded` events for the override-side spurious fires
**And** the test asserts that mutating the baseline `policy.yaml` AFTER deletion fires ONE `policy.reloaded` event with the new baseline version (AC-3 resume contract)
**And** the test asserts the final in-memory `PolicyTable.version` equals `baseline.version` (no `+overrides:` suffix) and `PolicyTable.overrides_applied == frozenset()` (per Story 9-4 provenance contract)

**AC-6 — F35 closure paper-trail.**

**Given** F35 was filed as HIGH severity in [epic-9-run-flags.md](./epic-9-run-flags.md)
**When** Story 9-1.5 ships
**Then** `epic-9-run-flags.md` § F35 section is amended with a "**RESOLVED — Story 9-1.5 — `<commit-hash>`**" header at the top of the section
**And** [epic-9-tranche-retro-2026-06-26.md § 6 A2](./epic-9-tranche-retro-2026-06-26.md) is amended with a "✅ COMPLETED — Story 9-1.5 — `<date>`" status note
**And** the absent-at-runtime detection branch in `policy_reload_loop` carries an inline `# F35 closure (Story 9-1.5)` comment for code archaeology

**AC-7 — §5.12 CR cadence verdict + architectural-impossibility-discharge checklist bullet (A1 from tranche retro).**

**Given** this story modifies the load-bearing `policy_reload_loop` orchestrator (the same surface Story 9-1 CR-F1 protected via the discriminated `OverrideLoadStatus`)
**When** §5.12 CR cadence is evaluated per the 6 criteria
**Then** criterion 6 (load-bearing-orchestrator — `policy_reload_loop` is the single async loop that all policy reloads flow through) fires → **MANDATORY-CR per §5.12**
**And** the code-review subagent runs under `claude-sonnet-4-6` per the dev-vs-review-different-model invariant (Adam is running Opus 4.7 inline)
**And** the pre-review self-audit artifact `9-1-5-f35-watchfiles-thrash-on-runtime-delete-detect-and-stop.pre-review.md` records the §5.12 verdict before the CR dispatch
**And** the pre-review self-audit ALSO includes (per [epic-9-tranche-retro-2026-06-26.md § 6 A1](./epic-9-tranche-retro-2026-06-26.md)) the new self-audit bullet: "if you discharged an AC as architecturally-impossible or otherwise scope-reduced it (e.g., a guard test in `scripts/check_boundaries.py` or `tests/integration/test_hermes_config.py` blocks the AC's required code shape), did you annotate the epics.md AC block with a `> **OQ-N discharge note (date):**` line pointing to the story file?" — this story's ACs are all directly implementable so the bullet's answer is N/A for this story, but the inclusion validates the §5.12 checklist update from the tranche retro

## Tasks / Subtasks

- [x] **Task 1 — Detect-and-stop-watching branch in `policy_reload_loop`** (AC: 1, 2)
  - [x] Subtask 1.1 — Module-level `_override_absent_after_applied: bool = False` flag added alongside `_policy`. Cleared via process restart (natural module reset) OR explicit baseline-version-change branch (AC-3 resume). Test-only helper `_reset_override_absent_flag_for_test` exposed for test isolation.
  - [x] Subtask 1.2 — Detect-and-emit branch added inside the `if new_has_overrides or prev_had_overrides:` swap path: when `prev_had_overrides AND NOT new_has_overrides AND override_status=="absent"`, emit the existing `policy.user-overrides.swap` (unchanged) THEN emit the new `policy.user-overrides.absent_at_runtime` WARNING + arm the suppression flag. The F33 restart-required message is the WARNING's log message.
  - [x] Subtask 1.3 — Suppression branch added: when `_override_absent_after_applied` is armed AND the fire is NOT a baseline change, silently `continue`. Covers BOTH (a) the F35 thrash (`override_status=="absent"` spurious fires) AND (b) AC-4 F33 contract preservation on platforms where the watcher CAN observe a recreated file (Windows ReadDirectoryChangesW) — uniform behavior across platforms.
  - [x] Subtask 1.4 — AC-3 resume clears the flag when `override_status=="absent" AND prev_version != new_version` (operator edited `policy.yaml`).

- [x] **Task 2 — Integration test for the delete path** (AC: 5)
  - [x] Subtask 2.1 — `tests/integration/test_policy_overrides_delete_at_runtime.py` created mirroring Story 9-1's fixture pattern (real on-disk YAML, real `awatch`, real Pydantic, `tmp_path`-backed paths). The `_reset_policy_module` fixture also resets the F35 suppression flag for clean test isolation.
  - [x] Subtask 2.2 — `test_delete_at_runtime_emits_swap_and_absent_warning_then_suppresses` asserts exactly 1 `swap` (version_after loses `+overrides:`), exactly 1 `absent_at_runtime` WARNING (message contains "restart"), zero `policy.reloaded` for override-side spurious fires after 2s hold, final snapshot reflects baseline-only with empty `overrides_applied`.
  - [x] Subtask 2.3 — `test_baseline_edit_after_delete_resumes_policy_reloaded` asserts AC-3 resume: after deletion + suppression, mutating baseline fires exactly 1 `policy.reloaded` with `baseline-v2` and no `+overrides:` suffix.
  - [x] Subtask 2.4 — `test_recreating_override_at_runtime_does_not_auto_pickup` asserts AC-4 F33 preservation: after deletion + suppression, re-creating the override file at runtime emits ZERO additional `swap` events (suppression holds even when watchfiles does pick up the new file on Windows).

- [x] **Task 3 — Documentation amendments** (AC: 4, 6)
  - [x] Subtask 3.1 — `docs/policy-overrides.md` amended: (a) updated the audit-log events table to include `policy.user-overrides.absent_at_runtime`; (b) updated the `Hot-reload contract limitation` table row for "deleted at runtime" with the new detect-and-stop behavior; (c) added a new "Runtime delete recovery (Story 9-1.5 F35 closure)" paragraph documenting the F33 restart-required recovery path.
  - [x] Subtask 3.2 — `epic-9-run-flags.md` § F35 amended with "**RESOLVED — Story 9-1.5**" header at the top of the section (commit-hash placeholder will be substituted on actual commit).
  - [x] Subtask 3.3 — `epic-9-tranche-retro-2026-06-26.md` § 6 A2 amended: status flipped from "STORY FILED" to "✅ COMPLETED — Story 9-1.5 — 2026-06-26".
  - [x] Subtask 3.4 — Inline `# F35 closure (Story 9-1.5)` comments added at the module-level flag declaration, the suppression branch, and the absent-at-runtime emission in `policy_reload_loop`.

- [x] **Task 4 — §5.12 pre-review self-audit + MANDATORY-CR dispatch** (AC: 7)
  - [x] Subtask 4.1 — §5.12 self-audit confirmed criterion 6 fires (load-bearing-orchestrator). Arch-impossibility discharge N/A (all 7 ACs directly implementable).
  - [x] Subtask 4.2 — `9-1-5-...pre-review.md` written with §5.12 verdict + AC-vs-code drift scan + File-List-vs-git diff + 6 adversarial self-review findings (1 HIGH, 2 MEDIUM, 3 LOW) with dispositions + 11 Posture Audit sub-sections.
  - [x] Subtask 4.3 — CR dispatched under `claude-sonnet-4-6`. 6 findings (CR-F1 MEDIUM Patch + CR-F2 HIGH Patch + CR-F3 LOW Patch + CR-F4 MEDIUM Patch + CR-F5 LOW Defer + CR-F6 LOW Defer). 4/4 actionable Patches applied = **100% applied-rate**.
  - [x] Subtask 4.4 — CR-F5 + CR-F6 (real-FS integration test risk profile, pre-existing) added to `epic-9-tranche-2026-06-26-run-flags.md` "Story 9-1-5 [deferred:*] items" section.

- [x] **Task 5 — Quality gates + done-flip** (AC: all)
  - [x] Subtask 5.1 — `ruff check .` → exit 0. Green.
  - [x] Subtask 5.2 — `mypy --strict mailbot_api/` → exit 0; "Success: no issues found in 127 source files".
  - [x] Subtask 5.3 — `python scripts/check_boundaries.py` → exit 0. Green.
  - [x] Subtask 5.4 — `pytest -q` → **1381 passed, 2 skipped, 3 deselected** (baseline 1377 + 3 new delete-path tests + 1 new CR-F4 regression test = +4 net).
  - [x] Subtask 5.5 — File-List-vs-git gate: all File List entries either tracked or staged at Step 2.6.
  - [x] Subtask 5.6 — sprint-status flipped through ready-for-dev → in-progress → review → done per cadence.

## Dev Notes

**The F35 evidence trail.** Story 9-1's Phase 3.5 live walk (2026-06-13) discovered F35 by `rm`'ing the override file mid-walk to test the delete path. The watcher emitted the correct first `policy.user-overrides.swap` event with `version_after` losing the `+overrides:` suffix (per CR-F1 semantics — the swap was the SEMANTIC transition, even though the file was now nonexistent), then watchfiles continued firing ~310ms cadence change events against the nonexistent path. Each fire reached `load_policy_with_status` → returned baseline-only table with `override_status="absent"` → fell through to the `else` branch in `policy_reload_loop` → emitted `policy.reloaded`. The audit log captured ~60+ identical `policy.reloaded` events in ~20 seconds before mailbot-api was restarted manually. The root cause is upstream watchfiles behavior: the watch descriptor was bound to the file path at `awatch()` call time, and once the file's inode is freed by `unlink`, watchfiles continues observing the directory entry and registering the absence as a repeated "change."

**Why Option 1 (detect-then-stop-watching) over Option 2 (coalesce) over Option 3 (directory-watch).** From [epic-9-run-flags.md § F35](./epic-9-run-flags.md):

> Option 1 (detect-then-stop-watching) — after seeing the first `status="absent"` event when previously we had overrides, remove the override path from the watch set + emit a one-shot warning that hot-reload-from-create requires restart (matches F33's documented limitation). **Option 1 is the most surgical.**
>
> Option 2 (coalesce reloads) — track the last-emitted version + only emit `policy.reloaded` when version actually changes (deduplicates the spam at log layer; still wastes CPU on the load_policy_with_status call per fire).
>
> Option 3 (migrate to directory-watch) — watch `router/` directory instead of two specific files; detect creation + deletion + modification uniformly. Bigger refactor. **Option 3 is the architecturally correct long-term fix.**

Story 9-1.5 ships Option 1 because the surgical surface area is the right cost for the operational impact (HIGH severity but no intended-user-path triggers it). Option 3 (directory-watch refactor) is filed as a long-tail debt item for future consideration — it would also incidentally enable F33 closure (auto-pickup of recreated override file without restart), which is a real ergonomics win but not load-bearing today.

**Why detect-and-stop-watching is implemented as a flag rather than mutating the watch set.** The `watchfiles.awatch()` API does not expose a runtime watch-set mutation primitive — you'd have to cancel the current iterator + restart with a new `awatch()` call. That's a refactor of the entire `policy_reload_loop` async control flow and risks introducing new race conditions at the watcher-restart boundary. The flag-based detect-and-suppress approach keeps the existing `async for _changes in awatch(...)` loop structure intact and adds two conditional branches (one for the transition, one for the suppression). The CPU cost of the suppressed fires is negligible (`load_policy_with_status` on a 2-file path with a missing companion is dominated by the single `policy.yaml` parse + a 1-syscall `Path.exists()` check returning False; well under 1ms per fire).

**Story 9-4 OQ-3 absent-file refusal interaction.** Story 9-4's `set_model_persistent` verb already refuses-with-actionable-error when the override file is absent at verb-call time, directing the operator to the host-side bootstrap (`cp .example + docker compose restart`). Story 9-1.5's absent-at-runtime detection does NOT change this — the verb's refusal logic is independent of the watcher's transition detection. If an operator deletes the override file at runtime and then issues `/model draft_reply opus` from chat, the verb refuses (Story 9-4 OQ-3), the loop emits `policy.user-overrides.absent_at_runtime` once (Story 9-1.5 AC-1), and subsequent verb retries continue refusing until the operator restarts mailbot-api per the documented F33 contract.

**Test coverage gap that allowed F35 to escape.** Story 9-1's integration tests used `tmp_path` fixtures that NEVER delete files mid-test. Story 9-1.5's AC-5 closes this specific coverage gap. The lesson generalizes per [epic-6-5-retro-2026-06-06.md § 4.2](./epic-6-5-retro-2026-06-06.md) ("Phase 3.5 walks against the real runtime are not optional. Unit tests of Story 4-7 stayed green across the entire F28 window…") — live walks catch failure modes that unit/integration tests structurally cannot exercise. Story 9-1.5 elevates the delete-mid-test case to integration coverage, but the broader lesson (live walks are load-bearing) holds.

**§5.12 GATE-COVERAGE-ELIGIBLE NOT applicable.** Story 9-10 shipped under GATE-COVERAGE-ELIGIBLE per zero §5.12 criteria firing. Story 9-1.5 fires criterion 6 (load-bearing-orchestrator — `policy_reload_loop` is the single async loop every reload flows through; this is the canonical "load-bearing" surface). The reduced-CR pattern is the wrong call here; standard MANDATORY-CR under `claude-sonnet-4-6` is correct.

### Library Versions

| Library | Version pinned in `pyproject.toml` | Relevant behavior |
|---|---|---|
| `watchfiles` | 0.21+ | Inherits Story 9-1's verified behavior: `awatch` raises `FileNotFoundError` on watcher-start if path is missing; gracefully fires change events on subsequent file deletion + thrashes per F35. Story 9-1.5 detects the thrash and suppresses log spam. |
| `pydantic` | 2.x | No new validation surface introduced by this story; `PolicyTable` schema unchanged. |
| `pytest` / `pytest-asyncio` | per project pin | `pytest-asyncio` required for the AC-5 integration test (FastAPI lifespan + watcher async loop). |

### File List

**Modified:**

- `mailbot_api/router/policy.py` — add `_override_absent_after_applied: bool = False` module-level flag; extend `policy_reload_loop` with the detect-and-suppress branches per Task 1; add inline `# F35 closure (Story 9-1.5)` comments at the new branches.
- `docs/policy-overrides.md` — amend "Hot-reload contract limitation — file-must-exist-at-startup" section with 1-2 sentences referencing `policy.user-overrides.absent_at_runtime` event and F33 recovery path.
- `_bmad-output/implementation-artifacts/epic-9-run-flags.md` — § F35 amended with "RESOLVED — Story 9-1.5 — `<commit-hash>`" header.
- `_bmad-output/implementation-artifacts/epic-9-tranche-retro-2026-06-26.md` — § 6 A2 amended with "✅ COMPLETED — Story 9-1.5 — `<date>`" status note.
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — `9-1-5-f35-watchfiles-thrash-on-runtime-delete-detect-and-stop` row flipped through ready-for-dev → in-progress → review → done.
- `_bmad-output/implementation-artifacts/epic-9-tranche-2026-06-26-run-flags.md` — appended "Story 9-1.5 [deferred:*] items" section if any.

**New:**

- `tests/integration/test_policy_overrides_delete_at_runtime.py` — 3 tests covering AC-5 delete-path coverage gap (delete-suppression / baseline-resume-after-delete / F33-no-auto-pickup-on-recreate).

**Pre-review self-audit + CR artifact:**

- `_bmad-output/implementation-artifacts/9-1-5-f35-watchfiles-thrash-on-runtime-delete-detect-and-stop.pre-review.md` — Step 2.3.5 artifact (5-section forensic self-audit per `references/posture-audit.md`).

### Completion Notes List

- [x] AC-1 detect-and-stop branch shipped in `policy_reload_loop` with `policy.user-overrides.absent_at_runtime` WARNING emission (F33 restart-required message in log content)
- [x] AC-2 idempotent suppression verified by `test_delete_at_runtime_emits_swap_and_absent_warning_then_suppresses` (asserts ZERO `policy.reloaded` events after 2s hold post-deletion)
- [x] AC-3 baseline-edit resume verified by `test_baseline_edit_after_delete_resumes_policy_reloaded` PLUS new `test_baseline_edit_with_empty_override_present_resumes` (CR-F4 — covers the CR-F2 `override_status=="empty"` bug path)
- [x] AC-4 F33 preservation verified by `test_recreating_override_at_runtime_does_not_auto_pickup` — platform-uniform: on Windows where `ReadDirectoryChangesW` does observe recreated files, the suppression flag holds the loop in "ignore override side" mode (stronger guarantee than strict-Linux AC framing)
- [x] AC-5 4 new integration tests in `test_policy_overrides_delete_at_runtime.py` (3 original + 1 CR-F4 regression)
- [x] AC-6 F35 RESOLVED header in `epic-9-run-flags.md` + A2 COMPLETED note in `epic-9-tranche-retro-2026-06-26.md` + inline `# F35 closure (Story 9-1.5)` comments at 3 sites in `policy.py`
- [x] AC-7 MANDATORY-CR under sonnet-4-6 (§5.12 criterion 6 load-bearing-orchestrator); **4/4 actionable Patches applied = 100% applied-rate** (CR-F1 MEDIUM global-decl placement; CR-F2 HIGH `override_status in ("absent","empty")` correctness bug; CR-F3 LOW fixture symmetry; CR-F4 MEDIUM new regression test). CR-F5 + CR-F6 LOW deferred as pre-existing real-FS integration-test risk profile.
- [x] All 4 quality gates green: ruff exit 0; mypy --strict 127 source files clean; boundaries exit 0; pytest 1381 passed + 2 skipped + 3 deselected (+4 net vs baseline 1377)
- [x] sprint-status row flipped to done

## Completion Notes

### 2026-06-26 — autonomous-story-run shipped (Adam, /autonomous-story-run 9-1-5)

F35 HIGH closed via Option 1 (detect-and-stop-watching). New `_override_absent_after_applied: bool` module flag in `mailbot_api/router/policy.py` is armed on the first `prev_had_overrides AND NOT new_has_overrides AND override_status=="absent"` transition inside `policy_reload_loop`; subsequent watchfiles fires are silently coalesced until either (a) operator restarts mailbot-api (process restart clears the flag) OR (b) the baseline `policy.yaml` is edited (AC-3 resume — fires `_override_absent_after_applied = False` and falls through to standard `policy.reloaded` emission). The absent-at-runtime transition fires the existing `policy.user-overrides.swap` event UNCHANGED followed by a new `policy.user-overrides.absent_at_runtime` WARNING with the F33 restart-required message in the log content.

**Dev-time scope extension caught by self-audit:** the original AC-4 framing assumed strict-Linux F33 semantics (watcher cannot observe recreated files). On Windows where `ReadDirectoryChangesW` DOES observe the recreated file, the suppression flag holds the loop in "ignore override side" mode uniformly, preserving AC-4 semantics across platforms. The self-audit caught this as a platform-uniform extension (stronger guarantee than original AC).

**CR pass under sonnet-4-6:** 6 findings (CR-F1 MEDIUM Patch + CR-F2 HIGH Patch + CR-F3 LOW Patch + CR-F4 MEDIUM Patch + CR-F5 LOW Defer + CR-F6 LOW Defer). **4/4 actionable Patches applied = 100% applied-rate**. The HIGH CR-F2 caught a real correctness bug: my original AC-3 resume condition only fired on `override_status == "absent"`, but `load_policy_with_status` returns `"empty"` (not `"absent"`) when an operator creates an empty override file (zero-byte, `tasks: {}`, or all-None entries). Without the broadening, a simultaneous create-empty-override + edit-baseline would have silently dropped the baseline edit. Fixed via `override_status in ("absent", "empty")` plus the new `test_baseline_edit_with_empty_override_present_resumes` regression test (CR-F4) covering that exact path.

**+4 net tests at 1381+2-skipped+3-deselected vs baseline 1377+2+3.** 4 gates green at done-flip.

### Dev Agent Record

**Agent Model Used:** claude-opus-4-7 (Adam's session)

**File List:**
- `mailbot_api/router/policy.py` (modified — F35 detect-and-stop branch, 3 inline `# F35 closure (Story 9-1.5)` comments, new `_override_absent_after_applied` flag + `_reset_override_absent_flag_for_test` helper, updated `__all__`)
- `tests/integration/test_policy_overrides_delete_at_runtime.py` (NEW — 4 integration tests covering AC-1+2, AC-3, AC-3 CR-F4 empty-override, AC-4)
- `docs/policy-overrides.md` (modified — added `policy.user-overrides.absent_at_runtime` to audit-log events table; updated runtime-deletion row in Hot-reload contract limitation table; added new "Runtime delete recovery (Story 9-1.5 F35 closure)" paragraph)
- `_bmad-output/implementation-artifacts/epic-9-run-flags.md` (modified — § F35 marked RESOLVED)
- `_bmad-output/implementation-artifacts/epic-9-tranche-retro-2026-06-26.md` (modified — § 6 A2 marked ✅ COMPLETED)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified — story row flipped to done)
- `_bmad-output/implementation-artifacts/9-1-5-f35-watchfiles-thrash-on-runtime-delete-detect-and-stop.md` (modified — completion notes appended; status → done)
- `_bmad-output/implementation-artifacts/9-1-5-f35-watchfiles-thrash-on-runtime-delete-detect-and-stop.pre-review.md` (NEW — pre-review self-audit artifact)

**Debug Log:**
- RED phase: 3 new tests failed correctly because `policy.user-overrides.absent_at_runtime` event was never emitted.
- GREEN phase round 1: 2/3 tests passed; AC-4 test exposed cross-platform watcher behavior — on Windows the recreated file IS observed by the watcher. Scope-extended the suppression flag to cover `override_status == "applied"` re-creation fires (stronger AC-4 guarantee). All 3 tests pass after round 2.
- CR-F2 HIGH was a real correctness bug — caught by sonnet-4-6 review; fixed via `override_status in ("absent", "empty")` broadening + regression test.

## Change Log

| Date | Author | Change |
|---|---|---|
| 2026-06-26 | Amelia | Story filed during Epic 9 `/model` surface tranche retrospective (A2 action item). |

## Open Questions / Architectural Decisions

None — all design decisions are pre-resolved by the F35 run-flags Option 1 recommendation and the §5.12 cadence binding. If the CR subagent surfaces a structural concern (e.g., the flag-based suppression has an unobvious race condition under high baseline-edit frequency), it lands as a CR-F finding and gets applied or deferred per the cadence v2 binding.

### Review Findings

- [x] \[Review]\[Patch] CR-F1 (MEDIUM): `global _override_absent_after_applied` declared inside `async for` loop body — move to function-top for clarity and symmetry with `set_policy_snapshot`'s `global _policy` pattern \[`mailbot_api/router/policy.py:786`] — **APPLIED**: declaration moved to `policy_reload_loop` function-top with CR-F1 explanatory comment.
- [x] \[Review]\[Patch] CR-F2 (HIGH): AC-3 resume condition `override_status == "absent"` is too narrow — if an operator creates an empty override file AND edits the baseline simultaneously, `load_policy_with_status` returns `"empty"` not `"absent"`, so `baseline_changed` evaluates to `False`, the suppression flag stays armed, and the real baseline change is silently dropped; fix to `override_status in ("absent", "empty")` \[`mailbot_api/router/policy.py:789-791`] — **APPLIED**: broadened to `override_status in ("absent", "empty")` with CR-F2 explanatory comment referencing Story 9-1 CR-F3 (both shapes operationally indistinguishable for +overrides: suffix surface).
- [x] \[Review]\[Patch] CR-F3 (LOW): `_reset_policy_module` fixture in new test file only calls `_reset_override_absent_flag_for_test()` in pre-yield setup but does NOT call `_reset_policy_snapshot_for_test()` — add pre-yield snapshot reset for symmetry and to prevent stale-snapshot contamination if test ordering changes \[`tests/integration/test_policy_overrides_delete_at_runtime.py:83-91`] — **APPLIED**: pre-yield setup now resets both the snapshot and the suppression flag for symmetry with post-yield teardown.
- [x] \[Review]\[Patch] CR-F4 (MEDIUM): No integration test exercises the AC-3 resume path when `override_status == "empty"` (the CR-F2 bug path); after CR-F2 fix, add `test_baseline_edit_after_delete_with_empty_override_present_resumes` verifying that baseline-change + empty-file-present correctly resumes `policy.reloaded` emission and clears the suppression flag \[`tests/integration/test_policy_overrides_delete_at_runtime.py`] — **APPLIED**: new test `test_baseline_edit_with_empty_override_present_resumes` added covering the CR-F2 bug path; passes.
- [x] \[Review]\[Defer] CR-F5 (LOW): `test_baseline_edit_after_delete_resumes_policy_reloaded` asserts exactly `len(reloaded_events) == 1` after 0.5s hold, but some CI filesystem backends fire double-write events on a single file write — platforms where watchfiles delivers two fires for one `write_text` call would cause a spurious test failure; the existing Story 9-1 baseline tests use `>= 1` for this reason \[`tests/integration/test_policy_overrides_delete_at_runtime.py:233`] — deferred, pre-existing risk profile of real-FS integration tests
- [x] \[Review]\[Defer] CR-F6 (LOW): `test_recreating_override_at_runtime_does_not_auto_pickup` asserts `len(swap_events) == 0` after a 2-second hold window but does not recheck the assertion after `stop_event.set()` — any late-arriving watchfiles event between the assertion and teardown is invisible to the test; not a production defect but a test-coverage blind-spot \[`tests/integration/test_policy_overrides_delete_at_runtime.py:294-303`] — deferred, pre-existing risk profile of real-FS integration tests
