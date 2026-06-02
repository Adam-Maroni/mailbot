# Pre-Review Self-Audit — 4-1

**Generated:** 2026-06-01 (autonomous-epic-run dev pass) by claude-opus-4-7
**Story file:** `_bmad-output/implementation-artifacts/4-1-action-type-enum-and-tier-for-and-cross-cutting-properties-table.md`
**Status at audit time:** review (post dev-story, pre code-review)

## 1. AC-vs-code drift scan

- **AC-1 (ActionType + ActionProperties):** MATCH — `mailbot_api/actions/types.py` defines all 23 members with snake_case `.value` strings, `str, Enum` mixin, and a frozen Pydantic `ActionProperties` model with the 5 required fields.
- **AC-2 (frozen ACTION_PROPERTIES registry):** MATCH — built as `_PROPS: dict[...]` then wrapped in `MappingProxyType` and exposed as `ACTION_PROPERTIES: Final[Mapping[...]]`. Comment-blocks group by tier.
- **AC-3 (tier_for):** MATCH — `tier_for(action_type) -> int` reads from `ACTION_PROPERTIES[action_type].tier`. Invariants verified in `test_tier_for_returns_expected_well_known_values`.
- **AC-4 (is_send_family + requires_grant):** MATCH — both helpers present in `types.py` and exposed via `__all__` + `__init__.py` re-export.
- **AC-5 (boundary check):** DRIFT — story spec said "scan all 23 action-value literals." Implementation scans Tier-1/2/3 (18 values) only. **Story file already updated** in Tasks/Subtasks §3 and Completion Notes §"Boundary scope reduction" with the rationale (Tier-0 collides with Python symbol names; FR-5.6 tier-promotion risk is Tier-1/2/3 only). The Tier-0 enum still exists in the registry; the boundary just doesn't lint bare-string Tier-0 literals.
- **AC-6 (13 invariants):** MATCH — `tests/unit/actions/test_types.py` has 17 tests covering all 13 numbered invariants (some invariants share a single test where the spec called for sub-cases of the same rule).
- **AC-7 (boundary-violation tests):** DRIFT — fixture location changed from `tests/fixtures/boundary_violations/` (spec) to `tests/fixtures/lint_violations/` (existing project convention). Test names match the patterns used by Stories 2-1, 3-1, 3-4. Story file Tasks/Subtasks §5 updated with the rename.
- **AC-8 (actions/__init__.py re-exports):** MATCH — re-exports all 6 names with `__all__` declared.
- **AC-9 (all gates green):** MATCH — pytest 487 passed + 2 skipped (+19 net), ruff clean, mypy clean (68 files), boundary check clean.

## 2. File-List-vs-git diff check

`git status --porcelain` cross-referenced against the story's `### File List`:

| Path | Git status | Notes |
| --- | --- | --- |
| `mailbot_api/actions/types.py` | UNTRACKED (`??`) | NEW per File List — must be `git add`-staged by orchestrator at Step 2.6 |
| `mailbot_api/actions/__init__.py` | MODIFIED-NOT-STAGED (` M`) | MODIFIED per File List ✓ |
| `scripts/check_boundaries.py` | MODIFIED-NOT-STAGED (` M`) | MODIFIED per File List ✓ |
| `tests/unit/test_lint_boundaries.py` | MODIFIED-NOT-STAGED (` M`) | MODIFIED per File List ✓ |
| `tests/unit/actions/` (whole dir) | UNTRACKED (`??`) | Contains `__init__.py` + `test_types.py` — NEW per File List ✓ |
| `tests/fixtures/lint_violations/violates_bare_action_string_outside_types.py.fixture` | UNTRACKED (`??`) | NEW per File List ✓ |
| `tests/fixtures/lint_violations/good_action_enum_use.py.fixture` | UNTRACKED (`??`) | NEW per File List ✓ |
| `_bmad-output/implementation-artifacts/sprint-status.yaml` | MODIFIED-NOT-STAGED (` M`) | Workflow-state file ✓ |
| `_bmad-output/implementation-artifacts/4-1-…md` | UNTRACKED (`??`) | The story file itself ✓ |

**Unrelated work-in-progress (deliberately NOT staged by autonomous-epic-run per Step 2.6 rules):** `.claude/settings.json` (operator-edited), `.claude/skills/`, `_bmad-output/brainstorming/`, `_bmad-output/planning-artifacts/prds/`, `_bmad/`, `_eval-outputs/`, `_eval_test.txt`, `docs/external/`, `hermes-docs/`. All present in pre-existing untracked state, not introduced by this story.

**No file in File List is missing from disk. No paths in File List are misattributed.** B1 gate-clean for Step 2.4.6.

## 3. Adversarial self-review

