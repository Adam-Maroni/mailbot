---
baseline_commit: 5880d1e
phase_2_baseline_commit: bc180e6
---

# Story 10.6.1 (AI-1): Local tool-caller — verify, restore, and reach it from chat

Status: done (Phase 1 DONE + committed; Phase 2 AC-5 dev-complete + MANDATORY-CR NOTABLE 5-patch + all done-gates green; AC-5 + AC-6 + privacy disposition VERIFIED live L3 at the real /v1/chat/completions endpoint + real drain-gate 2026-07-13 — see story-run-flags.md § "Story 10-6-1 Manual Verification". Epic 10.6 done-flip clause 3 discharged for the endpoint boundary.)
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
4. [DONE] **Phase 2:** investigated `policy.yaml` routing for `chat_completions_tool_call`. Root cause found: `dispatch_tool_call` sourced its DEFAULT model from the `hermes_aux` policy entry (haiku) — so every default chat tool-call landed on the paid lane regardless of qwen's Phase-1 capability. Fix: added a dedicated `chat_completions_tool_call` policy task (model=qwen) as the tool-call MODEL default; `hermes_aux` stays the LANE proxy (rate-limit/semaphore). `main.py` alias-resolution + the dispatcher's default-reason attribution both now key on the new entry. Overrides (one-shot/persistent/force) + degraded demotion unchanged. MANDATORY-CR owed (reviewer ≠ dev).
5. [DONE — no Hermes-side change needed] **Phase 2:** confirmed the persona does NOT self-serve tool-calls in haiku. `hermes-config/config.yaml` sends `model: "hermes_aux"` and `AGENTS.md` Rule N states the persona "does not name a model at all" — it delegates model choice to the Router per policy.yaml. The gap was 100% server-side (the Router's tool-call default pinned haiku), now fixed by Task 4. No persona/dispatch-contract change required.
6. [OPEN — Adam-hands-on, Phase 3.5] **Phase 2:** live Discord L3 walk for AC-5 + AC-6 (small/$0 — qwen is local). Restart hermes after any api restart to avoid the MCP session-drop; confirm Graph-auth drain works first (10-6-0 done). This is the per-story manual-verification prompt at run-end.

### In-scope latent bug surfaced + fixed during Phase 2

Routing the default to qwen REACHED the Ollama multi-turn translation path for the first time (Phase 1 opened the capability gate; Phase 2 made it the default). A prior-turn assistant message echoing OpenAI-shape `tool_calls[].function.arguments` (a JSON **string**) raised a pydantic `ValidationError` inside the `ollama` library, which requires `arguments` to be a **dict**. Fixed in `_translate_messages_openai_to_ollama` (string→dict decode; malformed args left as-is so the translator never raises mid-history). Witnessed by the `test_sensitivity_refusal_envelope_boundary` regression once the default routed to qwen. This is the exact "wired+capable+tested ≠ reached" class the story is about — the single-turn path was tested (Phase 1 6/6), the multi-turn echo was not reached until now.

### Privacy-model consequence (surfaced, not silently changed)

With the default routing to the LOCAL lane, a **confidential** email tool-call is no longer `SENSITIVITY_BLOCKS_API`-refused on the default path — the API-block gate fires only for API-bound models (`_API_BOUND_MODEL_RE`), and local qwen reading confidential content never leaves the device (NFR-PRIV-2 blocks EXTERNAL APIs, not local inference; this is why sensitivity classification itself runs on qwen). The `F-10-5-6` boundary test was updated to force an API model (so it still guards the API-bound graceful-refusal render) AND a companion test now pins the correct new behavior (confidential served locally, no id leak, audited as qwen). **Reviewer/Adam should confirm this privacy disposition is intended** — it is consistent with the documented local-safe model, but it is a real behavior change on the confidential tool-call path.

## Risks / Notes

- **Graph 401 at drain (separate infra blocker):** the AI-1 walk saw `drainer.row.failed provider_4xx_401` — action_id 40 (`mark_read`) proposed correctly as Tier-1 but failed to dispatch to Graph. Likely an expired `OUTLOOK_REFRESH_TOKEN`. NO action-taking walk (this story's AC-6, or AI-2's) can pass until Graph auth is restored. Chase this first. Handle any token via copy-to-file, never in chat ([[feedback_oauth_token_handling]]).
- **Fidelity is ~90%, not 100%, on realistic ids** — acceptable ONLY because the safety-net design routes irreversible actions through human confirmation. If a future need arises to let qwen auto-execute irreversible actions, that ~90% silent-corruption rate is disqualifying and a constrained-decoding shim / larger local model would be required. Out of scope here.
- **MCP session-drop (F-10-5-1-W2):** restarting mailbot-api drops Hermes's MCP session; restart hermes to re-handshake before a walk.

## Relationship

Pairs with [ai-2-draft-pipeline-reachability-from-chat.md](ai-2-draft-pipeline-reachability-from-chat.md) — AI-2 is the same "capability wired, persona/policy doesn't reach it" class for the Opus draft pipeline. Both are the reachability last-mile before Epic 7.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (dev, Phase 2 — autonomous-story-run). Phase 1 was dev=opus-4-8 / review sonnet across 2 rounds (see Phase 1 completion, committed 3c20304 + 5880d1e).

### Debug Log

- **Root cause of AC-5 (layer 3 reachability):** `dispatch_tool_call` resolved its default model from `policy.tasks["hermes_aux"].model` (haiku) — both in the dispatcher's default-reason branch and in `main.py._chat_completions_tools_dispatch`'s alias resolution. So every default chat tool-call landed on haiku regardless of Phase-1 capability. Confirmed against `router/policy.yaml` (no `chat_completions_tool_call` task existed) + the live-walk DB truth cited in the story.
- **Fix seam (2 files + 1 policy entry):** new `chat_completions_tool_call` policy task (model=qwen) as the MODEL default; `hermes_aux` retained as LANE proxy only. `main.py` alias→`chat_completions_tool_call`; dispatcher default reason→`policy_default(_TOOL_CALL_TASK_TYPE)`. Overrides + degraded demotion untouched (verified by existing bridge/degraded suites, all green).
- **Task 5 investigation (persona):** no Hermes-side change — the persona delegates model choice to the Router (config.yaml `model: hermes_aux`; AGENTS.md Rule N). Gap was 100% server-side.
- **Latent bug REACHED by the new routing:** Ollama multi-turn translation rejected string-form `tool_calls[].function.arguments` (pydantic ValidationError; ollama requires dict). Fixed in `_translate_messages_openai_to_ollama` (+ helper `_ollama_assistant_tool_calls_args_to_dict`). This broke `test_sensitivity_refusal_envelope_boundary` on first full-suite run — a genuine find, not a flaky test.
- **Discord-picker no-op guard:** `chat_completions_tool_call` added to `EXCLUDED_FROM_PERSIST_CHOICES` (same rationale as `embedding` — the persistent-override peek keys on `hermes_aux`, so persisting the tool-call task would be a silent no-op). Keeps the frozen Discord payload fixture unchanged.
- **Privacy disposition surfaced for reviewer/Adam:** confidential tool-calls are no longer API-blocked on the default (local) path — correct per the local-safe privacy model, but a real behavior change; flagged, tested both directions, not silently accepted.

### Completion Notes List

- **AC-5 (dev-complete):** a default chat tool-call now routes to qwen (local lane), proven by `router_calls` rows with `model_chosen=qwen2.5:*, model_chosen_reason=policy:chat_completions_tool_call:default` in `test_dispatch_tool_call_default_routes_to_local.py` + `test_main_tool_call_alias_resolves_local.py`. Overrides + force still win (regression-covered). The DB-truth proof of AC-5 on a *real Discord turn* is the Phase 3.5 walk (AC-6 precondition).
- **AC-6 (OPEN — Adam-hands-on):** live Discord L3 walk (reversible action served by qwen executes without prompt; irreversible prompts for confirmation). Not dev-codeable; fires as the per-story manual-verification prompt. Graph-auth drain precondition satisfied (10-6-0 done).
- **Safety invariant preserved:** the dispatcher only picks the PROPOSING model; the propose_action → drain tier/grant/sensitivity pipeline (model-independent) still gates whether a qwen-proposed action may ACT (unchanged; covered by `test_ai1_qwen_proposed_irreversible_still_gated.py`, still green). [[project_local_model_is_safety_net]]

### File List

- `router/policy.yaml` — new `chat_completions_tool_call` task (model=qwen) as the tool-call MODEL default; `hermes_aux` note updated to lane-proxy-only.
- `mailbot_api/main.py` — `_chat_completions_tools_dispatch` alias resolution `hermes_aux`→`chat_completions_tool_call` default.
- `mailbot_api/router/router.py` — default-reason attribution keys on `_TOOL_CALL_TASK_TYPE`.
- `mailbot_api/router/models.py` — `_translate_messages_openai_to_ollama` converts assistant `tool_calls` arguments string→dict for Ollama; new helper `_ollama_assistant_tool_calls_args_to_dict`.
- `scripts/register_discord_commands.py` — `chat_completions_tool_call` added to `EXCLUDED_FROM_PERSIST_CHOICES`.
- `tests/integration/test_dispatch_tool_call_default_routes_to_local.py` — NEW (AC-5 dispatcher default routing + override precedence).
- `tests/integration/test_main_tool_call_alias_resolves_local.py` — NEW (AC-5 main.py alias-resolution site).
- `tests/unit/router/test_ollama_adapter.py` — +2 tests (assistant tool_calls args string→dict; malformed-args preserved).
- `tests/integration/test_sensitivity_refusal_envelope_boundary.py` — F-10-5-6 test forced to API model + NEW companion (confidential served locally on the default lane).
- `tests/integration/test_chat_completions_tool_calling.py` — 2 tests updated to the new local-default contract.
- `tests/integration/test_dispatch_tool_call_override_bridges.py` — baseline fixture + no-override reason updated to the new default entry.

### Change Log

- 2026-07-13 — AI-1 Phase 2 (AC-5): route default chat tool-calls to the local lane (qwen) via a dedicated `chat_completions_tool_call` policy default; fix Ollama multi-turn tool_calls arg translation surfaced by the new routing; preserve override precedence + the model-independent action-safety pipeline. AC-6 live walk = Adam-hands-on (Phase 3.5).

## Review Findings — MANDATORY-CR 2026-07-13 (reviewer sonnet-5 ≠ dev opus-4-8)

3-hunter adversarial review (Blind Hunter, Edge Case Hunter, Acceptance Auditor) via `bmad-code-review`. The three safety-critical claims the Blind Hunter flagged as "asserted, not shown in diff" were independently VERIFIED by direct code read by the Acceptance Auditor + Edge Case Hunter:

- **SAFETY invariant** — Acceptance Auditor confirmed by code read: none of the changed files touch the sensitivity/tier/grant gating (`_API_BOUND_MODEL_RE`, `SENSITIVITY_BLOCKS_API`, drain pipeline). Phase-1 `test_ai1_qwen_proposed_irreversible_still_gated.py` still green.
- **Confidential-on-local privacy** — Acceptance Auditor located canonical PRD `confidential: Qwen-only, no exception`; the new behavior is *closer* to NFR-PRIV-2's letter than pre-diff (which defaulted confidential chat tool-calls to haiku, saved only by the separate refusal gate). Edge Case Hunter: "no code path escalates a confidential-content default dispatch from qwen to an API-bound model." Both directions pinned by tests. **Adam sign-off requested at Phase 3.5** on this disposition.
- **Override precedence** — Acceptance Auditor verified end-to-end: main.py supplies only a default + `is_force_override` flag; the dispatcher's one-shot/persistent peek is unconditional. Now also covered by a full-alias-path test (`test_oneshot_override_wins_through_main_alias_path`).

**Patches APPLIED (5):**

1. **[Blind #8 / Edge #5] valid-JSON-non-object args** — `_ollama_assistant_tool_calls_args_to_dict` now substitutes ONLY when the decoded value is a dict; a valid-JSON scalar/list (`'42'`, `'[1,2]'`, `'"x"'`, `'true'`, `'null'`) is left as the original string (Ollama surfaces its own typed error, same disposition as malformed JSON). +parametrized test.
2. **[Edge #2] broadened fallback guard** — `main.py` alias resolution now catches `(RuntimeError, AttributeError, KeyError)` so the documented haiku fallback holds for any snapshot-resolution failure, not just RuntimeError.
3. **[Edge #1] missing-entry visibility** — `main.py` logs a WARNING when `chat_completions_tool_call` is absent from the snapshot (a silent paid-lane fallback would otherwise look like normal traffic on the cost dashboard).
4. **[Edge #4] stale docstring** — `_emit_tool_calls_unavailable_audit_row` route-(b) comment corrected from `policy:hermes_aux:default` → `policy:chat_completions_tool_call:default`.
5. **[Blind isolation / docstring] copy semantics** — helper docstring corrected ("deep-copy" → accurate shallow-copy-of-mutated-substructures wording); +test asserting the caller's original message dicts are never aliased/mutated.

**DEFERRED / ACCEPT-WITH-RATIONALE:**

- `[deferred: hermes_aux lane-proxy fragility]` — removing the `hermes_aux` entry from a future policy edit would break tool-call dispatch (PROVIDER_ERROR). Documented in policy.yaml + router.py comments; both hunters + pre-review agree low-severity. Not blocking; no test added (a policy-completeness test is a separate concern).
- `[deferred: recursive nested-JSON decode]` (Edge #7) — the translator decodes only top-level `arguments`; a nested JSON-string value inside decoded args is left as a string. No evidence this system emits nested-JSON-string tool args (Ollama tool schemas take flat objects). Out of scope.
- `[deferred: redundant historical comments]` (Blind) — the "hermes_aux=lane proxy, chat_completions_tool_call=model source" fact is restated in 3-4 files. Style/maintainability; not a defect.
- `[deferred: /model force one-shot picker]` (Blind) — the one-shot force command does not enumerate policy tasks the way `/model persist` does, so the `EXCLUDED_FROM_PERSIST_CHOICES` concern doesn't apply symmetrically. No action.
- `[accept: malformed-args test doesn't assert ollama boundary error]` (Blind) — the malformed/non-object branches deliberately leave the string so Ollama raises; asserting the ollama validator's specific error is testing ollama, not our translator. Our contract (don't raise mid-history, don't fabricate a dict) is what's tested.

**Verdict:** NOTABLE — 5 patches applied (100% of actionable code findings), 5 deferred/accepted with rationale, 0 blocking. Reviewer ≠ dev held. All 4 gates re-green after patches.
