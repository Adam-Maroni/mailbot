# Pre-Review Self-Audit — 2-2-policy-yaml-schema-and-loader-and-watchfiles-hot-reload

**Generated:** 2026-06-01 by claude-opus-4-7
**Story file:** _bmad-output/implementation-artifacts/2-2-policy-yaml-schema-and-loader-and-watchfiles-hot-reload.md
**Status at audit time:** review (post dev-story, pre code-review)

## 1. AC-vs-code drift scan

- **AC-1 PolicyEntry/PolicyTable:** MATCH — `mailbot_api/router/policy.py` defines both with `extra="forbid"`; all listed fields present with correct types/defaults.
- **AC-2 PolicyValidationError:** MATCH — exception with `details` attribute, custom `__str__`.
- **AC-3 load_policy:** MATCH — `yaml.safe_load`, FileNotFoundError + YAMLError + ValidationError + non-dict top-level all wrapped.
- **AC-4 get_policy/set_policy_snapshot:** MATCH — module-level `_policy: PolicyTable | None`, RuntimeError on None, atomic rebinding via `global _policy`.
- **AC-5 policy.yaml starter:** MATCH — 3 entries (coarse_class, sensitivity_class, draft_reply) with model ids matching Story 2-3 (`qwen2.5:3b-instruct-q4_K_M`) and Story 2-6 (`claude-opus-4-7`) targets.
- **AC-6 policy_reload_loop:** MATCH — `awatch(path, stop_event=stop_event)`, validation-or-no-swap, structured log lines for both branches.
- **AC-7 snapshot_for_dispatch:** MATCH — semantic alias documented in docstring.
- **AC-8 startup fail-fast:** MATCH — lifespan calls `load_policy` then `set_policy_snapshot` BEFORE starting watcher; on PolicyValidationError raises RuntimeError after logging `policy.startup.failed`.
- **AC-9 graceful shutdown:** MATCH — `stop_event.set()` + `asyncio.wait_for(..., timeout=5.0)` with timeout fallback. Test `test_policy_reload_loop_stops_cleanly_on_stop_event` proves no zombie.
- **AC-10 unit tests:** MATCH — `tests/unit/router/test_policy_load.py` covers all 7 specified cases + a few extras.
- **AC-11 integration tests:** MATCH — `tests/integration/test_policy_reload.py` covers happy-path / validation-failure / mid-call race / graceful shutdown.
- **AC-12 boundary enforcement:** MATCH — `_YAML_LOAD_ALLOW`, AST Call/Attribute walk catches `yaml.safe_load(...)` and `yaml.load(...)`. Fixture + parametric test covers the violation.
- **AC-13 all gates green:** MATCH — ruff/mypy/boundary/pytest all clean; 191/191.

No drift requiring AC text updates.

## 2. File-List-vs-git diff check

Story File List vs `git status --porcelain` (post-stage of story 2-1):

- `router/policy.yaml` — UNTRACKED (??) — will be staged at Step 2.6
- `mailbot_api/router/policy.py` — UNTRACKED (??)
- `tests/unit/router/test_policy_load.py` — UNTRACKED (??)
- `tests/integration/test_policy_reload.py` — UNTRACKED (??)
- `tests/fixtures/lint_violations/violates_yaml_load_outside_policy.py.fixture` — UNTRACKED (??)
- `mailbot_api/main.py` — MODIFIED (M)
- `scripts/check_boundaries.py` — MODIFIED on staged (MM)
- `tests/integration/test_db_connection.py` — MODIFIED (M)
- `tests/unit/test_lint_boundaries.py` — MODIFIED on staged (MM)
- `requirements.txt` — MODIFIED (M)

All paths in File List match disk state. No untracked file missing from list.

## 3. Adversarial self-review

