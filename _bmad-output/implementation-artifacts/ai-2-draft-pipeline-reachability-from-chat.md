---
baseline_commit: 5880d1e
---

# Story 10.6.2 (AI-2): Draft-pipeline reachability — the persona reaches the real Opus draft path from chat

Status: backlog (spawned at the Epic 10.5 retrospective, 2026-07-11)
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

1. Reproduce F-10-5-11 live: confirm current behavior (persona improvises in haiku; 0 Opus `draft_reply` rows on a chat draft request) against the running stack.
2. Diagnose the reach gap: is `draft_reply` actually exposed to the persona as an MCP tool (10-5-3 registered it — verify it's discoverable + its description is accurate), and does the persona's contract tell it to issue that verb for draft requests vs improvise?
3. Fix the reachability: persona-contract / hermes-config change (and/or MCP tool-description fix) so a draft request deterministically dispatches the real `draft_reply` pipeline. Boundary-honest: if the fix is Hermes-side, do NOT fabricate a `mailbot_api` change (same discipline as Epic 10.5).
4. MANDATORY-CR (reviewer ≠ dev).
5. Live Discord L3 walk (AC-1/AC-5) — Adam-hands-on, small real Opus spend. Precondition: Graph-auth drain works and MCP session is live (restart hermes after any api restart).

## Risks / Notes

- **Depends on the same live-infra health as AI-1's walk:** the Graph 401 at drain (see AI-1 story Risks) and the Hermes MCP session-drop (F-10-5-1-W2) both affect any live draft walk. Draft itself may not hit the drain path (drafting ≠ sending), but a send-the-draft follow-through would.
- **Boundary honesty:** 10-5-3 established that the draft tool IS registered; the residual is persona-reach, which is Hermes-side. Expect the fix to live in `hermes-config/` (persona contract), not `mailbot_api` — same pattern as 10-5-6's charter/dispatch work. Confirm before writing code.
- Real Opus spend on the verification walk — pre-flight estimate + Console truth, never local placeholder.

## Relationship

Sibling to [ai-1-local-tool-caller-and-chat-path-reachability.md](ai-1-local-tool-caller-and-chat-path-reachability.md) — both are the "capability wired but persona/policy doesn't reach it" class (AI-1 = local qwen tool-calls routed to haiku; AI-2 = Opus draft pipeline not dispatched by the persona). Both are the reachability last-mile that must close before Epic 7 calibrates a perimeter these capabilities live behind. Kept as separate stories per Adam D2 (distinct seams: AI-1 = router/policy + adapter; AI-2 = persona draft-dispatch contract).
