---
baseline_commit: 4412da006f66930eecd36f7b5be004b3d98edd96
---

# Story 6.6.5: Epic 5 capstone carry-forward walk — verify the wiring resurrects the dormant capstone

Status: review

## Story

As Adam,
I want a dedicated Phase 3.5 walk against the now-wired stack (post-Story 6.6) that proves Story 5-9's draft-reply capstone runs end-to-end against a real Outlook test account AND clears Story 4-0's deferred checkpoints (drainer end-to-end, real Graph write-back, 20-send/day cap live),
So that the Epic 5 carry-forward is closed under a Phase 3.5 walk record — not under a "we wired it, looks fine" claim folded into another story's ACs.

## Acceptance Criteria

**Given** Story 6.6 has wired the drainer + cooling-off ticker + Outlook adapter into `worker.py`
**When** Adam (with Amelia walking through agent-side checkpoints first) runs the capstone walk against a real Outlook test account
**Then** the Story 5-9 happy path completes end-to-end: DM "draft a reply to that" (normal email) → reference resolution → tone_style_mirror (cached) → draft_reply (Opus) → defender presents draft → Adam replies "send" → propose_action SEND_REPLY → 60s cooling-off → drainer claims and dispatches via `OutlookGraphWriteAdapter` → real Graph send → reply lands in the test recipient's inbox
**And** the corresponding `pending_actions` row reaches `status="applied"` with `budget_consumed=true`
**And** the day's send count increments by 1 (verified by querying the 20-send cap state)
**And** `/cost month` reflects the Opus draft_reply call in the breakdown

**Given** the sensitive-email path
**When** Adam walks the path: DM "draft a reply to that" on a `sensitive`-classified email → defender requests `/confirm` → `mint_sensitivity_token(email_id, "draft_reply")` succeeds → token passed → draft_reply runs with the F1 task_type-binding fix (token passed to draft_reply Router call but NOT to tone_style_mirror)
**Then** the draft generates successfully against real Anthropic
**And** the `router_calls` row carries `sensitivity_grant_id` + `sensitivity_grant_minted_at`
**And** the consume-aware Router precondition layer accepted the token and emitted the audit pair

**Given** the confidential-email path
**When** Adam walks the path: DM "draft a reply to that" on a `confidential`-classified email
**Then** the defender refuses without dispatching any Anthropic call
**And** `router_calls` has no new row for the refusal (per Story 4.7 design)

**Given** Story 4-0's deferred Phase 3.5 CPs (drainer end-to-end, real Graph write-back, 20-send/day cap live) wait on this wiring
**When** the capstone walk completes
**Then** all three deferred CPs are marked PASS in the walk record
**And** the 20-send/day cap is exercised: 20 successful sends (or simulated quick budget burn) → the 21st returns `BUDGET_CAP_HIT` and the drainer refuses without dispatching to the adapter
**And** a midnight-UTC rollover (clock-frozen test or live wait) confirms the cap resets

**Given** the walk completes
**When** the walk record is written
**Then** the record is appended to `_bmad-output/implementation-artifacts/epic-6-run-flags.md` (or wherever Epic 6 keeps its Phase 3.5 evidence) with: real recipient address (redacted), real reply body (redacted), the `pending_actions.id` and `router_calls` IDs walked, the budget burn observed, any findings
**And** the Epic 5 capstone carry-forward is explicitly closed in `epic-5-run-flags.md`: F-deferred items linked to this walk record
**And** if any finding surfaces, it is filed as either an Epic 6 story amendment or a backlog item — *no silent close*

## Tasks / Subtasks

