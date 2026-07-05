# Story 10-1 walk evidence — Live folder-move walk, sacrificial Outlook folder (Adam-hands-on, Claude-assisted)

## Session header

| Field | Value |
| --- | --- |
| Session date | 2026-07-05 (Europe/Paris) |
| mailbot-api commit at walk start | `5222589d0b6ef51cc71c53cd720d9c9848367677` (== story baseline_commit; tree dirty only with Story 10-1 tracking/story files) |
| Code state at walk completion | `5222589` + docs/evidence/tracking changes only (zero code); 5 files staged in one commit per doc-drift rule (a) |
| Hermes image | `nousresearch/hermes-agent:latest` @ `sha256:27195f1cfec04c5c585a63f6524ba44b88858df857c4b7168baad576f584054e` |
| Discord channel | _pending (Path A only)_ |
| Walk executor | Adam: mailbox-touching actions (folder create, Discord prompts, Outlook verification, manual restore) + all verdict signatures. Claude: read-only checks, SQL evidence capture, log reads, evidence drafting. |
| Spend authorization | $0 expected (no Router calls on this path — Contract Pin 7) |
| Adam signature | signed Adam Maroni 2026-07-05 — all 5 AC verdicts PASS ("Sign all PASS") |

**Execution mode:** live local Docker stack against Adam's real mailbox, per Epic 10 D4 (local-stack-first). Walk protocol per story Tasks 0-8 with pause-before-propose choreography (Contract Pin 4).

---

## Section 0 — Task 0: Pre-walk stack + OAuth verification (BLOCKING gate)

**Verdict: PASS** (all 7 checks green; 4 status-board warnings recorded, none walk-blocking).

- 0.1 `git rev-parse HEAD` = `5222589d0b6ef51cc71c53cd720d9c9848367677` == baseline_commit ✅. Working tree dirty only with: `.claude/settings.json` (session-local), `sprint-status.yaml` (10-1 flip), story file (untracked), `scratch/` (untracked) — no code drift.
- 0.2 `docker compose ps` ✅: `mailbot-api` Up 29 min (healthy), `mailbot-hermes` Up 44 h, `mailbot-ollama` Up 2 days (healthy).
- 0.3 `curl http://localhost:8000/health` → **200** ✅.
- 0.4 `mailbot status` (verbatim key lines) ✅:
  - OAUTH: `refresh failing: no`, `consecutive fails: 0`, `rotation count: 244`, `last rotated at: 2026-07-05T08:16:01Z`, `access token: fresh`
  - ROUTER: `paused: no`
  - ACTIONS: `pending by tier: {}`, `awaiting grant: 0`, `failed (24h): 0`
  - SYNC: `last_heartbeat_at: 2026-07-05T08:53:58Z`, `last_outcome: ok`, `minutes_since: 1.6`
  - Warnings recorded (exit 1, 4 warnings — none walk-blocking):
    1. BUDGET month `$70.2359 / $30.00 cap (234.1%)` → **degraded mode: yes**. Not a blocker: degraded mode demotes Router model choice only; the move path makes zero Router calls (Pin 7). Budget overage is the Epic 9.5 benchmark spend — pre-existing, not walk-induced.
    2. CACHE hit rate 11.4% — irrelevant to this walk.
    3. ERRORS rows are qwen/haiku ingest-pipeline outcomes (latest id=13539) — irrelevant here; relevant later to Story 10-3.
    4. CONTAINERS `mailbot-hermes: unknown` — Hermes has no healthcheck; container Up 44 h. To be confirmed live at Path A time.
- 0.5 Drainer alive in the worker ✅ (verbatim log excerpt, 2s cadence, real-adapter process per Pin 3):
  ```text
  {"ts":"2026-07-05T08:55:57.429351Z","module":"mailbot_api.actions.drainer","event":"action.drainer.tick.start","prefetch_count":0}
  {"ts":"2026-07-05T08:55:57.429530Z","module":"mailbot_api.actions.drainer","event":"action.drainer.tick.done","prefetch_count":0,"processed_count":0}
  {"ts":"2026-07-05T08:55:59.432152Z","module":"mailbot_api.actions.drainer","event":"action.drainer.tick.start","prefetch_count":0}
  ```
- 0.6 DB baselines (verbatim from live DB, 2026-07-05 ~08:56Z) ✅:
  - `pending_actions` count = **3** — all terminal Epic-6-era `send_reply` rows: `(1, failed, 2026-06-04)`, `(2, applied, 2026-06-06)`, `(3, applied, 2026-06-06)`. Status board's `pending by tier: {}` is consistent (zero non-terminal). **Next action row will be id=4.**
  - `action_history` count = 3; `action_grants` count = 3; last `router_calls.id` = **13539**; `emails` count = 1933.
