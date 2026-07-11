---
baseline_commit: 5880d1e
---

# Story 10.6.1 (AI-1): Local tool-caller — verify, restore, and reach it from chat

Status: in-progress (Phase 1 DONE + committed; Phase 2 reachability OPEN)
Epic: 10.6 (Capability Reachability) — sprint-status key `10-6-1-local-tool-caller-chat-path-reachability`

**Spawned at the Epic 10.5 retrospective (2026-07-11).** Adam-surfaced architecture-integrity finding: the founding cost thesis — *an LLM assistant that functions without high cost* — structurally depends on a LOCAL model that can call the pre-configured `mailbot_api` functions, because tool-calling IS how the cheap lane reaches those functions. Full history + evidence: [AI-1-local-tool-caller-verify-or-restore.md](AI-1-local-tool-caller-verify-or-restore.md) (working-notes precursor to this story).

## Story

As Adam,
I want the local model (Qwen) to be able to call the `mailbot_api` tools AND to actually be routed the chat tool-calls it's now capable of serving — with irreversible actions still gated by the existing human confirmation,
So that the cheap local lane genuinely carries real work end-to-end (not just in tests), the founding "LLM without high cost" thesis holds on the live product, and a wrong id from a 3B model can never silently touch my mailbox.

## Background & Findings

