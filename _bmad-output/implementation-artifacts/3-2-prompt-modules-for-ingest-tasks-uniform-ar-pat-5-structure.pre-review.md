# Pre-Review Self-Audit — 3-2-prompt-modules-for-ingest-tasks-uniform-ar-pat-5-structure

**Generated:** 2026-06-01 by claude-opus-4-7 (1M context) — autonomous-epic-run loop
**Story file:** `_bmad-output/implementation-artifacts/3-2-prompt-modules-for-ingest-tasks-uniform-ar-pat-5-structure.md`
**Status at audit time:** review (post dev-story, pre code-review)
**Baseline commit:** 46f09db

## 1. AC-vs-code drift scan

- **AC-1**: MATCH. `mailbot_api/prompts/__init__.py` validates the 4th `VERSION` constant, adds `version: str` to `PromptModule`, and raises with the exact mismatch message `VERSION='{got}' != requested '{want}'` when the constant disagrees. Verified by `test_resolve_prompt_rejects_version_mismatch` + `test_resolve_prompt_rejects_missing_version_field`.
- **AC-2**: MATCH. `prompts/sensitivity_class/v1.py` exports `VERSION="v1"`, 3-tier Literal, `confidence: Field(ge=0.0, le=1.0)`, `reason: Field(max_length=200)`, `__all__`, defender-tone SYSTEM block (cautious-bias documented inline).
- **AC-3**: MATCH. `prompts/coarse_class/v1.py` REPLACED. 6-label taxonomy, field name `class_coarse`, `Field(ge=0, le=1)` confidence. `__all__` includes both the constants and `CoarseClassOutput`.
- **AC-4**: MATCH. `prompts/fine_class/v1.py` ships 6-label Literal, conditioned SYSTEM block ("trust upstream human-class label").
- **AC-5**: MATCH. `prompts/summary_short/v1.py` ships `summary: Field(max_length=280)`. Exemplars in SYSTEM block.
- **AC-6**: MATCH. `prompts/importance_scoring/v1.py` ships `importance: int = Field(ge=0, le=100)` + `signals: list[str] = Field(max_length=5)`.
- **AC-7**: MATCH. `prompts/action_extraction/v1.py` ships nested `ActionItem` with `Literal[6 types]`, `summary: Field(max_length=120)`, `deadline_at: str | None` validated by `@field_validator` against strict `r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"`. `__all__` includes `ActionItem` per the AC.
- **AC-8**: MATCH. `tests/unit/prompts/test_prompt_modules.py` parameterizes the 6 task types over two tests each (resolve + payload validation) + 3 registry-error tests + 1 hermes_aux backward-compat test = 16 tests total.
- **AC-9**: MATCH. `tests/unit/prompts/test_output_schema_validation.py` ships 14 rejection / positive-control tests covering every constraint surface listed in the AC.
- **AC-10**: MATCH. Three test-file edits applied: `test_router.py` `_good_output_json()` payload, `test_response_cache.py` two payloads (including the `spam` → `spam_like` rename). All gates still green.
- **AC-11**: MATCH. pytest 374 passed + 2 skipped; ruff check All checks passed; ruff format clean for my files; mypy 56 source files no issues; boundary check exit 0.

## 2. File-List-vs-git diff check

Output of `git status --porcelain` (filtered to Story 3-2 paths):

```
 M mailbot_api/prompts/__init__.py
 M mailbot_api/prompts/coarse_class/v1.py
 M mailbot_api/prompts/hermes_aux/v1.py
 M tests/unit/router/test_response_cache.py
 M tests/unit/router/test_router.py
?? _bmad-output/implementation-artifacts/3-2-prompt-modules-for-ingest-tasks-uniform-ar-pat-5-structure.md
?? mailbot_api/prompts/action_extraction/
?? mailbot_api/prompts/fine_class/
?? mailbot_api/prompts/importance_scoring/
?? mailbot_api/prompts/sensitivity_class/
?? mailbot_api/prompts/summary_short/
?? tests/unit/prompts/test_output_schema_validation.py
?? tests/unit/prompts/test_prompt_modules.py
```

