---
baseline_commit: 8c1e02f
---

# Story 10.7.0: Characterization Spike — Harness-Fixable vs. Qwen-3B Ceiling

Status: done

## Story

As the MailBot maintainer chasing the founding cost thesis's final gate,
I want a **measured** characterization of *why* local qwen mis-selects tools (`send_message` over `find_emails`) and emits its tool calls as literal `<tool_call>` text instead of a structured `tool_calls` object,
so that I can decide — on evidence, not guess — whether the fix belongs in the **harness** (rescue parser / system prompt / surface trim, stories 10.7.1–10.7.3) or requires a **local model swap** (story 10.7.4, only if this is a Qwen-3B ceiling).

This is the **HIGHEST-priority** story in Epic 10.7 and **gates 10.7.1–10.7.4**, which are all provisional/contingent on this spike's go/no-go finding. It is a **characterization spike** — it produces a recommended fix path, not a production code change. Discipline: **measure-before-fix** (mirrors 10.6.4's `num_ctx` red-herring, where a plausible fix lever was measured irrelevant before any code was committed).

## Acceptance Criteria

1. **Reproduce the two defects in a controlled harness.** A repeatable probe (against the live local `mailbot-ollama` qwen `qwen2.5:3b-instruct-q4_K_M`, temperature 0) reproduces, on a **clean** 5-toolset surface matching the 10.6.5 post-fix `platform_toolsets.discord` allow-list, BOTH observed defects from the F-10-6-5-W1 walk (router_calls id=14937): (a) **mis-SELECTION** — qwen prefers a non-`find_emails` tool (e.g. `send_message`) for a "find my unread emails" turn; and (b) **FORMAT** — qwen emits the call as literal `<tool_call>{…}</tool_call>` text in `message.content` rather than a structured `message.tool_calls` array. If either defect does **not** reproduce on the clean surface, that itself is a first-class finding (record it — it would mean the defect was surface-coupled after all).

2. **Isolate SELECTION from FORMAT.** The probe distinguishes the two failure modes independently — i.e. it can report cases where qwen picks the *right* tool but *wrong* format, and vice-versa — so the finding attributes each defect to its own root cause and its own candidate fix lever.

3. **Test the candidate harness levers, measured, before committing to any.** For at least the two cheapest harness levers, run an A/B probe and record the delta:
   - **System-prompt / format instruction** (the 10.7.2 lever) — inject a qwen-specific instruction on *how* to emit a structured tool call and to *prefer* MailBot verbs; measure whether structured-`tool_calls` rate and correct-selection rate improve.
   - **Rescue-parser feasibility** (the 10.7.1 lever) — characterize the exact wire-shape of the `<tool_call>`-as-text emission (is it always well-formed JSON inside the tags? consistent tag delimiters? single vs. multiple calls?) enough to judge whether a deterministic content→`tool_calls` promotion parser is robust or brittle.
   - *(Optional / contingent)* surface-narrowing (the 10.7.3 lever) — only if AC-1/AC-2 suggest a mis-pickable peer (`send_message`) is the selection driver.

4. **Temp-0 argument-fidelity invariant is not silently traded away.** Any lever the finding recommends must be checked against the load-bearing temp-0 argument-fidelity property (`models.py:596-628`, the `ABC123→ABC132` corruption at non-zero temp). The finding explicitly states whether the recommended lever preserves exact argument round-trip or flags it as owed at implementation-walk time.

5. **Produce a recorded go/no-go finding with a recommended fix path.** A written spike-finding artifact (`10-7-0-spike-finding.md`, sibling to this story) records: the reproduced defects + their measurements; the SELECTION-vs-FORMAT attribution; the A/B lever deltas; and a **clear recommendation** — either **HARNESS-FIXABLE** (name which of 10.7.1 / 10.7.2 / 10.7.3 to fire, and whether any merge/drop) or **3B CEILING** (fire 10.7.4, swap to a bigger/better *local* $0 model), or **ESCALATE-TO-ADAM** (founding-assumption decision: bigger local vs. haiku-as-floor vs. GPU host at CP-1). This finding discharges Epic 10.7 done-flip clause 1.

6. **Cost thesis + safety framing preserved in the finding.** The recommendation keeps the local lane at **$0** (memory `project_local_model_is_safety_net` — even a model swap stays local, not a paid API floor) and notes that any downstream fidelity fix must not bypass the model-independent propose→grant→drain safety pipeline (F28 gate). No harness change proposed here weakens that pipeline (this spike touches no product code, so this is a framing check, not a regression risk).

