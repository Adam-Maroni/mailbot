# Pre-Review Self-Audit — 6-18-sensitivity-class-prompt-missing-confidence-field-f24-closure

**Generated:** 2026-06-05 20:25 by claude-opus-4-7
**Story file:** _bmad-output/implementation-artifacts/6-18-sensitivity-class-prompt-missing-confidence-field-f24-closure.md
**Status at audit time:** in-progress (post dev-story, pre code-review dispatch)

## 1. AC-vs-code drift scan

- AC-1: MATCH — `mailbot_api/prompts/sensitivity_class/v2.py` SYSTEM block explicitly enumerates `sensitivity`, `confidence`, and `reason` as required JSON fields with type constraints; `VERSION = "v2"`; resolver routes via `policy.yaml prompt_version: "v2"`.
- AC-2: DRIFT — live qwen roundtrip is the bonus AC-3.c test (`pytest.mark.live`), opted-out by default per `addopts = "-m 'not live and not slow'"`. The actual live verification belongs to next VPS deploy walk where the F24 712-row backlog drains. Same disposition as F21/Story 6-14 closure (Task 6 in that story was DEFERRED to VPS — N/A in local dev). Documented in story Completion Notes as the equivalent operational deferral.
- AC-3: MATCH — three regression tests in `tests/integration/test_sensitivity_class_f24.py`: (a) F24 counter-test (missing confidence → SCHEMA_VALIDATION_FAILED both legs), (b) happy path (all three fields → outcome=ok, single adapter call), (c) live roundtrip gated `pytest.mark.live` (opted-out by default).
- AC-4: DRIFT — backlog drain is VPS-side only (production ingest pipeline). N/A in local dev — same as F21's AC-4 in Story 6-14. Will land naturally on next VPS deploy; the previously-failed sensitivity_class calls left no idempotency rows, so emails retry on next ingest tick with v2 prompt eliciting the canonical 3-field JSON.
- AC-5: PARTIAL — sprint-status.yaml row updated to in-progress (still needs done-flip after CR). `epic-6-run-flags.md § F24` flip + walk-record amendment will happen at Phase 2.6 staging (post-CR done-flip). Done in Completion Notes section now.
- AC-6: MATCH — MANDATORY-CR cadence will be dispatched per §5.12 verdict (criteria a + b both fire). Sonnet 4.6 reviewer.

## 2. File-List-vs-git diff check

Per `rtk git status --porcelain`:

```
?? mailbot_api/prompts/sensitivity_class/v2.py
?? tests/integration/test_sensitivity_class_f24.py
 M mailbot_api/sensitivity/classifier.py
 M router/policy.yaml
 M _bmad-output/implementation-artifacts/6-18-sensitivity-class-prompt-missing-confidence-field-f24-closure.md
 M _bmad-output/implementation-artifacts/sprint-status.yaml
```

Cross-reference against story File List (to be filled at done-time):
- `mailbot_api/prompts/sensitivity_class/v2.py` — UNTRACKED (will `git add` at Step 2.6)
- `mailbot_api/sensitivity/classifier.py` — MODIFIED-NOT-STAGED
- `router/policy.yaml` — MODIFIED-NOT-STAGED
- `tests/integration/test_sensitivity_class_f24.py` — UNTRACKED (will `git add` at Step 2.6)
- `_bmad-output/implementation-artifacts/6-18-...-f24-closure.md` — MODIFIED-NOT-STAGED
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — MODIFIED-NOT-STAGED

All accounted for. No phantom or missing paths. Selective staging at Step 2.6 will explicitly add these 6 paths; nothing under workspace/scratch dirs touched.

## 3. Adversarial self-review