- 0.7 Hermes MCP discovery — _deferred to Path A decision (needs Adam in Discord)_.

---

## Section 1 — AC-1: Staging (sacrificial folder + subject email + pause)

**Verdict: _pending Adam signature at walk close_** — blast radius bounded to one email + one folder by construction.

- **Sacrificial folder:** `MailBot-UAT-10-1`, created by Adam in desktop Outlook at ~09:00Z, **nested under Inbox** ("Boîte de réception"), `totalItemCount: 0` at staging.
  - Graph folder id (verbatim): `AQMkADAwATYwMAItYTJhYi01MzMAZi0wMAItMDAKAC4AAAMo0axGHnyuT5vdoHoFosMoAQCLEw8Z0ndEQJbnH-wBocYBAAkplpvaAAAA`
  - Discovery notes: the folder was NOT visible at `/me/mailFolders` top level (it is an Inbox child); an intermediate `$expand=childFolders` sweep also missed it (created seconds earlier — desktop-Outlook→server sync lag observed live). Found via `GET /me/mailFolders/inbox/childFolders?$top=50` → 13 children. Adam supplied a desktop-Outlook screenshot as creation proof.
- **Subject email (Adam-selected, low-value):** Railway newsletter "The peaceful way to ship software, static outbound IPs and I…", received 2026-07-03, `class_coarse=newsletter`, `sensitivity=normal`, `deleted_at=NULL`, `removed_reason=NULL`.
  - `graph_id` (verbatim, = the immutable id `pending_actions.email_id` carries): `AAkALgAAAAAAHYQDEapmEc2byACqAC-EWg0AixMPGdJ3RECW5x-8AaHGAQAJKZe9rgAA`
