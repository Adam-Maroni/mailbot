---
baseline_commit: 46f09db
---

# Story 3.2: Prompt modules for ingest tasks (uniform AR-PAT-5 structure)

Status: done

## Story

As Adam,
I want the six ingest-task prompt modules (`sensitivity_class`, `coarse_class`, `fine_class`, `summary_short`, `importance_scoring`, `action_extraction`) written as `prompts/<task>/v1.py`, each exporting exactly `VERSION`, `SYSTEM`, `USER_TEMPLATE`, and `OUTPUT_SCHEMA` per AR-PAT-5, with the existing `coarse_class/v1.py` stub upgraded to match the spec and the registry extended to enforce all four exports,
so that the prompt-module structure is proven uniformly across six tasks before any of them runs in production, and Story 3-5's pipeline orchestrator can load every ingest prompt by convention.

## Acceptance Criteria

### AC-1 — Existing prompt-module registry extended to require the 4th `VERSION` export

**Given** Story 2-4 shipped `mailbot_api/prompts/__init__.py` with `resolve_prompt(task_type, prompt_version) -> PromptModule` that validates THREE constants (`SYSTEM`, `USER_TEMPLATE`, `OUTPUT_SCHEMA`),

**When** the registry is extended per the AR-PAT-5 spec (`architecture.md` §"prompt modules" + §"prompts/<task_type>/<version>.py" — VERSION, SYSTEM, USER_TEMPLATE, OUTPUT_SCHEMA),

**Then** `resolve_prompt(task_type, prompt_version)` validates a FOURTH constant `VERSION: str` on the imported module.

**And** `PromptModule` (the dataclass returned by `resolve_prompt`) gains a `version: str` field.

**And** `resolve_prompt` verifies the module's `VERSION` constant EQUALS the requested `prompt_version` argument — mismatch raises `PromptResolutionError(f"{module_path}.VERSION='{module.VERSION}' != requested '{prompt_version}'")`. This catches accidental copy-paste of v1 content into a v2 file.

**And** the existing `hermes_aux/v1.py` (Story 2-10) AND `coarse_class/v1.py` (Story 2-4 stub, replaced by AC-3 below) both export `VERSION = "v1"`.

### AC-2 — `prompts/sensitivity_class/v1.py` (new, Qwen-only per FR-2.5)

**Given** AR-PAT-5 mandates the 4-export shape,

**When** `mailbot_api/prompts/sensitivity_class/__init__.py` (empty package marker) and `mailbot_api/prompts/sensitivity_class/v1.py` are created,

**Then** the module exports:
- `VERSION: str = "v1"`
- `SYSTEM: str` — a concise defender-toned system prompt (≤ 600 chars; cacheable per Rule M — no per-call interpolation). The prompt directs the model to classify into `normal`/`sensitive`/`confidential` with cautious-bias on ambiguity (NFR-PRIV-1).
- `USER_TEMPLATE: str` — accepts named placeholders `{subject}`, `{sender}`, `{body_preview}`. Pure format-string.
- `OUTPUT_SCHEMA: type[BaseModel]` — `SensitivityClassOutput(BaseModel)` with fields:
  - `sensitivity: Literal["normal", "sensitive", "confidential"]`
  - `confidence: float = Field(ge=0.0, le=1.0)` — range-validated 0..1
  - `reason: str = Field(max_length=200)` — ≤ 200 chars
- Module-level `__all__ = ["VERSION", "SYSTEM", "USER_TEMPLATE", "OUTPUT_SCHEMA"]`.
- Module docstring naming Story 3-2 + FR-2.5 (Qwen-only — sensitivity must stay local) + Rule M (cacheable SYSTEM).

### AC-3 — `prompts/coarse_class/v1.py` (REPLACED — Story 2-4 stub upgraded to spec)

**Given** Story 2-4 shipped a 5-label stub (`newsletter`, `transactional`, `personal`, `promotional`, `spam`),

**When** the file is replaced with the spec-conformant module,

