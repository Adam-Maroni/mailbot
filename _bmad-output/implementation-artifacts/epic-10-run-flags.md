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

---

## Story 10-4 Run 1 — 2026-07-06 — EXECUTED (hybrid: Adam-hands-on Discord walk + orchestrator evidence capture; ~$0.11 haiku cents; COMPLETE pending Adam verdicts)

**Invocation:** Adam typed `autonomous story run 10-4`. Pre-flight found two blockers, both Adam-resolved in-session: (1) **degraded mode still active** (F-10-3-1/2 — chat walks unrunnable) → Adam chose "Reset now"; executed via `reset_degraded_mode` verb in-container + `docker compose restart mailbot-api` (both processes re-seeded; re-trip impossible — Layer-3 entry is crossing-only and the inflated counter sits far above the cap); exited 07:54:33Z, verified. F-10-3-1 stays FILED — this was an operator action, not a fix. (2) **Walk surface is Discord chat** (no run-mode binding existed) → Adam chose option (a) hands-on: Adam typed every turn and pasted replies; orchestrator (claude-fable-5) drove the case protocol, captured `router_calls`/mcp-log provenance read-only, and applied the doc-drift edits. Story file inline-authored from epics.md § Story 10.4 (Step 2.2 Branch A).

**Walk record (full detail in `10-4-walk-evidence.md`):** 8 README read-family anchors walked as 11 cases (C0 smoke + C1-C8 + 2 sub-cases), 08:05-08:27 UTC. **6 PASS / 5 FAIL / 0 EXCLUDED.** Every reply DB-cross-checked read-only (`mode=ro`): C1 3/3 exact, C2 3/3 exact, C5b aggregates exact (41 emails 2016→Jun 1), C7 7/7 exact in-window, C8 buckets 2+9=11 = last-24h baseline exact. Projection-first held (zero body-reads on list/count turns); C6 exactly one `hydrate_email`, cap constant 5 verified. Provenance rows 13607-13647, zero `degraded:*` reasons post-reset; walk traffic tripped the hourly anomaly detector live (captured).

**Findings F-10-4-1..6 ALL FILED per N.5, zero fixed:**

- **F-10-4-3 HIGH** — `get_thread` unreachable from chat by construction (`EmailProjection` exposes no `thread_id`; agent fabricates → `THREAD_NOT_FOUND` 2/2, log-proven incl. the C3-Stripe reply that dressed the error as "doesn't have a thread"). README thread-summary example cannot succeed.
- **F-10-4-4 HIGH** — enrichment layer has never run in production: `sender_reputation_summary` 0/727 senders, `thread_continuity_note` 0/1753 threads. Story 3-7's verbs have no production trigger.
- **F-10-4-6 HIGH** — `daily_digest_intro` has ZERO router_calls rows all-time; today's delivered digest carries no intro. The documented `ask_router(task_type="daily_digest_intro")` contract (cron-jobs.md §3, epics.md Story 6.5 AC) has never held.
- **F-10-4-1 MEDIUM** — `is_read` never synced (known 5-1 deferral, was undisclosed in README): C1 silently reframes "unread"→"from today"; C4 count flow refuses.
- **F-10-4-5 MEDIUM** — no display-name search: "Who is Steve Gabison" found 0 of 52 existing emails; `get_sender_summary` never invoked on the name form.
- **F-10-4-2 LOW** — transient Anthropic 529s surface as `failed` router rows; Hermes 3-attempt retry absorbs (4/17 rows this session; root-caused live at C8).

**C8 layered honestly:** scheduled slot FIRED today 08:49 local and FAILED under degraded mode (`tools_unsupported` in Discord — live blast-radius capture of F-10-3-1/2, ~49-min scheduler drift noted); manual trigger post-reset DELIVERED end-to-end (`compose_digest` → `finalize_digest_delivery` ok, honesty-tagged manually-triggered).