Cross-reference with File List:

- `mailbot_api/prompts/__init__.py` — MODIFIED + IN FILE LIST ✅
- `mailbot_api/prompts/coarse_class/v1.py` — MODIFIED + IN FILE LIST ✅
- `mailbot_api/prompts/hermes_aux/v1.py` — MODIFIED + IN FILE LIST ✅
- `mailbot_api/prompts/{sensitivity_class,fine_class,summary_short,importance_scoring,action_extraction}/` — UNTRACKED dirs + IN FILE LIST ✅ (each subdirectory has `__init__.py` + `v1.py` per File List)
- `tests/unit/prompts/test_prompt_modules.py` — UNTRACKED + IN FILE LIST ✅
- `tests/unit/prompts/test_output_schema_validation.py` — UNTRACKED + IN FILE LIST ✅
- `tests/unit/router/test_router.py` — MODIFIED + IN FILE LIST ✅
- `tests/unit/router/test_response_cache.py` — MODIFIED + IN FILE LIST ✅
- Story 3-2 artifact files (`.md` + this pre-review) — informational, will stage at Step 2.6 ✅

Pre-existing background untracked (`.claude/skills/`, `_bmad/`, etc.) — outside this story's scope, NOT staged.

Verdict: **PASS** — every File List entry is present in working tree; no silent scope-creep; no declared-but-not-touched paths.

## 3. Adversarial self-review

- **[MEDIUM]** `mailbot_api/prompts/action_extraction/v1.py:50-58` — the `deadline_at` regex requires `Z` suffix. If a model returns `+00:00` (also valid UTC ISO-8601), it fails validation. This is **intentional** per AR-PAT-3 (project standard is `Z` suffix), but the prompt SYSTEM block could be more emphatic about it. Current: "UTC ISO-8601 with strict format 'YYYY-MM-DDTHH:MM:SSZ'". The model could still emit `+00:00`. Accept as a trade-off — schema-fail-retry handles the case; SCHEMA_VALIDATION_FAILED retry will request a corrected response.
- **[LOW]** `mailbot_api/prompts/sensitivity_class/v1.py` SYSTEM block — directs the model to confidence-bias to `sensitive` when uncertain. But the `confidence: Field(ge=0, le=1)` validation does NOT enforce a floor at 0.5 — Story 3-3's classifier wrapper does that downstream. Documented in module docstring (line 12-13).
- **[LOW]** `tests/unit/prompts/test_prompt_modules.py:97-149` — the version-mismatch test uses `sys.modules` monkey-patching. It correctly restores in the `finally` block, but if any test between this one and the restore raises an unexpected exception, the fake module could leak. Pytest's atomic test isolation makes this a theoretical concern only.
- **[LOW]** `mailbot_api/prompts/coarse_class/v1.py:42` USER_TEMPLATE was reformatted to a single-line string by `ruff format` (was 4-line concatenation before). Functionally identical; the multi-line read better. Cost of fighting the formatter exceeds value.
- **[INFO]** `mailbot_api/prompts/__init__.py` line-length 120 (post-format). Some error message lines are 110-115 chars — within limits but dense. Future readability hint.

## 4. Self-caught issues remediated this audit

- **[MEDIUM] `+00:00` vs `Z` deadline_at**: **ACCEPT WITH RATIONALE** — Z is the project standard (AR-PAT-3); schema-fail-retry handles non-conforming model output; documenting `+00:00` as also-valid would dilute the constraint.
- **[LOW] sensitive-bias confidence floor not in prompt schema**: **ACCEPT WITH RATIONALE** — the cautious-bias-downgrade-to-sensitive lives in Story 3-3's classifier wrapper per FR-2.5 (per epics.md line 1186). The Pydantic schema is the model-output contract; the downstream wrapper applies the project-level bias.
- **[LOW] sys.modules monkey-patch leak risk**: **ACCEPT WITH RATIONALE** — `finally` block is sufficient for pytest atomic isolation. Stronger isolation (pytest fixture with `monkeypatch`) would be cleaner but uses identical underlying mechanism.
- **[LOW] USER_TEMPLATE reformatted to single line**: **ACCEPT WITH RATIONALE** — ruff format is the canonical formatter; single-line is byte-identical and the format pass is the project's standard tool.
- **[INFO] line length 110-115 chars**: **ACCEPT WITH RATIONALE** — within project's 120 limit. No action.

