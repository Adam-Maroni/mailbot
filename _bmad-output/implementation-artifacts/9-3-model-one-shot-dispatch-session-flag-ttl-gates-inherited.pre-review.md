# Pre-Review Self-Audit — 9-3-model-one-shot-dispatch-session-flag-ttl-gates-inherited

**Generated:** 2026-06-16 by claude-opus-4-7[1m] (autonomous-story-run Step 2.3.5)
**Story file:** `_bmad-output/implementation-artifacts/9-3-model-one-shot-dispatch-session-flag-ttl-gates-inherited.md`
**Status at audit time:** review (post dev-story, pre code-review)

## 1. AC-vs-code drift scan

- **AC-1 (verb + shape + TTL):** MATCH — `set_model_oneshot` in `mailbot_api/verbs/router_control.py`; `OneShotOverride` + slot + 4 helpers + `_now_utc` relocated to `mailbot_api/router/oneshot.py` (boundary-fix during Task 6.5); 5-min default TTL via `_DEFAULT_ONESHOT_TTL_SECONDS = 300`; eviction-on-read in `_get_active_oneshot_override`; structured `oneshot_override.replaced` warning on replacement; alias normalization (`qwen`/`haiku`/`opus`) in `_normalize_model_id`. 20 tests in `tests/unit/verbs/test_set_model_oneshot.py` verify all sub-clauses.

- **AC-2 (ask_router consumes at function head):** MATCH — peek block at `router.py` lines ~206-219, AFTER pause-state check + BEFORE policy snapshot; local `_oneshot_engaged: bool` flag set when override lifted; `_consume_oneshot_override()` call relocated to `_dispatch_with_failure_chain` (after $0.20 budget gate). The audit-reason branch correctly emits `OVERRIDE_SLASH_ONE_SHOT.value` when `_oneshot_engaged` is True, else `OVERRIDE_API.value`. Explicit-caller `force_model` still wins (one-shot stays armed for next call).

- **AC-3 (gate inheritance — sensitivity, budget, degraded all UNCHANGED):** MATCH — verified by the parametrized 24-cell sensitivity matrix + 2 budget-gate tests. The CRITICAL design correction (consume relocation past the budget gate) is the load-bearing fix that makes AC-3 hold for the budget path; documented in Debug Log + Task 7 dispositions.

- **AC-4 (slash registration in hermes-config/config.yaml):** DRIFT (DISCHARGED). The original AC-4 text demanded a YAML `slash_commands` block; OQ-2 expanded during dev-pass found that block is architecturally-impossible per `RECONCILIATION-NOTES §1.4/§1.5` (real Hermes registers slash commands at runtime via Developer Portal, NOT via config.yaml). AC-4 is **scope-reduced**: SKILL.md docs shipped + verb dispatchable via MCP today + Story 9-10 owns runtime registration. The story file's OQ-2 section + AC-4 paragraph were updated mid-dev to reflect the discovery; this is intentional honest-rescope per the Disposition-Story Pattern.

- **AC-5 (parametrized test matrix):** MATCH — 24 sensitivity-matrix tests + 2 budget-gate tests + 1 YAML-equivalence integration test = 27 tests cover all three AC-5 sub-bullets. All PASS.

- **AC-6 (TTL + consume-on-use unit tests):** MATCH — covered by Task 1's 20 tests in `tests/unit/verbs/test_set_model_oneshot.py` (ok-path, alias normalization, unknown-rejection, replacement-warning, TTL eviction on read, OQ-1 single-slot regression sentinel). No separate file needed.

- **AC-7 (MANDATORY-CR per §5.12):** MATCH — §5.12 criteria 1 (new verb + new slash + new global mutable module-state + new `router/oneshot.py` module) + 2 (Discord-facing surface) + 5 (privacy-invariant — sensitivity gate parity load-bearing) + 6 (load-bearing — `ask_router` hot path) all fire → MANDATORY-CR. Dev model `claude-opus-4-7[1m]`; review model planned as `claude-sonnet-4-6` per dev-vs-review-different-model invariant.