**Then** the module exports:
- `VERSION: str = "v1"`
- `SYSTEM: str` — concise, defender-toned, cacheable.
- `USER_TEMPLATE: str` — same `{subject}` / `{sender}` / `{body_preview}` placeholder shape.
- `OUTPUT_SCHEMA: type[BaseModel]` — `CoarseClassOutput(BaseModel)`:
  - `class_coarse: Literal["transactional", "newsletter", "human", "notification", "spam_like", "unknown"]` — 6 labels per epic spec (3-2 AC-3 in epics.md). Note: field name is `class_coarse` not `label` to align with the `emails.class_coarse` column (Story 3-1 column-vs-task-type ordering convention).
  - `confidence: float = Field(ge=0.0, le=1.0)`
- Module-level `__all__ = ["VERSION", "SYSTEM", "USER_TEMPLATE", "OUTPUT_SCHEMA"]`.

**Note (disposition)**: this rewrites Story 2-4's stub. Story 2-4's tests that referenced the old 5-label schema MUST be updated in the same diff. Story 2-4's Router tests use a fake adapter that produces `{"label": "newsletter", "confidence": 0.9}`-shaped output — those fixture payloads must be updated to `{"class_coarse": "newsletter", "confidence": 0.9}` and the integration may need a Pydantic test-data update.

### AC-4 — `prompts/fine_class/v1.py` (new)

**Given** the spec mandates `fine_class` is invoked ONLY after `coarse_class == "human"`,

**When** the new module is created,

**Then** the module exports:
- `VERSION = "v1"`, `__all__` + docstring.
- `SYSTEM` — explicitly conditioned: the prompt names that this task is invoked only for human-class email; the model SHOULD NOT second-guess that classification.
- `USER_TEMPLATE` — same placeholder shape.
- `OUTPUT_SCHEMA` — `FineClassOutput(BaseModel)`:
  - `class_fine: Literal["personal", "professional", "family", "cold_outreach", "automated", "unknown"]`
  - `confidence: float = Field(ge=0.0, le=1.0)`

### AC-5 — `prompts/summary_short/v1.py` (new)

**Given** Rule A mandates summaries are computed once and cached,

**When** the new module is created,

**Then** the module exports:
- Standard 4 + `__all__` + docstring.
- `OUTPUT_SCHEMA` — `SummaryShortOutput(BaseModel)`:
  - `summary: str = Field(max_length=280)` — Twitter-length defender brevity.

### AC-6 — `prompts/importance_scoring/v1.py` (new)

**Given** the spec mandates `importance: int` in range 0..100,

**When** the new module is created,

**Then** the module exports:
- Standard 4 + `__all__` + docstring.
- `OUTPUT_SCHEMA` — `ImportanceScoringOutput(BaseModel)`:
  - `importance: int = Field(ge=0, le=100)` — 0..100 integer
  - `signals: list[str] = Field(max_length=5)` — ≤ 5 short tags (Pydantic v2 `max_length` on `list` enforces max items)

**Note**: this column lives as REAL in 001_init.sql (Story 3-1 disposition note); the Pydantic schema's `int` declaration IS the contract — SQLite type affinity reads back the value as int. Story 3-1 documented this resolution.

### AC-7 — `prompts/action_extraction/v1.py` (new)

**Given** the spec mandates a nested `ActionItem` model,

**When** the new module is created,

**Then** the module exports:
- Standard 4 + `__all__` + docstring.
- The module ALSO exports a nested model `ActionItem(BaseModel)`:
  - `type: Literal["reply_needed", "deadline", "calendar_event", "payment", "password_reset", "info_only"]`
  - `summary: str = Field(max_length=120)`
  - `deadline_at: str | None = None` — UTC ISO-8601 with `Z` when present (validation: if non-None, the format MUST match a strict regex `r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"`; otherwise raise ValidationError per Pydantic v2 `@field_validator`).
- `OUTPUT_SCHEMA` — `ActionExtractionOutput(BaseModel)`:
  - `actions: list[ActionItem]`
- `__all__` includes BOTH `ActionItem` and the standard 4.

### AC-8 — Registry test extended; all six modules load cleanly via `resolve_prompt`

**Given** the registry now validates `VERSION` and the six new/updated modules ship the 4-export shape,

**When** `tests/unit/prompts/test_prompt_modules.py` (new file) is parameterized over the six task types,