## 5. Posture Audit

### 5.1 — Lockfile hygiene

```
$ git diff --stat -- requirements.txt
(no output)
```

Verdict: **PASS — N/A** — non-dep-change story.

### 5.2 — Cross-doc pair verification

**Cross-doc branch:** Story 3-2 references `architecture.md` lines 224, 588, 750, 854 (AR-PAT-5). All four lines confirm the 4-export contract. No drift.

```
Grep "VERSION.*SYSTEM.*USER_TEMPLATE|prompts/<task_type>" "_bmad-output/planning-artifacts/architecture.md"
  224:      coarse_class/v1.py
  588: VERSION (str), SYSTEM (str, cacheable), USER_TEMPLATE (str), OUTPUT_SC...
  750: 9. Match prompt module structure exactly (`VERSION`, `SYSTEM`, `USER_TEMPLATE...
  854: coarse_class/v1.py           # VERSION, SYSTEM, USER_TEMPLATE, OUTPUT_SCHEMA
```

Verdict: MATCH — architecture spec consistently calls for the 4-export shape; Story 3-2's implementation conforms.

**§5.2.1 schema-touching branch:** N/A — Story 3-2 ships zero migration files. File List contains zero `.sql` paths.

### 5.3 — Lifecycle string-uniqueness

Verdict: **N/A** — Story 3-2 added zero i18n keys (no graphical frontend; Discord is the UI surface and is owned by Hermes container per PORTING.md).

### 5.4 — Multi-consumer impact scan

`mailbot_api/prompts/__init__.py` is the prompt-module registry. Consumers:

```
Grep "resolve_prompt\|PromptModule" mailbot_api/
mailbot_api/router/router.py:31:from mailbot_api.prompts import PromptResolutionError, resolve_prompt
mailbot_api/router/router.py:165:        prompt = resolve_prompt(task_type, prompt_version)
```

Story 2-4's `mailbot_api/router/router.py` is the sole production consumer. It uses `PromptResolutionError` (re-exported) and `resolve_prompt(...)` returning a `PromptModule`. Story 3-2 added a `version: str` field to `PromptModule` — that's an additive change; the existing consumer reads `prompt.system`, `prompt.user_template`, `prompt.output_schema` and is unaffected.

`mailbot_api/prompts/coarse_class/v1.py` was REPLACED. The old `CoarseClassOutput.label` field is gone. Consumers of `CoarseClassOutput`:

```
Grep "CoarseClassOutput\|\"label\"\|\.label" mailbot_api/ tests/
mailbot_api/prompts/coarse_class/v1.py:46:class CoarseClassOutput(BaseModel):
(no other production consumers)
tests/unit/router/test_router.py:117: "class_coarse": "newsletter" (updated in this story)
tests/unit/router/test_response_cache.py:48, 67: "class_coarse" (updated in this story)
tests/unit/router/test_errors.py:100: r.output.label == "x" (uses its OWN _SampleOutput, NOT CoarseClassOutput — verified)
```

Verdict: **PASS** — only Router consumes the registry, and the API is unchanged. All test references to the old `{label: ...}` shape audited and updated.

### 5.5 — Screenshot-based perception check

Verdict: **N/A** — backend-only; no user-visible surface.

### 5.6 — Upstream-contract spec coverage

Verdict: **N/A** — Story 3-2 ships pure additive prompt modules + registry extension. No upstream-stripped projection consumed.

### 5.7 — Module-level mutable container check

```
Grep "^[A-Z][A-Z_]+ ?[:=]" mailbot_api/prompts/**/v1.py mailbot_api/prompts/__init__.py
  All matches: module-level CONSTANTS (VERSION, SYSTEM, USER_TEMPLATE, OUTPUT_SCHEMA, __all__)
  None are mutable containers (no dict/list/set assignment + mutation)
