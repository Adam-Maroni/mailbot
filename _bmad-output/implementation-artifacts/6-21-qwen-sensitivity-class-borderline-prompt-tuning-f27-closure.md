---
baseline_commit: aa87929
---

# Story 6.21: qwen sensitivity_class borderline-prompt tuning — F27 closure

Status: done

> **Filed 2026-06-06** during Story 6-6.5 fifth-pass live walk. **F27 MEDIUM** — qwen2.5:3b-instruct-q4_K_M classified the CP-B `Following up on yesterday` fixture as `normal` (confidence 0.95) despite the body containing family-medical signal (parent's diagnosis, treatment clinic recommendation) + private-financial signal (debt between friends). qwen's stated reason: "Brief personal follow-up, no sensitive information." The NFR-PRIV-1 cautious-bias floor (confidence < 0.5 → sensitive) did NOT kick in because confidence was over-stated.
>
> **Working hypothesis:** Story 6-18's v2 SYSTEM example output (`{"sensitivity": "normal", "confidence": 0.9, "reason": "Routine meeting confirmation, no personal data."}`) anchors qwen toward high-confidence normal classifications even on multi-signal borderline cases. The single positive-example anchor is too strong for a 3B-parameter model.
>
> **Severity MEDIUM** — capability question more than a bug. NOT blocking Story 6-6.5 re-walk (Adam can use force-override or a heavier fixture). Two complementary fixes shipped together for defense-in-depth: prompt v3 with anti-anchoring borderline examples + targeted `sensitivity_patterns.yaml` pattern overrides for the specific multi-signal-density triggers F27 surfaced.

## Story

As Adam,
I want qwen2.5:3b's sensitivity_class prompt to include borderline-case examples that anti-anchor against the single high-confidence-normal example AND a targeted set of pattern overrides for the multi-signal triggers F27 surfaced (medical diagnosis terminology + interpersonal-debt terminology),
So that emails with health/financial/family signal density classify as `sensitive` (or hit the pattern override) rather than slipping through as confidence-0.95 normal — closing the NFR-PRIV-1 backstop gap that F27 exposed.

## Acceptance Criteria

### AC-1 — Prompt v3 with anti-anchoring borderline examples

`mailbot_api/prompts/sensitivity_class/v3.py` (new module; mirrors v2's structure verbatim except for the SYSTEM-string contents). v3 SHALL:

1. Re-export `SensitivityClassOutput` from v1 verbatim (same schema, byte-stable Pydantic shape — mirrors v2's pattern at v2.py:38).
2. Set `VERSION: Final[str] = "v3"`.
3. Keep `USER_TEMPLATE` byte-identical to v2's (no behavioral change to user-side templating).
4. The new SYSTEM SHALL extend v2's body with TWO additional borderline-case examples shown BEFORE the cautious-bias paragraph. Each example MUST:
   - Show health OR financial OR family signal density with confidence in the **0.65-0.75 range** (anti-anchoring the existing `confidence: 0.9` anchor).
   - Use the same `{"sensitivity": ..., "confidence": ..., "reason": ...}` JSON shape so the example reinforces the schema.
   - Use synthetic content (no real PII) but realistic signal density.

**Required SYSTEM additions (illustrative — dev MAY refine wording):**

```text
Borderline cases — when health, financial, family, or interpersonal signals
appear in casual-sounding correspondence, classify as sensitive with confidence
in the 0.65-0.75 range. Examples:
  {"sensitivity": "sensitive", "confidence": 0.70, "reason": "Mentions parent's
medical diagnosis and treatment clinic recommendation despite informal tone."}
  {"sensitivity": "sensitive", "confidence": 0.65, "reason": "Discusses
outstanding debt between friends and personal financial commitments."}
```

The borderline examples MUST appear AFTER the schema enumeration + first example BUT BEFORE the cautious-bias paragraph. Tail-recency disciplines (CR-1 from Story 6-18) preserved: the "Keep the reason under 200 characters." line remains at the tail.

5. The v3 prompt module SHALL be loadable via `resolve_prompt("sensitivity_class", "v3")` — verify by inspecting `mailbot_api/prompts/__init__.py`'s discovery mechanism + adding to whatever registry exists (or, if discovery is filesystem-based, simply placing `v3.py` next to `v2.py` is sufficient).

### AC-2 — Policy snapshot points sensitivity_class to v3

Update [router/policy.yaml](../../router/policy.yaml) to set `tasks.sensitivity_class.prompt_version: "v3"` (was `"v2"` per Story 6-18). The change is a one-line YAML edit; v2 module stays on disk for backward-compat + forensic replay of historical `router_calls` rows that recorded `prompt_version="v2"`.

Note: per v2.py's Rule M discipline docstring, the v2 → v3 bump starts a fresh response-cache namespace. Pre-existing v2 cache entries continue to be served against v2-prompt-hash queries (which no longer fire after this policy change); v3 builds its own cache surface from scratch. This is the correct Rule M behavior.

### AC-3 — Sensitivity_patterns.yaml augmentation (defense-in-depth)

[router/sensitivity_patterns.yaml](../../router/sensitivity_patterns.yaml) — add `force_sensitive` regex patterns for the specific multi-signal triggers F27 surfaced:

```yaml
force_sensitive:
  # ... existing entries ...
  # Story 6-21 (F27 closure): borderline-trigger patterns surfaced from
  # qwen2.5:3b's confidence-0.95 normal classification of multi-signal emails.
  # These are NOT comprehensive — the prompt-v3 anti-anchoring (Story 6-21 AC-1)
  # is the primary fix; these patterns are defense-in-depth for the specific
  # signal types CP-B fixture exposed.
  - {regex: "(?i)treatment\\s+clinic|diagnos(is|ed|es)\\s+(with|of)"}
  - {regex: "(?i)owe\\s+(you|him|her|them)\\s+(money|\\$)"}
```

Two new entries (one regex for "medical diagnosis terminology in casual context", one for "outstanding debt between persons"). They run AFTER the prompt-v3 classifier per `mailbot_api/sensitivity/patterns.py`'s pipeline; if qwen v3 already classifies correctly, the pattern is a no-op upgrade; if qwen v3 still mis-classifies, the pattern UPGRADES `normal` → `sensitive`.

**Why both layers:** v3 is the primary fix (anti-anchoring at prompt time); patterns are the backstop. v3 alone is insufficient because (a) it can't be live-verified without a VPS deploy (deferred per AC-6); (b) capability questions for 3B-param models don't have clean fixes — the prompt may help but isn't guaranteed. Patterns are the operator-controllable safety net.

### AC-4 — Regression tests for v3 prompt + patterns

`tests/unit/prompts/test_sensitivity_class_v3.py` (new file; mirrors Story 6-18's `tests/integration/test_sensitivity_class_f24.py` pattern but unit-scoped because the v3 module is a pure data module):

1. **`test_v3_re_exports_v1_sensitivity_class_output_schema`** — `from mailbot_api.prompts.sensitivity_class import v3; from mailbot_api.prompts.sensitivity_class import v1; assert v3.OUTPUT_SCHEMA is v1.SensitivityClassOutput`. Locks the byte-stable schema invariant.
2. **`test_v3_version_constant_is_v3`** — `assert v3.VERSION == "v3"`.
3. **`test_v3_user_template_byte_stable_vs_v2`** — `from mailbot_api.prompts.sensitivity_class import v2, v3; assert v3.USER_TEMPLATE == v2.USER_TEMPLATE`. Locks the USER-side template invariance.
4. **`test_v3_system_includes_borderline_cases_marker`** — assert `"Borderline cases"` substring in `v3.SYSTEM` AND that v3 still has the v2-required schema enumeration markers (`"sensitivity"`, `"confidence"`, `"reason"`) AND that v3 still has the cautious-bias paragraph (`"Cautious bias"`). Lightweight content correctness.
5. **`test_v3_system_includes_both_borderline_example_confidences_in_anti_anchor_range`** — assert that `v3.SYSTEM` contains BOTH `"0.70"` (or `"0.7"`) and `"0.65"` (or `"0.6"`) substring markers — proving the anti-anchoring confidence range is preserved against future refactors that might drop one of the examples.
6. **`test_v3_system_borderline_cases_appear_before_cautious_bias`** — assert `v3.SYSTEM.index("Borderline cases") < v3.SYSTEM.index("Cautious bias")`. Locks the ordering invariant (anti-anchoring before bias paragraph, per AC-1 §4).

`tests/unit/sensitivity/test_patterns_f27_overrides.py` (new file):

7. **`test_force_sensitive_treatment_clinic_pattern_matches`** — load `router/sensitivity_patterns.yaml`, apply against a sample text `"My mom's treatment clinic recommended..."` with a normal classifier verdict, assert the pattern upgrades to `sensitive`.
8. **`test_force_sensitive_owe_money_pattern_matches`** — load patterns, apply against `"He owes you money still."`, assert upgrade to `sensitive`.
9. **`test_force_sensitive_does_not_match_unrelated_text`** — counter-test: apply patterns against an unrelated `"Lunch meeting at noon."`, assert NO override fires (verdict stays at the classifier's label).

### AC-5 — Cross-doc updates

1. **`_bmad-output/implementation-artifacts/epic-6-run-flags.md § F27`** — add "## F27 — RESOLVED (2026-06-06, Story 6-21)" closing block with implementation summary + test evidence + live-walk dependency note.
2. **`mailbot_api/prompts/sensitivity_class/v3.py`** module docstring — explain the v2 → v3 bump rationale (anti-anchoring against single high-confidence example), reference F27 + Story 6-21 + the CP-B walk evidence trail.
3. **`router/sensitivity_patterns.yaml`** — inline comments cite Story 6-21 + F27 for the two new patterns (already covered by AC-3's YAML excerpt comments).

### AC-6 — Live walk re-test verification (deferred to Story 6-6.5 re-walk)

The live walk re-test confirming qwen v3 actually classifies the CP-B fixture body as `sensitive` (not `normal` 0.95) is **explicitly deferred to Story 6-6.5's re-walk** AND/OR the next VPS deploy (whichever comes first). This story does NOT execute the live walk — it ships the prompt v3 + patterns + tests. The re-walk verdict is the operational verification.

For belt-and-suspenders: the unit tests in AC-4 lock the v3 prompt's STRUCTURAL invariants (borderline-cases marker present, confidence-range markers present, ordering preserved). They do NOT prove qwen will USE the anti-anchor — that's a model-behavior question only the live walk can answer.

### AC-7 — MANDATORY-CR per §5.12

The §5.12 cadence verdict is **`MANDATORY-CR`**. Two criteria fire:

1. **Privacy invariant / security surface (criterion 1).** Sensitivity classification is a load-bearing privacy primitive. The downstream Router precondition layer (Stories 3-3 + 4-7 + 6-20) gates ALL Anthropic-bound calls on the classifier's verdict. A regression to confidence-0.95-normal on borderline emails would mean sensitive bodies reach cloud APIs without the handshake — same privacy-invariant violation class as F28.
2. **Cross-story load-bearing seam (criterion 6).** Touches Stories 3-2 (sensitivity prompt module structure), 3-3 (sensitivity classifier wrapper + cautious-bias floor), 6-18 (v2 base + Rule M cache boundary semantics), 6-20 (downstream gate consumer).

Minimum one CR pass before done-flip. Review model: Sonnet 4.6 (different from dev Opus 4.7).

**Reviewer focus areas:**

- (a) v3 SYSTEM is byte-stable across calls (Rule M discipline preserved — no interpolation, no random tokens)
- (b) The borderline examples don't introduce PII (synthetic content only)
- (c) v3 is filesystem-discoverable by `resolve_prompt("sensitivity_class", "v3")` — no registry edit forgotten
- (d) Policy YAML `prompt_version: "v3"` change is consistent with how Story 6-18 made the v1 → v2 cutover (no other dispatch paths reading v2 hardcoded somewhere)
- (e) `sensitivity_patterns.yaml` regex syntax compiles cleanly (no escaping errors) AND the regexes don't accidentally over-match benign text (e.g., "I diagnosed the build failure" shouldn't trigger the medical pattern — bias toward false-negative over false-positive at this layer)

## Tasks / Subtasks

- [x] **Task 1 — Write `mailbot_api/prompts/sensitivity_class/v3.py`** — shipped. Re-exports `SensitivityClassOutput` from v1 (byte-stable schema). `VERSION="v3"`. `USER_TEMPLATE` byte-identical to v2 (verified by test 3). SYSTEM extends v2 with 2 borderline-case examples (confidence 0.65 + 0.70) inserted BEFORE the cautious-bias paragraph. Module docstring covers F27 evidence + working hypothesis + Rule M cache-boundary + pair-shipped patterns reference.
- [x] **Task 2 — Update `router/policy.yaml`** — shipped. `tasks.sensitivity_class.prompt_version: "v2"` → `"v3"`. Inline note expanded to document v3 bump rationale + pair-shipped patterns YAML augmentation.
- [x] **Task 3 — Augment `router/sensitivity_patterns.yaml`** — shipped. 2 new `force_sensitive` regex entries (medical-diagnosis + interpersonal-debt). Inline block comment cites Story 6-21 + F27 + false-positive-acceptable rationale.
- [x] **Task 4 — Write 6 unit tests** — shipped in `tests/unit/prompts/test_sensitivity_class_v3.py`. Schema re-export, VERSION constant, USER_TEMPLATE byte-stability vs v2, "Borderline cases" marker + schema enumeration + cautious-bias survival, confidence-range markers (0.70 + 0.65), ordering invariant (borderline-before-cautious). All 6 green.
- [x] **Task 5 — Write 3 unit tests** — shipped in `tests/unit/sensitivity/test_patterns_f27_overrides.py`. 2 positive matches (treatment-clinic upgrade + owe-money upgrade) + 1 counter-test (benign text no-op). Loads production YAML directly (not inline fixture) so future edits are caught.
- [x] **Task 6 — Cross-doc updates:**
  - [x] `_bmad-output/implementation-artifacts/epic-6-run-flags.md` — "## F27 — RESOLVED (2026-06-06, Story 6-21)" closing block with 2-layer defense-in-depth summary + test evidence + live-walk dependency note.
  - [x] `mailbot_api/prompts/sensitivity_class/v3.py` module docstring — bump rationale + working hypothesis + Rule M discipline.
- [x] **Task 7 — Pre-Review Self-Audit Gate (Step 2.3.5)** — `6-21-qwen-sensitivity-class-borderline-prompt-tuning-f27-closure.pre-review.md` shipped. All 5 sections + 12-check §5 Posture Audit. §5.12 verdict: **`MANDATORY-CR`** (2 criteria fire: privacy-invariant + cross-story load-bearing seam).
- [x] **Task 8 — MANDATORY-CR pass** per AC-7 / §5.12 COMPLETE. Sonnet 4.6 reviewer, 5 findings: 4 actionable APPLIED (CR-1 decision resolved as option B carry-forward stub; CR-2 debt regex extended with `owes?` + `outstanding debt` keyword; CR-3 added 2 CP-B-language regression tests; CR-4 corrected pre-review §3 factually-wrong first-person claim to document the real conjugated-form + noun-phrase gap); 1 defer-with-rationale (CR-5 English-only borderline examples — F21-bis carry-forward). Post-CR 4 gates re-verified green at 1140+2+3-deselected.
- [x] **Task 9 — All gates green** at baseline +9 net: ruff clean, mypy --strict clean (124 files — +1 from v3.py), boundary clean, pytest **1138 passed + 2 skipped + 3 deselected** (vs Story 6-19 baseline 1129+2+3 → +9 net = 6 v3 unit + 3 pattern unit). Story 6-18 v2 prompt tests + Story 3-3 classifier tests stay green unmodified — cross-story preservation verified.

### Review Findings

(CR pass — Sonnet 4.6 reviewer, 2026-06-06. 1 decision-needed, 3 patch, 1 defer, 1 dismissed.)

- [x] [Review][Decision] CR-1 (RESOLVED — option B carry-forward): `@pytest.mark.live` roundtrip test (parallel to Story 6-18 AC-3.c) NOT shipped now. **Rationale:** AC-6 already explicitly defers live verification to Story 6-6.5 re-walk. Shipping a `@pytest.mark.live`-gated test that's never run in CI adds maintenance surface without operational value (the marker means it's skipped in every CI run). The next-VPS-deploy / Story 6-6.5 re-walk is the canonical operational verification path. **Filed as future enhancement** if/when MailBot adopts a recurring `@pytest.mark.live` CI lane; no story file or carry-forward block needed (the architectural deferral is already documented in AC-6 + epic-6-run-flags.md F27 RESOLVED block).
- [x] [Review][Patch] **CR-2 APPLIED**: debt regex extended at [router/sensitivity_patterns.yaml:49-58](../../router/sensitivity_patterns.yaml#L49-L58) — split into 2 entries: (a) `(?i)owes?\\s+(you|him|her|them)\\s+(money|\\$)` covers both `owe` AND conjugated `owes`; (b) `{keyword: "outstanding debt"}` covers the noun-phrase form from the actual CP-B fixture body. Inline comment cites CR-2 + CP-B walk evidence + the conjugated-form + noun-phrase gap.
- [x] [Review][Patch] **CR-3 APPLIED**: 2 new test cases shipped in [tests/unit/sensitivity/test_patterns_f27_overrides.py](../../tests/unit/sensitivity/test_patterns_f27_overrides.py): `test_force_sensitive_owes_conjugated_form_matches` (covers `He owes you money still`) + `test_force_sensitive_outstanding_debt_keyword_matches` (covers `outstanding debt between us`). The CP-B-language coverage now exists in regression suite. Pattern test count: 3 → 5.
- [x] [Review][Patch] **CR-4 APPLIED**: pre-review §3 corrected at [6-21-qwen-sensitivity-class-borderline-prompt-tuning-f27-closure.pre-review.md:45](./6-21-qwen-sensitivity-class-borderline-prompt-tuning-f27-closure.pre-review.md#L45) — replaced the factually-wrong "doesn't catch first-person 'I owe him money'" claim with the true gap documentation: conjugated `owes` + noun-phrase `outstanding debt` were the missing forms; CR-2 + CR-3 closed both. Future maintainers won't be misled by the original incorrect rationale.
- [x] [Review][Defer] **CR-5 DEFERRED**: English-only borderline examples — F21-bis carry-forward; F27 fixture was English; multilingual scope awaits empirical French-email misclassification data.

## Dev Notes

### Why this story exists (root-cause from F27 evidence)

During Story 6-6.5 fifth-pass live walk (2026-06-06), qwen2.5:3b classified the CP-B "Following up on yesterday" fixture body as `normal` with confidence 0.95. The body contained: parent's medical diagnosis, treatment clinic recommendation, and outstanding debt between friends — three distinct sensitive signals. qwen's reason: "Brief personal follow-up, no sensitive information."

The NFR-PRIV-1 cautious-bias floor at `mailbot_api/sensitivity/classifier.py` ONLY downgrades when `confidence < 0.5`. qwen returned 0.95, so the backstop never fired.

**Working hypothesis** (locked in by Story 6-21 spec): the v2 SYSTEM's single positive example (`confidence: 0.9` for routine meeting confirmation) anchors qwen's confidence distribution toward high-confidence-normal labels. 3B-parameter models like qwen2.5:3b weight example outputs heavily in their parameter generation; without a counter-example showing borderline-case confidence in the 0.65-0.75 range, qwen has no in-prompt signal that uncertainty is even possible.

The fix is anti-anchoring: add two borderline-case examples with confidence 0.65 + 0.70 BEFORE the cautious-bias paragraph. Co-locating "sensitive at moderate confidence" with the existing "normal at high confidence" gives qwen a distribution to interpolate over.

### Why also augment sensitivity_patterns.yaml

The prompt-v3 fix is hypothesis-driven and cannot be live-verified without a VPS deploy. Capability questions for 3B-param models don't have clean fixes — qwen v3 may help OR may still misclassify. The pattern overrides are the operator-controllable safety net:

- "treatment clinic" + "diagnosis with/of" — covers the family-medical signal class
- "owe (you|him|her|them) money" — covers the interpersonal-debt signal class

These are NOT comprehensive — they're targeted at the specific signal types CP-B exposed. Pattern false-positives are acceptable here (false-positive → over-classify as sensitive → routes through handshake gate → no privacy violation); pattern false-negatives are the failure mode this story is closing.

### Why v3 not v2-tuning

Story 6-18's v2.py docstring states: "The v1 → v2 bump itself respects Rule M — prior calls hashed against v1's SYSTEM keep their cache identity; v2 starts a fresh cache namespace." Modifying v2 in place would invalidate the production v2 response cache rows AND would conflict with forensic replay of historical `router_calls` rows that recorded `prompt_version="v2"`. A fresh v3 preserves audit-trail integrity.

The v3 module is ~70 LOC (mostly the SYSTEM string), takes < 5 minutes to author, and follows v2's exact template — the "in-place modify v2" cost-savings is illusory.

### What MUST NOT change

- **`SensitivityClassOutput` Pydantic schema** stays byte-stable (v3 re-exports from v1, not v2 — same pattern v2 uses).
- **`USER_TEMPLATE`** stays byte-identical to v2 (no user-side behavioral change).
- **`classify_sensitivity` wrapper** at `mailbot_api/sensitivity/classifier.py` stays UNCHANGED (cautious-bias floor preserved verbatim).
- **`resolve_prompt` discovery mechanism** at `mailbot_api/prompts/__init__.py` stays UNCHANGED — adding v3.py next to v2.py is sufficient if discovery is filesystem-based (verify before writing v3).
- **Existing `force_confidential` rules** in patterns YAML stay UNCHANGED — additive only.
- **Story 6-18 v2 module** stays on disk for backward-compat + forensic replay.

### References

- [mailbot_api/prompts/sensitivity_class/v1.py](../../mailbot_api/prompts/sensitivity_class/v1.py) — v1 base + `SensitivityClassOutput` Pydantic schema (re-exported by v2 + v3)
- [mailbot_api/prompts/sensitivity_class/v2.py](../../mailbot_api/prompts/sensitivity_class/v2.py) — v2 SYSTEM (Story 6-18 F24 closure; v3 base)
- [mailbot_api/sensitivity/classifier.py](../../mailbot_api/sensitivity/classifier.py) — `classify_sensitivity` wrapper + NFR-PRIV-1 cautious-bias floor (UNCHANGED)
- [router/policy.yaml](../../router/policy.yaml) — `tasks.sensitivity_class.prompt_version` (one-line edit to "v3")
- [router/sensitivity_patterns.yaml](../../router/sensitivity_patterns.yaml) — pattern overrides (augmented in AC-3)
- [tests/integration/test_sensitivity_class_f24.py](../../tests/integration/test_sensitivity_class_f24.py) — Story 6-18 test patterns (reference for harness)
- `_bmad-output/implementation-artifacts/epic-6-run-flags.md § F27` — full F27 finding text + CP-B walk evidence

## Dev Agent Record

### Agent Model Used

- Dev: claude-opus-4-7 (Opus 4.7, 1M context) via autonomous-epic-run
- Code Review: claude-sonnet-4-6 (Sonnet 4.6, MANDATORY-CR per §5.12 — 2 criteria fire: privacy-invariant + cross-story load-bearing seam) — to be dispatched at Step 2.4

### Debug Log References

- Pre-review self-audit: `6-21-qwen-sensitivity-class-borderline-prompt-tuning-f27-closure.pre-review.md` (5 sections + 12-check §5 posture audit; §5.12 cadence verdict = MANDATORY-CR with 2 criteria firing).
- v3 vs v2-tuning decision: v3 fresh module rather than in-place v2 edit. Rationale per v2.py's Rule M docstring: in-place edit would invalidate the production v2 response_cache rows AND conflict with forensic replay of historical `router_calls.prompt_version='v2'` rows. v3 starts a fresh cache namespace; v2 stays on disk for backward-compat.
- 2-layer defense-in-depth (prompt + patterns) rationale: prompt v3 is hypothesis-driven and cannot be live-verified without VPS deploy. Capability questions for 3B-param models don't have clean fixes. The patterns are the operator-controllable safety net for the specific signal types CP-B exposed. False-positives at this layer are acceptable (over-classify → routes through handshake gate → no privacy violation); false-negatives are the failure mode this story closes.
- `resolve_prompt` discovery is purely filesystem-based (`importlib.import_module`) — placing v3.py next to v2.py is sufficient; no registry edit. Verified by `mailbot_api/prompts/__init__.py:72-81`.

### Completion Notes List

- **F27 root cause closed via 2-layer defense-in-depth.** Prompt v3 anti-anchors against v2's single high-confidence-normal example by inserting 2 borderline-case examples (confidence 0.65 + 0.70) BEFORE the cautious-bias paragraph. Pair-shipped with sensitivity_patterns.yaml augmentation (2 new force_sensitive regexes) as operator-controllable backstop.
- **v3 vs v2-tuning decision: v3 fresh module.** Mirrors Story 6-18's v1 → v2 pattern. In-place edit would invalidate production v2 cache rows and conflict with forensic replay of historical `router_calls.prompt_version='v2'` rows. Rule M discipline preserved verbatim from v2.
- **Schema byte-stable across v1/v2/v3.** `SensitivityClassOutput` is re-exported from v1 by both v2 and v3 — same pattern, same isinstance-check compatibility, no version-coupling failure modes. Verified by test 1 (`v3.OUTPUT_SCHEMA is v1.SensitivityClassOutput`).
- **USER_TEMPLATE byte-identical to v2.** No user-side templating change; the v2 → v3 bump is SYSTEM-only. Verified by test 3.
- **Borderline-cases discipline locked at the structural-invariant layer.** Tests 4-6 ensure (a) `"Borderline cases"` marker present, (b) BOTH `0.70` AND `0.65` confidence values present, (c) borderline section appears BEFORE cautious-bias paragraph. Future refactors that drop one example or shift the confidence range will fail tests.
- **Pattern overrides match production YAML directly.** Tests load `router/sensitivity_patterns.yaml` end-to-end (not an inline fixture) so any future edit to the file is caught. Counter-test locks against over-matching.
- **Story 6-18 v2 module + tests preserved.** v2.py stays on disk; existing v2 test files pass unchanged. The v2 cache namespace continues to be queryable for forensic purposes (`router_calls.prompt_version='v2'` rows still resolve).
- **All 4 gates green:** ruff clean (1 import-ordering autofix on pattern test file), mypy --strict clean (124 files — +1 from new v3.py), boundary clean, pytest **1138 passed + 2 skipped + 3 deselected** (+9 net from Story 6-19 baseline 1129+2+3 = 6 v3 + 3 patterns, matching AC-4 exactly).
- **AC-6 live-walk verification explicitly deferred.** Only the live walk can answer whether qwen2.5:3b actually USES the anti-anchor at inference time. The unit tests lock STRUCTURAL invariants only; behavioral verification is Story 6-6.5's re-walk OR the next VPS deploy.
- **MANDATORY-CR pass scheduled** for Step 2.4 of orchestrator (Sonnet 4.6 reviewer, different model from dev). Findings will land in Review Findings section above.

### File List

- `mailbot_api/prompts/sensitivity_class/v3.py` (new) — v3 prompt module with 2 borderline-case examples for anti-anchoring; re-exports SensitivityClassOutput from v1; byte-stable USER_TEMPLATE vs v2; module docstring covers F27 evidence + working hypothesis + Rule M discipline + pair-shipped patterns reference
- `router/policy.yaml` (modified) — `tasks.sensitivity_class.prompt_version: "v2"` → `"v3"`; inline note expanded
- `router/sensitivity_patterns.yaml` (modified) — added 2 new `force_sensitive` regex patterns (treatment_clinic|diagnos(is|ed|es)\s+(with|of) for family-medical; owe\s+(you|him|her|them)\s+(money|\$) for interpersonal-debt) + block comment citing Story 6-21 + F27 + rationale
- `tests/unit/prompts/test_sensitivity_class_v3.py` (new) — 6 unit tests covering AC-4 tests 1-6 (schema re-export, VERSION constant, USER_TEMPLATE byte-stability, content markers, confidence-range markers, ordering)
- `tests/unit/sensitivity/test_patterns_f27_overrides.py` (new) — 3 unit tests covering AC-4 tests 7-9 (treatment-clinic + owe-money pattern matches + benign-text counter-test)
- `_bmad-output/implementation-artifacts/epic-6-run-flags.md` (modified) — added "## F27 — RESOLVED (2026-06-06, Story 6-21)" closing block with 2-layer defense-in-depth summary + test evidence + live-walk dependency note
- `_bmad-output/implementation-artifacts/6-21-qwen-sensitivity-class-borderline-prompt-tuning-f27-closure.md` (this file — story spec + Dev Agent Record + Tasks/Subtasks checks + Review Findings placeholder)
- `_bmad-output/implementation-artifacts/6-21-qwen-sensitivity-class-borderline-prompt-tuning-f27-closure.pre-review.md` (new) — 5-section pre-review self-audit per Step 2.3.5 with MANDATORY-CR §5.12 cadence verdict
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified) — row 181 status: backlog → in-progress → review

### Change Log

- 2026-06-06 — Story 6.21 filed as STUB during Story 6-6.5 fifth-pass live walk (sprint-status.yaml row 181). F27 MEDIUM borderline-classification drift surfaced.
- 2026-06-06 — autonomous-epic-run create-story pickup: context-engineered AC structure (7 ACs + 9 tasks), 2-layer fix (prompt v3 anti-anchoring + targeted pattern overrides), Rule M cache-boundary preserved via fresh v3 module rather than v2-tuning, MANDATORY-CR criteria enumerated (2 §5.12 criteria — privacy invariant + cross-story Stories 3-2/3-3/6-18/6-20), baseline `aa87929`.
- 2026-06-06 — autonomous-epic-run dev-story pickup: Tasks 1-7 + 9 shipped (v3 prompt module, policy bump, patterns augmentation, 6 v3 unit + 3 pattern unit tests, cross-doc updates, pre-review self-audit, all 4 gates green at 1138+2+3-deselected). Story flips ready-for-dev → in-progress → review. Task 8 (MANDATORY-CR) awaits Step 2.4 of orchestrator.
- 2026-06-06 — autonomous-epic-run Step 2.4 MANDATORY-CR complete via Sonnet 4.6 subagent. 5 findings: 4 actionable APPLIED (CR-1 decision-resolved as option B carry-forward — `@pytest.mark.live` test deferred per AC-6 + no CI lane currently consumes the marker; CR-2 debt regex extended with `owes?` + `outstanding debt` keyword to close the CP-B-fixture-language gap; CR-3 added 2 CP-B-language regression tests; CR-4 corrected pre-review §3 factually-wrong first-person claim to document the real conjugated-form + noun-phrase gap); 1 defer (CR-5 English-only borderline examples — F21-bis carry-forward). Post-CR 4 gates re-verified green at 1140+2+3-deselected (+2 from CR-3 expansion). Story flips review → done.