**Then** for each task type `t` in `("sensitivity_class", "coarse_class", "fine_class", "summary_short", "importance_scoring", "action_extraction")`:
- `resolve_prompt(t, "v1")` succeeds, returns a `PromptModule` whose `version == "v1"`.
- The returned module's `SYSTEM` is a non-empty `str`.
- The returned module's `USER_TEMPLATE` is a non-empty `str`.
- The returned module's `OUTPUT_SCHEMA` is a Pydantic v2 BaseModel subclass.

**And** a separate test per task type instantiates the `OUTPUT_SCHEMA` against a known-good sample payload and asserts it validates cleanly.

**And** a separate test verifies the registry rejects a deliberately-broken module fixture (e.g., one that exports `VERSION = "v2"` while requested as `v1`) with the precise `PromptResolutionError` message.

### AC-9 — Test fixtures for the schema-rejection paths

**Given** Pydantic enforces the range / max-length / Literal constraints,

**When** `tests/unit/prompts/test_output_schema_validation.py` runs,

**Then** these rejection scenarios are covered (one test per scenario):
- `SensitivityClassOutput`: `confidence=1.5` → ValidationError (out of range).
- `SensitivityClassOutput`: `sensitivity="other"` → ValidationError (not in Literal).
- `CoarseClassOutput`: `class_coarse="garbage"` → ValidationError.
- `SummaryShortOutput`: `summary="x" * 281` → ValidationError (max_length=280).
- `ImportanceScoringOutput`: `importance=150` → ValidationError (gt 100).
- `ImportanceScoringOutput`: `signals=["a", "b", "c", "d", "e", "f"]` → ValidationError (max_length=5).
- `ActionExtractionOutput`: an ActionItem with `deadline_at="2026-06-01"` (no time, no Z) → ValidationError.
- `ActionExtractionOutput`: an ActionItem with `type="malicious_action"` → ValidationError.

### AC-10 — Story 2-4's existing tests updated to the new `coarse_class` schema

**Given** Story 2-4 had tests referencing the old `{label, confidence}` shape,

**When** the diff lands,

**Then** every existing test file that constructed a `CoarseClassOutput` (or mocked an adapter to produce one) is updated to use the new `class_coarse` field name and the new 6-label Literal.

**And** the test count net-delta is non-negative (no removed tests; only field-name swaps).

### AC-11 — All quality gates green

**Given** the six prompt modules, registry extension, and tests are in place,

**When** `python -m pytest`, `ruff check .`, `ruff format --check`, `mypy mailbot_api/`, and `python scripts/check_boundaries.py` are run,

**Then** all five pass cleanly:
- pytest: 345 baseline (post-Story-3-1) + new prompt tests; zero regressions
- ruff check / format: no violations on new files
- mypy: clean
- boundary check: exit 0 (Pydantic imports are project-permitted, no new boundary risk)

## Tasks / Subtasks

- [x] **Task 1**: Extend the registry to validate `VERSION` (AC-1)
  - [x] Update `mailbot_api/prompts/__init__.py` to validate the 4th constant `VERSION: str`
  - [x] Add a `version: str` field to `PromptModule` dataclass
  - [x] Add the equality check `module.VERSION == requested prompt_version`
  - [x] Update `mailbot_api/prompts/hermes_aux/v1.py` to export `VERSION = "v1"` + `__all__`
  - [x] Run Story 2-4's Router tests to confirm `resolve_prompt("coarse_class", "v1")` still works after registry change

- [x] **Task 2**: Replace `prompts/coarse_class/v1.py` (AC-3, AC-10)
  - [x] Replace the existing 5-label stub with the 6-label spec-conformant body
  - [x] Rename the field from `label` to `class_coarse` in the OUTPUT_SCHEMA
  - [x] Add `VERSION = "v1"` export
  - [x] Update any Story 2-4 test files that build a `CoarseClassOutput` to use the new field name + new labels (`personal`/`human`/`unknown` swap, etc.)

