# Epic 10 run flags — Full-Perimeter Live Validation (README-as-Charter UAT)

Modeled on `epic-9-5-run-flags.md`. One section per story run; halts, path decisions, findings dispositions, and CR-cadence determinations land here.

---

## Story 10-1 Run 1 — 2026-07-05 — EXECUTED (Adam-hands-on walk, Claude-assisted; COMPLETE)

**Invocation:** Adam typed `create-story 10-1` (context-engineering session), then chose "Execute the walk hands-on" in the same session — RUN-MODE BINDING satisfied: Adam drove every mailbox-touching action (folder creation, Discord prompt, Outlook verification, drag-and-drop restore) and green-lit the Path B propose ("go"); Claude performed read-only checks, SQL/log evidence capture, and evidence drafting. No dev-agent halt was required.

**Walk record (full detail in `10-1-walk-evidence.md`):**

- Task 0 preflight PASS (OAuth green, drainer live at 2s ticks, DB baselines; degraded-mode-on recorded as non-blocking — $0 walk).
- **Path A (Discord → Hermes) BLOCKED by F1:** router pause (the story's Contract-Pin-4 safety choreography) also blocks Hermes chat (`hermes_aux` → `ask_router` → PAUSED, 3×502 surfaced raw in Discord). `propose_action` never invoked; zero rows queued.
- **Path B (direct verb-level `propose_action`, Adam-green-lit) EXECUTED:** action id=4, `move_to_triage_folder`, tier 1, correct staged `destination_folder_id`. **F4 (CRITICAL) discovered at this instant:** the worker-process drainer dispatched the real Graph write **259 ms after propose, while the router was paused** — `PauseState` is a per-process in-memory singleton; the kill-switch does not cover mailbox writes in the production two-process topology. Blast-radius-by-construction (sacrificial staging) was the only real containment.
- Chain L3-verified: Graph `parentFolderId` == sacrificial folder; **Adam verified in desktop Outlook**; manual drag-and-drop restore; server-side back-in-Inbox confirmed; `router_calls` untouched ($0, Pin 7); Tier-1 silence observed (Pin 5); `GRANT_NOT_NEEDED` + `INVERSE_UNAVAILABLE` refusals captured live verbatim.
- **Findings F1-F6 + B1 ALL FILED per N.5, zero fixed in-walk** (F4 CRITICAL pause-bypass; F5 move soft-deletes local row as `'deleted'`; F6 `EMAIL_UPSERT` never resurrects — walk subject email deliberately left soft-deleted locally as live evidence). pre_state field list for 10-2 delivered (6 items, §5 of evidence).
- **Optional Path A′ (unpaused Discord retry) DECLINED** — with F6 the subject email is invisible to read verbs (mis-resolution risk) and with F4 a mis-resolved Tier-1 move is unstoppable; deferred to 10-5 after 10-2 ships revert.
- README doc-drift discharged same-story (tier-table row 1, verified pipeline-trace example — deliberately NOT a fabricated chat transcript — limitations rewrite; `<!-- verified 10-1, run_id action-4/2026-07-05 -->` convention introduced).

**CR-cadence determination (story AC-5):** zero of the 6 criteria fire — no code authored or changed (evidence/docs/tracking files only; the two ruff T201 hits are in untracked pre-existing `scratch/` from a prior session, outside story scope). **CR skipped per cadence binding.**

**Epic 10.5 triage inputs from this run:** F4 (CRITICAL, safety), F5+F6 (HIGH, local-DB truth), F1+F2 (Hermes/pause UX), F3 (audit), B1 (charter bookkeeping: error table is 16 rows, not 17).

---

## Story 10-2 Run 1 — 2026-07-05 — DEV PASS COMPLETE (Tasks 1-5 + 6.2); HALT at Task 7 per hybrid RUN-MODE BINDING

**Invocation:** Adam typed `create-story 10.2` then `dev-story 10-2` (same session, claude-fable-5). The story's hybrid binding was honored exactly: Tasks 1-5 implemented red-green-refactor + Task 6.2 gates run; **Task 7 (live revert walk) NOT executed — Adam-hands-on required** (one real email + the retained `MailBot-UAT-10-1` sacrificial folder, Outlook-client verification). Zero mailbox-touching actions performed; zero real spend.

**Dev record (full detail in the story Dev Agent Record + File List):**

- RED confirmed pre-implementation (5 representative failures on missing symbols); GREEN at close.
- Shipped per the story's design pins, zero deviations: MOVE_FAMILY registry + reserved `revert_of_action_id` payload key (types.py), `read_move_pre_state` adapter seam (Protocol + fakes + real GET `$select=parentFolderId` via `_request_with_retry` refactor), drainer fail-closed pre_state capture (`pre_state_capture_failed:*`, check-class — no history row, no dispatch), revert-row `target_deleted` bypass + local soft-delete repair (`EMAIL_CLEAR_SOFT_DELETE`), reverter move branch (state-dependent inverse + `PRE_STATE_MISSING`), propose reserved-key guard, mcp_server + SKILL.md stale-claim updates.
- **Fail-closed uniformity decision stands as pre-pinned** (Tier-2 moves also require a successful pre-state read; relaxation to best-effort is a one-line change if Adam vetoes — record here if so).
- Tests **+12 net** (13 new, 1 removed whose premise ended). Suite **1707 + 2 skipped + 3 deselected** (baseline 1695). ruff clean (2 pre-existing untracked `scratch/` T201), mypy clean (129 files), boundary checker exit 0.
- Notable in-pass observations (not defects): (1) the new fail-closed path fired correctly against the ARCHIVE wiring test's catch-all mock (`parent_folder_id_absent`) — mock updated to serve the GET; (2) test-design interaction: a revert row draining before a plain row on the SAME email repairs its soft-delete and un-gates the plain row — split onto two emails; real-world equivalent is benign (repair only fires on applied revert rows).

**Remaining to story done:** Task 6.1 MANDATORY-CR full scope (criterion 6 pre-declared; reviewer model ≠ claude-fable-5) → Task 7 Adam-hands-on revert walk (⚠ F4 live: no pause protection, blast-radius-by-construction; ⚠ F6 staging: pick a fresh subject email, the 10-1 Railway email is still soft-deleted locally) → Task 8 README doc-drift with the walk's run_id, same commit. Story flipped to `review`.

---

## Story 10-2 Run 2 — 2026-07-05 — MANDATORY-CR (Task 6.1) COMPLETE: 3/3 Patches applied = 100% + 1 Defer + 7 Dismissed

**Invocation:** Adam typed `code review 10-2` (bmad-code-review skill). Orchestrator claude-fable-5; all three review layers (Blind Hunter diff-only / Edge Case Hunter diff+repo / Acceptance Auditor diff+spec+pins) dispatched as parallel subagents on **sonnet** — reviewer ≠ dev model (fable-5) honored per AC-5 / 9.5-retro A5; recorded deviation from the skill's same-model default, epic norm controls. Diff source: uncommitted tree vs baseline_commit a28cd83 (20 files, +1075/−87).

**Layer outputs:** Blind Hunter 9 findings (1 MEDIUM, 8 LOW); Edge Case Hunter 2 (1 HIGH, 1 MEDIUM — merged, same fix); Acceptance Auditor **0 violations** (AC-1/2/4, PIN A–H, design pins 1–4, scope fence incl. file-list conformance and F4/F6/F1-F3 untouched; all 13 Task-5 tests confirmed asserting per spec) + 2 non-blocking observations.

**Triage (11 raw + 2 observations → 3 Patches / 1 Defer / 7 Dismissed):**

- **CR-10-2-1 (HIGH, Patch, applied):** concurrent `revert_action` TOCTOU — each DB call is its own `BEGIN IMMEDIATE` transaction, so two racers both pass the `ALREADY_REVERTED` gate read and queue duplicate inverse rows; newly dispatch-reachable for moves this story (pre-10-2 every move refused `INVERSE_UNAVAILABLE`). Fix: claim-first — `ACTION_HISTORY_MARK_REVERTED` (already `AND reverted_at IS NULL`-guarded) now runs BEFORE the inverse insert with rowcount checked; loser refuses `ALREADY_REVERTED`, no duplicate Graph dispatch. Absorbs the sibling unchecked-rowcount finding. +1 deterministic regression test (stale-read race simulation, `test_revert_claim_loser_refused_without_duplicate_inverse`).
- **CR-10-2-2 (MEDIUM, Patch, applied):** `_is_revert_row` trusted the reserved payload marker alone — the `_check_tier_1` deleted-gate bypass and `EMAIL_CLEAR_SOFT_DELETE` repair never re-validated `is_move_family` at point of use (both fail-safes leaned on the single propose-boundary guard). Fix: `_is_revert_row` now requires `is_move_family(row.action_type)` AND the marker.
- **CR-10-2-3 (LOW, Patch, applied):** NOT_APPLIED test now seeds the CR-4-4-2 history row with POPULATED pre_state — the AC-1 "misleading pre_state" structural pair is proven literally (real source_folder_id present, refusal still fires on status alone).
- **CR-10-2-D1 (Defer → deferred-work.md):** residual double-revert race for legacy rows with NO action_history row (4-4 tolerance — nothing to claim on); pre-existing since 4-8, static-map types only, consequence is a duplicate idempotent mark/category inverse, not a Graph move. Epic 10.5-candidate.
- **Dismissed 7 with evidence** (full list in story Review Findings): capture-vs-dispatch folder race (inherent to spec-pinned drain-time capture), `EMAIL_CLEAR_SOFT_DELETE` guard asymmetry (Task-3.3-verbatim SQL, idempotent, success-path-only), refusal-precedence untested (any refusal blocks), PRE_STATE_MISSING message granularity (no live malformed path), `revert_of_action_id` value unvalidated (presence-only semantics, fabrication outside threat model), adapter/reverter validation-philosophy asymmetry (masked by `str()` coercion), integration-mock per-email scoping (hypothetical future reuse only).

**Gates re-run post-patches (Task 6.2):** pytest **1708 passed + 2 skipped + 3 deselected** (+13 net vs 1695 baseline), ruff clean, mypy 129 files clean, `check_boundaries.py` exit 0.

**Remaining to story done:** Task 7 Adam-hands-on revert walk (⚠ F4 live, ⚠ F6 staging — fresh subject email) → Task 8 README doc-drift with the walk's run_id, same commit. Story stays `review`.

---

## Story 10-2 Run 3 — 2026-07-05 — LIVE REVERT WALK (Task 7) + doc-drift (Task 8): move → revert → Adam-verified back; $0, zero new defects

**Invocation:** same session as Run 2 — Adam picked "run the Task 7 revert walk" from the CR close-out. Full captures in `10-2-walk-evidence.md`.

- **Preflight:** image REBUILT from working tree (baseline a28cd83 + staged story diff incl. all 3 CR patches) and content-verified in-container before any write (A1 image-drift lesson); drainer ticking 2s; /health 200; baselines pending MAX(id)=4 / history 4 / router_calls 13579.
- **Chain:** action id=5 `move_to_triage_folder` (subject: Anthropic cache notification, Adam-picked fresh — 10-1 Railway F6 residual preserved) → **pre_state POPULATED with real Inbox id, captured 14:12:36.808 strictly before applied 14:12:37.020** (THE walk assertion, vs '{}' on legacy id=4) → Adam Outlook verify in sacrificial folder → `mailbot revert 5` (CLI) → inverse id=6 applied: payload destination == pre_state source (byte-identical), `revert_of_action_id=5`, **3.2 target_deleted bypass fired live** (local row was F5-soft-deleted at 14:12:44, ~8s post-move), **3.3 repair fired live** (`action.drainer.revert.local_row_repaired`, deleted_at/removed_reason NULL), audit symmetry (row 6's own pre_state = sacrificial folder), `reverted_at` set on id=5 → Graph parentFolderId back to Inbox → **Adam Outlook verify #2: "confirmed"**. Mailbox as found.
- **Post-checks:** second `revert 5` → `ALREADY_REVERTED` (idempotency live, post-CR-10-2-1 race-atomic); `revert 4` (legacy) → `PRE_STATE_MISSING` verbatim (id=4 was still INSIDE the 24h window — the story's guessed `REVERT_WINDOW_EXPIRED` never fired; the truer legacy refusal captured instead); router_calls unchanged ($0).
- **F-track: zero new product defects.** One ops note, not filed: in-container `python scripts/mailbot.py revert` initially failed `unable to open database file` — root-caused to **host Git-Bash MSYS path mangling** of the bare `/data/mailbot.db` arg before docker exec; `MSYS_NO_PATHCONV=1` eliminates it; CLI itself correct.
- **Task 8 doc-drift discharged same session:** README:118 tier-row rewrite (triage-move now revertible, legacy `PRE_STATE_MISSING` caveat), README:144 revert-path half (revert repairs local row; plain-move drop-out kept), README:370 limitations bullet rewritten to walked truth with honest caveats (legacy rows, Tier-2 still manual) — all tagged `<!-- verified 10-2, run_id action-6/2026-07-05 -->`; README:224 `mailbot revert` row + :146-150 undo example verified still-true, untouched; mcp_server/SKILL.md halves were done in the dev pass.
- **Verdicts:** PASS×5 proposed (per-AC table in walk evidence §7); Adam signature pending → story `done` on signature.

---

## Story 10-3 Run 1 — 2026-07-06 — EXECUTED (autonomous, read-only audit, $0; COMPLETE pending Adam verdicts)

**Invocation:** Adam typed `/autonomous-story-run 10-3`. No run-mode binding on this story (deliberate — every step is read-only SQL against the live DB via `mode=ro` URI, zero mailbox mutation, zero Router dispatch, $0 spend); the HARD sequencing gate (after Epic 9.5 close) was verified satisfied at pre-flight. Story file inline-authored from epics.md § Story 10.3 (Step 2.2 Branch A). Executor split: claude-fable-5 ran queries + spot-scoring; Adam signs verdicts at Phase 3.5.

**Audit record (full detail in `10-3-walk-evidence.md`):**

- **AC-1 usage:** qwen = 9,651 of 13,600 router calls (**71.0%**) — charter claim "free tier does most of the volume" CONFIRMED; 100% of the ingest classification trio. Conformance vs policy-v1-2026-07-04: **zero silent routing drift** — every off-policy (model, task) pair is explained by the closed `model_chosen_reason` set (benchmark `override:api:force_model`, `degraded:haiku→qwen`, `slash_command:*:adam`, `sensitivity_gate:refused`).
- **Headline operational find:** `degraded_mode_state` **active since 2026-07-03T14:41:24Z, `exited_at=NULL`** — the budget guard's $30 monthly hard cap (budget.py:37; distinct from the $35 Anthropic Console cap) tripped mid-9.5.3-benchmark on pre-A2 3× inflated opus placeholder pricing (est. $62.58 opus eval spend vs ~$26 Console-real for all July; DB-cumulative $35.37 at entry, counter-vs-ledger note in evidence §1.4). Honest counter would sit UNDER the cap — degraded would not be active. Estimated-July now $70.24 (234% of cap per live `mailbot status`) → degraded persists until Aug 1 or manual reset. Since 07-05 all Anthropic-policy ingest tasks are qwen-served; qwen tool-call turns fail 18/18. *(cap figure corrected $35→$30 during the 2026-07-06 delegated verification walk)*
- **AC-2 quality spot-score:** 29 labels (26 distinct emails), stratified tail-biased draw (methodology + posture inheritance documented in evidence §2.1 — single-evaluator claude-fable-5, categorical agreement vs the prompts' own rubrics, NOT the benchmark pipeline, per post-9.5.4 single-evaluator-trusted posture). 10 AGREE / 5 BORDERLINE / 14 DISAGREE. Patterns P1–P6 identified, headline: coarse `human` over-triggers on personalized automation (57.9% human share; ≥27.8% of human rows from automation-pattern senders) and fine `automated` escape valve NEVER fired (0/1,105).
- **Reliability find:** coarse_class + fine_class have **never returned first-attempt `ok` in 3,042 lifetime calls** (100% schema-fail-retry) — the F24-style required-JSON-fields fix shipped for sensitivity v2/v3 was never propagated to the sibling v1 prompts. sensitivity_class current-era (v3 since 06-07) is 100% ok — its historical 70% failure rate is F24/F27 archaeology, corroborated not re-filed.
- **Findings F-10-3-1..6 ALL FILED per N.5, zero fixed** (2 HIGH: stuck-degraded-on-inflated-counter, qwen-tool-call-hard-fail; 3 MEDIUM: degraded action_extraction ~45% fail, coarse/fine 2× retry tax, P1+P2 misclassification cascade; 1 LOW: sensitivity edge behaviors P3–P6). Epic 10.5 triage inputs.

**CR-cadence determination (story AC-4):** zero of the 6 criteria fire — zero code touched (evidence/tracking artifacts only). **CR skipped per cadence binding.**