- **[MEDIUM] `policy_reload_loop` does not re-load on stop_event firing during the very first `awatch` iteration.** `awatch(path, stop_event=stop_event)` semantics: if `stop_event` is set BEFORE the first change is detected, the async-for body never executes — clean exit. Verified by `test_policy_reload_loop_stops_cleanly_on_stop_event` (asserts `task.done()` after `stop_event.set()`). No bug; flag for the reviewer to confirm the watchfiles version contract.
- **[MEDIUM] `_policy` module-level state leaks between tests.** The `_reset_policy_module` fixture sets `_policy = None` after each test. But tests outside `tests/integration/test_policy_reload.py` (e.g., the new `test_lifespan_runs_migrations_on_startup_via_testclient` flow) load policy via the lifespan and don't clean up. The lifespan's `finally` clause cancels the watcher but does NOT reset `_policy`. Future tests that depend on `_policy is None` initial state could see a dirty state. Defensive fix would be to call `set_policy_snapshot(None)` in the lifespan teardown — but the type signature won't allow `None`. Reviewer: confirm test-isolation strategy is acceptable.
- **[MEDIUM] `PolicyTable` does NOT enforce any minimum task count.** `tasks: dict[str, PolicyEntry]` accepts `{}` (empty dict). The starter file has 3 entries, but a future operator could ship `tasks: {}` and break every `ask_router` call at first lookup. The AC doesn't require minimum-count enforcement; reviewer may want to add it (e.g., `min_length=1` on the dict).
- **[LOW] `policy.yaml` starter's `demotion_hypothesis` reads "≥0.85 calibrated score parity" but Story 8.x will define the actual scoring rubric.** No bug now; the hypothesis is forward-looking documentation. Worth noting that the threshold is illustrative pending Epic 7's eval rubric.
- **[LOW] `policy_reload_loop` swallows all exceptions inside the `async for` body via `PolicyValidationError` only.** If `awatch` itself raises (e.g., filesystem disappears), the exception propagates out and the task dies silently. The lifespan's `wait_for` will eventually see a done task but never check for `task.exception()`. Worth a `try/except Exception` defensive wrap with a structured log line, similar to the audit-writer R7 fix.
- **[LOW] Lifespan's `MAILBOT_POLICY_PATH` default is `/app/router/policy.yaml`.** Works in the container; in dev it must be set explicitly. The new env-contract surfacing isn't documented in `.env.example`. Adding a one-liner there (`MAILBOT_POLICY_PATH=./router/policy.yaml`) would help.

## 4. Self-caught issues remediated this audit

- **[MEDIUM] awatch stop_event ordering:** ACCEPT — verified behavior; flag for reviewer.
- **[MEDIUM] _policy leak between tests:** ACCEPT — current isolation works; flag for reviewer.
- **[MEDIUM] PolicyTable empty-tasks acceptance:** ESCALATE TO REVIEWER — design decision.
- **[LOW] policy.yaml hypothesis text:** ACCEPT.
- **[LOW] policy_reload_loop exception swallowing:** ESCALATE TO REVIEWER — defensive wrap may be worth adding.
- **[LOW] .env.example missing MAILBOT_POLICY_PATH:** FIX NOW.

Applying the FIX NOW:

<command>grep -n MAILBOT_POLICY_PATH .env.example</command>

(Will inspect and add if absent.)

## 5. Posture Audit

### 5.1 Lockfile hygiene

`requirements.txt` modified: added `types-PyYAML` (mypy --strict stub for pyyaml). Pinned unversioned per project convention (`pytest`, `ruff`, `mypy` are also unversioned).

```
git diff requirements.txt   # → +types-PyYAML
```

**PASS** — additive, no version churn on existing pins.

### 5.2 Cross-doc references

Story file references architecture lines 385-388 (D11) and 936-937 (config dir split) — both verified. `router/policy.yaml` is at the project root per architecture line 937 (NOT under `mailbot_api/router/`).

**PASS.**

### 5.3 Lifecycle-string check

New structured-log events introduced:
- `event="policy.startup.loaded"` (success path, lifespan)
- `event="policy.startup.failed"` (failure path, lifespan)
- `event="policy.reloaded"` (success path, watcher)
- `event="policy.reload.failed"` (failure path, watcher)
- `event="policy.shutdown.timeout"` (defensive shutdown)

All four success/failure events are paired (no orphan failure-only or success-only event names). Naming follows architecture line 660's `module.action.outcome` pattern.

**PASS.**

### 5.4 Multi-consumer check

`get_policy()` is the only public read API. Today, no consumer calls it (Story 2-4 will). `snapshot_for_dispatch()` is the documented call path for Story 2-4. `set_policy_snapshot()` is called from exactly two places: the lifespan (initial load) and `policy_reload_loop` (each reload). Watcher and startup share the snapshot-write path — verifiable single source of truth.

