---
baseline_commit: 01c03e9838c68f357dd17c800fc99e70134221fc
---

# Story 6.12: Anthropic `temperature` deprecated on `claude-opus-4-7` — F19 closure

Status: done

> Filed 2026-06-04 during Story 6-6.5 third-pass walk. Inline fix already applied during the walk and verified live (see `epic-6-run-flags.md § Story 6-6.5 walk record § Third pass § F19`). This story's job is to **add regression tests + formal CR + audit other model-specific param deprecations** for the patch that already ships in the repo.

## Story

As MailBot,
I want the AnthropicAdapter to gate Opus-4.7-incompatible parameters before dispatching to `messages.create()`,
So that any code path invoking the Opus reasoning model succeeds instead of returning HTTP 400 — and so future model-specific deprecations are caught before they ship.

## Acceptance Criteria

**AC-1**: `AnthropicAdapter.call` and `AnthropicAdapter.call_with_tools` MUST omit `temperature` from the request kwargs when `model_id == "claude-opus-4-7"`. (Already implemented in the inline-fixed code — this AC is the regression-test requirement.)

**AC-2**: Two regression tests added — one per code path (`call` + `call_with_tools`) — that assert the kwargs passed to a mock `messages.create()` do NOT include `temperature` when model_id is `claude-opus-4-7`, and DO include it when model_id is `claude-haiku-4-5-20251001`. Tests use `httpx.MockTransport` per existing adapter test pattern.

**AC-3**: One end-to-end live-anthropic smoke test (`@pytest.mark.live` skipped by default) that dispatches a minimal `messages.create(model="claude-opus-4-7", max_tokens=16, messages=[...])` and asserts HTTP 200 — guards against future Anthropic-side reintroduction or relocation of the param.

**AC-4**: Code audit for *other* model-specific param deprecations on Opus 4.7. Open Anthropic's current API docs (or `hermes-docs/` if mirrored), enumerate any params the Opus reasoning model rejects (top_p, top_k, frequency_penalty, presence_penalty, response_format, etc.), and either (a) add them to the same gating in `AnthropicAdapter.call*` OR (b) document why each is safe. Result: a one-paragraph audit note in this story's Dev Notes + (if needed) additional gates in the adapter.

**AC-5**: MANDATORY-CR per §5.12: this is a Router adapter boundary patch touching cross-story load-bearing seams (Story 2-x Router + Story 5-9 orchestrator + Story 6-9 tool-calling). At least one CR review pass with the F19 surface in scope.

## Tasks / Subtasks

- [x] **Task 1**: Verify the inline-fixed code is still in place (check `mailbot_api/router/models.py` line ~555 + ~650 carry the `if self.model_id != "claude-opus-4-7":` gates). — VERIFIED 2026-06-05: gates at models.py:559-560 (call) + :660-661 (call_with_tools), both omit `temperature` from `request_kwargs` when `self.model_id == "claude-opus-4-7"`.
- [x] **Task 2**: Add regression tests in `tests/unit/router/test_anthropic_adapter.py` — 4 tests added (2 required + 2 counter-tests on Haiku): `test_anthropic_adapter_call_omits_temperature_on_opus_4_7`, `test_anthropic_adapter_call_keeps_temperature_on_haiku`, `test_anthropic_adapter_call_with_tools_omits_temperature_on_opus_4_7`, `test_anthropic_adapter_call_with_tools_keeps_temperature_on_haiku`. All pass.
- [x] **Task 3**: Live smoke test `test_anthropic_adapter_live_opus_4_7_smoke` added under `@pytest.mark.live`. Marker registered in `pyproject.toml`; `addopts = "-m 'not live'"` ensures default `pytest` opts out (verified: 11 passed, 1 deselected). Skips cleanly when `ANTHROPIC_API_KEY` is unset. Opt-in: `pytest -m live`.
- [x] **Task 4**: Audit other Opus 4.7 param deprecations (AC-4) — audit completed, table added to Dev Notes. Finding: adapter only sends `model` / `max_tokens` / `system` / `messages` / `temperature` (gated) / `tools` / `tool_choice`. No `top_p`/`top_k`/`frequency_penalty`/`presence_penalty`/`response_format`/`stop_sequences`/`metadata` are ever sent. No additional gates required beyond F19. Future sampling-param additions must include matching gates + regression tests.
- [x] **Task 5 (dev portion)**: 4 gates green — ruff clean (full repo), `mypy --strict mailbot_api` clean (122 files), pytest 1083 passed + 2 skipped + 1 deselected (live smoke). +4 net tests vs baseline 1079+2. MANDATORY-CR per §5.12 is the orchestrator's Step 2.4 responsibility and will run after this story flips to `review`.

