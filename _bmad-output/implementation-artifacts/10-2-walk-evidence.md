# Story 10-2 Walk Evidence — Live Revert Walk (move → revert → verified back)

**Session:** 2026-07-05 ~14:05–14:25Z, Adam-hands-on + claude-fable-5 orchestrating (same session as the MANDATORY-CR).
**Chain walked:** propose `move_to_triage_folder` → drain (pre_state captured from Graph) → real Graph dispatch → Adam Outlook verify → `mailbot revert` → inverse row drain (deleted-gate bypass + local-row repair) → Adam Outlook verify back-in-Inbox.
**Spend:** $0 — `router_calls` MAX(id) = 13579 before, during, and after (no Router involvement on this path, 10-1 Pin 7 re-confirmed).
**Code under walk:** working tree at baseline_commit `a28cd83` + Story 10-2 staged changes **including all 3 MANDATORY-CR patches** (CR-10-2-1/2/3). Story code is staged-uncommitted; the container image was rebuilt from the working tree this session (9.5-retro A1 image-drift lesson honored) and the running image was verified to contain both the story seam (`MOVE_FAMILY` size 5) and the CR-10-2-2 patch (`is_move_family` re-check in `_is_revert_row`) via in-container `inspect.getsource` before any mailbox write.

---

## 0. Preflight (Task 7.0)

- HEAD `a28cd83` (= story baseline_commit); story diff staged-uncommitted (recorded honestly — the image build bakes the tree, not a commit).
- `docker compose ps`: mailbot-api / mailbot-hermes / mailbot-ollama all Up; mailbot-api **rebuilt + recreated this session** (`docker compose up -d --build mailbot-api`), healthy post-restart.
- `/health` 200: `{"ok":true,"sync_last_outcome":"ok","sync_minutes_since_last_ok":0.27,"sync_health_alarm":false}` — OAuth de-facto green (delta sync running on a live token).
- Drainer ticking at 2s in the NEW container (`action.drainer.tick.start/done` observed live).
- DB baselines: `pending_actions MAX(id)=4`, `action_history COUNT(*)=4`, `router_calls MAX(id)=13579`.
- Legacy row confirmed: id=4 `move_to_triage_folder`, `applied`, `terminal_at 2026-07-05T09:09:46.708Z`, `pre_state='{}'`. NOTE: id=4 is still **inside** the 24h window at walk time — the Task 7.6 expectation of `REVERT_WINDOW_EXPIRED` was wrong in the story text; the actual (and better) legacy refusal captured is `PRE_STATE_MISSING` (§6).

## 1. Staging (Task 7.1)

- **Sacrificial folder:** `MailBot-UAT-10-1` (retained empty from 10-1), re-captured this session via container Graph seam: `GET /me/mailFolders/inbox/childFolders?$top=50` → id `AQMkADAwATYwMAItYTJhYi01MzMAZi0wMAItMDAKAC4AAAMo0axGHnyuT5vdoHoFosMoAQCLEw8Z0ndEQJbnH-wBocYBAAkplpvaAAAA`, `totalItemCount: 0`.
- **Subject email (fresh — 10-1 Railway residual deliberately NOT consumed, F6 evidence preserved):** Adam picked from 8 candidates: *"Your Claude API prompt cache hit rate is low"* (no-reply@…anthropic…, received 2026-07-05T10:07), graph_id `AAkALgAAAAAAHYQDEapmEc2byACqAC-EWg0AixMPGdJ3RECW5x-8AaHGAQAJKZfujgAA`.
- Local row pre-walk: `deleted_at=NULL, removed_reason=NULL` (clean — passes `_check_tier_1`).
- Pre-move source folder: `GET /me/messages/{id}?$select=parentFolderId` → 200, `parentFolderId` **byte-identical to the well-known Inbox id** (`…ACAQwAAAA=`, cross-checked against `GET /me/mailFolders/inbox`). Adam's Outlook view agrees (Inbox).
- Graph reads used the worker's cached `oauth_state.access_token` (refreshed by the worker every 240s) — **no refresh-token exchange performed** (no rotation risk), no token ever left the container process or entered chat.