- [MEDIUM] mailbot_api/prompts/sensitivity_class/v2.py:24-58 — SYSTEM block contains an explicit example output (`{"sensitivity": "normal", "confidence": 0.9, "reason": "..."}`). One worry: qwen2.5:3b may anchor too strongly on the example values (always returning `confidence=0.9` regardless of actual certainty) — a known instruction-following quirk for small-parameter local models. Mitigation already in place: NFR-PRIV-1 cautious-bias floor at `classifier.py:196` downgrades any `normal + confidence<0.5` to `sensitive`, but an over-anchored `confidence=0.9` defeats that floor. The live AC-2 probe (deferred to VPS walk) is the only way to confirm; design accepts this risk because the alternative (no example) is what caused F24 in the first place.
- [LOW] mailbot_api/sensitivity/classifier.py:36-44 — import comment block explains the v1→v2 lockstep contract but no machine-enforced check that classifier-import-version equals `policy.yaml prompt_version`. If a future polylith mistake bumps policy to v3 but forgets the classifier import, the same isinstance() check failure that originally surfaced would recur silently. Mitigation: the structural test `test_sensitivity_class_v2_system_enumerates_required_fields` would catch it because it asserts `VERSION == "v2"`, but only if the classifier import gets revised. Accept as documented-fragility; a runtime cross-check (compare classifier import VERSION against the resolved policy entry's prompt_version on first dispatch) would be belt-and-suspenders.
- [LOW] tests/integration/test_sensitivity_class_f24.py:200-203 — the F24 counter-test seeds the same `_FakeQwenAdapter` with two identical F24-shape responses (both missing `confidence`). Real qwen2.5:3b at temperature=0 IS deterministic, so this models the production trace correctly. But a future Ollama upgrade that flipped default sampling to temperature>0 could produce stochastic outputs (one leg with confidence, one without) — the test wouldn't catch that because it's hardcoded to the deterministic-loss shape. Accept as scope: this test is the F24 reproducer, not a fuzz harness.
- [LOW] tests/integration/test_sensitivity_class_f24.py:215-220 — the retry-leg user-message assertion (`adapter.call_log[0]["user"] != adapter.call_log[1]["user"]`) is structurally fragile. If the router's retry path changes to NOT widen the user message (e.g., simplified to identical re-call), the test fails noisily but the failure mode (SCHEMA_VALIDATION_FAILED both legs) is unchanged. Accept as audit-trail signal — better to flag the structural change than silently rubber-stamp.
- [INFO] router/policy.yaml:31 — policy notes line bumped to ~3 lines explaining the v1→v2 transition + F24 motivation. Standard for the project (Story 1-9, 6-15 do similar inline rationale).

## 4. Self-caught issues remediated this audit

- §3 [MEDIUM] over-anchoring on example confidence value: **ACCEPT WITH RATIONALE** — the live AC-2.bonus probe (when run) will catch over-anchoring; design tradeoff already documented (alternative = no example = F24 root cause). No code change.
- §3 [LOW] classifier-version vs policy-version drift: **ACCEPT WITH RATIONALE** — current structural test catches the explicit case at test time; a runtime cross-check is gold-plating for a 2026-06-05 fix. Documented in pre-review §5.3 for reviewer to consider.
- §3 [LOW] deterministic-loss-shape coupling in counter-test: **ACCEPT WITH RATIONALE** — F24 reproducer is intentionally scoped to deterministic trace; fuzz harness is a separate concern (would belong in Epic 7 eval).
- §3 [LOW] retry-leg user-message structural assertion fragility: **ACCEPT WITH RATIONALE** — fragility is the audit-trail signal we want; flag is intentional.

## 5. Posture Audit

### 5.1 Lockfile hygiene
N/A — no `requirements.txt` change. The story adds no new dependencies; uses existing pydantic + pytest infrastructure.

### 5.2 Cross-doc consistency
APPLIED — policy.yaml notes string explicitly explains the v1→v2 transition + the F24 root-cause; story file Completion Notes will reference both. The Story 6-18 file's "References" section already cites v1.py, classifier.py, policy.yaml, router.py — all paths still valid post-edit.

### 5.3 Lifecycle-string check
N/A — no schema migration (Pydantic shape unchanged v1→v2; same `SensitivityClassOutput`), no new env var, no FastAPI lifespan touch.

### 5.4 Multi-consumer audit
APPLIED — `SensitivityClassOutput` has ONE consumer (classifier.py line 36-37, line 181 isinstance check). Both consumers updated to v2 import. `VERSION` constant has ONE consumer (classifier.py line 38, line 215 used for `sensitivity_prompt_v` companion column). Updated in lockstep. No other importers of the v1 module exist:

```
$ grep -rn "sensitivity_class.v1" mailbot_api/ tests/ 2>&1 | grep -v __pycache__
(zero hits post-edit — v1 import surface fully migrated to v2)
```

### 5.5 Screenshot-perception check
N/A — no graphical UI surface (PORTING.md marks `<frontend-src>` as N/A).

### 5.6 Upstream-contract check
APPLIED — qwen2.5:3b-instruct-q4_K_M's actual response format (per F24 root-cause probe captured 2026-06-05 in story Dev Notes): the model honored "Reply with valid JSON" but dropped `confidence` because v1 SYSTEM never named the field. v2 SYSTEM explicitly enumerates field names. The contract is between v2 SYSTEM and the model — verified offline via mock; live verification deferred to VPS walk (AC-3.c live roundtrip is opted-out by default).

### 5.7 Module-mutable-state check
N/A for this story — no new module-level state. The `VERSION` constant is `Final[str]` from existing pattern; `SensitivityClassOutput` is an immutable Pydantic model. No global counters, lru_caches, dicts, or lists added.

### 5.8 Dev-fixture seed-vs-production-shape parity
APPLIED — the `_FakeQwenAdapter` in `test_sensitivity_class_f24.py:60-79` returns AdapterResponse with `tokens_in=20, tokens_out=10` matching the production qwen call shape (small input/output for the 128-token policy cap). The F24 counter-test response shape (`{"sensitivity": "normal", "reason": "L'email concerne des applications Microsoft."}`) is literally the production-captured F24 trace from the 2026-06-05 fourth-pass walk (per story Dev Notes lines 71-75). Seed = production shape. Parity locked.

### 5.9 Grep-verify-cited-figures
APPLIED — "1088 + 2 skipped tests" baseline cited above is unverified until full pytest run completes (in progress). Pre-edit baseline per Story 6-14 closure: `1086 + 2 skipped + 2 deselected`. Post-edit expected: `1086 + 3 new F24 tests` = `1089 + 3 deselected` (1 new live test deselected + the existing 2). Will verify at done-time; pre-review attests intent. The "712+ unclassified emails" figure cited in the story header is sourced from `epic-6-run-flags.md § F24` and not re-asserted in code (it is operational evidence, not a code claim).

### 5.10 Producer-boundary contract
APPLIED — `SensitivityClassOutput` Pydantic model defines `confidence: float = Field(ge=0.0, le=1.0)` and `reason: str = Field(max_length=200)` — explicit constraints at the producer boundary. Pydantic validates on `model_validate_json` at `router.py:593`. If the model emits a non-conforming value (out-of-range confidence, oversized reason), SCHEMA_VALIDATION_FAILED fires — exactly the F24-shape failure path locked by the counter-test.

### 5.11 Git-evidence consistency
APPLIED — `rtk git status --porcelain` output captured above (§2 of this audit) matches the 6-file scope claimed in the story File List. No extra untracked artifacts in the changed-directory neighborhoods (no stray `.pyc`, no scratch files, no `tmp/` dumps). The `_bmad-output/planning-artifacts/epics.md` modification predates this story (untouched in this edit pass) — would not be staged at Step 2.6.

### 5.12 CR-cadence-mandatory surface classification
**Cadence verdict: MANDATORY-CR**

Criteria fired (2 of the §5.12 trigger set):

1. **Prompt-version bump (Rule M discipline)** — v1 → v2 is a load-bearing change. `router_calls.prompt_version` is a denormalized audit field consumed by `/cost` aggregation, the cache-key composition (`compute_idempotency_key`), and the Anthropic ephemeral-cache key. A botched bump produces silent data corruption in all three surfaces.
2. **Cross-story load-bearing seam** — touches Story 3-2 (prompt-module registry), Story 3-3 (classifier safeguard + FR-2.5 enforcement), Story 4-7 (sensitivity-grant gate consumer downstream), and the ingest pipeline orchestrator (Story 3-5). The defender persona's privacy invariant (NFR-PRIV-1 cautious bias) depends on this prompt eliciting valid `confidence` so the downstream floor can fire.

CR dispatch is non-negotiable per Adam-decided Epic 4 retro 2026-06-02 action item #1 (option A). Sonnet 4.6 reviewer at Step 2.4.

Summary table:

| Check | Status |
|---|---|
| 5.1 Lockfile | N/A — no deps change |
| 5.2 Cross-doc | APPLIED |
| 5.3 Lifecycle-string | N/A — no schema/env/lifespan |
| 5.4 Multi-consumer | APPLIED |
| 5.5 Screenshot-perception | N/A — no graphical UI |
| 5.6 Upstream-contract | APPLIED |
| 5.7 Module-mutable-state | N/A — no new state |
| 5.8 Dev-fixture parity | APPLIED |
| 5.9 Grep-verify | APPLIED (with pending full-pytest verification) |
| 5.10 Producer-boundary | APPLIED |
| 5.11 Git-evidence | APPLIED |
| 5.12 Cadence verdict | **MANDATORY-CR** |
