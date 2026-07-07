# Epic 10.5 — Run Flags

Per-story flags raised during autonomous / dev runs of Epic 10.5.

## Story 10-5-1 — 2026-07-07 (autonomous-story-run dev pass)

**Dev model:** claude-opus-4-8[1m] · **Review model:** claude-sonnet-5 (pending Task 6 MANDATORY-CR)

### Task 5 HALT (Adam-hands-on live walk) — INFO

Per the story's Run-mode binding, Tasks 1–4 (code + unit/integration tests) are
dev-story/autonomous-story-run compatible and are COMPLETE. **Task 5's live
validation walk is Adam-hands-on** and was NOT executed autonomously:

- **Live pause→propose/queue→wait ≥1 drainer tick→assert-not-applied** against
  the sacrificial folder `MailBot-UAT-10-1` (the F4 CRITICAL live proof; the
  259ms-after-propose scenario must be non-reproducible).
- **Live pause→resume-from-Discord-chat**, asserting resume succeeds through the
  chat surface (F1 + F-10-5-4 proof).

$0 expected (local stack, move verbs are $0, no Opus). Evidence, when walked,
lands in `10-5-1-walk-evidence.md`. The autonomous run substituted a
**two-instance integration test** (`test_worker_drainer_wiring.py::
test_cross_process_pause_stops_worker_drainer_dispatch`) that proves a DB-only
pause (no worker `initialize`) stops a REAL `OutlookGraphWriteAdapter` drain
loop — the offline analog of the AC-1 live assertion.

### Scope refinement flag — INFO (not a defect)

Story Task 2 listed five degraded-flag consumers to make authoritative:
`router.py` (×2 dispatch gates), `router_control.py:inspect_policy`,
`budget_admin.py:reset_degraded_mode`, `cost.py:cost_breakdown`. During dev the
last three were identified as **status-REPORT surfaces that govern no mailbox
write**. Making their degraded read fail-closed (the safe direction for a
dispatch gate) would make them **falsely report "degraded/Active" on a transient
DB-read error** — worse for the operator than a momentarily-stale mirror. AC-2's
text scopes the fix to "a decision that governs mailbox writes or dispatch," so
the authoritative read was applied to the two router DISPATCH gates only; the
three report consumers keep the in-memory `is_degraded()`. Surfaced here for the
reviewer to confirm the interpretation.

### MANDATORY-CR outcome (sonnet-5 ≠ dev opus-4-8) — INFO

Reviewer ran 3 layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor).
**1 Decision + 3 Patches + 7 Defers.** All 4 actionable items APPLIED (100%),
converged in ONE round:

- **Decision (APPLIED):** `dispatch_embedding` — the THIRD pause-enforcement
  site the story's Dev Notes named — was left on the stale `is_paused()` mirror
  (a real same-class gap, undisclosed). Fixed: migrated to authoritative
  `is_paused_now` + `pause_gate:refused` audit row. Regression test added.
- **Patch (APPLIED):** `reason_now` silently swallowed exceptions → now logs
  via the shared `snapshot_now`.
- **Patch (APPLIED):** paused-refusal test now asserts the full zero-cost row
  shape (outcome/cost/tokens), verifying the no-spend-pollution claim.
- **Patch (APPLIED):** `is_paused_now`+`reason_now` non-atomic pair collapsed
  into a single-read `snapshot_now` → closes the CR-13 (paused,reason)
  inconsistency window; drainer reads once per gate.
- **7 Defers (documented):** DRY duplicate audit helpers; two allowlists with
  no shared invariant; TOCTOU-narrow re-check gaps on the permit branches;
  broad `except Exception` in the deliberate fail-closed path; `_tool_name`
  malformed-dict edge (fail-safe direction already correct); per-row mid-tick
  read at batch-25 (negligible). None are correctness bugs in this diff.

### Gate results (post-CR)

- ruff (mailbot_api/tests/scripts): clean. Pre-existing `scratch/` T201s
  (untracked, out of scope) unchanged.
- mypy --strict: clean (129 files).
- check_boundaries.py: clean (paused-refusal audit rows use the Rule-C
  `record_router_call` writer; no new raw SQL).
- pytest: **1727 passed, 2 skipped, 3 deselected** (+19 net vs 1708 baseline).

### Task 5 LIVE WALK EXECUTED (Adam co-walk, 2026-07-07) — 1 live defect fixed + 1 new finding filed

Full evidence: `10-5-1-walk-evidence.md` §B. Real stack + real Graph mailbox +
real Discord. AC-1 **PASS** (Adam-confirmed both halves in Outlook: paused move
held, resume released it — F4 non-reproducible live). AC-3 chat-reachable
**PASS**. AC-3 resume-from-Discord **PARTIAL** — see below.

- **F-10-5-1-W1 (HIGH) — FIXED IN-SESSION (in scope, dev defect).** The
  `_PAUSE_ALLOWED_TOOLS` allowlist matched bare verb names, but Hermes exposes
  MCP tools namespaced (`mcp_mailbot_api_resume_router`). In production the gate
  filtered out EVERY tool (`allowed_count: 0`), so the resume control path was
  unreachable from chat — F-10-5-4 re-opened from a new angle. All unit tests
  missed it (bare names). Fix: `_tool_on_pause_allowlist()` suffix-matches the
  namespaced form + new regression test. Live-verified: `allowed_count` 0→12,
  write verbs still filtered. This was a real hole in the AC-3 fix that ONLY the
  live walk could surface.

- **F-10-5-1-W2 (HIGH) — FILED per N.5 (OUT OF SCOPE — Hermes MCP transport).**
  After the W1 fix, the agent really invoked `mcp_mailbot_api_resume_router`,
  but the Hermes↔mailbot-api MCP streamable-HTTP session drops the call before
  it reaches the verb (`Session termination failed: 404`; `MCP call timed out
  after 30.0s`; `Session terminated`). Server side logged NO resume_router
  execution — the request never arrived. **Isolation proof:** direct
  `resume_router(db_path=…)` returned `ok=True` + flipped `paused=0` — OUR verb
  works; the failure is purely the Hermes MCP transport layer. Pre-existing
  Hermes-side defect surfaced by the walk; belongs to a Hermes-transport story,
  NOT 10-5-1's router-pause-gate scope. Needs its own story (Cluster C/transport
  or a dedicated Hermes-MCP-session finding).

- **F5/F6 residue (NOT new):** the sacrificial email's local row is soft-deleted
  after the move-out + manual drag-back (move-out synced as `@removed`; EMAIL_
  UPSERT doesn't resurrect). Documented Epic 10 finding; repair is story 10-5-4
  (Cluster D). Physical email safe in Inbox; pause/degraded restored to 0/0.

### Story disposition

Story stays in **review** (NOT done): Tasks 1–4 dev-complete + MANDATORY-CR
converged + live walk executed. AC-1/AC-2/AC-3(F1)/AC-4/AC-5/AC-6 = **PASS**;
AC-3 resume-from-Discord = **PARTIAL** (router fix proven; blocked only by the
out-of-scope Hermes-transport defect F-10-5-1-W2). Done requires Adam-signed AC
verdicts + a disposition on whether the AC-3 PARTIAL (router side fully fixed,
external transport blocker filed) is sign-off-acceptable or blocks done.
Nothing committed — staged only.
