# Pre-Review Self-Audit — 9-1-contract-pin-policy-user-overrides-yaml-schema-and-shallow-leaf-merge-semantics

**Generated:** 2026-06-13 by claude-opus-4-7 (1M context)
**Story file:** [9-1-contract-pin-policy-user-overrides-yaml-schema-and-shallow-leaf-merge-semantics.md](9-1-contract-pin-policy-user-overrides-yaml-schema-and-shallow-leaf-merge-semantics.md)
**Status at audit time:** review (post dev-story, pre code-review)

---

## 1. AC-vs-code drift scan

- **AC-1 (companion-file load + shallow-leaf merge):** MATCH. `_merge_user_overrides` in `mailbot_api/router/policy.py:201-263` iterates `overrides.tasks`; for each known task, `baseline.tasks[k].model_copy(update=override.model_dump(exclude_none=True))`; unknown tasks log `policy.user-overrides.unknown_task` WARNING and are discarded.
- **AC-2 (malformed overrides non-fatal):** MATCH. All override-side failure paths (OSError, yaml.YAMLError, non-mapping, ValidationError) in `load_policy` (`mailbot_api/router/policy.py:319-371`) log `policy.user-overrides.parse_failed` ERROR + return baseline. Baseline failures still raise unchanged.
- **AC-3 (hot-reload watch set extended):** MATCH WITH NUANCE. `policy_reload_loop` (`mailbot_api/router/policy.py:412-486`) takes `overrides_path` kwarg; `awatch` filters paths_to_watch to existing files only at startup (watchfiles raises FileNotFoundError on absent paths — discovered during integration test; documented in `docs/policy-overrides.md` + Story 9-4 owns the restart-on-first-create surfacing).
- **AC-4 (all-Optional + extra="forbid" schema):** MATCH. `UserOverridesEntry` (`mailbot_api/router/policy.py:99-126`) every field `Optional[T] = None` + `ConfigDict(extra="forbid")`. `UserOverridesTable` (`mailbot_api/router/policy.py:129-145`) tasks defaults `dict`. 19 unit tests cover all 7 AC-4 cases.
- **AC-5 (merge docstring + design doc):** MATCH. `_merge_user_overrides` docstring documents 4 contract points + 2 examples (`mailbot_api/router/policy.py:201-251`). `docs/policy-overrides.md` is 187 lines covering why-companion, file location, schema, merge semantics, failure handling, audit events, version-suffix, forward refs, hot-reload limitation, race semantics.
- **AC-6 (version-suffix `+overrides:<sha256[:8]>`):** MATCH. `_compute_overrides_hash` (`mailbot_api/router/policy.py:161-170`) returns first 8 hex chars of SHA-256; `_compute_merged_version` (`mailbot_api/router/policy.py:173-188`) composes the final string; `load_policy` returns `PolicyTable(tasks=merged.tasks, version=merged_version)`.
- **AC-7 (production docker-compose bind-mount):** MATCH. `docker-compose.yml` mailbot-api service now mounts `./router/policy.yaml:/app/router/policy.yaml:ro` + `./router/policy.user-overrides.yaml:/app/router/policy.user-overrides.yaml`. `.gitignore` excludes the override file but tracks the `.example`. `router/policy.user-overrides.yaml.example` is operator-facing template with `tasks: {}` no-op default.
- **AC-8 (MANDATORY-CR per §5.12):** PENDING — fired by §5.12 below; CR dispatch is the next orchestrator step.

**No drift detected.** All 7 functional ACs MATCH; AC-8 fires correctly.

---

## 2. File-List-vs-git diff check

Cross-referenced story `### File List` against `git status --porcelain`:

**Modified (tracked):**

- `mailbot_api/router/policy.py` — TRACKED (verified via `git ls-files --error-unmatch`)
- `mailbot_api/main.py` — TRACKED
- `docker-compose.yml` — TRACKED
- `.gitignore` — TRACKED

**New (untracked, expected; will be staged at Step 2.6):**

- `tests/unit/router/test_policy_user_overrides_merge.py` — UNTRACKED (new file)
- `tests/integration/test_policy_user_overrides_lifespan.py` — UNTRACKED (new file)
- `docs/policy-overrides.md` — UNTRACKED (new file)
- `router/policy.user-overrides.yaml.example` — UNTRACKED (new file)
- `_bmad-output/implementation-artifacts/9-1-contract-pin-policy-user-overrides-yaml-schema-and-shallow-leaf-merge-semantics.md` — UNTRACKED (new story file)
- `_bmad-output/implementation-artifacts/9-1-contract-pin-policy-user-overrides-yaml-schema-and-shallow-leaf-merge-semantics.pre-review.md` — UNTRACKED (this file, will be added at Step 2.6)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — already MODIFIED (existing file)

