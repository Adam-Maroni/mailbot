---
baseline_commit: TBD
---

# Story 6.11: Ingest pipeline `sensitivity_class` provider_error investigation — F17 closure

Status: backlog

> **Filed 2026-06-04** during Story 6-6.5 Section B prereq fulfillment. The Section B walk (CP-A/B/C/D live Discord ↔ Outlook ↔ Anthropic round-trip) attempted to seed a `confidential`-classified fixture email and discovered that classification has been broken since 2026-06-01 21:02 UTC — 1618 emails sitting unclassified, every `sensitivity_class` ingest tick failing with bare `error_code=provider_error` (no underlying message field). This story is a **surgical investigation + fix** — NOT a sprawling refactor. See [`epic-6-run-flags.md § F17`](./epic-6-run-flags.md#f17--ingest-pipeline-sensitivity_class-step-stuck-on-provider_error-3-day-backlog-of-1618-emails--new-finding-2026-06-04) for the full finding.

## Story

As the MailBot system,
I want the ingest pipeline's `sensitivity_class` step to successfully dispatch to the Router and write classification results to the `emails.sensitivity` column,
So that the 1618-email unclassified backlog drains, Story 6-6.5's Section B walk (CP-A/B/C) becomes unblocked, and the privacy-defending sensitivity gate (Story 3-3 + Story 4-7) actually fires against incoming mail.

## Acceptance Criteria

**Given** the ingest pipeline runs its 5-minute interval task,
**When** the next batch of unclassified emails is picked up,
**Then** at least one row reaches the Router (visible as a new `router_calls` row with `task_type='sensitivity_class'` and `ts > 2026-06-01T21:02:22Z`),
**And** the row's `outcome` is `ok` or `retry_recovered` (NOT `failed`),
**And** the corresponding `emails.sensitivity` + `emails.sensitivity_at` cells are populated post-tick.

**Given** the root cause is identified,
**When** the fix lands,
**Then** the fix is accompanied by a regression test in `tests/integration/test_ingest_pipeline_*.py` (or wherever Story 3-5/3-6's tests live) that would have caught the failure mode (likely shape: assert `process_email` produces a Router call for `sensitivity_class` against a real `ModelAdapter` boundary, NOT a mocked Router).

**Given** the 1618-email backlog,
**When** the fix is deployed,
**Then** the ingest pipeline drains the backlog at its configured backpressure-throttled cadence,
**And** `/admin/status` reports `ingest.unprocessed_count` dropping over successive ticks,
**And** `ingest.backpressure_active` eventually flips to `false` once the queue is drained.

**Given** Story 6-6.5 Section B is gated on this fix,
**When** 6-11 closes,
**Then** Story 6-6.5's `epic-6-run-flags.md § Story 6-6.5 walk record § Section B` is updated to remove the BLOCKED state on CP-A/B/C and the re-walk proceeds.

## Investigation Plan (Dev Notes)

**Triage order — most likely cause first:**

1. **SecretMissing at the verb boundary** (most likely per `mailbot_api/config.py:18` contract). Hypothesis: a `get_secret_required(...)` call inside the sensitivity_class code path is raising `SecretMissing` which `RouterError`-wraps to `code="provider_error"`. The classifier path in `mailbot_api/sensitivity/classifier.py` (or its callers in `mailbot_api/ingest/pipeline.py`) reads an env var that no other Router path reads. Investigation steps:
   - Add temporary debug logging at the verb boundary (e.g., `mailbot_api/router/router.py` or wherever `RouterError(code="provider_error", message="secret missing: <name>")` is constructed) to surface the actual `<name>` in the log line. The current ingest log redacts the message field.
   - Re-run an ingest tick and check the log for the unmasked secret name.
   - Cross-reference against `.env` to find the missing key. Likely candidates: a sensitivity-pattern-related config, a model-name override env var (`SENSITIVITY_CLASS_MODEL=...`?), or a feature flag that was added in a recent story but never documented in Story 4-0's credential rubric.
   - Remove the temporary debug logging once root cause is identified (it logs a secret name, which is itself a redaction-class signal under NFR-SEC-4 — temporary only).

2. **Adapter dispatch table gap or model lookup**. Hypothesis: somewhere between Story 6-0 (Hermes runtime corrective, 2026-06-02) and the next attempted classification, a regression removed `sensitivity_class` from the adapter dispatch table or the Qwen adapter rejects the prompt module's request shape. Counter-evidence: the 4 successful 2026-06-01 calls used `qwen2.5:3b-instruct-q4_K_M` (same model still loaded in Ollama today per `/api/tags`). Investigation steps:
   - `git log --since=2026-06-02 --until=2026-06-03 -- mailbot_api/router/ mailbot_api/sensitivity/ mailbot_api/ingest/ mailbot_api/prompts/sensitivity_class/` to spot the regression window.
   - Inspect any policy.yaml change that might have orphaned the `sensitivity_class` task type from its model binding.

3. **Prompt-module version mismatch**. Hypothesis: `mailbot_api/prompts/sensitivity_class/v1.py` was bumped to v2 somewhere without a corresponding `prompt_version` migration, and the Router rejects requests whose `prompt_version` doesn't match the registered set. Investigation steps:
   - Check `prompts/sensitivity_class/__init__.py` for the currently-registered version.
   - Check `router_calls` historical rows for `prompt_version` — did it shift on 2026-06-01 to a value that's no longer valid?

**What this story does NOT include:**
- Backlog re-classification beyond what the natural ingest tick drains. If a manual `mailbot ingest --backfill` CLI is needed for the 1618-email backlog, file it as Story 6-12.
- Story 6-6.5 Section B re-walk. That's a separate re-invocation of Story 6-6.5 (or a manual Adam walk) AFTER this story closes.
- Refactors of the broader Router error-as-data shape. NFR-SEC-4's redacted-secret-name contract stays — this story's debug logging is temporary.

## Tasks / Subtasks

- [ ] **Task 1: Reproduce the failure locally and surface the unredacted error.**
  - [ ] Stack up if not running.
  - [ ] Confirm `ingest.unprocessed_count > 0` via `/admin/status`.
  - [ ] Add temporary debug log at the `RouterError(code="provider_error", ...)` construction site to surface the underlying exception's `repr(exc)`.
  - [ ] Run an ingest tick (wait 5 min or call `run_drain_loop(max_batches=1)` directly via `docker exec`).
  - [ ] Capture the unredacted error message.
- [ ] **Task 2: Root cause analysis.**
  - [ ] Map the message to one of the 3 hypotheses (or document a 4th if surfaced).
  - [ ] Identify the specific code path / config / env var causing the failure.
  - [ ] If env-var gap: document the missing key + add it to `.env` (do NOT commit) + update Story 4-0's credential rubric to include it (Epic 6 retro A6 amendment continues).
- [ ] **Task 3: Code fix + regression test.**
  - [ ] Apply the minimal code change to close the root cause.
  - [ ] Add an integration test exercising the `sensitivity_class` path against a real-adapter `ModelAdapter` boundary per Step 2.4.7 Middleware-Real-Bootstrap rule.
  - [ ] Remove the temporary debug logging from Task 1.
- [ ] **Task 4: Backlog drain verification.**
  - [ ] Confirm next ingest tick produces `router_calls` rows for `sensitivity_class`.
  - [ ] Tail `/admin/status` over 30 min — `unprocessed_count` should be dropping.
  - [ ] Once drained (or substantially drained), report final classification distribution (normal / sensitive / confidential counts).
- [ ] **Task 5: Unblock Story 6-6.5 Section B.**
  - [ ] Update `epic-6-run-flags.md § Story 6-6.5 walk record § Section B`: change CP-A/B/C from BLOCKED to QUEUED.
  - [ ] Update sprint-status.yaml row for 6-6.5 noting the unblock.
  - [ ] Update F17 finding status from OPEN to RESOLVED.

## Dev Agent Record

### Agent Model Used

TBD (next dev session).

### Debug Log References

TBD.

### Completion Notes List

TBD.

### File List

TBD.

### Change Log

- 2026-06-04 — Story 6-11 filed as F17 carry-forward from Story 6-6.5 Section B prereq seeding. Status: backlog.
