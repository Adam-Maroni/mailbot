---
baseline_commit: 18ea6d4
---

# Story 10.6.2 (AI-2): Draft-pipeline reachability — the persona reaches the real Opus draft path from chat

Status: done  (dev pass + MANDATORY-CR complete 2026-07-13; done at L1/L2 [code-complete + self-verified via gates]. AC-1/AC-5 live Opus draft walk = L3, Adam-hands-on Phase 3.5 + done-flip clause 4.)
Epic: 10.6 (Capability Reachability) — sprint-status key `10-6-2-draft-pipeline-reachability-from-chat`

**F-10-5-11 (HIGH), filed forward across Epic 10.5.** The flagship capability — MailBot drafts a reply in Adam's voice via the Opus pipeline — is built, tested, and (as of Story 10-5-3) registered as an MCP tool, yet the live persona STILL does not reach it: it hand-writes drafts in haiku instead. This story closes the reachability gap so a real Discord "draft a reply" turn produces an actual Opus `draft_reply` `router_calls` row.

## Story

As Adam,
I want the persona to dispatch the real Opus `draft_reply` pipeline when I ask it to draft a reply from chat — not improvise a draft in haiku,
So that "MailBot drafts replies in my voice" stops being an L2-green illusion and becomes a thing that actually happens (with the quality the Opus pipeline was built for), and the charter's flagship promise is true on the live product.

## Background & Findings

**F-10-5-11 HIGH — draft-pipeline reachability from chat.** The Opus draft pipeline (`handle_draft_reply` in `mailbot_api/chat/orchestrator.py`: `tone_style_mirror` → Opus `draft_reply` → `accept_draft`, Opus-bound per FR-4.4) is fully built and unit/integration tested. Story 10-5-3 registered `draft_reply` as an MCP tool and proved it via a fake-adapter integration test (a real `router_calls` row through the wrapper). **But across all three Epic 10.5-6 live Discord walks, 0 Opus `draft_reply` rows were ever created** — the persona says *"the Router's draft_reply task isn't directly exposed via MCP"* and improvises the draft in haiku instead (10-5-6-walk-evidence.md §RESIDUAL, CP3: "draft_reply rows created: 0 — the Opus draft pipeline NEVER dispatched").

**The class:** identical to AI-1's Phase-2 finding and the retro's central lesson — *"wired + capable + registered + tested" ≠ "the persona reaches it on a real turn."* The tool exists; the persona doesn't call it. This is a persona/dispatch-contract gap (Hermes-side), the F-10-5-1/F-10-5-10 self-narration class — the persona narrates/improvises a capability instead of issuing the verb that invokes it.

## Acceptance Criteria

**AC-1.** A real Discord "draft a reply to <email>" turn produces an Opus `draft_reply` `router_calls` row — proven by DB ground truth: `task_type` reflecting the draft pipeline, `model_chosen=claude-opus-*` (not haiku), from a `caller_origin` traceable to the chat turn. The persona no longer hand-writes the draft in haiku.