- **Pre-move state captured live from Graph BEFORE any propose** (2026-07-05 ~09:01Z, read-only `GET /me/messages/{id}?$select=parentFolderId,subject,changeKey` via the container's own oauth seam; access token never surfaced):
  - `parentFolderId`: `AQMkADAwATYwMAItYTJhYi01MzMAZi0wMAItMDAKAC4AAAMo0axGHnyuT5vdoHoFosMoAQCLEw8Z0ndEQJbnH-wBocYBAAACAQwAAAA=` — **byte-identical to the well-known Inbox id** (`GET /me/mailFolders/inbox`), confirming Adam's "sits in Inbox" observation and the numbered-child-folder structure does not apply to this email.
  - `changeKey`: `CQAAABYAAACLEw8Z0ndEQJbnH/wBocYBAAkoiHVJ`
  - Local-DB cross-check: `emails` has **no folder column** (PRAGMA table_info verified live — 52 columns, none folder-related) → the local DB could NOT have supplied this fact (Contract Pin 6 verified at L3).
- **Pause engaged (Task 1.4, pre-propose):** `mailbot pause` at 2026-07-05T09:04:33Z → `router.paused, reason: "manual cli pause"` (log verbatim). Drainer tick gate now no-ops.

---

## Section 2 — AC-2: The chain (propose → authorization evidence → drain → Graph dispatch)

### 2.1 Path A attempt (Discord → Hermes) — FAILED-BY-DESIGN-CONFLICT, findings filed

**Adam Discord prompt (verbatim, 2026-07-05 11:06 CEST / 09:06Z, router paused per Task 1.4):**

> move the Railway email "The peaceful way to ship software" to the folder MailBot-UAT-10-1

**Mailbot (Hermes) responses (verbatim from Discord):**

> ⚠ Retrying in 4.3s (attempt 2/3)...
> ❌ API failed after 3 retries — HTTP 502: Error code: 502 - {'detail': {'error': {'type': 'router_error', 'message': 'router paused'}}}
> API call failed after 3 retries: HTTP 502: Error code: 502 - {'detail': {'error': {'type': 'router_error', 'message': 'router paused'}}}

**Post-attempt DB check (verbatim):** `pending_actions` MAX(id)=3 (unchanged), non-terminal rows=0, last `router_calls.id`=13539 (unchanged). The turn died at Hermes's own chat completion (`hermes_aux` via `POST /v1/chat/completions` → `ask_router` → PAUSED); `propose_action` was never invoked.

**Walk-discovered findings (F-track, FILED per N.5 — not fixed in-walk):**

- **F1 — Pause choreography is mutually exclusive with the Discord entry path for Tier-1 actions.** Router pause (the ONLY safe pre-inspection window for a Tier-1 propose, per story Contract Pins 4+9: ~2s drain, no user-facing abort) also blocks Hermes chat itself, because Hermes's reasoning routes through mailbot-api `/v1/chat/completions`. Net: a user cannot both (a) propose a Tier-1 move via Discord and (b) inspect it before it fires. Design-gap candidates for a future story: pause granularity (drainer-pause vs router-pause) or a Tier-1 propose-hold window.
- **F2 — Hermes's "emergency fallback" direct-Anthropic key did NOT engage** on 3× 502 from its primary provider; the turn hard-failed with raw HTTP error text surfaced to the user (README doc-drift adjacent: error prose in Discord is raw, not the documented friendly refusal shape — soft-assert territory, recorded not failed).
- **F3 (micro) — Paused refusals write no `router_calls` audit rows** (last id unchanged across 2 refused turns). Whether PAUSED refusals should audit is a design question for the audit-trail contract; recorded for 10-6's `PAUSED` fault-injection row.

### 2.1(b) Path decision

Path A recorded as blocked-by-F1. Per the story's pre-authorized fallback, the propose entry switches to **Path B: direct MCP `propose_action`** with the exact staged payload, while paused — preserving the full Stage-1→4 evidence chain. _Path decision Adam sign-off: pending below._

### 2.2 Path B chain — all four stages captured; **pause bypass discovered (F4)**

**Propose (2026-07-05T09:09:46.449Z, Adam-green-lit "go"; verb-level invocation in-container — the same `mailbot_api/verbs/propose_action.py` function the MCP tool wraps; MCP HTTP transport itself was L3-validated in 5-2/9.5.2):**

`propose_action(email_id=<Railway graph_id>, 'move_to_triage_folder', {'destination_folder_id': <MailBot-UAT-10-1 id>})` returned (verbatim):

```json
{"ok": true, "action_id": 4, "tier": 1, "status": "pending", "error": null,
 "requires_grant": false, "requires_per_action_confirmation": false, "recovery_action": null}
```

**⚠ F4 — CRITICAL walk finding: the drainer dispatched WHILE THE ROUTER WAS PAUSED.** Row id=4: `proposed_at 09:09:46.449Z` → `terminal_at 09:09:46.708Z` (**259 ms**), despite `mailbot pause` engaged at 09:04:33Z and never lifted (Hermes chat was refused with PAUSED at 09:06 — Section 2.1). Root cause (code-read diagnosis only, NO fix per N.5): `mailbot_api/router/pause.py:21-34,93-97` — `PauseState` is an in-process module singleton; `is_paused()` returns an in-memory flag hydrated from SQLite only in `initialize()` at boot; `pause()` writes the DB and flips the flag **in the API process only**. The drainer runs in the separate worker OS process (`docker/entrypoint.sh:19`), whose own `_PAUSE_STATE` never re-reads the DB → the drainer's pause gate (`drainer.py:437-446`) is dead code in the production two-process topology. **Safety-relevant: the documented kill-switch does not cover mailbox writes.** The walk's pause-before-propose choreography (story Contract Pin 4) is therefore VOID in production topology — Stage-1 pre-drain inspection was impossible; blast-radius-by-construction (correct payload, sacrificial target) was the only real containment, vindicating AC-1's staging discipline. FILED for Epic 10.5-candidate triage.

**Stage evidence (all verbatim from live DB/logs):**

- **Stage 1 — queued intent:** the verb's return value captured `status: "pending"` at creation (above); full row dump post-drain: `id=4, email_id=<Railway graph_id>, action_type='move_to_triage_folder', tier=1, payload={"destination_folder_id": "<MailBot-UAT-10-1 id>"}, proposed_at=2026-07-05T09:09:46.449527Z, proposed_by_grant_id=None, change_marker_at_propose=None, retry_count=0, failure_reason=None, budget_consumed=0`. Payload verified byte-correct against the staged folder id.
- **Stage 2 — grant/authorization evidence (per AC interpretation pin):** live `mint_grant('move_to_triage_folder', [], now+1h)` → refused (verbatim): `{"ok": false, "error": {"code": "GRANT_NOT_NEEDED", "message": "action_type 'move_to_triage_folder' (tier 1) does not require a grant (Tier 0 verbs are never queued; Tier 1 is auto-approved per FR-5.1)"}}`. `action_grants` rows for this action_type: **0**. Authorization that actually ran = Tier-1 lenient check (`_check_tier_1`), by construction.
- **Stage 3 — drainer dispatch record:** `action_history` row (verbatim): `(4, '{}', '2026-07-05T09:09:46.479725Z', None)` — **`pre_state='{}'` live-proven** (the Story 10.2 gap), written pre-dispatch (applied_at 09:09:46.479 precedes terminal_at .708, consistent with CR-4-4-2 write-before-dispatch).
- **Stage 4 — Graph write audit trail:** drainer log (verbatim): `{"ts":"2026-07-05T09:09:46.714025Z","event":"action.drainer.row.applied","action_id":4,"action_type":"move_to_triage_folder","tier":1}`. Terminal state: `status='applied', terminal_at=2026-07-05T09:09:46.708432Z, failure_reason=None, budget_consumed=0`. Dispatched call shape: `POST /me/messages/{email_id}/move` body `{"destinationId": "<MailBot-UAT-10-1 id>"}` via the worker-bound real `OutlookGraphWriteAdapter`.
- **Server-side confirmation (read-only Graph re-read, 09:12Z):** `GET /me/messages/{graph_id}?$select=parentFolderId,changeKey` → 200; `parentFolderId` **byte-identical to the sacrificial folder id** (`== True`); `changeKey` advanced `…AAkoiHVJ` → `…AAkoiKY1`. **Immutable-id survival across the move verified live** (same graph_id resolved post-move) — pre_state finding for 10.2.
- **Negative evidence:** `router_calls` MAX(id) still 13539 across the entire chain → zero Router involvement, **$0 spend** (Contract Pin 7 verified at L3). Tier-1 emitted no Discord notification in either direction (Contract Pin 5 observed — channel silent).

**Post-chain state action:** router resumed at ~09:14Z (`mailbot resume` → "router resumed") — pause demonstrably does not gate the drainer (F4), and chat is needed for the optional Path A′ addendum.

_Outlook-client verification (AC-2 final clause) pending Adam's eyes — Section 3._

---

## Section 3 — AC-2 final clause: Outlook-client verification + delta-sync side effect

**Adam attestation (2026-07-05 ~11:15 CEST, desktop Outlook):** "It is inside!" — the Railway email verified physically inside `MailBot-UAT-10-1` in the Outlook client, not merely inferred from the 2xx / Graph re-read.

**Delta-sync side effect (Task 3.2, observed live):** the worker's own sync loop soft-deleted the local row at `2026-07-05T09:09:58.651712Z` — **12 seconds after the move**, before any manual `sync-now` (which then reported `messages_seen=0`). Local row post-move (verbatim): `deleted_at=2026-07-05T09:09:58.651712Z`, **`removed_reason='deleted'`** (NOT the `'changed'` that migration 005's design comment predicts for moved-out-of-synced-folder-set), `change_marker` = stale pre-move changeKey.