- [x] **Task 3**: Create the five new prompt modules (AC-2, AC-4, AC-5, AC-6, AC-7)
  - [x] `prompts/sensitivity_class/__init__.py` + `prompts/sensitivity_class/v1.py`
  - [x] `prompts/fine_class/__init__.py` + `prompts/fine_class/v1.py`
  - [x] `prompts/summary_short/__init__.py` + `prompts/summary_short/v1.py`
  - [x] `prompts/importance_scoring/__init__.py` + `prompts/importance_scoring/v1.py`
  - [x] `prompts/action_extraction/__init__.py` + `prompts/action_extraction/v1.py` (incl. nested `ActionItem`)

- [x] **Task 4**: Author the parametrized registry-load test (AC-8)
  - [x] Create `tests/unit/prompts/test_prompt_modules.py`
  - [x] Parameterize over the six task types
  - [x] Add per-task `OUTPUT_SCHEMA` instantiation tests with known-good payloads
  - [x] Add the version-mismatch rejection test

- [x] **Task 5**: Author the schema-rejection-path tests (AC-9)
  - [x] Create `tests/unit/prompts/test_output_schema_validation.py`
  - [x] Implement the 8 rejection scenarios listed in AC-9

- [x] **Task 6**: Update Story 2-4's affected tests (AC-10)
  - [x] grep `CoarseClassOutput\|"label":` under `tests/`
  - [x] For each hit, update field name + label values

- [x] **Task 7**: Run all gates locally and confirm green (AC-11)

### Review Findings

- [x] `Review/Patch` Registry `resolve_prompt` does not enforce non-empty SYSTEM / USER_TEMPLATE strings — `mailbot_api/prompts/__init__.py:92-94` — `if not isinstance(system, str)` passes for `""` (empty string), while `VERSION` is correctly guarded with `not version`. A module with `SYSTEM=""` or `USER_TEMPLATE=""` loads cleanly and silently produces empty prompts. Fix: change guards to `if not (isinstance(system, str) and system):` and `if not (isinstance(user_template, str) and user_template):` to mirror the VERSION guard pattern. Add a test verifying empty-string SYSTEM is rejected.
- [x] `Review/Patch` Tautological assertion in `test_hermes_aux_still_loads_post_story_3_2_registry_extension` — `tests/unit/prompts/test_prompt_modules.py:157` — `assert "auxiliary" in module.system.lower() or "auxiliary" in module.system.lower()` — both sides of `or` are identical (copy-paste error). The assertion always passes regardless of SYSTEM content. Fix: second arm should assert a distinct substring, e.g. `"text-processing"`, or the assertion should be simplified to a single condition.
- [x] `Review/Patch` `test_resolve_prompt_rejects_version_mismatch` has unused `tmp_path` and `monkeypatch` fixture parameters — `tests/unit/prompts/test_prompt_modules.py:89` — both are declared in the signature but the function body manipulates `sys.modules` directly rather than using `monkeypatch.setitem(sys.modules, ...)` which would auto-restore on test teardown. Fix: replace the `sys.modules` + `try/finally` pattern with `monkeypatch.setitem(sys.modules, "...", fake)` and remove `tmp_path` from the signature entirely.
- [x] `Review/Patch` `test_resolve_prompt_rejects_missing_version_field` has unused `tmp_path` fixture parameter — `tests/unit/prompts/test_prompt_modules.py:124` — `tmp_path` is injected but never referenced. Fix: remove `tmp_path` from the signature.
- [x] `Review/Patch` `policy.yaml` notes for `coarse_class` still lists the old 5-label Story 2-4 taxonomy — `router/policy.yaml:22` — string reads `"newsletter / transactional / personal / promotional / spam"` but `personal` and `promotional` are gone and `human / notification / spam_like / unknown` were added. Fix: update the notes string to reflect the current 6-label taxonomy.
- [x] `Review/Patch` AC-9 test suite missing rejection tests for `CoarseClassOutput` and `FineClassOutput` confidence out of range — `tests/unit/prompts/test_output_schema_validation.py` — `SensitivityClassOutput` has `test_sensitivity_class_rejects_confidence_above_one` but the parallel tests for `CoarseClassOutput(class_coarse="newsletter", confidence=1.5)` and `FineClassOutput(class_fine="professional", confidence=1.5)` are absent. Both share the same `Field(ge=0.0, le=1.0)` constraint. Fix: add two tests mirroring the existing sensitivity test.
- [x] `Review/Patch` VERSION equality test covers only one mismatch direction — `tests/unit/prompts/test_prompt_modules.py:89-121` — only tests module exports `v2` while requested as `v1`; no test for module exports `v1` while requested as `v2`. Fix: add `test_resolve_prompt_rejects_version_requested_as_v2` that injects `VERSION="v1"` under `coarse_class.v2` and calls `resolve_prompt("coarse_class", "v2")`.
- [x] `Review/Defer` `hermes_aux/v1.py` custom `model_validate_json` override causes double-wrapping on cache hit — `mailbot_api/prompts/hermes_aux/v1.py:31-35` — deferred, pre-existing. The override wraps any input as `text`, so `model_dump_json()` stores `{"text": "<raw>"}` but a cache-hit re-validation wraps the serialized JSON string again as `text`. Currently non-triggerable because `hermes_aux` has no `response_cache_ttl_seconds` in `policy.yaml`. Latent bug if TTL is ever added. Deferred to a future Story-2-10 patch or Epic 5 cache audit.

