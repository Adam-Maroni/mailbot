# Story 6.12: Anthropic `temperature` deprecated on `claude-opus-4-7` — F19 closure

Status: backlog

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

- [ ] **Task 1**: Verify the inline-fixed code is still in place (check `mailbot_api/router/models.py` line ~555 + ~650 carry the `if self.model_id != "claude-opus-4-7":` gates).
- [ ] **Task 2**: Add regression tests in `tests/unit/router/test_anthropic_adapter.py` (or wherever `AnthropicAdapter` is tested) — 2 tests minimum (AC-2).
- [ ] **Task 3**: Add the live smoke test (AC-3) — gated behind `@pytest.mark.live` so default `pytest` doesn't burn cost; runs in CI nightly or on-demand.
- [ ] **Task 4**: Audit other Opus 4.7 param deprecations (AC-4) — write the audit paragraph + add gates if needed.
- [ ] **Task 5**: Run all 4 gates green; MANDATORY-CR; apply findings.

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

### References

- `_bmad-output/implementation-artifacts/epic-6-run-flags.md § Story 6-6.5 walk record § Third pass § F19`
- `mailbot_api/router/models.py` — inline-fixed code
- Sibling-quartet pattern: stories 6-6.6 / 6-6.7 / 6-6.8 / 6-6.9
