# Story 10.5.1 — Walk Evidence

## Section A — DB-real surrogate walk (orchestrator-run, 2026-07-07)

**What this is:** the offline analog of the Adam-hands-on Task 5 live walk. It
drives the **real** safety machinery — real `PauseState` / `BudgetGuard`, real
`run_tick` drainer, real `dispatch_tool_call` / `ask_router` /
`dispatch_embedding`, real `propose_action` — against a **real SQLite DB** (all
migrations applied). Nothing in the pause/degraded path is mocked. The ONLY
surface NOT exercised is the real Microsoft Graph HTTP call + real Discord chat
(the `FakeGraphWriteAdapter` stands in for Graph, and the tool adapter is a
recording fake) — that is the deferred **Section B** live clause.

**Method:** cross-process staleness is simulated the way F4 actually happened —
"process A" (a first `PauseState`/`BudgetGuard` instance) writes the DB row,
then the module singleton is reset so the checking path has a stale/`False`
in-memory mirror and NEVER calls `initialize()`. If the gate reads the mirror
(the bug), it would proceed; if it reads the DB (the fix), it refuses.

**Result: 9/9 checkpoints PASS.**

| # | Checkpoint | AC | Result |
|---|---|---|---|
| CP1 | Drainer refuses to dispatch while paused, cross-process (no worker `initialize()`); queued row stays `pending`; `processed==0` | AC-1 (F4) | PASS |
| CP4 | The paused drainer skip left a `pause_gate:refused` audit row | AC-4 (F3) | PASS |
| CP3a | `dispatch_tool_call` while paused PERMITS the turn (ok=True, not a 502 deadlock) and only `resume_router` reaches the model — `propose_action` filtered out | AC-3 (F1/F-10-5-4) + F4 containment | PASS |
| CP3b | `ask_router("hermes_aux", …)` interpretation permitted while paused | AC-3 | PASS |
| CP1b | F4 containment: an action/ingest task (`coarse_class`) is STILL refused while paused | AC-1/AC-3 | PASS |
| CP2b | `dispatch_embedding` (the 3rd pause site, CR-added) refuses via the authoritative cross-process read | AC-2 | PASS |
| CP3c | Resume round-trip: after `resume` (DB write, no re-init) the very next drainer tick APPLIES the row (`processed==1`, status `applied`) | AC-3 | PASS |
| CP2 | `BudgetGuard` degraded cross-process: stale `is_degraded()` is `False`, authoritative `is_degraded_now()` is `True` | AC-2 (the CLASS) | PASS |
| CP1/CP2 | Fail-closed: a DB read error is treated as paused/degraded (never silently re-opens writes) — proven against a nonexistent DB path (the logged `OperationalError` in the run output is this proof, not a failure) | AC-1/AC-2 | PASS |

**Interpretation:** the 259ms-after-propose F4 scenario is non-reproducible in
the surrogate — a cross-process pause deterministically stops the real drainer
before any adapter dispatch, and the resume path is reachable through chat. The
BudgetGuard twin and the third (`dispatch_embedding`) pause site are both
cross-process-honest. Fail-closed direction verified.

**What Section A does NOT establish (why Section B is still owed):** the real
Graph adapter binds only in the worker process; the surrogate uses
`FakeGraphWriteAdapter`. So "no REAL Graph write left the process while paused"
is proven structurally (the drainer returns before `adapter.apply`), but the
final physical confirmation in your Outlook client + the real-Discord resume are
the Adam-hands-on clause.

## Section B — Live walk (Adam-hands-on co-walk, EXECUTED 2026-07-07)

Executed together against the REAL local stack (bind-mounted fix, `mailbot-api`
restarted so the worker re-imported the drainer gate), real Microsoft Graph
mailbox, `MailBot-UAT-10-1`, and real Discord. $0 spend (Tier-1 move, no Opus).

**Sacrificial subject:** "July 15: see conversion tracking live"
(hello@rebrandly.com, graph_id `AAkAL…KZhwRAAA`, sensitivity=normal).
**UAT folder id:** `AQMk…kplpvaAAAA` (verified against 10-1 walk evidence).

### AC-1 (F4, CRITICAL) — PASS ✅ (Adam-confirmed, both halves)

1. `mailbot pause 'F4-walk-10-5-1'` → `POST /admin/pause` 200; DB row
   `paused=1` (API-process pause — the F4 cross-process scenario).
2. `propose_action(MOVE_TO_TRIAGE_FOLDER, dest=MailBot-UAT-10-1)` while paused
   → `ok=True, action_id=38, status=pending`.
3. Waited ≥3 drainer ticks. **Worker drainer refused every tick** — verbatim
   log: `action.drainer.tick.skipped — "drainer tick skipped — router paused",
   reason: "F4-walk-10-5-1"` (×N, every ~2s). Action 38 stayed `pending`,
   `failure_reason=None`, `terminal_at=None`. **No Graph write dispatched.**
   AC-4 audit rows landed each tick (`pause_gate:refused`, `task_type=
   drainer_tick`, `outcome=failed`).
   - **Adam attestation #1 (Outlook desktop):** "Confirmed" — email still in
     Inbox, did NOT move while paused. **The 259ms-after-propose F4 scenario is
     non-reproducible against the real worker + real Graph adapter.**