**AC-2.** The persona/dispatch contract makes `draft_reply` reachable deterministically from chat — the persona issues the registered `draft_reply` MCP tool when the user asks for a draft, rather than narrating that it "isn't exposed." (Likely a hermes-config persona-contract change + verifying the MCP tool description/discoverability, in the same family as the F-10-5-6 recognized-phrase dispatch and 10-5-3's tool registration.)

**AC-3.** Privacy invariant preserved: drafting on a sensitive/confidential email still respects the sensitivity gate (the draft pipeline's existing sensitivity handling is not bypassed by the new reach). Verify no regression to the FR-2.3/F28 gate.

**AC-4.** MANDATORY-CR (reviewer ≠ dev model, [[feedback_reviewer_model_substitution]]) — the dispatch/persona seam is load-bearing (charter-flagship capability). If the fix is hermes-config-only (persona contract, no `mailbot_api` code), apply the §5.12 CR cadence appropriate to a contract-surface change, matching how 10-5-6 handled the recognized-phrase dispatch.

**AC-5.** Live Discord L3 walk: Adam asks for a draft in chat; the reply is produced by the real Opus pipeline (verified in DB + the draft quality), small real Opus spend, Console-authoritative per [[feedback_anthropic_spend_source_of_truth]].

## Tasks

1. [~] Reproduce F-10-5-11 live: confirm current behavior (persona improvises in haiku; 0 Opus `draft_reply` rows on a chat draft request) against the running stack. — **DEFERRED to Phase 3.5 (Adam-hands-on).** Not dev-codeable; the reproduction is a live Discord turn. The finding is already documented across three prior walks (10-5-6-walk-evidence.md §RESIDUAL). See Completion Notes.
2. [x] Diagnose the reach gap. — **Done via code inspection.** `draft_reply` IS exposed as an MCP tool: registered in `mailbot_api/mcp_server.py` (Story 10.5.3, tool count 26), with an accurate description (`_TOOL_DESCRIPTIONS["draft_reply"]`), wrapping the complete Opus-bound `handle_draft_reply` orchestrator (`mailbot_api/chat/orchestrator.py`, `task_type="draft_reply"` per FR-4.4). **The gap is NOT missing exposure — it is the persona contract.** The old SKILL.md `draft_reply` section described the verb but never instructed "you MUST issue it on a draft request," and Turn structure 2 framed the draft step as `ask_router(task_type="draft_reply")` (the router-internal name), which the persona conflated with the "ask_router is intentionally NOT MCP-exposed" note → hence the false "isn't directly exposed via MCP" narration + haiku improvisation.
3. [x] Fix the reachability (Hermes-side persona-contract change; NO `mailbot_api` change — boundary honest). — `hermes-config/skills/mailbot/SKILL.md`: added a **Reach contract** to the `draft_reply` verb section (MUST-dispatch verb; explicit prohibition on hand-writing/improvising the draft and on the "isn't exposed" false narration, naming F-10-5-11 in the F-10-5-6 false-narration family); rewrote Turn structure 2 step 5 to **dispatch the `draft_reply` MCP verb** (not the ask_router framing) with the confirmation-token wiring preserved; re-aligned the Turn-structure-2 "Banned" note to the verb-dispatch framing while keeping the sensitivity-gate ban (AC-3 no-regression). Structural drift test added: `tests/integration/test_draft_reply_reach_contract.py` (same offline posture as 10-5-6's `test_recognized_phrase_dispatch.py`).
4. [x] MANDATORY-CR (reviewer ≠ dev) — **COMPLETE.** Reviewer=claude-sonnet-5, dev=claude-opus-4-8 (satisfies [[feedback_reviewer_model_substitution]]). 11 adversarial findings; 6 applied, 5 skipped-with-rationale. See § Review Findings.
5. [~] Live Discord L3 walk (AC-1/AC-5) — Adam-hands-on, small real Opus spend. **DEFERRED to Phase 3.5.** Precondition: Graph-auth drain works (10-6-0 done) and MCP session is live (restart hermes after any api restart).

## Risks / Notes

- **Depends on the same live-infra health as AI-1's walk:** the Graph 401 at drain (see AI-1 story Risks) and the Hermes MCP session-drop (F-10-5-1-W2) both affect any live draft walk. Draft itself may not hit the drain path (drafting ≠ sending), but a send-the-draft follow-through would.
- **Boundary honesty:** 10-5-3 established that the draft tool IS registered; the residual is persona-reach, which is Hermes-side. Expect the fix to live in `hermes-config/` (persona contract), not `mailbot_api` — same pattern as 10-5-6's charter/dispatch work. Confirm before writing code.
- Real Opus spend on the verification walk — pre-flight estimate + Console truth, never local placeholder.

## Relationship

Sibling to [ai-1-local-tool-caller-and-chat-path-reachability.md](ai-1-local-tool-caller-and-chat-path-reachability.md) — both are the "capability wired but persona/policy doesn't reach it" class (AI-1 = local qwen tool-calls routed to haiku; AI-2 = Opus draft pipeline not dispatched by the persona). Both are the reachability last-mile that must close before Epic 7 calibrates a perimeter these capabilities live behind. Kept as separate stories per Adam D2 (distinct seams: AI-1 = router/policy + adapter; AI-2 = persona draft-dispatch contract).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (autonomous-story-run dev pass, 2026-07-13)

### Debug Log

- **Boundary confirmed by code, not assumed.** Verified `draft_reply` is genuinely MCP-registered (`mailbot_api/mcp_server.py:743` wrapper + `_TOOL_DESCRIPTIONS["draft_reply"]` + `_EXPECTED_TOOL_COUNT = 26`) and that `handle_draft_reply` (`mailbot_api/chat/orchestrator.py:144`) is the complete Opus-bound pipeline (sensitivity gate → optional tone_style_mirror → `task_type="draft_reply"` → accept_draft). So the reach gap is 100% persona-side; no `mailbot_api` change was warranted or made. Same boundary-honest discipline as Epic 10.5.
- **Root cause of the false "isn't exposed" narration.** SKILL.md's Turn structure 2 step 5 said *"Call the Router with `task_type="draft_reply"`"* — the router-internal name — while the same file's "Router-internal — `ask_router` is intentionally NOT MCP-exposed" section warns the agent NOT to call ask_router as a tool. A persona reading both conflates them and concludes the draft path is unreachable, then improvises. The fix removes the ambiguity: the draft step now says **dispatch the `draft_reply` MCP verb** explicitly, and the verb section carries a MUST-dispatch + no-improvise contract that names F-10-5-11.
- **AC-3 no-regression via structural anchors.** Two of the six drift tests (sensitivity-gate + AGENTS.md Rule N Opus note) passed on the FIRST (RED) run — they assert the pre-existing gate description survives the edit, which it does. The reach edits did not touch the confidential-refused / needs-sensitivity-token / confirmation_token contract.

### Completion Notes List

- **AC-2 (dev-codeable, DONE):** persona/dispatch contract now makes `draft_reply` reachable deterministically from chat — SKILL.md instructs the persona to issue the registered `draft_reply` MCP verb on a draft request and explicitly forbids hand-writing the draft or narrating "isn't exposed" (F-10-5-11, tied into the F-10-5-6 false-narration family). Turn structure 2 rewritten to dispatch the MCP verb.
- **AC-3 (dev-codeable, DONE):** privacy invariant preserved — the draft-reach contract keeps the sensitivity gate (confidential refused; sensitive requires `mint_sensitivity_token` → `confirmation_token`). Asserted by `test_skill_md_draft_reach_preserves_sensitivity_gate` + full suite green (no FR-2.3/F28 regression; `test_dispatch_tool_call_sensitivity_gate_f28.py` + `test_draft_reply_orchestrator.py` still pass).
- **AC-4 (MANDATORY-CR):** pending — reviewer ≠ dev (sonnet-5 ≠ opus-4-8), autonomous-story-run Step 2.4. Contract-surface change, so §5.12 CR cadence matching how 10-5-6 handled the recognized-phrase dispatch.
- **AC-1 + AC-5 (live Opus walk):** DEFERRED to Phase 3.5, Adam-hands-on — a real Discord "draft a reply" turn producing an Opus `draft_reply` `router_calls` row (`model_chosen=claude-opus-*`) + small real Opus spend, Console-authoritative. Not dev-codeable; the runtime proof is the walk (the drift test is the structural backstop, not a substitute for the walk — same posture as 10-5-6).
- Gates: ruff clean (changed files), mypy clean (new test file; no `mailbot_api` source touched so mypy-strict surface unchanged), full suite **1911 passed** + 3 skipped + 3 deselected (+6 net vs the 10-6-1 baseline of 1905).

### File List

- `hermes-config/skills/mailbot/SKILL.md` (modified) — `draft_reply` verb section Reach contract + Turn structure 2 verb-dispatch rewrite + Banned-note re-alignment.
- `tests/integration/test_draft_reply_reach_contract.py` (new) — 6 offline structural drift tests for the draft-reach contract (AC-2/AC-3).
- `_bmad-output/implementation-artifacts/ai-2-draft-pipeline-reachability-from-chat.md` (modified) — this story file (status flips, task dispositions, Dev Agent Record).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified) — 10-6-2 row status transitions.

Note: `AGENTS.md` was NOT modified — its Rule N "draft_reply routes to Opus per FR-4.4" note already anchors the "a draft is not a cheap inline improvisation" invariant (asserted, passed on first run). Adding redundant prose there would be churn.

### Change Log

- 2026-07-13 — Closed the persona-reach half of F-10-5-11: SKILL.md now mandates dispatching the registered `draft_reply` MCP verb on a draft request (MUST-dispatch + no-improvise + no-"isn't-exposed" contract), Turn structure 2 rewritten to the MCP-verb framing, sensitivity gate preserved. New drift test locks the contract. Hermes-side only; no `mailbot_api` change. Live Opus walk (AC-1/AC-5) deferred to Phase 3.5.
- 2026-07-13 — MANDATORY-CR applied: 6 of 11 findings fixed in SKILL.md (inline-variant reconciliation, router_error escape hatch, source-of-ambiguity disambiguation at the `ask_router` note, tightened sensitive-token phrasing, de-duplicated the triple prohibition to a single source of truth + cross-refs, action-oriented step-4 rewrite). See § Review Findings.

## Review Findings — MANDATORY-CR (2026-07-13)

**Reviewer:** claude-sonnet-5 (≠ dev claude-opus-4-8, per [[feedback_reviewer_model_substitution]]). Adversarial single-pass review of the SKILL.md diff + new drift test. 11 findings; 6 applied, 5 skipped-with-rationale. All fixes re-verified: 56 persona/drift/coverage tests green.

| # | Finding | Disposition |
|---|---------|-------------|
| 1 | "Inline-drafting variant — F28 awareness" section (left untouched) blesses inline drafting one paragraph below the new "never hand-write" ban — unreconciled contradiction. | **FIXED** — added carve-out #2 to the Prohibition block: the F28 inline-variant section is a *sensitivity-gate backstop note*, NOT a license to skip the pipeline. The pipeline is always the intended path. |
| 2 | Prohibition is a Markdown instruction with no code-level enforcement — "load-bearing" is aspirational. | **FIXED (light)** — added a Runtime note making the layering explicit: persona-level contract + router sensitivity gate (code backstop) + drift test (regression gate) + Phase 3.5 walk (L3 proof). This IS the persona-reach class; no code gate is possible by construction (boundary-honest). |
| 3 | "MUST dispatch the verb" has no sanctioned escape hatch if `draft_reply` returns `router_error`/is unreachable — traps the agent. | **FIXED** — carve-out #1: verb failure is NOT hand-writing; surface the error, do not improvise a substitute. Also added to Turn structure 2 step 5. |
| 4 | Step 4's "tone handled INSIDE the pipeline" + `tone_signals_blob` asserted without in-diff evidence. | **SKIPPED (verified correct)** — confirmed against `mailbot_api/chat/orchestrator.py:187-244` (pipeline dispatches `tone_style_mirror` then `draft_reply`) + the mcp_server `draft_reply` wrapper signature (`tone_signals_blob: str \| None`). Persona docs legitimately describe pipeline behavior; the assertion is true. |
| 5 | Same "don't hand-write / don't say unexposed" rule stated 3× (Reach contract + Prohibition + Banned note) → maintenance-drift risk. | **FIXED** — collapsed the Banned-note restatement into a cross-reference naming the Reach contract as "the single source of truth for this rule." |
| 6 | "the single reachable chat call site" absolute claim asserted without in-diff proof. | **SKIPPED (accurate)** — SKILL.md's own "Router-internal — ask_router NOT MCP-exposed" section establishes the single-entry-path invariant (Epic 2's cost-discipline center); the MCP `draft_reply` verb is the one tool call site. Softened "single" → "reachable" in step 5 to reduce absolutism without losing the point. |
| 7 | "(token if minted in step 3)" is soft/optional phrasing inside a MUST-toned instruction. | **FIXED** — step 5 now states the token is REQUIRED for sensitive (pipeline refuses at `needs_sensitivity_token` without it), omitted for normal — not "pass if you happen to have it." |
| 8 | Change blames the reader ("exactly the F-10-5-11 trap") but leaves the *root* ambiguity (the `ask_router` router-internal note) unpatched at its source. | **FIXED** — added a Disambiguation note to the "Router-internal — ask_router NOT MCP-exposed" section itself: `ask_router` (internal dispatcher) ≠ `draft_reply` (MCP verb); the pipeline uses ask_router internally but you never touch it. Kills the conflation at its source, not just at the one call site. |
| 9 | Step 4 "you do not dispatch X" is explanatory prose masquerading as a procedural step in a numbered "Steps:" list. | **FIXED (light)** — reworded step 4 to be action-oriented ("Do NOT dispatch tone_style_mirror separately … only if you already fetched signals, pass them forward in step 5"). |
| 10 | F-finding taxonomy (F-10-5-6/W1, F-10-5-2-W2 as "the false-narration class") asserted without in-diff definitions. | **SKIPPED (taxonomy correct)** — verified against SOUL.md + SKILL.md's existing Control-verb dispatch section which already establishes the F-10-5-6 false-narration family. Cross-referencing prior findings is the established persona-doc convention in this repo. |
| 11 | Drift tests are string/regex matches over prose — gameable by cosmetic rewording that preserves matched substrings while gutting intent; no proof the LLM obeys at runtime. | **SKIPPED (accepted, intentional)** — this is the explicit, documented posture of the 10-5-6 drift-test family (see the new test file's module docstring + 10-5-6's `test_recognized_phrase_dispatch.py`): the drift test is a *regression gate*, not a *behavioral proof*. The behavioral proof is the Phase 3.5 live walk (AC-1/AC-5). Acknowledged in-file, not a defect to fix. |

## Completion Notes

### 2026-07-13 — autonomous-story-run dev pass + MANDATORY-CR (truncated from sprint-status per §2.4.8)

**DEV PASS complete** (autonomous-story-run; dev=opus-4-8, review=sonnet-5). Hermes-side persona-contract fix ONLY — boundary-honest: the `draft_reply` MCP tool (`mailbot_api/mcp_server.py`, tool count 26) + the `handle_draft_reply` Opus pipeline (`mailbot_api/chat/orchestrator.py`) were already built + registered by Story 10.5.3; **no `mailbot_api` change was warranted or made.** The residual F-10-5-11 gap was 100% persona-reach.

**What shipped:** `hermes-config/skills/mailbot/SKILL.md` — the `draft_reply` verb section now carries a **Reach contract** (MUST-dispatch the registered MCP verb on a draft request; explicit prohibition on hand-writing/improvising the draft and on the false "isn't directly exposed via MCP" narration, naming F-10-5-11 in the F-10-5-6 false-narration family), Turn structure 2 rewritten to dispatch the `draft_reply` MCP verb (not the `ask_router` framing that fed the conflation), the sensitivity gate preserved (AC-3), plus a Disambiguation note added to the "Router-internal — ask_router NOT MCP-exposed" section that kills the ask_router↔draft_reply conflation at its source. New offline structural drift test `tests/integration/test_draft_reply_reach_contract.py` (6 tests) red-gates a regression of this contract.

**MANDATORY-CR** sonnet-5 ≠ opus-4-8: 11 adversarial findings → 6 FIXED (100% of the actionable/valid ones) + 5 SKIPPED-with-rationale (verified-correct or intentional-posture). Round-2 focused verify: all 4 load-bearing points HOLD (inline-variant contradiction resolved; AC-3 gate unweakened; ask_router non-exposure contract intact; no new contradiction from de-duplication). See § Review Findings.

**Gates:** ruff clean (changed files), mypy clean (new test; no `mailbot_api` source touched → mypy-strict surface unchanged), full suite **1911 passed** + 3 skipped + 3 deselected (+6 net vs the 10-6-1 baseline of 1905). §2.4.7 middleware-real-bootstrap = N/A (zero `mailbot_api/` verb/endpoint/DB-write/drainer touched; markdown+test-only).

**Done at L1/L2** (code-complete + self-verified via gates + CR). **REMAINING (does not block this story's `done`, blocks Epic 10.6 done-flip clause 4):** AC-1 + AC-5 live Discord L3 walk — Adam-hands-on Phase 3.5: a real "draft a reply" turn producing an Opus `draft_reply` `router_calls` row (`model_chosen=claude-opus-*`) + small real Opus spend, Console-authoritative per [[feedback_anthropic_spend_source_of_truth]]. Precondition: Graph-auth drain (10-6-0 done) + live MCP session (restart hermes after any api restart). Staged, nothing committed. baseline_commit 18ea6d4.