## Dev Notes

### Why this story exists

Story 6-6.5 walk discovered F19 live. Inline fix shipped during the walk to unblock CP-A. This story formalizes the fix per the inline-fix-and-walk pattern (same as 6-6.6 / 6-6.7 / 6-6.8 / 6-6.9 sibling-quartet).

### F19 details

`mailbot_api/router/models.py:555` (`AnthropicAdapter.call`) and `:650` (`AnthropicAdapter.call_with_tools`) unconditionally passed `temperature` to `messages.create()`. Anthropic deprecated the parameter on claude-opus-4-7 (reasoning-only model); call returns HTTP 400 `temperature is deprecated for this model`. Live-verified `request_id=req_011CbiWJ3Sb2u1dgaBxWnHW2`.

### Why this slipped past tests

- Story 5-9 14/14 orchestrator tests mock the Router boundary
- Story 6-9 tool-calling tests mock the same boundary
- Pricing entry at `mailbot_api/router/pricing.py:40` flags Opus 4.7 as "PLACEHOLDER pending live-billing verification" — a tell that nobody had run a real Opus call end-to-end
- All `draft_reply` / `chat_completions_tool_call` rows in `router_calls` for Opus-bound tasks before this walk showed `outcome=retry_recovered` or `failed` — never `ok`

### Opus 4.7 param-deprecation audit (AC-4)

**Scope:** other Anthropic `messages.create()` params that Opus 4.7's reasoning-only profile may reject or ignore. Per Anthropic's public reasoning-model guidance, the params at risk are: `top_p`, `top_k`, `temperature` (already gated as F19), and sampling-style modifiers like `frequency_penalty` / `presence_penalty` (which are OpenAI shapes, not Anthropic — never sent by this adapter).

**Audit method:** grep `mailbot_api/router/models.py` for every key written into the `request_kwargs` dict that flows into `self._client.messages.create(**request_kwargs)`. The complete set is:

| Param            | `call` path (line) | `call_with_tools` path (line) | Opus-4.7 safe?  |
| ---------------- | ------------------ | ----------------------------- | --------------- |
| `model`          | 554                | 656                           | ✅ required     |
| `max_tokens`     | 555                | 657                           | ✅ accepted     |
| `system`         | 556                | 663 (conditional)             | ✅ accepted     |
| `messages`       | 557                | 658                           | ✅ required     |
| `temperature`    | 560 (gated)        | 661 (gated)                   | ✅ gated by F19 |
| `tools`          | —                  | 665 (conditional)             | ✅ accepted     |
| `tool_choice`    | —                  | 674 (conditional)             | ✅ accepted     |

**Findings:**

1. **No `top_p`, `top_k`, `frequency_penalty`, `presence_penalty`, `response_format`, `stop_sequences`, or `metadata` are ever sent.** The adapter is intentionally minimal — it builds `request_kwargs` from a fixed set of inputs, with no `**kwargs` pass-through. Future deprecations on those params therefore cannot regress this code path without a deliberate new feature add.
2. **`temperature` is the only sampling-style param the adapter sends**, and it is now gated on `model_id != "claude-opus-4-7"` in both code paths (F19 closure).
3. **`tools` + `tool_choice` are accepted by Opus 4.7** per Anthropic's tool-use docs (reasoning models support tool use; the Story 6-9 integration tests + the F19 live walk both exercised Opus + tools without 400s).
4. **`system` block with `cache_control: ephemeral`** is exercised live in Story 6-9 + 6-6.5 against Opus and accepted (router_calls id=416 outcome=ok).

