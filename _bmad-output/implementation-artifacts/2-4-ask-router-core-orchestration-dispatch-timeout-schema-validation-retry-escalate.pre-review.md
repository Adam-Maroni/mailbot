# Pre-Review Self-Audit — 2-4-ask-router-core-orchestration

**Generated:** 2026-06-01 by claude-opus-4-7
**Story file:** _bmad-output/implementation-artifacts/2-4-ask-router-core-orchestration-dispatch-timeout-schema-validation-retry-escalate.md
**Status at audit time:** review

## 1. AC-vs-code drift scan

- **AC-1 Adapter registry:** MATCH — `mailbot_api/router/registry.py` with `register_adapter` / `get_adapter` / `init_default_adapters` / `_reset_registry_for_test`.
- **AC-2 Pricing skeleton:** MATCH — `mailbot_api/router/pricing.py` returns 0.0 for Qwen + unknown, placeholder rates for Anthropic; cached_input applied.
- **AC-3 Prompt-module registry:** MATCH — `mailbot_api/prompts/__init__.py` exports `resolve_prompt` + `PromptResolutionError`; `coarse_class/v1.py` stub ships.
- **AC-4 Escalation chain:** MATCH — `next_tier()` returns the canonical Qwen → Haiku → Opus → None chain.
- **AC-5 ask_router core:** MATCH — `router.py` implements the layered chain: timeout (no retry), schema fail (1 retry, stricter), escalation (recurse with next_tier + escalated_from_<X> reason), provider error, catch-all → PROVIDER_ERROR.
- **AC-6 verb shim:** MATCH — `mailbot_api/verbs/ask_router.py` re-exports.
- **AC-7 router/__init__.py public API:** MATCH — exports only `ask_router`.
- **AC-8 lifespan adapter init:** MATCH — `init_default_adapters()` called after policy load.
- **AC-9 record_router_call in finally:** MATCH — every code path hits the finally; verified by test row counts.
- **AC-10 Unit tests:** MATCH — all 12 listed scenarios covered in `test_router.py` + `test_registry.py` + `test_escalation.py` + `test_pricing.py`.
- **AC-11 No boundary updates needed:** CONFIRMED.
- **AC-12 All gates green:** 232 tests pass + 2 opt-in skipped; ruff clean; mypy --strict (33 files); boundary exit 0.

One mid-implementation drift fix: `_ESCALATED_FROM_RE` in `audit.py` (Story 2-1) didn't accept colons. Model id `qwen2.5:3b-instruct-q4_K_M` contains `:`. Regex updated to `r"^escalated_from_[\w.:\-]+$"`. The test for valid escalated_from values in `test_audit.py` already passed because it used a `-`-separated value; the implementation was just stricter than needed. This is a forward-compatible widening.

## 2. File-List-vs-git diff check

All 13 created files exist on disk per `git status`. All 2 modified files (`main.py`, `audit.py`) reflect the lifespan + regex update. No untracked-but-missing-from-File-List entries.

## 3. Adversarial self-review

- **[MEDIUM] Escalation recursion records two rows for one logical Router call.** Architecture audit-log expectations may want one row per dispatch (the failed first-tier + the escalated success); my implementation produces both. The test `test_ask_router_schema_failure_then_escalation_succeeds` asserts both rows. Reviewer should confirm two-row semantics is the intended observability shape (vs. one combined row with `model_attempted=[qwen, haiku]`).
- **[MEDIUM] `_dispatch_with_failure_chain` has multiple `return` statements in the `try` block, each followed by the `finally` that writes the audit row.** Verifiable via the test row counts, but cognitively complex. A reviewer may suggest a `result` variable + single `return` at the end. Trade-off: explicit-return is easier to trace branch-by-branch; single-return forces tracking through more state.
- **[MEDIUM] Cost is re-computed (estimate_cost_usd called twice) when retry happens.** Once for the original response, once for the retry response — and both contribute to `cost_usd_estimated` on the same audit row. This is correct (both calls cost money), but reviewer should confirm the cost-usd-estimate aggregation semantics is what we want.
- **[LOW] `max_cost_usd` parameter is unused (lint-suppressed with `# noqa: ARG001`).** Wired in Story 2-8's budget guard. Documented in the param comment; flag for reviewer.
- **[LOW] Mid-call race test (`test_ask_router_uses_dispatch_snapshot_not_swapped_policy`) does not actually test mid-call swap.** It tests sequential calls before/after a swap, which is weaker than testing a swap during an in-flight call. The actual mid-call race is verified in Story 2-2's `test_policy_reload_mid_call_race_snapshot_isolation`. Noted in code comment.
- **[LOW] `_record` helper has 13 keyword arguments.** Could be a Pydantic-validated `RouterCallRow` constructed at call site; my implementation expanded the kwargs at every callsite. Aesthetic choice; not a bug.