## Dev Notes

### Disposition: registry already exists; coarse_class stub already exists

- `mailbot_api/prompts/__init__.py` (Story 2-4) has the `resolve_prompt` registry. It currently validates 3 constants (not 4). Story 3-2 extends it.
- `mailbot_api/prompts/coarse_class/v1.py` (Story 2-4 stub) has 5 labels. Story 3-2 spec mandates 6 labels with a renamed field (`label` → `class_coarse`). The stub is REPLACED.
- `mailbot_api/prompts/hermes_aux/v1.py` (Story 2-10) needs `VERSION = "v1"` added per the new contract; otherwise the registry will reject it.

### Field-name conventions — important

- Per Story 3-1's "naming convention" Dev Note: **prompt task types** are `<dim>_class` (`coarse_class`, `fine_class`, `sensitivity_class`), but the **email columns** they write to use `class_<dim>` (`class_coarse`, `class_fine`) or the bare dim (`sensitivity`). So the prompt module is `prompts/coarse_class/v1.py`, the OUTPUT_SCHEMA field is `class_coarse`, and the column is `emails.class_coarse`. The orchestration in Story 3-5 maps `OUTPUT_SCHEMA.field → emails.column` explicitly.
- For sensitivity, the prompt task type is `sensitivity_class` (per `policy.yaml`), the OUTPUT_SCHEMA field is `sensitivity` (per spec), and the column is `emails.sensitivity`. No `_class` suffix on the column or the field — only on the task type.

### Rule M (Anthropic prompt cache) — SYSTEM block discipline

`SYSTEM` is sent verbatim across all calls for the same prompt module. Per Rule M (architecture.md §"Idempotency & caching") the Anthropic ephemeral cache fires when the cumulative prefix (SYSTEM + USER prefix) is byte-identical. So:
- DO NOT interpolate anything into `SYSTEM` (no `f"{some_var}"` even for stable values; use module-level constants if a value is shared across modules).
- DO NOT add a timestamp or version-string into `SYSTEM` — those break the cache.
- The 6-label list and the `class_<dim>` field-name discipline IS in `SYSTEM` (the model is told what to output) — that's safe because it's stable per-version.

### Confidence ranges — strict 0..1 Pydantic validation

Pydantic v2: `Field(ge=0.0, le=1.0)` rejects 1.0+ and negative values at parse time. The Router's response-validation path (Story 2-4's `ask_router`) catches the resulting ValidationError and routes it through `RouterError(code=SCHEMA_VALIDATION_FAILED, retryable=True)` — the schema-fail-retry chain kicks in. So a model that returns `confidence=1.5` will retry once before escalating.

### Why Story 3-2 does NOT update `policy.yaml`

`policy.yaml` entries map task_types → models. Per epic-3 spec, those mappings land when:
- Story 3-3 adds `sensitivity_class` routing (Qwen-locked).
- Story 3-5 adds the remaining `fine_class`, `summary_short`, `importance_scoring`, `action_extraction` to the policy.
- `coarse_class` is already in the policy (Story 2-4).

Story 3-2 is the prompt-module side. Adding `policy.yaml` entries here would create dead config; defer to the stories that actually use them.

### Test layout convention

