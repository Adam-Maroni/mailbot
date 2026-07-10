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

## Story 10-5-2 — 2026-07-10 (autonomous-story-run dev pass)

**Dev model:** claude-opus-4-8[1m] · **Review model:** claude-sonnet-5 (MANDATORY-CR complete)

### Run-mode: HYBRID (Tasks 1-4+6+7 autonomous; Task 5 Adam-hands-on HALT)

Cluster B security-adjacent dev story (authorization below the persona). The
story file was authored inline (backlog → ready-for-dev) from epics.md § Story
10.5.2 + retro §8.5 (B7 envelope design) + a full code-seam map (2 Explore
agents). Baseline_commit 5b36987; baseline suite 1728+2+3.

### What shipped (Tasks 1-4 + 7, dev-codeable)

- **AC-1 (F-10-5-5/F-10-5-8) — API-layer user-confirmation primitive.** New
  `user_confirmations` table (migration 026) + `actions/user_confirmation.py`.
  `mint_sensitivity_token` + `mint_grant` now refuse `NEEDS_USER_CONFIRMATION`
  unless a genuine user-gated confirmation exists — created ONLY at the
  `/v1/chat/completions` boundary from a real user-role message, consumed
  single-use. An agent that only issues MCP verb calls cannot manufacture the
  record, so it cannot self-authorize.
- **AC-3 (F-10-5-6) — structured sensitivity-refusal envelope.** `SensitivityRefusal`
  on `RouterError.refusal_envelope`, populated at all router refusal sites;
  `/v1/chat/completions` renders sensitivity refusals as graceful 200 four-beat
  messages instead of HTTP-502; the Graph email id is structurally unprintable
  (`email_ref` is a one-way hash — not a field on the envelope). Three message
  shapes pinned (sensitive offers escalate / confidential none / not-classified
  never suggests rederive).
- **AC-4 (F-10-5-7) — session-independent escalation handshake (code portion).**
  `pending_sensitive_refusal` keyed on caller_origin (NOT a session id — that
  divergence WAS the bug); confirm→single-use confirmation→mint succeeds;
  no-brick (per-request errors-as-data). Live end-to-end walk is Task 5.

### MANDATORY-CR outcome (sonnet-5 ≠ opus-4-8) — 7 Patches applied = 100%

Three parallel adversarial layers. **7 Patches + 1 Decision + 5 Defers + 1 Dismiss.**
All 7 actionable Patches APPLIED in one round:

- **CR-3 (the big one) — grant confirmation had ZERO production callers → every
  Tier-2 grant was permanently blocked** (a functional regression beyond AC-1's
  "user-gated" intent). Fixed: new `pending_grant_approval` table + boundary
  handshake (`_record_pending_grant_approvals_from_messages` scans the
  transcript's `propose_action(<grant-requiring>)` tool calls; a user
  "yes"/"approve" phrase confirms via `confirm_pending_grant`). Grants are now
  user-gated, not user-impossible.
- **CR-4 — grant confirmation is now email-scoped** (`(action_type, canonical
  sorted email_ids)`), so a user "yes" to {e1,e2} does not authorize a mint for
  {e1,e3}. Blast radius = the user-approved set, not agent-chosen.
- **CR-1/CR-2 — `ask_router` + both `NEEDS_SENSITIVITY_CONFIRMATION` branches now
  record the pending refusal** (parity with dispatch_tool_call), so the
  "yes, escalate" offer is genuine on every path that renders it.
- **CR-6 — atomic `DELETE ... RETURNING` claims** for both handshakes so two
  concurrent "yes" turns can't both mint from one user approval.
- **CR-7 — refused-mint paths now emit a structured audit event.**
- **CR-5 — documented as intentional last-refusal semantics.**

### DECISION deferred to Task 5 (Adam) — CR-8: caller_origin trust boundary

`caller_origin` (from the unauthenticated `X-Mailbot-Caller-Origin` header) is
now a security-relevant correlation key. **Adam decision owed at the Task 5 live
walk:** is the header stamped by the internal Hermes→mailbot-api proxy (trusted,
not client-settable in the real topology) or does it need a stronger identity
source? Fail-safe worst case: a mis-set header lets a caller consume their own
colliding default `unknown-external` pending row — never over-authorization
beyond a single user-approved (email,task) or (action,email-set).

### Deferred findings (5, filed not fixed) — INFO

Multi-row `_consume` TOCTOU (low likelihood); escalation phrase punctuation edge
(partially addressed — `_normalize_phrase` now strips `?"'`); `id(raw_request)`
completion id (pre-existing pattern); non-tools path no stream branch
(pre-existing); `RouterError.message` id interpolation on
SENSITIVITY_NOT_CLASSIFIED (pre-existing at baseline 5b36987, NOT user-reachable
— the render only ever surfaces `user_facing_guidance`, never `.message`;
flagged for a future id-safety sweep of internal error strings).

### AC-2 (F-10-5-12) — BOUNDARY-HONEST, code-side N/A — WARNING

The skill-file self-edit vector is entirely Hermes-side (`file`/`skills` write
toolsets on the RW bind-mount `hermes-config/skills/mailbot/**`). `mailbot_api/`
has NO file-write verb over skill files. AC-2 is satisfied by a Hermes
`config.yaml` toolset restriction and/or `:ro` bind-mount — authored + live-verified
at Task 5. A `mailbot_api`-side "fix" was deliberately NOT fabricated (that would
reproduce the persona-prose-pretending-to-be-enforcement failure this epic
exists to end).

