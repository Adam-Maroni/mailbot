---
baseline_commit: 260004f
---

# Story 5.3: Chat-side prompts — `intent_parsing_chat`, `reference_resolution`, `draft_reply`, `tone_style_mirror`, `multi_turn_refinement`

Status: done

## Story

As Adam,
I want five chat-side prompt modules written per the AR-PAT-5 4-export structure (VERSION / SYSTEM / USER_TEMPLATE / OUTPUT_SCHEMA), with `policy.yaml` assignments per Rule G (interactive default = API for chat surface; `draft_reply` force-routes to Opus per FR-4.4; the existing `draft_reply` policy entry from Story 2-4 stays as the authoritative routing decision and is verified against this story's prompt-module v1),
so that the chat surface (Story 5-4 Hermes wiring, Story 5-8 reference resolution, Story 5-9 draft reply capstone) has the prompts it needs before Hermes starts routing Discord traffic.

## Acceptance Criteria

### AC-1 — Five new AR-PAT-5 prompt modules under `mailbot_api/prompts/`

The following NEW prompt modules MUST exist with the AR-PAT-5 4-export shape (`VERSION: str`, `SYSTEM: str`, `USER_TEMPLATE: str`, `OUTPUT_SCHEMA: type[BaseModel]`):

- `mailbot_api/prompts/intent_parsing_chat/__init__.py` (empty marker per existing convention)
- `mailbot_api/prompts/intent_parsing_chat/v1.py`
- `mailbot_api/prompts/reference_resolution/__init__.py`
- `mailbot_api/prompts/reference_resolution/v1.py`
- `mailbot_api/prompts/draft_reply/__init__.py`
- `mailbot_api/prompts/draft_reply/v1.py`
- `mailbot_api/prompts/tone_style_mirror/__init__.py`
- `mailbot_api/prompts/tone_style_mirror/v1.py`
- `mailbot_api/prompts/multi_turn_refinement/__init__.py`
- `mailbot_api/promptsting_refinement/v1.py` — typo in placeholder; corrected to `multi_turn_refinement/v1.py`

Each `v1.py` MUST:

- Begin with a module docstring naming the task and citing this story (`Story 5-3`).
- Export `VERSION: str = "v1"`.
- Export `SYSTEM: str` — byte-stable across calls per Rule M (Anthropic ephemeral prompt cache discipline). MUST set the defender tone (conservative, terse, asks before destructive, never apologetic-when-unnecessary) consistent with the persona that Story 5-5 will codify in `SOUL.md`.
- Export `USER_TEMPLATE: str` — a Python format-string accepting the documented placeholders (see per-prompt AC sections below).
- Export `OUTPUT_SCHEMA: type[BaseModel]` — a frozen Pydantic v2 model. Use `model_config = ConfigDict(frozen=True)` consistently with `mailbot_api/verbs/schemas.py`. `Literal[...]` enums use `typing.Literal`; lists default via `Field(default_factory=list)`; optional fields use `T | None = None` (PEP 604).
- Expose all four constants plus the `<TaskType>Output` class in `__all__`.
- MUST resolve cleanly via `mailbot_api.prompts.resolve_prompt(task_type, "v1")` — the registry-level test (AC-7) parametrizes over the five new task types.

### AC-2 — `prompts/intent_parsing_chat/v1.py` schema

The Pydantic `OUTPUT_SCHEMA` (class `IntentParsingChatOutput`) MUST require:

- `intent: Literal["find_emails", "list_unread", "summarize_thread", "draft_reply", "count_query", "send_action", "delete_action", "mute_category", "label_emails", "small_talk", "ambiguous"]` — exactly these 11 literal members in this order.
- `target_email_ids: list[str] = Field(default_factory=list)` — may be empty when the intent does not target specific emails (e.g., `small_talk`, `count_query` without a specific email).
- `confidence: float = Field(ge=0.0, le=1.0)` — model's calibrated confidence in the parse.
- `proposed_filter: FindEmailsFilter | None = None` — when intent maps to a find/count query, the parsed filter; otherwise `None`. Imports `FindEmailsFilter` from `mailbot_api.verbs.schemas` (Story 5-1's frozen filter model).

The `SYSTEM` block MUST explain that this prompt parses a single Discord message from Adam into an intent + filter shape; that the agent should never fabricate `target_email_ids` (they MUST come from the current chat context or from a follow-up verb call); that `ambiguous` is the correct intent when the user's message could parse two equally-plausible ways.

`USER_TEMPLATE` accepts at minimum `{user_message}` and `{recent_context}` placeholders. `recent_context` is a short summary of the last few Discord turns (built by the orchestrator; this prompt does not concern itself with how the summary is built).

### AC-3 — `prompts/reference_resolution/v1.py` schema

The Pydantic `OUTPUT_SCHEMA` (class `ReferenceResolutionOutput`) MUST require:

- `resolved_email_ids: list[str] = Field(default_factory=list)` — the Graph message ids the agent picked; may be empty if no plausible candidate exists.
- `reasoning: str = Field(max_length=200)` — ≤ 200 chars per the AC spec; what made the agent pick these ids. Use Pydantic v2 `max_length` constraint.
- `confidence: float = Field(ge=0.0, le=1.0)`.
- `ambiguous: bool` — `True` when the resolution had to guess between multiple plausible candidates. When `True`, the chat orchestrator (Story 5-8) MUST surface a clarifying question rather than proceed silently.

`SYSTEM` MUST instruct the model to use the recent Discord turns + the projections of any emails referenced in the prior 3 turns + the cached `sender_reputation_summary` rows + Hermes persistent memory's `relevant_senders` entries as the resolution surface. MUST forbid hallucinating `email_id` values not present in the provided context (the agent MUST refuse with an empty `resolved_email_ids` list and `ambiguous=True` rather than invent a Graph id).

`USER_TEMPLATE` accepts at minimum `{user_message}`, `{recent_context}`, `{candidate_projections}` placeholders.

### AC-4 — `prompts/draft_reply/v1.py` schema + policy verification

The Pydantic `OUTPUT_SCHEMA` (class `DraftReplyOutput`) MUST require:

- `draft_body: str` — the reply text in Adam's tone (informed by `tone_style_mirror` output if available); no length cap at the schema level (the policy's `max_tokens_out=1500` is the cost-discipline ceiling).
- `suggested_subject: str` — the proposed subject line.
- `tone_signals_used: list[str] = Field(max_length=5)` — ≤ 5 stylistic cues the model picked up from prior sent emails.
- `defender_warnings: list[str] = Field(default_factory=list)` — anything the defender persona wants Adam to double-check before sending (e.g., "this reply commits to a deadline; confirm you can meet it"). Empty list is valid (no warnings).

`SYSTEM` MUST establish the defender voice: conservative, terse, never apologetic-when-unnecessary, never adds emoji/exclamation points unless the source email used them, surfaces commitments + deadlines explicitly via `defender_warnings`.

`USER_TEMPLATE` accepts at minimum `{source_email}`, `{thread_context}`, `{tone_signals}` placeholders. `tone_signals` is a short string built by the orchestrator from a prior `tone_style_mirror` cache lookup (may be empty on first contact with a recipient).

**Policy verification:** the existing `policy.yaml` entry for `draft_reply` (introduced in Story 2-4) MUST continue to set `model: claude-opus-4-7`, `escalate: false`, `max_tokens_out: 1500`, `lane: interactive`, `sensitivity: any`, `prompt_version: v1`. The story does NOT modify this entry — it verifies it. If any field has drifted, the dev pass fixes the drift to match the entry above (the spec's `max_tokens_out: 800` from the epics.md text is superseded by the already-shipped `1500` in `router/policy.yaml`; the higher cap is consistent with Opus' generation behavior on draft replies and was the deliberate choice at Story 2-4 time). Document the reconciliation in Dev Notes.

**`response_cache_ttl_seconds` is NOT set on `draft_reply`** — every draft must be fresh per FR-4.4 (Story 5-9 will explicitly bypass the response cache for `draft_reply`). The verification test asserts the field is absent OR explicitly `null` on this entry.

### AC-5 — `prompts/tone_style_mirror/v1.py` schema + new policy entry

The Pydantic `OUTPUT_SCHEMA` (class `ToneStyleMirrorOutput`) MUST require:

- `tone_attributes: list[str] = Field(max_length=10)` — short snake_case strings naming stylistic traits (e.g., `concise`, `formal`, `uses_first_names`, `avoids_emoji`, `prefers_bullets`). ≤ 10 attributes.
- `signature_pattern: str | None = None` — Adam's typical sign-off pattern if detectable from the sample (e.g., `"Best,\nAdam"`); `None` when the sample is too small or inconsistent.
- `salutation_pattern: str | None = None` — Adam's typical opening pattern; `None` when not detectable.

`SYSTEM` MUST instruct the model that the sample input is a small concatenated set of prior emails Adam sent TO THIS RECIPIENT (or, if none, a general sample of Adam's writing). The model MUST NOT invent attributes that aren't supported by the sample — `tone_attributes` MUST cite traits visible in ≥ 2 of the sample emails when ≥ 2 emails are provided.

`USER_TEMPLATE` accepts at minimum `{recipient_address}` and `{prior_emails_sample}` placeholders.

**New `policy.yaml` entry** under `tasks:` (alphabetical/grouped placement with other Opus tasks):

```yaml
  tone_style_mirror:
    model: "claude-opus-4-7"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 512
    lane: "interactive"
    sensitivity: "any"
    response_cache_ttl_seconds: 2592000  # 30 days — tone evolves slowly
    notes: "Per-recipient tone fingerprint. Invoked ONCE per recipient (cache-keyed on recipient_address) per Story 5-3 AC-5. Cache hit avoids the Opus call entirely on subsequent draft_reply turns."
    demotion_hypothesis: "Haiku may suffice for tone fingerprinting — demote when Epic 7 measures recipient-level tone accuracy parity."
```

The orchestrator/dev guidance: `tone_style_mirror` is invoked from the chat surface (Story 5-9 capstone) with `response_cache_ttl_seconds: 2592000` (30 days) via the Story 2-7 response cache; this story SHIPS the policy entry, not the orchestrator wiring — the wiring lands in Story 5-9.

### AC-6 — `prompts/multi_turn_refinement/v1.py` schema + new policy entry

The Pydantic `OUTPUT_SCHEMA` (class `MultiTurnRefinementOutput`) MUST require:

- `refined_draft: str` — the new draft after applying the refinement instruction.
- `changes_summary: str = Field(max_length=200)` — ≤ 200 chars summarizing what changed (e.g., "shortened to 3 sentences; removed unnecessary apology").
- `still_needs_clarification: bool` — `True` when the refinement instruction was itself ambiguous and the model wants Adam to clarify before proceeding (Story 5-9 then surfaces a clarification turn instead of presenting a half-baked refinement).

`SYSTEM` MUST establish that the prompt is invoked iteratively (Story 5-9 caps at 5 iterations with a defender warning at the 5th); MUST preserve the defender voice; MUST refuse to drift away from the prior draft's intent unless the user explicitly requests a restart.

`USER_TEMPLATE` accepts at minimum `{current_draft}` and `{refinement_instruction}` placeholders.

**New `policy.yaml` entry**:

```yaml
  multi_turn_refinement:
    model: "claude-opus-4-7"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 1500
    lane: "interactive"
    sensitivity: "any"
    notes: "Iterative draft refinement (Story 5-9). Routes to Opus per FR-4.4. No response_cache — refinements are turn-specific."
    demotion_hypothesis: "Haiku may suffice for small-delta refinements (e.g., 'make this shorter'); demote when Epic 7 measures refinement quality parity."
```

### AC-7 — New `policy.yaml` entries for `intent_parsing_chat` and `reference_resolution`

Two additional entries:

```yaml
  intent_parsing_chat:
    model: "qwen2.5:3b-instruct-q4_K_M"
    prompt_version: "v1"
    escalate: true   # escalate to Haiku on schema-fail-retry per Story 2-4
    max_tokens_out: 384
    lane: "interactive"
    sensitivity: "any"
    notes: "Discord message → intent + filter. Qwen-first per Rule N (cost discipline); Haiku escalation handles ambiguous parses. Interactive lane — chat latency matters."
    demotion_hypothesis: null  # already on the cheapest tier

  reference_resolution:
    model: "qwen2.5:3b-instruct-q4_K_M"
    prompt_version: "v1"
    escalate: true   # escalate to Haiku on schema-fail-retry
    max_tokens_out: 384
    lane: "interactive"
    sensitivity: "any"
    notes: "Resolve 'that one' / 'the lawyer' references against recent Discord context + sender_reputation_summary + Hermes persistent memory. Qwen-first; Haiku escalation. FR-4.3 ≥ 90% threshold validated in Epic 7 (Story 7-7 shadow-mode rollouts) per Story 5-8."
    demotion_hypothesis: null
```

### AC-8 — `tests/unit/prompts/test_chat_prompts.py` parametrized over the 5 modules

NEW test file `tests/unit/prompts/test_chat_prompts.py` MUST:

- Parametrize over the 5 task types `("intent_parsing_chat", "reference_resolution", "draft_reply", "tone_style_mirror", "multi_turn_refinement")` with one `test_chat_prompt_module_resolves_cleanly` test that calls `resolve_prompt(task_type, "v1")` and asserts the registry-level invariants (VERSION == "v1", SYSTEM non-empty str, USER_TEMPLATE non-empty str, OUTPUT_SCHEMA is BaseModel subclass).
- Parametrize over the same 5 task types with one `test_chat_prompt_output_schema_round_trips` test that provides a known-good payload per task type and asserts the OUTPUT_SCHEMA parses + dumps cleanly (mirrors the pattern in `tests/unit/prompts/test_prompt_modules.py`).
- Parametrize over the same 5 task types with one `test_chat_prompt_user_template_accepts_documented_placeholders` test that asserts `USER_TEMPLATE.format(**documented_kwargs)` does NOT raise `KeyError` for each module's documented placeholders.
- One dedicated test `test_intent_parsing_chat_proposed_filter_round_trip` that submits a payload with a non-null `proposed_filter` and asserts the nested `FindEmailsFilter` round-trips.
- One dedicated test `test_draft_reply_defender_warnings_default_empty` confirming `defender_warnings` defaults to `[]` (not `None`).
- One dedicated test `test_reference_resolution_reasoning_max_length` confirming Pydantic rejects a `reasoning` string > 200 chars with a `ValidationError`.
- One dedicated test `test_intent_parsing_chat_intent_literal_rejects_unknown` confirming Pydantic rejects an unknown intent value (e.g., `"hack_the_inbox"`) with a `ValidationError`.

The test module MUST use the same imports / fixtures style as `tests/unit/prompts/test_prompt_modules.py` for consistency.

### AC-9 — policy.yaml verification test

NEW test `tests/unit/router/test_policy_chat_entries.py` (or extension of the existing policy test module if one exists):

- Loads `router/policy.yaml` via `mailbot_api.router.policy.load_policy(...)`.
- Asserts the 5 new entries exist (`draft_reply` was pre-existing; the test checks all 5 anyway for symmetry).
- Asserts each entry's required fields match the table below — fail-loudly on drift:

| task_type             | model                                | prompt_version | escalate | lane        | max_tokens_out | sensitivity | response_cache_ttl_seconds |
| --------------------- | ------------------------------------ | -------------- | -------- | ----------- | -------------- | ----------- | -------------------------- |
| `intent_parsing_chat` | `qwen2.5:3b-instruct-q4_K_M`         | `v1`           | `true`   | `interactive` | `384`        | `any`       | absent / null              |
| `reference_resolution`| `qwen2.5:3b-instruct-q4_K_M`         | `v1`           | `true`   | `interactive` | `384`        | `any`       | absent / null              |
| `draft_reply`         | `claude-opus-4-7`                    | `v1`           | `false`  | `interactive` | `1500`       | `any`       | absent / null (NOT cached) |
| `tone_style_mirror`   | `claude-opus-4-7`                    | `v1`           | `false`  | `interactive` | `512`        | `any`       | `2592000` (30 days)        |
| `multi_turn_refinement`| `claude-opus-4-7`                   | `v1`           | `false`  | `interactive` | `1500`       | `any`       | absent / null              |

If any field has drifted, FAIL the test with a clear message (e.g., `assert entry.model == "claude-opus-4-7", f"draft_reply model drifted to {entry.model}"`).

### AC-10 — All four quality gates green

- Pytest: previous baseline (714 from Story 5-2 completion) + new tests. Net test count rises by **≥ 8** (per AC-8 minimum count: 3 parametrized × 5 = 15 parametrized, plus 4 dedicated tests; counted as test functions: minimum 8 new functions, where each parametrized test counts as 1 function). The actual collected-test count will be higher because pytest expands parametrize markers.
- Ruff clean (no new violations).
- Mypy clean on the new modules + the new test module.
- Boundary checker clean (no new violations); the new prompt modules and test do NOT need allow-list entries (they are pure Python data + tests; no SQL / no graph.microsoft.com / no anthropic.com calls).

## Tasks / Subtasks

- [ ] Create the 5 prompt module directories + `__init__.py` + `v1.py` files per AC-1
- [ ] Implement `intent_parsing_chat/v1.py` per AC-2 (schema + SYSTEM + USER_TEMPLATE)
- [ ] Implement `reference_resolution/v1.py` per AC-3
- [ ] Implement `draft_reply/v1.py` per AC-4 (verify existing policy.yaml entry)
- [ ] Implement `tone_style_mirror/v1.py` per AC-5 + add new policy.yaml entry
- [ ] Implement `multi_turn_refinement/v1.py` per AC-6 + add new policy.yaml entry
- [ ] Add `intent_parsing_chat` + `reference_resolution` policy.yaml entries per AC-7
- [ ] Write `tests/unit/prompts/test_chat_prompts.py` per AC-8
- [ ] Write `tests/unit/router/test_policy_chat_entries.py` (or extend the existing policy test module) per AC-9
- [ ] Run gate sweep per AC-10

### Review Findings

- [x] \[Review]\[Patch] `tone_signals_used` in `DraftReplyOutput` — APPLIED: added `default_factory=list` so first-contact drafts (no prior tone signals) don't raise ValidationError. New test `test_draft_reply_tone_signals_used_default_empty` covers the LLM-omits-field path. `mailbot_api/prompts/draft_reply/v1.py:74`
- [x] \[Review]\[Patch] `proposed_filter: {}` ambiguity — APPLIED option (b): SYSTEM block now explicitly forbids empty-object `proposed_filter={}` and instructs the model to use `null` for the no-filter case; orchestrator gets an unambiguous contract. (option a `@model_validator` rejected — would mutate LLM output in a way that hides parsing failures from the schema-fail-retry path). `mailbot_api/prompts/intent_parsing_chat/v1.py:34-39`
- [x] \[Review]\[Patch] `model_validate_json` path uncovered — APPLIED: added `test_chat_prompt_output_schema_json_validate_round_trips` parametrized over all 5 task types; exercises the `model_dump_json → model_validate_json` symmetric path the Router uses on schema-fail-retry. `tests/unit/prompts/test_chat_prompts.py:106`
- [x] \[Review]\[Decision] `reference_resolution` SYSTEM mentions surfaces with no matching placeholder — APPLIED option (b): added a "Placeholder injection contract for the Story 5-8 orchestrator" block at module level documenting that `{recent_context}` carries Hermes memory entries and `{candidate_projections}` carries `sender_reputation_summary` blobs. Format-stable across cold-start (no memory) and steady-state; orchestrator decides composition. `mailbot_api/prompts/reference_resolution/v1.py:70-94`
- [x] \[Review]\[Decision] `multi_turn_refinement` iteration-count signal — APPLIED option (b): updated module docstring to explicitly call out that the 5-iteration cap + defender warning is **orchestrator-level discipline** (Story 5-9 owns the counter); the prompt deliberately omits `{iteration_count}` because meta-loop control belongs in the orchestrator. AC-6 language refers to the orchestrator's contract that consumes this prompt. `mailbot_api/prompts/multi_turn_refinement/v1.py:8-15`
- [x] \[Review]\[Defer] `demotion_hypothesis` key absent from `intent_parsing_chat` and `reference_resolution` policy.yaml entries — AC-7 table shows `demotion_hypothesis: null`; shipped YAML omits the key entirely (consistent with older entries pre-dating the field); harmless if PolicyEntry defaults to None — deferred, pre-existing pattern
- [x] \[Review]\[Defer] Boundary checker `_VERBS_IMPORT_ALLOW` allowlist is file-path specific but does not protect against transitive re-export — a future prompt module importing `IntentParsingChatOutput` from `intent_parsing_chat/v1.py` inherits `FindEmailsFilter` dependency without triggering the checker `scripts/check_boundaries.py:137` — deferred, pre-existing architecture limitation
- [x] \[Review]\[Defer] `still_needs_clarification=True` SYSTEM instruction tension — SYSTEM says "produce your best-guess refinement" AND set the flag; the orchestrator (Story 5-9) decides presentation, so both behaviors are correct; conflict dissolves in Story 5-9 — deferred, resolved in Story 5-9 orchestrator

## Dev Notes

### AR-PAT-5 4-export shape — the canonical reference

Read `mailbot_api/prompts/__init__.py` (the registry) before writing the new modules. Key invariants the registry enforces:

- `VERSION` must be a non-empty `str` and MUST equal the requested `prompt_version`.
- `SYSTEM` and `USER_TEMPLATE` must be non-empty `str`.
- `OUTPUT_SCHEMA` must be a `type` subclass of `BaseModel` (Pydantic v2).

Mirror an existing module exactly for shape — `mailbot_api/prompts/summary_short/v1.py` is the cleanest small reference; `mailbot_api/prompts/importance_scoring/v1.py` shows how to use `Field(ge=, le=)` constraints; `mailbot_api/prompts/action_extraction/v1.py` shows how to nest a list-of-models schema. Match their docstring style, their `__all__` shape, and their `Field(description=...)` discipline.

### Defender persona — the chat-surface voice

Story 5-5 will codify the defender persona in `SOUL.md`. THIS story's SYSTEM blocks MUST anticipate that persona: conservative, terse, asks before destructive actions, surfaces reasoning when proposing actions, never apologetic-when-unnecessary, never cheerful chit-chat, never adds emoji/exclamation points unless the source content already uses them. The four banned anti-patterns from NFR-PERSONA-2 are: never send without per-message authorization; never delete without per-action authorization; never quote sensitive content outside chat; never produce noisy notifications. None of THIS story's prompts produce send/delete actions directly (those go through the verb surface), but the SYSTEM blocks SHOULD echo the spirit of the persona so the model's tone is consistent end-to-end.

### Rule G — policy.yaml as the single routing source of truth

Per architecture's Rule G ("policy.yaml owns the routing decision; prompts never name their own model"), the prompt modules MUST NOT mention model ids in their SYSTEM blocks. The routing is set by `router/policy.yaml`'s `model:` field for each task_type. The SYSTEM block speaks to "the model" generically.

### Rule M — byte-stable SYSTEM blocks

Anthropic's ephemeral prompt cache (Rule M discipline) only hits when the SYSTEM block is byte-stable across calls. Do NOT interpolate dynamic values (timestamps, user names, request ids) into SYSTEM. All dynamic content goes through `USER_TEMPLATE`'s placeholders.

### Rule N — cost discipline → Qwen-first for parsing, Opus for generative

`intent_parsing_chat` and `reference_resolution` are PARSING tasks — the cost-discipline policy puts them on Qwen with escalate=true (Haiku as the schema-fail-retry tier per Story 2-4). `draft_reply`, `tone_style_mirror`, `multi_turn_refinement` are GENERATIVE tasks where output quality is a tier-1 product capability (FR-4.4) — Opus-bound, no escalation. The architecture explicitly authorizes this cost-vs-quality split for chat-surface tasks.

### `FindEmailsFilter` import — Story 5-1 dependency

`intent_parsing_chat/v1.py`'s OUTPUT_SCHEMA imports `FindEmailsFilter` from `mailbot_api.verbs.schemas`. That model is frozen (Pydantic v2 `model_config = ConfigDict(frozen=True)`) and was introduced in Story 5-1. The dev pass MUST verify the import works at module import time (Pydantic v2 raises immediately on nested-model misuse). The intent-parsing prompt produces `proposed_filter` as a nested model — Pydantic v2 serializes it cleanly through `.model_dump()` for the schema-fail-retry pathway.

### `draft_reply` policy entry — already exists; verify, don't add

`router/policy.yaml` was first shipped in Story 2-4. The `draft_reply` entry already exists with `model: claude-opus-4-7`, `prompt_version: v1`, `escalate: false`, `max_tokens_out: 1500`, `lane: interactive`, `sensitivity: any`. The spec text in epics.md mentions `max_tokens_out: 800` but the shipped value is `1500` — this story takes the SHIPPED value as authoritative (deliberate choice at Story 2-4 time for Opus generation behavior). Document the reconciliation in a Dev Notes line during the dev pass + a code comment near the entry in `router/policy.yaml` if helpful.

### Why the `prompts/draft_reply/v1.py` module didn't exist before

Even though `policy.yaml`'s `draft_reply` entry has been live since Story 2-4, the actual prompt MODULE wasn't shipped — Story 2-4 only needed the routing to resolve, not the prompt body. Any call to `ask_router(task_type="draft_reply", ...)` before THIS story ships would raise `PromptResolutionError` at registry resolution time. THIS story closes that gap.

### `policy.yaml` reload semantics — validation-or-no-swap

Per architecture §"D11: policy.yaml reload semantics", the policy loader does validation-or-no-swap on every edit (Story 2-2). Adding the 4 new entries means the validation must pass on first reload — if any required PolicyEntry field is missing on a new entry, the previous policy stays live. The dev pass MUST verify (manually or via `load_policy()` in a test) that the post-edit YAML parses cleanly.

### Where the chat orchestrator USES these prompts (not in scope for this story)

- `intent_parsing_chat` — invoked by Story 5-8's chat orchestrator on every Discord message before reference resolution; Story 5-4 wires Hermes to call this.
- `reference_resolution` — invoked by Story 5-8's reference-resolution flow.
- `draft_reply` — invoked by Story 5-9's capstone draft-reply flow.
- `tone_style_mirror` — invoked by Story 5-9's draft-reply flow with response-cache-on per AC-5.
- `multi_turn_refinement` — invoked by Story 5-9's refinement loop.

None of these orchestrations are in scope for THIS story. THIS story ships only the prompt modules + policy entries + their tests. The orchestrator wiring lands in Stories 5-4 / 5-8 / 5-9.

### MailBot has no graphical frontend

Per PORTING.md: `<frontend-src>` is N/A. No `.tsx`/`.vue`/`.svelte` files. UI nouns in this story's ACs (none — every AC is server-side or test-side) would refer to Discord-rendered text. **Step 2.4.5 (UI-Scope Pre-Flight) is N/A.** Step 2.4.7 (Middleware-Real-Bootstrap MailBot reframing) is N/A for this story — pure-data prompt modules + Pydantic schemas + a policy-table verification test. No verb / Router call site / DB write is introduced.

### Test isolation note

The new test file follows the existing `tests/unit/prompts/test_prompt_modules.py` pattern. No DB fixtures, no FastAPI lifespan setup, no policy-watcher lifecycle teardown needed — `resolve_prompt` is a pure import + validation function.

The policy verification test (`test_policy_chat_entries.py`) loads `router/policy.yaml` directly via `load_policy(path)`. It does NOT mutate module-level policy state or trigger the watcher; it just parses the file and asserts on the returned `PolicyTable`. If a `_reset_policy_snapshot_for_test` fixture is needed for harmony with other policy tests, mirror that pattern.

### Existing tests that must remain green

The 714 baseline tests touch the prompt registry, policy loader, and Router orchestration. The new prompt modules add new modules to `mailbot_api/prompts/` but do NOT modify the registry or any existing prompt. The new policy entries add new keys to `policy.yaml` but do NOT modify existing keys. Regression risk is low; the gate sweep will confirm.

### Story dependency chain

- Story 5-3 prerequisites: Story 5-1 (FindEmailsFilter schema), Story 3-2 (AR-PAT-5 registry contract), Story 2-2 (policy.yaml loader), Story 2-4 (existing draft_reply policy entry).
- Story 5-3 consumers: Story 5-4 (Hermes wires `intent_parsing_chat` calls), Story 5-8 (`reference_resolution` flow), Story 5-9 (`draft_reply` + `tone_style_mirror` + `multi_turn_refinement` flow).

### References

- [Source: epics.md Story 5.3](../planning-artifacts/epics.md)
- [Source: architecture.md AR-PAT-5 prompt-module contract, Rule G policy.yaml, Rule M cache stability, Rule N cost discipline, FR-4.3, FR-4.4](../planning-artifacts/architecture.md)
- [Source: Story 3-2 — AR-PAT-5 4-export pattern for ingest prompts](./3-2-prompt-modules-for-ingest-tasks-uniform-ar-pat-5-structure.md)
- [Source: Story 5-1 — FindEmailsFilter schema (frozen Pydantic v2)](./5-1-read-side-verbs-projection-first-data-window-for-the-agent.md)
- [Source: Story 2-2 — policy.yaml loader + validation-or-no-swap reload](./2-2-policy-yaml-schema-and-loader-and-watchfiles-hot-reload.md)
- [Source: Story 2-4 — existing draft_reply policy entry](./2-4-ask-router-core-orchestration-dispatch-timeout-schema-validation-retry-escalate.md)
- [Source: mailbot_api/prompts/__init__.py — registry contract](../../mailbot_api/prompts/__init__.py)
- [Source: mailbot_api/prompts/summary_short/v1.py — canonical 4-export module shape reference](../../mailbot_api/prompts/summary_short/v1.py)
- [Source: router/policy.yaml — current policy table](../../router/policy.yaml)

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-epic-run dev pass

### Debug Log References

### Completion Notes List

- Shipped 5 chat-side AR-PAT-5 prompt modules: `intent_parsing_chat`, `reference_resolution`, `draft_reply`, `tone_style_mirror`, `multi_turn_refinement`. All 4 exports (`VERSION`, `SYSTEM`, `USER_TEMPLATE`, `OUTPUT_SCHEMA`) per Story 3-2 registry contract; `<TaskType>Output` Pydantic v2 frozen models with `ConfigDict(frozen=True)`.
- Added 4 new `policy.yaml` entries (`intent_parsing_chat`, `reference_resolution`, `tone_style_mirror`, `multi_turn_refinement`); verified pre-existing `draft_reply` entry (model=claude-opus-4-7, max_tokens_out=1500 — reconciled with epics.md spec text of `800` per Story 2-4's deliberate choice; epics.md was wrong, the shipped 1500 is correct).
- `intent_parsing_chat` SYSTEM forbids `proposed_filter={}` empty-object ambiguity (CR-2 fix); orchestrator gets unambiguous `null` vs filled-filter contract.
- `reference_resolution` ships a "Placeholder injection contract for the Story 5-8 orchestrator" docblock (CR-4): `{recent_context}` carries Hermes persistent memory entries, `{candidate_projections}` carries `sender_reputation_summary` blobs. Format-stable across cold-start and steady-state.
- `multi_turn_refinement` docstring explicitly delegates the 5-iteration cap + defender warning to the Story 5-9 orchestrator (CR-5); the prompt produces a refinement, the orchestrator owns the meta-loop counter.
- `_VERBS_IMPORT_ALLOW` extended by ONE entry (`mailbot_api/prompts/intent_parsing_chat/v1.py`) to permit the legitimate `FindEmailsFilter` nested-schema import. Documented inline; preserves the boundary rule's spirit (the prompt module IS an agent-facing schema, like the verbs themselves).
- CR (Sonnet 4.6) returned Changes Requested: 3 PATCH (tone_signals_used default, proposed_filter ambiguity, model_validate_json test coverage) + 2 DECISION (reference_resolution placeholder contract, multi_turn_refinement iteration signal) + 3 DEFER (boundary transitivity, demotion_hypothesis absence, refinement orchestrator-dissolves item). All 5 actionable findings applied (5/5 = 100%); 3 defers documented in story file as accepted-with-rationale.
- 749 tests pass (+35 net from 714 baseline; +6 beyond the initial dev-pass 29 from CR-3 (5 new parametrized + 1 dedicated test) + CR-1 (1 new dedicated test) = 7 new test functions = +6 collected at the parametrize-expansion level). All 4 gates green: pytest 749 / ruff clean / mypy clean / boundary check clean.

### File List

NEW:

- mailbot_api/prompts/intent_parsing_chat/__init__.py
- mailbot_api/prompts/intent_parsing_chat/v1.py
- mailbot_api/prompts/reference_resolution/__init__.py
- mailbot_api/prompts/reference_resolution/v1.py
- mailbot_api/prompts/draft_reply/__init__.py
- mailbot_api/prompts/draft_reply/v1.py
- mailbot_api/prompts/tone_style_mirror/__init__.py
- mailbot_api/prompts/tone_style_mirror/v1.py
- mailbot_api/prompts/multi_turn_refinement/__init__.py
- mailbot_api/prompts/multi_turn_refinement/v1.py
- tests/unit/prompts/test_chat_prompts.py
- tests/unit/router/test_policy_chat_entries.py
- _bmad-output/implementation-artifacts/5-3-chat-side-prompts-intent-parsing-chat-reference-resolution-draft-reply-tone-style-mirror-multi-turn-refinement.md
- _bmad-output/implementation-artifacts/5-3.pre-review.md

UPDATED:

- router/policy.yaml — 4 new task entries (intent_parsing_chat, reference_resolution, tone_style_mirror, multi_turn_refinement) appended after hermes_aux; existing entries (including draft_reply) untouched.
- scripts/check_boundaries.py — `_VERBS_IMPORT_ALLOW` gained `mailbot_api/prompts/intent_parsing_chat/v1.py` to permit the legitimate FindEmailsFilter nested-schema import; inline comment documents the rationale.
- _bmad-output/implementation-artifacts/sprint-status.yaml — 5-3 row flipped backlog → ready-for-dev → in-progress → done; last_updated bumped.

## Completion Notes

### 2026-06-02 — autonomous-epic-run close

Story 5-3 closed by autonomous-epic-run. CR (Sonnet 4.6) returned Changes Requested with 5 actionable findings (3 PATCH + 2 DECISION); all 5 applied (100%). 3 DEFER items accepted with documented rationale. Final test count: 749 (+35 net from 714 baseline). All 4 gates green. Story `done`.