**Doc-drift rule (a) discharged same session:** README:19 blanket-illustrative sentence rescoped (read family verified, write/slash still illustrative); C1/C2 examples replaced with real sanitized captured output + tags; C3 thread-summary example replaced with an honest currently-broken note (F-10-4-3/4); C4 count row + C5 sender row corrected to walked truth; digest sentence rewritten (buckets verified, intro-never-generated + scheduled-slot-failure caveats). FAIL cases carry no verified tag except as explicitly-marked honest-FAIL documentation.

**CR-cadence determination (story AC-4):** zero of the 6 criteria fire — zero code touched (README + evidence/tracking artifacts only). **CR skipped per cadence binding.**

---

## Story 10-5 Run 1 — 2026-07-06 — EXECUTED (hybrid Adam-hands-on Discord write+slash walk + orchestrator evidence; Console delta $1.31; COMPLETE pending Adam verdicts)

**Invocation:** Adam typed `autononomous story run 10-5`. Pre-flight surfaced the story's hard RUN-MODE BINDING (real spend + real sends + Adam's Discord — not pure-autonomous). Adam chose **"Hybrid hands-on now"** (10-4 Run 1 pattern): Adam typed every Discord turn + authorized spend + read Anthropic Console truth (pre $26.94 / post $28.25 screenshots); orchestrator (claude-fable-5) drove the frozen case protocol, captured `router_calls`/`pause_state`/`action_history`/`action_grants` + Hermes/API logs read-only (`mode=ro`), and applied README doc-drift. Story file inline-authored from epics.md § Story 10.5 (Step 2.2 Branch A). Mid-walk (from W1a) Adam authorized reply-transcription via read-only Discord REST fetch (bot token, never displayed); Adam still typed every user turn.

**Walk record (full detail in `10-5-walk-evidence.md`):** 16 cases (9 slash S1-S9 + 7 write incl. W1a/W1b/S1b/S4b sub-cases), 09:30-13:20 UTC. **10 PASS / 6 FAIL / 0 EXCLUDED.** Real Tier-3 SEND verified at L3 (action 15: 60s cooling-off enforced to 61.7s, real Graph dispatch, Gmail receipt Adam-confirmed); real Tier-2 ARCHIVE verified at L3 (7 newsletters, Outlook-confirmed, pre_state audit rows captured). Sensitivity privacy invariant HELD across 12 gate-refused dispatches (zero body egress DB-proven). Provenance rows 13667-13758; degraded mode never re-tripped; router paused+resumed (2m15s window, CLI-recovered).

**Findings F-10-5-1..12 ALL FILED per N.5, zero fixed** (7 HIGH / 3 MEDIUM / 2 LOW). Headlines:

- **F-10-5-1 HIGH** — Hermes owns the `/` prefix: entire documented MailBot slash surface unreachable in literal form (incl. `/cancel` + `/confirm`); README:190 dispatch claim false. Chat-equivalents (drop the slash) work.
- **F-10-5-11 HIGH** — README's flagship Opus draft pipeline is UNWIRED from chat: Story 5-9 orchestrator has zero production call sites; `draft_reply` 0 chat rows all-time, `tone_style_mirror`+`multi_turn_refinement` 0 rows EVER. Drafts are Haiku-improvised. The epic's $2-4 Opus-spend premise was structurally impossible ($1.31 real delta).
- **F-10-5-7 HIGH** — sensitive-draft escalation broken by construction: grant binds to MCP-session identity (survives `/new`), chat dispatch carries a different identity → token never attaches (repro'd fresh session); one attempt bricks the whole session.
- **F-10-5-5 HIGH** — `mint_sensitivity_token` self-invoked without user confirmation (succeeded twice, log-proven); documented confirm-first choreography unenforced.
- **F-10-5-8 HIGH** — Tier-2 approval never solicited: agent minted grant + queued 7 writes with no "yes"; API `pending_grant` gate was the only stop.
- **F-10-5-4 HIGH** — PAUSED chat deadlock: resume-by-chat impossible while paused; README:293 fix half-false (CLI-only recovery).
- **F-10-5-12 HIGH** — agent self-modified its gitted skill files mid-conversation (`skill_manage patch` ×2 on SKILL.md + new `tier2-grant-pitfall.md`) with confabulated content; captured verbatim, then **reverted** (Adam-decided "follow your reco"); working tree clean, nothing staged.
- MEDIUM: sensitivity refusal UX raw-502+id-leak (F-6); mint-before-propose stuck state + inert documented fix (F-9); false-success narration ×3 (F-10). LOW: NL 1-arg `/model` mapping (F-2); overrides-file wholesale-replace (F-3).

Corroborated not re-filed: 10-1 F1 (pause kills chat — reproduced S5/S6), 9.5.2 one-shot consume-race (S2), F-10-3-1 estimator inflation ($70.37 chart vs $28.25 Console).

**Spend truth (AC-3):** Console $26.94 → $28.25 = **$1.31** over ~6h window (all org traffic incl. background ingest, not walk-only); estimator $0.2498 walk-attributable (zero Opus). Well under the ~$2-4 estimate; F-10-5-11 explains the miss.

**Doc-drift rule (a) discharged same session:** README:17 preamble + Drafting-and-sending (real Coffee-Thursday transcript, cancel+send) + Mailbox-actions Tier-2 (real 7-newsletter walk w/ choreography-failure honesty) + Sensitive/confidential (confidential PASS real, sensitive FAIL note) + Slash-table (10 rows real captured output, type-without-slash header) + Limitations (5 new honest bullets). 7 `verified 10-5` PASS tags; FAIL cases documented honestly, no fabricated output.

**CR-cadence determination (story AC-5):** zero of the 6 criteria fire — zero code touched (README + evidence/tracking only; the agent's self-edit was reverted, not authored by this story). **CR skipped per cadence binding.**

**Epic 10.5 triage inputs from this run:** F-10-5-1 (slash-prefix — cross-cuts the whole Discord surface, arguably charter-level), F-10-5-11 (Opus draft pipeline unwired — largest capability gap), F-10-5-5/7 (sensitivity escalation authorization + session-binding — security-adjacent), F-10-5-8 (Tier-2 approval bypass — security-adjacent), F-10-5-12 (agent self-edits skill files — governance), F-10-5-4 (PAUSED recovery). 7 HIGH is the epic's largest single-story finding count — strong Epic 10.5 spawn signal for the retrospective.

---

## Story 10-6 Run 1 — 2026-07-06 — EXECUTED (pure-autonomous fault-injection walk, full risk envelope Adam-authorized; $0.0109 estimator; COMPLETE pending Adam verdicts)

**Invocation:** Adam typed `autonomous story run 10-6`. Pre-flight surfaced (1) no RUN-MODE BINDING existed and (2) the fault-injection risk envelope. Adam chose **PURE AUTONOMOUS** run-mode + authorized the **FULL** risk envelope (pause/degraded/rate/loop trips + container stop/start + simulated rw-DB rows honesty-tagged + sacrificial-folder mailbox micro-mutations). Orchestrator (claude-fable-5) induced every fault server-side against the RUNNING stack (MCP `/mcp/` mount + `/admin/*` + `/v1/chat/completions` + worker drainer), asserted codes at the layer each contractually surfaces (status/logs/router_calls/DB/refusal payloads), applied documented fixes, asserted recovery, and restored baseline. Story file inline-authored from epics.md § Story 10.6 (Step 2.2 Branch A). Walk-driver scaffolding `scratch/mcp_walk_106.py` (untracked, never staged).

**Walk record (full detail in `10-6-walk-evidence.md`):** all 16 README common-error rows (README:293-308) fault-injected, R15's 3 codes walked as R15a/b/c → **18 verdict rows**, 17:23-18:00 UTC. **13 PASS / 5 FAIL / 0 EXCLUDED** (FAIL: R3, R7, R11, R15a, R15c). Honesty split (D3): 12 INDUCED (R1/R2/R4/R5/R6/R9/R10/R11/R13/R16 + R15a `target_deleted` genuinely induced off the 10-1-F5 soft-delete + R3 real gate refusal, subject-only synthesized) / 5 SIMULATED honesty-tagged (R7/R8 staged budget counters, R12 oauth failure counter, R14 send-count, R15b change_marker — each staged a state) / R15c n/a (unreachable dead code). Every FAIL is a documentation-contract defect; **zero product-capability regressions** — every error condition that CAN surface DID surface with a stable code, and every system state recovered.

**Findings F-10-6-1..7 ALL FILED per N.5, zero fixed:**

- **F-10-6-3 HIGH** — `mailbot rederive` crashes on **every** invocation (`KeyError: no adapter registered for 'qwen2.5:3b-instruct-q4_K_M'`): `init_default_adapters()` is called by the FastAPI lifespan (main.py:178) + `python -m …pipeline` (pipeline.py:743) but NEVER by the `rederive` CLI subcommand. The documented recovery fix at README:295 (cross-ref :305) is broken; the actual working recovery is the ingest worker's own "wait a few minutes" pass.
- **F-10-6-2 MEDIUM** — move-induced `target_deleted` is NOT cleared by the documented `mailbot replay <id>` fix (replay re-reads the same local soft-delete and refuses again; only 10-2 revert rows bypass). README:307 replay clause inert for this common case.
- **F-10-6-4 MEDIUM** — `state_drift_noop` (errors.py:63) has ZERO raising sites — unreachable; README:307 hard-asserts a code that can never surface.
- **F-10-6-5 LOW** — `monthly_budget_exceeded` (errors.py:54) has ZERO raising sites — the breach surfaces as the `budget.degraded.entered` log + degraded behavior; README:299 Code cell half dead-code (`degraded_mode_blocked` IS real).
- **F-10-6-6 LOW** — paused refusal carries `provider_error` "router paused", not a `PAUSED` code; README:303's "`PAUSED` state" names a state, contra the "codes are stable strings" framing.
- **F-10-6-7 LOW** — `mailbot logs --filter level=error` crashes on a default Windows console (`UnicodeDecodeError: cp1252`); needs `PYTHONIOENCODING=utf-8`. Host-class-specific.
- **F-10-6-1 INFO** — charter says "17 error rows"; the README table has **16** (verified at 3 commits). Feeds 10-7 row count.

**Corroborated not re-filed:** F-10-3-1 (estimator month ~$70.6 far above the $30 cap — the reason R7 required simulation; genuine crossing unreachable this month); 10-1 F1 / F-10-5-4 (pause blocks chat — R11 refusals ARE that mechanism); 10-1 F5 (move soft-deletes local row — R15a's genuine target_deleted rode it); F-10-5-1 (slash-prefix — R7/R11 fix cells rely on `/budget reset` + `/resume` literals, worked around via verb/CLI).

**Spend truth (AC-3):** $0.0109 estimator-attributable (Haiku recovery micro-calls + R7/R8 crossing calls), **zero Opus** — three orders under the ~$2-4 Console-read threshold; per 10-3 $0-story precedent the estimator is the assertion surface here (Console truth reserved for real-spend stories per `feedback_anthropic_spend_source_of_truth.md`).

**Doc-drift rule (a) discharged same session:** README error-table made evidence-real — 6 FAIL-row corrections (dropped broken `mailbot rederive` clause R3/R13; corrected replay-inert R15; dropped unreachable `state_drift_noop` + `monthly_budget_exceeded` codes; relabeled `PAUSED`→`provider_error`; corrected "Qwen escalates to Haiku" over-generalization) + 10 `verified 10-6` PASS tags + a table-intro note flagging the two dropped dead codes. FAIL rows carry honest corrections, not fabricated output.

**Restoration verified at close:** degraded OFF, pause OFF, oauth counter 0, all synthetic rows deleted (2 router_calls + 18 pending_actions + 1 email + 5 idempotency), sacrificial email E118 back in Inbox (archived→restored via real R15a move), E117 change_marker restored, no open pending actions, 3 containers healthy (mailbot-api restarted ×3 for BudgetGuard counter re-seed, all recovered). Genuinely-failed sends (actions 18, 37) retained as audit truth per AR-D5-2.

**CR-cadence determination (story AC-4):** zero of the 6 criteria fire — zero production code touched (README + evidence/tracking only; `scratch/mcp_walk_106.py` untracked, never staged). **CR skipped per cadence binding.**

**Epic 10.5 triage inputs from this run:** F-10-6-3 (broken rederive CLI — user-facing recovery path dead, HIGH) is the standout for 10.5; F-10-6-2 (replay-inert target_deleted) is adjacent to the 10-2 move-family seam; F-10-6-4/5/6 are dead/mislabeled-code cleanups (cheap, batchable); F-10-6-7 is a host-specific CLI polish. Combined with 10-4's 3 HIGH + 10-5's 7 HIGH, Epic 10's FILED-defect backlog is now substantial — the retrospective's Epic 10.5 spawn decision has strong signal.

---

## Story 10-7 Run 1 — 2026-07-06 — EXECUTED (autonomous docs-closure sweep; $0; COMPLETE pending Adam verdicts)

**Invocation:** Adam typed `autonomous story run 10-7`. Pre-flight clean (0 blockers: deps 10-1..10-6 all done; no run-mode binding — docs-closure story; UI gate N/A; $0). Story file inline-authored from epics.md § Story 10.7 (Step 2.2 Branch A). Repo-only sweep — zero live-stack interaction, zero Router/API calls.

**What shipped (full detail in `10-7-walk-evidence.md`):**

- **AC-1 verified-tag sweep:** 29 walked example anchors + 18 error rows inventoried from the six walk-evidence files and checked against the README. 41 tag sites pre-existing; **3 back-filled** (README:56 thread-summary FAIL note → `10-4-c3+c3b` tag; :194 sensitive-escalation FAIL note → `10-5-w3` tag; :200 slash-table header → `10-5-s1+s4` tag — all citing already-captured evidence, zero invented output). **0 walked examples remain illustrative.** The 4 unwalked anchors (Tier-1 undo chat form, Tier-3 delete, `cost` row, status sample board) explicitly *illustrative*-marked with reasons — never retro-tagged.
- **AC-2 limitations honesty:** the section had zero coverage of the 10-3/10-4/10-6 findings. 4 bullets added: read-family gaps (F-10-4-1/3/4/5/6), estimator inflation + degraded-mode reality (F-10-3-1/2), free-tier classification quality edges (F-10-3-4/5/6), operator recovery-tooling gaps (F-10-6-2/3/7 + dead codes 4/5). Nothing still-true removed.
- **AC-3 verdict table:** **`epic-10-verdict-table.md` published as epic evidence** — Section 1: 29 walked README-example rows (18 PASS / 11 FAIL); Section 1b: 4 EXCLUDED-with-reason; Section 2: 18 error-table rows (13 PASS / 5 FAIL / 0 EXCLUDED) with induced-vs-simulated tags verbatim from 10-6. Roll-up: **31 PASS / 16 FAIL / 4 EXCLUDED across 51 rows**; every row cites its walk-evidence file § + run_id; verdicts transcribed, none re-adjudicated; completeness check both directions clean (discrepancy list empty).
- **Done-flip clauses 2/3/4 DISCHARGED.** Clause 1 completes when 10-7 flips done on Adam-signed verdicts; clause 5 held epic-wide (38 findings FILED, zero absorbed beyond 10-2's pre-declared scope).

**Findings:** zero new findings — transcription-only story; the one self-caught issue (tag-count imprecision 42→41 pre-existing sites) was corrected in-evidence before review.

**CR-cadence determination (AC-4):** zero of 6 criteria fire (README + `_bmad-output/` only, zero code). **CR skipped per cadence; ships under §5.12 self-audit** (pre-review artifact + verdict-table completeness check).

**Gates:** ruff clean on tracked tree (6 pre-existing T201 in untracked `scratch/`), mypy --strict clean (129 files), boundaries exit 0, pytest **1708 passed + 2 skipped + 3 deselected in 217.66s** — byte-identical to baseline.

**Spend:** $0 (no Router/API/container interaction).
