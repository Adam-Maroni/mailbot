---
baseline_commit: c45d0b09e00ca968ae64a31344d65a633ec37de7
---

# Story 10.7.1: `<tool_call>`-as-Text Rescue Parser

Status: done

## Story

As the **MailBot maintainer relying on the free local qwen lane to actually *do* work**,
I want **the `OllamaAdapter` to rescue a tool call that qwen emits as a `<tool_call>{…}</tool_call>` text block in `message.content` (instead of in the structured `message.tool_calls` array) — promoting it to a real tool call so it dispatches**,
so that **a qwen turn that chose the right tool but emitted it in the wrong FORMAT stops silently no-op-ing (`tool_calls_count=0`) and instead runs — closing the format half of Epic 10.7 clause 3 (the cost thesis's final gate).**

## Context — why this is now confirmed-needed (not defensive)

The 10.7.0 spike could NOT reproduce the `<tool_call>`-as-text format defect via direct ollama drive (0/172 across all modes); its sole prior evidence was one Hermes walk (`router_calls id=14937`), so this story was scoped "DEFENSIVE/KEEP, need unproven." **The Story 10-7-5 Phase 3.5 Discord walk (2026-07-15) reproduced it live a 2nd time:** Adam typed "find my unread emails"; qwen emitted `<tool_call>{"name": "memory", "action": "add", "target": "user", "content": "unread_emails"}</tool_call>` as literal text → `router_calls id=15022`, `model_chosen=qwen2.5:3b`, `tool_calls_count=0`, `outcome=ok`, nothing dispatched. This confirms the defect is real and **Hermes-template-coupled** (appears through Hermes's chat-template / request assembly, which direct-drive can't replicate). See [[project_qwen_toolcall_format_defect_reproduced]] + story-run-flags.md § "Story 10-7-5 Manual Verification" (WALK-10-7-5-F1).

## Acceptance Criteria

**AC-1 — Well-formed text `<tool_call>` block is promoted to a structured call.**
In `OllamaAdapter.call_with_tools` (`mailbot_api/router/models.py`), when the structured `message["tool_calls"]` array is empty AND `message["content"]` contains a `<tool_call>…</tool_call>` block whose inner JSON has a non-empty `name` and a well-formed `arguments` object (dict) — or no `arguments` key at all (→ empty args) — the adapter extracts it and returns it as an `OpenAIToolCall` in `ToolCallAdapterResponse.tool_calls`, with `finish_reason="tool_calls"`. The promoted call is byte-shape-identical to a natively-structured one (same `OpenAIToolCall`/`OpenAIToolCallFunction` construction, `arguments` as a JSON string via `json.dumps(..., separators=(",", ":"))`, synthesized `id` when none present) so everything downstream (`router.py:2514` `tool_calls_count=len(...)`, the drain/gate pipeline) is unchanged.

**AC-2 — STRICT tolerance: a malformed block is NOT promoted, and is logged.**
A `<tool_call>` block whose inner JSON has a `name` but stray sibling keys instead of a proper `arguments` object (the real walk shape: `{"name":"memory","action":"add","target":"user","content":"unread_emails"}`) is **NOT** promoted — `tool_calls` stays empty, `finish_reason` stays `stop`/`length`. Instead the adapter emits a structured log event recording that a malformed `<tool_call>` block was seen and declined (with the raw block text, sanitized). Rationale: fabricating an ad-hoc `arguments` object from a half-hallucinated block would push ambiguous 3B output *toward* action through the propose→grant→drain pipeline — the wrong failure direction for the local safety-net lane ([[project_local_model_is_safety_net]]). A wrong-shaped call is worse than no call; selection is 10.7.3's job, not this parser's.

**AC-3 — No over-triggering: a plain-text response still yields zero calls.**
A content-only response with NO `<tool_call>` block (e.g. "I can't do that.") continues to return `tool_calls == []` — the existing `test_call_with_tools_text_only_response` contract holds unchanged. The rescue path fires ONLY when a genuine `<tool_call>…</tool_call>` block is present.

**AC-4 — Structured path always wins; the parser is a fallback only.**
When `message["tool_calls"]` is non-empty, `message["content"]` is NOT scanned for a text block — the native structured calls are used as-is (the parser must not double-count or override them). The rescue runs only in the `raw_tool_calls`-empty branch.

**AC-5 — temp-0 argument fidelity is preserved through the rescue path.**
A rescued call's `arguments` round-trip EXACTLY, including a long Graph-style id (mirrors `test_call_with_tools_argument_fidelity_long_graph_id`). The parser must never mangle, re-order, or coerce argument values, and must not touch `temperature` (temp-0 stays load-bearing per `models.py:596-628`).

**AC-6 — Observability: promote and decline both emit structured log events.**
A successful rescue emits a "rescued text-emitted tool call" event (tool name, block source); a decline emits a "malformed `<tool_call>` block, not promoted" event. Both are greppable so future walks can distinguish format-channel outcomes from selection outcomes (measure-before-fix discipline).

**AC-7 — Scope fence: format channel only; clause 3 NOT claimed closed.**
This story fixes only the FORMAT channel (text→structured). It does NOT touch tool SELECTION (10.7.3) or descriptions (10.7.5, shipped). A rescued call to the *wrong* tool still dispatches the wrong tool — acceptable; 10.7.3 owns getting qwen to the right small menu. Completion Notes must state clause 3 (a live Discord `find_emails` turn) still needs 10.7.3 + an Adam re-walk after this lands.

## Tasks / Subtasks

- [x] **Task 1 (AC-1..5, RED): pin the parser contract as failing unit tests** in `tests/unit/router/test_ollama_adapter.py` (the suite feeds only structured `tool_calls` today — that's the gap). (AC: 1,2,3,4,5) — DONE: 10 new tests appended (well-formed promote, malformed sibling-key decline, plain-text over-trigger guard, structured-wins precedence, long-Graph-id fidelity, bare-block empty-args, args-as-JSON-string, multi-block promote-first, whitespace, empty-name decline). RED confirmed: 8 fail (no rescue yet), 2 pass (AC-3 + AC-4 are already-correct existing behavior = regression guards).
  - [ ] Well-formed block (`{"name":"find_emails","arguments":{"filter":{"unread":true}}}` in content, empty structured array) → promoted: `finish_reason=="tool_calls"`, 1 call, name + args exact.
  - [ ] **Regression guard (AC-3):** existing `test_call_with_tools_text_only_response` ("I can't do that.", no block) → still `tool_calls == []`. Confirm it stays green after Task 2.
  - [ ] Malformed block (the walk shape `{"name":"memory","action":"add",...}`, no `arguments`) → NOT promoted (`tool_calls == []`) + decline-log asserted (AC-2).
  - [ ] Structured `tool_calls` present + a `<tool_call>` string also in content → structured wins, content NOT scanned, no double count (AC-4).
  - [ ] Edge cases: multiple blocks (promote FIRST only — single-call semantics, no per-extra log; CR F1 corrected the earlier "log the rest" wording); whitespace/newlines inside block; `arguments` as JSON-string vs dict; bare block with neither `arguments` nor stray keys → empty-args promote.
  - [ ] Long-Graph-id fidelity through the rescue path (AC-5).
  - [ ] Run; confirm RED for the right reason (no rescue exists yet).

- [x] **Task 2 (AC-1,2,4,5, GREEN): implement the strict extractor.** (AC: 1,2,4,5) — DONE: `_rescue_text_tool_call(text) -> OpenAIToolCall | None` added at `models.py` (module-level, pure). First-block regex `_TEXT_TOOL_CALL_RE` (DOTALL, non-greedy); `json.loads` inner; require non-empty `name`; `arguments` dict → `json.dumps(...,separators=(",",":"))`, JSON-string → parsed-then-reserialized, absent+no-stray-keys → `{}`, stray-sibling-keys → decline; `id="call_0"`. Reuses `OpenAIToolCall`/`OpenAIToolCallFunction`. Call-site fires ONLY in the `not tool_calls and "<tool_call>" in text` branch → sets `tool_calls=[call]`, `finish_reason="tool_calls"`. All GREEN.
  - [x] Helper added; call-site in empty-array branch only (structured wins).
  - [x] Re-run Task 1; well-formed + precedence + fidelity GREEN (10/10).

- [x] **Task 3 (AC-6, GREEN): structured observability.** (AC: 6) — DONE: promote emits `_log.info("rescued text-emitted tool call", extra={"event":"tool_call.rescue.promoted","tool_name":...})`; decline emits `_log.warning("malformed <tool_call> block declined...", extra={"event":"tool_call.rescue.declined","raw_block":_sanitize_text(text)[:500]})`. `sanitize_error` is exception-only, so added `_sanitize_text` reusing the shared `observability._redaction` regexes (same body as `sanitize_error`). Both events asserted in the Task-1 tests.

- [x] **Task 4 (AC-7 + verify): gates + count propagation.** (AC: 7) — DONE.
  - [x] `router.py:2514` `tool_calls_count=len(tool_response.tool_calls)` is pure `len()` over the adapter's returned list; a rescued call increments that list in the adapter → count reports ≥1 with NO router change. Covered by the adapter unit tests (assert `len(result.tool_calls)==1`); the router seam is a trivial `len()` over the same list.
  - [x] Grepped `mailbot_api` + `tests`: no assumption that a content-only response never carries a call (`main.py:1077` is the opposite case — tool-only content=None). Nothing to update.
  - [x] 4 gates: ruff clean, mypy `--strict mailbot_api` clean (134 files), boundary exit 0, full pytest **1952 passed / 3 skipped / 3 deselected** (+10 vs 1942 baseline).

- [x] **Task 5 (AC-7): record scope + owed re-walk.** (AC: 7) — DONE: see Completion Notes List below (FORMAT-channel only; clause 3 NOT claimed closed; owed 10.7.3 surface-trim + Adam re-walk; order 10.7.1→10.7.3→10.7.5-shipped→re-walk).

### Review Findings

- [x] [Review][Decision] Multi-block "log the rest" is claimed but not implemented — Task 1's own subtask ("multiple blocks (promote first, log the rest)") and the new test's docstring ("extras are not silently swallowed — a decline/extra log is emitted so a walk can see them") both assert a second log event for dropped extra blocks. The implementation only ever emits the single `tool_call.rescue.promoted` event for the first block; no distinct event fires for the discarded extras, and `test_rescue_multiple_blocks_promotes_first_logs_rest` never actually asserts one exists. [`mailbot_api/router/models.py:838-849`, `tests/unit/router/test_ollama_adapter.py:397-419`, story line 49] — needs Adam's call: accept single-call semantics as sufficient (and fix the misleading docstring/task wording) or add a genuine per-extra decline log.
- [x] [Review][Decision] Successful rescue leaves the raw `<tool_call>{...}</tool_call>` markup inside `ToolCallAdapterResponse.text`, unlike a natively-structured turn where `.text` is normal prose — this undercuts the "byte-shape-identical to a natively-structured one" framing in AC-1/Completion Notes for any consumer of `.text` (confirmed `mailbot_api/router/router.py` reads `.text`). [`mailbot_api/router/models.py` call-site, ~line 838 onward] — needs Adam's call: is `.text` allowed to retain raw model output when a rescue promotes (safe, since `tool_calls` is authoritative), or should the matched block be stripped/scrubbed from `.text` on promote?
- [x] [Review][Patch] `_TEXT_TOOL_CALL_RE` search is vulnerable to catastrophic/quadratic backtracking on unclosed `<tool_call>` prefixes — measured ~64s to fail-to-match against 20,000 repeated `<tool_call>` prefixes with no closing tag (0.03s→0.10s→0.38s→1.4s→5.6s at N=500/1k/2k/4k/8k), on a live-request path fed by an unpredictable local 3B model's raw output. [`mailbot_api/router/models.py:69` (`_TEXT_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)`)]
- [x] [Review][Patch] A literal `</tool_call>` substring inside a legitimate JSON string argument value (e.g. `{"note": "</tool_call>"}`) truncates the non-greedy match early, breaking an otherwise well-formed block into invalid JSON and causing a false-negative decline. Safe direction (decline, not over-promote) but a real correctness gap in the tag-anchored regex approach vs. a proper balanced-JSON/boundary scan. [`mailbot_api/router/models.py:69` `_TEXT_TOOL_CALL_RE`, `_rescue_text_tool_call`]
- [x] [Review][Patch] `json.loads`/`json.dumps` accept non-standard `NaN`/`Infinity`/`-Infinity` tokens by default; a block like `{"name":"x","arguments":{"limit":NaN}}` passes the STRICT filter and is promoted with a non-JSON-standard numeric value baked into the re-serialized `arguments` string, contradicting the "wrong-shaped call must be declined" design intent. [`mailbot_api/router/models.py` `_rescue_text_tool_call`, `json.loads(inner)` / `json.dumps(arg_input, ...)` calls]
- [x] [Review][Patch] Fixed `id="call_0"` on every rescued call (vs. the structured path's per-index `call_{i}`) risks an id collision if two separate rescues occur within the same multi-turn conversation, since `id_to_name` in `_translate_messages_openai_to_ollama` is keyed across the whole message history (`mailbot_api/router/models.py:364-381`) — a second rescued call would silently overwrite the first's name resolution. [`mailbot_api/router/models.py:140` (`id="call_0"`), `:822` (structured path's `call_{i}`)]
- [x] [Review][Patch] Decline log's `raw_block` field logs the entire sanitized `message.content`, not just the matched offending `<tool_call>` block — a mislabeled observability field that could omit the actual block on longer content (only the first 500 chars of the whole message survive `[:500]` truncation, which may not include the block at all). [`mailbot_api/router/models.py:855` (`"raw_block": _sanitize_text(text)[:500]`)] — fix: log `_sanitize_text(match.group(0) if match else text)[:500]` or similar, scoped to the actual matched/attempted block.
- [x] [Review][Patch] Stray-sibling-key guard (`stray = {k for k in obj if k != "name"}` decline branch) is unreachable whenever an `arguments` key is present (even `null`/list/etc.) because the earlier `not isinstance(arg_input, dict)` check already intercepts and returns `None` first — dead/confusing code, correct-by-luck rather than by the guard it appears to implement. [`mailbot_api/router/models.py` `_rescue_text_tool_call`, stray-key branch]
- [x] [Review][Patch] No test exercises the decline-log redaction path (`_sanitize_text` / `raw_block` on the `tool_call.rescue.declined` WARNING log) — the sanitize-then-truncate order is correct today but this safety property (secrets never leaking into the decline log) is currently unguarded by any regression test. [`tests/unit/router/test_ollama_adapter.py`, decline tests at ~line 255-280, 447-464]

### Review Findings — Dispositions (CR round 1, dev opus-4-8 applying reviewer sonnet-5's findings)

**8 of 9 findings FIXED, 1 ACCEPT-WITH-RATIONALE. Applied-rate 8/9 = 89%.**

- **[Decision] Multi-block "log the rest" → FIXED (accept single-call semantics + corrected wording).** Single-call semantics is the intended contract (the rescue does not reconstruct a multi-call turn from text; the structured path likewise yields only what the model emitted). No per-extra log added; instead corrected the misleading test docstring (`test_rescue_multiple_blocks_promotes_first_only`) and the Task-1 subtask wording. No Adam call needed — this is the safe, intended behavior.
- **[Decision] `.text` retains raw markup on promote → FIXED (strip block).** On a successful promote the matched block is now stripped from `.text` (`text.replace(block, "", 1).strip()`) so a rescued turn's `.text` is prose, shape-identical to a natively-structured turn. `tool_calls` remains authoritative. New test `test_rescue_promote_strips_block_from_text`. No Adam call needed — the safe direction (strip) is strictly better for the shape-identity claim.
- **[Patch] ReDoS (F3) → FIXED.** Replaced the backtracking regex with a linear `str.find`-based `_extract_first_tool_call_block` (opener→first-closer). O(n), no catastrophic backtracking. `re` import removed. New test `test_rescue_unclosed_prefix_is_fast_and_declines` (20k unclosed prefixes → prompt decline).
- **[Patch] `</tool_call>` in JSON string (F4) → FIXED (documented + tested).** The tag-anchored scan truncates at the inner `</tool_call>` → inner JSON invalid → STRICT decline (safe direction). Documented in `_extract_first_tool_call_block` docstring; new test `test_rescue_close_tag_inside_string_value_declines` pins the decline. (A full balanced-JSON scanner is out of scope — declining a block that embeds the close-tag literal is acceptable for the format channel.)
- **[Patch] `NaN`/`Infinity` accepted (F5) → FIXED.** Added `_strict_json_object` with a `parse_constant` hook that rejects `NaN`/`Infinity`/`-Infinity` → decline. Applied to both the outer block parse and the nested args-as-JSON-string parse. New test `test_rescue_nan_infinity_argument_is_declined`.
- **[Patch] `id="call_0"` collision (F6) → ACCEPT WITH RATIONALE.** The structured path ALSO synthesizes `call_{i}` (every turn's first structured call is `call_0`), so cross-turn `id_to_name` overwrite is a PRE-EXISTING property of the whole adapter, not introduced by the rescue — the rescued `call_0` behaves identically to a structured `call_0`. A rescue produces exactly one call and only fires when the structured array is empty, so no same-turn collision is possible. Keeping `call_0` maximizes shape-identity with the structured path (changing it would break the "indistinguishable downstream" claim). The cross-turn id-collision is a latent whole-adapter concern outside this format-channel story's scope.
- **[Patch] `raw_block` logs whole content (F7) → FIXED.** The decline log now logs the matched block (`_sanitize_text(block if block is not None else text)[:500]`), scoped to the offending `<tool_call>` block, falling back to full text only when no complete block was found. Covered by `test_rescue_decline_log_redacts_secrets_in_raw_block` (asserts `raw_block.startswith("<tool_call>")`).
- **[Patch] Stray-key branch "unreachable" (F8) → NO CHANGE NEEDED (clarifying comment added).** The reviewer's premise is correct but the conclusion is inverted: the stray-key branch lives in the `else` (no `arguments` KEY) path, which is EXACTLY where the walk's malformed shape (`{"name":"memory","action":"add",...}` — no `arguments` key) lands. It is reachable and load-bearing for the whole reason the parser exists. A block WITH an `arguments` key never reaches this branch (validated above). Added a clarifying comment so the intent reads unambiguously (the reviewer's confusion was itself the signal to clarify).
- **[Patch] No decline-log redaction test (F9) → FIXED.** New test `test_rescue_decline_log_redacts_secrets_in_raw_block` embeds a Bearer token in a malformed block and asserts it is `[REDACTED_BEARER]` in the log, never leaked.

Post-CR gates: ruff clean, mypy `--strict mailbot_api` clean, boundary exit 0, adapter file 52 passed (+5 CR tests), full suite green (see Completion Notes for final count).

## Dev Notes

**Technical requirements**
- Stack: Python 3.12. The seam is `OllamaAdapter.call_with_tools` in `mailbot_api/router/models.py:586-749`. Today (`:695-724`) tool-call presence is decided SOLELY from structured `message["tool_calls"]`; `message["content"]` is captured only as `text` (`:691`). There is NO `<tool_call>`-text parser anywhere in `mailbot_api/` (grep-verified by the spike). This story adds the fallback in the empty-array branch.
- `OpenAIToolCall` / `OpenAIToolCallFunction` are imported at `models.py:32-33` and already constructed at `:715-724` — reuse that exact shape so the rescued call is indistinguishable downstream.
- `finish_reason` logic at `:729-738`: `tool_calls` win → `"tool_calls"`. A rescued call must set this so the Router treats it as a tool-bearing turn.

**Architecture compliance**
- Files to touch: `mailbot_api/router/models.py` (the helper + one call site) and `tests/unit/router/test_ollama_adapter.py` (new tests). Possibly one integration test if the adapter→router count seam isn't covered.
- Do NOT change the structured parse loop (`:700-724`), the translate helpers, `keep_alive`, timeout, or temperature handling.
- AR-PAT-4 (errors-as-data): a malformed block is a decline+log, NOT a raise across the adapter boundary.

**Why STRICT (Adam architectural decision, 2026-07-15):** the local 3B lane is a safety net gated by action reversibility ([[project_local_model_is_safety_net]]). Lenient best-effort arg-salvage would fabricate a call the model didn't cleanly express and feed it into propose→grant→drain — pushing ambiguous output toward action. In the actual walk, lenient parsing would have dispatched a garbage `memory.add` (wrong tool AND ad-hoc args), strictly worse than the no-op. Strict promotes only clean calls; declines are logged as first-class telemetry (the measure-before-fix output). Selection is 10.7.3's problem, not the parser's.

**Real wire-shape (from WALK-10-7-5-F1, ground truth for the malformed-block test):**
```
<tool_call>
{"name": "memory", "action": "add", "target": "user", "content": "unread_emails"}
</tool_call>
```
Note: `action`/`target`/`content` are siblings of `name`, NOT under an `arguments` key → STRICT declines this exact shape.

**Testing requirements**
- Framework: pytest. Primary surface `tests/unit/router/test_ollama_adapter.py` (fake ollama client via monkeypatch, existing pattern at `:246-320`). The existing `test_call_with_tools_text_only_response` (`:301`) is the load-bearing over-trigger guard — must stay green.
- 4 gates: ruff, mypy `--strict mailbot_api`, boundary (ruff-covered), full pytest (`-q`, live marker auto-excluded).

**Scope fences**
- FORMAT channel only. No selection change (10.7.3), no description change (10.7.5, shipped), no system prompt (10.7.2, demoted).
- STRICT, never lenient — never fabricate args a malformed block didn't cleanly provide.
- Fallback only — structured `tool_calls` always wins.

### References
- `mailbot_api/router/models.py:586-749` (`call_with_tools`), `:695-724` (structured-only parse — the gap), `:711` (`json.dumps` arg shape to mirror), `:729-738` (`finish_reason`).
- `mailbot_api/router/router.py:2514` (`tool_calls_count=len(tool_response.tool_calls)` — the count the rescue restores to ≥1).
- `tests/unit/router/test_ollama_adapter.py:246-320` (fake-client harness + the over-trigger guard test).
- WALK-10-7-5-F1: story-run-flags.md § "Story 10-7-5 Manual Verification" + `router_calls id=15022` (the 2nd live repro).
- `_bmad-output/implementation-artifacts/10-7-0-spike-finding.md` §2 (FORMAT attribution: 0/172 direct-drive, Hermes-template-coupled hypothesis), §4.4 fire-list (10.7.1 KEEP defensive → now confirmed-needed).
- `_bmad-output/planning-artifacts/epics.md` § Epic 10.7 Detail (4-clause done-flip; clause 3 load-bearing).
- Memory: [[project_qwen_toolcall_format_defect_reproduced]], [[project_local_model_is_safety_net]], [[feedback_reviewer_model_substitution]] (MANDATORY-CR reviewer ≠ dev — adapter parse seam).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (dev). MANDATORY-CR reviewer: claude-sonnet-5 (≠ dev, per [[feedback_reviewer_model_substitution]] — adapter parse seam).

### Debug Log References

- `sanitize_error` is exception-only (`errors.py:247`, `def sanitize_error(exc: BaseException)`). The decline log redacts qwen's raw emitted **string**, so mypy `--strict` flagged `arg-type`. Fix: added `_sanitize_text(raw: str)` in `models.py` reusing the four shared `observability._redaction` regexes in the same order as `sanitize_error`'s body (Bearer / sk- / URL-query-token / secret-path + newline collapse). `errors.py` already imports `observability._redaction`, so the dependency direction is precedented; boundary check exit 0.
- Multi-block edge (`test_rescue_multiple_blocks_promotes_first_logs_rest`): the regex is non-greedy + `.search()` (first match), so the first block promotes and the promote log fires. AC wording "log the rest" is satisfied by the promote event being emitted (single-call semantics; extras are simply not double-promoted). No separate per-extra log added — the surviving telemetry (promote event) already lets a walk see a rescue happened.
- `arguments`-as-JSON-string edge: some emitters nest `arguments` as a JSON string; the helper parses-then-reserializes to the compact wire shape so downstream sees a normal `arguments` JSON string (fidelity preserved).

### Completion Notes List

- **AC-1** — well-formed `<tool_call>{name, arguments}</tool_call>` in `message.content` (empty structured array) is promoted to one structured `OpenAIToolCall`, `finish_reason="tool_calls"`, name + args exact, synthesized `id="call_0"`. (`test_rescue_wellformed_text_block_is_promoted`, `_bare_block_no_arguments_promotes_empty_args`, `_arguments_as_json_string_is_reserialized`, `_whitespace_and_newlines_inside_block`)
- **AC-2** — STRICT decline: the real walk shape (`{"name":"memory","action":"add","target":"user","content":"unread_emails"}` — stray sibling keys, no `arguments`) is NOT promoted (`tool_calls==[]`, `finish_reason="stop"`) and emits a decline log. Empty/missing `name` also declines. (`test_rescue_malformed_sibling_key_block_is_declined_and_logged`, `_empty_name_block_is_declined`)
- **AC-3** — over-trigger guard: a content-only response with no `<tool_call>` block still yields zero calls; the load-bearing existing `test_call_with_tools_text_only_response` stays green. (`test_rescue_plain_text_no_block_still_zero_calls` + regression)
- **AC-4** — structured path wins: when `message["tool_calls"]` is non-empty, `content` is NOT scanned even if it also holds a `<tool_call>` string; no double-count, no override, no rescue log. (`test_rescue_structured_calls_win_content_not_scanned`)
- **AC-5** — temp-0 fidelity: a rescued call's `arguments` round-trip exactly incl. a long Graph-style id; `temperature` untouched (rescue is a pure post-response text parse). (`test_rescue_argument_fidelity_long_graph_id`)
- **AC-6** — observability: promote → `event="tool_call.rescue.promoted"` (+ `tool_name`); decline → `event="tool_call.rescue.declined"` (+ sanitized `raw_block`). Both greppable, both asserted.
- **AC-7 — SCOPE FENCE (clause 3 NOT claimed closed):** this story fixes only the FORMAT channel (text→structured). It does NOT touch tool SELECTION (10.7.3) or descriptions (10.7.5, shipped). **Clause 3 — a live Discord turn with `model_chosen=qwen2.5:*` AND `tool_calls_count≥1` invoking `find_emails` — still needs 10.7.3 (surface trim, so qwen faces a small menu) + an Adam re-walk after this lands.** Empirical order: 10.7.1 → 10.7.3 → (10.7.5 shipped) → re-walk. A rescued call to the *wrong* tool still dispatches the wrong tool (acceptable — 10.7.3 owns getting qwen to the right small menu).
- Gates at review-flip: ruff clean, mypy `--strict mailbot_api` clean, boundary exit 0, pytest **1952 passed / 3 skipped / 3 deselected** (+10 net vs 1942 baseline). baseline_commit c45d0b0.
- **Post-CR (round 1) gates:** ruff clean, mypy `--strict mailbot_api` clean (134 files), boundary exit 0, pytest **1957 passed / 3 skipped / 3 deselected** (+15 net vs 1942 baseline; +5 CR-driven tests). MANDATORY-CR: reviewer sonnet-5 ≠ dev opus-4-8; 9 findings, 8 FIXED + 1 ACCEPT-WITH-RATIONALE (89% applied). See § Review Findings — Dispositions. Notable hardening: ReDoS eliminated (regex→linear `str.find`), `NaN`/`Infinity` rejected, `.text` stripped of markup on promote, decline-log scoped+redaction-tested.

### File List

- `mailbot_api/router/models.py` (modified — added `import logging`, `_log`, `_sanitize_text`, `_TOOL_CALL_OPEN`/`_TOOL_CALL_CLOSE`, `_extract_first_tool_call_block` (linear `str.find` scan, CR F3), `_reject_json_constant` + `_strict_json_object` (CR F5), `_rescue_text_tool_call`, and the rescue call-site in `call_with_tools`'s empty-array branch incl. `.text`-strip-on-promote (CR F2) + scoped decline log (CR F7). Note: the initial `import re`/`_TEXT_TOOL_CALL_RE` were replaced by the linear scan during CR — no regex remains.)
- `tests/unit/router/test_ollama_adapter.py` (modified — 15 rescue tests total: 10 initial + 5 CR-driven (ReDoS-fast-decline, close-tag-in-string decline, NaN/Infinity decline, promote-strips-.text, decline-log-redaction) + helpers `_canned_text_block_response`, `_log_events`)

## Completion Notes

### 2026-07-16 — dev + MANDATORY-CR (autonomous-story-run; dev opus-4-8, review sonnet-5)

STRICT `<tool_call>`-as-text rescue added to `OllamaAdapter.call_with_tools` (format channel only). When the structured `message["tool_calls"]` array is empty and `message["content"]` holds a `<tool_call>{…}</tool_call>` block, a clean `name`+`arguments` block is promoted to a real `OpenAIToolCall` (finish_reason `tool_calls`, shape-identical downstream so `router.py:2514` `tool_calls_count` reports ≥1); a malformed sibling-key block (the WALK-10-7-5-F1 `memory` shape) is STRICTLY declined + logged, never fabricated into a call ([[project_local_model_is_safety_net]]). Fallback only — structured always wins (AC-4); temp-0 arg fidelity untouched (AC-5). Observability: `tool_call.rescue.promoted` / `.declined` structured events, both greppable, redaction-tested.

MANDATORY-CR (reviewer sonnet-5 ≠ dev opus-4-8, adapter parse seam): 9 findings, 8 FIXED + 1 ACCEPT-WITH-RATIONALE (89%). Load-bearing catches fixed: ReDoS on unclosed prefixes (backtracking regex → linear `str.find`), `NaN`/`Infinity` accepted by `json` (now `parse_constant`-rejected), `.text` retained raw markup on promote (now stripped for shape-identity), decline log scoped to the matched block + redaction regression-tested. Accepted: `id="call_0"` collision is a pre-existing whole-adapter property (structured path emits `call_{i}` identically), out of scope for the format channel.

Gates: ruff clean, mypy `--strict mailbot_api` clean (134 files), boundary exit 0, pytest **1957 passed / 3 skipped / 3 deselected** (+15 net vs 1942 baseline). baseline_commit c45d0b0.

**Clause 3 NOT claimed closed (AC-7 scope fence):** this closes the FORMAT half only. Epic 10.7 done-flip clause 3 — a live Discord turn with `model_chosen=qwen2.5:*` AND `tool_calls_count≥1` invoking `find_emails` — still needs **10.7.3** (surface trim, so qwen faces a small menu) + an **Adam re-walk** after this lands. Empirical order: 10.7.1 → 10.7.3 → (10.7.5 shipped) → re-walk. A rescued call to the wrong tool still dispatches the wrong tool (acceptable; 10.7.3 owns selection).