`tests/unit/prompts/__init__.py` already exists (Story 2-4 created it). Add:
- `tests/unit/prompts/test_prompt_modules.py` — registry-load tests (AC-8)
- `tests/unit/prompts/test_output_schema_validation.py` — schema-rejection tests (AC-9)

### Pre-Review Self-Audit Gate reminder

After dev-story marks this story `review`, the autonomous-epic-run orchestrator runs the Pre-Review Self-Audit Gate (Step 2.3.5). Produce `3-2-prompt-modules-for-ingest-tasks-uniform-ar-pat-5-structure.pre-review.md` with all 5 sections + the 11 Posture Audit sub-checks. §5.4 (multi-consumer) will fire because `coarse_class/v1.py` is replaced — every consumer of `CoarseClassOutput`'s `label` field needs auditing.

### Project Structure Notes

- New files: `mailbot_api/prompts/sensitivity_class/{__init__.py,v1.py}`, `mailbot_api/prompts/fine_class/{__init__.py,v1.py}`, `mailbot_api/prompts/summary_short/{__init__.py,v1.py}`, `mailbot_api/prompts/importance_scoring/{__init__.py,v1.py}`, `mailbot_api/prompts/action_extraction/{__init__.py,v1.py}`, `tests/unit/prompts/test_prompt_modules.py`, `tests/unit/prompts/test_output_schema_validation.py`.
- Modified files: `mailbot_api/prompts/__init__.py` (registry: +VERSION validation, +equality check), `mailbot_api/prompts/coarse_class/v1.py` (replaced), `mailbot_api/prompts/hermes_aux/v1.py` (+VERSION).
- Tests touched by AC-10: any Story 2-4 test that built a `CoarseClassOutput` instance.

### References

- Architecture: `_bmad-output/planning-artifacts/architecture.md` lines 224, 588, 750, 854 (AR-PAT-5 prompt-module shape)
- Story 2-4 registry: `mailbot_api/prompts/__init__.py`
- Story 2-4 stub: `mailbot_api/prompts/coarse_class/v1.py` (will be replaced)
- Story 2-10 hermes_aux: `mailbot_api/prompts/hermes_aux/v1.py` (needs +VERSION)
- Epic 3 spec: `_bmad-output/planning-artifacts/epics.md` lines 1109–1155 (Story 3.2 ACs)
- Rule M: architecture.md §"Idempotency & caching" — Anthropic ephemeral prompt cache discipline

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-epic-run loop (Phase 2, Story 3-2)

### Debug Log References

- pytest baseline (post-Story-3-1): 345 passed + 2 skipped.
- pytest after Story 3-2: **374 passed + 2 skipped** (+29 net new tests: 14 from `test_prompt_modules.py` — 6 parametrized resolves × 2 (load + payload) + 4 registry-error tests — and 14 from `test_output_schema_validation.py`, with +1 from `test_hermes_aux_still_loads_post_story_3_2_registry_extension`).
- ruff check: clean across `mailbot_api/`, `tests/`, `scripts/`.
- ruff format: all 8 modified/created files re-formatted in place; final pass clean.
- mypy: 56 source files (was 46 before — Story 3-2 added 5 new prompt subpackages, each with `__init__.py` + `v1.py`), no issues.
- boundary check: exit 0 — no violations. Pydantic + Literal imports are project-permitted; no new boundary risk introduced.

### Completion Notes List

#### 2026-06-01 — dev-pass + code-review (autonomous-epic-run, Phase 2 Story 3-2)

- **Registry extension (AC-1)**: `mailbot_api/prompts/__init__.py` now validates 4 constants. `PromptModule` gained a `version: str` field. The new `VERSION == prompt_version` equality check catches the most common silent-failure mode (v1 content accidentally copied into a v2 directory).
- **coarse_class replaced (AC-3, AC-10)**: Story 2-4's 5-label stub (`{label: Literal[newsletter, transactional, personal, promotional, spam]}`) replaced with the 6-label spec (`{class_coarse: Literal[transactional, newsletter, human, notification, spam_like, unknown], confidence: Field(ge=0, le=1)}`). Field name change `label` → `class_coarse` propagated to:
  - `tests/unit/router/test_router.py:115-117` (the `_good_output_json` helper for Router orchestration tests)
  - `tests/unit/router/test_response_cache.py:48` (`newsletter` payload)
  - `tests/unit/router/test_response_cache.py:67` (`spam` → `spam_like` payload — the label name also changed in the new taxonomy)