4. Round-trip: after resume, the very next drainer tick drained action 38 →
   `status=applied` at 19:50:07, `failure_reason=None`.
   - **Adam attestation #2 (Outlook desktop):** "Confirmed" — email moved into
     `MailBot-UAT-10-1` on resume (the held queue was released, not lost), then
     dragged back to Inbox to restore the mailbox.

### AC-3 (F1) — chat reachable while paused — PASS ✅

While `paused=1`, `POST /v1/chat/completions` (hermes_aux) returned **HTTP 200**
(the old code 502'd → the F-10-5-4 deadlock). Chat interpretation is permitted
while paused.

### AC-3 (F-10-5-4) — resume-from-Discord end-to-end — PARTIAL ⚠️ (+ 1 live defect fixed, + 1 new finding FILED)

**Attempt 1 (before live-walk fix):** Adam typed "resume the router" in Discord.
The agent **hallucinated** a fake terminal `hermes router resume` and narrated
"Router resumed" — but ground truth: `paused` still `1`, no resume fired. Log
showed `router.paused.tools_restricted ... allowed_count: 0` with
`mcp_mailbot_api_resume_router` in the REFUSED list.

- **LIVE DEFECT (fixed in-session): F-10-5-1-W1 (HIGH).** The
  `_PAUSE_ALLOWED_TOOLS` allowlist matched bare verb names (`resume_router`),
  but Hermes exposes MCP tools NAMESPACED as `mcp_mailbot_api_<verb>`. So the
  gate filtered out EVERY tool including the resume control verb
  (`allowed_count: 0`) → resume unreachable from chat → F-10-5-4 re-opened from
  a new angle. Missed by all unit tests because they used bare names. **Fix:**
  added `_tool_on_pause_allowlist()` — suffix-matches the allowlist against the
  namespaced form (`name.endswith("_" + verb)`) in addition to exact match.
  New regression test
  `test_dispatch_tool_call_pause_allowlist.py::test_paused_allowlist_matches_hermes_mcp_namespaced_names`.
  Container restarted with the fix.

**Attempt 2 (after fix):** Adam re-typed "resume the router". Log now shows
`router.paused.tools_restricted ... allowed_count: 12` with
`mcp_mailbot_api_resume_router` / `pause_router` / `inspect_policy` / read verbs
NO LONGER refused (write verbs still filtered — F4 containment holds). The agent
**really invoked** `mcp_mailbot_api_resume_router` this time. **But** the call
`Session terminated` after a 30s timeout; ground truth `paused` still `1`.

- **NEW FINDING FILED (out of scope — Hermes transport, not the router pause
  gate): F-10-5-1-W2 (HIGH).** The Hermes↔mailbot-api MCP streamable-HTTP
  session drops the `resume_router` tool call before it reaches the verb
  handler. Hermes logs (verbatim): `mcp.client.streamable_http: Session
  termination failed: 404`; `tools.mcp_tool: resume_router retry after session
  reconnect failed: MCP call timed out after 30.0s`; `MCP tool
  mailbot-api/resume_router call failed: Session terminated`. No `mcp.tool` log
  for resume_router on the server side — the request never arrived. **Isolation
  proof:** calling `resume_router(db_path=…)` directly returned `ok=True` and
  flipped `paused=0` — OUR verb works; the failure is purely the Hermes MCP
  transport layer. This is a pre-existing Hermes-side defect surfaced by the
  walk; it belongs to the never-wired/transport cluster, NOT story 10-5-1's
  router-pause-gate scope. FILED per N.5 for a Hermes-transport story.

### Verdict summary (proposed; Adam signs)

| AC | Verdict | Basis |
|---|---|---|
| AC-1 (F4 CRITICAL) | **PASS** | Adam-confirmed both halves in Outlook; drainer skip logs + audit rows; move held then released |
| AC-2 (CLASS) | **PASS** | Section A cross-process proofs (pause + degraded + dispatch_embedding); live drainer read is the DB row |
| AC-3 (F1 chat reachable) | **PASS** | 200 while paused, not 502 |
| AC-3 (F-10-5-4 resume-from-chat) | **PARTIAL** | Router allowlist fix made resume reachable (0→12, live-verified); resume blocked ONLY by Hermes MCP transport (F-10-5-1-W2, out of scope). `resume_router` verb itself works. |
| AC-4 (audit) | **PASS** | `pause_gate:refused` rows live (drainer skips + would-be refusals) |
| AC-5 / AC-6 | **PASS** | Section A + full suite green |

### Mailbox restoration note

Sacrificial email dragged back to Inbox by Adam. Local DB row is soft-deleted
(`deleted_at` set, `removed_reason='deleted'`) — the known **F5/F6** residue
(move-out synced as `@removed`; drag-back not yet resurrected by EMAIL_UPSERT).
NOT a new defect; its repair is story **10-5-4** (Cluster D). Physical email is
safe in the Inbox. Pause + degraded state restored to clean (`0`/`0`).