- **F5 (FILED) — Move-family actions poison local-DB truth.** Moving an email from Inbox to an Inbox child folder makes the Graph delta report it as removed with reason `'deleted'`: the synced folder set is effectively Inbox-proper only, and the `'changed'`-vs-`'deleted'` distinction (Story 1-10 AC-3, built so "Epic 4's Tier-1 reverter can distinguish recoverable removals from permanent ones", `db/queries.py:155-157`) does not hold live for this move shape. Consequence: after ANY move (bot- or human-initiated), the local DB believes the email is deleted — read verbs exclude it, and local-DB-driven revert logic would consider it gone.

---

## Section 4 — AC-3: Manual restore, mailbox as found

**Restore procedure (documented verbatim per AC):** Adam, in desktop Outlook, **drag-and-drop** of the Railway email from `MailBot-UAT-10-1` back to Inbox ("Boîte de réception"), 2026-07-05 ~11:20 CEST. No MailBot command involved (deliberately — `propose_action(move_to_inbox)` would have been a second unwalked, grant-gated Tier-2 write path).

**Server-side confirmation (read-only Graph re-read):** `GET /me/messages/{graph_id}?$select=parentFolderId` → 200, `parentFolderId == Inbox id` → **True**. Mailbox as found: email in Inbox, sacrificial folder `MailBot-UAT-10-1` retained empty for Story 10-2's revert walk (Adam's staging choice).

**Post-restore sync observation (Task 4.3, verbatim):** `sync-now` → `messages_seen=1 messages_upserted=1 messages_soft_deleted=0`; local row after: `change_marker` advanced to the post-restore changeKey (`…AAkoiKZF`) **but `deleted_at` and `removed_reason='deleted'` remain set**.

