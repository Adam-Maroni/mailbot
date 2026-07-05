---
baseline_commit: a28cd835bc09bdbd9fca0a1e3040f848ad51c87d
---

# Story 10.2: pre_state capture for `MOVE_TO_TRIAGE_FOLDER` + move-family + Tier-1 revert support + revert walk

> ⚙️ **HYBRID STORY — dev-codeable core + Adam-hands-on revert walk (AC-3).** Tasks 1–6 (code + tests + CR) ARE compatible with `dev-story` / `/autonomous-story-run`. Task 7 (the live revert walk) is **NOT**: it moves ONE real email in Adam's REAL Outlook mailbox and requires verification in the Outlook client. A dev agent reaching Task 7 must HALT, log the halt in `_bmad-output/implementation-artifacts/epic-10-run-flags.md` (9.5.x halt pattern), flip the story to `review`, and return control to Adam. $0 spend expected (no Router calls on this path — 10-1 Pin 7, live-proven).

Status: done (2026-07-05 — Tasks 1-8 all complete: dev pass + MANDATORY-CR 3/3 Patches = 100% + live revert walk Adam-hands-on ($0, zero new defects) + README doc-drift with verified 10-2 tags; all 5 AC verdicts PASS, Adam-signed "Sign all PASS" in-session; suite 1708+2+3, ruff/mypy/boundaries green)

<!--
THE one dev story in Epic 10, pre-declared per D2. Every other walk-discovered defect in this
epic is FILED per N.5; this one is absorbed because it was known at epic-filing time and its fix
makes the rest of the write-family walks safely repeatable. Dep-on 10-1: the walk's evidence §5
defines the pre_state field list (delivered 2026-07-05, all 6 items live-evidenced).

SCOPE FENCE (D2, hard): pre_state capture + move-family Tier-1 revert + the minimal local-row
repair the revert needs (10-1 evidence §5 item 5) + same-commit doc-drift. NOTHING ELSE.
Explicitly OUT of scope (already FILED per N.5 — do NOT fix here, however tempting):
  - F4 CRITICAL pause-does-not-gate-worker-drainer (Epic 10.5-candidate)
  - F6 general EMAIL_UPSERT resurrection fix (do NOT touch EMAIL_UPSERT)
  - F1/F2/F3 (pause-vs-chat, Hermes fallback, PAUSED audit rows)
  - propose-time destination_folder_id validation (Pin 2 silent-inbox retarget — FILED-class)
  - folder-name→id resolution for the chat path (10-5 territory)
-->

## Story