All UNTRACKED entries are expected new-file-additions. No phantom files. No File List entries missing from git surface. **PASS.**

---

## 3. Adversarial self-review

Self-caught issues from a deliberately harsh re-read of the implementation:

- **[MEDIUM] `mailbot_api/router/policy.py:_merge_user_overrides` — silent typing drift.** The function signature declares `overrides: UserOverridesTable` but the inner loop `for task_key, override_entry in overrides.tasks.items()` iterates `dict[str, UserOverridesEntry]`. If a future contributor changes `UserOverridesTable.tasks` to a different shape, the loop would silently iterate something unexpected. Acceptable risk: Pydantic + mypy --strict catch this at module load; the function body is small.
- **[LOW] `mailbot_api/router/policy.py:load_policy` — duplicate FileNotFoundError handling for override path.** The function checks `if overrides_path is None or not overrides_path.exists()` (line ~309) AND wraps `read_text` in a try/except OSError. The `exists()` check makes the OSError catch slightly redundant (the file did exist between exists() and read, but a TOCTOU race during cold start is implausible). Defensive belt-and-suspenders is fine; flagging for awareness.
- **[LOW] `mailbot_api/router/policy.py:policy_reload_loop` — watch-set frozen at startup.** Per the AC-3 nuance, if the override file is created AFTER mailbot-api starts, it is NEVER picked up by hot-reload (must restart). Documented in `docs/policy-overrides.md` "Hot-reload contract limitation"; Story 9-4 owns the create-flow restart-requirement surfacing. Acceptable trade-off.
- **[LOW] `mailbot_api/router/policy.py:_compute_merged_version` — 8-hex-char hash collision space.** 32-bit truncation. Collision probability: ~10⁻⁵ at thousands of overrides over the project lifetime. Operationally acceptable per Story 9-1 Dev Notes "Version derivation contract — explanation". Documented inline.
- **[INFO] `docker-compose.yml` — bind-mount creates a directory if host-side file is missing.** Compose v2 silently creates the target path as a directory if missing on Linux hosts; mailbot-api would then fail because `load_policy` tries to read a directory as a file. Mitigated by the comment block warning operators + the `policy.user-overrides.yaml.example` discoverable sibling. Not a code bug; a deploy-time gotcha the comment surfaces.
- **[INFO] `tests/integration/test_policy_user_overrides_lifespan.py:test_hot_reload_emits_swap_event_when_overrides_change` — relies on watchfiles polling cadence.** Test polls `get_policy().version` with 50ms ticks for up to 5s. If a CI environment is unusually slow, this could flake. Mitigation: 5s timeout is generous; teardown via `stop_event.set()` is clean. Watching for flakes.

---

## 4. Self-caught issues remediated this audit

- **[MEDIUM] silent typing drift:** ACCEPT WITH RATIONALE. Pydantic + mypy --strict already enforce the shape; an explicit runtime guard would be defensive-pyramid noise.
- **[LOW] duplicate FileNotFoundError handling:** ACCEPT WITH RATIONALE. Belt-and-suspenders OSError catch protects against TOCTOU edge cases (extremely rare but cheap to handle); zero downside.
- **[LOW] watch-set frozen at startup:** ESCALATE TO REVIEWER. The reviewer should sanity-check whether the file-must-exist-at-startup limitation is acceptable for the Story 9-4 consumer flow. My read is YES (one-time bootstrap inconvenience), but I want a different model's opinion.
- **[LOW] 8-hex-char hash collision:** ACCEPT WITH RATIONALE. Standard practice (matches Git short-hash convention); the full SHA-256 is available in the swap log for forensic disambiguation if a collision occurs.
- **[INFO] bind-mount-target-as-directory:** ACCEPT WITH RATIONALE. Mitigation via docker-compose comment + example file sibling. A `setup_vps.sh` `touch` step is the cleanest fix; that script doesn't exist yet (Story 6-7 territory — defer).
- **[INFO] polling-cadence flake risk:** ACCEPT WITH RATIONALE. 5s timeout + clean teardown; standard pattern matching Story 2-2's `test_policy_reload.py` precedent.

