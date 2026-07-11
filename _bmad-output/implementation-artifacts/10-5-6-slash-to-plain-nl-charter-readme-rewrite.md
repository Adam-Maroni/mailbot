---
baseline_commit: bc5cef2f0ca3b3bdd7e5b044acae03850f3bf92c
---

# Story 10.5.6: Slash → plain-NL charter README rewrite + recognized-phrase control dispatch

Status: done

## Story

As Adam,
I want the README rewritten to drop the `/command` metaphor entirely — documenting intents in plain natural language instead of a slash table — with a deterministic recognized-phrase dispatch contract for the control verbs that touch the mailbox or the kill-switch,
So that the documented syntax is the syntax that actually works, and control verbs (cancel/confirm/pause/resume, plus "yes, escalate" and model-override) are reliably understood by exact-match dispatch, not free-form LLM interpretation that could re-open the false-narration class.

## Context — why this story exists (Cluster B / charter, retro §8.7 / B9)

Epic 10's perimeter walk (Story 10-5) proved that the **entire documented MailBot slash surface** (README §188-207, including load-bearing `/cancel` and `/confirm`) never reaches the MailBot agent: Discord reserves the `/` prefix for application commands, and the Hermes runtime above MailBot owns that namespace (`/model` opens Hermes's own picker; everything else bounces "Unknown command"). This is **architectural, not a missing registration** (F-10-5-1 HIGH). The walk also proved plain text ALREADY works once the slash is dropped (`spend month`, `cancel 14`, `mute newsletter` all dispatched).

Two follow-on live findings, both filed to this story, established the **second half** of the problem — free-form interpretation of control phrases is unreliable (the "false-narration class"):

- **F-10-5-6-W1 (from 10-5-5 Discord walk, 2026-07-11):** "use qwen for next request" → the Hermes persona *replied* "Qwen is now armed... expires at 2026-07-11T09:12:33Z" but **never called `set_model_oneshot`** (mailbot-api logs show only `pull_pending_notifications`; the expiry timestamp was confabulated — 27 min *before* the arming turn). The same phrase DID dispatch the verb 30 min earlier — non-deterministic. Root cause: **the persona narrated a control action without issuing the verb.** `router/oneshot.py` TTL/eviction is correct; the bug is persona-side. (See 10-5-5-walk-evidence.md § F-10-5-6-W1.)
- **F-10-5-2-W2 (from 10-5-2 Task 5 live walk, 2026-07-10):** after a user "yes, escalate", the agent does **not** re-attempt the sensitive dispatch — it re-emits the SKILL.md refusal template instead of issuing the `mint_sensitivity_token` tool call, so the (working, proven) API-layer escalation authorization is never consumed. Same persona-self-narration class. **This is what blocks 10-5-2's AC-4 live end-to-end** despite the API layer being ready. (See 10-5-2-walk-evidence.md § AC-4.)

Both findings are the **F-10-5-1 / F-10-5-10 persona-self-narration class** this story exists to close. The fix is a two-tier dispatch contract: read/status/discovery intents stay free-NL (the agent parses and dispatches), but **control verbs that touch the mailbox or kill-switch dispatch via a deterministic recognized-phrase contract** — the persona is instructed that specific exact phrases MUST map to a specific verb call, not "usually understood" free-form interpretation.

### Boundary reality (verified against source — the recurring Epic 10.5 theme)

The dispatch layer is a **persona/agent-contract surface**, and in this repo that surface is **`hermes-config/`** — tracked, bind-mounted into the Hermes container, and already validated by offline structural tests:

- `hermes-config/skills/mailbot/SKILL.md` — the MailBot verb-catalog + control-flow the Hermes agent reads. Currently riddled with the `/command` slash metaphor (§236-361 "Slash-command verbs", `/cancel`/`/confirm`/`/pause`/`/resume`/`/model` examples) that F-10-5-1 proved unreachable.
- `hermes-config/AGENTS.md` — operational rules incl. Rule S (Recovery Action Expressivity, §277-321) and the Tier-2/Tier-3 confirmation flows (which still cite `/cancel <id>` and `/confirm <id>`).
- `hermes-config/SOUL.md` — identity/persona (no slash content; not rewritten by this story beyond consistency).
- `tests/integration/test_hermes_persona_files.py` — the offline structural drift test that already asserts load-bearing markers in these three files.

This is the **same pattern** as Story 9-10 (config.yaml slash-registration drift test), Story 5-5 (persona-file structural tests), and Story 10-5-2 AC-2 (Hermes-side hardening): the **dev-codeable** work is (1) the README charter rewrite, (2) the persona-contract recognized-phrase dispatch layer in `hermes-config/*.md`, and (3) a drift/structural test that enforces the recognized-phrase contract is present and the dead slash metaphor is gone. The **runtime proof** that the persona now issues the verb deterministically on a recognized phrase is a **live Discord walk** — Hermes runs an LLM persona this repo cannot unit-test, so behavioural confirmation is Adam-hands-on, exactly like 10-5-2/10-5-3/10-5-4/10-5-5.

**RUN-MODE BINDING: HYBRID.** Tasks 1-4 (README rewrite + persona-contract dispatch layer + drift test + MANDATORY-CR) ARE dev-story / autonomous-story-run compatible. Task 5 (live Discord walk verifying the persona deterministically dispatches cancel/confirm/pause/resume + "yes, escalate" + "use qwen") is **Adam-hands-on** (small or $0 real spend) — the dev agent HALTs at Task 5, flips to `review`, and logs to `epic-10-5-run-flags.md`. This mirrors the 10-5-2/10-5-5 binding-marker precedent.

## Acceptance Criteria

**AC-1 — README charter rewrite (drop the slash metaphor).**
**Given** F-10-5-1 (the whole slash surface is unreachable — Hermes owns the `/` prefix)
**When** the README is rewritten
**Then** the "Slash commands" table (§198-217) is removed and replaced with a plain-NL "Talking to MailBot" section that documents *intents* (not a slash table); the write examples (the `/cancel 14` / `/confirm` prose in §69-107 and §166-194), the error-table fix cells that cite `/pause`/`/resume`/`/budget reset`/`/confirm`, and the §386 slash-honesty limitation bullet are all rewritten to plain-NL intents; the interim "type these WITHOUT the leading `/`" honesty note is SUPERSEDED (plain NL is now the actual contract, not a documented workaround). No `/command` form is presented as the way to invoke a MailBot intent anywhere in the README (native Hermes `/model` opening its own UI may still be *described* as the reason plain NL is used).