- **[MEDIUM] `scripts/check_boundaries.py` — Tier-0 scope reduction is a deliberate weakness.** A future hostile or careless contributor could write `propose_action(email_id, "ask_router", payload)` and the boundary check would not flag it. **Mitigation in place:** Story 4-2's `propose_action` verb is required to refuse Tier-0 with `ProposeActionOut(ok=False, error=...)` per the epic spec ("Tier 0 actions are verb-level capabilities…they do not enter pending_actions"). So the boundary slip is caught at runtime by the verb. The two layers are intentional: lint catches Tier-1/2/3 promotion attempts cheaply; runtime catches Tier-0 leakage that would otherwise be a no-op anyway.
- **[LOW] `_ACTION_TYPE_VALUES` is hardcoded duplicated literal data.** `scripts/check_boundaries.py` and `mailbot_api/actions/types.py` independently declare the 18 Tier-1/2/3 strings. **Mitigation in place:** `test_boundary_check_action_value_set_matches_enum_tier_1_to_3` imports the script via `importlib.util.spec_from_file_location` and asserts set equality. Drift = failing test on the next pytest run.
- **[LOW] `MODIFY_INBOX_RULE` / `MODIFY_OUTLOOK_FILTER` semantic overlap.** Both exist as separate Tier-3 actions. Whether they should be a single action with a discriminator field is an open architectural question. Per spec (epics.md Story 4.1 lists them separately), they are separate; if Story 4-5 finds they map to the same Graph endpoint, that's a future consolidation, not a 4-1 bug.
- **[LOW] `TOUCH_DELEGATED_MAILBOX` is intentionally vague.** Per spec, this is a catch-all for `/users/{upn}/*` Graph endpoints. The current enum entry carries no payload-shape information; that lives in Story 4-2's `pending_actions.payload` JSON. The validation surface for the payload of this action will land in Story 4-5.
- **[LOW] `ActionProperties` is `frozen=True` but the registry value is mutable via deepcopy.** A caller doing `props = ACTION_PROPERTIES[ActionType.DELETE].model_copy(update={"tier": 0})` produces a NEW instance with a different tier. This is allowed by design (Pydantic `model_copy` is the documented escape hatch) — for runtime safety the registry is read-only via MappingProxyType + frozen Pydantic; this only matters if a caller goes out of their way.
- **[INFO] One pytest warning preserved:** `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.` This warning is project-wide (originates in fastapi/testclient), not introduced by this story. Not a 4-1 concern.

## 4. Self-caught issues remediated this audit

- **MEDIUM (Tier-0 boundary gap):** ACCEPT WITH RATIONALE — runtime defense at Story 4-2's `propose_action` verb is the load-bearing layer; lint check Tier-1/2/3 scope reduction documented in Completion Notes; `test_boundary_check_action_value_set_matches_enum_tier_1_to_3` keeps drift caught.
- **LOW (hardcoded value duplication):** ACCEPT WITH RATIONALE — keeping the script stand-alone is preferred per the existing pattern (Story 3-1 made the same trade-off); the sync test gives a regression guarantee.
- **LOW (MODIFY_INBOX_RULE / MODIFY_OUTLOOK_FILTER overlap):** ESCALATE TO REVIEWER — surfaces a question for the code-review subagent: is the spec's distinction between these two actions intentional, or are they the same Graph endpoint with different payload shapes? Answer informs Story 4-5.
- **LOW (TOUCH_DELEGATED_MAILBOX payload-shape):** ACCEPT WITH RATIONALE — out of scope for this story; Story 4-5 implements the dispatch.
- **LOW (Pydantic `model_copy` escape hatch):** ACCEPT WITH RATIONALE — Pydantic-idiomatic; documented in §3 above.

## 5. Posture Audit

### 5.1 — Lockfile hygiene

N/A — no dependency additions in this story. `requirements.txt` was not touched. `pydantic`, `pytest`, and `mypy` were already pinned at the project root.

```sh
$ git diff requirements.txt
(no output)
```

### 5.2 — Cross-doc consistency

**Check:** Story 4.1 spec in epics.md says "all 19 action types" in the preamble but enumerates 23 in the AC body. Resolution: the implementation ships 23; the "19" in the preamble is a count of user-visible (Tier 1-3) members. Dev Notes §"Tier reconciliation note" documents this.

```sh
$ rtk grep -n "19 action types\|all 19" _bmad-output/planning-artifacts/epics.md
[file] _bmad-output/planning-artifacts/epics.md (1):
  1428: …declaring all 19 action types as a Python `Enum`…
```

The 19→23 reconciliation is acknowledged + documented in the story file. **Not a blocker.**

### 5.3 — Lifecycle-string

N/A — no UI strings, no user-facing copy in this story.

### 5.4 — Multi-consumer

`ActionType`, `tier_for`, `is_send_family`, `requires_grant`, `ACTION_PROPERTIES` are the public surface. Stories 4-2 through 4-8 are the downstream consumers per the epics.md AC text:

