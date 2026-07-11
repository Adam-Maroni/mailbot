# Story AI-1 — Local tool-caller: verify-or-restore the cheap lane

**Status:** DONE-READY — full implementation + 2× MANDATORY-CR (round 2 PASS) + fidelity sweep + safety regression test all complete 2026-07-11. Nothing committed (staged in working tree per park convention). Awaiting Adam done-sign / commit.

## CLOSE-OUT 2026-07-11 (resumed + completed)

**Router gate fix (closes CR CRITICAL #1):** `_model_supports_tool_calls` split to capability-only; `qwen2.5:*` now tool-CAPABLE (regex `^qwen2\.5:`, `nomic-embed-text`/`qwen3`/etc fail-closed). Trust stays downstream in the model-INDEPENDENT propose_action→pending_actions→drain tier/grant pipeline (safety trace confirmed by 2 reviewers + direct read: `propose.py` has NO model param, `pending_actions` has NO model column). CR findings #2 (stale test), #3 (multi-turn tool-message translation), #4 (edge tests) all closed.

**MANDATORY-CR round 2: PASS** (reviewer sonnet ≠ dev opus, [[feedback_reviewer_model_substitution]]). Security-adjacent review independently traced the safety claim through real code — no bypass: a qwen tool-call can PROPOSE an irreversible action but it still needs grant+sensitivity-confirmation at drain, identical to opus. Test rewrites verified genuinely-correct (not green-washed). 0 findings.

**Fidelity sweep (the reliability-at-scale check, EXECUTED live vs mailbot-ollama, temp 0):**
- 6/6 short ids (initial probe) · 19/24 mixed/adversarial ids (79%) · 18/20 realistic Graph ids (90%; the 2 misses were on ids I malformed with stray chars).
- **Failure mode is SILENT CORRUPTION** (wrong-but-plausible id, e.g. trailing `.` appended, or truncation at an embedded quote), NOT a loud error. Realistic clean Graph ids are high-fidelity but NOT 100%.
- **This is exactly why Option 1 (Adam's safety-net design) is correct:** for REVERSIBLE actions a wrong id is undoable; for IRREVERSIBLE actions the human confirmation shows Adam the id before it fires — the architecture already contains this failure mode. Fidelity is NOT trusted blindly; the confirmation gate is the backstop.
- Residual consideration (NOT blocking): if a future need arises to let qwen auto-execute irreversible actions without confirmation, the ~90% silent-corruption rate would be disqualifying — a constrained-decoding/grammar shim or a larger local model would be needed. Not needed under the current design.

**Safety regression test (locks the load-bearing property):** `tests/integration/test_ai1_qwen_proposed_irreversible_still_gated.py` — 3 tests: (1) behavioural (DELETE Tier-3 + ARCHIVE Tier-2 land in confirmation-required states via real propose_action), (2) structural — `propose_action` signature carries no model/caller param, (3) structural — `pending_actions` schema carries no model/caller column. A future refactor adding model-awareness to the auth gate fails loudly. Honest limit: structural checks are a denylist (catch natural refactor names model/caller/proposer, not an obscure `proposed_via`).

**Final gates:** 114/114 tests green across all AI-1-touched files + the new safety test + F28 sensitivity gate (no privacy regression); ruff clean; mypy --strict clean. Test delta across the whole story: adapter +9 unit / +1 real (session 1), router-gate + contract-flip updates + edge/multi-turn (session 2), +3 safety tests. Suite green.

**REMAINING to fully close:** Adam done-sign. Code COMMITTED (branch `ai-1-local-tool-caller`, 2 commits). L2 complete.

### LIVE DISCORD WALK 2026-07-11 — AI-1 code CORRECT but NOT REACHED on the chat path (significant finding)

Ran the L3 walk. Result: **AI-1's Qwen tool-calling is real and correct, but the live Discord flow never routes a chat tool-call to Qwen — so the walk could not exercise AI-1 end-to-end.** DB ground truth (`router_calls`, last 15 min): EVERY chat turn logged `task_type=chat_completions_tool_call, model_chosen=claude-haiku-4-5-20251001`. The only qwen row was a background ingest enrichment (`sender_reputation_summary`), NOT a chat turn.

**Root cause — a stale write-off ONE MORE LAYER UP (policy, not code):** the routing policy sends `chat_completions_tool_call` → haiku. This was almost certainly written because until AI-1, qwen COULDN'T tool-call — so the policy correctly never sent tool-calls there. Now that qwen CAN (AI-1), the policy is a stale constraint. Same class as the adapter's old `tools_unsupported` and F-10-5-11: **"wired + capable + tested" ≠ "reached on the real user path."** AI-1 fixed the adapter + the router capability gate; the LAST mile is a `policy.yaml` routing decision (+ the persona self-serving tool-calls in haiku rather than asking the Router to dispatch to qwen).

**Walk also surfaced (all PRE-EXISTING, none AI-1):**
- **MCP session-drop** on first attempt — caused by MY mid-walk `mailbot-api` restart; known Hermes-transport fragility (F-10-5-1-W2). Fixed by restarting hermes to re-handshake. Lesson: restart hermes AFTER any api restart before a walk.
- **"use qwen" false-narration** (turn 1): persona replied in haiku claiming qwen — F-10-5-6-W1, already filed.
- **Premature "Done, marked as read"** while the drainer then FAILED `provider_4xx_401` (Graph auth) on action_id 40 — the Steam email was NOT actually marked read. Persona declared success before drain + a real Graph 401. The `mark_read` DID correctly propose as `tier:1 status:pending` (Tier-1 reversible, no confirmation) — that part matches AI-1's design — but drain failed on Graph creds (separate infra issue) and the persona over-narrated.

**Disposition:** AI-1 code stays DONE-READY/committed (correct + L2-proven). Its LIVE reachability is blocked by a policy/persona last-mile that is its OWN follow-up (route `chat_completions_tool_call` to qwen where appropriate, or have the persona dispatch through the Router). Pairs naturally with AI-2 (draft reachability) — same "capability wired, persona/policy doesn't reach it" class. Filed as AI-1-FU (chat-path routing to the local tool-caller). Also note: a Graph-auth 401 at drain is a separate live-infra item to chase before any action-taking walk.

---
**Epic:** pre-Epic-7 (drafted at the Epic 10.5 retrospective, 2026-07-11)
**Owner:** dev + Winston (architecture sign-off)
**Sequence:** before Epic 7. Was a P0 critical-path re-test with auto-escalation; **re-test EXECUTED — see verdict.**

---

## PARK NOTE — 2026-07-11 (pick up HERE)

Dev pass + MANDATORY-CR ran this session. **Adapter fix is real and green; the story is NOT goal-complete.** Parked at Adam's request pending one architecture decision.

**DONE + green (staged, uncommitted):**
- `mailbot_api/router/models.py` — `OllamaAdapter.call_with_tools` implemented for real (mirrors AnthropicAdapter; `_translate_tools_openai_to_ollama` helper; temp-0 pinned for argument fidelity; dict→JSON-string arguments; synthesized ids; fail-loud kept; docstring de-falsified). +helper.
- `tests/unit/router/test_ollama_adapter.py` — +9 unit tests (11→20). `tests/integration/test_ollama_adapter_real.py` — +1 opt-in real tool-call test (MAILBOT_RUN_REAL_OLLAMA=1).
- Gates: `pytest tests/unit/router/` 379 passed; `ruff` clean; `mypy --strict` clean.

**MANDATORY-CR verdict: FAIL** (reviewer sonnet ≠ dev opus, per [[feedback_reviewer_model_substitution]]). Findings, most-severe first:
1. **CRITICAL — `router.py:125` `_model_supports_tool_calls` still hard-codes `^claude-(haiku|opus|sonnet)` → returns False for `qwen2.5:*`.** This is the gate at `router.py:1937` (Story 10.5.5) that refuses a tool-call with `TOOL_CALLS_UNAVAILABLE_DEGRADED` **before** the now-fixed adapter is ever reached. So the cheap lane STILL can't act end-to-end — the adapter engine is fixed but the gate in front of it is shut. Same stale-write-off pattern, one layer up. **CONFIRMED by direct read.**
2. **HIGH — `tests/integration/test_chat_completions_tool_calling.py:751`** hits the real unmocked adapter (no MAILBOT_RUN_REAL_OLLAMA gate) and asserts the old `tools_unsupported` raise → now FAILS (`DID NOT RAISE`). Stale test; fix or gate it.
3. **MEDIUM — `models.py` `call_with_tools`** forwards OpenAI `role:"tool"` messages to Ollama unchanged; Ollama uses `tool_name` not `tool_call_id` → multi-turn tool rounds have no correlation guarantee. Latent (masked by #1), untested.
4. **LOW —** no tests for multiple tool_calls in one response, nor simultaneous text+tool_calls.

**THE PENDING DECISION (Adam's — do NOT flip autonomously):** the `router.py:125` gate was CORRECT when 10.5.5 built it (Qwen genuinely failed 18/18 then). Opening it now changes what **degraded mode** does: instead of cleanly refusing a tool-call when the budget-blown demotion lands on Qwen, it would **route a real mailbox action to the 3B local model** — the exact fidelity surface AI-1 says needs validation-at-scale before trusting writes. So the fix is not "flip True," it's "flip True *with a decision about the degraded-mode path*." Three options were on the table:
- **(A) Open gate + keep degraded refusal** — Qwen tool-capable in normal mode (cost thesis works); a degraded-demotion tool-call still refuses cleanly. (Amelia's recommendation — matches the fidelity caution.)
- **(B) Open gate fully** — Qwen tool-capable everywhere incl. degraded; simplest, most cost-saving, but routes real writes to 3B under budget overrun.
- **(C) Adapter-only now, gate as its own story** — land the (correct) adapter fix + test cleanups, defer opening the gate to a follow-up story with a real fidelity fixture first.

**To resume:** pick A/B/C, then close CRITICAL #1 (+ test cleanups #2, edge tests #4, and decide #3), re-run MANDATORY-CR (reviewer ≠ dev), then done-gates. Fidelity-at-scale fixture (≥20 realistic Graph ids) is still owed regardless of which option.

---

## ARCHITECT'S REFRAME — Winston, 2026-07-11 (decision DEFERRED — Adam is thinking about the values)

Adam asked to discuss the CRITICAL with the architect rather than pick A/B/C. Winston's reframe (preserve at full fidelity — this is the valuable artifact, not a choice):

**The `router.py:125` gate conflates TWO different questions under one regex, and shouldn't:**
1. **`can_emit_tool_calls(model)`** — a CAPABILITY question. AI-1 answered it: yes, Qwen can (temp 0, 6/6 probe).
2. **`should_route_action_to(model, action, reason)`** — a TRUST/POLICY question. Never actually designed — capability was standing in for it. Now that capability is `True`, the missing trust layer is exposed.

**Architectural claim:** the fix is to SPLIT the predicate into those two, not flip a boolean. Once split, A/B/C become consequences of where the trust line is drawn.

**The degraded-mode asymmetry (the crux):** two routes land a tool request on Qwen —
- **(route a) intentional** — `use qwen` one-shot / policy resolves local. Refusing here is *insulting* (you asked for it). This is the F-10-3-2 bug Adam is annoyed by.
- **(route b) involuntary** — budget blown, degraded demotion sheds paid models onto Qwen. Silently *acting* here is *dangerous* (a 3B model writes to the mailbox without the user ever choosing that).
The right behavior is OPPOSITE in the two routes → a single mode-based gate cannot express it.

**Winston's actual proposal (beyond A/B/C): gate on the ACTION'S BLAST RADIUS, not on the mode.**
- **Reads / reversible** (summarize, classify, draft-to-review, label): Qwen may act anywhere — normal AND degraded. Wrong label is cheap to undo.
- **Writes / irreversible** (move, archive, delete, send): require a capable paid model OR an explicit user confirmation when the actor is a 3B local model — regardless of mode. A `use qwen` one-shot can still PROPOSE a write; the human-in-the-loop confirmation (machinery ALREADY built in Epic 10.5 Cluster B) makes the 3B hand on the inbox safe.
- Reframes the fidelity worry correctly: the `ABC123→ABC132` risk isn't that Qwen is *local*, it's that it'd be *acting without a check*. Reuse the confirmation seam we already hardened (avoids the "mint-half/consume-half never wired" defect that hit twice this epic) rather than building a parallel model-size gate. Model size stops being the gate; action REVERSIBILITY becomes the gate — where it should have been all along.

**The values fork Winston put to Adam (Adam chose to think first, no code direction this session):**
- **Local lane is the SAFETY NET** — the local model is the zero-cost floor and SHOULD keep acting under budget pressure, gated by reversibility not mode (→ Winston's blast-radius design; bigger build; most faithful to the founding thesis that the local lane IS the floor).
- **Local lane is CONVENIENCE ONLY** — cost-saver in normal use, NOT trusted to autonomously act when the user isn't watching cost; degraded-mode action-taking refuses cleanly (≈ option A; simpler/safest; but the local lane stops being a floor exactly when most needed).

**DECISION — Adam, 2026-07-11: OPTION 1 (the SAFETY-NET / blast-radius design).** The local model stays useful under budget pressure; it acts on its own for reversible things and asks for user confirmation before anything irreversible — gated by the action's reversibility, NOT by mode. In plain terms Adam chose: "the free helper keeps working when money's tight, but asks me first before anything it can't easily undo."

**What this means for the implementation (the design now follows mechanically from the choice):**
- **SPLIT the `router.py:125` predicate** into `can_emit_tool_calls(model)` (capability — now True for qwen) and `should_route_action_to(model, action, reason)` (trust — the new gate).
- **Gate on blast radius, not mode:**
  - reads / reversible (summarize, classify, draft-to-review, label): qwen may act in BOTH normal and degraded mode.
  - writes / irreversible (move, archive, delete, send): when the actor is a 3B local model, require an explicit user confirmation — in normal AND degraded mode alike. A `use qwen` one-shot can PROPOSE a write; the confirmation makes it safe.
- **REUSE the Epic 10.5 Cluster B confirmation/approval machinery** for the write-confirmation step — do NOT build a parallel model-size gate (avoids the "mint-half/consume-half never wired" defect that hit twice this epic).
- Net effect on the CR CRITICAL #1: the gate opens for reads always; for writes it routes through confirmation rather than refusing. Route (a) intentional `use qwen` is honored; route (b) involuntary degraded-demotion writes go behind confirmation instead of silently acting — the danger Winston flagged is neutralized by the human check, not by refusal.

**STATUS: values decided (Option 1). RESUMED 2026-07-11 — implementation refined after code investigation (see below).** Adapter fix (staged) + CR findings above stand unchanged. Still nothing committed.

### RESUME INVESTIGATION 2026-07-11 — the design is ALREADY 80% built (Winston + Amelia)

Traced the action-authorization pipeline before writing code. **Key finding: the "reversibility gate" Winston designed already exists as the Tier system in `mailbot_api/actions/types.py`, and the trust layer is already model-independent.** This shrinks the CRITICAL fix from "build a new trust gate" to "stop the capability gate from doing double duty."

**What already exists (do NOT rebuild):**
- `ActionType` + `ACTION_PROPERTIES` registry (`actions/types.py`) classifies all 23 actions by reversibility via tier:
  - **Tier 1** = "silent + auto-revertible within 24h" (`reversibility_window_hours=24`): mark_read/unread, add/remove_local_category, move_to_triage_folder → **REVERSIBLE**.
  - **Tier 2** = grant-gated (`requires_grant`=True): archive, mark_junk, move_to_user_folder, unsubscribe, move_to_inbox → needs a grant.
  - **Tier 3** = grant + change-marker + (delete/send-family) sensitivity-token handshake → **IRREVERSIBLE/high-consequence**, already behind confirmation.
- Chat tool-calls that ACT flow through `propose_action` (`chat/orchestrator.py:312`) → `pending_actions` → drain-time grant/confirmation check. **This gate is MODEL-INDEPENDENT** — it doesn't care whether qwen or opus proposed the action. So a 3B model CANNOT punch a Tier-3 delete straight through; the delete still needs its grant + sensitivity confirmation at drain, same as always.

**Refined implementation (minimal, mostly deletion of a false constraint):**
1. **`router.py:125` `_model_supports_tool_calls`** — this gate was doing DOUBLE DUTY (capability AND trust). Split per Winston: make it answer capability only → qwen is now tool-CAPABLE (return True for `qwen2.5:*`). The trust decision is already handled downstream by the propose→grant→drain tier gate, which is untouched and model-independent.
2. **Degraded-mode path (`router.py:1937` gate):** the `TOOL_CALLS_UNAVAILABLE_DEGRADED` refusal should no longer fire merely because the model is local. Reversible (Tier-1) tool-calls proceed; irreversible ones still hit the existing grant/confirmation at drain. Route (a) intentional `use qwen` honored; route (b) degraded-demotion writes go behind the existing confirmation, not a silent action and not a blanket refusal.
3. **Preserve the sensitivity precondition** (`router.py:1980+`, Story 6-20 F28) and the FR-2.5 Qwen-locked classifier — untouched.
4. **Close CR findings:** #2 stale `test_chat_completions_tool_calling.py:751` (update to expect success now that qwen tool-calls), #3 multi-turn `role:"tool"` message translation (add or document), #4 edge tests (multiple tool_calls, text+tool_calls).
5. **Fidelity fixture** (≥20 realistic Graph ids) against live `mailbot-ollama` — still owed.
6. **Re-run MANDATORY-CR** (reviewer ≠ dev) on the full change, then done-gates.

**Why this is safe:** the fix is mostly REMOVING a false "qwen can't" constraint at the capability layer while the real trust enforcement (tier/grant/confirmation) was already correct and already model-agnostic. This is the "reuse the seam, don't build a parallel gate" the [[project_local_model_is_safety_net]] memory called for — confirmed by reading the pipeline, not assumed.

---

---

## Motivation

The founding cost thesis — *an LLM assistant that functions without high cost* — structurally depends on a LOCAL model that can call the pre-configured `mailbot_api` functions. Tool-calling IS how the cheap lane reaches those functions. Story 10-5-5 found the current local path fails 18/18 tool-call attempts because `OllamaAdapter.call_with_tools` ([mailbot_api/router/models.py:403-422](../../mailbot_api/router/models.py)) **unconditionally raises `tools_unsupported`** with the docstring claim *"Qwen 2.5 doesn't expose OpenAI-shape tool-calling at the inference surface we use."*

**Hard constraint (Adam-decided, retro D3):** any solution must run on the LOCAL Ollama stack, same hardware, $0 marginal cost. No cloud fallback on the default lane.

---

## Re-test verdict (EXECUTED 2026-07-11, live local stack)

**The docstring premise is FALSE. Qwen 2.5 3B (`qwen2.5:3b-instruct-q4_K_M`) CAN tool-call, on both API surfaces. No model swap required.**

Environment: live `mailbot-ollama` container (up 5 days, healthy), model `qwen2.5:3b-instruct-q4_K_M` (3B params, Q4_K_M quant), probed directly over HTTP (SDK-independent).

### Probe 1 — single call, both surfaces, default settings
- **Ollama native `/api/chat` + `tools`** → clean `tool_calls`: `archive_email(email_id="ABC123")`, empty content, `done`. **Correct.**
- **OpenAI-compat `/v1/chat/completions` + `tools`** → `finish_reason:"tool_calls"` with proper `tool_calls` array (the exact wire-shape the Router's `dispatch_tool_call` expects) — BUT argument corrupted: sent `ABC123`, got **`ABC132`** (digit transposition). ⚠️

### Probe 2 — argument-fidelity sweep, 6 varied ids, **temperature 0**
| Surface | Result |
|---|---|
| Ollama native `/api/chat` @ temp 0 | **6/6 EXACT** (incl. `AAmkAD00`, `msg-44172`, `hello-world-01`) |
| OpenAI-compat `/v1/chat/completions` @ temp 0 | **6/6 EXACT** (same set) |

**Conclusion:** the `ABC123→ABC132` corruption in Probe 1 was the OpenAI-compat surface at **default (non-zero) temperature**, NOT a model-capability ceiling. At **temperature 0** both surfaces are exact on 6/6. The adapter already calls at `temperature=0.0` by default ([models.py:350](../../mailbot_api/router/models.py)), so the correct-settings path is the one we'd wire.

**Verdict altitude (retro D5):** re-test **PASSES** → this is a **minor wiring fix**, NOT the hard Epic-7 gate. The cost thesis survives. No model swap, no constrained-decoding shim needed for basic tool-calling. **BUT** fidelity at 3B/Q4 must be validated at scale before we trust it with real mailbox writes (the Probe-1 transposition is a real warning that a small quantized model CAN corrupt an argument under the wrong settings).

---

## Scope (revised by the re-test verdict)

1. **Wire `call_with_tools` for real.** Replace the unconditional `raise` at [models.py:419](../../mailbot_api/router/models.py) with a real implementation calling `self._client.chat(model=..., messages=..., tools=..., options={"temperature": 0})` and mapping the `message.tool_calls` block into `ToolCallAdapterResponse` (mirror the Anthropic adapter's `_split_tool_calls` shape at [models.py:300-321](../../mailbot_api/router/models.py)). Keep the fail-loud contract for any surface that genuinely returns no tool_calls when tools were required — silent-drop is how F11 hid.
2. **Pin temperature 0 on the tool-call path** — the fidelity evidence shows default temperature corrupts arguments; temp 0 is exact. Make this explicit and commented (cite this probe).
3. **Reliability validation at scale (load-bearing).** Build a real fixture set (≥ 20–30 cases across the actual mailbot_api tool set: archive/move/draft/label with realistic Graph-style ids like `AAMkAD...`) and assert **exact argument fidelity + correct tool selection**. Pass bar: *reliable correct*, not happy-path. If fidelity drops below threshold on realistic long ids, THEN evaluate (a) Qwen 3 or (b) an adapter-side constrained-decoding/grammar-forced shim — ascending blast radius, evidence-driven (retro D4).
4. **Preserve the privacy invariant** — the Qwen-locked sensitivity classifier (FR-2.5, `assert_qwen_only`) stays local and unchanged; this story only touches the tool-call surface.
5. **Update the docstring with evidence** — replace the false `tools_unsupported` prose with the real behavior + a link to this probe evidence. No more prose-asserted limitations.

## MANDATORY-CR
Touches a load-bearing Router↔adapter seam → MANDATORY-CR, reviewer ≠ dev model ([[feedback_reviewer_model_substitution]]).

## Deploy note
`scripts/` and adapter code are bind-mounted, but verify the running `mailbot-ollama` path end-to-end (not just unit tests) — the whole point is driving the real inference surface (WALK-10-5-4-F1 deploy-mount caution).

## Relationship to AI-2
Kept SEPARATE from AI-2 (draft-pipeline reachability, F-10-5-11) per Adam D2 — distinct seams (Ollama adapter here vs chat-orchestration/persona there).