- **F6 (FILED) — Delta re-add does not resurrect a soft-deleted row.** `EMAIL_UPSERT` (`db/queries.py:136-152`) updates 9 content fields on conflict but never clears `deleted_at`/`removed_reason`. A moved-away-and-back email (bot move + manual restore, or any user drag-out/drag-back) stays **permanently invisible to read verbs** until a full resync/manual fix. Live proof: the walk's subject email is now back in Inbox on the server yet still soft-deleted locally. (Left as-is at walk close — deliberate: it is live evidence for the 10-2/Epic-10.5 triage; noted in Limitations honesty check.)

---

## Section 5 — AC-3 second clause: pre_state field list for Story 10.2 (direct input)

What this walk proves a move-family revert needs, with live evidence for each:

1. **`source_folder_id` (Graph `parentFolderId`) — MANDATORY.** Captured pre-move only from Graph (`GET /me/messages/{id}?$select=parentFolderId`); the local DB **cannot** supply it (emails table has no folder column — verified live, Section 1). Revert = `POST /me/messages/{id}/move {"destinationId": pre_state.source_folder_id}` via the same worker-bound Graph seam.
2. **Capture point: at drain time, immediately BEFORE the Graph dispatch** — the drainer already writes `action_history` pre-dispatch (live-proven ordering, Section 2.2 Stage 3); the pre_state Graph read belongs in that same window. A dispatch-failed move must NOT record a pre_state that implies a completed move (mirrors 10.2 AC).
3. **`graph_id` (immutable id) is the stable revert handle** — verified live: the same id resolved the message before the move, after the move, and after the restore. Safe key.
4. **`changeKey` is NOT a stable revert precondition** — it mutated on the move (`…HVJ` → `…KY1`) and again on the restore (`…KZF`). Usable only as drift-detection, never as identity. (`change_marker_at_propose` is NULL for Tier-1 by design anyway.)
5. **Revert must also repair the LOCAL row, not just the mailbox** — the move soft-deletes the local row as `removed_reason='deleted'` (F5), and the delta re-add after a successful revert will NOT clear it (F6). 10.2's revert path must either clear `deleted_at`/`removed_reason` on revert success or depend on an F6 fix; otherwise a "reverted" email remains invisible to every read verb.
6. **Optional/nice:** source folder `displayName` at capture time (human-readable evidence + refusal messages), and destination folder id echo (already in `payload`).

---

## Section 6 — AC-4: README doc-drift discharge (same story, same commit)

The README had **no folder-move worked example and zero `<!-- verified -->` tags anywhere** (this walk introduces the convention; tag format `<!-- verified 10-1, run_id action-4/2026-07-05 -->`, run_id = `pending_actions.id` + walk date). Edits shipped in this story's commit:

1. **Tier table row 1** — added `move to triage folder` to the Tier-1 examples (it previously appeared in NO tier row; only Tier-2 "move (batch)" existed, which correctly refers to `move_to_user_folder`/`move_to_inbox`/`archive` per `types.py:205-239`) and qualified the "revertible for 24h" claim with the triage-move exception.
2. **New verified example block** after the archive example — deliberately shaped as a **pipeline trace, NOT a chat transcript**: the chat path demonstrably cannot propose a folder move today (F1 + no folder-name lookup), so a `You:/MailBot:` example would be fabricated. Tagged verified. Caveats stated inline (folder-name resolution missing; moved email drops out of the local view — F5/F6).
3. **Limitations rewrite** — line "Folder moves not live-walked" replaced with the true post-walk state (walked once at L3, one email, sacrificial folder) + verified tag + honest naming of the walk's defects (pause doesn't stop the drainer; moved emails recorded as deleted and not resurrected; chat path can't propose moves). The "no auto-revert" line stays (still true) and its refusal is now **live-confirmed** on this walk's own action: `revert_action(4)` → `{"code": "INVERSE_UNAVAILABLE", "message": "no Tier-1 inverse available for 'move_to_triage_folder' (…pre_state…not yet populated)"}` (verbatim, mutation-free refusal).

**Bookkeeping flag (Task 6.4, not fixed):** the README common-errors table body counts **16 data rows** (README.md:273-288); the Epic 10 charter says "17 error rows". Scope-accounting discrepancy recorded for 10-6/10-7.

### Optional Path A′ addendum — DECLINED (safety rationale)

