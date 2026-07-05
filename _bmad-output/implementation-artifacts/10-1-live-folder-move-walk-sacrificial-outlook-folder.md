---
baseline_commit: 5222589d0b6ef51cc71c53cd720d9c9848367677
---

# Story 10.1: Live folder-move walk — sacrificial Outlook folder, full propose→grant→drain→Graph dispatch chain

> ⚠️ **WALK STORY — dev agents halt here per § "RUN-MODE BINDING enforcement".** Do not proceed with `dev-story` or `/autonomous-story-run`. Log the halt in `_bmad-output/implementation-artifacts/epic-10-run-flags.md` (CREATE the file if absent — it does not exist yet; model it on `epic-9-5-run-flags.md`, matching the Story 9.5.2 Run 2 / 9.5.3 Run 1 halt pattern) and return control to Adam. Walk execution is Adam-hands-on: it moves ONE real email in Adam's REAL Outlook mailbox into ONE sacrificial folder and requires verification in the Outlook client (web or desktop). Zero real Anthropic spend expected ($0 — no Router calls on this path; see Contract Pin 7).

Status: done (walk executed 2026-07-05, same session as context-engineering; all 5 AC verdicts PASS, Adam-signed "Sign all PASS" 2026-07-05 — see 10-1-walk-evidence.md footer)

<!--
Walk story (Phase-3.5-shaped), Epic 10 README-as-charter UAT. NOT an implementation story:
it produces walk evidence + same-commit README doc-drift updates, not code. Sequenced FIRST
in Epic 10 because folder-move is the only write path never live-walked (FakeGraphWriteAdapter
/ L2 only) and is irreversible today (no pre_state, no revert). Story 10.2 fixes the
irreversibility, informed by THIS walk's findings.

Scope fence (Epic 10 D2): any defect discovered here OTHER than the pre-declared Story 10.2
scope (pre_state capture + move-family revert) is FILED per the N.5 policy, NOT fixed in-walk.
Any in-walk code fix escalates CR per §5.12.
-->

## Story

As Adam,
I want to execute one real folder-move against a sacrificial Outlook folder through the full propose→grant→drain→Graph dispatch chain, verify the move in Outlook itself, and restore manually afterward,
So that the one never-live-walked irreversible write path is validated at L3 before Epic 10 walks the rest of the perimeter, and so Story 10.2 learns exactly what pre_state must capture to make the move-family revertible.

## Acceptance Criteria

**AC-1 — Staging bounds the blast radius**
**Given** the live local stack is running against Adam's real mailbox
**When** the walk is staged
**Then** Adam creates (or designates) a sacrificial folder in the live Outlook mailbox and selects a low-value email as the move subject — blast radius bounded to one email + one folder by construction

**AC-2 — Full chain fires with per-stage evidence**
**Given** the staged subject email
**When** the full chain fires — propose (queued intent) → grant → drain → Graph dispatch
**Then** each stage's evidence is captured: the queued-intent row, the grant/authorization evidence, the drainer dispatch record, and the Graph write audit trail
**And** the email physically appears in the sacrificial folder **verified in the Outlook client** (web or desktop), not merely inferred from a 2xx Graph response

**AC-3 — Manual restore + pre_state findings for 10.2**
**Given** the move is irreversible today
**When** the walk completes
**Then** Adam manually restores the email to its original folder and the restore procedure is documented in the walk evidence (the walk leaves the mailbox as found)
**And** `10-1-walk-evidence.md` explicitly records what pre-move state a future revert would have needed (source folder id at minimum, plus anything else observed) — this is the direct input to Story 10.2's pre_state field list

**AC-4 — README doc-drift discharge, same story same commit**
**Given** doc-drift rule (a)
**When** the walk closes
**Then** the README's folder-move example is updated with the real captured output + `<!-- verified 10-1, run_id ... -->` tag in the same story, same commit

**AC-5 — CR cadence**
**Given** this is a walk story
**When** CR cadence is evaluated per the 6 criteria
**Then** zero criteria fire → CR skipped per cadence binding; any in-walk code fix escalates per §5.12 (and, per D2, any defect other than the pre-declared 10.2 scope is FILED, not fixed)

### AC interpretation pins (code-reality; read before executing)