- [x] **Task 1: Agent-side Section A — offline + DB-real pre-walk verification** (AC: all) — **HALTED at F6 prerequisite check**: F6 (MCP /mcp 307→404 mismatch from Story 6-0) is NOT RESOLVED in epic-6-run-flags.md — still filed as carry-forward to "Story 6-3 or a dedicated follow-up." Remaining Section A and all of Section B require Hermes↔mailbot-api MCP discovery to work, which F6 blocks. Story halted per its own hard-prerequisite contract; surfaced to orchestrator.
  - [x] Read `epic-6-run-flags.md` § Story 6-0 walk record + Story 6-6 disposition to confirm the F3/F4/F5 + F6 status; if F6 (MCP /mcp 307→404 mismatch) is NOT yet RESOLVED, **HALT and surface to Adam** — CP-Live requires Hermes ↔ mailbot-api MCP discovery to work, which F6 blocks. If RESOLVED, proceed. — F6 IS NOT RESOLVED → HALTING.
  - [ ] Verify scheduler wiring offline: `python -c "from mailbot_api.worker import _worker_main; print('ok')"` exits 0; `python scripts/check_hermes_config.py` exits 0.
  - [ ] Verify drainer wiring offline: run `tests/integration/test_worker_drainer_wiring.py` — all 4 tests pass; the Tier-2 ARCHIVE real-adapter test PROVES the drainer↔adapter contract works against `MockTransport`.
  - [ ] Verify Story 5-9 chat orchestrator surface offline: re-run `tests/integration/test_draft_reply_capstone*.py` (or whatever Story 5-9 named them) — all tests pass; the F1 task_type-binding fix is in place.
  - [ ] Confirm `.env` has the credentials Story 4-0 captured: `OUTLOOK_*` (5 keys), `ANTHROPIC_API_KEY`, `DISCORD_BOT_TOKEN`, `DISCORD_ALLOWED_USERS`, `MAILBOT_ROUTER_KEY`. (Don't echo them — just check presence + non-empty.)
- [ ] **Task 2: Bring the stack up** (AC: walk-prerequisite)
  - [ ] `docker compose up -d` from project root; wait 60s for all services to reach healthy.
  - [ ] Verify `docker compose ps`: mailbot-api healthy, ollama healthy, mailbot-hermes running (not restart-looping).
  - [ ] `docker logs mailbot-hermes --tail 50` — assert gateway is up (look for `⚕ Hermes Gateway Starting...` or equivalent). If Hermes is still failing per F6, halt here.
  - [ ] `curl http://localhost:8000/health` returns 200 with `sync_*` fields populated (per Story 1-8 + 6-6 worker scheduler running).
- [ ] **Task 3: Send the test fixture emails** (AC: pre-walk)
  - [ ] Adam sends himself (the test Outlook account) 3 emails from a SECOND email account he controls — designed to land in classifications `normal`, `sensitive`, `confidential` respectively. (Or: instruct Adam to use the corpus seed Story 7-1 will eventually ship; for now, hand-crafted is fine.)
  - [ ] Wait 4 minutes for the sync loop to fetch them; verify they appear in SQLite via `docker exec mailbot-api python -c "from mailbot_api.db.connection import fetchall; import asyncio; print(asyncio.run(fetchall('/data/mailbot.db', 'SELECT graph_id, subject, sensitivity_class FROM emails ORDER BY received_at DESC LIMIT 5', ())))"`
  - [ ] Wait for the ingest pipeline to classify them (sensitivity_at NOT NULL); verify `sensitivity_class` per email matches expected (`normal`, `sensitive`, `confidential`).
- [ ] **Task 4: Walk the normal-email happy path (CP-A)** — REQUIRES ADAM
  - [ ] Adam DMs the bot: "draft a reply to that" (referring to the normal email in his Discord context).
  - [ ] Verify the response: bot presents a draft (defender persona, normal voice).
  - [ ] Adam replies in DM: "send" — capture the `propose_action SEND_REPLY` action_id from the bot's response.
  - [ ] Wait 60s for cooling-off → pending → drainer claim.
  - [ ] Adam's TEST RECIPIENT account receives the reply email — verify by checking that inbox.
  - [ ] In SQLite: verify `pending_actions.status='applied'` and `budget_consumed=1` for the action_id; verify a `router_calls` row exists for the draft_reply Opus call with `caller_origin='chat-draft-reply'`-or-equivalent; verify the 20-send cap state shows day_sent=1.
  - [ ] Adam DMs the bot: `/cost month` — verify the response includes the Opus draft_reply call in the breakdown.
  - [ ] Mark CP-A PASS in walk record with: redacted recipient address, redacted reply body excerpt, `pending_actions.id`, `router_calls.id`, budget burn.
- [ ] **Task 5: Walk the sensitive-email path (CP-B)** — REQUIRES ADAM
  - [ ] Adam DMs the bot: "draft a reply to that" (referring to the SENSITIVE email).
  - [ ] Verify the bot requests `/confirm` (defender persona; explicit sensitivity acknowledgment).
  - [ ] Adam DMs: `/confirm <email_id> draft_reply` — captures `mint_sensitivity_token` success.
  - [ ] Adam re-DMs: "draft a reply to that" — the token is consumed; draft generates against real Anthropic.
  - [ ] In SQLite: verify the `router_calls` row for the draft_reply Opus call carries `sensitivity_grant_id` (NOT NULL) + `sensitivity_grant_minted_at` (NOT NULL); verify the consume-aware Router precondition layer accepted the token (no `SENSITIVITY_BLOCKS_API` error in audit).
  - [ ] Critical: verify the F1 task_type-binding fix held — the `tone_style_mirror` Router call (if it fired in this turn) does NOT carry the sensitivity token (`router_calls.sensitivity_grant_id IS NULL` for the tone call).
  - [ ] Mark CP-B PASS in walk record.
- [ ] **Task 6: Walk the confidential-email path (CP-C)** — REQUIRES ADAM
  - [ ] Adam DMs the bot: "draft a reply to that" (referring to the CONFIDENTIAL email).
  - [ ] Verify the bot REFUSES without dispatching any LLM call (defender voice: "I can't help with confidential emails — please reply manually").
  - [ ] In SQLite: verify NO new `router_calls` row was written for the refusal (per Story 4.7 design — `confidential` short-circuits BEFORE Router dispatch).
  - [ ] Mark CP-C PASS in walk record.
- [ ] **Task 7: Walk the 20-send/day cap (CP-D)** — REQUIRES ADAM
  - [ ] Approach: simulate-quick-budget-burn via direct DB manipulation rather than 20 real sends (saves Adam 20 round-trips). Use `docker exec mailbot-api python -c "..."` to update the day's send-count state to 19; then drive ONE more real send through the chat → cool-off → drain path (action 20).
  - [ ] After action 20 completes, attempt action 21 (drive another chat → propose SEND_REPLY → cool-off → drain).
  - [ ] Verify: action 21 lands in `pending_actions` but the drainer marks it `failed` with `failure_reason='BUDGET_CAP_HIT'` (or whatever the Story 4-6 contract named it). No Graph dispatch; the test recipient does NOT receive a 21st email.
  - [ ] For midnight rollover: bias to clock-frozen test rather than live wait. Run a small Python script (`docker exec mailbot-api python -c "..."`) that fast-forwards the day_utc cell and verifies the cap resets (day_sent → 0 after rollover). Alternatively, defer the live midnight-wait check to a follow-up.
  - [ ] Mark CP-D PASS in walk record (or PARTIAL if midnight rollover is clock-frozen-only verified).
- [ ] **Task 8: Write the walk record + close carry-forward** (AC: walk-record)
  - [ ] Append a `## Story 6-6.5 walk record` section to `_bmad-output/implementation-artifacts/epic-6-run-flags.md` with: timestamp, per-CP verdict (PASS / PASS WITH FINDINGS / FAIL / PARTIAL), evidence per CP (redacted recipient address, redacted reply body excerpts, `pending_actions.id` + `router_calls.id` for each, budget burn, any findings).
  - [ ] Update `_bmad-output/implementation-artifacts/epic-5-run-flags.md`: append a one-line "Capstone carry-forward CLOSED 2026-06-03 — see epic-6-run-flags.md § Story 6-6.5 walk record" note to the F-deferred items section (audit trail preserved).
  - [ ] Update `_bmad-output/implementation-artifacts/4-0-interactive-credential-capture-and-phase-3-5-verification.md`: amend the 3 deferred CPs (drainer e2e, real Graph write-back, 20-send/day cap live) with their PASS status + link to the 6-6.5 walk record.
  - [ ] If any finding surfaces: file as Epic 6 story amendment OR backlog item — NO silent close. Track in `epic-6-run-flags.md` § Story 6-6.5 walk record findings sub-section.
- [ ] **Task 9: Tear down + housekeeping**
  - [ ] `docker compose down` to release resources.
  - [ ] Stage all walk-record artifacts via `git add` (story file + epic-6-run-flags + epic-5-run-flags + 4-0 file + sprint-status); NO `git add -A`.

## Dev Notes

### Phase 3.5 walk story — REQUIRES Adam at the keyboard

This is NOT a code-implementation story. It's a Phase 3.5 walk story per the structural-backstop lesson from Epic 4 retro action #6: explicit story file = explicit Phase 3.5 record. Story 4-0 worked precisely BECAUSE it was its own story with its own structural requirements; folding "verify the wiring" into Story 6.6's ACs would short-change the verification.

**Agent-vs-Adam division** (Epic 5 Phase 3.5 walk pattern):

- **Agent walks Section A** (offline + DB-real surrogates): Tasks 1, 2, 3 (most of), 8 (writing the walk record from Adam's input + agent-side DB queries), 9 (teardown).
- **Adam walks Section B** (live operator-only checkpoints): Tasks 4, 5, 6, 7 — these REQUIRE Adam at the Discord client, real Outlook inbox, and a SECOND email account to send test fixtures from.

The agent's job during Section B is to:
1. Be ready to answer DB-query questions ("did `pending_actions.id=X` flip to applied?")
2. Tail the relevant logs and surface anomalies in real time
3. Record the walk evidence into `epic-6-run-flags.md` as Adam confirms each CP

### Walk-record evidence convention

Per the autonomous-epic-run skill's Walk-Evidence Convention, evidence sub-folder:
- `_bmad-output/implementation-artifacts/6-6-5-uat-evidence/` for any screenshots, CSV exports, JSON dumps
- Inline ≥1 most-diagnostic screenshot per CP in the walk record using markdown image syntax
- Stage explicitly per Step 2.6 (no `git add -A`)

Walk record fields per CP (canonical shape):

```text
### CP-A — Normal email happy path
- Verdict: PASS
- Timestamp: 2026-06-03 HH:MM UTC
- Real recipient: <REDACTED>
- Reply body excerpt: "Thanks for the heads-up..." <REDACTED-MIDDLE>
- pending_actions.id: 47
- router_calls.id: 1832 (draft_reply, Opus, $0.0184)
- Budget burn: $0.0184 added to day's total
- Findings: none / one-line description
```

### Pre-flight: F6 RESOLVED is a hard prerequisite

The MCP /mcp 307→404 redirect mismatch (Story 6-0 F6 finding) blocks Hermes from discovering mailbot-api's MCP tools. Without that, Hermes can answer "hello" to Adam but cannot invoke `find_emails`, `propose_action`, `mint_sensitivity_token`, etc. — which means EVERY CP in this walk is dead-on-arrival.

**Mandatory check at Task 1**: read `epic-6-run-flags.md` § Story 6-0 walk record + any subsequent updates. If F6 is RESOLVED (in a follow-up story shipped between 6-6 and 6-6.5), proceed. If NOT RESOLVED, halt this story and surface to Adam — F6 is the dependency that must close first.

This is a common-cause hazard: the autonomous loop sequenced 6-0 → 6-6 → 6-6.5 assuming F6 would be closed by an intermediate fix. Since the orchestrator does NOT autonomously dispatch F6 work (it was filed as carry-forward, not as a sequenced story), the agent must check explicitly at story kickoff and halt if F6 is still open.

### Test-recipient setup

CP-A requires Adam to have a SECOND email account he controls — the bot's "send a reply" target. Story 4-0 captured credentials but did NOT establish a test-recipient. Recommended: Adam uses any non-MailBot-monitored email account (Gmail, personal Outlook, etc.). The bot's draft_reply targets the original sender's address, so the SECOND account is the sender of the test emails.

Flow:
1. Adam, from `test-sender@gmail.com`, sends a test email to `adam-mailbot@outlook.com` (the MailBot-monitored account).
2. MailBot syncs + ingests + classifies.
3. Adam DMs bot "draft a reply to that".
4. Bot drafts a reply addressed to `test-sender@gmail.com`.
5. After "send", drainer dispatches via Graph; `test-sender@gmail.com` receives the reply.

### Sensitivity-class seeding

Use the corpus from Story 7-1 if it exists by the time this story runs; if NOT (Story 7-1 hasn't shipped — it's in Epic 7), hand-craft three test emails with content that should trigger:

- **normal**: e.g., "Hey, are you free for coffee next week?" — pattern-clean, low-stakes.
- **sensitive**: e.g., "Re: the password reset — can you confirm the security questions?" — triggers patterns like `password`, `security question`.
- **confidential**: e.g., "Per our NDA discussion — here's the unreleased product spec attached." — triggers patterns like `NDA`, `confidential`, `unreleased`.

`sensitivity_patterns.yaml` lists the actual trigger patterns; consult it to pick triggers that match your local config.

### What this story does NOT touch

- **No code changes.** Story 6.6 wired everything; this story walks it. If a finding surfaces that requires code, file as a follow-up story — DO NOT patch in this story (audit trail discipline).
- **No new tests.** The integration tests from Story 6.6 already prove the contracts; this walk proves the REAL-stack behavior. If a CP fails and the cause is a code defect, the follow-up story writes the regression test.
- **No `_bmad-output/planning-artifacts/` edits.** The AC text is the source of truth; if it's wrong, file an amendment for the next retro.

### What "PASS WITH FINDINGS" means

If a CP works but Adam observes something off (rendering glitch, slow defender response, off-tone draft, etc.) that doesn't fail the CP outright, mark PASS WITH FINDINGS and record the observation in the walk record. The orchestrator's Phase 3.5 gate accepts this verdict.

If a CP fails outright (e.g., the draft never arrives, the cooling-off never expires, the recipient never gets the reply), mark FAIL — the epic does NOT close until the failure is fixed in a follow-up story.

### Project Structure Notes

- **NEW**: `_bmad-output/implementation-artifacts/6-6-5-epic-5-capstone-carry-forward-walk.md` (this file)
- **NEW (conditional, if walk produces screenshots)**: `_bmad-output/implementation-artifacts/6-6-5-uat-evidence/`
- **MODIFIED**: `_bmad-output/implementation-artifacts/epic-6-run-flags.md` (append § Story 6-6.5 walk record)
- **MODIFIED**: `_bmad-output/implementation-artifacts/epic-5-run-flags.md` (one-line capstone-carry-forward-closed note)
- **MODIFIED**: `_bmad-output/implementation-artifacts/4-0-interactive-credential-capture-and-phase-3-5-verification.md` (amend 3 deferred CPs with PASS + link)
- **MODIFIED**: `_bmad-output/implementation-artifacts/sprint-status.yaml`
- **NO code-side files** (no `mailbot_api/`, `tests/`, `scripts/`, `docker-compose.yml`, `hermes-config/` changes — this is a walk story).

### Testing standards summary

No new pytest tests. The 4 quality gates (ruff, mypy --strict, boundary checker, pytest) MUST be green BEFORE the walk starts (Task 1 sanity check) — if they're not, halt; a previous story broke something. They MUST also be green AFTER the walk completes (Task 9 sanity check) — this story didn't touch code, so if gates fail at the end, something external changed. Document anything weird.

### References

- [_bmad-output/planning-artifacts/epics.md](../planning-artifacts/epics.md) §"Story 6.6.5" — canonical AC source
- [_bmad-output/implementation-artifacts/epic-5-retro-2026-06-02.md](./epic-5-retro-2026-06-02.md) §4 (story creation + scope) — the retro that created this story
- [_bmad-output/implementation-artifacts/epic-5-run-flags.md](./epic-5-run-flags.md) § "Aggregated `[deferred:*]` items" — capstone carry-forward to be closed
- [_bmad-output/implementation-artifacts/epic-6-run-flags.md](./epic-6-run-flags.md) § Story 6-0 walk record — F6 status check
- [_bmad-output/implementation-artifacts/5-9-draft-reply-flow-end-to-end-capstone.md](./5-9-draft-reply-flow-end-to-end-capstone.md) — Story 5-9 capstone contract being walked
- [_bmad-output/implementation-artifacts/4-0-interactive-credential-capture-and-phase-3-5-verification.md](./4-0-interactive-credential-capture-and-phase-3-5-verification.md) — Story 4-0 deferred CPs being closed
- [_bmad-output/implementation-artifacts/4-7-sensitive-content-api-override-handshake-mint-sensitivity-token-and-confirmation-token-parameter-and-in-memory-registry.md](./4-7-sensitive-content-api-override-handshake-mint-sensitivity-token-and-confirmation-token-parameter-and-in-memory-registry.md) — Story 4-7 sensitivity token + Router precondition layer contract (CP-B reference)
- [_bmad-output/implementation-artifacts/6-6-worker-process-integration-wire-all-dormant-background-work-into-worker-py.md](./6-6-worker-process-integration-wire-all-dormant-background-work-into-worker-py.md) — Story 6-6 wiring that this walk verifies

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Debug Log References

- `epic-6-run-flags.md` § "New finding F6": F6 status is "**Filed as:** Story 6-3 (notification dispatcher) or a dedicated follow-up." No subsequent RESOLVED disposition found in the file.
- Story 6-6 (just completed) did NOT close F6 — its scope was worker-process scheduler integration, not MCP redirect resolution.

### Completion Notes List

- **[BLOCKED: f6-still-open]** Story 6-6.5 cannot proceed. F6 (MCP `/mcp` 307→404 redirect mismatch between FastMCP at `mailbot-api:8000/mcp` and Hermes's MCP client) is the prerequisite for every CP in this walk:
  - **CP-A (normal email happy path)**: requires Hermes to dispatch `find_emails` / `propose_action` MCP verbs → blocked.
  - **CP-B (sensitive-email handshake)**: requires Hermes to dispatch `mint_sensitivity_token` MCP verb → blocked.
  - **CP-C (confidential-email refusal)**: requires Hermes to even know the verb surface to refuse against → blocked.
  - **CP-D (20-send/day cap)**: depends on CP-A's drain path being live → blocked.
- **Resolution path**: F6 must close in a follow-up story BEFORE Story 6-6.5 can be re-run. Per Story 6-0 RECONCILIATION-NOTES, the fix space is one of: (1) trailing-slash on `mcp_servers.mailbot-api.url` (`http://mailbot-api:8000/mcp/`); (2) FastMCP mount-path adjustment on the mailbot-api side; (3) Hermes redirect-follow configuration. The orchestrator did NOT autonomously dispatch F6 work because it was filed as carry-forward, not as a sequenced story. **Recommended: Adam files a NEW story (e.g., `6-6.6-mcp-redirect-fix-f6-closure`) and dispatches it manually before re-running 6-6.5.**
- **What this story SHOULD have done if F6 were resolved**: Tasks 1-3 (agent-side Section A — offline checks + Docker stack bring-up + test fixture seeding); Tasks 4-7 surfaced to Adam (Section B requires Adam at the keyboard for real Discord ↔ Outlook ↔ Anthropic round-trip); Task 8-9 walk-record write + teardown.
- **Phase 3.5 gate consequence**: the autonomous-epic-run skill's end-of-epic Phase 3.5 manual-verification gate will fire when Epic 6 closes. At that point either (a) F6 is fixed and the gate walks Story 6-6.5's CPs, OR (b) F6 is still open and Phase 3.5 verdict is FAIL — epic stays `in-progress` until F6 resolves. **The orchestrator should NOT mark Epic 6 done until Story 6-6.5 walk completes; the closure-gate annotation between Stories 6-7 and 6-3 in sprint-status.yaml correctly enforces this.**
- **Story status flipped to `review` with `[blocked: f6-still-open]` disposition** rather than left `in-progress`: the agent-side verification work this story owns (F6 prerequisite check) IS complete; the remaining work belongs to a downstream story + Adam's Phase 3.5 walk. Marking `review` keeps the orchestrator's main loop moving without falsely claiming `done`. The walk record at `epic-6-run-flags.md` § Story 6-6.5 will be appended when Adam walks the live CPs post-F6-fix.

### File List

- `_bmad-output/implementation-artifacts/6-6-5-epic-5-capstone-carry-forward-walk.md` (this story file)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status flip ready-for-dev → review-with-block-note)

### Change Log

- 2026-06-03 — Story 6-6.5 HALTED at Task 1 prerequisite check: F6 (MCP /mcp 307→404 mismatch) is NOT RESOLVED. Story flipped to `review` with `[blocked: f6-still-open]` disposition; walk deferred until F6 closes in a follow-up story.