The offered unpaused Discord retry was **not executed**. Rationale: with F6 live, the subject email is invisible to Hermes's read verbs (soft-deleted locally) → reference resolution could bind a *different* email; with F4 live, a mis-resolved Tier-1 move auto-fires in ~2s with no working pause and no user-facing abort (Contract Pin 9). Blast radius would no longer be bounded by construction. The Discord propose surface is 10-5's walk, after 10-2 ships revert support.

---

## Walk-discovered findings (F-track) — ALL FILED per N.5, zero fixed in-walk

| # | Severity | Finding | Evidence | Disposition |
| --- | --- | --- | --- | --- |
| F1 | HIGH | Router pause blocks Hermes chat (`hermes_aux` routes through `ask_router`) → Discord entry and pre-drain inspection of a Tier-1 action are mutually exclusive | §2.1 Discord transcript | FILED (design gap: pause granularity / Tier-1 propose-hold) |
| F2 | MEDIUM | Hermes "emergency fallback" direct-Anthropic key did not engage on 3× 502; raw HTTP error prose surfaced in Discord | §2.1 | FILED |
| F3 | LOW | PAUSED refusals write no `router_calls` audit rows | §2.1 (max id 13539 unchanged across 2 refused turns) | FILED (input to 10-6 `PAUSED` row) |
| F4 | **CRITICAL** | **Kill-switch does not cover mailbox writes**: `PauseState` is a per-process in-memory singleton (`router/pause.py:21-34,93-97`); CLI pause flips the API process only; the worker-process drainer dispatched a real Graph write 259 ms after propose **while paused** | §2.2 | FILED (Epic 10.5-candidate; safety-relevant) |
| F5 | HIGH | Move to an Inbox child folder soft-deletes the local row with `removed_reason='deleted'` (not `'changed'` per the 1-10/migration-005 design intent) → local DB believes a moved email is gone | §3 | FILED (10-2 direct input) |
| F6 | HIGH | Delta re-add does NOT resurrect a soft-deleted row (`EMAIL_UPSERT` never clears `deleted_at`/`removed_reason`, `db/queries.py:136-152`) → moved-and-restored email permanently invisible to read verbs; live-proven on the walk subject | §4 | FILED (10-2/10.5 triage; subject email left in this state deliberately as live evidence) |
| B1 | bookkeeping | README error-table body = 16 rows vs epic charter "17" | §6 | Recorded for 10-6/10-7 scope accounting |

**Scope fence honored:** zero code changed; the one pre-declared absorbable defect (pre_state/revert) remains 10-2's, with its field list delivered in §5.

---

## Footer — gates, git state, signatures

**4 gates at walk close (host venv, baseline_commit + docs/evidence changes only):**

- pytest: **1695 passed, 2 skipped, 3 deselected** in 224s — byte-identical to the baseline suite count (zero code changed, as expected)
- ruff: clean on the tracked tree (2 pre-existing `T201` in untracked `scratch/walk_bootstrap.py`, a prior-session leftover outside story scope)
- mypy: `Success: no issues found in 129 source files`
- boundary checker: exit 0, clean

**Files changed by this story (all staged in one commit per doc-drift rule (a)):** `README.md`, `10-1-walk-evidence.md` (new), `epic-10-run-flags.md` (new), `10-1-live-folder-move-walk-sacrificial-outlook-folder.md` (story), `sprint-status.yaml`.

**Deliberate residuals at walk close (recorded, not defects of the walk):** walk subject email remains soft-deleted in the local DB (F6 live evidence); sacrificial folder `MailBot-UAT-10-1` retained empty for Story 10-2's revert walk; `scratch/` untracked leftovers untouched.

### Adam-signed AC verdicts

| AC | Verdict | Signature |
| --- | --- | --- |
| AC-1 staging (blast radius bounded) | **PASS** | signed Adam Maroni 2026-07-05 ("Sign all PASS") |
| AC-2 chain + Outlook verification | **PASS** | signed Adam Maroni 2026-07-05 ("Sign all PASS") |
| AC-3 restore + pre_state field list | **PASS** (signed knowing the F6 local-DB residual: mailbox as found; local row deliberately left soft-deleted as live evidence) | signed Adam Maroni 2026-07-05 ("Sign all PASS") |
| AC-4 README doc-drift + verified tag | **PASS** | signed Adam Maroni 2026-07-05 ("Sign all PASS") |
| AC-5 CR cadence (skipped, zero criteria) | **PASS** | signed Adam Maroni 2026-07-05 ("Sign all PASS") |