- **AC-2's "grant" stage:** `MOVE_TO_TRIAGE_FOLDER` is **Tier-1 in code** — a grant row is impossible by construction (`mint_grant` refuses Tier-1 with `GRANT_NOT_NEEDED`). The AC's "grant/authorization evidence" is discharged HONESTLY as authorization-model evidence, not a grant row: capture (a) the `ACTION_PROPERTIES` tier pin, (b) a live `mint_grant` → `GRANT_NOT_NEEDED` refusal as proof-of-construction, and (c) the drainer's Tier-1 lenient check as the authorization gate that actually ran. See Contract Pin 1. Do NOT fake a grant by walking a different action type.
- **AC-4's "README's folder-move example":** the README has **no folder-move worked example today** and **zero `<!-- verified -->` tags anywhere** (Story 10-1 introduces the convention). Discharge = update the Limitations claim README.md:357 ("Folder moves not live-walked") with the walk's real captured output + verified tag, and/or add a small worked move example modeled on the Tier-2 archive example at README.md:122-130. See Task 6.
- **Verdict vocabulary:** PASS / PARTIAL-PASS / FAIL, Adam-signed per AC section, per the 9.5.x walk-evidence convention.

## Tasks / Subtasks

<!--
Tasks are Adam-hands-on walk checkpoints, NOT code-authoring steps. Claude may assist live
(composing queries, reading logs, drafting evidence) but Adam drives every mailbox-touching
action and signs every verdict. Adam-phrasing retries in Discord are NOT an AC failure.
-->