- **Five new prompt modules created**: `sensitivity_class`, `fine_class`, `summary_short`, `importance_scoring`, `action_extraction`. Each has its own subpackage (`__init__.py` package marker + `v1.py` module). All export the 4-constant shape + `__all__`. SYSTEM blocks are byte-stable across calls per Rule M (Anthropic ephemeral prompt cache).
- **action_extraction `deadline_at` strict-ISO regex**: `r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"` enforced via Pydantic v2 `@field_validator(mode="after")`. Vague dates ("next week") are filtered to `None` by the prompt instruction; malformed ISO strings fail validation and route through the Router schema-fail-retry chain.
- **Comprehensive schema-rejection tests (AC-9)**: 14 scenarios covering ranges, max-lengths, Literal sets, and the strict ISO-8601-Z regex. Also includes positive controls (null deadline accepted, empty actions list accepted).
- **VERSION-mismatch test pattern**: uses `sys.modules` monkey-patching to inject a fake module with `VERSION = "v2"` registered under `coarse_class.v1`, asserts the precise mismatch error message, and restores the real module in the `finally` block. Same pattern used for the missing-VERSION test.
- **Hermes-aux backward-compat**: `hermes_aux/v1.py` patched to add `VERSION = "v1"` + `__all__`. Confirmed loads cleanly via `test_hermes_aux_still_loads_post_story_3_2_registry_extension`.
- **Policy YAML NOT touched**: per Dev Notes, adding `policy.yaml` entries for the 5 new task types creates dead config (no caller until Stories 3-3 / 3-5). Deferred to those stories.

#### Final gate state (post code-review)

- **pytest**: **379 passed + 2 skipped** (+5 net from CR patches: CR-1 empty SYSTEM, CR-1 empty USER_TEMPLATE, CR-6 coarse confidence range, CR-6 fine confidence range, CR-7 reverse VERSION mismatch).
- **ruff check**: All checks passed (project-wide).
- **ruff format**: All touched files formatted.
- **mypy**: 56 source files, no issues.
- **scripts/check_boundaries.py**: exit 0.

#### Code-review subagent (claude-sonnet-4-6) findings — 7 patched, 1 deferred

- **CR-1 registry empty-string guard PATCHED**: `mailbot_api/prompts/__init__.py` now applies `if not isinstance(...) or not value` to SYSTEM and USER_TEMPLATE, matching the existing VERSION guard pattern. Two new tests (`test_resolve_prompt_rejects_empty_system`, `test_resolve_prompt_rejects_empty_user_template`) verify the rejection paths.
- **CR-2 tautological assertion PATCHED**: `test_hermes_aux_still_loads_post_story_3_2_registry_extension` now asserts two distinct substrings (`"auxiliary"` AND `"text-processing"`), both verified present in the hermes_aux SYSTEM block.
- **CR-3 sys.modules monkey-patch refactor PATCHED**: all 6 registry-error tests now use `monkeypatch.setitem(sys.modules, ...)` with auto-restore on teardown. `try/finally` boilerplate removed. New shared helper `_build_fake_module(name, *, version)` deduplicates fake-module construction across the 5 tests.
- **CR-4 unused tmp_path PATCHED**: removed `tmp_path` from `test_resolve_prompt_rejects_version_mismatch` and `test_resolve_prompt_rejects_missing_version_field` signatures.
- **CR-5 policy.yaml notes PATCHED**: `router/policy.yaml` coarse_class entry now reflects the new 6-label taxonomy (transactional / newsletter / human / notification / spam_like / unknown) and cites Story 3-2.
- **CR-6 confidence-range tests PATCHED**: added `test_coarse_class_rejects_confidence_above_one` and `test_fine_class_rejects_confidence_above_one` mirroring the existing SensitivityClassOutput test.
- **CR-7 reverse VERSION mismatch test PATCHED**: added `test_resolve_prompt_rejects_version_mismatch_reverse` — injects `VERSION="v1"` under `coarse_class.v2` registry path and confirms the mismatch error with the correct directional message.
- **CR-8 hermes_aux double-wrap on cache hit DEFERRED**: pre-existing Story 2-10 latent bug. Currently non-triggerable because `hermes_aux` has no `response_cache_ttl_seconds` in `policy.yaml`. Flagged to a future cache audit (Story 6-N or Epic 5 followup).
- **Refactor side effect**: introduced module-level `_FakeOut(BaseModel)` helper class consolidating the per-test fake schema (was previously redeclared in each test). Reduces the diff surface for future test additions.
- **Style fix during refactor**: moved `import sys` and `import types` from per-test function bodies to module top to satisfy ruff F821 under `from __future__ import annotations`.