## 2. Move (Task 7.2) — action id=5

Payload byte-verified against the staged folder id BEFORE propose (F4 discipline: dispatch is unstoppable ~2s after propose; blast-radius-by-construction is the only containment).

- Propose (in-container `propose_action`, Path B direct verb per 10-1 precedent): `ok=True action_id=5 tier=1 status='pending' requires_grant=False` at `proposed_at=2026-07-05T14:12:35.781Z`.
- **THE new assertion this walk exists for — `action_history.pre_state` POPULATED (vs `'{}'` on legacy id=4):**
  ```json
  {"source_folder_id": "AQMkADAwATYwMAItYTJhYi01MzMAZi0wMAItMDAKAC4AAAMo0axGHnyuT5vdoHoFosMoAQCLEw8Z0ndEQJbnH-wBocYBAAACAQwAAAA=", "captured_at": "2026-07-05T14:12:36.808791Z"}
  ```
  `source_folder_id` byte-identical to the pre-move Inbox `parentFolderId` captured at staging.
- **Capture strictly before dispatch** (drainer logs, verbatim):
  ```
  {"ts":"2026-07-05T14:12:36.808864Z","event":"action.drainer.pre_state.captured","action_id":5,"action_type":"move_to_triage_folder","tier":1}
  {"ts":"2026-07-05T14:12:37.020501Z","event":"action.drainer.row.applied","action_id":5,"action_type":"move_to_triage_folder","tier":1}
  ```
- Terminal: `status='applied'`, `terminal_at=2026-07-05T14:12:37.014Z` (~1.2s propose→applied). Payload byte-check vs staged destination: True.
- Graph re-read: `parentFolderId` == `MailBot-UAT-10-1` → True.
- **F5 fired live on this walk too:** local row soft-deleted by delta sync at `2026-07-05T14:12:44.697Z` (`removed_reason='deleted'`, ~8s post-dispatch) — establishing the exact precondition the Task 3.2 revert-row bypass exists for.

## 3. Adam Outlook verification #1 (Task 7.3 — AC-3 first half)

**Adam attestation (2026-07-05, desktop Outlook):** "The mail is inside the folder named MailBot-UAT-10-1" — email physically in the sacrificial folder, not merely inferred from 2xx/Graph re-read.

## 4. Revert (Task 7.4) — inverse action id=6

Fired via the CLI surface (README:224): `python scripts/mailbot.py revert 5 --db-path /data/mailbot.db` in-container →
```
action 5 reverted; revert_action_id=6 queued for drain
```
(Ops note, NOT a product defect: the first two CLI attempts failed with `sqlite3.OperationalError: unable to open database file` — root-caused to Git-Bash **MSYS path mangling on the Windows host** rewriting the bare `/data/mailbot.db` argument to a host path before it reached `docker exec`. Reproduced, then eliminated with `MSYS_NO_PATHCONV=1`; the CLI itself is correct and all subsequent CLI calls used the env guard.)

- **Inverse row 6:** `move_to_triage_folder`, tier 1, `status='applied'`, `terminal_at=2026-07-05T14:17:17.675Z`; payload `destination_folder_id` **byte-identical to pre_state.source_folder_id (Inbox)**, `revert_of_action_id=5`.
- **Task 3.2 bypass fired live:** row 6 drained + applied while the subject's local row was soft-deleted (`deleted_at=2026-07-05T14:12:44Z` at drain time) — the exact F5 state that would have refused `target_deleted` without the bypass.
- **Task 3.3 repair fired live** (log verbatim):
  ```
  {"ts":"2026-07-05T14:17:17.497671Z","event":"action.drainer.pre_state.captured","action_id":6,"action_type":"move_to_triage_folder","tier":1}
  {"ts":"2026-07-05T14:17:17.682758Z","event":"action.drainer.row.applied","action_id":6,"action_type":"move_to_triage_folder","tier":1}
  {"ts":"2026-07-05T14:17:17.688736Z","event":"action.drainer.revert.local_row_repaired","message":"drainer revert applied — local soft-delete cleared","action_id":6,"action_type":"move_to_triage_folder"}
  ```
  Post-revert local row: `deleted_at=NULL, removed_reason=NULL`.