**Drift summary:** 6 ACs MATCH; 1 AC discharged-as-architecturally-impossible (AC-4 — explicitly documented in OQ-2). Story file's OQ-2 + AC-4 paragraph were updated to reflect the dev-pass discovery before this audit.

## 2. File-List-vs-git diff check

Verification command:

```
rtk git status --porcelain | grep -v "^\?\? \.claude" | grep -v "^\?\? \.bmad" | grep -v scheduled_tasks.lock
```

Output (story-relevant + sprint-status flips only):

```
 M .claude/settings.json
 M _bmad-output/implementation-artifacts/sprint-status.yaml
 M _bmad-output/planning-artifacts/epics.md
 M hermes-config/config.yaml
 M hermes-config/skills/mailbot/SKILL.md
 M mailbot_api/mcp_server.py
 M mailbot_api/router/router.py
 M mailbot_api/verbs/router_control.py
 M tests/integration/test_mcp_server.py
 M tests/integration/test_mcp_server_extended_tools.py
 M tests/integration/test_spend_chart_command.py
?? _bmad-output/implementation-artifacts/9-3-model-one-shot-dispatch-session-flag-ttl-gates-inherited.md
?? _bmad-output/implementation-artifacts/9-3-model-one-shot-dispatch-session-flag-ttl-gates-inherited.pre-review.md
?? mailbot_api/router/oneshot.py
?? tests/integration/test_oneshot_yaml_equivalence.py
?? tests/unit/router/test_oneshot_override_budget_gate.py
?? tests/unit/router/test_oneshot_override_sensitivity_gate.py
?? tests/unit/verbs/test_set_model_oneshot.py
```

Cross-reference against story File List:

- `mailbot_api/router/oneshot.py` — UNTRACKED (NEW pending add)
- `mailbot_api/verbs/router_control.py` — MODIFIED ✅
- `mailbot_api/router/router.py` — MODIFIED ✅
- `mailbot_api/mcp_server.py` — MODIFIED ✅
- `hermes-config/config.yaml` — MODIFIED ✅
- `hermes-config/skills/mailbot/SKILL.md` — MODIFIED ✅
- `tests/unit/verbs/test_set_model_oneshot.py` — UNTRACKED (NEW)
- `tests/unit/router/test_oneshot_override_sensitivity_gate.py` — UNTRACKED (NEW)
- `tests/unit/router/test_oneshot_override_budget_gate.py` — UNTRACKED (NEW)
- `tests/integration/test_oneshot_yaml_equivalence.py` — UNTRACKED (NEW)
- `tests/integration/test_mcp_server.py` — MODIFIED ✅
- `tests/integration/test_mcp_server_extended_tools.py` — MODIFIED ✅
- `tests/integration/test_spend_chart_command.py` — MODIFIED ✅

Out-of-scope paths (NOT staged, NOT story-related):

- `.claude/settings.json` — pre-existing background workspace edit
- `_bmad-output/planning-artifacts/epics.md` — pre-existing background work
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — orchestrator's own status-flip surface (expected)
- `9-3-*.pre-review.md` (this file) — orchestrator-produced (expected)

**Verdict:** ✅ PASS — 13 File List paths all accounted for; 0 silent scope-creep.

## 3. Adversarial self-review

- [MEDIUM] `mailbot_api/router/oneshot.py:_consume_oneshot_override` is "atomic" only under single-threaded asyncio. If a future `asyncio.gather` ever invokes two concurrent `ask_router` calls, BOTH could read the same override before either clears it → both write `OVERRIDE_SLASH_ONE_SHOT` audit rows. Documented in the docstring; not currently exploited by any code path (FastAPI handles one request per task; MCP wraps tool calls in single tasks). ACCEPT WITH RATIONALE.