- **Step 2.4.5 UI-Scope**: N/A — no graphical frontend.
- **Step 2.4.6 File-List-vs-git**: PASS — verified §2 of pre-review + post-CR-patch state.
- **Step 2.4.7 Middleware-Real-Bootstrap (MailBot reframing)**: N/A — Story 3-2 ships pure prompt modules; no `ask_router` call sites, no DB writes, no HTTP endpoints. Pydantic validation IS the producer boundary; integration tests use the real Pydantic constructors directly.
- **Step 2.4.8 Verbose-Row Truncation**: applied — sprint-status row stays terse.
- **Step 2.4.5 UI-Scope**: N/A — no graphical frontend.
- **Step 2.4.6 File-List-vs-git**: PASS — all File List paths present in working tree.
- **Step 2.4.7 Middleware-Real-Bootstrap (MailBot reframing)**: N/A — Story 3-2 ships pure prompt modules (no Router call sites, no DB writes, no Verb endpoints). The schema-rejection tests (`test_output_schema_validation.py`) exercise the Pydantic boundary directly without mocking; the registry-load tests (`test_prompt_modules.py`) use real imports.
- **Step 2.4.8 Verbose-Row Truncation**: applied — sprint-status row is terse; full narrative here.

### File List

**Created:**

- `mailbot_api/prompts/sensitivity_class/__init__.py` — package marker
- `mailbot_api/prompts/sensitivity_class/v1.py` — Qwen-locked sensitivity classifier prompt (3 labels, cautious bias)
- `mailbot_api/prompts/fine_class/__init__.py` — package marker
- `mailbot_api/prompts/fine_class/v1.py` — fine-grained human-class refiner (6 labels)
- `mailbot_api/prompts/summary_short/__init__.py` — package marker
- `mailbot_api/prompts/summary_short/v1.py` — Twitter-length defender-tone summary (≤ 280 chars)
- `mailbot_api/prompts/importance_scoring/__init__.py` — package marker
- `mailbot_api/prompts/importance_scoring/v1.py` — 0..100 score + ≤ 5 signal tags
- `mailbot_api/prompts/action_extraction/__init__.py` — package marker
- `mailbot_api/prompts/action_extraction/v1.py` — nested `ActionItem` model + strict ISO-8601 Z deadline regex
- `tests/unit/prompts/test_prompt_modules.py` — 6 parametrized resolve tests + 6 payload-validation tests + 3 registry-error tests
- `tests/unit/prompts/test_output_schema_validation.py` — 14 schema-rejection / positive-control tests

**Modified:**

- `mailbot_api/prompts/__init__.py` — registry now validates 4 constants including `VERSION`; `PromptModule` gained `version: str` field; mismatch + missing-VERSION error messages added; CR-1: SYSTEM and USER_TEMPLATE now also rejected when empty
- `mailbot_api/prompts/coarse_class/v1.py` — replaced Story 2-4's 5-label stub with the 6-label spec-conformant body; renamed field `label` → `class_coarse`
- `mailbot_api/prompts/hermes_aux/v1.py` — added `VERSION = "v1"` + `__all__` for the new 4-export contract
- `router/policy.yaml` — CR-5: coarse_class notes updated to reflect the new 6-label taxonomy (post-Story-3-2)
- `tests/unit/router/test_router.py` — `_good_output_json()` updated to `{class_coarse: "newsletter", ...}` shape
- `tests/unit/router/test_response_cache.py` — two cached payloads updated to the new field name + the `spam` → `spam_like` label rename