**Gate decision:** no additional gates needed beyond F19. If a future story adds `top_p` / `top_k` / similar sampling controls to the adapter API, those additions must include matching `model_id != "claude-opus-4-7"` gates and a regression test mirroring the F19 pattern.

### References

- `_bmad-output/implementation-artifacts/epic-6-run-flags.md § Story 6-6.5 walk record § Third pass § F19`
- `mailbot_api/router/models.py` — inline-fixed code (lines 559-560, 660-661)
- Sibling-quartet pattern: stories 6-6.6 / 6-6.7 / 6-6.8 / 6-6.9
- Story 6-9 (F11 closure) — proved Opus 4.7 + tools work post-F19

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Debug Log

- Verified F19 inline-fix presence at `mailbot_api/router/models.py:559-560` and `:660-661`. Both code paths build `request_kwargs` dict then conditionally insert `temperature` only when `self.model_id != "claude-opus-4-7"`.
- Added 4 regression tests using existing `httpx.MockTransport` pattern from `test_anthropic_adapter.py`. Tests assert request body via `json.loads(captured[0].content)` — same shape as the pre-existing `test_anthropic_adapter_request_targets_correct_model_id` test.
- Live smoke test gated via new `live` pytest marker. Verified default-exclusion: `pytest tests/unit/router/test_anthropic_adapter.py -v` reports `11 passed, 1 deselected`.
- AC-4 audit method: grep on `request_kwargs[` and `messages.create(` in models.py — full set of params dispatched is `model`/`max_tokens`/`system`/`messages`/`temperature`/`tools`/`tool_choice`. No `top_p`/`top_k`/etc. ever reach Anthropic from this adapter.

### Completion Notes List

- AC-1 satisfied by existing inline fix (Task 1 verification step).
- AC-2 satisfied: 4 regression tests added (2 required + 2 Haiku counter-tests for both `call` and `call_with_tools` code paths). All pass under `httpx.MockTransport`.
- AC-3 satisfied: `test_anthropic_adapter_live_opus_4_7_smoke` added under `@pytest.mark.live`. Marker registered in `pyproject.toml`. `addopts = "-m 'not live'"` ensures plain `pytest` invocations never hit the live API.
- AC-4 satisfied: full param-deprecation audit table added to Dev Notes. No additional gates required — adapter is intentionally minimal and only sends `temperature` as a sampling-style param (now gated).
- AC-5 (MANDATORY-CR) deferred to orchestrator Step 2.4 per autonomous-story-run contract.

### File List