**The bug class (the retro's central lesson, hit three layers deep in this one story): "wired + capable + tested" ≠ "reached on the real user path."**

- **F-10-3-2** (Epic 10.5-5 walk) — qwen tool-calls failed 18/18. Root cause layer 1: `OllamaAdapter.call_with_tools` unconditionally raised `tools_unsupported` — a stale Story-6-9 write-off. **FIXED (Phase 1).**
- **AI-1 CR CRITICAL** — the router capability gate `_model_supports_tool_calls` hard-coded `^claude-*`, refusing qwen tool-calls before the fixed adapter was reached. Layer 2, same stale-write-off pattern. **FIXED (Phase 1).**
- **AI-1 live-walk finding (2026-07-11)** — even with adapter + router gate fixed, the live Discord flow routes EVERY `chat_completions_tool_call` to haiku, never qwen (DB `router_calls` ground truth). Layer 3: `policy.yaml` still routes chat tool-calls to haiku (correct pre-AI-1; stale now) AND/OR the persona self-serves tool-calls in haiku rather than asking the Router to dispatch to qwen. **OPEN (Phase 2 — the reachability last mile).**

**Values decision (Adam, 2026-07-11):** the local model is a SAFETY NET, not a convenience — it keeps acting under budget pressure, gated by action REVERSIBILITY not by mode, reusing the existing Cluster B confirmation machinery. Memory: [[project_local_model_is_safety_net]]. This is enforced by construction: the `propose_action → pending_actions → drain` tier/grant pipeline keys on the action, never on the proposing model (verified by 2 CR passes).

## Acceptance Criteria

### Phase 1 — capability (DONE + committed, branch `ai-1-local-tool-caller`)

**AC-1 (DONE).** `OllamaAdapter.call_with_tools` is a real implementation (not `raise tools_unsupported`): translates OpenAI-shape tools→Ollama, dispatches at temperature 0, maps `message.tool_calls` (dict args → JSON-string) into `ToolCallAdapterResponse`, keeps fail-loud, docstring de-falsified with probe evidence.

**AC-2 (DONE).** `_model_supports_tool_calls` split to capability-only; `qwen2.5:*` recognized as tool-capable; `nomic-embed-text`/`qwen3`/non-2.5 fail-closed. Docstring records that TRUST is enforced downstream and model-independently.

**AC-3 (DONE).** Safety property proven + regression-tested: a qwen-proposed irreversible (Tier-2/3) action still requires the existing grant/sensitivity confirmation at drain, because the auth pipeline has no model input. Test: `tests/integration/test_ai1_qwen_proposed_irreversible_still_gated.py` (behavioural + 2 structural).

**AC-4 (DONE).** MANDATORY-CR ×2, reviewer ≠ dev both rounds ([[feedback_reviewer_model_substitution]]); round-2 PASS (0 findings, safety trace independently confirmed). Fidelity sweep executed live: ~90% exact on realistic Graph ids at temp 0; failure mode is silent-corruption → the confirmation gate is the backstop. Gates green (114/114 on touched files, ruff, mypy-strict).

### Phase 2 — reachability (OPEN — the actual remaining work)

**AC-5 (OPEN).** A chat tool-call for a task the local lane should serve is ROUTED to qwen, not haiku — proven by a DB `router_calls` row with `task_type=chat_completions_tool_call, model_chosen=qwen2.5:*` from a real Discord turn. Requires resolving the `policy.yaml` routing for `chat_completions_tool_call` (currently → haiku, a stale pre-AI-1 constraint) so tool-calls can land on the now-capable local model per the cost policy, AND/OR the persona dispatching tool-calls through the Router rather than self-serving in haiku.

**AC-6 (OPEN).** Live Discord L3 walk: a reversible action requested in chat is served by qwen and EXECUTES with no confirmation prompt; an irreversible action requested in chat is served by qwen and PROMPTS for confirmation before dispatch (safety-net design, live). Precondition: the Graph-auth drain path works (see Risks — a 401 at drain currently defeats any action-taking walk regardless of model).

## Tasks

1. [DONE] Wire `OllamaAdapter.call_with_tools` + temp-0 fidelity pin + tests (session 1).
2. [DONE] Split `_model_supports_tool_calls` capability-only; qwen capable; fail-closed others (session 2).
3. [DONE] Safety regression test + CR findings #2/#3/#4 closed; MANDATORY-CR ×2 PASS; live fidelity sweep.
4. [OPEN] **Phase 2:** investigate `policy.yaml` routing for `chat_completions_tool_call`; decide where the local lane should serve tool-calls vs escalate; make the routing send eligible tool-calls to qwen. MANDATORY-CR (reviewer ≠ dev) — this touches the cost-routing seam.
5. [OPEN] **Phase 2:** if the persona (Hermes) self-serves tool-calls in haiku rather than dispatching through the Router, address the persona/dispatch contract so the Router's model selection is honored (may overlap the F-10-5-6 recognized-phrase dispatch work).
6. [OPEN] **Phase 2:** live Discord L3 walk for AC-5 + AC-6 (small/$0 — qwen is local). Restart hermes after any api restart to avoid the MCP session-drop; confirm Graph-auth drain works first.

## Risks / Notes

- **Graph 401 at drain (separate infra blocker):** the AI-1 walk saw `drainer.row.failed provider_4xx_401` — action_id 40 (`mark_read`) proposed correctly as Tier-1 but failed to dispatch to Graph. Likely an expired `OUTLOOK_REFRESH_TOKEN`. NO action-taking walk (this story's AC-6, or AI-2's) can pass until Graph auth is restored. Chase this first. Handle any token via copy-to-file, never in chat ([[feedback_oauth_token_handling]]).
- **Fidelity is ~90%, not 100%, on realistic ids** — acceptable ONLY because the safety-net design routes irreversible actions through human confirmation. If a future need arises to let qwen auto-execute irreversible actions, that ~90% silent-corruption rate is disqualifying and a constrained-decoding shim / larger local model would be required. Out of scope here.
- **MCP session-drop (F-10-5-1-W2):** restarting mailbot-api drops Hermes's MCP session; restart hermes to re-handshake before a walk.

## Relationship

Pairs with [ai-2-draft-pipeline-reachability-from-chat.md](ai-2-draft-pipeline-reachability-from-chat.md) — AI-2 is the same "capability wired, persona/policy doesn't reach it" class for the Opus draft pipeline. Both are the reachability last-mile before Epic 7.