- [x] **Task 0 — Pre-walk stack + OAuth verification (BLOCKING — must PASS before AC-1)**
  - [x] 0.1 `git rev-parse HEAD` == `baseline_commit` above (or record the drift + rationale in evidence header)
  - [x] 0.2 `docker compose ps` → `mailbot-api` (healthy), `mailbot-hermes` up, `mailbot-ollama` (healthy). If any down: `docker compose up -d`. Record Hermes image sha (`docker inspect mailbot-hermes | jq -r '.[0].Image'`) into the evidence header
  - [x] 0.3 `curl http://localhost:8000/health` → 200
  - [x] 0.4 OAuth green: `docker compose exec -T mailbot-api python scripts/mailbot.py status` → OAUTH `refresh failing: no`, router `paused: no`. If failing → 3-step re-seed per `docs/auth-recovery.md` (mint on the browser box via `scripts/mint_refresh_token.py`; token travels via file/stdin, **NEVER pasted into chat** — durable memory `feedback_oauth_token_handling.md`)
  - [x] 0.5 Confirm the worker (which owns the drainer + real Graph adapter, Contract Pin 3) is alive: `mailbot status` sync heartbeat fresh, and `docker compose logs --tail 50 mailbot-api` shows worker activity
  - [x] 0.6 Record DB baselines into evidence: `SELECT COUNT(*) FROM pending_actions;` + `SELECT COUNT(*) FROM action_history;` + last `router_calls.id` (use the `docker compose exec -T mailbot-api python -c "import sqlite3..."` pattern — the image has NO sqlite3 CLI)
  - [x] 0.7 If walking Path A (Discord entry): verify Hermes MCP discovery by asking Hermes to list its `mcp_mailbot-api_*` tools (renders `mcp_mailbot_api_*` all-underscore in Discord — cosmetic) — *(not reached: the Path A turn died at Hermes's chat completion (F1) before any tool interaction; MCP discovery previously L3-validated in 9.5.2)*

- [x] **Task 1 — Stage the walk (AC-1)**
  - [x] 1.1 Adam creates (or designates) the sacrificial folder in the live Outlook mailbox (suggested name: `MailBot-UAT-10-1`); record its display name
  - [x] 1.2 Obtain the sacrificial folder's **Graph folder id** — e.g. one-off script inside the container using the existing GraphClient/token seam: `GET /me/mailFolders?$filter=displayName eq 'MailBot-UAT-10-1'` → record `id`. Redact any access token from captured output
  - [x] 1.3 Adam selects a low-value subject email that **exists in the local DB** (the drainer's Tier-1 lenient check reads the local emails row — Contract Pin 1c). Find it via a read verb (`find_emails`) or SQL; record its `email_id` (Graph immutable id), subject, and **current folder as seen in the Outlook client** (the local DB has NO folder column — Contract Pin 6; the Outlook client is the only source of the source-folder fact)
  - [x] 1.4 **Pause before propose:** `docker compose exec -T mailbot-api python scripts/mailbot.py pause` — the drainer tick gate honors pause; without it the move dispatches ~2s after propose and Stage-1 evidence is uncapturable (Contract Pin 4)

- [x] **Task 2 — Fire the chain: propose → authorization evidence → resume → drain → Graph dispatch (AC-2)**
  - [x] 2.1 Propose. **Path A (preferred, user-realistic):** Discord → Hermes: e.g. *"move the email '<subject>' to the MailBot-UAT-10-1 folder"* and observe Hermes call `propose_action`. **Risk:** Hermes must pass `payload={"destination_folder_id": "<id from 1.2>"}` — a missing key silently retargets the move to `inbox` (Contract Pin 2). Inspect the queued row's `payload` BEFORE resuming; if the folder id is wrong/absent, abort the row **while still paused** via direct SQL (`UPDATE pending_actions SET status='cancelled', terminal_at=<now ISO-Z> WHERE id=:id AND status='pending'` — `cancel_action` CANNOT do this, see PIN 9; record the manual intervention verbatim in evidence), record the finding (likely a FILED defect: agent/skill doesn't know folder ids), and fall back to **Path B:** direct MCP `propose_action(email_id=<id>, action_type="move_to_triage_folder", payload={"destination_folder_id": "<id>"})`. Record which path ran (9.5.x Path-γ/B naming convention)
  - [x] 2.2 **Stage-1 evidence (queued intent):** run the Stage-1 SQL (Dev Notes § Evidence SQL) → expect `status='pending'`, `tier=1`, `action_type='move_to_triage_folder'`, `proposed_by_grant_id=NULL`, `change_marker_at_propose=NULL`, payload carries the correct `destination_folder_id`
  - [x] 2.3 **Stage-2 evidence (grant/authorization, per AC pin):** capture the Tier-1 authorization model: (a) `ACTION_PROPERTIES` pin cite, (b) live `mint_grant(action_type="move_to_triage_folder", ...)` → expect `GRANT_NOT_NEEDED` refusal (this is the proof the "grant" stage is N/A by construction), (c) note the drainer check that will run is `_check_tier_1` (lenient, no grant)
  - [x] 2.4 **Resume + drain:** `mailbot resume` → drainer claims within ~2s. **Stage-3 evidence (drainer dispatch record):** action_history row (`pre_state='{}'` — capture this verbatim; it IS the 10.2 gap) + `pending_actions` terminal state (`status='applied'`, `terminal_at` set, `failure_reason=NULL`, `budget_consumed=0`)
  - [x] 2.5 **Stage-4 evidence (Graph write audit trail):** `docker compose logs mailbot-api` — capture the `action.drainer.*` log lines for this action_id (Tier-1 has NO Discord notification either way — Contract Pin 5; logs + DB are the only audit surface). Record the dispatched call shape: `POST /me/messages/{email_id}/move` body `{"destinationId": "<folder id>"}`
  - [x] 2.6 **Negative evidence:** `router_calls` gained no row for this action (Contract Pin 7) — capture the last-id check vs the 0.6 baseline

- [x] **Task 3 — Verify in Outlook client + observe the delta-sync side effect (AC-2 final clause)**
  - [x] 3.1 Adam opens the Outlook client (web or desktop): the subject email is physically inside `MailBot-UAT-10-1`. Screenshot or signed attestation into evidence — a 2xx alone does NOT discharge this clause
  - [x] 3.2 Observe the local-DB side effect: `mailbot sync-now`, then re-query the subject email's row. Migration 005 predicts an email moved out of the synced folder set may surface as `removed_reason='changed'` on the next delta. Record what ACTUALLY happens (either outcome is evidence, not a failure) — direct 10.2 input: a revert must also reconcile the local row

- [x] **Task 4 — Manual restore, mailbox as found (AC-3)**
  - [x] 4.1 Adam manually drags/moves the email back to its original folder **in the Outlook client**. Do NOT restore via `propose_action("move_to_inbox"/"move_to_user_folder")` — that is a second, unwalked, grant-gated Tier-2 write path, out of this walk's scope
  - [x] 4.2 Document the restore procedure step-by-step in the evidence (this is the AC's "restore procedure is documented")
  - [x] 4.3 `mailbot sync-now` again; re-query the local row; record the post-restore local state. Confirm mailbox as found (email in original folder, sacrificial folder may remain for 10-2 reuse — record the choice)

- [x] **Task 5 — pre_state findings for Story 10.2 (AC-3 second clause)**
  - [x] 5.1 Write an explicit `## pre_state field list for Story 10.2` section in the evidence, recording at minimum: **source folder id** (Graph `parentFolderId` — observed from where? record the only viable capture point, since the local DB has no folder column — Contract Pin 6), and anything else observed: folder displayName↔id mapping need, whether the Graph **immutable id survived the move** (verify live — the sync layer assumes immutable ids per Story 1-10), local-row `removed_reason` behavior from 3.2, changeKey behavior if observed
  - [x] 5.2 Note capture-timing recommendation for 10.2: pre_state must be written **before the Graph dispatch fires**, and a dispatch-failed move must NOT record a misleading pre_state (mirrors 10.2's AC wording)

- [x] **Task 6 — README doc-drift discharge, same story same commit (AC-4)**
  - [x] 6.1 Update README.md:357 (`- **Folder moves not live-walked.**` …) to the walk's true post-state (e.g., walked once at L3 against a sacrificial folder, single email) + append `<!-- verified 10-1, run_id <action_id>/<date> -->` (use the `pending_actions.id` + walk date as the run_id — this walk has no benchmark run_id). Keep README.md:358 (no auto-revert) **as-is** — still true until 10-2 ships
  - [x] 6.2 Add a short worked folder-move example (modeled on the archive example README.md:122-130) showing the REAL captured shape from Task 2/3, tagged with the same verified comment — this is the "README's folder-move example" the AC names
  - [x] 6.3 Tier-table check (README.md:120 says `move (batch)` is Tier 2): verify against `ACTION_PROPERTIES` (`mailbot_api/actions/types.py`) which move-family members are Tier-1 vs Tier-2, and correct the row **only if it misstates the walked reality** (`move_to_triage_folder` is Tier-1 — silent, no grant). Hard-assert applies to command names + error codes; the tier table is a factual claim in the walked example's family, so a mismatch is in-scope doc-drift for THIS story
  - [x] 6.4 FLAG, do not fix: the common-errors table body counts **16 data rows** (README.md:273-288), not the 17 the epic charter states — record as a finding for 10-6/10-7 scope accounting (FILED-class bookkeeping, not a walk failure)

- [x] **Task 7 — Compose `10-1-walk-evidence.md`**
  - [x] 7.1 Structure per the 9.5.2-walk-evidence conventions: `## Session header` table (date+TZ, commit at start/end, Hermes image sha, Discord channel, executor split "Adam does X / Claude does Y", Adam signature line) → per-AC `## Section N — AC-x` each opening `**Adam-signed verdict: PASS / PARTIAL-PASS / FAIL.**` → evidence blocks (SQL dumps as tables, chat transcripts as blockquotes, CLI output fenced + "verbatim" noted) → `## Walk-discovered findings (F-track)` table (severity | finding | disposition — disposition is FILED unless it's 10.2's pre-declared scope) → `## Footer` (end-of-walk `git status`, gate counts, corrections-appended-never-rewritten rule honored)
  - [x] 7.2 Honesty rules: signed blocks are never rewritten — corrections are appended as amendment banners; every induced condition tagged honestly (this walk should have none — it's a happy-path walk)

- [x] **Task 8 — Run-flags, sprint flip, stage (never commit autonomously)**
  - [x] 8.1 CREATE `_bmad-output/implementation-artifacts/epic-10-run-flags.md` (does not exist yet; model on `epic-9-5-run-flags.md`) and append the Story 10-1 walk record (path A/B choice, findings, any halts)
  - [x] 8.2 CR cadence determination per AC-5: zero criteria fire if no code was touched → record "CR skipped per cadence binding" in the story's Dev Agent Record; if ANY code fix shipped in-walk, escalate per §5.12 instead
  - [x] 8.3 Flip `sprint-status.yaml` `10-1-live-folder-move-walk-sacrificial-outlook-folder` → `review` at walk close, → `done` on Adam's signed verdicts; update `last_updated`
  - [x] 8.4 Stage all changes (`rtk git add`); Adam decides the commit (walk evidence + README must land in the SAME commit per doc-drift rule (a))

## Dev Notes

### RUN-MODE BINDING enforcement

Per the Epic 9.5 durable end-state (double-encoding: story-file banner + sprint-status marker; see `epic-9-5-run-flags.md` §"Story 9.5.3 Run 1/Run 2"), this story is **NOT compatible with `/autonomous-story-run` OR manual `dev-story` invocation**. The ACs require: creating a folder in Adam's real Outlook mailbox, verifying a physical move in the Outlook client, and manually restoring the email — none of which a dev agent can perform. Zero real Anthropic spend, but REAL mailbox mutation (one email, one folder).

If a dev agent picks this up regardless:
1. Log the halt in `epic-10-run-flags.md` (create if absent) matching the epic-9-5 halt pattern
2. Do NOT author code; do NOT propose/drain any action
3. Return control to Adam with a "walk story — Adam-hands-on required" message

### Code-reality contract pins (each verified against source at baseline_commit)

- **PIN 1 — MOVE_TO_TRIAGE_FOLDER is Tier-1, grant-impossible.** `mailbot_api/actions/types.py:59` (`= "move_to_triage_folder"` — the string that lands in SQL/payload); `types.py:197-203` (`tier=1`, `reversibility_window_hours=24`, `change_marker_required=False`, `budget_against=None`, `requires_sensitivity_token=False`); `requires_grant` → False (`types.py:329-337`); `mint_grant` refuses Tier-1 with `GRANT_NOT_NEEDED` (`actions/authorization.py:121-128`). Drainer authorization for this row is `_check_tier_1` (`actions/drainer.py:277-295`): NO grant check, lenient AR-D4-2 only — fails `target_deleted` if the local email row is missing/deleted. `email_id` is REQUIRED (not in `EMAIL_LESS_ACTIONS`, `types.py:346`); Tier-1 propose with `email_id=None` → `INVALID_PAYLOAD`. Note: `EMAIL_NEVER_SYNCED` fires only on the Tier-3 change-marker path — a Tier-1 propose does NOT hit the email lookup at propose time (`actions/propose.py:126,151-156,267-268`).
- **PIN 2 — Destination folder is payload-only; missing key silently targets inbox.** `actions/outlook_adapter.py:140`: `POST /me/messages/{id}/move`, body from `_body_move` (`:65-72`) = `{"destinationId": payload["destination_folder_id"]}` with fallback `_DEFAULT_FOLDERS.get(action_type, "inbox")` — and MOVE_TO_TRIAGE_FOLDER is NOT in `_DEFAULT_FOLDERS` (`:129-133`). There is NO triage-folder env var or config anywhere. **The walk MUST set `payload["destination_folder_id"]` to the real sacrificial folder id and verify it in the queued row before resuming.**
- **PIN 3 — The real Graph adapter lives ONLY in the worker process.** `drainer.run_tick`/`run_loop` default `adapter=None` → `FakeGraphWriteAdapter` (always ok=True; `actions/drainer.py:425-426`, `actions/graph_write.py:35-40`). The real `OutlookGraphWriteAdapter` is bound only in `worker.py:305-307` + `:381-385` (continuous drainer task, launched by `docker/entrypoint.sh:19` backgrounding `python -m mailbot_api.worker`). **Never drive `run_tick` from an ad-hoc script — it produces a false-positive `applied` with zero mailbox change.** The container's own worker is the walk's dispatch engine.
- **PIN 4 — Timing + pause choreography.** Drainer ticks every 2s (`DEFAULT_TICK_INTERVAL_SECONDS=2.0`, `drainer.py:68`); a Tier-1 propose drains ~2s later. `run_tick` honors the pause gate (`drainer.py:437-446`) → `mailbot pause` BEFORE propose to capture Stage-1 evidence, `mailbot resume` to fire the drain. Cooling-off (`MAILBOT_COOLING_OFF_SECONDS`, default 60) is Tier-3-send-only — NOT on this path. Retry chain on dispatch: 429/503 backoff (1,4,16s), 4xx fail-fast (`outlook_adapter.py:240-313`).
- **PIN 5 — Tier-1 failure is SILENT.** `_notify_failure` returns immediately for tier 1 (`drainer.py:372-373`) — no Discord notification on success OR failure. Audit surface = DB rows + `action.drainer.*` log lines only.
- **PIN 6 — The local DB does not know folders.** No folder/parentFolderId column exists on `emails` (verified across all migrations). Source folder id is observable ONLY from Graph/Outlook at capture time → this IS the 10.2 pre_state gap this walk documents. Related: `005_emails_removed_reason.sql:5` — an email moved out of the synced folder set surfaces as `removed_reason='changed'` on the next delta sync; Task 3.2 observes this live.
- **PIN 7 — router_calls stays empty; $0 spend.** The propose/drain/adapter path never calls `ask_router` — expect NO new `router_calls` row (capture as negative evidence). No Anthropic spend on this walk; if any appears, something else ran.
- **PIN 8 — Revert today = INVERSE_UNAVAILABLE.** `actions/reverter.py:46-51` (inverse map excludes moves) + `:162-171` (returns `INVERSE_UNAVAILABLE`, message names the missing pre_state); `_build_pre_state` returns `{}` for every action (`drainer.py:219-227`), so `action_history.pre_state='{}'` today. The `pre_state` column already exists (`017_action_history.sql:13`) — 10.2 populates it; this walk documents WHAT it must hold.
- **PIN 9 — There is NO user-facing abort for a wrong Tier-1 pending row.** `cancel_action` atomically flips ONLY `cooling_off` → `cancelled` (Tier-3 SEND rows; `actions/cancel.py:1-5,34-63` — the `AND status='cooling_off'` guard makes it a no-op on `pending`). Combined with PIN 4 (~2s drain) this means a mis-targeted Tier-1 move is user-unstoppable once proposed unless the router is paused. The walk's pause choreography is the ONLY safe abort window; if the abort path is exercised (Task 2.1), record the "no user-facing Tier-1 abort" observation as a walk finding (FILED-class candidate, not fixed here).

### Evidence SQL (verbatim; run via `docker compose exec -T mailbot-api python -c "import sqlite3; ..."` — image has no sqlite3 CLI)

```sql
-- Stage 1: queued intent (after propose, while paused)
SELECT id, email_id, action_type, tier, payload, proposed_at, proposed_by_grant_id,
       change_marker_at_propose, status, retry_count, failure_reason, terminal_at, budget_consumed
FROM pending_actions WHERE id = :action_id;
-- expect: status='pending', tier=1, action_type='move_to_triage_folder',
--         proposed_by_grant_id=NULL, change_marker_at_propose=NULL,
--         payload JSON contains the sacrificial destination_folder_id

-- Stage 2: grants — expect ZERO rows for this action type (Tier-1, grant-impossible)
SELECT id, action_type, email_ids, expires_at, minted_at, revoked_at
FROM action_grants WHERE action_type = 'move_to_triage_folder';

-- Stage 3: drainer history row (written BEFORE dispatch, CR-4-4-2)
SELECT action_id, pre_state, applied_at, reverted_at
FROM action_history WHERE action_id = :action_id;
-- expect: pre_state='{}' (the 10.2 gap — capture verbatim), reverted_at=NULL

-- Stage 4: terminal state after drain
SELECT status, terminal_at, failure_reason, budget_consumed
FROM pending_actions WHERE id = :action_id;
-- success: status='applied', terminal_at set, failure_reason=NULL, budget_consumed=0

-- Negative evidence: no Router involvement
SELECT id, ts, task_type, caller_verb, email_id, outcome
FROM router_calls ORDER BY id DESC LIMIT 5;  -- compare last id vs Task 0.6 baseline
```

Column-name gotcha (9.5.2 sibling finding): `router_calls` uses `task_type` / `model_chosen` — not `task` / `model_used`.

### README oracle anchors (walk targets + doc-drift surface)

- README.md:12 — propose→grant→cool-off write-back diagram line (context)
- README.md:115-120 — tier table; **:120 `| 2 | archive, move (batch) | approve the batch grant in chat |`** — Task 6.3 tier-check target
- README.md:122-130 — Tier-2 batch archive worked example (the analog to model the new move example on)
- README.md:203-212 — operator CLI table (`status` :207, `sync-now` :210, `replay` :211, `revert` :212 — revert is Tier-1-only and will NOT cover this move until 10-2)
- README.md:227-230 — `mailbot status` ACTIONS block fields to assert on during the walk
- README.md:271-288 — common-errors table; relevant codes: `pending_grant` (:277), `state_drift_etag`/`target_deleted`/`state_drift_noop` (:287), `INVALID_ACTION_TYPE` (:288). **Row-count finding: body has 16 data rows, epic charter says 17 — Task 6.4 flags it**
- README.md:352-361 — Limitations; **:357 "Folder moves not live-walked" is THE claim this walk discharges**; :358 "Triage-move has no auto-revert yet" stays true until 10-2
- No `<!-- verified -->` tag exists anywhere in the README yet — this story introduces the convention (format: `<!-- verified 10-1, run_id ... -->` per the epic done-flip clause 3)

### Live-stack operational facts (from 9.5.x walk records)

- Bring-up: `docker compose ps` → `mailbot-api` healthy + `mailbot-hermes` up + `mailbot-ollama` healthy; `curl http://localhost:8000/health` → 200. Hermes depends_on mailbot-api service_healthy; mailbot-api depends_on ollama service_healthy; warmup service pulls qwen2.5:3b-instruct-q4_K_M + nomic-embed-text (idempotent)
- Hermes MCP session is LAZY — established on first tool call, lost across `docker compose down mailbot-api`, reconnects on next user prompt. Gateway log inside container: `/opt/data/logs/gateways/default/current`
- Host `router/policy.user-overrides.yaml` must exist as a FILE before first `up` (else Docker creates a directory)
- Single-user Adam-only deploy; 9.5.x walks ran in Adam DM; `DISCORD_HOME_CHANNEL` is the Hermes-side env var
- OAuth escape hatch: `docs/auth-recovery.md` 3-step re-seed — mint (`scripts/mint_refresh_token.py`, browser box, token printed between `=====` markers) → persist (`scripts/refresh_outlook_oauth.py` from stdin/file, never CLI arg; DB `oauth_state` row is source of truth, `.env` seed never re-read) → confirm (`scripts/check_graph_auth.py` + `mailbot status`). Router auto-pauses after 3 consecutive refresh failures (`reason: oauth_refresh_failing`) and auto-resumes on recovery
- Env that matters here: `MAILBOT_DB_PATH=/data/mailbot.db`, `OUTLOOK_CLIENT_ID/TENANT_ID/REFRESH_TOKEN` (+`OUTLOOK_CLIENT_SECRET`/`OUTLOOK_PUBLIC_CLIENT`), `MAILBOT_ROUTER_KEY`. No folder-related env exists (PIN 2)

### Testing requirements

No new tests — walk story. The full suite baseline at baseline_commit is **1695 passed + 2 skipped + 3 deselected**; it must remain green at walk close (expected trivially: only README + evidence + tracking files change). Run the 4 gates for the evidence footer per the 9.5.x convention. Any code change voids this section and escalates CR per §5.12.

### Project Structure Notes

Files this story may touch — and ONLY these:
- `README.md` (doc-drift discharge, Task 6)
- `_bmad-output/implementation-artifacts/10-1-walk-evidence.md` (new)
- `_bmad-output/implementation-artifacts/epic-10-run-flags.md` (new — first Epic 10 run-flags file)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status flips)
- this story file (checkboxes, Dev Agent Record)

ZERO changes under `mailbot_api/`, `scripts/`, `router/`, `hermes-config/`, `docker/`, `tests/`. Walk-discovered defects → FILED per N.5 (except 10.2's pre-declared pre_state/revert scope, which is deliberately NOT fixed here either — it is 10.2's job, informed by this walk's Task 5 findings).

### References

- [Source: _bmad-output/planning-artifacts/epics.md § "Epic 10 Detail" + § "Story 10.1"] — epic identity, D1-D4 decision record, doc-drift rules (a)/(b), done-flip gate, story ACs (verbatim here)
- [Source: mailbot_api/actions/types.py §ACTION_PROPERTIES; actions/propose.py; actions/authorization.py; actions/drainer.py; actions/outlook_adapter.py; actions/reverter.py; actions/graph_write.py; worker.py; docker/entrypoint.sh] — contract pins 1-8
- [Source: mailbot_api/db/migrations/015_pending_actions.sql, 016_action_grants.sql, 017_action_history.sql, 005_emails_removed_reason.sql] — evidence schema + delta-sync side-effect prediction
- [Source: README.md:12,115-130,203-212,227-230,271-288,352-361] — oracle anchors
- [Source: _bmad-output/implementation-artifacts/9.5.2-model-live-walks-bundle.md + 9.5.2-walk-evidence.md + epic-9-5-run-flags.md] — walk-story shape, RUN-MODE BINDING double-encoding, evidence conventions, halt precedents
- [Source: docs/auth-recovery.md] — OAuth re-seed procedure
- [Source: memory feedback_oauth_token_handling.md, feedback_l1_l2_l3_done_layers.md, project_epic_6_scope_cleave.md (N.5), project_local_viability_over_deployment.md (D4)] — durable rules binding this walk

## Dev Agent Record

### Agent Model Used

claude-fable-5 (Claude Fable 5) — context-engineering + Claude-assisted walk execution, same session. Adam-hands-on per RUN-MODE BINDING (folder creation, Discord prompt, Outlook verification, drag-and-drop restore, Path B green-light).

### Debug Log References

- `10-1-walk-evidence.md` (all stage evidence, verbatim SQL/log/Graph captures)
- `epic-10-run-flags.md` § "Story 10-1 Run 1" (path decisions, CR determination)

### Completion Notes List

- Context-engineered 2026-07-05 (create-story). Ultimate context engine analysis completed - comprehensive developer guide created. Three-agent artifact sweep (README oracle / write-chain code / walk precedents); 8 code-reality contract pins verified at baseline_commit (a 9th — no user-facing Tier-1 abort — added during checklist validation); AC interpretation pins added for the Tier-1-vs-"grant" wording and the missing README move example.
- Walk executed same session, Adam-hands-on. Full chain L3-verified: propose (id=4) → Tier-1 authorization (live `GRANT_NOT_NEEDED`) → drain → real Graph dispatch → **Adam-verified in desktop Outlook** → manual drag-and-drop restore → server-side back-in-Inbox confirmed. $0 spend, `router_calls` untouched.
- **Path A (Discord) blocked by F1** (pause kills Hermes chat); Path B (direct verb, Adam-green-lit) executed per the story's pre-authorized fallback. Optional Path A′ declined on safety rationale (F4+F6 interaction).
- **Findings F1-F6 + B1 ALL FILED per N.5, zero code changed.** Headline: **F4 CRITICAL — `mailbot pause` does not gate the worker-process drainer** (per-process in-memory `PauseState`); the drainer dispatched the real Graph write 259 ms after propose while paused. Also F5 (move soft-deletes local row as `'deleted'`) + F6 (`EMAIL_UPSERT` never resurrects) — the walk subject email is deliberately left soft-deleted locally as live evidence for 10-2/10.5 triage.
- pre_state field list for Story 10.2 delivered (evidence §5): source_folder_id from Graph pre-dispatch (mandatory; local DB has no folder column), immutable graph_id as revert handle, changeKey drift-only, revert must also repair the local row (F5/F6), failed dispatch must not record misleading pre_state.
- README doc-drift discharged same story (AC-4): tier-table row 1 correction, verified pipeline-trace example (deliberately not a fabricated chat transcript), limitations rewrite; `<!-- verified 10-1, run_id action-4/2026-07-05 -->` convention introduced (first verified tags in the README).
- CR cadence (AC-5): zero criteria fire — no code authored; CR skipped per cadence binding.
- Gates at walk close: ruff clean on tracked tree (2 pre-existing T201 in untracked `scratch/` from a prior session, out of scope), mypy clean (129 files), boundary checker clean; pytest suite result recorded in evidence footer.

### File List

- `_bmad-output/implementation-artifacts/10-1-live-folder-move-walk-sacrificial-outlook-folder.md` (this file)
- `_bmad-output/implementation-artifacts/10-1-walk-evidence.md` (new)
- `_bmad-output/implementation-artifacts/epic-10-run-flags.md` (new)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status flips)
- `README.md` (doc-drift discharge: tier table, verified example, limitations)
