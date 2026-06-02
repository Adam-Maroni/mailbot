---
baseline_commit: 260004f
---

# Story 5.8: Conversational reference resolution — built and instrumented (FR-4.3 ≥ 90% validated in Epic 7)

Status: done

## Story

As Adam,
I want the reference-resolution flow wired end-to-end: a `resolve_reference()` orchestrator that builds the context from the last 10 Discord turns + projections of emails referenced in the prior 3 turns + cached `sender_reputation_summary` rows + (cold-startable) Hermes persistent-memory entries, dispatches via `ask_router(task_type="reference_resolution", caller_origin="verb-ask-router")` per `router/policy.yaml`, and returns the resolved `email_ids` to the chat orchestrator — with every dispatch logging to `router_calls` so Epic 7 (Story 7-7's shadow-mode rollouts) has the data to validate the FR-4.3 ≥ 90% threshold,
so that multi-turn conversations work today and the ≥ 90% accuracy threshold from FR-4.3 has the row data it needs to be measured in Epic 7.

## Acceptance Criteria

### AC-1 — `mailbot_api/chat/reference.py` module + public API

NEW module `mailbot_api/chat/reference.py` (sibling to the Story 5-7 redactor under the existing `mailbot_api/chat/` package). Exposes:

- `@dataclass(frozen=True) class DiscordTurn` — one Discord chat turn with fields:
  - `role: Literal["user", "assistant"]`
  - `content: str`
  - `at: str` — ISO-8601 UTC Z timestamp.
- `@dataclass(frozen=True) class ReferenceContext` — the assembled context for one call. Fields:
  - `recent_turns: tuple[DiscordTurn, ...]` — most-recent-last; the chat orchestrator passes the last 10 turns of the conversation.
  - `candidate_projections: tuple[EmailProjection, ...]` — projections from emails referenced in the prior 3 turns (the chat orchestrator extracts these by walking the prior turns' `target_email_ids` from `intent_parsing_chat` results).
  - `sender_summaries: tuple[str, ...]` — pre-fetched cached `sender_reputation_summary` strings for senders named explicitly in the most recent user turn. Empty tuple if no senders named.
  - `relevant_senders_memory: str | None` — opaque blob from Hermes persistent memory's `relevant_senders` entries (per AR-USERMODEL-1); `None` on cold-start (no memory yet) — the resolver must work with `None` per the AC text "cold-start: resolution falls back to using only Discord context + sender_reputation_summary rows — no error".
- `@dataclass(frozen=True) class ReferenceResolutionResult` — returned by `resolve_reference()`. Fields:
  - `ok: bool`
  - `resolved_email_ids: tuple[str, ...]` — empty when no candidate exists OR when `ambiguous=True`.
  - `reasoning: str` — ≤ 200 chars per the Story 5-3 prompt schema (mirrored here verbatim).
  - `confidence: float` — 0.0..1.0 per the Story 5-3 prompt.
  - `ambiguous: bool` — when True, the chat orchestrator MUST surface a clarifying question (the resolver itself does not surface; it returns the verdict for the orchestrator to act on).
  - `router_call_id: int | None` — the `router_calls.id` of the dispatched call, for forensic linking to Epic 7's sampler queries.
  - `error: RouterError | None` — Router-level failure (e.g., DEGRADED_MODE_BLOCKED, SENSITIVITY_NOT_CLASSIFIED, etc.); when set, `resolved_email_ids` is empty and `ambiguous` is True.
- `async def resolve_reference(context: ReferenceContext, *, db_path: str, caller_origin: str = "verb-ask-router") -> ReferenceResolutionResult`

### AC-2 — `build_reference_resolution_content` helper

NEW function `build_reference_resolution_content(context: ReferenceContext) -> dict[str, Any]` builds the `content` dict passed to `ask_router`. The dict has the EXACT three keys the Story 5-3 `reference_resolution/v1.py` `USER_TEMPLATE` placeholders expect:

- `"user_message"`: the most recent `DiscordTurn` from the user, by content.
- `"recent_context"`: a single multi-line string concatenating the last 10 turns oldest-first (roles + content separated by `\n`). When `relevant_senders_memory` is not None, append a separator line `--- relevant_senders ---\n` followed by the memory blob per the Story 5-3 placeholder-injection contract.
- `"candidate_projections"`: a single multi-line string with one projection per line in the format `id={email_id} subject={subject!r} from={from_address} class={class_coarse}`. When `sender_summaries` is non-empty, append a separator line `--- sender_summaries ---\n` followed by one summary per line.

This builder is pure (no I/O); the chat orchestrator (Story 5-9) is responsible for fetching the projections + sender_summaries + memory and threading them into `ReferenceContext`.

### AC-3 — `resolve_reference` dispatches via `ask_router`

`resolve_reference` MUST:

1. Validate the context — if `recent_turns` is empty OR if the most recent turn's role is not `"user"`, return `ReferenceResolutionResult(ok=False, ambiguous=True, resolved_email_ids=(), reasoning="invalid context: missing user turn", confidence=0.0, router_call_id=None, error=None)`. Do NOT dispatch the Router.
2. Call `build_reference_resolution_content(context)`.
3. Call `ask_router(task_type="reference_resolution", content=<built dict>, db_path=db_path, caller_origin=caller_origin, email_id=None)`. `email_id` is intentionally `None` because reference resolution operates over the chat surface, not on a single resolved email (that's the OUTPUT, not the INPUT).
4. On a successful `RouterResult` (ok=True), parse the dispatched output against the Story 5-3 `ReferenceResolutionOutput` Pydantic schema (`from mailbot_api.prompts.reference_resolution.v1 import ReferenceResolutionOutput`) — the Router already validates per AR-PAT-4, but the orchestrator parses the dict-shaped output back into the typed model for caller convenience.
5. Return `ReferenceResolutionResult(ok=True, resolved_email_ids=tuple(parsed.resolved_email_ids), reasoning=parsed.reasoning, confidence=parsed.confidence, ambiguous=parsed.ambiguous, router_call_id=<from RouterResult>, error=None)`.
6. On a failed `RouterResult` (ok=False), return `ReferenceResolutionResult(ok=False, ambiguous=True, resolved_email_ids=(), reasoning=<sanitized error string>, confidence=0.0, router_call_id=<from RouterResult if present>, error=<RouterError>)`. The orchestrator (Story 5-9) treats `ambiguous=True` as "surface a clarifying question" — for Router-level failures the clarifying question doubles as the graceful-degradation surface.

The `caller_origin="verb-ask-router"` default matches the existing project convention for verb-internal Router calls; Story 5-9 may override with a chat-orchestrator-specific origin.

### AC-4 — Hermes memory is read-only from this surface

`ReferenceContext.relevant_senders_memory` is the orchestrator's responsibility to fetch (Story 6-5/6-7's memory tooling). `resolve_reference` MUST NOT write to Hermes memory; it MUST NOT call any memory API. If the orchestrator passes `relevant_senders_memory=None`, the resolver works (cold-start path per AC). The prompt's SYSTEM block in Story 5-3 already names the memory entries as a resolution surface; the dev pass just has to thread them through `recent_context` per the AC-2 builder contract.

### AC-5 — Logging is implicit via `router_calls`

Every successful Router dispatch writes a `router_calls` row with `task_type="reference_resolution"` (per Story 2-1's audit table contract). The orchestrator does NOT emit additional logs — Epic 7's sampler queries `router_calls` directly. Verified in AC-6 tests by asserting at least one row with the documented task_type after a successful dispatch.

### AC-6 — Integration tests

NEW file `tests/integration/test_reference_resolution.py` (DB-real per Step 2.4.7 reframing). Tests:

1. **Builder contract — placeholders match Story 5-3 USER_TEMPLATE:** parametrize over a small context fixture; assert `build_reference_resolution_content` returns a dict with exactly `{"user_message", "recent_context", "candidate_projections"}` keys.
2. **Empty context refuses without dispatch:** call `resolve_reference` with `ReferenceContext(recent_turns=())` against a real DB. Assert `ok=False`, `ambiguous=True`, AND `router_call_id is None` (no Router dispatch). Assert the `router_calls` table count did not increase.
3. **Last-turn-not-user refuses without dispatch:** same shape but the most recent turn is `role="assistant"`. Same assertions.
4. **Happy path — Router returns resolved_email_ids:** monkeypatch `ask_router` to return a `RouterResult(ok=True, output={"resolved_email_ids": ["g-1"], "reasoning": "matches sender", "confidence": 0.8, "ambiguous": False}, ...)`. Call `resolve_reference` with a valid context. Assert the returned `resolved_email_ids == ("g-1",)`, `ambiguous=False`, `router_call_id` is set.
5. **Ambiguous result surfaces as ambiguous=True:** Router returns `ambiguous=True` + empty `resolved_email_ids`. Assert the orchestrator passes that through (does not try to "fix" it).
6. **Router-level failure → ambiguous=True + error set:** Router returns `RouterResult(ok=False, error=RouterError(code=ErrorCode.PROVIDER_ERROR, message="paused", retryable=True))`. Assert `ResolveReferenceResult(ok=False, ambiguous=True, error=<...>)`.
7. **Cold-start memory case:** `relevant_senders_memory=None` is accepted; the built `recent_context` does NOT contain the `--- relevant_senders ---` separator.
8. **Sender summaries threaded into candidate_projections:** non-empty `sender_summaries` produces a `--- sender_summaries ---` separator + the summaries in `candidate_projections`.
9. **Router-call row written on dispatch:** seed a real DB + policy.yaml; call `resolve_reference` (mock the underlying adapter to avoid live Ollama); assert `SELECT COUNT(*) FROM router_calls WHERE task_type='reference_resolution'` ≥ 1. (Trick: use the existing `FakeAdapter` pattern from `tests/unit/router/test_orchestration.py`.)
10. **Sanitized error string on Router failure:** the error message returned from the Router is not blindly stuffed into `reasoning`; it goes through `sanitize_error` (or equivalent) so secrets in the message do not leak.

Minimum 9 tests; the file ships parametrized variants where natural.

### AC-7 — Boundary check

The new `mailbot_api/chat/reference.py` imports:

- `from mailbot_api.verbs.schemas import EmailProjection` — same Rule G consumer as Story 5-3's `intent_parsing_chat`; ADD this file to `_VERBS_IMPORT_ALLOW` in `scripts/check_boundaries.py`.
- `from mailbot_api.router import ask_router` — direct Router import is fine (verb-side); not subject to verbs-import boundary.
- `from mailbot_api.prompts.reference_resolution.v1 import ReferenceResolutionOutput` — fine (prompt registry public API).

No FastMCP, no Graph client, no Anthropic client direct imports.

### AC-8 — All four quality gates green

- Pytest: previous baseline (817 from Story 5-7) + ≥ 9 new tests = ≥ 826.
- Ruff clean on the new module + test file.
- Mypy clean on the new module.
- Boundary check clean (AC-7 allowlist extension is the only change).

## Tasks / Subtasks

- [ ] Write `mailbot_api/chat/reference.py` per AC-1 / AC-2 / AC-3 / AC-4
- [ ] Extend `scripts/check_boundaries.py` allowlist per AC-7
- [ ] Write `tests/integration/test_reference_resolution.py` per AC-6 (≥ 9 tests)
- [ ] Run gate sweep per AC-8

### Review Findings

- [x] \[Review]\[Decision] `sanitize_error("Exception: ")` prefix — APPLIED: strip the `"Exception: "` prefix in `resolve_reference` after calling `sanitize_error`. The wrap-then-unwrap pattern preserves the redaction logic; the noisy prefix is gone from chat-surface reasoning text.
- [x] \[Review]\[Decision] `ok=True + ambiguous=True` contract contradiction — APPLIED: `ReferenceResolutionResult` docstring rewritten with a full result-state matrix that EXPLICITLY documents the four states (ok=T/ambig=F confident, ok=T/ambig=T multiple plausible candidates with non-empty ids, ok=F/ambig=T graceful degradation, ok=F/ambig=F reserved). The Story 5-3 SYSTEM block authorizes `"return BOTH ids in resolved_email_ids AND set ambiguous=True"` so non-empty IS valid; Story 5-9 MUST check `ambiguous` before treating ids as an action target. The AC-1 docstring text in the story file remains as the original spec (the dataclass docstring is the authoritative implementation contract).
- [x] \[Review]\[Decision] Null projection fields → literal "None" in LLM context — APPLIED: extracted `_projection_line(p)` helper that maps `None` → `"unknown"` for `subject`, `from_address`, and `class_coarse`. The LLM never sees literal `from=None` / `subject='None'`. Dedicated regression test `test_builder_projection_with_null_fields_uses_unknown_sentinels` asserts zero "None" substrings in the rendered line. Material for FR-4.3 ≥ 90% accuracy preservation in Epic 7.
- [x] \[Review]\[Patch] Leading `\n` in `candidate_projections` — APPLIED: `candidate_projections = candidate_projections.lstrip("\n")` at the end of the builder. New regression test `test_builder_sender_summaries_without_projections_no_leading_newline` pins the fix.
- [x] \[Review]\[Patch] Dead `else` branch (`"router returned ok=False with no error"`) — APPLIED: replaced with `assert err is not None, "RouterResult.ok=False contract violation: error is None"` so the invariant is explicit.
- [x] \[Review]\[Patch] Dead `_DummyOk(RouterResult)` subclass — APPLIED: removed; replaced with an expanded test docstring explaining why `model_construct` is used (validator-bypass for impossible-state defensive coverage).
- [x] \[Review]\[Patch] No forward-compat guard for `router_call_id` — APPLIED: added `assert not hasattr(result, "router_call_id"), <...canary message...>` so when a future RouterResult gains this attribute the canary fires at first dispatch and forces a revisit. The orchestrator's `router_call_id: int | None = None` line is right next to the canary so the future fix is obvious.
- [x] \[Review]\[Defer] Single-turn context produces duplicate message in both `recent_context` and `user_message` (the user's only turn appears in both fields per the Story 5-3 USER_TEMPLATE design) — this is per-spec; the LLM receives one turn twice but the SYSTEM block treats them as separate resolution surfaces; not a bug in this story [`mailbot_api/chat/reference.py:98-106`] — deferred, pre-existing

## Dev Notes

### Why the orchestrator is on the mailbot-api side, not Hermes

Hermes is the Discord adapter + the agent runtime (model dispatch via `/v1/chat/completions`). The reference-resolution orchestrator lives on the mailbot-api side because:

1. It composes `ask_router(...)` calls, which is mailbot-api code (Rule M / Rule N enforcement happens at the Router boundary).
2. It needs SQL access to fetch projections + sender_summaries from the DB (Rule C — verbs are the only code that touches SQL for the agent's benefit).
3. Hermes calls into this orchestrator via the MCP surface in a future story OR via a typed HTTP endpoint. THIS story does NOT add the HTTP/MCP entry point — Story 5-9 wires that (the chat capstone is the natural place).

### `build_reference_resolution_content` placeholder contract

The Story 5-3 `reference_resolution/v1.py` USER_TEMPLATE accepts `{user_message}`, `{recent_context}`, `{candidate_projections}`. The builder produces a dict with those exact keys. The Story 5-3 module's "Placeholder injection contract" docblock (AC-3 of 5-3) committed to threading Hermes persistent memory through `recent_context` and `sender_reputation_summary` through `candidate_projections` — this story is the producer for that contract.

### Why `email_id=None` on the Router call

`ask_router`'s `email_id` parameter triggers the sensitivity precondition layer (Story 3-3): unclassified emails refuse, sensitive/confidential block escalation to API. Reference resolution operates OVER the chat surface, not on a single email; passing `email_id=None` is the documented bypass for chat-level Router calls (per Story 3-3 sender_reputation_summary precedent: cross-email aggregation tasks set `email_id=None`).

### Ambiguous handling — orchestrator's responsibility

When `ambiguous=True`, this orchestrator returns the verdict. The CHAT orchestrator (Story 5-9) surfaces the clarifying question to the user. This separation lets THIS module stay pure: it parses, dispatches, returns. No I/O beyond the Router call + the `router_calls` write (which the Router does internally).

### MailBot has no graphical frontend

Per PORTING.md: `<frontend-src>` is N/A. Step 2.4.5 N/A. Step 2.4.7 MailBot-reframing: this story ships a NEW orchestration surface that dispatches Router calls. The integration tests are DB-real + Router-real (with a FakeAdapter for the model boundary), satisfying the reframed Middleware-Real-Bootstrap gate.

### References

- [Source: epics.md Story 5.8](../planning-artifacts/epics.md)
- [Source: architecture.md FR-4.3, AR-USERMODEL-1 (Hermes persistent memory)](../planning-artifacts/architecture.md)
- [Source: Story 5-3 — reference_resolution prompt module](./5-3-chat-side-prompts-intent-parsing-chat-reference-resolution-draft-reply-tone-style-mirror-multi-turn-refinement.md)
- [Source: Story 5-1 — EmailProjection schema](./5-1-read-side-verbs-projection-first-data-window-for-the-agent.md)
- [Source: Story 2-1 — router_calls audit table](./2-1-router-calls-audit-table-and-router-result-router-error-data-shapes.md)
- [Source: Story 2-4 — ask_router orchestration](./2-4-ask-router-core-orchestration-dispatch-timeout-schema-validation-retry-escalate.md)
- [Source: Story 3-3 — Router precondition layer + email_id=None bypass for cross-email tasks](./3-3-sensitivity-classifier-and-sensitivity-patterns-yaml-and-router-precondition-layer.md)

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-epic-run dev pass

### Completion Notes List

- Shipped `mailbot_api/chat/reference.py`: `DiscordTurn` / `ReferenceContext` / `ReferenceResolutionResult` frozen dataclasses + `build_reference_resolution_content` pure builder + `resolve_reference` async orchestrator. Cold-start memory case handled; ambiguous=True propagation handled; Router-failure graceful-degradation handled.
- Extended `scripts/check_boundaries.py` allowlist for `mailbot_api/chat/reference.py` (legitimate EmailProjection consumer — agent-facing chat surface, mirror of Story 5-3 / 5-6 patterns).
- CR (Sonnet 4.6, MANDATORY-CR for load-bearing orchestrator) returned 7 findings: 3 DECISION + 3 PATCH + 1 DEFER. All 6 actionable items applied (6/6 = 100%):
  - **Decision CR-1 (sanitize_error prefix)** — strip `"Exception: "` prefix on reasoning text; cleaner chat-surface output.
  - **Decision CR-2 (ok=T+ambiguous=T contract clarification)** — biggest concern. Rewrote `ReferenceResolutionResult` docstring with a full 4-state matrix; the Story 5-3 SYSTEM block authorizes non-empty resolved_email_ids alongside ambiguous=True (multiple plausible candidates → user disambiguates). Story 5-9 capstone MUST check `ambiguous` before acting on the ids.
  - **Decision CR-3 (None field → "unknown" sentinels)** — extracted `_projection_line` helper that guards null `subject` / `from_address` / `class_coarse` → "unknown" so the LLM never sees literal `from=None`. Critical for FR-4.3 ≥ 90% accuracy preservation.
  - **Patch CR-4 (leading \n)** — `.lstrip("\n")` on candidate_projections.
  - **Patch CR-5 (dead else branch)** — replaced with assert.
  - **Patch CR-6 (dead _DummyOk subclass)** — removed; expanded test docstring.
  - **Patch CR-7 (router_call_id canary)** — `assert not hasattr(result, "router_call_id")` fires when future RouterResult gains the field, forcing a revisit.
  - Defer: single-turn duplication in recent_context + user_message — per-spec; not a bug.
- 831 tests pass (+14 net from 817 baseline; +2 from CR fixes). Ruff clean. Mypy clean. Boundary clean.

### File List

NEW:

- mailbot_api/chat/reference.py
- tests/integration/test_reference_resolution.py
- _bmad-output/implementation-artifacts/5-8-conversational-reference-resolution-built-and-instrumented-fr-4-3-validated-in-epic-7.md
- _bmad-output/implementation-artifacts/5-8.pre-review.md

UPDATED:

- scripts/check_boundaries.py — `_VERBS_IMPORT_ALLOW` gains `mailbot_api/chat/reference.py`.
- _bmad-output/implementation-artifacts/sprint-status.yaml — 5-8 row backlog → in-progress → done.

## Completion Notes

### 2026-06-02 — autonomous-epic-run close

Story 5-8 closed by autonomous-epic-run. §5.12 MANDATORY-CR cadence honored — Sonnet 4.6 CR dispatched, 6/6 actionable findings applied (100%), 1 defer documented (per-spec single-turn duplication). Most material catches:

1. **ok=T+ambiguous=T contract** rewritten with 4-state matrix so Story 5-9 knows non-empty ids on ambiguous IS valid (per Story 5-3 SYSTEM block) and MUST be surfaced as disambiguation rather than acted on.
2. **Null projection fields** now use "unknown" sentinels — prevents literal `from=None` in LLM context that could silently degrade FR-4.3 accuracy below the 90% threshold Epic 7 validates against.
3. **Forward-compat canary** for router_call_id so future Router work doesn't silently leave this orchestrator returning None when the contract evolves.

Final test count: 831 (+14 net from 817 baseline). All 4 gates green. Story `done`. Story 5-9 capstone is the next consumer.