### Gate results (post-CR)

- ruff (mailbot_api/tests): clean. Pre-existing untracked `scratch/` T201s unchanged.
- mypy --strict: clean (131 files, +2 new modules).
- check_boundaries.py: clean (audit rows are structured logs; no new raw SQL outside queries.py).
- pytest: **1775 passed, 2 skipped, 3 deselected** (+47 net vs 1728 baseline).

### Task 5 HALT (Adam-hands-on) — INFO

NOT executed autonomously. Two live clauses:
1. **AC-2 live:** author the Hermes skill-file hardening (config.yaml toolset
   restriction and/or `:ro` bind-mount) → Adam verifies a `skill_manage patch` /
   `write_file` against `hermes-config/skills/mailbot/SKILL.md` is REJECTED.
2. **AC-4 live:** real stack + real Discord + one real sensitive email →
   four-beat refusal renders → Adam replies "yes, escalate" → confirmation
   recorded → token attaches → draft/summary dispatches (small real Opus spend,
   Console-sourced) → confirm NO session brick. Evidence → 10-5-2-walk-evidence.md.
Plus the CR-8 caller_origin trust-boundary decision.

### Self-driven manual verification (2026-07-10, orchestrator) — AC-1/AC-3/AC-4-code PASS

Adam directed "run manual verification yourself." Drove the real production code
paths (real migrated DB + real router + real `/v1/chat/completions` via
TestClient), not mocks:
- **AC-1 PASS** — self-mint sensitivity/grant → NEEDS_USER_CONFIRMATION;
  user-confirmed mint succeeds once (single-use); grant-approval handshake mints;
  CR-4 email-scoping holds ({e1,e2} approval ≠ {e1,e3} authorization).
- **AC-3 PASS** — all 3 classes render graceful 200 (not 502), correct four-beat
  shapes, Graph id never in body.
- **AC-4 code PASS** — sensitive refusal records pending refusal → "yes, escalate"
  boundary turn records real single-use confirmation for the exact email → mint
  unlocks (session-independent) → later normal turn NOT refused (no session brick).

### Live-stack rebuild + live AC-3 verification (2026-07-10, orchestrator)

Adam directed "rebuild the mailbot-api image so a subsequent live walk tests the
new code." Executed:
- **MIGRATION-IDEMPOTENCY FINDING (F-10-5-2-DEV1, filed):** the live DB had
  `_migrations` recording `026_user_confirmations.sql` applied at 07:40:33Z — an
  EARLY version (only `user_confirmations`), because the dev bind-mount +
  UVICORN_RELOAD hot-reloaded and applied 026 before the CR-fix pass added
  `pending_sensitive_refusal` + `pending_grant_approval` to the same file. The
  runner is filename-keyed, so it would NOT re-apply the changed file → the two
  correlation tables were silently missing from the live DB. Root cause: editing
  a migration file after it's been recorded-applied. Remediation applied: ran the
  current (idempotent, `CREATE TABLE IF NOT EXISTS`) 026 SQL against the live DB —
  all 3 tables now present, existing `user_confirmations` untouched. **Process
  note for the epic:** never edit a migration after first apply; a new story
  touching an existing-DB migration should ship a NEW migration prefix. (This bit
  only because dev hot-reload applied a mid-flight version; a clean deploy from
  the final file would have been correct.)
- **Rebuild:** `docker compose build mailbot-api` → new image
  `ed18774792db`; `docker compose up -d --force-recreate mailbot-api` → healthy,
  clean lifespan boot (policy + patterns + adapters + MCP 25 tools; no tracebacks).
- **LIVE AC-3 verified** against the running container's real
  `/v1/chat/completions` with a REAL confidential email from the live DB: HTTP
  **200** (not 502), rendered the four-beat confidential message (🔒 … "Read it
  directly in Outlook"), **Graph id NOT leaked**, no escalation offered. Confirms
  the new code is serving live.
- Incidental (NOT this story): startup logged `this_month_spend_usd 70.86,
  degraded false` — the F-10-3-1 inflated-July-estimator, owned by Story 10-5-5
  (Cluster E). Under cap here; no degraded trip.

### Still Adam-hands-on (Task 5, unchanged)

- AC-2 live (Hermes skill-file hardening + reject-verify via real `skill_manage
  patch` in Discord).
- AC-4 live tail (real Discord "yes, escalate" → real Opus draft dispatch,
  Console-sourced spend).
- CR-8 caller_origin trust-boundary decision.

### Story disposition — DONE (Adam-signed 2026-07-10)

Task 5 live co-walk executed (real stack + real Discord). **Adam: "Sign all —
flip to done."** AC-1/AC-2/AC-3 live-PASS; AC-4 accepted at code-L3 (API layer
proven; live end-to-end blocked by persona no-re-dispatch → F-10-5-2-W2 filed to
10-5-6); AC-5 CR complete (7/7). Live-walk fix F-10-5-2-W1 (turn-ordering →
migration 027 escalation_armed singleton) shipped + live-verified. F-10-5-2-W3
(migration-edit-after-apply) + CR-8 (caller_origin=unknown-external, sidestepped
by singleton arm) recorded. Suite 1779+2+3 (+51 net). Staged, nothing committed.
Live stack runs this story's code (image ed18774792db). See 10-5-2-walk-evidence.md.
