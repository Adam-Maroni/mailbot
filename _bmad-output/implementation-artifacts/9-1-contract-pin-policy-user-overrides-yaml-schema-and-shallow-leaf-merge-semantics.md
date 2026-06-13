# Story 9.1: Contract pin — `policy.user-overrides.yaml` schema + shallow-leaf merge semantics

Status: done

## Story

As Adam,
I want a companion-file pattern for routing overrides at `router/policy.user-overrides.yaml` (bind-mounted, not in image), merged into the shipped `router/policy.yaml` at load time via shallow-leaf semantics, with the same Pydantic schema validation + hot-reload + validation-or-no-swap discipline,
So that `/model` persistent overrides (Story 9.4) survive image-rebuild deploys instead of being silently lost when a new policy.yaml ships, and so the merge contract is settled before either `/model` or benchmark stories touch the policy-load pathway.

## Acceptance Criteria

**AC-1 — Companion-file load path with shallow-leaf merge.**

**Given** the current single-file load path `mailbot_api/router/policy.py::load_policy(path)` reads only `router/policy.yaml`
**When** the load path is extended
**Then** the loader reads `router/policy.yaml` (baseline, in-image OR bind-mounted), then reads `router/policy.user-overrides.yaml` if present (companion, bind-mounted at `/app/router/policy.user-overrides.yaml` per AC-7), then merges via `_merge_user_overrides(baseline: PolicyTable, overrides: UserOverridesTable) -> PolicyTable` with shallow-leaf semantics
**And** shallow-leaf semantics means: for each top-level key in `tasks`, if the key exists in `overrides.tasks`, the override leaves (per-field — `model`, `prompt_version`, `escalate`, `max_tokens_out`, `lane`, `sensitivity`, `notes`, `demotion_hypothesis`, `promotion_hypothesis`, `response_cache_ttl_seconds`, `cache_warm`) replace the baseline; fields NOT present in overrides keep their baseline value; the override does NOT need to specify all fields per task
**And** if a task exists in overrides but not in baseline, the loader logs a WARNING (`event="policy.user-overrides.unknown_task"`) and DISCARDS the override entry (defensive — protects against typos that would otherwise create phantom task entries the rest of the system cannot route through)

**AC-2 — Malformed override file is non-fatal + non-swapping.**

**Given** the merge happens on every load + reload
**When** `router/policy.user-overrides.yaml` is malformed (invalid YAML, schema violation, top-level non-mapping)
**Then** the loader logs ERROR (`event="policy.user-overrides.parse_failed"`) with the specific validation error sanitized via `sanitize_error()` (same discipline as `PolicyValidationError` in current `load_policy`)
**And** the loader continues with the BASELINE policy only (the malformed override file is treated as if it did not exist)
**And** the running policy is NOT swapped per AR-D11-1 validation-or-no-swap discipline; the previous in-memory snapshot stays in place
**And** the file is NOT auto-corrected or rewritten — Adam fixes it manually
**And** an integration test asserts: malformed override file → `load_policy()` returns the baseline `PolicyTable` (not raise), error is logged once, baseline `version` is preserved

**AC-3 — Hot-reload watch set extended to companion file.**

**Given** `watchfiles.awatch` is already wired for `router/policy.yaml` in `mailbot_api/router/policy.py::policy_reload_loop`
**When** `router/policy.user-overrides.yaml` is added to the watch set
**Then** `awatch(str(policy_path), str(overrides_path), stop_event=stop_event)` watches BOTH files; hot-reload fires on either changing
**And** mid-call race acceptable per AR-D11-2 (unchanged — the snapshot-at-dispatch contract is preserved)
**And** the audit log emits `event="policy.user-overrides.swap"` with both file paths + the post-merge effective `version` on successful swap; the diff field carries a summary of which `tasks[key].field` entries changed vs the previous merged snapshot (computed via dict comparison, NOT a full YAML diff — keep it structured)
**And** if ONLY the baseline `policy.yaml` changes, the existing `event="policy.reloaded"` log is preserved (no behavior regression for Story 2-2 callers); if the override file changes (alone OR in combination), the new `policy.user-overrides.swap` event fires
**And** the companion file's ABSENCE (file does not exist) is NOT an error and NOT a watchfiles failure — `awatch` gracefully handles non-existent paths in 0.21+ (verified: see Library Versions section)

**AC-4 — Schema validation: all-Optional + extra="forbid".**