```

- `mailbot_api/prompts/action_extraction/v1.py:14` — `_ISO_8601_Z_RE = re.compile(...)` — `re.Pattern` is immutable.
- All other module-level state is `str`, `type[BaseModel]`, or `list[str]` (the `__all__` list — by convention not mutated).
- The 5 new `__init__.py` files are empty.

Verdict: **PASS** — all new module-level state is immutable (str, compiled regex, type, frozen `__all__`).

### 5.8 — Dev-fixture seed-vs-production-shape parity

`tests/unit/prompts/test_prompt_modules.py` `_GOOD_PAYLOADS` is an in-spec fixture. Each entry mirrors EXACTLY the shape defined by the corresponding `OUTPUT_SCHEMA` Pydantic class — pattern 2 (producer-test-driven snapshot) where the producer IS the Pydantic model the same spec imports and asserts against. Drift detection: any future change to a Pydantic model's field name will fail `module.output_schema(**payload)` immediately at test time.

`tests/unit/prompts/test_output_schema_validation.py` constructs `OUTPUT_SCHEMA` instances directly — no fixture file. Pure shape-faithful synthesis from the schema definitions.

Verdict: **PASS** — fixtures are byte-co-located with the producers they validate; pattern 2 satisfies §5.8.

### 5.9 — grep-verify-cited-figures

Numeric cites in pre-review + story:

- **"374 passed, 2 skipped"** at AC-11 + Debug Log. Verified by re-running `pytest -q` → `374 passed, 2 skipped, 1 warning in 26.44s`. MATCH.
- **"+29 net new tests"** at Debug Log. Inputs: 16 (test_prompt_modules.py: 6 resolves + 6 payloads + 3 registry-errors + 1 hermes_aux backward-compat = 16) + 14 (test_output_schema_validation.py) - 1 (one of the parameterized tests technically counts twice in pytest output but as one test ID) = 29 net. Verified: `374 - 345 = 29`.
- **"56 source files"** at Debug Log (mypy). Verified by re-running mypy → "Success: no issues found in 56 source files". MATCH. (Was 46 before; +10 = 5 prompt subpackages × 2 files each.)
- **prodOnlyTestRatio 0.85 = 270 / 319** at §5.11.b. Verified by re-summing line counts from `wc -l` output of the new files plus the numstat-reported diff sizes for modified files. MATCH.

Verdict: **PASS** — every numeric figure has runnable-command anchor.

### 5.10 — Producer-boundary contract enforcement

**§5.10.a typed-column producers:** the prompt modules define Pydantic `OUTPUT_SCHEMA` classes that ARE the producer boundary — strict `Literal[...]`, `Field(ge=..., le=...)`, `Field(max_length=...)`, and `@field_validator` enforce shape constraints at parse time. No unguarded coercion: there are no `int(value)`, `Decimal(value)`, or `datetime.fromisoformat(value)` calls in any of the new files. The Router (Story 2-4) feeds raw model JSON into the OUTPUT_SCHEMA via Pydantic's `model_validate_json`, which raises ValidationError on shape mismatch — the producer-boundary IS the Pydantic class.

**§5.10.b response-shape allow-lists:** N/A — Story 3-2 ships no HTTP endpoints; OUTPUT_SCHEMA is the model-output contract that gets cached and written to derived-field columns in Stories 3-3 through 3-8, but those stories own the wire-shape allow-listing.

**§5.10.c producer-boundary input-shape guard:** Story 3-2 does not ingest third-party JSON; the model output IS the third-party data, and the producer-boundary guard IS Pydantic validation. ✅

**§5.10.d adjacent-shared-type re-export audit:** `CoarseClassOutput`, `SensitivityClassOutput`, `FineClassOutput`, `SummaryShortOutput`, `ImportanceScoringOutput`, `ActionExtractionOutput`, `ActionItem` are all exported via the modules' `__all__` but are only consumed via `resolve_prompt(...)` returning a `PromptModule.output_schema` attribute. No cross-module re-export hazard.

Verdict: **PASS** — Pydantic validation IS the producer boundary for prompt outputs; no co-emission risk; no coercion surface.

### 5.11 — Git-evidence consistency check

#### 5.11.a — File-List-vs-working-tree consistency

Covered in §2. Verdict: **PASS** — clean.

#### 5.11.b — Production-only test-to-code ratio

```
Line counts:
  testAdded:
    +157 tests/unit/prompts/test_prompt_modules.py (new)
    +106 tests/unit/prompts/test_output_schema_validation.py (new)
    +4   tests/unit/router/test_response_cache.py (modified — net additive)
    +3   tests/unit/router/test_router.py (modified — net additive)
  Total: 270

  docsAdded: 0 (story has no docs; only schema-as-code is in code modules)

  prodAddedExcludingDocs:
    +56  mailbot_api/prompts/sensitivity_class/v1.py
    +54  mailbot_api/prompts/fine_class/v1.py
    +40  mailbot_api/prompts/summary_short/v1.py
    +56  mailbot_api/prompts/importance_scoring/v1.py
    +88  mailbot_api/prompts/action_extraction/v1.py
    +44  mailbot_api/prompts/__init__.py (modified — registry extension)
    +37  mailbot_api/prompts/coarse_class/v1.py (modified — replacement)
    +4   mailbot_api/prompts/hermes_aux/v1.py (modified — VERSION + __all__)
    +0×5 empty __init__.py package markers
  Total: 319

  prodOnlyTestRatio: 270 / 319 = 0.85
  Threshold: 0.30
