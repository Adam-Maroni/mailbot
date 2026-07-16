---
baseline_commit: 6cf920b
---

# Story 10.7.2: Tool-Format + Selection System Prompt (qwen dispatch seam)

Status: done

## Story

As the **MailBot Router dispatching a tool-call turn to the local qwen model**,
I want **a small, qwen-specific system-prompt instruction injected on the tool-call path that tells the model HOW to emit a structured tool call and to prefer the MailBot read/action verbs (e.g. `find_emails`) over plausible-but-wrong distractors**,
so that **the cheap local lane has a defensive belt-and-suspenders nudge toward faithful tool selection + structured-call format — WITHOUT trading away the load-bearing temp-0 argument fidelity, and without pretending it is the load-bearing fix (the `find_emails` description rewrite in 10.7.5 is).**

## Scope framing (READ FIRST — this story is DEMOTED to optional/defensive)

The 10.7.0 characterization spike (`10-7-0-spike-finding.md` §3, §4.4) measured this lever directly and found:

- On a **good tool description**, a system prompt adds **ZERO** — leaf selection was already 20/20 from the description rewrite alone (10.7.5, `done`); the strong enumerating prompt kept it at 20/20 (`leaf_desc` vs `leaf_desc_hint` vs `leaf_desc_strong`, all 20/20, §4.4).
- On a **bad (jargon) description**, a prompt was a *partial* recovery fighting the description (0/20 → 15/20, §4.3) — but 10.7.5 fixed the description, so that regime no longer exists on the primary read verbs.
- On the **flat 26-verb surface**, NO prompt tested recovers selection (0/N even with a strong enumerating prompt, §1) — the flat-menu problem is 10.7.3's (surface trim), not a prompt problem.

**Therefore this story is EXPLICITLY defensive / belt-and-suspenders (spike §4.4 fire-list item 3: "DEMOTED to optional/defensive; keep only as belt-and-suspenders").** It ships a *minimal, low-risk* qwen-path system-prompt hook so a residual on the real Hermes path has a cheap lever to lean on. It MUST NOT be sold as the clause-3 fix, and it MUST NOT regress temp-0 fidelity or the existing Hermes system-message concatenation contract. If measurement (Task 4) shows it adds nothing measurable on the real read verbs AND carries any fidelity risk, the honest outcome is to ship it OFF-by-default (gated, no-op unless explicitly enabled) and file that as the disposition — not to force a change that looks busy.

## Acceptance Criteria

1. **A qwen-specific tool-call system-prompt instruction exists and is injected only on the local tool-capable model path.** When `dispatch_tool_call` resolves the effective model to a tool-capable LOCAL model (`_TOOL_CAPABLE_LOCAL_MODEL_RE`, i.e. `qwen2.5:*`) AND a tools request is being dispatched, a short qwen-authored instruction is composed into the `system_text` handed to `adapter.call_with_tools` (`router.py:2442-2477`). API-bound models (`claude-*`) receive NO such injection — their path is unchanged, byte-for-byte.

2. **The injection composes WITH the client-sent system messages, never replaces them.** The existing Hermes contract (concatenate ALL client system messages with `"\n\n"`, `router.py:2442-2459`, CR-6 Story 6-9) is preserved: SOUL.md + AGENTS.md + SKILL.md system blocks the client sent still all reach the model. The qwen instruction is composed as an ADDITIONAL block (documented order — appended or prepended, with a rationale), not a substitution. A dispatch with zero client system messages still gets a valid (instruction-only) system_text; a dispatch with N client system messages gets all N + the instruction.

3. **The instruction is a no-op for non-tool dispatch and for `tool_choice == "none"`.** The `system_text` handed to the adapter for a `qwen2.5:*` NON-tool `ask_router` call (the `call(...)` path, not `call_with_tools`) is unaffected — this story touches ONLY the `dispatch_tool_call` tool-calling seam, not `ask_router`. (`ask_router` prompt assembly is out of scope; do not touch it.)