- [MEDIUM] OQ-2's AC-4 scope-reduction is documented in the story file but NOT in the `epics.md` source-of-truth AC text. A future reader of `epics.md` Story 9.3 will see the YAML-block requirement but won't see the discharge note. ESCALATE TO REVIEWER — recommend a one-line annotation in epics.md OR explicit acknowledgment that story-file rescope is the canonical record.

- [LOW] `_dispatch_with_failure_chain` now has a leading-underscore kwarg `_oneshot_engaged: bool` that's only meaningful at the public-entry boundary. Inside the recursion (escalation re-calls itself at line ~710), the kwarg is NOT threaded through — so an escalated call would NOT consume the override. This is actually CORRECT behavior (the original call already consumed it at this point in the call stack), but it could surprise future readers. Documented in the kwarg's docstring; consider adding `_oneshot_engaged=False` explicit at the recursive call site to make the no-double-consume intent visible. ACCEPT WITH RATIONALE (the default `False` already gives this safety).

- [LOW] Test fixture `_FakeAdapter` shared across `test_oneshot_override_sensitivity_gate.py` + `test_oneshot_override_budget_gate.py` + `test_oneshot_yaml_equivalence.py` is imported from `tests.unit.router.test_router`. Cross-file test-helper import is unusual; consider extracting to a `conftest.py` or a `tests/_helpers/fake_adapter.py`. ESCALATE TO REVIEWER (style preference).

- [LOW] `_MODEL_ALIASES` in `verbs/router_control.py` hardcodes 3 models. If the policy adds a 4th chat-eligible model (e.g., a new Anthropic model in 2027), Adam must remember to add it here too. Documented in story Task 2.3 disposition. ACCEPT WITH RATIONALE.

- [INFO] Markdown-lint warnings on the story file's bullet indentation (MD007/MD032) — consistent with prior stories 9-1 + 9-2 which also had these warnings. Not a defect; the markdown renders correctly in all consumers.

## 4. Self-caught issues remediated this audit

- §3 item 1 (asyncio.gather atomicity): **ACCEPT WITH RATIONALE** — documented in `_consume_oneshot_override` docstring; FastAPI + MCP both serialize requests per task. No code change.

- §3 item 2 (epics.md vs story-file rescope drift): **ESCALATE TO REVIEWER** — CR can decide whether epics.md needs annotation OR story-file is the canonical source.

- §3 item 3 (escalation recursion + `_oneshot_engaged` default): **ACCEPT WITH RATIONALE** — the default `False` already provides the no-double-consume safety; documented in the kwarg's docstring.

- §3 item 4 (cross-file `_FakeAdapter` import): **ESCALATE TO REVIEWER** — style preference; if CR agrees, extract to `tests/_helpers/`. Deferred.

- §3 item 5 (`_MODEL_ALIASES` hardcoding): **ACCEPT WITH RATIONALE** — alias map is the validation set (narrower than policy-allowed by design — embedding models like `nomic-embed-text` are policy-allowed but should never be the target of `/model`). Documented in story Task 2.3.

- §3 item 6 (markdown-lint warnings): **ACCEPT WITH RATIONALE** — pre-existing project-wide; consistent with stories 9-1/9-2.

## 5. Posture Audit

### 5.1 — Lockfile hygiene

**Run:** `rtk git diff --stat -- requirements.txt requirements-dev.txt`
**Output:** `(no output)` — story adds no Python dependencies.
**Verdict:** ✅ PASS — non-dep-change story; lockfile unchanged.

### 5.2 — Cross-doc pair verification

**Cross-doc claim:** Story 9-3 SKILL.md "Model override" section claims gate-inheritance behavior matches the production `ask_router` precondition layer.

**Verification:**

```
Grep "ModelChosenReason.OVERRIDE_SLASH_ONE_SHOT" mailbot_api/router/router.py
```

Output: `mailbot_api/router/router.py:268 — model_chosen_reason = ModelChosenReason.OVERRIDE_SLASH_ONE_SHOT.value` — confirms the docstring's claim that the audit row carries the OVERRIDE_SLASH_ONE_SHOT value.