As Adam,
I want move-family queued intents to capture pre_state (at minimum the source folder id, plus whatever Story 10.1's evidence names) at queue/drain time, and the reverter to support Tier-1 revert for `MOVE_TO_TRIAGE_FOLDER` and the move-family, verified by a live revert walk,
So that folder-move stops being the only irreversible action in the perimeter, and so the Tier-1 revert promise in the authorization model is true for the move-family rather than aspirational.

## Acceptance Criteria

**AC-1 — pre_state captured before dispatch, never misleading**
**Given** Story 10.1's walk evidence names the state a revert needs
**When** the move-family intent is queued/drained
**Then** pre_state is captured on the intent row (source folder id at minimum; field list per 10.1 findings) before the Graph dispatch fires
**And** a move that fails at dispatch does NOT leave a misleading pre_state claiming a completed move

**AC-2 — Tier-1 revert re-moves via the same Graph seam; refuses cleanly on missing pre_state**
**Given** the reverter surface
**When** Tier-1 revert is requested on a completed move-family action
**Then** the reverter re-moves the email back to the pre_state source folder via the same Graph write seam, with its own audit row
**And** revert on an action with missing/legacy-null pre_state refuses with a clear error rather than guessing

**AC-3 — Live revert walk (Adam-hands-on)**
**Given** the fix is live-validated, not just unit-tested
**When** the revert walk fires
**Then** Adam performs move → revert against the sacrificial folder and verifies in the Outlook client that the email is back in its original folder; evidence captured in `10-2-walk-evidence.md`

**AC-4 — Regression tests**
**Given** the change touches load-bearing production code
**When** tests are written
**Then** +8-12 net-new regression tests cover: pre_state write at queue/drain, revert dispatch, missing-pre_state refusal, and idempotency of the revert path

**AC-5 — MANDATORY-CR full scope**
**Given** this story touches the actions/drainer/reverter load-bearing seam
**When** CR cadence is evaluated per the 6 criteria
**Then** criterion 6 (load-bearing) fires → **MANDATORY-CR per §5.12** with full scope, reviewer model ≠ dev model

### AC interpretation pins (read before coding)

- **AC-1 "on the intent row":** pre_state lives in `action_history.pre_state` (column exists since migration 017; `'{}'` today for every action — live-proven on real action id=4). NO schema migration needed. "Queue/drain time" resolves to **drain time, in the `_insert_history` window immediately before dispatch** — 10-1 evidence §5 item 2 pins this: the drainer already writes `action_history` pre-dispatch (CR-4-4-2 ordering, live-proven `applied_at 09:09:46.479` < `terminal_at .708`), and the source folder is observable ONLY from Graph at that moment (local DB has no folder column — Pin 6, verified live via PRAGMA).
- **AC-1 "misleading pre_state":** do NOT move the history write post-dispatch — that would regress CR-4-4-2 (failed dispatches must keep their audit row). The AC is discharged structurally: the reverter's existing `status='applied'` gate means a dispatch-failed move can never be reverted, so its pre_state cannot mislead the revert path. Tests assert the pairing (failed row + `NOT_APPLIED` refusal).
- **AC-2 "the move-family":** capture pre_state for ALL five actions that dispatch `POST /me/messages/{id}/move` (`MOVE_TO_TRIAGE_FOLDER` T1; `ARCHIVE`, `MARK_JUNK`, `MOVE_TO_USER_FOLDER`, `MOVE_TO_INBOX` T2 — `outlook_adapter.py` `_DISPATCH_TABLE`). REVERT support extends ONLY to the Tier-1 member, `MOVE_TO_TRIAGE_FOLDER` — the reverter's `ONLY_TIER_1_REVERTIBLE` gate is the authorization model (FR-5.1: only Tier-1 is auto-revertible; `types.py` gives `reversibility_window_hours=24` to Tier-1 only) and stays UNCHANGED. Tier-2 moves gain pre_state (cheap, audit-valuable, future-proof) but remain non-revertible via this path. This is the only reading consistent with the story's own So-that ("the **Tier-1 revert promise** … true for the move-family").
- **AC-2 "its own audit row":** the revert is an inverse `pending_actions` row queued for the drainer (existing 4-8 pattern) — it gets its own id, its own drain, its own `action_history` row (which, being a move-family row, gets its own pre_state = the sacrificial folder — audit symmetry for free).
- **AC-3 walk:** Adam-hands-on, $0, sacrificial folder `MailBot-UAT-10-1` retained empty from 10-1 precisely for this walk. See Task 7 + the F4/F5/F6 walk landmines in Dev Notes.
- **Verdict vocabulary:** PASS / PARTIAL-PASS / FAIL, Adam-signed per AC section, 9.5.x convention.

## Tasks / Subtasks

- [x] **Task 1 — Move-family registry + pre_state plumbing foundations (AC-1)**
  - [x] 1.1 `mailbot_api/actions/types.py`: add `MOVE_FAMILY: Final[frozenset[ActionType]]` = {MOVE_TO_TRIAGE_FOLDER, ARCHIVE, MARK_JUNK, MOVE_TO_USER_FOLDER, MOVE_TO_INBOX} + `is_move_family(action_type) -> bool`, mirroring the `EMAIL_LESS_ACTIONS` + `is_send_family` patterns (boundary checker bans string literals outside types.py — never inline `"move_to_triage_folder"`). Add both to `__all__`. Membership must match `_DISPATCH_TABLE`'s `/move` rows exactly — add a test pinning the invariant (pattern: `test_email_less_actions_membership_exact`)
  - [x] 1.2 `mailbot_api/actions/graph_write.py`: extend the `GraphWriteAdapter` Protocol with a pre-state read, e.g. `async def read_move_pre_state(self, email_id: str) -> GraphReadResult` where `GraphReadResult` is a small frozen model `{ok: bool, source_folder_id: str | None, error: str | None}`. Update `FakeGraphWriteAdapter` (return a configurable stub id, default e.g. `"fake-source-folder"`) and `FailingGraphWriteAdapter` (configurable ok/fail so tests can fail the READ while allowing/blocking dispatch — a second constructor flag or a dedicated fake; dev agent's choice, keep it obvious)
  - [x] 1.3 `mailbot_api/actions/outlook_adapter.py`: implement the real read — `GET /me/messages/{id}?$select=parentFolderId` with Bearer token from the SAME `access_token_provider`, parse `parentFolderId` from the JSON body. Reuse/mirror the AR-D5-1 retry semantics (429/503 backoff, 4xx fail-fast); `_dispatch_with_retry` returns no body, so either refactor it to optionally return the response JSON or write a sibling `_get_with_retry` — do NOT duplicate the whole retry ladder blindly. Rule B: this file is one of only two allowed to touch graph.microsoft.com; adding a GET here keeps the boundary (run `scripts/check_boundaries.py` — the read-side allowlist may need the `$select=parentFolderId` pattern added; extend the allowlist in the same commit if so)

- [x] **Task 2 — Drainer: capture pre_state, fail closed (AC-1)**
  - [x] 2.1 `mailbot_api/actions/drainer.py`: replace the `_build_pre_state` stub. In `_process_claimed_row`, AFTER per-tier checks + send-cap and BEFORE `_insert_history`: if `is_move_family(row.action_type)`, call `adapter.read_move_pre_state(row.email_id)`. On success, pre_state JSON = `{"source_folder_id": "<id>", "captured_at": "<ISO-Z>"}` (keep the shape minimal + versionable; `graph_id` is already on the row, changeKey is drift-only per 10-1 evidence §5 item 4 — do NOT store it as identity)
  - [x] 2.2 **Fail closed:** if the pre-state read fails (or returns `source_folder_id=None`), `_mark_failed(row, "pre_state_capture_failed:<detail>")` + `_notify_failure` and do NOT dispatch — dispatching without pre_state re-creates the exact irreversibility this story closes. Consistent with existing check-failure paths (no history row is written for check-failed rows today — keep that). Recovery = `mailbot replay <id>` re-queues. Tier-1 failure stays silent per Pin 5 (log + DB only); Tier-2 move failures route `important` per the existing `_notify_failure` bands — no new notification code. **Deliberate consequence:** fail-closed applies uniformly to Tier-2 moves too (ARCHIVE/MARK_JUNK/…) — the epic AC binds pre_state capture to "the move-family intent" as a Then-clause, and a split policy (strict T1 / best-effort T2) would make the capture guarantee untestable. A Graph-read outage therefore fails Tier-2 moves visibly instead of archiving irreversibly-unaudited; if Adam prefers best-effort for Tier-2, that is a one-line relaxation to record in run-flags, not a redesign
  - [x] 2.3 Non-move actions keep `pre_state='{}'` byte-identical (regression: send/delete/category paths untouched)
  - [x] 2.4 Structured log on capture: extend the existing `action.drainer.*` event family (e.g. `action.drainer.pre_state.captured` / `.failed` with `action_id`, `action_type`, no folder-id PII concerns — folder ids are opaque, fine to log; match house logging style)

- [x] **Task 3 — Drainer: revert-row special-casing (AC-2 — the F5 landmine)**
  - [x] 3.1 **Reserved payload key `revert_of_action_id`:** the inverse row queued by the reverter carries `payload["revert_of_action_id"] = <original action id>`. `mailbot_api/actions/propose.py`: refuse any `propose_action` payload containing this key (mirror the FR-5.6 `"tier"` reserved-key refusal, code `INVALID_PAYLOAD` or a sibling; message: reserved for the reverter). Without this guard, an agent could set the key to bypass 3.2's deleted-gate — the guard is what makes the bypass provenance-safe (only the reverter inserts via `PENDING_ACTION_INSERT` directly, not via `propose_action`)
  - [x] 3.2 **Bypass the lenient deleted-gate for revert rows:** `_check_tier_1` currently fails `target_deleted` when the local row is missing or `deleted_at IS NOT NULL`. 10-1 F5 (live-proven) means the ORIGINAL move soft-deletes the local row ~12s after dispatch — so by revert time the local row is almost always `deleted_at`-set and the revert would be refused. When `row.payload.get("revert_of_action_id")` is present, skip the deleted/missing refusal — the row's purpose is restoring an email the local DB believes gone; the Graph immutable id is the stable handle (10-1 evidence §5 item 3, live-verified across move+restore), and Graph itself 404s (adapter 4xx fail-fast → `provider_4xx_404` failure) if the message is truly gone
  - [x] 3.3 **Local-row repair on revert success (10-1 evidence §5 item 5 — in scope):** when a row carrying `revert_of_action_id` is `_mark_applied`, clear the soft-delete: new query constant in `db/queries.py`, e.g. `EMAIL_CLEAR_SOFT_DELETE = "UPDATE emails SET deleted_at = NULL, removed_reason = NULL WHERE graph_id = ?"`, executed for `row.email_id`. Self-correcting: if the revert destination is outside the synced folder set, the next delta re-soft-deletes correctly. Do NOT touch `EMAIL_UPSERT` (that's F6, FILED)

- [x] **Task 4 — Reverter: state-dependent move inverse + refusal (AC-2)**
  - [x] 4.1 `mailbot_api/actions/reverter.py`: add `"PRE_STATE_MISSING"` to `RevertErrorCode`. For `action_type == MOVE_TO_TRIAGE_FOLDER` (the Tier-1 move-family member), branch BEFORE the static `_INVERSE_ACTION` lookup: read `history_row[0]` (pre_state JSON, already fetched). If history row absent, or pre_state parses to `{}`/no `source_folder_id` → refuse `PRE_STATE_MISSING` with a message that names legacy pre-10-2 rows (real action id=4 is the live legacy case). Never guess a destination
  - [x] 4.2 On valid pre_state: insert the inverse row — `action_type = MOVE_TO_TRIAGE_FOLDER` (the Tier-1 move primitive; `MOVE_TO_INBOX`/`MOVE_TO_USER_FOLDER` are Tier-2/grant-gated and the reverter's own `inverse_tier != 1` defensive check would refuse them), `payload = {"destination_folder_id": pre_state["source_folder_id"], "revert_of_action_id": action_id}`, tier 1, status `pending`, then `ACTION_HISTORY_MARK_REVERTED` as today. All existing gates (tier-1-only, applied-only, 24h window, already-reverted) run UNCHANGED before the branch
  - [x] 4.3 Update the module docstring + the stale 4-8 comments (the "MOVE_TO_TRIAGE_FOLDER excluded / pre_state not yet populated" story is over); keep the static map for the 4 mark/category pairs exactly as-is
  - [x] 4.4 Doc-drift on the refusal message surfaces: `mcp_server.py:932-934` tool description ("MOVE_TO_TRIAGE_FOLDER returns INVERSE_UNAVAILABLE" → now revertible; PRE_STATE_MISSING only for legacy rows) + `hermes-config/skills/mailbot/SKILL.md:215` (same claim). The 9-10 drift test compares registration/sections, not prose — but both claims become FALSE this story; update both in the same commit

- [x] **Task 5 — Regression tests, +8-12 net-new (AC-4)**  *(baseline suite: 1695 passed + 2 skipped + 3 deselected; all 4 gates green at close)*
  - [x] 5.1 `test_types.py`: MOVE_FAMILY membership exact-set invariant (cross-check against `_DISPATCH_TABLE` `/move` rows)
  - [x] 5.2 `test_drainer.py`: move-family row captures pre_state before dispatch — drain a MOVE_TO_TRIAGE_FOLDER row with the stub-returning fake; assert `action_history.pre_state` JSON has `source_folder_id` + `captured_at`
  - [x] 5.3 `test_drainer.py`: non-move row (e.g. MARK_READ) still writes `'{}'`
  - [x] 5.4 `test_drainer.py`: pre-state read failure → `status='failed'`, `failure_reason` starts `pre_state_capture_failed`, adapter `.apply()` NEVER called (record-calls fake), no history row
  - [x] 5.5 `test_drainer.py`: revert-marked row drains despite soft-deleted local email row (seed `deleted_at` set → applied, not `target_deleted`); non-marked row on the same email still fails `target_deleted` (gate intact)
  - [x] 5.6 `test_drainer.py`: applied revert-marked row clears `deleted_at`/`removed_reason` on the email row
  - [x] 5.7 `test_reverter.py`: applied MOVE_TO_TRIAGE_FOLDER with populated pre_state → ok; inverse row is `move_to_triage_folder`, tier 1, payload has `destination_folder_id == source_folder_id` + `revert_of_action_id`; `reverted_at` set
  - [x] 5.8 `test_reverter.py`: pre_state `'{}'` (legacy) → `PRE_STATE_MISSING`; history row absent → `PRE_STATE_MISSING`
  - [x] 5.9 `test_reverter.py`: second revert → `ALREADY_REVERTED` (idempotency, existing gate now covering the move path)
  - [x] 5.10 `test_reverter.py`: dispatch-FAILED move → `NOT_APPLIED` (the AC-1 "misleading pre_state" structural pair)
  - [x] 5.11 `test_propose_action.py`: payload with `revert_of_action_id` → refused (reserved key)
  - [x] 5.12 `test_outlook_adapter.py`: `read_move_pre_state` via `httpx.MockTransport` — 200 parses `parentFolderId`; 404 → ok=False (+ optionally 429-retry behavior if the retry ladder is reused)
  - [x] 5.13 Tier-2 move (ARCHIVE with valid grant) also captures pre_state AND stays `ONLY_TIER_1_REVERTIBLE` on revert attempt

- [x] **Task 6 — MANDATORY-CR full scope (AC-5)**
  - [x] 6.1 Criterion 6 fires by pre-declaration (actions/drainer/reverter load-bearing seam). Run FULL-scope CR with a reviewer model ≠ the dev-agent model (epic norm; 9.5 retro A5 reviewer-substitution rule). Triage per house convention (Patches applied / Defers / Dismisses with evidence), record applied-rate in Dev Agent Record + run-flags — **DONE 2026-07-05: sonnet reviewer layers, 3/3 Patches applied = 100%, 1 Defer, 7 Dismissed (see Review Findings)**
  - [x] 6.2 Gates after CR patches: pytest (expect 1695+2+3 baseline + net-new), ruff, mypy, `scripts/check_boundaries.py` — all green before the walk — **re-run post-CR-patches 2026-07-05: 1708+2+3 (+13 net vs baseline), ruff clean, mypy 129 files clean, boundaries exit 0**

- [x] **Task 7 — Live revert walk (AC-3) — ⚠ ADAM-HANDS-ON; dev agents HALT here** (flip story → `review`, log halt in `epic-10-run-flags.md`, return control) — **WALKED 2026-07-05, Adam-hands-on, $0, zero new defects; full captures in `10-2-walk-evidence.md`; per-AC verdicts proposed PASS×5, Adam signature pending**
  - [x] 7.0 **Preflight (10-1 Task 0 pattern):** HEAD vs baseline+story-commits recorded; `docker compose ps` healthy; `/health` 200; `mailbot status` OAuth green; drainer ticking in worker logs; DB baselines (`pending_actions` MAX(id), `action_history` count, last `router_calls.id`). **The container image must include this story's code** — rebuild/restart `mailbot-api` (`docker compose up -d --build`) and verify the worker restarts BEFORE walking (9.5 retro A1 image-drift lesson: hotfix-drift between host tree and running image invalidated evidence)
  - [x] 7.1 **Stage:** sacrificial folder `MailBot-UAT-10-1` still exists (retained empty from 10-1) — re-capture its folder id via the container's Graph seam. Subject email: a low-value email whose local row has `deleted_at IS NULL` — ⚠ do NOT reuse the 10-1 Railway email as-is: it is still soft-deleted locally (F6 residual, deliberate) and the ORIGINAL move's `_check_tier_1` would fail `target_deleted`. Either pick a fresh subject (RECOMMENDED — preserves the F6 live evidence for Epic 10.5 triage) or, if Adam prefers to consume the residual, manually repair the row first (`UPDATE emails SET deleted_at=NULL, removed_reason=NULL WHERE graph_id=?`) and record the repair as a staging step. Record the subject's source folder as seen in the Outlook client + via Graph `parentFolderId`
  - [x] 7.2 **Move (⚠ F4 is LIVE — pause does NOT stop the worker drainer; blast-radius-by-construction is the ONLY containment):** verify the payload folder-id byte-correct BEFORE proposing; then `propose_action(email_id=<id>, "move_to_triage_folder", {"destination_folder_id": "<id>"})` (Path B direct verb, 10-1 precedent; Discord entry is 10-5's walk) — dispatch fires ~2s later, unstoppable. Capture: queued row, **`action_history.pre_state` now populated with the REAL source folder id (THE new assertion this walk exists for — vs `'{}'` on action id=4)**, terminal `applied`, drainer logs, Graph `parentFolderId` == sacrificial folder
  - [x] 7.3 Adam verifies in the Outlook client: email physically in `MailBot-UAT-10-1` (attestation/screenshot into evidence)
  - [x] 7.4 **Revert:** `mailbot revert <action_id>` (CLI, README:224) or MCP `revert_action` — capture the ok envelope + inverse row (payload destination == pre_state source, `revert_of_action_id` set) + its drain (applied; the local row will likely be soft-deleted by then — the 3.2 bypass firing live IS evidence) + `reverted_at` on the original's history row + Graph `parentFolderId` back to source
  - [x] 7.5 Adam verifies in the Outlook client: email back in its original folder — the AC-3 clause; 2xx/Graph-re-read alone does NOT discharge it
  - [x] 7.6 **Post-checks:** local row repaired (`deleted_at IS NULL`, `removed_reason IS NULL` — Task 3.3 live); second `revert` attempt → `ALREADY_REVERTED` (idempotency live); `revert_action(4)` (10-1's legacy row, if still within nothing — it is outside the 24h window, so expect `REVERT_WINDOW_EXPIRED`; record whichever refusal fires as legacy-row evidence); `router_calls` unchanged ($0)
  - [x] 7.7 Compose `10-2-walk-evidence.md` (9.5.x conventions: session header, per-AC Adam-signed verdicts, verbatim SQL/log/Graph captures, F-track table — any NEW defect found here is FILED per N.5, zero absorbed beyond the pre-declared scope)

- [x] **Task 8 — Doc-drift discharge, same story same commit + close-out**
  - [x] 8.1 README.md:370 limitations line ("Triage-move has no auto-revert yet … `INVERSE_UNAVAILABLE` … next planned fix") → rewrite to walked truth + `<!-- verified 10-2, run_id <revert_action_id>/<date> -->`; honest caveats stay (legacy rows refuse `PRE_STATE_MISSING`; Tier-2 moves still manual)
  - [x] 8.2 README.md:118 tier-table row 1: drop/adjust the "**except** triage-move (manual revert only…)" qualifier; README.md:144 caveat sentence ("moved email drops out of MailBot's local view") — update the revert-path part only if walked reality changed it (revert now repairs the local row; a plain move still drops out — keep that half)
  - [x] 8.3 README.md:146-150 Tier-1 undo example + :224 `mailbot revert` row: verify still-true; extend only with real captured output if touched (hard-assert command names + error codes; prose soft-assert)
  - [x] 8.4 `mcp_server.py` + SKILL.md updates from Task 4.4 land in this same commit
  - [x] 8.5 Append Story 10-2 record to `epic-10-run-flags.md` (CR determination, walk record, findings dispositions); flip sprint-status `10-2-…` → `review` at walk close → `done` on Adam-signed verdicts; stage everything (`rtk git add`) — never commit autonomously

### Review Findings

MANDATORY-CR (Task 6.1) 2026-07-05 — reviewer layers on **sonnet** (≠ dev model fable-5, per AC-5 / 9.5-retro A5), 3 parallel layers (Blind Hunter / Edge Case Hunter / Acceptance Auditor), 11 raw findings + 2 auditor observations → 3 Patches, 1 Defer, 7 Dismissed. Acceptance Auditor: **0 violations** across AC-1/2/4, PIN A–H, design pins 1–4, scope fence; all 13 Task-5 subtasks confirmed present.

- [x] [Review][Patch] CR-10-2-1 (edge, HIGH) — concurrent `revert_action` calls on the same move can both pass `ALREADY_REVERTED` (each DB call is its own transaction) and queue duplicate inverse Graph moves; newly dispatch-reachable for moves in this story. Fix: claim `ACTION_HISTORY_MARK_REVERTED` (already guarded `AND reverted_at IS NULL`) BEFORE the inverse-row insert and refuse `ALREADY_REVERTED` on rowcount 0 — absorbs the sibling finding that the mark's rowcount was silently discarded [mailbot_api/actions/reverter.py:249-271]
- [x] [Review][Patch] CR-10-2-2 (blind+auditor, MEDIUM) — `_is_revert_row` trusts the reserved payload marker alone; the `_check_tier_1` deleted-gate bypass and the `EMAIL_CLEAR_SOFT_DELETE` repair never re-validate `is_move_family` at point of use (defense-in-depth: today only the reverter can mint the marker and it only mints move rows, but both fail-safes trust that single propose-boundary guard) [mailbot_api/actions/drainer.py:227-232]
- [x] [Review][Patch] CR-10-2-3 (auditor, LOW) — `test_revert_dispatch_failed_move_refused_not_applied` simulates the failed dispatch without seeding the CR-4-4-2 history row, so it never literally proves "populated pre_state present but revert still refused"; seed a populated-pre_state history row to make the AC-1 structural pair exact [tests/unit/actions/test_reverter.py]
- [x] [Review][Defer] CR-10-2-D1 — residual double-revert race for legacy rows with NO action_history row (Story 4-4 tolerance: nothing to claim on; the claim-first fix cannot cover them) [mailbot_api/actions/reverter.py:264-268] — deferred, pre-existing

Dismissed (7, with evidence): capture-vs-dispatch folder race (inherent to spec-pinned drain-time capture; ms window, no atomic Graph alternative); `EMAIL_CLEAR_SOFT_DELETE` missing `deleted_at IS NOT NULL` guard (SQL is Task-3.3-verbatim; clearing is idempotent and only runs on successful Graph dispatch); reserved-key vs other-refusal precedence untested (any refusal blocks; ordering non-load-bearing); `PRE_STATE_MISSING` message doesn't distinguish malformed from legacy-empty (no live malformed path — drainer validates shape before write); `revert_of_action_id` value never cross-checked downstream (only presence is read; fabrication requires direct DB write, outside threat model); adapter truthy-`str()` vs reverter `isinstance` validation asymmetry (masked by coercion, no failure path); integration mock transport not per-email-scoped (fixture fragility for hypothetical future reuse only).

## Dev Notes

### Previous-story intelligence (10-1 walk, 2026-07-05 — all live-proven, cite `10-1-walk-evidence.md`)

- **pre_state field list (evidence §5, the direct input):** (1) `source_folder_id` = Graph `parentFolderId`, MANDATORY, Graph-read is the only source (emails table has NO folder column — PRAGMA-verified, 52 columns); (2) capture at drain time immediately before dispatch; (3) immutable `graph_id` is the stable revert handle (survived move + restore live); (4) `changeKey` mutates on every move — drift-detection only, never identity; (5) revert must also repair the LOCAL row (F5 soft-deletes as `removed_reason='deleted'`, F6 delta re-add never resurrects); (6) optional: folder displayName (nice-to-have; skip if it costs a second Graph call — evidence value only)
- **F4 CRITICAL (FILED — do NOT fix, do NOT rely on pause):** `PauseState` is per-process in-memory; `mailbot pause` flips the API process only; the worker drainer dispatched a real Graph write 259 ms after propose WHILE PAUSED. Walk choreography must assume propose→dispatch ~2s, unstoppable. Blast-radius-by-construction (verified payload + sacrificial folder) is the only containment. There is also NO user-facing Tier-1 abort (10-1 Pin 9: `cancel_action` only flips `cooling_off` rows)
- **F5/F6 (FILED, but they shape THIS story's design):** move → delta soft-deletes local row (`removed_reason='deleted'`, ~12s, before any manual sync-now) → revert rows will face `target_deleted` (hence Task 3.2); delta re-add never clears `deleted_at` (hence Task 3.3). The 10-1 walk subject (Railway email, graph_id ending `…KZe9rgAA`) is STILL soft-deleted locally as deliberate live evidence — see Task 7.1 staging warning
- **Legacy row for refusal testing:** real `pending_actions` id=4 (`move_to_triage_folder`, applied 2026-07-05, `pre_state='{}'`) — the canonical legacy-null case; its live `revert_action(4)` → `INVERSE_UNAVAILABLE` refusal was captured verbatim in 10-1 evidence §6
- **Ops facts:** image has no sqlite3 CLI (use `docker compose exec -T mailbot-api python -c "import sqlite3; …"`); drainer tick 2s; Tier-1 silent both directions (logs + DB only audit surface); `router_calls` uses `task_type`/`model_chosen` column names; degraded-mode budget warning is pre-existing and non-blocking for $0 walks

### Code-reality contract pins (verified against source at baseline_commit)

- **PIN A — dispatch seam:** `_DISPATCH_TABLE` maps all 5 move-family types to `POST /me/messages/{id}/move` with `_body_move` (`outlook_adapter.py:135-147,65-72`); `destination_folder_id` payload-only, fallback `_DEFAULT_FOLDERS.get(type, "inbox")` and MOVE_TO_TRIAGE_FOLDER is NOT in `_DEFAULT_FOLDERS` — a revert row MUST carry the explicit destination
- **PIN B — drainer order today:** claim → mid-tick pause re-check → per-tier checks (`_check_tier_1` `drainer.py:277-295` fails `target_deleted` on missing/deleted local row) → send-cap → `_insert_history` (pre_state `'{}'` via `_build_pre_state` stub `:219-227`) → `adapter.apply` → `_mark_applied`/`_mark_failed`. Check-failed rows get NO history row; dispatch-failed rows DO (CR-4-4-2). Preserve both properties
- **PIN C — reverter today:** `reverter.py` gates in order: exists → tier==1 (`ONLY_TIER_1_REVERTIBLE`) → `status=='applied'` (`NOT_APPLIED`) → `terminal_at`+24h (`REVERT_WINDOW_EXPIRED`, `REVERT_WINDOW=timedelta(hours=24)`) → `reverted_at` null (`ALREADY_REVERTED`) → static `_INVERSE_ACTION` map (`INVERSE_UNAVAILABLE` for moves) → defensive `inverse_tier != 1` refusal → `PENDING_ACTION_INSERT` + `ACTION_HISTORY_MARK_REVERTED`. Note: it proceeds when history row is ABSENT for static-map types (4-4 legacy tolerance) — the move branch must NOT inherit that tolerance (no pre_state = refuse)
- **PIN D — adapter/token topology:** real `OutlookGraphWriteAdapter` bound ONLY in `worker.py:305-307` with a SYNC `access_token_provider` reading the `_CachedAccessToken` cell (refreshed every 240s from `oauth_state`); `run_tick(adapter=None)` defaults to `FakeGraphWriteAdapter` — ad-hoc `run_tick` produces false-positive `applied` with zero mailbox change (never demo that way). The pre-state read gets its token from the same provider — no new token plumbing
- **PIN E — Rule B boundary:** only `outlook_adapter.py` + `sync/graph_client.py` may touch graph.microsoft.com; `scripts/check_boundaries.py` enforces (also bans action-type string literals outside `types.py`/tests). Put the pre-state GET in `outlook_adapter.py`; run the boundary gate locally before CR
- **PIN F — propose surface:** `propose.py` refuses reserved payload key `"tier"` (`TIER_PROMOTION_ATTEMPT`, `:227-235`) — the model for the Task 3.1 `revert_of_action_id` guard. Tier-1 propose does NO email lookup and NO payload-content validation (Pin 2 from 10-1 — missing destination silently retargets inbox at dispatch; OUT of scope to fix). The reverter inserts inverse rows via `PENDING_ACTION_INSERT` directly, NOT via `propose_action` — the reserved-key guard therefore cannot block the reverter
- **PIN G — schema:** `action_history(action_id PK, pre_state TEXT NOT NULL, applied_at, reverted_at)` (migration 017) — one history row per action; pre_state is TEXT JSON; NO migration needed. `pending_actions` columns per `PENDING_ACTION_SELECT_BY_ID` (queries.py:728-733); payload is JSON TEXT, `sort_keys=True` on propose (match when inserting inverse rows for deterministic tests)
- **PIN H — status vocabulary:** `pending → draining → applied/failed`, plus `pending_grant`/`cooling_off`/`cancelled`. The inverse row is a normal `pending` Tier-1 row — drains within ~2s in production; tests drive `run_tick` directly

### Design rationale pins (decided at context-engineering; deviate only with recorded reason)

1. **Fail-closed on capture failure** (Task 2.2): a move dispatched without pre_state is irreversible-by-construction — the exact defect this story closes. Cost: a Graph-read outage blocks moves (they fail visibly, replayable via `mailbot replay`); benefit: the Tier-1 revert promise becomes structural, never best-effort. Matches the house safety posture (belt-and-suspenders DELETE, kill-switch findings)
2. **Inverse action = MOVE_TO_TRIAGE_FOLDER with explicit destination** (Task 4.2): it is mechanically "the Tier-1 move primitive" — same endpoint, same body builder, tier 1 (no grant), passes the reverter's own tier-1-inverse defensive check. `MOVE_TO_INBOX`/`MOVE_TO_USER_FOLDER` are Tier-2 (grant-gated) and would deadlock the revert on `pending_grant`
3. **`revert_of_action_id` as the provenance marker** (Task 3): payload survives the queue round-trip in the existing schema (no migration), is visible in every audit dump, and is protectable at the propose boundary. A schema column would be cleaner but costs a migration for the same semantics — not worth it
4. **Local-row repair scoped to revert-success only** (Task 3.3): 10-1 evidence §5 item 5 names it as a revert-path requirement ("otherwise a 'reverted' email remains invisible to every read verb" — the revert would be a lie at L3). The general resurrection fix (EMAIL_UPSERT clearing deleted_at on any re-add) stays FILED as F6 — bigger blast radius, belongs to its own story

### Testing requirements

- Suite baseline **1695 passed + 2 skipped + 3 deselected**; +8-12 net-new (Task 5 lists 13 candidates — trim, don't pad; the four AC-4-named areas are mandatory)
- House test idiom (see `test_reverter.py`, `test_drainer.py`): real SQLite via `tmp_path` + `apply_pending_migrations`; seed emails with raw INSERT; simulate drain outcomes with `_mark_applied_with_history`-style helpers; drainer tests drive `run_tick(db_path, adapter=<fake>)` directly; adapter tests use `httpx.MockTransport`. anyio/asyncio mode per existing conftest — copy a neighboring test's shape
- Gates: pytest, ruff, mypy (129 files clean at baseline), `scripts/check_boundaries.py` — all green pre-walk AND at close

### Project Structure Notes

Files this story may touch — and ONLY these:
- `mailbot_api/actions/types.py`, `graph_write.py`, `outlook_adapter.py`, `drainer.py`, `reverter.py`, `propose.py`
- `mailbot_api/db/queries.py` (EMAIL_CLEAR_SOFT_DELETE constant; do NOT touch EMAIL_UPSERT)
- `mailbot_api/mcp_server.py` (revert_action tool description only)
- `scripts/check_boundaries.py` (only if the new GET needs an allowlist entry)
- `tests/unit/actions/test_types.py`, `test_drainer.py`, `test_reverter.py`, `test_outlook_adapter.py`, `test_propose_action.py`
- `hermes-config/skills/mailbot/SKILL.md` (:215 stale claim)
- `README.md` (doc-drift per Task 8)
- `_bmad-output/implementation-artifacts/`: `10-2-walk-evidence.md` (new), `epic-10-run-flags.md` (append), `sprint-status.yaml`, this story file

NO new modules, NO migrations, NO changes under `router/`, `sync/` (the pre-state read lives in the actions-side adapter per Rule B), `docker/`, `benchmark/`. `verbs/revert_action.py` is a pass-through shim — untouched unless the return envelope changes (it doesn't; only a new error code value flows through the existing shape).

### References

- [Source: _bmad-output/planning-artifacts/epics.md § "Epic 10 Detail" + § "Story 10.2"] — D2 pre-declaration, scope fence, doc-drift rules (a)/(b), AC text (verbatim above), MANDATORY-CR pre-declaration
- [Source: _bmad-output/implementation-artifacts/10-1-walk-evidence.md §2.2, §3, §4, §5, §6, F-track table] — pre_state field list, F4/F5/F6, legacy action id=4, live refusal texts
- [Source: _bmad-output/implementation-artifacts/10-1-live-folder-move-walk-sacrificial-outlook-folder.md § Dev Notes] — contract pins 1-9 (inherited where still relevant), ops facts, evidence SQL patterns
- [Source: mailbot_api/actions/drainer.py:219-245,277-295,513-586; reverter.py:46-51,90-226; outlook_adapter.py:65-72,129-166,240-313; types.py:197-203,318-357; propose.py:186-280; worker.py:225-307; graph_write.py] — seam reality
- [Source: mailbot_api/db/queries.py:136-167,721-880; db/migrations/017_action_history.sql, 015_pending_actions.sql, 005_emails_removed_reason.sql] — schema + query surfaces
- [Source: README.md:118,134-150,224,271-288,369-370; hermes-config/skills/mailbot/SKILL.md:204-215; mailbot_api/mcp_server.py:438-451,932-934] — doc-drift oracle anchors
- [Source: memory project_epic_6_scope_cleave.md (N.5), feedback_l1_l2_l3_done_layers.md, feedback_oauth_token_handling.md, project_local_viability_over_deployment.md (D4)] — durable rules binding this story

## Dev Agent Record

### Agent Model Used

claude-fable-5 (Claude Fable 5) — dev-story pass 2026-07-05, same session as context-engineering. MANDATORY-CR (Task 6.1) deliberately NOT run by this model per AC-5 reviewer ≠ dev model.

### Debug Log References

- RED confirmed before implementation: 5 representative new tests failed on missing symbols (`MOVE_FAMILY`, `FakeGraphWriteAdapter(source_folder_id=...)`, `read_move_pre_state`, reserved-key refusal, `PRE_STATE_MISSING`).
- One RED→GREEN test-design fix: the bypass test originally staged the plain row and the revert row on the SAME soft-deleted email; the revert row drained first (earlier proposed_at), applied, and repaired the shared email's soft-delete — un-gating the plain row. Split onto two emails (`e-1`/`e-2`); the interaction itself is documented in the test comment.
- One legitimate premise update outside the story's new tests: `tests/integration/test_worker_drainer_wiring.py::_make_mock_transport` — its catch-all 200/`{}` mock now also serves the pre-state GET (`$select=parentFolderId`); without it the ARCHIVE wiring test failed CLOSED with `pre_state_capture_failed:parent_folder_id_absent` (the new fail-closed path working as designed, live-proven by the gate run).

### Completion Notes List

- Context-engineered 2026-07-05 (create-story). Ultimate context engine analysis completed - comprehensive developer guide created. All load-bearing seams read at baseline_commit (drainer, reverter, adapters, propose, worker, queries, migrations); 10-1 walk evidence §5 field list fully absorbed incl. the F5 target_deleted landmine on revert rows and the F6 staging warning; 8 contract pins + 4 design-rationale pins recorded; scope fence encoded from D2 + N.5.
- **Dev pass complete 2026-07-05 (Tasks 1-5 + 6.2), red-green-refactor.** Implementation exactly per design pins, zero deviations:
  - `types.py`: `MOVE_FAMILY` frozenset + `is_move_family()` + reserved `REVERT_OF_ACTION_ID_KEY` constant; re-exported from `actions/__init__.py`.
  - `graph_write.py`: `GraphReadResult` frozen model; `GraphWriteAdapter` Protocol extended with `read_move_pre_state`; `FakeGraphWriteAdapter` grew a configurable `source_folder_id` stub (default `"fake-source-folder"`, backward-compatible no-arg construction); `FailingGraphWriteAdapter` grew `fail_pre_state_read` flag (read succeeds by default so dispatch-failure tests still reach `apply()`).
  - `outlook_adapter.py`: real `read_move_pre_state` = `GET /me/messages/{id}?$select=parentFolderId` through the same token seam; `_dispatch_with_retry` refactored into `_request_with_retry` returning `(result, response)` so the read parses the 2xx body without duplicating the AR-D5-1 retry ladder (Rule B honored — no new Graph-touching file; boundary checker exit 0, no allowlist change needed).
  - `drainer.py`: `_capture_move_pre_state` before `_insert_history`, fail-closed `pre_state_capture_failed:*` (check-class failure — no history row, no dispatch, tier-banded notification); pre_state shape `{"source_folder_id", "captured_at"}`; non-move rows keep `'{}'` byte-identical; `_check_tier_1` bypasses missing/deleted refusal for revert-marked rows (F5); applied revert rows clear `deleted_at`/`removed_reason` via new `EMAIL_CLEAR_SOFT_DELETE` (10-1 evidence §5 item 5); structured events `action.drainer.pre_state.captured/.failed` + `action.drainer.revert.local_row_repaired`.
  - `propose.py`: reserved-key guard 2b refuses `revert_of_action_id` payloads with `INVALID_PAYLOAD` (mirrors the FR-5.6 `"tier"` guard) — the provenance fence that makes the drainer bypass safe.
  - `reverter.py`: `PRE_STATE_MISSING` added to `RevertErrorCode`; move-family branch (state-dependent inverse: same `MOVE_TO_TRIAGE_FOLDER` primitive, `destination_folder_id = pre_state.source_folder_id`, payload marked with `revert_of_action_id`, `sort_keys=True`); missing history row OR legacy `'{}'`/malformed pre_state → `PRE_STATE_MISSING` (the move branch does NOT inherit the static-map types' absent-history tolerance); all five pre-existing gates unchanged; static map untouched.
  - Doc surfaces updated same pass: `mcp_server.py` revert_action tool description + `hermes-config/skills/mailbot/SKILL.md` §revert_action (both stale claims that MOVE_TO_TRIAGE_FOLDER is unrevertible).
- **Tests: +12 net-new** (13 added, 1 removed whose premise this story ends — `test_build_pre_state_returns_empty_dict_for_now`): types membership/dispatch-table cross-check (5.1), drainer capture/non-move-fence/fail-closed/bypass/local-repair/Tier-2-capture (5.2-5.6, 5.13), reverter inverse-queue/PRE_STATE_MISSING×2-scenarios/idempotency/NOT_APPLIED (5.7-5.10), propose reserved key (5.11), adapter GET parse + 404 fail-closed (5.12; the optional 429-retry variant skipped — the retry ladder is shared with dispatch and already covered).
- **Gates (Task 6.2) all green:** pytest **1707 passed + 2 skipped + 3 deselected** (baseline 1695 → +12 net); ruff clean on tracked tree (2 pre-existing T201 in untracked `scratch/walk_bootstrap.py`, out of scope, same as 10-1 footer); mypy `Success: no issues found in 129 source files`; `scripts/check_boundaries.py` exit 0.
- **NOT done in this pass (by design):** Task 6.1 MANDATORY-CR (requires reviewer model ≠ dev model — run `code-review` next); Task 7 live revert walk (Adam-hands-on, halt logged in `epic-10-run-flags.md`); Task 8 README doc-drift (walk-gated — verified tags need the walk's run_id; the `mcp_server.py`/SKILL.md halves of Task 4.4/8.4 are already done). Story flipped to `review`.
- **MANDATORY-CR complete 2026-07-05 (Task 6.1), reviewer ≠ dev model honored:** orchestrator fable-5, all 3 review layers (Blind Hunter diff-only / Edge Case Hunter diff+repo / Acceptance Auditor diff+spec) dispatched on **sonnet**. 11 raw findings + 2 auditor observations → triage: **3 Patches applied (100%)**, 1 Defer (CR-10-2-D1 pre-existing legacy-absent-history race → deferred-work.md), 7 Dismissed with evidence. Acceptance Auditor: 0 violations (AC-1/2/4, PIN A–H, design pins 1–4, scope fence, all 13 Task-5 tests confirmed). Patches: CR-10-2-1 claim-first `ACTION_HISTORY_MARK_REVERTED` rowcount-checked before inverse insert (kills concurrent-double-revert duplicate Graph dispatch) + new deterministic stale-read regression test; CR-10-2-2 `_is_revert_row` re-validates `is_move_family` at point of use (defense-in-depth for gate bypass + repair); CR-10-2-3 NOT_APPLIED test now seeds populated-pre_state history row (AC-1 pair literal). Gates re-run post-patches: pytest **1708+2+3** (+13 net vs 1695 baseline), ruff clean, mypy 129 files clean, boundaries exit 0. Story stays `review` — the skill's done-flip is overridden by this story's own close-out rule (Task 7 Adam-hands-on walk + Task 8 walk-gated doc-drift still pending).

### File List

- `mailbot_api/actions/types.py` (MOVE_FAMILY, REVERT_OF_ACTION_ID_KEY, is_move_family)
- `mailbot_api/actions/__init__.py` (re-exports)
- `mailbot_api/actions/graph_write.py` (GraphReadResult, Protocol extension, fakes)
- `mailbot_api/actions/outlook_adapter.py` (read_move_pre_state, _request_with_retry refactor)
- `mailbot_api/actions/drainer.py` (pre_state capture fail-closed, revert-row bypass, local-row repair)
- `mailbot_api/actions/propose.py` (reserved revert-marker guard)
- `mailbot_api/actions/reverter.py` (move-family branch, PRE_STATE_MISSING)
- `mailbot_api/db/queries.py` (EMAIL_CLEAR_SOFT_DELETE)
- `mailbot_api/mcp_server.py` (revert_action tool description)
- `hermes-config/skills/mailbot/SKILL.md` (revert_action section)
- `tests/unit/actions/test_types.py` (+1 test)
- `tests/unit/actions/test_drainer.py` (+6 tests, −1 stale, helper `_insert_revert_row`)
- `tests/unit/actions/test_reverter.py` (+4 tests, 1 replaced, `_mark_applied_with_history` pre_state param)
- `tests/unit/actions/test_propose_action.py` (+1 test)
- `tests/unit/actions/test_outlook_adapter.py` (+2 tests)
- `tests/integration/test_worker_drainer_wiring.py` (mock transport serves pre-state GET)
- `_bmad-output/implementation-artifacts/deferred-work.md` (CR-10-2-D1)
- `_bmad-output/implementation-artifacts/10-2-walk-evidence.md` (new — Task 7 live revert walk)
- `README.md` (Task 8 doc-drift: :118 tier row, :144 caveat revert-half, :370 limitations bullet; verified 10-2 run_id action-6/2026-07-05 tags)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status flips)
- `_bmad-output/implementation-artifacts/epic-10-run-flags.md` (Story 10-2 dev-pass record + Task 7 halt)
- this story file (checkboxes, Dev Agent Record, Status)