4. **Measured, not assumed — a real-N fidelity + selection re-check is run and recorded (spike §4.4 caveat, review Finding #3 carry-forward).** Using the existing `scratch/qwen_toolcall_spike_107.py` direct-drive harness at temp 0, measure with the new instruction present: (a) tool-call argument round-trip fidelity at AI-1-comparable N (≥ the AI-1 baseline sample count, on adversarial Graph-style ids) — MUST remain exact (no `ABC123`→`ABC132`-class corruption); and (b) leaf selection on the (already-rewritten) `find_emails` description — MUST stay ≥ the description-only 20/20 baseline (i.e. the prompt must not REGRESS selection). Record both in a short evidence note. If fidelity regresses at all, the instruction ships gated-OFF (AC-6 disposition) — fidelity is non-negotiable (memory `project_local_tool_caller_gates_epic_7`, models.py:596-628 / 760-765).

5. **Unit tests prove the seam.** `tests/unit/router/` gains tests asserting: (a) a `qwen2.5:*` tools dispatch produces a `system_text` containing the qwen instruction (spy/capture on `adapter.call_with_tools`'s `system` kwarg); (b) a `claude-*` tools dispatch produces a `system_text` WITHOUT the instruction (unchanged path); (c) client system messages are all preserved alongside the instruction (AC-2); (d) the non-tool `ask_router` qwen path is unchanged (AC-3). Existing `dispatch_tool_call` + `test_ollama_adapter.py` tests stay green.

6. **Honest disposition recorded — on-by-default vs gated-off decided by AC-4's data.** The story's Completion Notes state explicitly whether the instruction ships on-by-default (measurement showed neutral-or-better selection AND exact fidelity) or gated-off/defensive-only (measurement showed no benefit or any fidelity risk). Either is an acceptable ship; forcing on-by-default against the data is NOT. Cost thesis stays $0/local; the propose→grant→drain safety pipeline is untouched (no model-column change; a faithful qwen call is still gated by reversibility at drain — memory `project_local_model_is_safety_net`).

## Tasks / Subtasks

- [x] **Task 1 — Author the qwen tool-call instruction string + gating predicate (AC: 1, 2)** — added `_QWEN_TOOLCALL_SYSTEM_INSTRUCTION` (short, natural-language: emit structured call not `<tool_call>` text + prefer email-reading verbs) + `_compose_qwen_toolcall_system_text(model, system_text)` helper near the gate predicates (`router.py:117-215` region). Gate reuses `_TOOL_CAPABLE_LOCAL_MODEL_RE` (qwen-only) — NOT `_model_supports_tool_calls` (which is True for `claude-*` too).
  - [x] Module-level constant added.
  - [x] Gate reuses the existing qwen-only regex.
- [x] **Task 2 — Wire the injection into the `dispatch_tool_call` system-prompt assembly (AC: 1, 2, 3)** — after `system_text = "\n\n".join(system_parts)`, call `_compose_qwen_toolcall_system_text(model, system_text)`. Instruction APPENDED after client persona blocks (rationale in helper docstring: persona leads, mechanical nudge trails as most-recent directive). `claude-*` path returns unchanged.
  - [x] Composed at the `system_text` assembly site, `"\n\n"` contract preserved.
  - [x] Flows unchanged to `adapter.call_with_tools(system=system_text, …)`; F14 non-empty guard handles instruction-only case.
  - [x] `ask_router` / non-tool `call(...)` path untouched (AC-3).
- [x] **Task 3 — Unit tests for the seam (AC: 5)** — `tests/integration/test_dispatch_tool_call_qwen_system_prompt.py`: qwen dispatch injects instruction; claude dispatch does not; client system messages preserved alongside; instruction-only when zero client system messages. 4/4 pass; existing dispatch + `test_ollama_adapter.py` green.
  - [x] RED (import of missing constant failed) → GREEN (4 passed) → REFACTOR (reused the `_RecordingAdapter` spy pattern from the sibling default-routes test).
- [x] **Task 4 — Real-N measurement + evidence note (AC: 4, 6)** — `mailbot-ollama` WAS up; ran `scratch/qwen_toolcall_10_7_2_measure.py` (imports the PRODUCTION constant). Selection 20/20 (no regression vs description-only baseline); adversarial Graph-id fidelity 20/20 exact at temp 0. Evidence: `10-7-2-measurement-evidence.md`.
  - [x] Live measurement run (not deferred — container available).
  - [x] Evidence note written with sample-size honesty + disposition.
- [x] **Task 5 — Completion Notes disposition (AC: 6)** — ship ON-by-default (both AC-4 conditions cleared: neutral selection + exact fidelity); $0/local; safety pipeline untouched; does NOT discharge clause 3 (defensive scaffolding under the live-Discord gate).

### Review Findings

- [x] [Review][Patch] APPLIED — added `test_budget_degraded_demotion_to_qwen_receives_instruction` (degraded mode active + model=haiku → demotes to qwen → spy asserts `system` carries the instruction). No test proves the demoted-to-qwen path receives the instruction — the injection's central placement rationale (gating on the post-degraded-demotion `model`, per the Dev Notes / inline comment at `router.py:2519`) is asserted but never exercised end-to-end [mailbot_api/router/router.py:2020-2023, 2523] — Add a test that puts degraded mode active (`_reset_guard_for_test` / the guard's degraded-set helper used by sibling tests, e.g. `test_dispatch_tool_call_degraded_no_qwen_tools`), dispatches with a `claude-*` (or policy-default) model that demotes to `qwen2.5:*`, and asserts the `system` kwarg captured by a `_RecordingAdapter` spy contains `_QWEN_TOOLCALL_SYSTEM_INSTRUCTION`. Without this, a future change to `demote_model`/the degraded-mode gate ordering could silently break the one scenario (budget-degraded turn lands on qwen) this story explicitly cites as its reason for gating on `model` at the late call site rather than earlier.
- [x] [Review][Patch] APPLIED — changed `if system_text:` → `if system_text.strip():` so all-whitespace client system text is treated as empty (instruction-only, no leading blank-line junk); added `test_whitespace_only_client_system_message_no_leading_junk` (seam) + `test_compose_helper_instruction_only_for_whitespace_system` (unit). Whitespace-only / empty-string client system message is untested at the composition seam [mailbot_api/router/router.py:184-186] — `if system_text:` is truthy for any non-empty string including `"   "`, so a client system message of `{"role": "system", "content": ""}` or all-whitespace content is untested through `_compose_qwen_toolcall_system_text`/`dispatch_tool_call`. Add a case (unit-level on the helper, or seam-level via `_RecordingAdapter`) asserting the resulting `system` is still well-formed (no leading blank-line junk before the instruction, or explicitly accept the cosmetic leading `"\n\n"` if that's the intended behavior).
- [x] [Review][Patch] APPLIED — added 7 direct unit tests on the pure helper: canonical qwen, empty system, whitespace system, claude no-op, empty-model no-op, case-sensitive gate (`Qwen2.5:3b` → no-op), colon-required gate (`qwen2.5` → no-op). `_compose_qwen_toolcall_system_text` has no direct/unit-level test — all 4 tests exercise it only through the full `dispatch_tool_call` integration seam [tests/integration/test_dispatch_tool_call_qwen_system_prompt.py] — Add direct unit tests for the pure function covering: `model=""` (empty string), a case-variant qwen id (e.g. `"Qwen2.5:3b"`), and a no-colon variant (e.g. `"qwen2.5"`), asserting `_TOOL_CAPABLE_LOCAL_MODEL_RE.match` boundary behavior is what's intended (case-sensitive, colon-required) rather than relying solely on the two integration tests that only cover the canonical `qwen2.5:3b-instruct-q4_K_M` and `claude-haiku-*` ids.
- [x] [Review][Patch] APPLIED — extracted `_SYSTEM_BLOCK_SEPARATOR = "\n\n"` module constant; both the `dispatch_tool_call` `.join(system_parts)` site and `_compose_qwen_toolcall_system_text` now use it, so they cannot drift. The `"\n\n"` separator convention is duplicated as a bare literal in two places with no shared constant, coupling `_compose_qwen_toolcall_system_text` to the caller's join convention by convention only [mailbot_api/router/router.py:185, 2515] — The helper's docstring explicitly says it must match "the same separator the caller used" (CR-6 Story 6-9 contract); if the `"\n\n".join(system_parts)` separator at the call site ever changes, `_compose_qwen_toolcall_system_text` would silently drift out of sync since nothing enforces the two literals stay identical. Extract a shared module-level constant (e.g. `_SYSTEM_BLOCK_SEPARATOR = "\n\n"`) and use it at both sites.
- [x] [Review][Patch] APPLIED — rewrote the AC-6 Completion Notes bullet to state the decision is "zero-measured-benefit, zero-measured-cost, ship anyway for defensive coverage of the untested regime" and explicitly that AC-4 never touched the flat-26 / live-Hermes surfaces where a benefit might show — not a symmetric strong pass. AC-6 disposition ("ship ON-by-default... both AC-4 conditions cleared") reads as a clean pass but the underlying evidence is "no measured downside," not "measured upside" — the spike's own §4.4 finding (cited in this story's Scope framing) is that the prompt adds ZERO benefit on the regime actually tested (good description, leaf surface); AC-4's measurement never touches the flat-26 surface or the live Hermes path where a benefit might actually show up [_bmad-output/implementation-artifacts/10-7-2-tool-format-and-selection-system-prompt.md Completion Notes AC-6; 10-7-2-measurement-evidence.md Disposition section] — Not a functional defect (the "ship it, it can't hurt" call is defensible), but the Completion Notes should say explicitly that the decision is "zero-measured-benefit, zero-measured-cost, ship anyway for defensive coverage of the untested regime" rather than implying both AC-4 conditions were symmetrically satisfied as a strong pass. A one-sentence rewrite of the AC-6 Completion Notes bullet resolves this.
- [x] [Review][Defer] Client-sent system messages could contain adversarial/conflicting text that neutralizes the trailing qwen instruction (prompt-injection-style override risk); the append-after-persona ordering rationale ("most-recent = operative") is asserted, not verified against adversarial input [mailbot_api/router/router.py:172-176] — deferred, out of scope for this defensive/belt-and-suspenders story; would apply equally to any system-prompt composition in the codebase and is not introduced or worsened by this change.
- [x] [Review][Defer] Dev Notes / inline comment cite the degraded-mode demotion reassignment at `router.py:1964-1967`; the actual current location is `router.py:2020-2023` (the file has grown since the citation was authored) [_bmad-output/implementation-artifacts/10-7-2-tool-format-and-selection-system-prompt.md Dev Notes; mailbot_api/router/router.py:2519] — deferred, stale citation only; the underlying claim (injection site is post-demotion) was independently verified true against current code, and the related test-coverage gap is tracked as a separate Patch item above.
- [x] [Review][Defer] Story spec text says new tests land in `tests/unit/router/` (AC-5 preamble, File structure requirements) but the file actually shipped at `tests/integration/test_dispatch_tool_call_qwen_system_prompt.py`, matching the sibling integration-test pattern it reused — deferred, cosmetic spec-text/actual-path mismatch with no functional impact; correct at next spec touch-up.

## Dev Notes

### Technical requirements (stack, seam, invariants)

- **Language/stack:** Python 3.12, `mailbot_api` package. Router is the integration boundary; MANDATORY-CR applies (dispatch seam, reviewer ≠ dev — memory `feedback_reviewer_model_substitution`).
- **The seam is `dispatch_tool_call`, NOT `ask_router`.** `dispatch_tool_call` (`router.py:1754`) is the OpenAI-shape tool-call sibling. Its system-prompt assembly is at `router.py:2442-2459` (concatenate client system messages with `"\n\n"`), then `system_text` is passed to `adapter.call_with_tools(system=system_text, …)` at `:2470-2477`. The effective `model` variable is fully resolved (incl. degraded-mode demotion to qwen, `:1964-1967`) before that block — so gating on `model` there is correct.
- **Gate predicate already exists:** `_TOOL_CAPABLE_LOCAL_MODEL_RE = re.compile(r"^qwen2\.5:")` (`router.py:130`) and `_model_supports_tool_calls(model)` (`:133-167`). Use the regex directly for the "is-local-qwen" gate — `_model_supports_tool_calls` is TRUE for `claude-*` too, so it is the WRONG gate here (we want qwen-only). This is a subtle trap: the injection must be qwen-only, so match `_TOOL_CAPABLE_LOCAL_MODEL_RE` (or an equivalent qwen-only check), NOT `_model_supports_tool_calls`.
- **Adapter behavior confirmed (`models.py:785-794`):** `OllamaAdapter.call_with_tools` prepends the `system` message only when non-empty (F14 guard), then forwards the caller's messages. So an instruction-only `system_text` is handled cleanly; a `system_text` with client blocks + instruction is prepended whole as one system message.
- **Temp-0 fidelity is LOAD-BEARING and must not regress** (`models.py:596-628` in the anthropic translate helper region + `:760-765` docstring): the AI-1 probe saw non-zero temp corrupt `ABC123`→`ABC132`. This story adds a system prompt, which changes the model's context — AC-4 exists precisely to prove the added prompt does not perturb argument round-trip. Do not raise temperature; do not add `num_ctx` (Story 10-6-4 measured it irrelevant, `models.py:797-801`).

### Architecture compliance (files to touch, patterns)

- **Touch:** `mailbot_api/router/router.py` (the instruction constant + the injection at the `system_text` assembly), `tests/unit/router/` (new seam tests), `scratch/` (measurement harness flag — NEVER staged), `_bmad-output/implementation-artifacts/10-7-2-measurement-evidence.md` (evidence).
- **Do NOT touch:** `ask_router`, the `call(...)` non-tool path, `mcp_server.py` (that's the tool-description surface — 10.7.5's territory, already done), `hermes-config/` (that's 10.7.3's surface-trim territory), `mailbot_api/actions/*` (the safety pipeline is model-independent and untouched).
- **Pattern:** mirror the existing single-writer / gated-behavior style in `router.py`. Comment the injection block with the story id + the spike's "DEMOTED / defensive" framing so a future dev knows this is NOT the load-bearing lever.

### File structure requirements

- New instruction constant lives at module scope near `_TOOL_CAPABLE_LOCAL_MODEL_RE` / `_model_supports_tool_calls` (`router.py:117-167` region) for locality with the gate.
- New tests co-locate with the existing `dispatch_tool_call` test module under `tests/unit/router/`.

### Testing requirements

- Framework: pytest (`.venv/Scripts/python.exe -m pytest -q`; live marker auto-excluded via `addopts`).
- Gates: ruff (`ruff check .`), mypy (`mypy --strict mailbot_api` or project target), full pytest suite green. Baseline suite count per the most recent done story (10-7-1: pytest 1957). Net-new tests should raise the count.
- Direct-drive measurement (Task 4) is a `scratch/` harness run, NOT a pytest test — its output is an evidence `.md`, not a committed test (the live-Ollama dependency makes it non-hermetic).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 10.7 Detail] — epic identity (routed → usable → faithful), the two F-10-6-5-W1 defects, code-recon grounding, done-flip 4-clause gate (clause 3 load-bearing = live Discord qwen `find_emails` turn; this story is defensive under it, does NOT discharge it).
- [Source: _bmad-output/implementation-artifacts/10-7-0-spike-finding.md#4.4] — the measurement that DEMOTES this story: system prompt added ZERO on a good description (20→20); description rewrite (10.7.5) is the primary lever; flat-26 selection unrecoverable by prompt (10.7.3's territory). Sample-size honesty note to carry forward. Temp-0 fidelity re-check at real N owed at 10.7.2 impl time (§4.1 / review Finding #3).
- [Source: mailbot_api/router/router.py#L2442-2477] — the `dispatch_tool_call` system-prompt assembly + adapter dispatch seam (injection site).
- [Source: mailbot_api/router/router.py#L130-167] — `_TOOL_CAPABLE_LOCAL_MODEL_RE` + `_model_supports_tool_calls` (gate predicates; use the regex, not the capability fn, for qwen-only injection).
- [Source: mailbot_api/router/models.py#L741-835] — `OllamaAdapter.call_with_tools` (F14 non-empty-system guard, temp-0 fidelity docstring, num_ctx-red-herring note).
- [Source: sprint-status.yaml 10-7-2 row] — DEMOTED to optional/defensive; dispatch fix; NONE exists on the qwen tool-call path today; must NOT trade away temp-0 arg fidelity without a walk; MANDATORY-CR reviewer≠dev.
- [Memory: project_local_tool_caller_gates_epic_7] — qwen 6/6 exact at temp 0; fidelity is the invariant.
- [Memory: project_local_model_is_safety_net] — reversibility (not model size) is the trust gate; a faithful qwen call is still gated by propose→grant→drain.
- [Memory: feedback_reviewer_model_substitution] — MANDATORY-CR reviewer model ≠ dev model.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (dev, autonomous-story-run). Review: claude-sonnet-5 (MANDATORY-CR, reviewer ≠ dev).

### Debug Log

- Gate for the injection is `_TOOL_CAPABLE_LOCAL_MODEL_RE` (qwen-only), NOT `_model_supports_tool_calls` — the latter matches `claude-*` too, which would wrongly inject on the API path. This is the one subtle trap in the story; a dedicated test (`test_claude_tool_dispatch_does_not_inject_instruction`) locks it.
- `model` at the injection site (`router.py:~2467`, the `system_text` assembly) is the EFFECTIVE post-degraded-demotion target (demotion happens at `:1964-1967`), so a budget-degraded demotion landing on qwen correctly receives the instruction.
- Instruction APPENDED (not prepended) after client persona blocks: the client's SOUL/AGENTS/SKILL persona leads; the mechanical tool-call nudge trails as the most-recent operative directive. Preserves the CR-6 Story 6-9 `"\n\n"` concatenation contract.
- Live measurement (Task 4) confirmed the spike's §4.4 prediction on the PRODUCTION string: a good prompt adds nothing on a good description (selection 20/20 either way) — and, load-bearingly, subtracts nothing from temp-0 argument fidelity (adversarial Graph-id 20/20 exact).

### Completion Notes List

- **AC-1** — qwen-only instruction injected at the `dispatch_tool_call` seam via `_compose_qwen_toolcall_system_text`, gated on `_TOOL_CAPABLE_LOCAL_MODEL_RE`; `claude-*` path byte-for-byte unchanged (test-locked both directions).
- **AC-2** — composed WITH client system messages (`"\n\n"` join preserved); N client blocks + instruction all reach the model; zero-client-block case yields instruction-only system_text (3 tests).
- **AC-3** — only `dispatch_tool_call` touched; `ask_router` and the non-tool `call(...)` path untouched (scope fence; the helper is called nowhere else).
- **AC-4** — live direct-drive measurement (SPIKE_N=5): selection 20/20 (no regression vs description-only 20/20), adversarial Graph-id fidelity 20/20 exact at temp 0. Evidence in `10-7-2-measurement-evidence.md`.
- **AC-5** — `tests/integration/test_dispatch_tool_call_qwen_system_prompt.py`, 13/13 pass (4 seam + degraded→qwen + whitespace-edge + 7 direct helper unit tests, the last 9 added in the CR round); full suite 1970 passed (+13 vs 10-7-1 baseline 1957).
- **AC-6** — DISPOSITION: **ship ON-by-default — on a "zero-measured-benefit, zero-measured-cost, ship anyway for defensive coverage of the untested regime" basis, NOT a symmetric strong pass.** Honest framing (10.7.2 review [Patch]): AC-4 measured the instruction on the ONE regime the spike already characterized (good `find_emails` description, small leaf surface) and found it neutral (selection 20/20 either way) AND fidelity-safe (Graph-id 20/20 exact). It did NOT measure the flat-26 surface or the live Hermes path where a benefit (if any) would show up — so the ship decision rests on "measured no downside" + "cheap belt for the untested real path," not "measured upside." $0/local, safety pipeline (propose→grant→drain) untouched (no model column). **Does NOT discharge Epic 10.7 clause 3** (the live Discord qwen→find_emails turn) — this is defensive scaffolding UNDER that gate, owed at the epic live walk.
- **Scope-honesty (spike §4.4):** this story is DEMOTED to optional/defensive. The load-bearing lever was the `find_emails` description rewrite (10.7.5, done); getting qwen to a small menu is 10.7.3 (surface trim). Shipped anyway as a cheap belt for the real Hermes path, with measurement proving it is neutral-or-better and fidelity-safe.

### File List

- `mailbot_api/router/router.py` — added `_QWEN_TOOLCALL_SYSTEM_INSTRUCTION` constant + `_compose_qwen_toolcall_system_text` helper; wired the injection into the `dispatch_tool_call` `system_text` assembly.
- `tests/integration/test_dispatch_tool_call_qwen_system_prompt.py` — NEW; 4 seam tests.
- `_bmad-output/implementation-artifacts/10-7-2-tool-format-and-selection-system-prompt.md` — this story file.
- `_bmad-output/implementation-artifacts/10-7-2-measurement-evidence.md` — NEW; Task 4 evidence.
- `scratch/qwen_toolcall_10_7_2_measure.py` — NEW measurement harness (scratch-only, gitignored, NOT staged).

### Change Log

- 2026-07-16 — Shipped a qwen-only, defensive tool-call system-prompt injection at the `dispatch_tool_call` seam; live-measured neutral selection (20/20) + exact temp-0 fidelity (20/20); ships on-by-default. Does not discharge clause 3.
- 2026-07-16 — MANDATORY-CR (reviewer sonnet-5 ≠ dev opus-4-8): 5 Patch findings, 5/5 applied (100%) + 3 Defers (all correctly out-of-scope: adversarial prompt-injection is a codebase-wide property not introduced here, a stale line-cite whose underlying claim was independently verified, a cosmetic test-path spec mismatch). Fixes: degraded→qwen instruction test, whitespace-only client-system `.strip()` guard + test, 7 direct helper unit tests, extracted `_SYSTEM_BLOCK_SEPARATOR` constant, honest AC-6 disposition rewrite. Test count +9 this round.