## Tasks / Subtasks

- [x] **Task 1 — Build the probe harness in `scratch/` (spike scaffolding, never staged)** (AC: 1, 2) — `scratch/qwen_toolcall_spike_107.py` drives live `mailbot-ollama` qwen directly at temp 0; clean 5-toolset surface (find_emails + send_message peer + count_emails/get_sender_summary/schedule_cronjob); records the 4-cell {right/wrong}×{structured/text} outcome + `<tool_call>`-text wire capture.
  - [x] Author `scratch/qwen_toolcall_spike_107.py` — direct `ollama.AsyncClient` drive, `keep_alive=-1`, temp 0, bypassing Router/Hermes.
  - [x] Define the clean 5-toolset surface (find_emails right answer + send_message mis-pick peer).
  - [x] Harness records per-probe raw message, structured-tool_calls (FORMAT), selected name (SELECTION), `<tool_call>`-text detection (text-emission).
- [x] **Task 2 — Reproduce + isolate the two defects (baseline measurement)** (AC: 1, 2) — 5-tool stub: FORMAT did not reproduce (0/20), SELECTION 6/20 wrong (`count_emails`). **REAL 26-verb surface (post-CR re-run): SELECTION collapses 0/32 — `pull_pending_notifications` 100%.** FORMAT not reproduced on any direct-drive mode (0/152) — honestly scoped as not-reproducible-via-direct-drive, not proven absent under Hermes templating.
- [x] **Task 3 — A/B the cheapest harness levers, measured** (AC: 3, 4)
  - [x] **Lever B (system prompt):** STUB 14→20/20 BUT **real surface 0/N** (ablated + strong + persona-concat all 0/32; strong 0/12). The stub win was a small-surface artifact — system prompt is NOT the real-scale fix.
  - [x] **Lever A (rescue parser):** 0/152 direct-drive text emissions → feasibility unmeasured; kept defensive against the Hermes-template path only.
  - [x] **Temp-0 fidelity guard:** 3/3 exact (stub) — underpowered spot-check, real-N re-check OWED at 10.7.2.
  - [x] **Lever C / tool-description:** drop-send_message didn't help (stub); on real surface the mis-pick is `pull_pending_notifications` and even a natural-language `find_emails` description rewrite failed 0/16 → **10.7.3 surface-trim RE-OPENED** + tool-description work is the most promising cheap lever.
- [x] **Task 4 — Write the go/no-go spike finding** (AC: 5, 6) — `10-7-0-spike-finding.md` written: **HARNESS-FIXABLE**, fire-list = 10.7.2 primary + 10.7.1 defensive, drop 10.7.3, do-not-fire 10.7.4; temp-0 fidelity preserved; $0-cost + safety framing intact. Discharges Epic 10.7 clause 1.
- [x] **Task 5 — §5.12 self-audit (spike cadence; no product code → no MANDATORY-CR)** (AC: all) — no `mailbot_api/`/`hermes-config/` change; only `scratch/` scaffolding (gitignored) + 2 finding docs. Self-audit completed in `10-7-0.pre-review.md`; product-code posture checks N/A-with-justification.

### Review Findings