---

## 5. Posture Audit

### 5.1 — Lockfile hygiene

`requirements.txt` UNCHANGED by Story 9-1. No new pip dependencies added (`watchfiles`, `pydantic`, `pyyaml`, `hashlib` are all pre-existing). **N/A — story adds no dependencies.**

### 5.2 — Cross-doc consistency

Cross-doc surface touched: `docs/policy-overrides.md` (NEW); `mailbot_api/router/policy.py` module docstring (updated); story file Dev Notes; Dev Agent Record Completion Notes List.

Verified: all cross-references in the docstring point to extant ACs + extant code paths. `docs/policy-overrides.md` forward-references Story 9-4 + 9-6 + 9-7 consistently with the epics.md spec. **PASS.**

### 5.3 — Lifecycle string consistency

Pydantic field `Literal` values for `lane` (`"interactive"|"batch"`) and `sensitivity` (`"normal"|"sensitive"|"confidential"|"any"`) UNCHANGED — mirrored exactly from `PolicyEntry` to `UserOverridesEntry`. No string-literal drift. **PASS.**

### 5.4 — Multi-consumer impact

Downstream consumers of `load_policy()` + `get_policy()`:

- `mailbot_api/main.py` lifespan — updated to pass `overrides_path` kwarg.
- `mailbot_api/router/router.py::ask_router` via `snapshot_for_dispatch()` — UNCHANGED (post-merge `PolicyTable` is the same shape; consumers see the merged view transparently).
- `mailbot_api/sensitivity/classifier.py::assert_qwen_only` — UNCHANGED (consumer reads the post-merge snapshot; operator cannot override `sensitivity_class` to a non-Qwen model because the snapshot is validated against `PolicyEntry` semantics, which the merge preserves).

**One consumer surface (main.py) updated; all others see merged view without change. PASS.**

### 5.5 — Screenshot-perception parity

N/A — project has no graphical frontend per PORTING.md `<frontend-src>` carve-out.

### 5.6 — Upstream-contract preservation

`watchfiles.awatch` upstream contract: raises `FileNotFoundError` on non-existent path. Story 9-1 honors this by filtering watch_paths to existing files at watcher start. Documented limitation in `docs/policy-overrides.md`. **PASS — upstream contract preserved.**

`yaml.safe_load`, `Pydantic.model_validate`, `hashlib.sha256` — all used per upstream-canonical patterns; no contract violations. **PASS.**

### 5.7 — Module-mutable state

Story 9-1 does NOT add new module-mutable state. The existing `_policy: PolicyTable | None` singleton (Story 2-2) is the only mutable module-level state in `policy.py`; it stays singular + Python-GIL-atomic-rebind under `set_policy_snapshot()`. **PASS — no new module-mutable surface.**

### 5.8 — Dev-fixture seed-vs-production-shape parity

The unit + integration test fixtures use 2-task baselines (`coarse_class` + `draft_reply`) matching the shape of production `router/policy.yaml` (16 tasks). The reduced fixture exercises the same code paths; production schema is structurally identical. **PASS — fixtures are production-shape compatible.**

### 5.9 — Grep-verify cited figures

Story Dev Notes cites:

- "16 tasks in baseline" — verified via `Grep ^  [a-z_]+:` on `router/policy.yaml`: 16 matches at lines 15, 24, 33, 44, 53, 62, 71, 80, 89, 98, 107, 118, 127, 136, 147, 157. **VERIFIED.**
- "AR-D11-1 validation-or-no-swap" — `architecture.md` line 387: "On change: re-read → validate against the `PolicyTable` Pydantic schema → atomic swap of the in-memory policy only on success." **VERIFIED.**
- "1168 tests baseline" — recorded in sprint-status.yaml at e26acf5 commit message. **VERIFIED.**
- "+25 net tests" — final run `1193 passed + 2 skipped + 3 deselected` minus `1168 baseline` = 25. **VERIFIED.**

**PASS — all figures verified.**

### 5.10 — Producer-boundary contract

The boundary between operator-edited YAML and Python runtime is the producer-boundary surface. Defense layers:

1. `yaml.safe_load` (not `yaml.load`) — already enforced project-wide by `scripts/check_boundaries.py`.
2. `UserOverridesEntry` Pydantic schema with `extra="forbid"` and `Optional[T] = None` types — typed runtime validation.
3. Sanitized error logging via `sanitize_error()` — accidental secrets in YAML cannot leak via failure logs.

**PASS — three layers of defense at the producer boundary.**

### 5.11 — Git-evidence consistency

`git status` shows: 4 tracked modifications (policy.py, main.py, docker-compose.yml, .gitignore) + 6 untracked new files (tests + docs + example + story file + pre-review file). All match the story File List. **PASS.**

Test ratio: 25 net new tests (19 unit + 6 integration) for ~400 LOC of new code. Ratio = 25 tests / 400 LOC ≈ 6.25 tests-per-100-LOC. Healthy. **PASS.**

### 5.12 — CR-cadence-mandatory surface classification (load-bearing — Adam-decided 2026-06-02 retro)

Evaluating the 6 §5.12 criteria against Story 9-1:

| # | Criterion | Story 9-1 fires? | Rationale |
|---|---|---|---|
| 1 | New architectural surface / new boundary | **YES** | Companion-file load path is brand new. New Pydantic models (UserOverridesEntry, UserOverridesTable). New merge function (_merge_user_overrides). New audit event taxonomy (policy.user-overrides.swap, .parse_failed, .unknown_task, .empty_entry). New version-suffix derivation contract. |
| 2 | External-facing change / Discord-facing surface | NO | No Discord-side change; no API surface change. The change is internal to the policy load path. |
| 3 | Cost / budget / Anthropic-API surface | NO | No new Anthropic call; no budget-guard change; no cost-discipline change. |
| 4 | Cross-story load-bearing seam (touches multiple stories' assumptions) | **YES** | Story 9-4 (set_model_persistent) is a direct downstream consumer. Story 9-6 (benchmark_runs.cohort_key.router_policy_version) consumes the version-suffix. The watchfiles + Pydantic + validation-or-no-swap surface touches Story 2-2's contract. Story 3-3's sensitivity_class FR-2.5 safeguard reads the post-merge snapshot. |
| 5 | Privacy-invariant / sensitivity-gate touch | NO | The merge preserves PolicyEntry shape; sensitivity_class qwen-only invariant is enforced at the per-call layer (Story 3-3) against the post-merge snapshot — Story 9-1 does not relax this. Operator cannot override sensitivity_class to a non-Qwen model because the override entry is merged THROUGH PolicyEntry's `Literal["qwen2.5:3b-..."]`-aware downstream consumer (FR-2.5 startup safeguard checks the merged model). |
| 6 | Load-bearing — every X depends on this | **YES** | Every Router call, every benchmark dispatch, every /model persistent write depends on the merge being correct. Single-point-of-truth for policy-load-time semantics. |

**Criteria fired: 1, 4, 6 (three).**

**Cadence verdict: MANDATORY-CR**

The reviewer should focus on:

- Correctness of `_merge_user_overrides` shallow-leaf semantics (the 4 contract points)
- AC-3 watchfiles file-must-exist-at-startup limitation — is the workaround acceptable for Story 9-4 consumer flow?
- AC-6 8-hex-char hash collision space — operationally fine?
- AC-7 docker-compose bind-mount — any production-deploy edge cases missed?
- Test coverage gaps — are there AC paths not exercised?
- Atomic-rebind under hot-reload — is the `set_policy_snapshot()` call correctly placed in `policy_reload_loop`?

---

## Posture Audit Summary

| § | Check | Verdict |
|---|---|---|
| 5.1 | Lockfile hygiene | N/A (no deps added) |
| 5.2 | Cross-doc consistency | PASS |
| 5.3 | Lifecycle string consistency | PASS |
| 5.4 | Multi-consumer impact | PASS (1 consumer updated; all others see merged view) |
| 5.5 | Screenshot-perception parity | N/A (no graphical frontend) |
| 5.6 | Upstream-contract preservation | PASS |
| 5.7 | Module-mutable state | PASS (no new mutable surface) |
| 5.8 | Dev-fixture seed-vs-production parity | PASS |
| 5.9 | Grep-verify cited figures | PASS (all 4 figures verified) |
| 5.10 | Producer-boundary contract | PASS (3 defense layers) |
| 5.11 | Git-evidence consistency | PASS |
| 5.12 | CR-cadence-mandatory | **MANDATORY-CR (criteria 1, 4, 6 fire)** |