**AC-2 — two-tier recognized-phrase dispatch contract in the persona files.**
**Given** the two-tier load-bearing constraint (retro §8.7)
**When** the dispatch contract is written into `hermes-config/skills/mailbot/SKILL.md` + `hermes-config/AGENTS.md`
**Then** read/status/discovery intents (spend, cost, policy table, mute list, digest, find/summarize) are documented as free-NL (the agent parses intent and dispatches), AND the control verbs that touch the mailbox or the kill-switch — **`cancel <id>` → `cancel_action`, `confirm`/"yes, escalate" → the confirmation/escalation dispatch, `pause`/`resume` → `pause_router`/`resume_router`, and model-override phrases ("use qwen", "use haiku", "use opus") → `set_model_oneshot`** — are documented as a **deterministic recognized-phrase contract**: an explicit exact-match phrase → exact verb table that the persona MUST follow by issuing the verb call, NOT by narrating an outcome.
**And** the contract explicitly states the anti-pattern it forbids: **narrating a control action ("Qwen is now armed…", "Escalation confirmed…") without issuing the corresponding tool call is prohibited** — this is the F-10-5-6-W1 / F-10-5-2-W2 / F-10-5-10 false-narration failure the contract exists to prevent. The two inherited findings (F-10-5-6-W1 "use qwen", F-10-5-2-W2 "yes, escalate") are named in the contract as the motivating cases.
**And** the dead `/command` slash examples in SKILL.md (§236-361) and AGENTS.md (the `/cancel <id>` / `/confirm <id>` prose) are rewritten to the plain-NL recognized-phrase forms.