**Disposition summary (2026-07-15, post-review re-run):** the reviewer was RIGHT on the load-bearing point (#1) — I had tested only a 5-tool stub. Re-ran against the REAL 26-verb MCP surface: selection collapsed to 0/N (`pull_pending_notifications` 100%), the system-prompt lever's 20/20 was a small-surface artifact, and even a strong prompt + a `find_emails` description rewrite failed 0/N. **The finding's headline verdict was REVERSED accordingly** (`10-7-0-spike-finding.md` fully rewritten). Findings #1/#2/#4/#7/#9 → FIXED via the real-surface re-run + honest reframe. #3/#5/#6/#11 → FIXED (sample-size honesty language, N=turns×repeats caveat, regex finditer + malformed bucket, per-turn `tool picks` capture + run-log artifacts). #8 (do-not-fire softening) → FIXED (10.7.3 re-opened, 10.7.4 explicitly NOT closed). #10 (mixed-intent turns) → DEFER (belongs to 10.7.2 impl walk). Details inline below.

- [x] [Review][Decision] **[FIXED — verdict reversed] AC-1's "clean 5-toolset surface matching the 10.6.5 allow-list" is a cardinality mismatch, not a match — this undermines the finding's central "surface-coupled" attribution.** The real `platform_toolsets.discord` allow-list (`hermes-config/config.yaml:173-179`) is five MCP *toolset* names, and the config file's own comments state `mailbot-api` alone resolves to "the 26 email verbs" at turn time (plus messaging/cronjob/memory/clarify tools). The 10-6-5 walk that produced router_calls id=14937 ran against that full resolved surface (dozens of tools). The harness (`scratch/qwen_toolcall_spike_107.py:103-108`) instead hand-authors exactly 5 flat tool functions — one per toolset category. The finding's headline claim ("the `<tool_call>`-as-text emission... is Hermes/Router-surface-coupled, NOT an intrinsic qwen-3B behavior," `10-7-0-spike-finding.md` §1) and the "do-not-fire 10.7.4" / "10.7.1 demoted to belt-and-suspenders" recommendations all rest on this un-reproduced-therefore-surface-coupled inference — but the spike never tested anything resembling the real ~26+ tool surface, so 0/60 text-emission on a 5-tool stub does not license concluding the defect is absent from the model itself. Needs Adam's call: accept the inference as a reasonable spike-scope limitation (as the self-audit already partially flags at [LOW]/[MEDIUM]), or require a re-run against the real MCP-pulled tool list (`scratch/mcp_walk_106.py` pattern) before the fire-list is treated as final.
- [x] [Review][Decision] **[FIXED — reframed] AC-3's rescue-parser lever (10.7.1) was never actually measured — a null result (0/60 text emissions to parse) is reported as "feasibility characterized" alongside the system-prompt lever's real A/B delta.** AC-3 asks the spike to characterize the `<tool_call>`-as-text wire shape (well-formed JSON? consistent delimiters? single vs. multiple calls?) "enough to judge whether a deterministic content→tool_calls promotion parser is robust or brittle." The harness has the plumbing (`print_mode`'s `wellformed = sum(...)` check) but it never fires because zero text emissions occurred on direct-drive. The only real wire-shape evidence is the single historical walk sample (id=14937). Task 3's checkbox ("[x] Lever A (rescue parser): ... feasibility framed") and the finding's AC-3 completion note both present this as a discharged deliverable rather than a gap. Needs Adam's call on whether 10.7.1's scope/fire decision should wait for a wire-shape sample pulled from replaying the real Hermes-surface conditions.
- [x] [Review][Decision] **[FIXED — caveated + owed] AC-4's temp-0 argument-fidelity check (3/3 exact) is not statistically capable of confirming the invariant against the story's own cited baseline.** The story's Dev Notes cite the AI-1 probe's finding of ~79-90% exact-match (i.e., 10-21% SILENT CORRUPTION rate) on adversarial/realistic Graph ids at temp 0. A 3-sample check has roughly a 27-49% chance of missing a true ~10-20% failure rate entirely (i.e., seeing 3/3 clean by chance). The finding states the invariant is "PRESERVED" (`10-7-0-spike-finding.md` §3) without a sample-size caveat or a call to re-test at comparable N to the AI-1 baseline. Needs Adam's call: accept 3/3 as a go/no-go-adequate spot-check (with the residual risk explicitly flagged as owed at 10.7.2 implementation time), or require the fidelity re-check to scale to something closer to AI-1's N before AC-4 is considered discharged.
- [x] [Review][Decision] **[FIXED — both re-opened] The do-not-fire verdicts for 10.7.3 (surface trim) and 10.7.4 (model swap) are permanent-deprioritization conclusions drawn from a single-run, small-N delta and the unverified surface-coupling assumption above.** 10.7.3's "measured NOT to help" rests on droppeer's 15/20 vs baseline's 14/20 (a one-sample flip, not a stable delta.) 10.7.4's "No 3B ceiling found" is entirely downstream of the FORMAT-defect-is-surface-coupled inference (Review Finding #1) — if that inference doesn't hold under the real surface, "no 3B ceiling" doesn't follow either. Needs Adam's call on whether to soften these to "no evidence found at this N" (leaving the door open) vs. accepting the current hard "do-not-fire" framing as-is for epic sequencing purposes.
- [x] [Review][Patch] **[FIXED — sample-size honesty block added to finding]** N=20 per mode is 4 independent turns × 5 deterministic (temp=0) repeats, not 20 independent trials — the finding's headline ratios (14/20, 20/20, "0/60 text-emission across all modes") and the word "DECISIVE" for the sysprompt lever should be reframed to make clear the real sample size is 4 (or 12 across 3 modes), with the repeats noted as drift-confirmation only, not additional evidence. [`_bmad-output/implementation-artifacts/10-7-0-spike-finding.md`, `scratch/qwen_toolcall_spike_107.py:217-232`]
- [x] [Review][Patch] **[FIXED in harness]** `TOOL_CALL_TEXT_RE.search()` only detects a single well-formed `<tool_call>{json}</tool_call>` block (no `.finditer()`, no handling of malformed/partial/unwrapped-JSON text emissions), and malformed JSON caught by the `except (ValueError, TypeError)` branch is aliased to the sentinel `"<malformed-json>"` which then flows into the `wrong_text` bucket in `cells()` — conflating "wrong tool selected" with "syntactically broken output" and silently undercounting any FORMAT-defect shape that isn't the one exact pattern anticipated. [`scratch/qwen_toolcall_spike_107.py:45`, `:199-205`, `:467-476`]
- [x] [Review][Decision] **[FIXED — ablation run; moot at real scale]** `SYSTEM_PROMPT_LEVER_B` explicitly enumerates the three "right" tool names and explicitly excludes `send_message` by name** (`scratch/qwen_toolcall_spike_107.py:120-126`) — closer to answer-leaking than a general format/selection-hygiene instruction, especially since the actual observed baseline confusion was `find_emails` vs. `count_emails` (not `send_message`). The 20/20 result may be partly attributable to the explicit exclusion rather than to resolving the real find/count ambiguity the spike itself identified as the driver. Needs Adam's call on whether 10.7.2's production system prompt should be validated against this specific confound (e.g., an ablation dropping the explicit tool enumeration) before being treated as the primary load-bearing fix.
- [x] [Review][Patch] **[FIXED — persona-concat modes run (realsurface_persona / realsurface_sysprompt), both 0/32]** The sysprompt lever was validated as the sole system message; the real Router path concatenates ALL system messages with `"\n\n"` (`mailbot_api/router/router.py:2442-2459`), including SOUL.md/AGENTS.md/SKILL.md persona blocks per the F14 guard the story itself names as an open risk ("the Router adds the F14 system-prepend, which must not clobber the instruction" — `10-7-0-spike-finding.md` §4.1). Re-run the sysprompt probe with representative persona boilerplate concatenated ahead of the candidate instruction to test survival under realistic concatenation, rather than leaving this purely as a prose caveat for the 10.7.2 implementation walk to discover.
- [x] [Review][Defer] **[DEFER — to 10.7.2 impl walk, agreed]** No turns beyond the 4 near-identical unread-email paraphrases were tested — no multi-intent turn, no turn where `send_message` is legitimately correct (e.g. "email me a summary" / "let the team know"), so the blanket "never send_message" instruction's effect on legitimately-mixed intents is untested. Deferred to the 10.7.2 implementation walk's own validation pass rather than blocking this spike's finding. [`scratch/qwen_toolcall_spike_107.py:426-431`]
- [x] [Review][Defer] **[FIXED — superseded: real mis-pick is `pull_pending_notifications`, and 10.7.3 surface-trim is now RE-OPENED as a live lever]** Lever C (`droppeer`) tests dropping `send_message`, but the harness's own per-turn detail output shows the actual observed confusion is `find_emails` ↔ `count_emails` (a sibling MailBot verb), not the messaging peer — so Lever C measured the wrong candidate for the residual it was trying to explain. The finding's own prose already notes this ("the residual mis-pick is a sibling MailBot verb, not the messaging peer"), so this is recorded as a methodology gap for a future iteration rather than blocking this spike's verdict. [`scratch/qwen_toolcall_spike_107.py:103-108`]
- [x] [Review][Defer] **[FIXED — run logs captured on-disk in scratch/ (gitignored): 10-7-0-realsurface-run.log / -strong.log / -betterdesc.log + 10-7-0-tool-descriptions.txt; each mode now prints a `tool picks:` line]** No raw run transcript/log output is captured anywhere in the story's deliverables (File List has no log artifact) — the reported counts (14/20, 20/20, 15/20, 3/3) are asserted in prose with no captured stdout to verify against, despite the Appendix providing reproduce commands. Deferred as a reproducibility-hygiene note rather than a blocker, since the commands are documented and the model/harness are still live for re-verification.

## Dev Notes

### What this story is (and is NOT)

- **IS:** a measurement spike. Deliverables = (1) a reusable probe harness in `scratch/` (never staged), (2) a recorded go/no-go finding doc that gates the rest of Epic 10.7. Mirrors the 10.6.4 `num_ctx` discipline: characterize the root cause before committing to a fix.
- **IS NOT:** a product-code change. No edits to `mailbot_api/`, no adapter/router/dispatch changes, no `hermes-config/` change. Those are 10.7.1–10.7.4, *shaped by this finding*. Because there is no product code, there is **no MANDATORY-CR** — only the §5.12 self-audit (epics.md § Epic 10.7 table).

### The two defects, grounded in code (2026-07-15 recon, read-only)

- `OllamaAdapter.call_with_tools` (`mailbot_api/router/models.py:586-749`) decides tool-call presence **solely** from structured `message["tool_calls"]` (`:700`, `:733-738`); `message.content` is captured only as `text` (`:691`). **No `<tool_call>`-as-text parser exists anywhere in `mailbot_api/`** (grep-verified) — this is the mechanism behind `tool_calls_count=0` when qwen emits the call as text.
- `tool_calls_count` is recorded to `router_calls` at `router.py:2514` as `len(tool_response.tool_calls)`; `0` (not NULL) = "a tool-call dispatch that produced no calls."
- **No system prompt / tool-format / selection instruction is injected on the qwen tool-call path** — `main.py` forwards the client's messages/tools verbatim; `router.py:2442-2459` only concatenates system messages the client already sent; the adapter adds no format guidance. Insertion seams for 10.7.2: `main.py:760-848` or `router.py:2442-2459`.
- **Temperature 0 is already load-bearing** for argument fidelity (`models.py:596-628`). Selection/format failures persist *despite* temp 0 — so turning temp down further is NOT the lever, and any harness lever must not raise temp (AC-4).
- Existing tool-call test surface `tests/unit/router/test_ollama_adapter.py` feeds only **structured** `tool_calls`; `test_call_with_tools_text_only_response` (`:301`) asserts empty for a content-only response but does not parse `<tool_call>` text — the gap 10.7.1 would fill.

### The defect evidence this spike must reproduce (F-10-6-5-W1)

From the 10-6-5 walk (surface already CLEANED — built-ins + skills dropped, allow-list = `[mailbot-api, messaging, cronjob, memory, clarify]`): `router_calls id=14937, tool_calls_count=0` — qwen picked `send_message` (from `messaging`) and emitted the call as literal `<tool_call>` **text**. This is the *residual after* the surface fix, which is why it is a model/harness-fidelity problem (Adam D1 reassigned Epic 10.6 clause 3b here), not a surface defect. Contrast (WALK-10-6-4-F1): when the agent-driven endpoint supplied its OWN correct 4-tool surface directly, `tool_calls_count=1`, `find_emails` picked at 1.7–4.9s — so the model *can* do it under some conditions; the spike must find which.

### Harness / methodology (reuse prior art)

- **AI-1 probe pattern** (`AI-1-local-tool-caller-verify-or-restore.md`): direct HTTP/SDK drive of live `mailbot-ollama`, temp 0, argument-fidelity sweeps (6/6 exact short ids; ~79–90% on adversarial/realistic Graph ids, failure mode = SILENT CORRUPTION). That probe validated *argument* fidelity; THIS spike extends the same rig to *selection* + *format* fidelity.
- **`scratch/mcp_walk_106.py`** — the live-MCP-session pattern against `http://localhost:8000/mcp/` (list tools, call tools). Reuse for pulling the real `find_emails` / messaging tool schemas if the probe wants exact shapes rather than hand-authored stubs.
- **Live env note (WALK-10-5-4-F1):** `scripts/` + adapter code are bind-mounted; drive the REAL running `mailbot-ollama` inference surface, not a mock — the whole point is characterizing the real model.

### Architecture compliance

- Rule I: the Router is the only production code that may call Ollama/Anthropic adapters. This spike's probe lives in `scratch/` (test scaffolding, boundary-exempt, never staged) and drives ollama directly to isolate the MODEL from the Router/Hermes layers — this is legitimate spike methodology, not a Rule-I violation of production code (no `mailbot_api/` file is added or changed).
- Model: `qwen2.5:3b-instruct-q4_K_M`, 3B / Q4_K_M, served by the `mailbot-ollama` container (architecture.md:71,133,669).
- Temp-0 invariant (`models.py:596-628`) is load-bearing and must be respected by the probe and any recommended lever (AC-4).

### Cost + safety framing (memory)

- `project_local_model_is_safety_net` — the local lane is the $0 floor gated by action *reversibility*, not mode. A model-swap recommendation (10.7.4) stays LOCAL/$0; escalation to a paid floor is an Adam founding-assumption decision, never a dev auto-resolve.
- `project_reached_not_equal_usable` — this spike is the sharpest instance: routed + fast + tools-on-surface, but STILL not usable because the model won't fire the right structured call. Clause 3 ("faithful tool invocation REACHED") is the load-bearing done-flip gate = Epic 10.6 clause 3b.

### Testing requirements

- This is a spike: the "test" is the **reproducibility of the probe measurements**, not a pytest suite addition. No new tests are added to `tests/` (that surface is 10.7.1's, which fills the `<tool_call>`-text-parse gap). Repo gates (ruff/mypy/pytest) must still be GREEN at close since no product code changed — confirm the baseline suite is unperturbed.
- `scratch/` is excluded from ruff + mypy and gitignored (Story 10-6-3) — the probe harness lives there and is never staged.

### References

- epics.md § Epic 10.7 Detail (lines 4343-4391) — epic charter, the two defects, code recon, 4-clause done-flip gate, sequencing (spike gates all).
- sprint-status.yaml:370-377 — Epic 10.7 roster + this story's HIGHEST/gating marker.
- `AI-1-local-tool-caller-verify-or-restore.md` — prior probe methodology (direct ollama drive, temp-0 fidelity sweep) this spike extends.
- `WALK-10-6-4-F1-hermes-tool-surface-pollution.md` — the surface-pollution walk that isolated selection from surface; the clean-surface contrast.
- `mailbot_api/router/models.py:586-749` — `OllamaAdapter.call_with_tools`, the structured-only tool-call read (defect mechanism).
- `mailbot_api/router/router.py:2514` — `tool_calls_count = len(tool_response.tool_calls)`.
- `scratch/mcp_walk_106.py` — live MCP session pattern for pulling real tool schemas.
- Memory: `project_local_model_is_safety_net`, `project_reached_not_equal_usable`, `project_qwen_cpu_toolcall_latency`, `feedback_reviewer_model_substitution`.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (dev, autonomous-story-run inline dev walk)

### Debug Log References

- Live stack confirmed up: `mailbot-ollama` (8 days, healthy, :11434), `mailbot-api` (:8000). Probe drove ollama directly from host.
- Baseline N=20: right+structured 14 / wrong+structured 6 / text-emission 0. Sysprompt N=20: 20/0/0. Droppeer N=20: 15/5/0.
- Per-turn detail exposed the mis-pick as `count_emails` (sibling verb), NOT `send_message` — refines the walk's `send_message` framing (that was surface-coupled).
- Temp-0 arg fidelity under sysprompt: 3/3 exact incl. `AAMkAD00-9f3b-msg-44172`.
- `importlib` load of the harness for an ad-hoc detail run failed on the `field(default_factory=)` dataclass under a synthetic module name → added a first-class `detail` mode to the script instead.

### Completion Notes List

**IMPORTANT — the finding was REVISED after MANDATORY code-review.** The reviewer (sonnet-5 ≠ dev opus-4-8) correctly flagged that the initial pass tested only a 5-tool STUB, not the real 26-verb MCP surface, and over-inferred "surface-coupled → no 3B ceiling." Re-running against the real surface **reversed the headline verdict.** Both the initial and corrected results are preserved below.

- **AC-1 (reproduce defects):** On the 5-tool stub: SELECTION partially reproduced (6/20 wrong), FORMAT did not. **On the REAL 26-verb surface: SELECTION collapses to 0/N — qwen picks `pull_pending_notifications` 100% of the time** (32/32, 32/32, 32/32 across 3 modes; 12/12 strong prompt; 16/16 desc-rewrite). FORMAT (`<tool_call>` text) did not reproduce on any direct-drive mode (0/152) — honestly scoped as "not reproducible via direct ollama drive," NOT proven absent from the model under Hermes templating.
- **AC-2 (isolate SELECTION from FORMAT):** SELECTION is the load-bearing defect and is SEVERE at real scale; root cause = `find_emails`'s jargon-first description ("email projections matching filter, Rule J") + a dominant `pull_pending_notifications` distractor ("Pull… urgent notifications"). FORMAT = plausibly Hermes-template-coupled but unproven.
- **AC-3 (A/B levers, measured):** system prompt 14→20/20 on the STUB but **0/N on the real surface** (both ablated + strong) — the stub win was a small-surface artifact. Tool-description rewrite tested (0/16, attractor still dominates). Surface-trim RE-OPENED. Rescue-parser feasibility unmeasured (no direct-drive text).
- **AC-4 (temp-0 fidelity not traded):** 3/3 exact where selection succeeded (stub); explicitly caveated as an underpowered spot-check (cannot confirm vs AI-1's ~10-20% adversarial corruption) — a real-N re-check is OWED at 10.7.2 impl time.
- **AC-5 (go/no-go finding):** `10-7-0-spike-finding.md` (rewritten) — verdict **HARNESS-FIXABLE IN PRINCIPLE but NOT by the cheap system-prompt lever; the load-bearing defect is SELECTION-at-scale.** Required next step: a combined description + surface-scoping experiment on the real surface. Fire-list: RE-OPEN 10.7.3 + tool-description work (most promising), DEMOTE 10.7.2 to one ingredient, KEEP 10.7.1 defensive, **DO NOT CLOSE 10.7.4** (3B ceiling not ruled out). Discharges Epic 10.7 clause 1 (a legitimate go/no-go outcome — measure-before-fix caught the cheap lever's insufficiency).
- **AC-6 ($0 + safety framing):** local lane stays $0 (every lever incl. a possible model swap stays local); no product code changed so propose→grant→drain (F28) pipeline unperturbed.
- **No product code:** no `mailbot_api/` or `hermes-config/` change. Deliverables = `scratch/` probe harness + run logs (gitignored, never staged) + 2 artifact docs (finding + pre-review). No MANDATORY-CR (spike, §5.12 self-audit) but a review pass ran and materially improved the finding.
- **Gates:** repo suite/ruff/mypy GREEN + UNCHANGED from baseline (no product code touched) — pytest 1941, ruff clean; see Change Log.
- **Clause 3 NOT yet de-risked:** contrary to the initial pass, the spike does not give confidence a system prompt yields a faithful qwen `find_emails` call on a real turn — it shows the opposite at real scale.

### File List

- `_bmad-output/implementation-artifacts/10-7-0-characterization-spike-harness-vs-3b-ceiling.md` (this story file — new)
- `_bmad-output/implementation-artifacts/10-7-0-spike-finding.md` (go/no-go finding — new)
- `_bmad-output/implementation-artifacts/10-7-0.pre-review.md` (§5.12 self-audit — new)
- `scratch/qwen_toolcall_spike_107.py` (probe harness — new, **NOT staged**; scratch/ is gitignored + ruff/mypy-excluded per Story 10-6-3)
- `scratch/10-7-0-realsurface-run.log`, `scratch/10-7-0-realsurface-strong.log`, `scratch/10-7-0-realsurface-betterdesc.log`, `scratch/10-7-0-tool-descriptions.txt` (run-evidence artifacts — new, **NOT staged**, gitignored; on-disk for verification)
- No source files modified — characterization spike, no product code.

### Change Log

- 2026-07-15 (initial) — Characterization spike executed against live local qwen on a 5-tool stub. Initial verdict HARNESS-FIXABLE (system prompt 14→20/20).
- 2026-07-15 (REVISED post-CR) — Reviewer (sonnet-5≠opus-4-8) flagged the 5-tool-stub over-inference. Re-ran on the REAL 26-verb MCP surface: selection collapses 0/N (`pull_pending_notifications` 100%), the stub's 20/20 was a small-surface artifact, strong prompt + description rewrite also 0/N. **Verdict REVERSED:** load-bearing defect is SELECTION-at-scale; cheap system-prompt lever insufficient; RE-OPEN 10.7.3 + tool-description work; DO NOT CLOSE 10.7.4. Clause 3 not yet de-risked. All 11 CR findings dispositioned (10 FIXED/reframed, 1 DEFER). Discharges Epic 10.7 clause 1.