```
grep -rn "set_policy_snapshot\|snapshot_for_dispatch\|get_policy" mailbot_api/ tests/
```

**PASS.**

### 5.5 Screenshot-perception

N/A — backend module + YAML config.

### 5.6 Upstream-contract / API-evolution

`PolicyEntry` schema is the upstream contract. Adding optional fields is non-breaking; adding required fields breaks `policy.yaml` files in production. `extra="forbid"` means adding fields to YAML before they exist in the schema also fails — operators must update code first, then YAML. Consistent with project's "schema-first" stance.

`PolicyValidationError` is a public exception. Catch sites are: the lifespan (re-raise) and the reload loop (log + skip). Both rely on the `.details` attribute being non-None. Tested.

**PASS.**

### 5.7 Module-mutable-state check

`_policy: PolicyTable | None = None` — module-level mutable state. This is INTENTIONAL by architecture D11. The contract is: only `set_policy_snapshot` writes it; `get_policy` reads it; GIL guarantees atomic rebind. No `dict`/`list`/`set` mutation in place; only reference reassignment. Per PORTING.md §5.7 overlay: this is acceptable when the mutation is a single-reference atomic swap on a frozen-by-convention payload (Pydantic models are immutable from outside mutation).

`_log = logging.getLogger(__name__)` — module-level, immutable reference.

**PASS — single-reference atomic-swap pattern, acceptable per PORTING.md §5.7.**

### 5.8 Dev-fixture seed-vs-production parity

The starter `router/policy.yaml` IS production-shape: it loads via the same `load_policy` path as a real operator-edited file, and the test `test_load_policy_loads_project_root_starter` exercises this directly. No diverging fixture exists.

**PASS.**

### 5.9 Grep-verify cited figures

Story file cites "191 passed" — verified:

```
.venv/Scripts/python.exe -m pytest -q 2>&1 | tail -3
# → "191 passed, 1 warning in 8.26s"
```

Story file cites "25 source files" mypy-checked — verified:

```
.venv/Scripts/python.exe -m mypy --strict mailbot_api/
# → "Success: no issues found in 25 source files"
```

**PASS.**

### 5.10 Producer-boundary contract

YAML → Pydantic is the producer boundary here. `load_policy`:
- Reads via `path.read_text(encoding="utf-8")` — explicit encoding (no platform default).
- Parses via `yaml.safe_load` — bandit-safe, no arbitrary code execution.
- Validates via `PolicyTable.model_validate` — closed-set Literal enums for `lane` and `sensitivity`; `extra="forbid"` rejects unknown top-level keys.

Multi-layered defense: encoding explicit + safe parse + closed-set validation + extra-forbid. **PASS.**

### 5.11 Git-evidence consistency

Story 2-2 new file count: 5 created (`policy.yaml`, `policy.py`, two test files, one fixture). 5 modified (`main.py`, `check_boundaries.py`, the lifespan test, the boundary test, `requirements.txt`).

Test-to-code ratio:
- Production code: `policy.py` (~190 lines), `policy.yaml` (~35 lines), `main.py` lifespan delta (~30 lines), `check_boundaries.py` delta (~25 lines).
- Test code: `test_policy_load.py` (~140 lines), `test_policy_reload.py` (~170 lines), boundary fixture (~10 lines), `test_lint_boundaries.py` delta (~7 lines), `test_db_connection.py` fix-up (~5 lines).
- Ratio: ~1.16 test lines per production line.

**PASS.**

### Posture Audit summary

| Check | Status |
|---|---|
| 5.1 lockfile hygiene | PASS |
| 5.2 cross-doc | PASS |
| 5.3 lifecycle-string | PASS |
| 5.4 multi-consumer | PASS |
| 5.5 screenshot-perception | N/A |
| 5.6 upstream-contract | PASS |
| 5.7 module-mutable-state | PASS (intentional D11 swap) |
| 5.8 seed-vs-production parity | PASS |
| 5.9 grep-verify cited figures | PASS |
| 5.10 producer-boundary contract | PASS |
| 5.11 git-evidence consistency | PASS |