**Given** the schema is shared shape with the baseline `PolicyEntry`
**When** the user-overrides Pydantic model is defined (in `mailbot_api/router/policy.py` alongside the existing `PolicyEntry`/`PolicyTable`)
**Then** define:
  - `UserOverridesEntry(BaseModel)` — every field is `Optional[T] = None` (subset of `PolicyEntry`'s fields; supports specifying any subset)
  - `UserOverridesTable(BaseModel)` — `tasks: dict[str, UserOverridesEntry] = Field(default_factory=dict)` + optional `version: str | None = None` (the merged effective version is derived; see AC-3 effective-version computation)
  - Both models use `model_config = ConfigDict(extra="forbid")` for typo defense
**And** a unit test in `tests/unit/router/test_policy_user_overrides_merge.py` covers, at minimum:
  1. Empty overrides file (`{}` or just `tasks: {}`) → merged result equals baseline byte-for-byte (no spurious mutations)
  2. Single-field override on one task (e.g., `tasks.draft_reply.model: claude-opus-4-7`) → that task's `model` replaced; other fields of that task + other tasks entirely unchanged
  3. Full-task override on one task (every override-eligible field set) → that task fully replaced field-wise; other tasks unchanged
  4. Unknown-task override (e.g., `tasks.nonexistent_task: {...}`) → WARNING log + discard; merged result equals baseline
  5. Malformed override (top-level non-mapping; or `tasks.draft_reply.model: 42` which fails string type check) → ERROR + return baseline, no exception raised by `load_policy()`
  6. `extra="forbid"` defense — `tasks.draft_reply.unknown_field: ...` raises `PolicyValidationError`
  7. Override `tasks.draft_reply.model: null` (explicit None) → field is treated as "not specified" (None means absent in override semantics); baseline `model` preserved. (Rationale: Pydantic `Optional[str] = None` defaults to None; we must distinguish "specified as None to mean nothing" from "specified as None to override"; we choose the former because YAML-emitted None has no clear override intent — the Adam workflow of `/model qwen draft_reply` always emits a concrete value)

**AC-5 — Merge function docstring + design doc.**

**Given** the merge function is symmetric in input shape but NOT in semantics
**When** `_merge_user_overrides(baseline, overrides)` is documented
**Then** the docstring documents the shallow-leaf rule with at least two concrete examples (one single-field, one multi-field) showing the resulting `PolicyEntry.model_dump()` for clarity
**And** the docstring is explicit about the four contract points:
  1. Override leaves replace baseline leaves (per-field, NOT per-task-block)
  2. Unknown tasks are dropped with a warning
  3. None/absent fields in override = baseline preserved
  4. The merge is total: every baseline task survives unless explicitly overridden (overrides cannot DELETE a task; there is no negation primitive — Adam-decision deferred to Epic-9 retro if needed)
**And** a new design doc `docs/policy-overrides.md` (~1-2 pages) explains: why companion file pattern (image-rebuild survival, separation of source-of-truth from operator-driven tactical changes), how to use (file location, YAML shape with one example), the merge rule with the same examples as the docstring, the audit log entries (`policy.user-overrides.swap`, `policy.user-overrides.parse_failed`, `policy.user-overrides.unknown_task`), forward-reference to Story 9.4 (`/model` persistent flow integration point) and Story 9.6 (benchmark `cohort_key.router_policy_version` derivation from merged-effective `version`)

**AC-6 — `caller_origin` discipline preserved (defense-in-depth).**

**Given** `mailbot_api/router/router.py::ask_router` captures the policy snapshot via `snapshot_for_dispatch()` and the snapshot's contents flow into `router_calls` rows via the existing audit emit path
**When** an override is applied at load time
**Then** the merged `PolicyTable.version` reflects BOTH source files; the convention is `f"{baseline.version}+overrides:{stable_hash_of_overrides_yaml[:8]}"` (e.g., `"v2026-06-13+overrides:a3f4c2d9"`), so any `router_calls.policy_version` query (if such a column exists; if not, just `policy_version` exposed via `/health`) shows the override application
**And** if the overrides file is empty or absent, the version stays `f"{baseline.version}"` (no `+overrides:` suffix)
**And** the `stable_hash_of_overrides_yaml` is computed via `hashlib.sha256(overrides_text.encode("utf-8")).hexdigest()[:8]` — content-addressed, stable across whitespace-equivalent edits only if the YAML normalizes to the same canonical form (we accept that whitespace-only edits do change the hash; this is a feature, not a bug, because they may correspond to an operator-intentional re-save)

**AC-7 — Production docker-compose bind-mount + `.gitignore`.**

**Given** the current production `docker-compose.yml` does NOT mount `./router:/app/router` (only the dev `docker-compose.override.yml` does — verified at story-creation time)
**When** Story 9.1 ships
**Then** `docker-compose.yml` `mailbot-api.volumes` MUST add (read-only mount for the baseline; read-write mount for the override file so Story 9.4 can write it):
  ```yaml
  - ./router/policy.yaml:/app/router/policy.yaml:ro
  - ./router/policy.user-overrides.yaml:/app/router/policy.user-overrides.yaml
  ```
**And** the Dockerfile is NOT modified (the baseline `policy.yaml` is bind-mounted, not COPY'd — this is the safest "fixes-on-redeploy" pattern given the override file MUST survive image rebuilds)
**And** `.gitignore` is updated to ignore `router/policy.user-overrides.yaml` (the file is operator-state, not source-of-truth; Adam's overrides should NOT leak into git history)
**And** a small README or comment in `router/` documents that `policy.yaml` is the baseline (in-git, source-of-truth) and `policy.user-overrides.yaml` is the operator-state (gitignored, bind-mounted, written by Story 9.4 `set_model_persistent`)
**And** a sanity-check integration test asserts: starting the FastAPI lifespan with an empty/missing `policy.user-overrides.yaml` succeeds and the in-memory `PolicyTable.version` matches `baseline.version` (no `+overrides:` suffix); starting with a populated override file produces the `+overrides:` suffix

**AC-8 — MANDATORY-CR per §5.12.**

**Given** this is a contract pin: companion-file load path is a new architectural surface AND every policy read depends on the merge contract
**When** CR cadence is evaluated per the 6 §5.12 criteria
**Then** the §5.12 verdict is **MANDATORY-CR** because criteria 1 (new architectural surface — companion-file load path + new Pydantic models + new merge function) AND 6 (load-bearing — every Router call, every benchmark dispatch, every `/model` persistent write depends on this merge contract being correct) fire
**And** the code-review subagent runs under `claude-sonnet-4-6` per the dev-vs-review-different-model invariant
**And** the pre-review self-audit artifact (`9-1-contract-pin-policy-user-overrides-yaml-schema-and-shallow-leaf-merge-semantics.pre-review.md`) records the §5.12 verdict before the CR dispatch

## Tasks / Subtasks

- [ ] **Task 1 — Pydantic models** (AC: 4)
  - [ ] Subtask 1.1 — Add `UserOverridesEntry(BaseModel)` to `mailbot_api/router/policy.py`. Mirror every `PolicyEntry` field as `Optional[T] = None`. Set `model_config = ConfigDict(extra="forbid")`.
  - [ ] Subtask 1.2 — Add `UserOverridesTable(BaseModel)` with `tasks: dict[str, UserOverridesEntry] = Field(default_factory=dict)` + `version: str | None = None`. `extra="forbid"`.
  - [ ] Subtask 1.3 — Export both new models from `__all__` at module bottom.

- [ ] **Task 2 — Merge function** (AC: 1, 4, 5)
  - [ ] Subtask 2.1 — Implement `_merge_user_overrides(baseline: PolicyTable, overrides: UserOverridesTable) -> PolicyTable`. Iterate `overrides.tasks.items()`; for each key, if in baseline.tasks, build a new `PolicyEntry` via `baseline.tasks[key].model_copy(update={k: v for k, v in override.model_dump(exclude_none=True).items()})`; if not in baseline.tasks, log WARNING and skip.
  - [ ] Subtask 2.2 — Compose new `PolicyTable` with the merged tasks dict + the version-derivation from AC-6 (`f"{baseline.version}"` if overrides absent or empty, else `f"{baseline.version}+overrides:{hash[:8]}"`).
  - [ ] Subtask 2.3 — Write the docstring per AC-5 (two concrete examples + four contract points).

- [ ] **Task 3 — Extend `load_policy()`** (AC: 1, 2)
  - [ ] Subtask 3.1 — Change signature to `load_policy(path: Path, *, overrides_path: Path | None = None) -> PolicyTable`. Default `overrides_path` to `path.parent / "policy.user-overrides.yaml"` if `None` AND that file exists; otherwise, no override.
  - [ ] Subtask 3.2 — After baseline `PolicyTable.model_validate(raw)`, check if `overrides_path` exists. If yes, read + `yaml.safe_load` + `UserOverridesTable.model_validate`. On ANY failure (FileNotFoundError treated as "no overrides", but YAMLError or ValidationError treated as malformed): log ERROR `event="policy.user-overrides.parse_failed"` with sanitized details, return baseline (do NOT raise).
  - [ ] Subtask 3.3 — On successful override-load, call `_merge_user_overrides(baseline, overrides)` and return the merged table.
  - [ ] Subtask 3.4 — Add a SHA-256 hash helper for the overrides file content (per AC-6).

- [ ] **Task 4 — Extend `policy_reload_loop`** (AC: 3)
  - [ ] Subtask 4.1 — Change signature to `policy_reload_loop(path: Path, *, overrides_path: Path | None = None, stop_event: asyncio.Event | None = None) -> None`.
  - [ ] Subtask 4.2 — Pass BOTH paths to `awatch(str(path), str(overrides_path), stop_event=stop_event)` when `overrides_path` is not None; if `overrides_path is None`, watch only the baseline (preserve backward compatibility for any test caller).
  - [ ] Subtask 4.3 — On every change event, call `load_policy(path, overrides_path=overrides_path)`. On success, compare the merged result to the previous module-level snapshot (via `_policy.model_dump() != new_table.model_dump()`) to determine which event to log:
    - If the previous `version` did NOT contain `+overrides:` and the new one DOES → emit `policy.user-overrides.swap` with both paths
    - If the previous `version` DID contain `+overrides:` and the new one does too → emit `policy.user-overrides.swap` if the override hash changed, else `policy.reloaded`
    - If neither version has `+overrides:` (overrides file absent in both pre and post) → emit `policy.reloaded` (unchanged from current behavior)
  - [ ] Subtask 4.4 — Compute the structured diff (which `tasks[key].field` entries differ between pre + post merged snapshots) and include in the `extra={}` payload of the `policy.user-overrides.swap` log row.

- [ ] **Task 5 — Update `mailbot_api/main.py` lifespan wiring** (AC: 1, 7)
  - [ ] Subtask 5.1 — In the lifespan policy-load block (around lines 105-115), resolve `overrides_path = Path(get_secret_optional("MAILBOT_POLICY_OVERRIDES_PATH", "/app/router/policy.user-overrides.yaml"))`.
  - [ ] Subtask 5.2 — Pass `overrides_path` to `load_policy(policy_path, overrides_path=overrides_path)`.
  - [ ] Subtask 5.3 — Pass `overrides_path` to `policy_reload_loop(policy_path, overrides_path=overrides_path, stop_event=policy_stop_event)`.
  - [ ] Subtask 5.4 — Log the resolved overrides_path at startup so operators see what file the lifespan is watching.

- [ ] **Task 6 — Unit tests** (AC: 1, 2, 3, 4, 5, 6)
  - [ ] Subtask 6.1 — Create `tests/unit/router/test_policy_user_overrides_merge.py`. Cover the seven AC-4 cases plus AC-6 version-suffix computation.
  - [ ] Subtask 6.2 — Hash determinism test: same YAML content → same suffix; differ-by-whitespace YAML → differ-by-suffix (per AC-6 stance).
  - [ ] Subtask 6.3 — Backward-compat test: `load_policy(path)` without `overrides_path` AND no companion file in `path.parent` returns baseline unchanged (no `+overrides:` suffix).

- [ ] **Task 7 — Integration tests** (AC: 2, 3, 7)
  - [ ] Subtask 7.1 — Create `tests/integration/test_policy_user_overrides_lifespan.py`. Boot the FastAPI lifespan with a temp policy.yaml + temp policy.user-overrides.yaml fixture; assert merged `version` carries `+overrides:` suffix; `get_policy().tasks['draft_reply'].model` reflects override.
  - [ ] Subtask 7.2 — Lifespan with absent overrides file: merged version matches baseline; no error log.
  - [ ] Subtask 7.3 — Hot-reload integration: start lifespan; mutate the overrides file; await the next reload (poll `get_policy().tasks[...]` for up to 5s); assert the new model is reflected.
  - [ ] Subtask 7.4 — Malformed-override-on-reload: start lifespan with valid overrides; mutate to invalid YAML; assert `policy.user-overrides.parse_failed` log emitted; assert `get_policy()` STILL returns the previous valid merged snapshot (NOT raised, NOT reverted to baseline — the previous merged snapshot stays).

- [ ] **Task 8 — Documentation** (AC: 5)
  - [ ] Subtask 8.1 — Create `docs/policy-overrides.md` per AC-5 spec.
  - [ ] Subtask 8.2 — Update `mailbot_api/router/policy.py` module docstring to reference the new contract (companion-file pattern, merge semantics).

- [ ] **Task 9 — docker-compose + .gitignore** (AC: 7)
  - [ ] Subtask 9.1 — Edit `docker-compose.yml` `mailbot-api.volumes`: add `./router/policy.yaml:/app/router/policy.yaml:ro` and `./router/policy.user-overrides.yaml:/app/router/policy.user-overrides.yaml`.
  - [ ] Subtask 9.2 — Edit `.gitignore`: add `router/policy.user-overrides.yaml`.
  - [ ] Subtask 9.3 — Create `router/policy.user-overrides.yaml.example` with a brief comment explaining the file's purpose + a commented-out example task override (so operators discover the surface in their first directory listing).

- [ ] **Task 10 — Pre-review self-audit + MANDATORY-CR** (AC: 8)
  - [ ] Subtask 10.1 — Generate `_bmad-output/implementation-artifacts/9-1-contract-pin-policy-user-overrides-yaml-schema-and-shallow-leaf-merge-semantics.pre-review.md` per Step 2.3.5 of `autonomous-epic-run/SKILL.md` — sections 1-5 mandatory, §5.12 verdict = `MANDATORY-CR`.
  - [ ] Subtask 10.2 — Orchestrator dispatches the code-review subagent under `claude-sonnet-4-6` per Phase 1 contract.

## Dev Notes

### Architecture surface being modified

**File: `mailbot_api/router/policy.py`** — currently 240 lines. This story extends it with:
- 2 new Pydantic models (`UserOverridesEntry`, `UserOverridesTable`)
- 1 new merge function (`_merge_user_overrides`)
- Extended `load_policy(path, *, overrides_path=None)` signature
- Extended `policy_reload_loop(path, *, overrides_path=None, stop_event=None)` signature
- 1 new helper (overrides-file SHA-256 hash for version-suffix)
- Updated module docstring

**Module-level state:** the `_policy` global pattern (set via `set_policy_snapshot`, read via `get_policy()`/`snapshot_for_dispatch()`) stays UNCHANGED. The merge happens at load time before `set_policy_snapshot` is called; the in-memory snapshot is always the post-merge `PolicyTable`. This means downstream callers (Router, audit, escalation, sensitivity safeguard) see the merged view transparently — they don't know overrides exist.

### Why a companion file and not edit-policy.yaml-in-place

`policy.yaml` is checked into git as source-of-truth and SHIPS WITH IMAGE BUILDS (eventually — see "Production deploy gap" below). Operator-driven tactical changes via `/model` (Story 9.4) MUST survive an image rebuild that ships an updated `policy.yaml`. Editing `policy.yaml` in place would either (a) be overwritten on next deploy, OR (b) require git mutations from the running container — both unacceptable.

The companion-file pattern:
- Baseline `policy.yaml` ships in-image (gitted, source-of-truth)
- Override `policy.user-overrides.yaml` is bind-mounted (gitignored, operator-state)
- Merge happens at load time + on every reload
- Audit log shows the merge happened + which fields changed

### Production deploy gap (discovered at story-creation time — pre-existing latent issue)

**Finding:** The `mailbot-api` Dockerfile does NOT COPY the `router/` directory into the image. Yet `main.py` defaults `MAILBOT_POLICY_PATH=/app/router/policy.yaml`. In dev mode, `docker-compose.override.yml` line 16 (`./router:/app/router`) provides the file via bind-mount; in production mode (base `docker-compose.yml`), there is NO bind-mount AND no COPY → `policy.yaml` would NOT exist at the expected path.

This was latent because Stories 2-2 through 5-9 ran under dev-mode override OR tests that supply `MAILBOT_POLICY_PATH` via env var. The first production deploy (CP-1) would have hit this. Story 9.1 surfaces and closes the gap by adding explicit bind-mounts in the base `docker-compose.yml` per AC-7. Treat this as part of Story 9.1's scope, not a separate hotfix.

**Cross-story finding to file:** flag this in `epic-9-run-flags.md` under `## Findings` for retro discussion: "production docker-compose was missing `policy.yaml` bind-mount (latent since Story 1-2 image baseline); fixed in Story 9.1 AC-7 as part of companion-file plumbing."

### Why merge at load time, not at lookup time

Two alternatives were considered:
1. **Merge at load time** (chosen) — `load_policy` returns the merged `PolicyTable`; downstream code is unaware overrides exist. Simpler call path, single audit point, no per-call merge cost.
2. **Merge at lookup time** — keep two `PolicyTable` instances; `get_policy()` walks override first, then baseline. Allows lazy evaluation but introduces per-call branches and a possible non-atomic mid-call swap if one snapshot updates without the other.

Chosen path (1) preserves AR-D11-2 (mid-call race acceptable) symmetrically across both source files — a single merged snapshot is captured at dispatch and used throughout the call.

### Why shallow-leaf and not deep-merge

`PolicyEntry` is a flat record (no nested structure beyond Optional scalars). Deep-merge has no meaningful semantics here. Shallow-leaf is the natural fit AND matches the Pydantic `model_copy(update={...})` primitive directly.

### Version derivation contract (AC-6) — explanation

The reason for the `+overrides:<hash>:` suffix is observability + benchmark cohort grouping. Story 9.6's `benchmark_runs.cohort_key` is composed of `(prompt_v, scorer_model, anchors_v, router_policy_v)`. The fourth tuple element `router_policy_v` MUST distinguish "ran on baseline policy.yaml v2026-06-13 with no overrides" from "ran on baseline policy.yaml v2026-06-13 with override file hash=a3f4c2d9" — otherwise benchmark results that span an Adam-issued `/model qwen draft_reply` mid-run would be grouped as the same cohort despite different routing.

The hash is short (8 hex chars = 32 bits) because collision is operationally acceptable here — Adam's overrides change infrequently and Adam would notice if two un-related overrides produced visually-confusing identical hashes. Full SHA-256 in the audit log + 8-char in the version-suffix is the standard Git approach.

### Cross-story dependencies (forward references)

- **Story 9.2** (`model_chosen_reason` enum) is a sibling contract pin; both land before Stories 9.3+ touch the router force-path.
- **Story 9.3** (`/model` one-shot) does NOT touch the policy load path — it only sets a session-scoped flag the router reads. No coupling with 9.1 except both must succeed before /model is end-to-end usable.
- **Story 9.4** (`/model` persistent) IS the consumer of Story 9.1's contract — `set_model_persistent` writes to `router/policy.user-overrides.yaml` and relies on hot-reload (AC-3) to make the change effective.
- **Story 9.6** (benchmark runner) consumes `policy_version` for `cohort_key` — relies on AC-6 version-suffix.
- **Stories 9.10/9.11** are unrelated to policy load.

### Testing standards (boundary contract + ALL-VERBOSE log discipline)

- Every test that writes a YAML file MUST clean up via `tmp_path` (pytest fixture) — do NOT write to repo files even in tests.
- Log assertions: use `caplog.set_level(logging.ERROR)` for parse-fail tests; assert `event=` key in `record.extra` (consistent with how Story 2-2 tests Story-2-2's existing `policy.reloaded` event).
- Mock the SHA-256 hash function in version-suffix tests — pass in a known-content YAML and assert exact suffix string. (Avoid Python's `hashlib` indirection being a test-coupling point.)
- Hot-reload integration test SHOULD use a real `watchfiles.awatch` poll loop with a 3-5s timeout and an explicit `stop_event.set()` in teardown — do NOT mock `awatch`, the timing-correctness of the watcher is part of what the test validates.

### Library versions

- `watchfiles >= 0.21.0` (already pinned in `requirements.txt` from Story 2-2) — supports multi-path watch via `awatch(p1, p2, ..., stop_event=...)`. Verify the pin allows this signature.
- `pydantic >= 2.5` (already pinned) — supports `model_copy(update={...})` and `model_config = ConfigDict(extra="forbid")`.
- `pyyaml >= 6.0` (already pinned) — `safe_load` semantics unchanged.

### Project Structure Notes

- All new code lives in `mailbot_api/router/policy.py` (single-file extension) — alignment with the architecture's "policy module is the only YAML reader for routing config" boundary check.
- The new design doc `docs/policy-overrides.md` lives under `docs/` (NOT under `docs/external/` — it's project-internal documentation, not vendored upstream content).
- The new test files live under `tests/unit/router/` (model-level unit tests) and `tests/integration/` (lifespan + hot-reload).
- `router/policy.user-overrides.yaml.example` lives next to `router/policy.yaml` so operators discover both as a pair.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 9 Detail — Story 9.1 (lines 3114-3154)] — canonical AC source
- [Source: _bmad-output/planning-artifacts/architecture.md#policy.yaml reload semantics (D11) (lines 385-388)] — AR-D11-1 validation-or-no-swap, AR-D11-2 mid-call race acceptable
- [Source: mailbot_api/router/policy.py:1-240] — current implementation being extended
- [Source: mailbot_api/main.py:103-194] — lifespan policy-load + watcher wiring being extended
- [Source: docker-compose.yml:70-109] — production mailbot-api service definition (no `./router` bind-mount currently)
- [Source: docker-compose.override.yml:14-18] — dev-mode `./router:/app/router` bind-mount (the surviving mechanism that masked the production gap)
- [Source: docker/Dockerfile.mailbot-api:53-55] — Dockerfile COPY directives (no `router/` COPY)
- [Source: _bmad-output/implementation-artifacts/sprint-status.yaml:228-231] — cohort_key Adam-decision context (informs AC-6 version-suffix design)
- [Source: .claude/skills/autonomous-epic-run/references/posture-audit.md#5.12 CR-cadence-mandatory] — §5.12 verdict definition for AC-8

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context, inline execution via /autonomous-epic-run main loop)

### Debug Log References

- Initial integration-test run surfaced `watchfiles.awatch FileNotFoundError: Input watch path is neither a file nor a directory` when override file absent at watcher start. Resolved by filtering watch_paths to only existing files at startup + documenting first-deploy bootstrap requirement in `docs/policy-overrides.md`.

### Completion Notes List

**AC verification (Story 9-1):**

- **AC-1 (companion-file load + shallow-leaf merge):** MATCH. `load_policy(path, *, overrides_path=None)` extended; `_merge_user_overrides()` implemented with per-field shallow-leaf semantics; unknown-task entries logged and discarded.
- **AC-2 (malformed override non-fatal):** MATCH. All override-side failure paths (FileNotFoundError-equivalent, OSError, yaml.YAMLError, ValidationError, non-mapping top-level, empty-file) → log `policy.user-overrides.parse_failed` at ERROR + return baseline. Baseline failures still raise (unchanged).
- **AC-3 (hot-reload watch set extended):** MATCH WITH NUANCE. `policy_reload_loop` extended to take `overrides_path` kwarg; `awatch` covers both files when override exists at startup. **Discovered watchfiles contract limitation:** non-existent paths raise `FileNotFoundError`; cannot watch a file before it exists. Documented in `docs/policy-overrides.md` "Hot-reload contract limitation — file-must-exist-at-startup" section; Story 9-4 owns the create-flow + restart-requirement surfacing.
- **AC-4 (all-Optional + extra="forbid" schema):** MATCH. `UserOverridesEntry` (every field `Optional[T] = None`) + `UserOverridesTable` (tasks defaults to `{}`) + 19 unit tests covering all 7 AC-4 cases.
- **AC-5 (merge function docstring + design doc):** MATCH. `_merge_user_overrides` docstring documents 4 contract points + 2 concrete examples. `docs/policy-overrides.md` (~150 lines) covers why-companion-file, file location, schema, merge semantics with examples, failure handling, audit events, version-suffix derivation, forward references, hot-reload limitation, race semantics.
- **AC-6 (version-suffix `+overrides:<sha256[:8]>`):** MATCH. `_compute_overrides_hash` + `_compute_merged_version` helpers; suffix appears IFF file exists with parseable content. Hash determinism + whitespace-sensitivity verified in unit tests.
- **AC-7 (production docker-compose bind-mount):** MATCH. `docker-compose.yml` extended with `./router/policy.yaml:/app/router/policy.yaml:ro` + `./router/policy.user-overrides.yaml:/app/router/policy.user-overrides.yaml`. `.gitignore` excludes `router/policy.user-overrides.yaml` but tracks the `.example` sibling. `router/policy.user-overrides.yaml.example` created with operator-facing template + `tasks: {}` no-op default.
- **AC-8 (MANDATORY-CR per §5.12):** PENDING. Pre-review self-audit + CR subagent dispatch next.

**Architectural finding (filed for epic-9-run-flags.md):**

Discovered during AC-7 implementation: `router/sensitivity_patterns.yaml` has the same latent production gap as `policy.yaml` (no Dockerfile COPY; lifespan defaults `/app/router/sensitivity_patterns.yaml`; dev-mode bind-mount in docker-compose.override masks the issue). Out of scope for Story 9-1. Filed as a sibling finding for the follow-up story.

**Test outcomes:**

- New unit tests (19): `tests/unit/router/test_policy_user_overrides_merge.py` — all pass.
- New integration tests (6): `tests/integration/test_policy_user_overrides_lifespan.py` — all pass.
- Full test suite: 1193 passed + 2 skipped + 3 deselected (was 1168 at baseline e26acf5; +25 net per Story 9-1 expectation).
- All 4 quality gates green: ruff clean, mypy --strict clean (no new issues in policy.py + main.py), boundary check clean.

**Sanity baseline:** the pre-existing 1168-test corpus continues to pass unchanged — backward-compat preserved for Story 2-2's `load_policy(path)` callers (the override-loading is silently a no-op when no companion file exists in `path.parent` and `overrides_path` is None).

### File List

**Modified:**

- `mailbot_api/router/policy.py` — added UserOverridesEntry, UserOverridesTable, _compute_overrides_hash, _compute_merged_version, _merge_user_overrides, _version_has_overrides_suffix; extended load_policy + policy_reload_loop with `overrides_path` kwarg; updated module docstring and `__all__`.
- `mailbot_api/main.py` — extended lifespan to resolve `overrides_path` env var (defaults to `policy_path.parent / "policy.user-overrides.yaml"`), pass to load_policy + policy_reload_loop, log overrides_path + presence at startup.
- `docker-compose.yml` — added `./router/policy.yaml:/app/router/policy.yaml:ro` + `./router/policy.user-overrides.yaml:/app/router/policy.user-overrides.yaml` bind-mounts under `mailbot-api.volumes`. Closes pre-existing latent production gap (Dockerfile does not COPY `router/`; dev-mode bind-mount in override masks this).
- `.gitignore` — added `router/policy.user-overrides.yaml` (operator-state) + negation pattern `!router/policy.user-overrides.yaml.example` (template tracked).

**New:**

- `tests/unit/router/test_policy_user_overrides_merge.py` — 19 unit tests covering AC-4 (7 cases) + AC-6 version-suffix + AC-2 malformed-non-fatal + backward-compat.
- `tests/integration/test_policy_user_overrides_lifespan.py` — 6 integration tests covering lifespan-shape load + 4 hot-reload paths (mutation, malformed-on-reload, override-change-emit-swap, baseline-only-emit-reloaded).
- `docs/policy-overrides.md` — design doc (~180 lines).
- `router/policy.user-overrides.yaml.example` — operator-facing template (gitted, opens with operator-onboarding doc comment + commented examples + empty `tasks: {}` no-op).

**Pre-review self-audit + CR artifact:**

- `_bmad-output/implementation-artifacts/9-1-contract-pin-policy-user-overrides-yaml-schema-and-shallow-leaf-merge-semantics.pre-review.md` — 5-section forensic self-audit per Step 2.3.5.

### MANDATORY-CR Pass — sonnet-4-6 reviewer

**§5.12 verdict at pre-review:** MANDATORY-CR (criteria 1 + 4 + 6 fired). CR-subagent dispatched under `claude-sonnet-4-6` per dev-vs-review-different-model invariant (dev was `claude-opus-4-7`).

**7 findings (1 CRITICAL + 2 HIGH + 3 MEDIUM + 1 LOW):**

- **F1 CRITICAL — AC-2 contract violation:** `policy_reload_loop` was unconditionally swapping to baseline-only snapshot when override file became malformed, violating AC-2 "the running policy is NOT swapped." **PATCH APPLIED:** new `load_policy_with_status()` returns `(PolicyTable, OverrideLoadStatus)`; reload loop checks `status == "parse_failed"` and refuses the swap. Integration test re-written to assert the prior merged snapshot survives malformed-override mutation. New unit tests cover all 4 `OverrideLoadStatus` branches.
- **F2 HIGH — Comment-vs-code drift in main.py:** Pre-existing comment claimed "watchfiles 0.21+ gracefully handles non-existent paths" — contradicted by the actual code (filter to existing paths only). **PATCH APPLIED:** comment rewritten to accurately describe the filter behavior + cross-reference `docs/policy-overrides.md` "Hot-reload contract limitation".
- **F3 HIGH — Zero-byte vs `tasks: {}` version-suffix inconsistency:** Zero-byte file produced no suffix; `tasks: {}` produced a suffix. AC-6 specifies "empty or absent → no suffix" — both should be no-suffix. **PATCH APPLIED:** `_merge_user_overrides` now returns `(merged_tasks, applied_field_count)`; `load_policy_with_status` returns `status="empty"` when count is zero (regardless of file presence); version field gets no suffix. Unit tests updated to assert the corrected behavior + new `_load_policy_with_status_empty` test.
- **F4 MEDIUM — Spurious reload event on content-identical rewrite:** **DEFERRED.** Real-world impact is observability noise only (`policy.reloaded` instead of nothing); content-identical rewrites are operationally rare. Documented as acceptable noise in the comment block of policy_reload_loop.
- **F5 MEDIUM — Test fixture missing `Iterator[None]` annotation:** Fixture used `yield` but was annotated `-> None`. **PATCH APPLIED:** annotation corrected to `-> Iterator[None]` on the fixture + all 4 test functions that consume it; `from collections.abc import Iterator` added.
- **F6 MEDIUM — `_merge_user_overrides` double-construct maintenance trap:** Function was constructing a `PolicyTable` with the WRONG version (unsuffixed baseline), then the caller discarded that version and rebuilt the table with the correct merged version. **PATCH APPLIED:** function now returns `(dict[str, PolicyEntry], applied_field_count)` directly; caller composes the final `PolicyTable`. Three new unit tests cover the returned-tuple shape.
- **F7 LOW — Bind-mount RW permission risk:** UID-alignment between the host-side `touch`ed file and the mailbot user inside the container is unverified. **DEFERRED to Story 9-4** (which owns the write path).

**Applied rate:** 5/7 actionable PATCHES applied = **71% applied rate** (above the ≥70% target documented in epic-3-retro). 2 DEFER with rationale (F4 + F7).

**Post-CR test outcomes:**

- 32 new Story 9-1 tests pass (19 unit + 6 integration baseline + 7 dedicated F1/F3/F6 tests).
- Full suite: 1200 passed + 2 skipped + 3 deselected (was 1193 pre-CR; +7 from new tests).
- All 4 quality gates green: ruff clean, mypy --strict clean, boundary check clean, pytest green.

**Architectural delta from CR:** new public function `load_policy_with_status(path, *, overrides_path=None) -> tuple[PolicyTable, OverrideLoadStatus]` + new `OverrideLoadStatus` Literal exported from `mailbot_api.router.policy`. `load_policy()` (the original, single-return API) is preserved as a convenience wrapper that discards the status — backward-compat for all Story 2-2 callers. The reload loop uses the new function exclusively.