- `mailbot_api/router/models.py` — verified F19 fix in place (no edits this story).
- `tests/unit/router/test_anthropic_adapter.py` — added 5 new tests (4 regression + 1 live smoke) + 2 new helper functions (`_trivial_tool`, `_mock_messages_response_no_tool_use`) + 2 new imports (`ChatCompletionFunctionDef`, `ChatCompletionToolDef`).
- `pyproject.toml` — registered `live` pytest marker + added `addopts = "-m 'not live'"` default-exclusion.
- `_bmad-output/implementation-artifacts/6-12-anthropic-temperature-deprecated-on-opus-4-7-f19-closure.md` — this story file (YAML frontmatter `baseline_commit`, task checkboxes, Dev Agent Record, File List, Change Log, Status flip).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — row flipped to `in-progress` (dev-story) then will flip to `review` post-dev (orchestrator's Step 2.3.5 + 2.4 chain).

### Review Findings

- [x] [Review][Patch] Live smoke test imports `os` inside function body — moved `import os` to the module-level import block (line 19, alphabetical position between `json` and `typing`). Mid-function import removed. [tests/unit/router/test_anthropic_adapter.py:19]
- [x] [Review][Patch] `addopts = "-m 'not live'"` CI operator trap — fixed by changing `addopts` to `-m 'not live and not slow'` (option a from the finding). Both default exclusions are now co-enforced so a CI invocation like `pytest -m 'not slow'` no longer accidentally re-includes live tests. Added a multi-line comment explaining the marker-override semantics. Verified: full pytest run is now `1082 passed, 2 skipped, 2 deselected` — the second deselection is one pre-existing `slow`-marked test now opt-out by default (was inadvertently included before this fix). [pyproject.toml:128-138]
- [x] [Review][Defer] Model gate string literal (`!= "claude-opus-4-7"`) vs prefix match — if Anthropic ships a date-suffixed variant (e.g., `claude-opus-4-7-20261001`) with the same no-temperature contract, the exact-literal gate would miss it and temperature would leak again. `not self.model_id.startswith("claude-opus-4-")` would future-proof but risks over-broad gating if a future Opus variant reintroduces temperature support. Decision: keep exact literal for precision; revisit if a date-suffixed Opus 4.7 variant ships. [mailbot_api/router/models.py:559,660] — deferred, pre-existing and design-choice
- [x] [Review][Defer] `call_with_tools` F19 regression test does not assert that `tools` were correctly included in the request body — the test verifies temperature is absent but does not verify that `tools` was populated (only the temperature assertion is made). A future refactor stripping tools from the request when `tool_choice` is None would not be caught. Out of scope for F19 story; tools-translation coverage is Story 6-9's responsibility. [tests/unit/router/test_anthropic_adapter.py:275-296] — deferred, pre-existing
- [x] [Review][Defer] `call` method lacks the F14 empty-system guard present in `call_with_tools` — `call` at line 539 unconditionally wraps `system` in `TextBlockParam` with `cache_control: ephemeral`, while `call_with_tools` at line 641 has `if system and system.strip():` (F14 fix). An Opus 4.7 `call()` with empty system would get the ephemeral block and likely a 400 from Anthropic. Pre-existing asymmetry, out of scope for this story; should be tracked as a follow-up to apply F14's guard to the `call` path. [mailbot_api/router/models.py:539-545] — deferred, pre-existing

### Change Log

- 2026-06-05 — F19 regression coverage shipped. 4 unit tests + 1 live smoke + AC-4 audit. Baseline 01c03e9 → 1083 passed + 2 skipped + 1 deselected (live). +4 net tests vs baseline 1079+2.
- 2026-06-05 — Code review pass (sonnet-4-6) applied: 2 patches (mid-function import os → module-level; addopts marker-override CI trap fix); 3 defers (pre-existing model-gate literal, pre-existing test gap, pre-existing F14-asymmetry on call path). Final: 1082 passed + 2 skipped + 2 deselected (the second deselection is a pre-existing slow-marked test now properly opt-out by default per the CR-2 fix).

## Completion Notes

### 2026-06-05 — dev + code-review complete

F19 regression coverage shipped via autonomous-story-run v3 (inline-walk architecture). 4 unit tests + 1 live smoke pin the temperature-gate at the AnthropicAdapter boundary; AC-4 audit table proves the adapter sends no other Opus-4.7-deprecated params. MANDATORY-CR (sonnet-4-6 reviewer): 2 patches applied (mid-function import os; CI-trap addopts fix co-enforcing `not live and not slow`); 3 defers accepted as pre-existing or design-choice. All 4 gates green: ruff clean, mypy --strict mailbot_api clean (122 files), pytest 1082 passed + 2 skipped + 2 deselected. Baseline 01c03e9 → +4 net tests (1079+2 → 1082+2-1-deselected-slow-now-default-out). See story file `### Review Findings` + `### Change Log` for the per-finding triage and the pre-review self-audit artifact at `_bmad-output/implementation-artifacts/6-12.pre-review.md` for the §5.12 cadence determination.