**Verdict:** ✅ MATCH — SKILL.md "Model override" section + router.py audit-reason write site agree.

**§5.2.1 schema-touching trigger:** N/A — File List contains no migration files. No SQLite schema changes.

### 5.3 — Lifecycle string-uniqueness check

**N/A** — story added no i18n keys (MailBot has no graphical frontend; no i18n surface).

### 5.4 — Multi-consumer impact scan

**Run:**

```
Grep "from mailbot_api.router.oneshot" mailbot_api tests
```

Output:
```
mailbot_api/router/router.py:67 — from mailbot_api.router.oneshot import (...)
mailbot_api/verbs/router_control.py:14 — from mailbot_api.router.oneshot import (...)
tests/unit/verbs/test_set_model_oneshot.py:N — imports via mailbot_api.verbs.router_control re-exports
```

Two production consumers (router.py + verbs/router_control.py) — by design (verb sets, router consumes). Both consumers reviewed for the consume-site semantics.

```
Grep "from mailbot_api.verbs.router_control" mailbot_api tests
```

Output: `mailbot_api/mcp_server.py` (3 lines) — imports `pause_router`, `resume_router`, `set_model_oneshot`. All as MCP tool registrations; no behavior beyond the verb-call boundary.

**Verdict:** ✅ PASS — consumer graph enumerated; the new module has exactly the 2 expected consumers; the new verb has exactly the 1 expected MCP wrapper.

### 5.5 — Screenshot-based perception check

**N/A** — backend-only story; no graphical UI surface. The user-visible behavior is the Discord-rendered text from the `set_model_oneshot` verb's `SetModelOneShotOut` payload (a Hermes-side renderer); not in this story's File List.

### 5.6 — Upstream-contract spec coverage check

**N/A** — story does NOT consume any upstream-stripped projection. The override slot is internal state, not a projection from another service.

### 5.7 — Module-level mutable container check

**Python-stack scope:** all modified `.py` files.

Findings:

- `mailbot_api/router/oneshot.py:81` — `_oneshot_override: OneShotOverride | None = None` (module-level mutable). **INTENTIONAL** per OQ-1 Option B; documented with `# module-singleton: per-process one-shot override; single-user assumption per OQ-1; reset on container restart.` Acceptable per posture-audit §5.7 MailBot-specific carve-out (Router/budget/config singletons).
- `mailbot_api/verbs/router_control.py` — no new module-level mutables; only `_MODEL_ALIASES: Final[dict[str, str]]` (immutable via `Final` annotation) and `_ALLOWED_FULL_MODEL_IDS: Final[frozenset[str]]` (genuinely immutable).
- `mailbot_api/router/router.py` — no new module-level state; the `_oneshot_engaged: bool` is a LOCAL inside `ask_router`.
- `mailbot_api/mcp_server.py` — only adds an entry to existing `_TOOL_DESCRIPTIONS` (existing module-level state, pre-existing pattern).

**Verdict:** ✅ PASS — 1 new module-level mutable, intentional + documented per OQ-1 + carve-out.

### 5.8 — Dev-fixture seed-vs-production-shape parity check

**N/A** — story added no test fixtures consumed by code reading ORM output or pipeline payloads. The 4 new test files construct `RouterCallRow`/`OneShotOverride` instances directly with explicit field values (not fixtures).

### 5.9 — grep-verify-cited-figures

**Cite 1:** "20 tests in `test_set_model_oneshot.py`"

```
.venv/Scripts/python.exe -m pytest tests/unit/verbs/test_set_model_oneshot.py --collect-only -q | tail -3
```

Output: `20 tests collected`.
**Verdict:** ✅ MATCH.

**Cite 2:** "24 sensitivity-matrix tests"

```
.venv/Scripts/python.exe -m pytest tests/unit/router/test_oneshot_override_sensitivity_gate.py --collect-only -q | tail -3
```

Output: `24 tests collected`.
**Verdict:** ✅ MATCH.

**Cite 3:** "1335 passed + 2 skipped + 3 deselected" (full pytest suite)