- **Audit symmetry for free (AC-2 pin):** row 6's OWN `action_history.pre_state.source_folder_id` = the sacrificial folder (`…AAkplpvaAAAA`) — a revert of the revert would know where to go.
- `reverted_at=2026-07-05T14:17:15.685Z` set on action 5's history row.
- Graph re-read: subject `parentFolderId` back to Inbox → True.

## 5. Adam Outlook verification #2 (Task 7.5 — the AC-3 clause)

**Adam attestation (2026-07-05, desktop Outlook):** "confirmed" — email back in Inbox, `MailBot-UAT-10-1` empty again. Mailbox as found.

## 6. Post-checks (Task 7.6)

- Second `mailbot revert 5` (CLI, verbatim): `REFUSED: ALREADY_REVERTED: action_id 5 was already reverted at 2026-07-05T14:17:15.685749Z` — idempotency live (and post-CR-10-2-1, the claim is race-atomic).
- Legacy `mailbot revert 4` (CLI, verbatim): `REFUSED: PRE_STATE_MISSING: action_id 4 has no usable pre_state (source_folder_id) — rows drained before Story 10-2 recorded pre_state='{}'; refusing to guess a destination folder` — the canonical legacy-row refusal, live (id=4 was still inside the 24h window, so the story's guessed `REVERT_WINDOW_EXPIRED` never fired; `PRE_STATE_MISSING` is the truer legacy evidence).
- Local row repaired: `deleted_at IS NULL`, `removed_reason IS NULL` ✓ (§4).
- `router_calls` MAX(id)=13579 unchanged → $0 ✓.

## 7. Per-AC verdicts (PASS / PARTIAL-PASS / FAIL — Adam-signed)

| AC | Verdict | Evidence |
| --- | --- | --- |
| AC-1 pre_state captured before dispatch, never misleading | **PASS** (Adam-signed 2026-07-05) | §2: populated pre_state, capture-log ts strictly < applied ts, byte-identical to staged Graph read; "never misleading" discharged structurally (NOT_APPLIED gate) + CR-10-2-3 test seeds populated pre_state on a failed row |
| AC-2 Tier-1 revert via same Graph seam; clean refusal on missing pre_state | **PASS** (Adam-signed 2026-07-05) | §4: inverse row through the same drainer/adapter seam with own audit row + pre_state symmetry; §6: `PRE_STATE_MISSING` live on real legacy id=4 |
| AC-3 live revert walk, Adam-verified in Outlook both directions | **PASS** (Adam-signed 2026-07-05) | §3 + §5 attestations; mailbox as found |
| AC-4 regression tests +8-12 net-new | **PASS** (Adam-signed 2026-07-05) | +13 net (12 dev + 1 CR); suite 1708+2+3; all four AC-named areas covered (capture, revert dispatch, missing-pre_state refusal, idempotency) |
| AC-5 MANDATORY-CR full scope, reviewer ≠ dev model | **PASS** (Adam-signed 2026-07-05) | sonnet reviewer layers vs fable-5 dev; 3/3 Patches = 100% + 1 Defer + 7 Dismissed; run-flags § "Story 10-2 Run 2" |

**Signature (10-1 convention), verbatim, 2026-07-05 in-session:** Adam selected **"Sign all PASS"** ("All five ACs signed PASS — story 10-2 flips to done").

## 8. F-track

**Zero new product defects found this walk.** The single anomaly (CLI `unable to open database file`) root-caused to host-side Git-Bash MSYS path mangling — harness/ops note (§4), not a MailBot defect; nothing to file per N.5. Pre-existing FILED findings behaved exactly as 10-1 documented: F5 soft-delete fired at ~8s (§2), F6 non-resurrection made the 3.2 bypass + 3.3 repair load-bearing (§4). F4 remains live and was treated as such (payload byte-verify before propose; no reliance on pause).

**Deliberate residuals at walk close:** 10-1 Railway email remains soft-deleted locally (F6 evidence preserved, untouched); sacrificial folder `MailBot-UAT-10-1` retained (empty) for any future move-family walk; `scratch/` untracked leftovers untouched.