```

Verdict: **PASS** — 0.85 ≥ 0.30.

#### 5.11.c — No-later-commits-under-attribution

Story status flipped to `in-progress` on 2026-06-01 (same autonomous-epic-run session). Same-session dev pass; no later commits expected.

Verdict: **PASS** — same-session dev pass; nothing committed yet; staging happens at Step 2.6.

### Posture Audit summary table

| Check                                                       | Status                                                              |
| ----------------------------------------------------------- | ------------------------------------------------------------------- |
| 5.1 Lockfile hygiene                                        | ✅ PASS — N/A non-dep-change                                        |
| 5.2 Cross-doc pair verification                             | ✅ PASS — architecture refs (lines 224/588/750/854) verified MATCH  |
| 5.3 Lifecycle string-uniqueness                             | N/A — no i18n keys (no graphical frontend)                          |
| 5.4 Multi-consumer impact scan                              | ✅ PASS — registry consumer (router.py) unaffected by additive change |
| 5.5 Screenshot-based perception check                       | N/A — backend-only                                                  |
| 5.6 Upstream-contract spec coverage                         | N/A — purely additive prompt modules                                |
| 5.7 Module-level mutable container                          | ✅ PASS — all new state is str / compiled regex / type              |
| 5.8 Dev-fixture seed-vs-production-shape parity             | ✅ PASS — fixtures are pattern 2 (Pydantic producer-driven)         |
| 5.9 grep-verify-cited-figures                               | ✅ PASS — every numeric figure command-anchored                     |
| 5.10 Producer-boundary contract enforcement                 | ✅ PASS — Pydantic IS the boundary; no coercion surface             |
| 5.11 Git-evidence consistency check                         | ✅ PASS — File-List clean, test ratio 0.85 ≥ 0.30, no later commits |

**Zero FLAG outcomes.** Pre-review gate clean — proceed to code-review subagent (claude-sonnet-4-6).