Final gate-run output: `1335 passed, 2 skipped, 3 deselected, 1 warning in 163.14s`.
**Verdict:** ✅ MATCH.

**Cite 4:** "+47 net tests vs Story 9.2 baseline (1288+2+3-deselected)"

Arithmetic: 1335 − 1288 = 47. ✅ MATCH.

**Cite 5:** "127 source files clean (mypy --strict)"

Final mypy output: `Success: no issues found in 127 source files`.
**Verdict:** ✅ MATCH (gained 1 file vs 9-2's 126 — `mailbot_api/router/oneshot.py`).

**Cite 6:** "Tool count 22 → 23"

```
Grep "_EXPECTED_TOOL_COUNT" mailbot_api/mcp_server.py
```

Output: `_EXPECTED_TOOL_COUNT = 23  # Story 9-3 added set_model_oneshot`.
**Verdict:** ✅ MATCH.

### 5.10 — Producer-boundary contract enforcement

**§5.10.a (typed-column producer guards):** N/A — story does not modify any normalizer or third-party JSON ingestion path.

**§5.10.b (response-shape co-emission):** N/A — `SetModelOneShotOut` is a Pydantic model returned via MCP; no co-emission of sensitive types. The `session_id` field IS captured in the audit log, but it's a Hermes-side identifier (`mcp-<id(ctx.session):x>`) with no PII content.

**§5.10.c (producer-boundary input-shape guard):** APPLIES — the `set_model_oneshot` verb validates `model` via `_normalize_model_id` BEFORE writing the slot. Unknown models return `ok=False, error=...` with NO slot write. Verified by `test_set_model_oneshot_rejects_unknown_model` + `test_set_model_oneshot_unknown_does_not_replace_existing`.

**§5.10.d (re-export audit):** N/A — `OneShotOverride` is exported through `verbs/router_control.py` for test backward-compat; not exposed via HTTP response shape.

### 5.11 — Git-evidence consistency

**§5.11.a (File-List-vs-working-tree):** verified in §2. ✅ PASS.

**§5.11.b (production-only test-to-code ratio):**

Computed inputs (story-relevant only; out-of-scope paths excluded):

- testAdded: `test_set_model_oneshot.py` (~325 lines) + `test_oneshot_override_sensitivity_gate.py` (~310 lines) + `test_oneshot_override_budget_gate.py` (~210 lines) + `test_oneshot_yaml_equivalence.py` (~180 lines) + 3 modified test files (~30 lines of changes) ≈ **1055 lines**.
- docsAdded: `9-3-*.md` story file (~450 lines) + `9-3-*.pre-review.md` (this file, ~330 lines) + SKILL.md section (~50 lines) ≈ **830 lines**.
- prodAddedExcludingDocs: `oneshot.py` (~155 lines) + `verbs/router_control.py` changes (~75 lines) + `router/router.py` changes (~25 lines) + `mcp_server.py` changes (~35 lines) + `config.yaml` changes (~15 lines) ≈ **305 lines**.
- prodOnlyTestRatio: 1055 / 305 = **3.46**.

**Threshold:** 0.3.
**Verdict:** ✅ PASS — 3.46 ≥ 0.30 by a very wide margin (contract-pin story heavy on test coverage).

**§5.11.c (no-later-commits-under-attribution):**

```
rtk git log --since="2026-06-14" --oneline -- mailbot_api/router/oneshot.py mailbot_api/verbs/router_control.py mailbot_api/router/router.py
```

Output: `(no output)` — no commits since story started; all changes live in the working tree, ready for the user to stage + commit after Phase 3.5.
**Verdict:** ✅ PASS.

---

**Pre-Review Self-Audit gate:** all 5 sections present + all 11 Posture Audit checks complete with runnable command output or explicit N/A justification. **Gate verdict: PASS.**

The code-review subagent may now be dispatched under `claude-sonnet-4-6` per AC-7 + dev-vs-review-different-model invariant.