## 4. Self-caught issues remediated this audit

- All MEDIUM/LOW items: ESCALATE TO REVIEWER for design confirmation.
- No FIX NOW items uncovered.

## 5. Posture Audit

### 5.1 Lockfile hygiene

requirements.txt unchanged for this story (all deps already in place from 2-1 / 2-2 / 2-3). PASS.

### 5.2 Cross-doc

Architecture line 850 `errors.py` ↔ Story 2-1; line 843 `models.py` ↔ Story 2-3; line 842 `policy.py` ↔ Story 2-2; line 841 `router.py` ↔ this story. All paths match. Pricing (line 844) and budget (line 845) are placeholders/skeletons here; Story 2-6 fills pricing; Story 2-8 fills budget. PASS.

### 5.3 Lifecycle-string check

New event: `event="adapters.startup.registered"` (lifespan). Single success-only event, no paired failure event yet — adapter init currently can't fail at this layer (the only failure would be from `OllamaAdapter` construction, which is side-effect-free per Story 2-3). Acceptable.

### 5.4 Multi-consumer

`ask_router` is the single public API for LLM dispatch. Verified by `router/__init__.py` exporting only that name. `verbs/ask_router.py` re-exports it for the verb-registration surface. PASS.

### 5.5 Screenshot-perception — N/A.

### 5.6 Upstream-contract

`ask_router` signature is the canonical contract for every downstream Router caller. Stories 2-5 (lanes), 2-7 (cache), 2-8 (budget) will wrap or delegate to this function. Adding kwargs is non-breaking; changing the return shape would break every caller. Test coverage proves all current branches return `RouterResult`. PASS.

### 5.7 Module-mutable-state

`_ADAPTER_REGISTRY: dict[str, ModelAdapter]` is intentional mutable state with `register_adapter` as the single writer + `_reset_registry_for_test` for test isolation. Consistent with PORTING.md §5.7 overlay (single-writer module-level container with named test helper). PASS.

### 5.8 Dev-fixture parity

Test policy uses `tasks.coarse_class.escalate: {true|false}` parametric — matches production policy.yaml shape. PASS.

### 5.9 Grep-verify cited figures

"232 tests pass" — verified. "33 source files" mypy — verified. PASS.

### 5.10 Producer-boundary contract

Adapter response → AdapterResponse Pydantic → schema-validated against prompt's OUTPUT_SCHEMA → typed RouterResult.output. Multi-layered. PASS.

### 5.11 Git-evidence consistency

Story 2-4 net: 13 new + 2 modified. Production code: ~430 lines across 7 new files. Test code: ~420 lines across 4 new test files. Ratio ~0.98. PASS.

### Summary

| Check | Status |
|---|---|
| 5.1 lockfile | PASS |
| 5.2 cross-doc | PASS |
| 5.3 lifecycle-string | PASS (no failure event yet — by design) |
| 5.4 multi-consumer | PASS |
| 5.5 screenshot | N/A |
| 5.6 upstream-contract | PASS |
| 5.7 module-mutable | PASS |
| 5.8 fixture parity | PASS |
| 5.9 grep-verify | PASS |
| 5.10 producer-boundary | PASS |
| 5.11 git-evidence | PASS |