**AC-3 — discoverability tie-in via the B7 envelope.**
**Given** the discoverability tie-in (retro §8.7 + 10-5-2's `user_facing_guidance` envelope)
**When** a refusal or ambiguous request surfaces
**Then** the persona contract documents that the B7 `user_facing_guidance` field (RecoveryAction, shipped in 10-5-2) is how the exact working phrase reaches the user at the moment of need ("to abort this, type: cancel 14") — the envelope replaces the dead slash table as the mechanism by which users learn the syntax. (Contract/documentation requirement — the envelope machinery already exists; this AC binds the persona to *use* it as the discoverability surface and the README to *point at* it rather than at a slash table.)

**AC-4 — enforceable structural drift test.**
**Given** these are persona-contract + charter-doc surfaces that regress silently (a future edit could re-introduce the slash metaphor or drop the recognized-phrase contract)
**When** the drift test is written
**Then** `tests/integration/test_hermes_persona_files.py` is extended (and/or a sibling test added) to assert: (a) the recognized-phrase control-verb contract is present in `SKILL.md`/`AGENTS.md` (the exact-match phrase→verb markers + the explicit "do not narrate without issuing the verb" prohibition), (b) the dead `/cancel`/`/confirm`/`/pause`/`/resume` slash-invocation examples are gone from the persona files, and (c) the README no longer presents a slash-command invocation table (the "Slash commands" heading / "type these WITHOUT the leading `/`" note is gone). The test passes; the full suite stays green (+N net).

**AC-5 — MANDATORY-CR (load-bearing dispatch contract + charter docs).**
**Given** this story touches the control-verb dispatch contract + charter-level docs
**When** CR cadence is evaluated per the 6 criteria (§5.12)
**Then** criterion 6 (load-bearing dispatch surface) fires → **MANDATORY-CR**, full scope, reviewer model ≠ dev model.

**AC-6 — live runtime verification (Adam-hands-on, Task 5).**
**Given** the persona runs an LLM this repo cannot unit-test
**When** Adam drives a live Discord walk
**Then** each recognized control phrase deterministically issues its verb: `cancel <id>` cancels (router_calls/action_history evidence), `pause`/`resume` gate the router from chat (closing the F-10-5-4 chat-resume gap end-to-end via plain NL), "yes, escalate" consumes the 10-5-2 escalation arm and dispatches (closing F-10-5-2-W2), and "use qwen" issues `set_model_oneshot` with a real ledger row (closing F-10-5-6-W1) — no confabulated "armed…" narration without the verb. Findings filed per N.5; verdicts Adam-signed at Phase 3.5.

## Tasks / Subtasks

- [x] **Task 1 — README charter rewrite (AC-1).**
  - [x] Remove the "## Slash commands" section (§198-217) and replace with a "## Talking to MailBot" plain-NL intents section: a table/list of *intents* (cost, spend, policy table, mute/unmute, cancel `<id>`, confirm / "yes, escalate", pause/resume, budget reset, model-override) in the exact plain-NL phrasing that works, carrying the real captured outputs already in the current table (preserve the `<!-- verified 10-5 ... -->` tags where the output is still accurate; re-label any that referenced the slash form).
  - [x] Rewrite the write-family prose that shows `/cancel 14` (§93/§95/§107) and `/confirm <id>` (§166-194) to the plain-NL recognized phrases (`cancel 14`, `yes, escalate` / `confirm <id> <task>` without slash).
  - [x] Rewrite the error-table fix cells that cite `/pause` / `/resume` / `/budget reset` / `/confirm` (e.g. §305 loop_detected row) to plain-NL.
  - [x] Rewrite the §386-387 slash-honesty limitation bullet: it currently documents the "type WITHOUT the leading `/`" workaround; make plain NL the stated contract (the workaround note is superseded). Keep the honest architectural explanation (Hermes owns `/`).
  - [x] Sweep the README for any other `/command` MailBot-invocation references (`/spend`, `/cost`, `/mute`, `/model <...>` as an invocation) and rewrite. (Native Hermes `/model`-opens-its-own-UI may stay as *explanation*, not as a MailBot invocation.)

- [x] **Task 2 — recognized-phrase dispatch contract in the persona files (AC-2, AC-3).**
  - [x] In `hermes-config/skills/mailbot/SKILL.md`: rewrite the "## Slash-command verbs" section (§236-361) into a "## Control-verb dispatch (deterministic recognized phrases)" section. Add an explicit exact-match phrase → verb table: `cancel <id>`→`cancel_action`; `confirm` / `yes, escalate`→the sensitivity/escalation confirmation dispatch (consume the 10-5-2 escalation arm via `mint_sensitivity_token`); `pause [reason]`→`pause_router`; `resume`→`resume_router`; `use qwen`/`use haiku`/`use opus`→`set_model_oneshot`. Update the `cancel_action`/`confirm`/model verb example blocks (§192-361) to plain-NL trigger phrases (remove `/cancel <action_id>` / `/confirm <email_id> <task>` slash forms).
  - [x] Add the **explicit prohibition**: "Never narrate a control-verb outcome without issuing the verb call. Saying 'Qwen is now armed' / 'Escalation confirmed' / 'Paused' without the corresponding tool call is a defect (F-10-5-6-W1, F-10-5-2-W2, F-10-5-10). On a recognized control phrase you MUST issue the verb; report only what the verb actually returned."
  - [x] Name the two inherited findings as the motivating cases in the contract prose.
  - [x] In `hermes-config/AGENTS.md`: rewrite the Tier-2/Tier-3 flow prose that cites `/cancel <id>` (§136) and `/confirm <id>` (§145) to the plain-NL recognized phrases; add a short cross-reference to the SKILL.md recognized-phrase table; document that `user_facing_guidance` (Rule S / RecoveryAction) is the discoverability surface that surfaces the exact working phrase (AC-3).
  - [x] Keep the two-tier boundary explicit in-contract: read/status/discovery intents remain free-NL; only the mailbox/kill-switch control verbs are deterministic recognized-phrase.

- [x] **Task 3 — structural drift test (AC-4).**
  - [x] Extend `tests/integration/test_hermes_persona_files.py` (RED first): assert SKILL.md contains the recognized-phrase control-verb table markers + the "do not narrate without issuing the verb" prohibition + the two finding IDs; assert the dead slash-invocation examples (`/cancel `, `/confirm `, `/pause`, `/resume` as invocation) are absent from SKILL.md and AGENTS.md.
  - [x] Add a README assertion (extend this test or add a sibling `test_readme_no_slash_invocation_table.py`): the README has no "## Slash commands" heading and no "type these WITHOUT the leading `/`" note; the plain-NL "Talking to MailBot" section exists.
  - [x] GREEN: rewrites from Tasks 1-2 make the assertions pass. REFACTOR: dedupe marker constants, keep the test readable.

- [x] **Task 4 — gates + Dev Agent Record + flip to review.**
  - [x] Run the 4 gates: `ruff check .` (exclude `scratch/` — pre-existing T201 there), `mypy --strict mailbot_api`, boundary check (via ruff), full `pytest -q` (live marker auto-excluded). All green; capture +N net vs baseline 1834+2+3 (10-5-5's close).
  - [x] Fill Dev Agent Record (model, completion notes per AC, File List, change log).
  - [x] Flip Status → `review`; update sprint-status row.

- [x] **Task 5 — MANDATORY-CR (AC-5) then HALT for Adam live walk (AC-6).**
  - [x] MANDATORY-CR: reviewer model ≠ dev model, full scope (this is orchestrated by autonomous-story-run Step 2.4 — a `review`-status handoff).
  - [x] CR fixes applied → **HALT** (hybrid binding). Task 5 live Discord walk is Adam-hands-on — the dev agent does NOT drive it. HALT + walk checklist logged to `epic-10-5-run-flags.md` § Story 10-5-6.
  - [x] **Adam-hands-on live Discord walk (AC-6) — DONE (2026-07-11).** cancel/pause/resume/"yes, escalate" each deterministically ISSUE their verb (DB-verified live). CP3 required the W2/W3 dispatch-seam fix (+ MANDATORY-CR PASS) to complete; `use qwen` (CP4) verb proven working, its walk failure was collateral of the pre-fix session-brick. Adam-decided "bank 10-5-6 here" → `done`. Residuals F-10-5-11 (draft-pipeline reachability) + F-10-5-6-W4 (grant clock-skew) filed as separate story-sized follow-ups. See § AC-6 live walk + § W2/W3 FIX + § MANDATORY-CR.

## Dev Notes

### Technical requirements / boundary

- **This is a docs + persona-contract + test story. Zero `mailbot_api` source logic changes are expected.** The dispatch layer is not a code module in this repo — it is a *contract* the Hermes LLM persona reads. The enforceable artifact this repo can ship + gate is (a) the README, (b) the `hermes-config/*.md` persona files, and (c) the offline structural drift test. Do not invent a `mailbot_api` "recognized-phrase parser" — Hermes owns message dispatch; MailBot exposes MCP verbs. If a code change appears necessary, it is a scope signal — surface it, do not fabricate.
- **Stack:** persona files are Markdown; the test is `pytest` (integration, offline — no Hermes loader, no container). Follow the existing style of `tests/integration/test_hermes_persona_files.py` (module-level `Path` constants, marker-string assertions, `read_text(encoding="utf-8")`).
- **Boundary/lint:** the persona `.md` files are not import-scanned; the new test lives under `tests/integration/` (already allowlisted). No new deps.

### Architecture compliance — files to touch

- `README.md` — AC-1 (slash table removal + write/error/limitation rewrites).
- `hermes-config/skills/mailbot/SKILL.md` — AC-2 (control-verb dispatch contract; §236-361 rewrite + verb example blocks).
- `hermes-config/AGENTS.md` — AC-2/AC-3 (Tier-2/3 flow phrasing §136/§145 + Rule S discoverability cross-ref).
- `tests/integration/test_hermes_persona_files.py` (+ optional sibling README test) — AC-4.
- `_bmad-output/implementation-artifacts/10-5-6-*.md` (this file), `.pre-review.md`, `epic-10-5-run-flags.md`, `story-run-flags.md` — process artifacts.

### The two inherited findings (must be closed by the contract, verified live at Task 5)

- **F-10-5-6-W1** (10-5-5-walk-evidence.md § F-10-5-6-W1): "use qwen" narrated-but-not-dispatched. Contract must make `use qwen`/`use haiku`/`use opus` a recognized phrase → `set_model_oneshot`. `router/oneshot.py` is correct — do NOT touch it.
- **F-10-5-2-W2** (10-5-2-walk-evidence.md § AC-4): "yes, escalate" re-parrots refusal template instead of dispatching. Contract must make "yes, escalate" a recognized phrase that consumes the 10-5-2 `escalation_armed` singleton (migration 027) via `mint_sensitivity_token`. The API layer is ready; this is purely the persona-dispatch contract.

### Testing requirements

- Framework: `pytest` under `tests/integration/`. Offline/structural only (matches Story 5-5 AC-4 precedent — these tests do NOT exercise Hermes's loader; runtime behaviour is the Task 5 walk).
- Coverage: assert the recognized-phrase contract markers PRESENT; assert dead slash-invocation examples ABSENT; assert README slash table ABSENT. Keep assertions marker-based and resilient to prose edits.
- Full suite must stay green; report net delta vs 1834+2+3 baseline (10-5-5 close).

### CR cadence

MANDATORY-CR per §5.12 criterion 6 (load-bearing control-verb dispatch contract + charter docs). Reviewer model ≠ dev model. Full scope.

### References

- `_bmad-output/planning-artifacts/epics.md` § "Story 10.5.6" (lines 4225-4251) + § Epic 10.5 Detail sequencing notes (4030-4053).
- `_bmad-output/implementation-artifacts/10-5-5-walk-evidence.md` § F-10-5-6-W1 (inherited finding).
- `_bmad-output/implementation-artifacts/10-5-2-walk-evidence.md` § AC-4 + § F-10-5-2-W2 (inherited finding).
- `_bmad-output/implementation-artifacts/epic-10-retro-2026-07-07.md` §8.7 (B9 design) + §7 (cluster table).
- `README.md` §69-107 (write examples), §166-194 (Tier-3 + sensitive escalation), §198-217 (slash table), §305 (loop_detected error row), §386-387 (slash-honesty limitation).
- `hermes-config/skills/mailbot/SKILL.md` §192-361 (verb blocks + slash-command verbs), `hermes-config/AGENTS.md` §115-321 (Tier flows + Rule S), `hermes-config/SOUL.md`.
- `tests/integration/test_hermes_persona_files.py` (Story 5-5 AC-4 drift-test precedent), `scripts/check_hermes_config.py`, `tests/integration/test_hermes_config.py`.
- Sequencing: 10-5-6 supersedes the interim "type WITHOUT the leading `/`" note (epics.md:4039); 10-5-2 (done) precedes it and ships the `user_facing_guidance` envelope 10-5-6's AC-3 leans on.
- Durable memory: `feedback_anthropic_spend_source_of_truth.md` (Task 5 spend truth = Console, if any paid turn); `project_hermes_mcp_namespaces_and_session_drop.md` (Hermes MCP quirks); `ops_msys_path_mangling_docker_exec.md` (if Task 5 needs docker exec).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (dev). Review model: claude-sonnet-5 (MANDATORY-CR, reviewer ≠ dev).

### Debug Log

- Boundary verification up front resolved the pivotal scope question: the "recognized-phrase dispatch layer" is a **persona/agent-contract surface**, and in this repo that surface is `hermes-config/` (tracked, bind-mounted into the Hermes container, already drift-tested by `test_hermes_persona_files.py`). Hermes itself is an external image (`hermes:latest`) running an LLM this repo cannot unit-test. So the dev-codeable artifact = README charter rewrite + `hermes-config/*.md` contract + a structural drift test; the runtime proof = Adam's Task-5 Discord walk. Same pattern as Stories 9-10, 5-5, 10-5-2 AC-2.
- TDD: wrote `test_recognized_phrase_dispatch.py` first (RED — 11 failures pinpointing every dead slash surface), then rewrote README + SKILL.md + AGENTS.md to GREEN. Refined the dead-slash matcher to a token-boundary regex so slash-separated prose word-lists ("abort/pause/confirm", "Pause/resume the Router") are not false-positives.
- Scope surfaced at pre-review (§3/§4): the MCP tool `description` strings (agent-facing, read by Hermes) and `_SENSITIVE_ESCALATION_PROMPT` (user-facing) still emitted the dead slash forms, directly contradicting the charter. Rewrote those string-literals (no logic change) and updated their tests (`test_mcp_server.py`, `test_draft_reply_orchestrator.py`). Kept the `OVERRIDE_SLASH_ONE_SHOT`/`OVERRIDE_SLASH_PERSISTENT` audit-vocab enum VALUES untouched (closed-set code identifiers, not invocations — renaming is cross-cutting/out-of-scope).
- One pre-existing test broke and was corrected to the new contract: `test_spend_chart_command.py::test_skill_md_documents_render_spend_chart` asserted `"/spend" in text` — the exact dead-slash form F-10-5-1 removes; re-pointed to the plain-NL `spend month` intent.

### Completion Notes List

- **AC-1** — README slash surface removed. `## Slash commands` → `## Talking to MailBot` (two-tier: read/status free-NL table + control-verb recognized-phrase table). Rewrote write examples, Tier-3 delete example, 4 error-table fix cells (sensitivity/degraded/loop_detected/paused), the §349 override note, the §398 limitation bullet, the §401 sensitive-escalation bullet, and the §19 intro. Interim "type WITHOUT the leading `/`" note removed (superseded).
- **AC-2** — recognized-phrase dispatch contract in `hermes-config/skills/mailbot/SKILL.md` (`## Control-verb dispatch (deterministic recognized phrases)`: exact-match phrase→verb table for cancel/confirm+yes-escalate/pause/resume/use-qwen, the "never narrate a control-verb outcome without issuing the verb" prohibition, both inherited findings named) + `hermes-config/AGENTS.md` Tier-2/3 flows rewritten to plain NL with a cross-ref to the SKILL.md section.
- **AC-3** — `user_facing_guidance` (RecoveryAction / Rule S) documented as the discoverability surface in both SKILL.md and README ("to abort this, type: cancel 14").
- **AC-4** — `tests/integration/test_recognized_phrase_dispatch.py` (19 tests): README no-slash-table + plain-NL-present, SKILL.md recognized-phrase contract + prohibition + finding IDs + both inherited phrases, AGENTS.md plain-NL flows + discoverability, cross-file dead-slash sweep with token-boundary matcher.
- **AC-5** — MANDATORY-CR classified (pre-review §5.12: criteria 4 capstone + 6 load-bearing-dispatch; 5 partial privacy-adjacent). Reviewer sonnet-5 ≠ dev opus-4-8.
- **AC-6** — Adam-hands-on Task-5 Discord live walk (HYBRID RUN-MODE HALT): each recognized phrase deterministically issues its verb (cancel/pause/resume/"yes, escalate"→mint/"use qwen"→set_model_oneshot, no confabulated narration). Closes F-10-5-2-W2 + F-10-5-6-W1 end-to-end. Pending Adam-signed verdicts.
- **Gates (post-CR):** ruff clean (`--exclude scratch`), mypy --strict clean (134 files), pytest **1859 passed, 2 skipped, 3 deselected** (+25 net vs 1834 baseline — the 25-test drift gate, incl. the CR regression tests for the matcher fix). Dev-pass pre-CR was 1853+2+3 (19-test drift gate); the CR round grew it to 1859 (25-test drift gate).

### File List

- `README.md` — charter rewrite (slash table → plain-NL "Talking to MailBot"; write/error/limitation/intro rewrites).
- `hermes-config/skills/mailbot/SKILL.md` — recognized-phrase control-verb dispatch contract + prohibition; verb-block slash forms rewritten to plain NL.
- `hermes-config/AGENTS.md` — Tier-2/3 flow prose to plain NL + dispatch-section cross-ref; `/cost` informational example to plain NL.
- `mailbot_api/chat/orchestrator.py` — `_SENSITIVE_ESCALATION_PROMPT` (user-facing) + docstring to plain-NL `yes, escalate` (string-literal only).
- `mailbot_api/mcp_server.py` — MCP tool `description` strings (agent-facing) + module docstring + one inline comment to plain-NL recognized-intent phrasing (string-literal only; no logic).
- `tests/integration/test_recognized_phrase_dispatch.py` — NEW; 19-test structural drift gate (AC-4).
- `tests/integration/test_mcp_server.py` — updated description assertions to plain-NL + dead-slash-absence guard.
- `tests/integration/test_draft_reply_orchestrator.py` — updated defender-message assertion to `yes, escalate`.
- `tests/integration/test_spend_chart_command.py` — updated SKILL.md doc assertion from `/spend` to plain-NL `spend month`.
- `_bmad-output/implementation-artifacts/10-5-6-slash-to-plain-nl-charter-readme-rewrite.md` (this file) + `10-5-6.pre-review.md` — process artifacts.

### Change Log

- 2026-07-11 — Slash→plain-NL charter README rewrite + deterministic recognized-phrase control-verb dispatch contract in the Hermes persona files (hermes-config/), plus agent/user-facing MCP-description + defender-prompt de-slashing. New structural drift gate (25 tests post-CR, incl. matcher-correctness regression tests). Closes F-10-5-1 (charter); the recognized-phrase contract closes the F-10-5-6-W1 / F-10-5-2-W2 false-narration class (runtime confirmation = Task-5 Adam walk). MANDATORY-CR (sonnet-5 ≠ opus-4-8): 3-layer pass, 100% of actionable findings applied (unmute §492 dead-slash + model-verb sweep gap + matcher boundary bugs), 1 round. Gates green at 1859+2+3 (+25 net).

## Review Findings (CR round — sonnet-5, 2026-07-11)

**HIGH — `hermes-config/skills/mailbot/SKILL.md:492`** — the `unmute_category` verb's own doc section still says `Slash command: \`/unmute <category>\` (Story 6-4).` — a real, untouched dead slash-invocation form, directly contradicting AC-2's requirement that "the dead `/command` slash examples in SKILL.md ... are rewritten to the plain-NL recognized-phrase forms." This is the exact defect class the story exists to close (a persona-contract file telling the Hermes agent to expect a `/` prefix that F-10-5-1 proved never reaches MailBot). It survives because the AC-4 drift test's `_dead_slash_offenders` matcher (`tests/integration/test_recognized_phrase_dispatch.py:49-58`) uses the token `r"mute "` (with a trailing space) for its regex `(?:^|[\s`])/mute `, which requires the character immediately after `/` to be `m`, then `ute `. `/unmute <category>` has `/u`, not `/m` — so the matcher's own token-boundary logic (designed to reject `un`-prefixed false starts like "the/pause command") also accidentally rejects the true positive `/unmute`. Confirmed via direct regex reproduction: zero matches against the current SKILL.md despite the literal line 492 offender. Note `mute_category`'s section (line 334) was correctly rewritten to "Recognized intent (free-NL): `mute <category> [until]` / `unmute <category>`." — only the separate `unmute_category` section below it (§486-492) was missed. **Fix:** rewrite line 492 to a plain-NL form (e.g. "Recognized intent (free-NL): `unmute <category>` (Story 6-4)."), matching the sibling `mute_category` section's phrasing; and extend `_DEAD_SLASH_INVOCATIONS`/`_dead_slash_offenders` (or add a dedicated assertion) to also catch `/unmute` — e.g. add `r"unmute "` as its own entry (checked before or independent of `r"mute "`) so a regression here fails red instead of passing silently.

No other material issues found. The recognized-phrase contract in SKILL.md (exact-match table for cancel/confirm+yes-escalate/pause/resume/use-qwen), the explicit "never narrate without issuing the verb" prohibition, and both finding IDs (F-10-5-6-W1, F-10-5-2-W2) are present and unambiguous; AGENTS.md's Tier-2/3 flows and Rule S cross-ref are consistent with SKILL.md; the `mailbot_api/mcp_server.py` and `orchestrator.py` string-literal edits are behavior-neutral and their updated test assertions check both presence of the new phrasing and absence of the dead form (no vacuous passes); AC-1 through AC-5 are otherwise met as documented in the pre-review self-audit.

### Additional findings from the 3-layer pass (Blind Hunter / Edge Case Hunter / Acceptance Auditor)

- **HIGH — `_DEAD_SLASH_INVOCATIONS` omitted the `model` verb** (all 3 layers). The story's own headline dead form (`/model qwen`, F-10-5-6-W1 territory) was unguarded by the sweep — a reintroduced `/model qwen` invocation would pass silently.
- **CRITICAL/HIGH/MEDIUM — matcher regex had no end-boundary** (Blind + Edge Hunter). `(?:^|[\s`])/` + `verb` with trailing-space-baked-in stems produced both false NEGATIVES (`/confirm` glued to backtick/period/quote/paren escaped) and false POSITIVES (`/pauseless`, `/resumes` wrongly flagged). The matcher wasn't the token-boundary matcher its docstring claimed.
- **LOW — AC-3 `user_facing_guidance` test is marker-only** (Edge Hunter). Accepted per Dev Notes ("keep assertions marker-based and resilient to prose edits").

### Disposition (dev round 2, opus-4-8) — ALL actionable findings APPLIED

- **HIGH (unmute §492): FIXED.** `SKILL.md:492` `Slash command: /unmute <category>` → `Recognized intent (free-NL): unmute <category>`. Added `unmute` as its own matcher stem (`/unmute` has `/u`, not `/m`, so the `mute` stem could never catch it) + regression test `test_dead_slash_matcher_distinguishes_unmute_from_mute`.
- **HIGH (model verb gap): FIXED.** Added `model` to `_DEAD_SLASH_INVOCATIONS` with an explanation-only carve-out (`_EXPLANATION_ONLY_SLASH`) so the permitted "native Hermes `/model` opens its own UI" note passes while a real `/model qwen` invocation fails red. Added `model` to the parametrized persona test + `test_dead_slash_matcher_flags_reintroduced_model_invocation` + `test_readme_model_slash_is_explanation_only`.
- **CRITICAL/HIGH/MEDIUM (matcher boundaries): FIXED.** Rewrote `_dead_slash_offenders` to `(?<![\w/])/` + `re.escape(verb)` + `\b` — a real start-boundary (excludes `abort/pause` prose) AND an end word-boundary (excludes `/pauseless`; catches every trailing delimiter). Added `test_dead_slash_matcher_catches_all_trailing_delimiters` + `test_dead_slash_matcher_ignores_prose_and_stem_prefixes`.
- **LOW (marker-only AC-3 test): ACCEPT WITH RATIONALE.** Dev Notes explicitly chose marker-based assertions for prose-resilience; a content-shape assertion would be brittle against legitimate rewording. No change.

Post-fix: swept all three files with the fixed matcher (`/model` × survivors all explanatory carve-outs; `/me/messages/.../move` is a Graph path; `register_discord_commands.py` is native-registration infra) — zero real dead-slash invocations remain. Gates re-green: ruff/mypy clean, full suite 1859+2+3 (+25 net vs 1834; the drift test now carries the CR regression tests). 1 round, 100% of actionable findings applied.

## Phase 3.5 evidence — delegated verification (2026-07-11, Adam "run the manual verification yourself")

**Scope honesty (load-bearing):** AC-6 is a **live-persona-behaviour** walk. The persona is the external Hermes LLM the orchestrator cannot drive, and the failure this story closes (F-10-5-6-W1 / F-10-5-2-W2) is *the persona narrating a control action without issuing the verb* — which can ONLY be observed on a real Discord turn through the running Hermes container (and, for escalation, real Opus spend on Adam's account). The orchestrator therefore verified the **infrastructure half** ($0, direct against the live stack) and honestly leaves the **persona-dispatch half** to Adam. This is the 10-4/10-5 delegated-walk split: everything surfaceable without the persona was surfaced; the persona turn is Adam's.

**Stack:** all 3 containers up (`mailbot-hermes` 26h, `mailbot-api` 2h healthy [NOT restarted for this code — bind-mounted `mailbot_api/` + `hermes-config/` are live; the mailbot_api string edits are description/prompt text, not behaviourally load-bearing], `mailbot-ollama` 4d). Probes run in-container against `/data/mailbot.db` (production DB).

**Verified live by the orchestrator — the dispatch targets the recognized phrases hit all WORK ($0):**
- **All 5 dispatch-target verbs registered as MCP tools** in a freshly-built `build_mcp_server()` (loads this code): `cancel_action`, `pause_router`, `resume_router`, `mint_sensitivity_token`, `set_model_oneshot` — all `registered=True`, and `slash_in_desc=False` for every one (the agent-facing descriptions are de-slashed in the live-code build). 26 tools total.
- **F-10-5-6-W1 target intact:** `router/oneshot.py` arm/consume/TTL surface present (`_set_oneshot_override`, `_consume_oneshot_override`, `_DEFAULT_ONESHOT_TTL_SECONDS`) — the story never claimed oneshot was broken; the bug was the persona not calling it. Target is callable + correct.
- **F-10-5-2-W2 target present in prod DB:** `escalation_armed` singleton (10-5-2 migration 027) + `user_confirmations` tables both exist in `/data/mailbot.db` — the API-layer machinery `yes, escalate` must consume is real and in place.
- **10-5-1 pause/resume seam:** `router.py` references `is_paused_now` (DB-authoritative cross-process reader) + the resume-permitted control allowlist — so `resume` from chat while paused is reachable (F-10-5-4 close) at the code level.
- **AC-1 charter honesty (docs):** the fixed drift matcher swept README + both persona files → zero real dead-slash MailBot invocations; surviving `/model` mentions are all the permitted "native Hermes opens its own UI" explanation. Verified by the 25-test gate + a manual grep.

**REMAINS Adam-hands-on (persona-dispatch — cannot be orchestrator-verified):** each recognized phrase, typed in real Discord, must make the Hermes persona ISSUE the verb (not narrate):
1. `cancel <id>` during cooling-off → `cancel_action` fires (router_calls/action_history).
2. `pause` → gates all processes; `resume` (while paused) → `resume_router` fires from chat.
3. `yes, escalate` on a sensitive email → `mint_sensitivity_token` consumes the arm → draft dispatches (NOT the refusal template re-parroted) — small real Opus spend, Console-authoritative.
4. `use qwen` → `set_model_oneshot` issued + real ledger row + real TTL reported (NOT confabulated "armed… expires…").

**Orchestrator verdict on the delegated half: PASS** — every dispatch target the contract points at is registered, de-slashed, and functional against the live prod stack; the charter docs are honest and drift-gated. **AC-6 persona-dispatch verdicts remain Adam's** (steps 1-4 above). Environment left as found (no pause, no override armed, no spend — all probes read-only).

### AC-6 live walk EXECUTED (2026-07-11, interactive — Adam+orchestrator) → **FAIL** → Status back to `in-progress`

Full evidence: **10-5-6-walk-evidence.md**. Scorecard:

| CP | Phrase | Dispatch (10-5-6 contract) | End-to-end AC-6 | Verdict |
|----|--------|----------------------------|-----------------|---------|
| 1 | `cancel` | ✅ `cancel_action` fired, `pending_actions 39 → cancelled`, 0 Graph dispatch | ✅ | **PASS** |
| 2 | `pause`/`resume` | ✅ both fired; `pause_state` 0→1→0 with fresh 07-11 timestamps; resume-while-paused replied (F-10-5-4 closed live) | ✅ | **PASS** |
| 3 | `yes, escalate` | ✅ `mint_sensitivity_token` fired (`escalation_armed` set + `user_confirmations` id=3 minted) | ❌ token `consumed_at=NULL`, 0 `draft_reply` rows, 4× `sensitivity_gate:refused` | **FAIL** |
| 4 | `use qwen` | ❌ never reached — session bricked in CP3's refusal loop | ❌ `set_model_oneshot` never fired, 0 one_shot/qwen rows | **FAIL** |

**AC-6 = FAIL** (2/4 checkpoints incomplete end-to-end). **The 10-5-6 charter is CORRECT and CR-clean — CP1/CP2 prove the recognized-phrase dispatch layer works, and CP3 fired its verb.** The two FAILs are **upstream defects** below 10-5-6's charter:

- **F-10-5-6-W2 (HIGH) — ROOT CAUSE LOCATED at `router.py:2088-2095`.** The `chat_completions_tool_call` sensitive branch refuses unless a `confirmation_token` is passed as a **call argument**; it does NOT consult `escalation_armed` (via `consume_escalation_arm`) NOR a pre-recorded `user_confirmations` row. So `yes, escalate` arms + `mint_sensitivity_token` records a confirmation (id=3), but the actual draft DISPATCH ignores both → refuses → 0 `draft_reply` rows, `consumed_at`=NULL. The arm/mint half and the dispatch-authorization half were both built but never wired to each other on this path. **Fix locus is precise: `router.py:~2095` must consult the arm / recorded confirmation before refusing** (mirror what `mint_sensitivity_token` already does). Compounded by F-10-5-11 (persona hand-writes drafts in haiku — CP1). **Blocks 10-5-2 AC-4 + 10-5-6 AC-6 CP3.**
- **F-10-5-6-W3 (HIGH) — same root cause as W2.** Because the dispatch refuses (W2), it re-writes `pending_sensitive_refusal` every turn; that row is keyed on the shared `unknown-external` caller_origin (10-5-2 CR-8), so it short-circuits EVERY later turn — `use qwen` (CP4) never reaches the recognized-phrase layer (F-10-5-7 session-brick resurfacing). Fixing W2 (so the arm unlocks the dispatch instead of refusing) stops the `pending_sensitive_refusal` accumulation that bricks the session. **CP4 deep-dive proved `set_model_oneshot` itself works (real 5-min TTL, direct call) — CP4's FAIL was collateral, not intrinsic.**
- **F-10-5-6-W4 (MEDIUM)** — grant-mint `expires_at` clock-skew loop on CP1 `send` (~6× retries, ~$0.05 haiku) then false "Reply sent." narration; grant never minted. Tier-2/3 grant path, not a 10-5-6 control verb.

**Remaining work to close 10-5-6 (Adam decides next session whether it lands here or in a new story):** fix the mint→consume→draft chain (F-10-5-6-W2) + the session-brick refusal loop (F-10-5-6-W3). The README + persona contract + drift test (Tasks 1-4) stay as shipped — they are not the defect. Environment left as found: `escalation_armed` self-expires ~10min; not paused/degraded; action 39 cancelled.

### UPDATE 2026-07-11 — W2 + W3 FIXED, code + live verified (Adam-directed dev pass)

**F-10-5-6-W2 + W3 CLOSED.** Fix: `mailbot_api/router/router.py` sensitive `chat_completions_tool_call` branch now calls the new `authorize_sensitive_dispatch(email_id, task_type)` (in `mailbot_api/actions/user_confirmation.py`) before refusing — the same user-gated escalation primitive `mint_sensitivity_token` uses, applied at the DISPATCH seam. It records a TTL-windowed, re-readable `escalation_dispatch` grant scoped to `(email, task)` (migration `028_user_confirmations_escalation_dispatch_scope.sql` widens the `user_confirmations.scope` CHECK) so ONE `yes, escalate` authorizes the whole multi-dispatch escalation turn, while a DIFFERENT email still refuses (blast-radius preserved). Three live Discord walks show a monotonic path to a clean state: original **bricked** → round-1 fix **worked but re-refused mid-flow** → refined **1× `yes, escalate` covered the turn, 0 standing pending refusal, session clean**. $0 live proofs + migration-028 dry-run-on-prod-copy in `10-5-6-walk-evidence.md`. Gates: ruff/mypy clean, suite **1864+2+3** (+5 net vs 1859). **F-10-5-11 (persona hand-writes drafts in haiku, no Opus `draft_reply` dispatch) PERSISTS — separate, story-sized defect, not this fix's scope.**

**Added File List (this dev pass):**
- `mailbot_api/router/router.py` — dispatch-seam escalation authorization (W2/W3 fix).
- `mailbot_api/actions/user_confirmation.py` — new `authorize_sensitive_dispatch` helper (+ `__all__`).
- `mailbot_api/db/queries.py` — `USER_CONFIRMATION_FIND_ESCALATION_DISPATCH`.
- `mailbot_api/db/migrations/028_user_confirmations_escalation_dispatch_scope.sql` — NEW; widens scope CHECK (table rebuild, data + indexes preserved; applied live).
- `tests/integration/test_dispatch_tool_call_sensitivity_gate_f28.py` — +5 dispatch-seam escalation tests (arm/confirmation authorize; multi-dispatch same-email; different-email refuses; no-auth still refuses).

## MANDATORY-CR — W2/W3 escalation-dispatch fix (sonnet-5, 2026-07-11)

Scope: security-adjacent review of the W2/W3 fix touching the NFR-PRIV-1 sensitivity gate — `mailbot_api/router/router.py` (~line 2095), `mailbot_api/actions/user_confirmation.py` (`authorize_sensitive_dispatch`), `mailbot_api/db/queries.py` (`USER_CONFIRMATION_FIND_ESCALATION_DISPATCH`), `mailbot_api/db/migrations/028_user_confirmations_escalation_dispatch_scope.sql`, and `tests/integration/test_dispatch_tool_call_sensitivity_gate_f28.py`. Reviewed inline (Read/Grep + two throwaway sqlite3 repros against migration 028 and `PRAGMA foreign_keys` semantics); no sub-agents spawned.

**Findings**

1. **LOW — `mailbot_api/router/router.py:2124-2150`** — `authorize_sensitive_dispatch(...)` is called with no `try/except`, unlike its sibling token-consume path three branches below (`router.py:2205-2225`, which wraps `_consume_token` in a defensive `except Exception` specifically to avoid leaking a token value into a traceback and to convert a DB crash into a clean refusal). A DB error inside `authorize_sensitive_dispatch` (e.g. a transient `sqlite3.OperationalError` from `execute_write`'s `BEGIN IMMEDIATE` hitting `busy_timeout`) propagates as an unhandled exception out of `dispatch_tool_call` instead of degrading to the existing "sensitive email requires confirmation" refusal. Failure mode is fail-closed (crash, not a silent bypass), so this is not a privacy defect, just an inconsistency with the established defensive pattern next to it and a worse operator experience (500 instead of a clean refusal envelope) under DB contention. Suggested fix: wrap the `authorize_sensitive_dispatch` call in the same style of `try/except Exception as exc: ... _authorized = False` used for the token-consume branch, logging `exception_type` only.

2. **LOW — `mailbot_api/db/migrations/028_user_confirmations_escalation_dispatch_scope.sql:19,49`** — `PRAGMA foreign_keys = OFF` / `= ON` are no-ops here: SQLite silently ignores `PRAGMA foreign_keys` writes while a transaction is open, and the migration runner (`mailbot_api/db/migrations_runner.py:126-132`) wraps every migration body in an outer `BEGIN; ... COMMIT;` via `executescript`, so the pragma toggle inside the body never takes effect during the table rebuild. Confirmed empirically: a `PRAGMA foreign_keys=OFF` issued inside an open transaction does not suppress FK enforcement for statements later in that same transaction (verified with a throwaway sqlite3 repro — an FK-violating INSERT still raised `IntegrityError` after the mid-transaction `OFF` pragma). In this specific migration it is harmless because `user_confirmations` has no `REFERENCES` clauses and nothing else references it (confirmed via grep across `mailbot_api/db/migrations/*.sql`), so there is no real FK to suppress — the rebuild (create new → copy → drop → rename → recreate 2 indexes) was verified end-to-end against a fresh DB built through `apply_pending_migrations`: all 8 columns preserved, both indexes (`ix_user_confirmations_sensitivity`, `ix_user_confirmations_grant`) recreated identically to migration 026, and the widened `CHECK(scope IN ('sensitivity_token','grant','escalation_dispatch'))` correctly accepts `'escalation_dispatch'` and still rejects a bogus scope value. Flagging only because the comment/pragma implies FK-suppression is doing real work when it is dead code in the runner's transaction model — a future migration that actually needs mid-rebuild FK suppression (e.g. a table WITH real FK references) would hit this same no-op silently and NOT get the protection its author expects. Suggested fix: either drop the pragma pair (dead code) or note in the runner/migration-authoring docs that `PRAGMA foreign_keys` toggles are transaction-scoped and cannot be used mid-migration-body — a real fix for a future FK-bearing rebuild would need the pragma issued on a separate, non-transactional connection before the migration transaction begins.

3. **LOW — `mailbot_api/db/migrations/028_user_confirmations_escalation_dispatch_scope.sql` / `mailbot_api/actions/user_confirmation.py:373-388`** — `escalation_dispatch` grant rows are never consumed (`consumed_at` stays `NULL` forever by design, since they're peeked not consumed) and there is no cleanup/expiry sweep, so they accumulate one row per first-authorization-in-a-TTL-window, unboundedly, for the life of the database. Not a security hole (expired grants are correctly excluded by the code-side TTL check at read time — `_parse_iso(grant_created_at) + CONFIRMATION_TTL > _utc_now()` — regardless of how many stale rows exist), and the `ix_user_confirmations_sensitivity (scope, email_id, task_type)` index keeps the `WHERE scope=... AND email_id=... AND task_type=... ORDER BY id DESC LIMIT 1` lookup cheap even as the table grows. Pure storage growth, same class as the pre-existing `sensitivity_token`/`grant` scopes (which are consumed but not deleted either — `USER_CONFIRMATION_CONSUME` sets `consumed_at`, doesn't `DELETE`). No fix required; noting for completeness since the review brief asked about accumulation.

**Clean on the axes that matter most:**

- **Privacy invariant (highest priority): CLEAN.** Traced both value sources `authorize_sensitive_dispatch` can consume: `consume_sensitivity_confirmation` (reads `user_confirmations` scope=`sensitivity_token`, written only by `record_sensitivity_confirmation`, called only from `confirm_pending_escalation`, called only from `mailbot_api/main.py:588` gated on `_is_escalation_confirmation(_latest_user_text)` where `_latest_user_text` is filtered to `m.role == "user"`) and `consume_escalation_arm` (reads `escalation_armed`, written only by `arm_escalation`, called only from `mailbot_api/main.py:589`, same user-role gate). `is_escalation_confirmation` is a deterministic exact-phrase match (`_ESCALATE_PHRASES`), not LLM interpretation. Grepped the full MCP verb surface (`mailbot_api/mcp_server.py` tool wrappers) — `arm_escalation`, `record_sensitivity_confirmation`, and `authorize_sensitive_dispatch` itself are not registered as or reachable from any MCP tool; the only caller of `authorize_sensitive_dispatch` in the whole tree is the router seam under review. No path exists for the agent verb surface to self-authorize. Confidential is refused unconditionally at `router.py:2051-2087`, strictly ABOVE the sensitive branch (`router.py:2088+`) inside the same per-`eid` loop iteration, so a confidential email returns before ever reaching the new escalation-authorize code — confirmed by reading the branch ordering directly, not inferred.
- **TTL / grant reuse: CLEAN.** The `> _utc_now()` peek check at `user_confirmation.py:358` is the correct polarity (live iff created_at + TTL is still in the future), consistent with the negated `<=` "expired" check used at the other 4 TTL sites in the same file (sensitivity confirmation consume, grant confirmation consume, escalation-arm consume, pending-escalation claim). 10 minutes matches the pre-existing `CONFIRMATION_TTL` used for the sensitivity-token and arm paths — not a new/wider window introduced by this fix. No test exercises actual wall-clock expiry of the new `escalation_dispatch` grant (only same-window reuse and cross-email exclusion are tested) — a freeze-time test for "grant recorded at T, dispatch attempted at T+11min re-refuses" would be a nice-to-have coverage gap, not a defect (the code path is identical to the already-tested-elsewhere `_parse_iso(...) + CONFIRMATION_TTL` pattern).
- **Blast radius: CLEAN, verified beyond the test.** `USER_CONFIRMATION_FIND_ESCALATION_DISPATCH` (`db/queries.py:873-878`) filters `WHERE scope = 'escalation_dispatch' AND email_id = ? AND task_type = ?` — exact match on both columns, no wildcard/prefix matching, `ORDER BY id DESC LIMIT 1` so a fresh grant always wins over a stale one for the same key. Confirmed the existing `test_dispatch_tool_call_arm_does_not_authorize_different_email` test's premise holds at the SQL level, not just by trusting the assertion.
- **Migration 028 safety: CLEAN** apart from finding 2 above (dead pragma). Verified live: ran `apply_pending_migrations` against a fresh temp DB through all 28 migrations, diffed `PRAGMA table_info` (all 8 columns present, correct types/nullability) and `sqlite_master` index SQL against migration 026's originals (byte-identical index definitions) — no data-loss or index-drop risk for existing rows, since this environment has no rows to lose in the rebuild target's referential graph anyway (finding 2 covers why FK safety specifically is moot here).
- **Router integration / magic grant_id string: ACCEPTABLE, flagged for awareness only (no fix needed).** `_sensitivity_grant_id = "escalation-confirmed"` (`router.py:2136`) writes into `router_calls.sensitivity_grant_id`, a plain `TEXT NULL` column (`db/migrations/006_router_calls.sql:44`) with no format constraint — confirmed no CHECK, FK, or downstream parser expects the token-path's `sha256(token)[:16]` hex shape (`mailbot_api/actions/sensitivity_tokens.py:65-86`); grepped all `sensitivity_grant_id` references across the tree and found only forwarding (escalation-hop audit linkage at `router.py:1157-1158`) and column projection (`observability/audit.py`), never a format check. The one real consequence: every escalation-authorized dispatch across all emails/tasks shares the identical literal `"escalation-confirmed"` grant_id, so a forensic query that assumes grant_id uniquely identifies one mint (as it does for the sha256 token path) would see them all collapse into one indistinguishable bucket — a minor observability/forensics limitation, not a security gap (the real per-dispatch distinguishing keys — `email_id`, `task_type`, `caller_origin`, `router_calls.id`, `sensitivity_grant_minted_at` timestamp — are still recorded per-row). `_consumed_for_eid = eid` + `continue` correctly mirrors the valid-token path's bookkeeping (same variables, same loop-continuation semantics, confirmed by reading both branches side by side).
- **Concurrency: CLEAN.** Every `fetchone`/`execute_write` call opens its own short-lived connection with its own `BEGIN IMMEDIATE ... COMMIT` (`db/connection.py:72-87`), so the peek (step 1) and the eventual grant INSERT (end of `authorize_sensitive_dispatch`) are two separate transactions — a real TOCTOU window exists between them, but it is not exploitable into a double-authorization: the only way to reach the INSERT is by first winning a genuinely single-use atomic consume (`consume_sensitivity_confirmation`'s `UPDATE ... WHERE id = ? AND consumed_at IS NULL` / `consume_escalation_arm`'s `DELETE ... RETURNING`), both of which are race-safe by construction (only one concurrent caller can ever observe a non-empty result). Two concurrent dispatches for the same (email, task) with no live grant yet: at most one wins the consume and proceeds to INSERT the grant; the loser gets `authorized=False` and correctly refuses. Repeated same-window calls after the grant exists take the peek-only path (step 1) and never re-consume or re-INSERT, so no duplicate-grant-row pathway exists from legitimate reuse either.

**AC-conformance / no-regression: CLEAN.** Read `router.py:2051-2200` end-to-end: confidential-unconditional-refuse, valid-inline-token consume, normal-email passthrough (untouched code paths, outside the `if confirmation_token is None or _consumed_for_eid is not None:` branch this fix modifies), and no-email passthrough are all structurally unchanged by this diff — the fix only adds a new `if _authorized: ... continue` fast-path inside the pre-existing "would otherwise refuse" branch, guarded by `_consumed_for_eid is None` so it cannot override the existing first-id-wins multi-id token semantics. New tests (`test_dispatch_tool_call_allows_sensitive_when_escalation_armed`, `..._when_confirmation_recorded`, `..._arm_authorizes_repeat_same_email_within_ttl`, `..._arm_does_not_authorize_different_email`, `..._still_refuses_sensitive_with_no_authorization`) cover both authorization sources, multi-dispatch reuse, cross-email exclusion, and the negative (no-auth-at-all) case; ran a mental trace against each and the assertions match the code's actual behavior rather than testing a mocked substitute.

**Summary:** No CRITICAL, HIGH, or MEDIUM findings. 3 LOW findings, none privacy-invariant-breaking: (1) missing defensive try/except around the new authorize call (robustness/consistency, fail-closed), (2) a dead-code `PRAGMA foreign_keys` toggle in migration 028 that is harmless for this specific table but could mislead a future FK-bearing rebuild, (3) unbounded (but harmless, TTL-gated-at-read) accumulation of `escalation_dispatch` rows. The core privacy seam — agent cannot self-authorize, confidential is unconditionally refused above this branch, authorization is exact-scoped to (email_id, task_type), and the peek/consume split cannot be raced into a double-authorization — holds up under adversarial tracing back to first principles (chat-boundary user-role gate → MCP verb surface grep → SQL scoping → transaction semantics), not just by trusting the new tests' assertions.

### Disposition (dev, opus-4-8, 2026-07-11) — 2 APPLIED, 1 ACCEPT-WITH-RATIONALE

- **LOW-1 (missing try/except): FIXED.** `router.py:~2128` — wrapped `authorize_sensitive_dispatch` in `try/except Exception → _authorized=False` mirroring the token-consume path's defensive style (logs `exception_type` only, degrades to the existing fail-closed sensitivity refusal instead of a 500). CR-10-5-6-1.
- **LOW-2 (dead PRAGMA in migration 028): FIXED.** Removed the inert `PRAGMA foreign_keys = OFF/ON` pair (no-op inside the runner's `BEGIN;…COMMIT;` wrapper) and replaced with an accurate FK note explaining why + what a future FK-bearing rebuild must do instead. Verified: edited 028 still applies cleanly on a fresh DB (8 cols, both indexes, `escalation_dispatch` accepted, bogus scope rejected). The already-applied live DB is unaffected (pragma was inert; runner is filename-keyed, no content hash). CR-10-5-6-2.
- **LOW-3 (unbounded escalation_dispatch rows): ACCEPT WITH RATIONALE.** TTL-gated at read (stale rows never authorize), indexed lookup stays cheap, same non-deletion class as the pre-existing `sensitivity_token`/`grant` scopes. Reviewer explicitly said no fix required. A periodic cleanup sweep is a future ops nicety, not a defect — filed mentally to Cluster G if it ever matters.

Post-disposition gates: ruff/mypy clean, suite re-run green (see sprint-status). The router.py robustness fix requires a mailbot-api restart to go live (applied + verified).

**MANDATORY-CR verdict: PASS** (reviewer sonnet-5 ≠ dev opus-4-8; §5.12 crit 4+6; 0 CRITICAL/HIGH/MEDIUM; 2/2 actionable LOWs applied, 1 accepted). Privacy seam adversarially cleared.
