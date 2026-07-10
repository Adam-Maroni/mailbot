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

## Story 10-5-3 — 2026-07-10 (autonomous-story-run dev pass)

**Dev model:** claude-opus-4-8[1m] · **Review model:** claude-sonnet-5 (MANDATORY-CR, AC-4).
**Run-mode:** HYBRID (Tasks 1-6 autonomous; Task 7 live draft walk = Adam-hands-on HALT, small real Opus spend). baseline_commit 7864de4.

### Dev-pass summary — never-wired capabilities wired / boundary-honestly re-documented

- **AC-1 (F-10-5-11) — Opus draft pipeline chat call site: FIXED.** Registered `draft_reply` as MCP tool #26 wired to the real `handle_draft_reply` orchestrator. Integration test proves a REAL `router_calls` row for `task_type='draft_reply'` with a non-qwen Opus model via a registered fake adapter (NO monkeypatched ask_router — kills the L2-green illusion). Live real-Opus confirmation is Task 7 (Adam-hands-on).
- **AC-2 (F-10-4-3) — get_thread reachable: FIXED (implement path).** Added `thread_id` to `EMAIL_PROJECTION_COLUMNS` + `EmailProjection` + `row_to_projection`. `find_emails` rows now carry the thread_id the model hands to `get_thread`; round-trip proven.
- **AC-3 enrichment (F-10-4-4): FIXED (wire path).** `_run_enrichment_step` fires `enrich_sender`+`enrich_thread` as a best-effort trailing step in `process_email` (Qwen-only=free, cached-forever=cost-safe). Non-fatal by construction — failures logged + swallowed, `result.ok` unaffected.

### F-10-4-6 (daily_digest_intro zero rows) — HERMES-SIDE FOLLOW-UP, boundary-honest re-doc — INFO

**Disposition: honest re-documentation, NOT a fabricated mailbot_api fix** (per AC-3's "OR its non-wiring is honestly re-documented" clause + the 10-5-2 AC-2 boundary-honesty precedent).

Root cause is OUTSIDE `mailbot_api`: the `daily_digest_intro` prompt module exists and is complete, but its ONLY intended call site is the **Hermes cron-with-agent step** — `hermes-config/scripts/digest_prepare.py:12` documents that "the cron job's agent step generates the intro via `ask_router(task_type='daily_digest_intro')`", but the script itself only calls `compose_digest` (which deliberately returns cached projections with NO LLM call per its Rule J/Rule A contract) and writes the payload. The agent step that would issue the intro `ask_router` call never fires → zero rows all-time. There is NO `mailbot_api` call site to add — fabricating one would violate the `compose_digest`-is-LLM-free contract.

**Follow-up (Hermes-side, filed):** the Hermes daily-digest cron skill must actually issue the `daily_digest_intro` inference call from its agent step (or the intro claim is dropped). README limitations bullet updated to state this honestly (the intro is Hermes-runtime-issued, not a mailbot_api verb). Same class as F-10-5-2-W2 (persona/Hermes-runtime) — a Hermes-config gap, not a mailbot_api defect.

### Gates + suite (post-dev, pre-CR)

To be captured at Task 5 gate run.

### Task 7 / Phase 3.5 — DELEGATED LIVE WALK EXECUTED (Adam-directed "do the manual verification yourself") — 2026-07-10

Adam delegated the manual verification. Executed against the **live running stack** (mailbot-api restarted to load this story's code — bind-mount already on disk; `mailbot_api/` → `/app/mailbot_api`, so restart reloaded the working tree; stack healthy post-restart, Hermes reconnected + MCP serving 200 OK). All checkpoints driven against the **real production DB** (`/data/mailbot.db`) + real Ollama + real Opus.

**Verdict: PASS (all 5 checkpoints).**

- **AC-1 (F-10-5-11) — PASS (LIVE, real Opus).** Live MCP server registers **26 tools incl. `draft_reply`** (startup `_EXPECTED_TOOL_COUNT==len(wrappers)` assertion passed → healthy). F-10-5-11 baseline confirmed on real DB: 748 all-time `draft_reply` rows were **746 benchmark-runner + 2 cp-a-walk = ZERO chat-origin** (exactly the finding). Drove `handle_draft_reply(caller_origin='chat-orchestrator')` on a real normal email → `STATE: draft_presented` + the **first-ever chat-origin `router_calls` row**: `model_chosen=claude-opus-4-7` (non-qwen), 1133 in / 212 out, estimator **$0.0110** (Console is spend source-of-truth per `feedback_anthropic_spend_source_of_truth.md`; one sub-cent Opus call). Draft pipeline reaches chat for the first time.
- **AC-1 privacy — PASS (LIVE).** Real confidential email → `confidential_refused`, **0 router_calls delta** (body never reached API), correct defender message. Real sensitive email (no token) → `needs_sensitivity_token`, **0 router_calls delta**. Gate holds at the new surface.
- **AC-2 (F-10-4-3) — PASS (LIVE).** All 10 real `find_emails` projections carry populated `thread_id`; feeding one to `get_thread` → `ok=True`, no `THREAD_NOT_FOUND` (the broken chat round-trip now works).
- **AC-3 enrichment (F-10-4-4) — PASS (LIVE).** F-10-4-4 baseline confirmed on real DB: **0/745 senders, 0/1830 threads**. After real `process_email`: sender enriched → real Qwen summary ("Client — recurring business calls and meetings", $0 local); a real multi-message thread enriched → real note ("Q3 budget review — awaiting CFO approval…"). Single-message thread correctly short-circuits (best-effort). Enrichment runs on the live ingest path.
- **AC-3 digest (F-10-4-6) — PASS (honest re-doc verified).** `daily_digest_intro` rows still **0** on real DB → confirms it's genuinely a Hermes-cron-agent gap, NOT a mailbot_api-fixable capability. README bullet states this honestly ("issued by the Hermes-side cron agent step, not by mailbot_api…tracked as a follow-up").

**Real side effects (legitimate production activations, not test pollution):** 2 senders + 1 thread enriched (from 0), 1 chat-origin draft row (from 0). Stack left healthy. mailbot-api now runs this story's code (restarted 2026-07-10T14:19Z).

**Spend:** ~$0.011 estimator (one Opus draft call). Console-authoritative per durable memory; sub-cent, well within the "small real Opus spend" envelope.