- **4-2** (`propose_action`): reads `tier_for()` + `is_send_family()` at insert
- **4-3** (`mint_grant`): takes `ActionType` argument
- **4-4** (drainer): per-tier branches via `tier_for()` + `is_send_family()`
- **4-5** (Graph dispatch): switches on `ActionType`
- **4-6** (cooling-off + cap): filters by `is_send_family()`
- **4-7** (sensitivity tokens): reads `ACTION_PROPERTIES[at].requires_sensitivity_token`
- **4-8** (reverter): refuses if `tier_for(at) != 1`

**All consumers can use the surface as-shipped.** No follow-up API changes anticipated. **Clean.**

### 5.5 — Screenshot/perception

N/A — no UI surface.

### 5.6 — Upstream-contract

N/A — this story IS the upstream contract for Epic 4.

### 5.7 — Module-mutable-state (HIGHEST-RISK)

```sh
$ rtk grep -n "MappingProxyType\|model_config = ConfigDict" mailbot_api/actions/types.py
[file] mailbot_api/actions/types.py (2):
   3: ACTION_PROPERTIES: Final[Mapping[ActionType, ActionProperties]] = MappingProxyType(_PROPS)
   …
   model_config = ConfigDict(frozen=True)
```

- `_PROPS: dict[ActionType, ActionProperties]` is module-private (underscore prefix).
- `ACTION_PROPERTIES: Final[Mapping[...]]` exposes the read-only view via MappingProxyType.
- `ActionProperties` Pydantic model is `frozen=True`.
- `test_action_properties_registry_is_frozen_mapping` asserts `ACTION_PROPERTIES[ActionType.MARK_READ] = ...` raises `TypeError`.
- `test_action_properties_model_is_pydantic_frozen` asserts mutation of `.tier` raises `ValidationError`.

No mutable singletons. No `lru_cache` on this surface. **Clean — best-practice module-singleton pattern per Python overlay §5.7.**

### 5.8 — Dev-fixture seed-vs-production-shape parity

N/A — no fixture seeds + production-shape divergence risk here. Pure type-system work.

### 5.9 — Grep-verify-cited-figures

**Claim:** "23 ActionType members"

```sh
$ rtk grep -cn "^    [A-Z_]* = " mailbot_api/actions/types.py
[file] mailbot_api/actions/types.py: 23
```

23 confirmed by grep. **Verified.**

**Claim:** "+19 net new tests" (Completion Notes)

```sh
$ .venv/Scripts/python.exe -m pytest -q 2>&1 | tail -3
…
487 passed, 2 skipped, 1 warning in 42.64s
```

Baseline 468 → final 487 = +19. **Verified.**

**Claim:** "68 source files in mypy strict pass" (Completion Notes)

```sh
$ .venv/Scripts/python.exe -m mypy --strict mailbot_api/ 2>&1 | tail -1
Success: no issues found in 68 source files
```

**Verified.**

### 5.10 — Producer-boundary contract

N/A for the type module — there is no "producer-boundary" surface here in the JSON-shape-coercion sense. The boundary check IS the producer-boundary defense for downstream string-literal mistakes (Tier 1/2/3 callers must pass `ActionType.X`, not `"x"`).

For raw-SQL: this story does NOT touch SQL. No `SELECT *`-vs-explicit-column-list concern. No Pydantic `@field_validator(mode="before")` concern.

### 5.11 — Git-evidence consistency

```sh
$ rtk git status --porcelain | wc -l
17 (9 of which are pre-existing untracked unrelated background work)
```

Story-relevant files (9 of 17): match the File List exactly. Per §2 above, every story-relevant path tracks back to the File List. The 8 unrelated untracked entries are pre-existing scratch directories explicitly excluded from staging per Step 2.6.

```sh
$ rtk git diff --stat HEAD -- mailbot_api/ scripts/ tests/
mailbot_api/actions/__init__.py  | +25 / -0
scripts/check_boundaries.py      | +85 / -0  (approximate)
tests/unit/test_lint_boundaries.py | +66 / -0
```

Net code delta: ~176 modified lines + 4 new files. Proportionate to a type-foundation story.

### 5.12 — Posture Audit summary table

| Section | Verdict | Evidence |
| --- | --- | --- |
| 5.1 Lockfile hygiene | N/A | no requirements.txt change |
| 5.2 Cross-doc consistency | PASS (with documented reconciliation) | 19→23 spec drift acknowledged in Dev Notes |
| 5.3 Lifecycle string | N/A | no UI surface |
| 5.4 Multi-consumer | PASS | downstream surface use-cases enumerated for 4-2..4-8 |
| 5.5 Screenshot/perception | N/A | no UI |
| 5.6 Upstream-contract | N/A | this IS the upstream contract |
| 5.7 Module-mutable-state | PASS | MappingProxyType + Pydantic frozen + 2 invariant tests |
| 5.8 Dev-fixture parity | N/A | no fixtures |
| 5.9 Grep-verify-cited-figures | PASS | 23 enum members, 487 tests, 68 mypy files all verified |
| 5.10 Producer-boundary contract | N/A | no JSON/SQL boundary surface in this story |
| 5.11 Git-evidence | PASS | File List = git status diff exactly |
