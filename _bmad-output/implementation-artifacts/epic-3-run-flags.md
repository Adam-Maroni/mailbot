# Epic-3 Run Flags

**Epic:** Epic 3 — Ingest Pipeline
**Status:** COMPLETE (originally 2026-06-01; retroactive CR pass 2026-06-02)
**Originating run:** `epic-run-flags.md` (shared appended file — superseded by this per-epic file per Epic 3 retro action #4)

This file consolidates the Epic 3 sections of the prior shared `epic-run-flags.md` into a dedicated per-epic file, matching the per-epic convention `epic-2-run-flags.md` + `epic-4-run-flags.md` already follow. Closes the inconsistency flagged in Epic 3 retro action #4.

---

## Summary

- All 8 Epic 3 stories shipped 2026-06-01; sprint-status `epic-3: done` since same date.
- CR subagent invoked on **Stories 3-1 + 3-2** (boundary-introducing + prompt-foundation surfaces). Stories 3-3 through 3-8 ran gate-coverage-only.
- CR cadence v2 (Epic 3 retro action #1, then re-decided in Epic 4 retro action #1 as **Option A — structural**) identified **Story 3-3 (privacy-invariant)** and **Story 3-5 (load-bearing-orchestrator)** as MUST-CR surfaces that had not received CR. Stories 3-4, 3-6, 3-7, 3-8 stayed eligible for gate-coverage-only.

## Retroactive Code Review — 2026-06-02

Per Epic 4 retro action item #2 (Adam, 2026-06-02): retroactive CR pass dispatched on **Stories 3-3 and 3-5** to pay down the second-pair-of-eyes debt before Epic 5 work depends on these surfaces.

### Story 3-3 — Sensitivity classifier + patterns + Router precondition (privacy invariant)

- **Reviewer:** claude-sonnet-4-6 via Agent dispatch
- **Verdict:** NOTABLE — 9 findings, 8 applied (89%)
- **HIGH:** CR-3-3-1 (force_sensitive early-exit bug), CR-3-3-2/3 (missing test_classifier.py file + assert_qwen_only coverage)
- **MEDIUM:** CR-3-3-4 (confidence-floor boundary tests), CR-3-3-5 (router.py:341 inline timestamp; missed by Epic 4 sub-second `ts` migration), CR-3-3-6 (KeyError on unknown sensitivity label), CR-3-3-7 (degraded-mode + sensitivity-gate interaction untested — accepted-no-change)
- **LOW:** CR-3-3-8 (signature divergence from AC-3 — doc-comment added), CR-3-3-9 (regex scope undocumented in YAML — comment added)
- Story file § Retroactive Code Review captures full disposition.

### Story 3-5 — Pipeline ordering enforcement (load-bearing orchestrator)

- **Reviewer:** claude-sonnet-4-6 via Agent dispatch
- **Verdict:** NOTABLE — 9 findings, 8 applied (89%)
- **HIGH:** CR-3-5-1 (coarse_class sensitivity-block misattributes fine_class), CR-3-5-2 (missing test_pipeline.py file)
- **MEDIUM:** CR-3-5-3 (silent skip on missing body row mid-override), CR-3-5-4 (`= []` → `Field(default_factory=list)`), CR-3-5-5 (retryable error propagation — Adam chose option a), CR-3-5-6 (sensitive-email integration test missing DB-level assertion)
- **LOW:** CR-3-5-7 (CLI missing assert_qwen_only call), CR-3-5-8 (missing embedding policy — Adam chose option a hard-fail), CR-3-5-9 (sensitivity-step-failure scenario — deferred, logically covered)
- Story file § Retroactive Code Review captures full disposition.

### Gates after retroactive CR

- pytest: 625 → 646 (+21 net new tests across both retroactive passes)
- ruff: clean
- mypy --strict: clean across 85 source files
- boundary checker: clean

### Status

Both Story 3-3 and Story 3-5 are now **CR-cleared**. The privacy-invariant + load-bearing-orchestrator surfaces have received the second pair of eyes that the original ship deferred.

---

## Carryover items NOT addressed by retroactive CR

These items remain open from the original Epic 3 ship and are tracked against future stories:

- **`docs/DATABASE.md`** — Epic 3 retro action #8; 17 migrations across 4 epics now; still not shipped. Owed before Epic 5 Story 5-2.
- **Architecture.md doc-debt** — 4 paragraphs owed (AR-SCHEMA-2, migration-numbering policy, AR-PAT-N writer-monopoly, AR-AUTH-N tier-enforcement defense-in-depth). Owed before Epic 5 Story 5-2.
- **Hermes-aux cache double-wrap latent bug** — Story 3-2 CR-8; non-triggerable today; guard test owed before Epic 5 Story 5-3.
- **Story 3-5 `run_batch` enrichment wiring deferred** — TODO comment in run_batch; Epic 6 scheduler story will wire `enrich_sender` + `enrich_thread` per Epic 3 retro action #9.
- **Story 3-8 hardening pass** — Epic 3 retro action #11; rederive CLI still at 9 tests; deferred decision.

---

## Files staged by this retroactive CR pass

**Production:**

- `mailbot_api/sensitivity/patterns.py` (CR-3-3-1, CR-3-3-6, CR-3-3-8)
- `mailbot_api/router/router.py` (CR-3-3-5)
- `router/sensitivity_patterns.yaml` (CR-3-3-9)
- `mailbot_api/ingest/pipeline.py` (CR-3-5-1, CR-3-5-3, CR-3-5-4, CR-3-5-5, CR-3-5-7, CR-3-5-8)

**Tests:**

- `tests/unit/sensitivity/test_classifier.py` (new — CR-3-3-2/3/4; 10 tests)
- `tests/unit/ingest/test_pipeline.py` (new — CR-3-5-2; 11 tests)
- `tests/integration/test_pipeline_e2e.py` (CR-3-5-6 — 4-line assertion strengthening)

**Workflow state:**

- `_bmad-output/implementation-artifacts/3-3-...md` (retro CR section appended)
- `_bmad-output/implementation-artifacts/3-5-...md` (retro CR section appended)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (story rows + last_updated)
- `_bmad-output/implementation-artifacts/epic-3-run-flags.md` (this file — closes Epic 3 retro action #4)
