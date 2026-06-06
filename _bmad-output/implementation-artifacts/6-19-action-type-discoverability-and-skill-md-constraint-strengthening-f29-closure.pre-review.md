---
name: 6-19 pre-review self-audit
description: Step 2.3.5 gate artifact for Story 6-19 (F29 closure)
type: pre-review
---

# Pre-Review Self-Audit — 6-19

**Generated:** 2026-06-06 by claude-opus-4-7 (autonomous-epic-run pickup)
**Story file:** `_bmad-output/implementation-artifacts/6-19-action-type-discoverability-and-skill-md-constraint-strengthening-f29-closure.md`
**Status at audit time:** review (post dev-story, pre code-review)

## 1. AC-vs-code drift scan

- **AC-1 (verb-shim error response carries `valid_action_types`):** **MATCH.** `ProposeActionError` extended at [mailbot_api/actions/propose.py:54-66](../../mailbot_api/actions/propose.py#L54-L66) with `valid_action_types: list[str] | None = None`. Verb shim at [mailbot_api/verbs/propose_action.py:27-60](../../mailbot_api/verbs/propose_action.py#L27-L60) computes module-level `_VALID_ACTION_TYPES: Final[list[str]] = sorted(at.value for at in ActionType)` (23 sorted snake_case values), populates `valid_action_types=_VALID_ACTION_TYPES` AND embeds full list in error message on INVALID_ACTION_TYPE only. Other error paths (EMAIL_NOT_FOUND, etc.) flow through `_propose_action_impl` unchanged — field defaults to None per AC-1 §4.
- **AC-2 (MCP resource `mailbot://action-types`):** **MATCH.** Helper `_build_action_types_resource_body()` at [mailbot_api/mcp_server.py:911-948](../../mailbot_api/mcp_server.py#L911-L948) builds JSON body with sorted-by-`value` entries, each carrying the 5 required fields (`value`, `tier`, `requires_sensitivity_token`, `is_send_family`, `is_email_less`). `_ACTION_TYPE_SYNONYMS_REJECTED` anti-anchor list at line 905-908. Resource registered via `server.add_resource(TextResource(uri=AnyUrl("mailbot://action-types"), ...))` in `build_mcp_server` after tool registration loop.
- **AC-3 (SKILL.md amendment):** **MATCH.** Added `#### Canonical action_type values` H4 subsection inside `### propose_action` at [hermes-config/skills/mailbot/SKILL.md:106-127](../../hermes-config/skills/mailbot/SKILL.md#L106-L127). Covers literal lowercase snake_case requirement + 3-row user-intent → canonical-value table (send/delete/archive) + pointer to `read_resource("mailbot://action-types")`. Existing content unchanged.
- **AC-4 (regression tests):** **MATCH.** 5 unit tests + 7 parametrized synonym tests in [tests/unit/verbs/test_propose_action_invalid_action_type_recovery.py](../../tests/unit/verbs/test_propose_action_invalid_action_type_recovery.py) (11 unit assertions total). 4 integration tests in [tests/integration/test_mcp_server_action_types_resource.py](../../tests/integration/test_mcp_server_action_types_resource.py). All 15 green on first run after the test 4 EMAIL_NOT_FOUND fixture-correction (Tier-3 `delete` needed to surface change_marker-capture path).
- **AC-5 (live walk re-test deferred):** **MATCH.** Explicitly deferred to Story 6-6.5 re-walk per AC text. This story does NOT execute the live walk; documented in Dev Notes + Completion Notes.
- **AC-6 (MANDATORY-CR):** **MATCH (verdict-only).** §5.12 of this audit produces `MANDATORY-CR` verdict (2 criteria fire: cross-story load-bearing seam + external transport / contract surface). CR runs at Step 2.4 of orchestrator.

**Net drift:** zero. No AC was reframed, narrowed, or punted to a follow-up.

## 2. File-List-vs-git diff check

| Path | Status | Verdict |
|---|---|---|
| `mailbot_api/actions/propose.py` | ` M` (modified) | **TRACKED** |
| `mailbot_api/verbs/propose_action.py` | ` M` | **TRACKED** |
| `mailbot_api/mcp_server.py` | ` M` | **TRACKED** |
| `hermes-config/skills/mailbot/SKILL.md` | `MM` (modified in both staged + unstaged — Story 6-20 staged the SOUL/AGENTS/SKILL.md AGENTS edits; this story added more) | **TRACKED** |
| `_bmad-output/implementation-artifacts/epic-6-run-flags.md` | `MM` (similarly chained) | **TRACKED** |
| `_bmad-output/implementation-artifacts/sprint-status.yaml` | `MM` (similarly chained) | **TRACKED** |
| `_bmad-output/implementation-artifacts/6-19-action-type-discoverability-and-skill-md-constraint-strengthening-f29-closure.md` | `??` (new) | **UNTRACKED — expected (new file)** |
| `_bmad-output/implementation-artifacts/6-19-action-type-discoverability-and-skill-md-constraint-strengthening-f29-closure.pre-review.md` | `??` (new, will exist after this write) | **UNTRACKED — expected (new file)** |
| `tests/unit/verbs/test_propose_action_invalid_action_type_recovery.py` | `??` (new) | **UNTRACKED — expected (new file)** |
| `tests/integration/test_mcp_server_action_types_resource.py` | `??` (new) | **UNTRACKED — expected (new file)** |

**Step 2.6 selective staging** will pick up all 10 entries explicitly. No surprise strays.

## 3. Adversarial self-review

- **[MEDIUM]** [tests/unit/verbs/test_propose_action_invalid_action_type_recovery.py:106-125](../../tests/unit/verbs/test_propose_action_invalid_action_type_recovery.py#L106-L125) — AC-4.4 uses `delete` (Tier-3) to surface `EMAIL_NOT_FOUND`. **Concern:** the test's correctness depends on the Story 4-2 / Story 4-1 invariant that Tier-1/Tier-2 propose paths don't call `_capture_change_marker`. If a future story refactors that (e.g., adds change-marker capture to Tier-2), the test would start hitting INVALID_PAYLOAD or similar instead. **Mitigation considered:** add an inline comment explaining the dependency (DONE — already commented). Acceptable — pinning a Tier-1/Tier-2 test on EMAIL_NOT_FOUND would be MORE brittle.
- **[LOW]** [mailbot_api/mcp_server.py:905-908](../../mailbot_api/mcp_server.py#L905-L908) — `_ACTION_TYPE_SYNONYMS_REJECTED` is a hand-curated list (9 entries). **Concern:** can drift from real-world hallucination patterns over time. Could be auto-populated by examining `router_calls` audit rows where `INVALID_ACTION_TYPE` fired. **Verdict:** out of scope; hand-curated list is sufficient for F29's specific failure mode + 3-4 obvious variants. Future story may auto-expand if hallucination pattern shifts.
- **[LOW]** [mailbot_api/verbs/propose_action.py:30](../../mailbot_api/verbs/propose_action.py#L30) — `_VALID_ACTION_TYPES: Final[list[str]] = sorted(at.value for at in ActionType)` is a mutable list. `Final` annotates "name binding immutable", not "object immutable". A caller could `_VALID_ACTION_TYPES.append("HACK")` to mutate it. **Mitigation considered:** use `Final[tuple[str, ...]]` instead. **Verdict:** ESCALATE TO REVIEWER. The error model returns this same list to the caller; if a malicious caller mutates it, subsequent error responses carry the mutation. tuple would be defense-in-depth.
- **[LOW]** [mailbot_api/mcp_server.py:1042-1056](../../mailbot_api/mcp_server.py#L1042-L1056) — Resource description string is 144 chars on a single line. MCP `Resource.description` has no documented max length, but very long descriptions could clutter the agent's `list_resources` output. **Verdict:** acceptable; the description's purpose is to be self-documenting in agent-facing tooling.
- **[LOW]** AC-2 says the resource JSON has top-level keys `action_types`, `synonyms_rejected`, `constraint`. Test 7 asserts `set(body.keys()) >= {...}` (subset, not equality). **Concern:** future additive fields to the resource body would pass the test silently. **Mitigation:** intentional — additive schema evolution is the stable-contract default; making the test STRICT-equal would lock in v1 and reject any future field. Documented in AC-7 reviewer focus (c).

5 self-caught issues. 1 ESCALATE-TO-REVIEWER (Final[list] vs Final[tuple]).

## 4. Self-caught issues remediated this audit

- **[MEDIUM] test 4 Tier-3 dependency:** ACCEPT WITH RATIONALE. Inline comment already explains; alternative pinning approaches are more brittle.
- **[LOW] synonyms_rejected hand-curation:** ACCEPT WITH RATIONALE. Out of scope; sufficient for F29.
- **[LOW] Final[list] vs Final[tuple]:** ESCALATE TO REVIEWER. Defense-in-depth question; reviewer call.
- **[LOW] Resource description length:** ACCEPT. Self-documenting purpose.
- **[LOW] Test 7 subset semantics:** ACCEPT WITH RATIONALE. Intentional for additive schema evolution.

## 5. Posture Audit

### 5.1 Lockfile hygiene
**N/A — no dependency changes.** `requirements.txt` unmodified per `git status --porcelain`.

### 5.2 Cross-doc pair verification
- SKILL.md propose_action ↔ verb-shim contract: updated together (Task 4 ↔ Task 2).
- epic-6-run-flags.md F29 ↔ Story 6-19 implementation: updated together (Task 7 ↔ Tasks 1-6).
- AC-2 MCP resource JSON shape ↔ AC-4.7 test: schema constants checked symmetrically.

### 5.2.1 Schema-touching schema-doc verification
**N/A — no schema changes.** No new migration file in `git status`. `ProposeActionError` field addition is Pydantic-only, not SQL.

### 5.3 Lifecycle string-uniqueness check
- **`valid_action_types`** new field name — `Grep "valid_action_types" mailbot_api/` shows 7 hits all in propose.py/propose_action.py (the new code) + tests; no collision with existing field names. ✓
- **`mailbot://action-types`** URI string — first MCP resource in the project. `Grep "mailbot://" mailbot_api/` shows hits only in the new mcp_server.py block. No collision. ✓
- **`INVALID_ACTION_TYPE`** error code — pre-existing ErrorCode literal; no change in semantics, only payload extension.
- **`action-types`** resource name — first resource; no collision.

### 5.4 Multi-consumer impact scan
Production consumers of `ProposeActionError`:
- **`mailbot_api/verbs/propose_action.py`** — uses code + message (modified to also use valid_action_types) ✓
- **`mailbot_api/actions/propose.py`** — _capture_change_marker, _validate_payload, etc. raise ProposeActionError instances with code + message (unchanged; default None for new field) ✓
- **`tests/unit/actions/test_propose.py` etc.** — existing assertion patterns use code + message; new field defaults None on those paths so existing tests don't need changes ✓

Production consumers of `build_mcp_server`:
- **`mailbot_api/main.py`** — FastAPI lifespan binds the server; resource is added during build. No call-site changes needed.
- **22 tool wrappers** — unchanged.
- **Tests:** 2 existing MCP server test files (`test_mcp_server.py`, `test_mcp_server_extended_tools.py`) — neither asserts "no resources registered", so adding one resource doesn't break them. ✓

### 5.5 Screenshot-based perception check
**N/A — no UI changes.** `<frontend-src>` is N/A per PORTING.md.

### 5.6 Upstream-contract spec coverage
- Story 4-1 ActionType enum (23 members): preserved unchanged. ✓
- Story 4-1 ACTION_PROPERTIES + EMAIL_LESS_ACTIONS: read-only consumption in the resource body builder. ✓
- Story 4-2 propose_action verb-boundary tier-promotion guard: unchanged. ✓
- Story 4-2 `ProposeActionError` model: backwards-compatible extension (new optional field with default None). ✓
- Story 5-2 MCP server build pattern: extended (resource added after tool loop) without changing existing patterns. ✓
- Story 5-5 Hermes-config SKILL.md propose_action section: H4 subsection ADDED; existing H3 + paragraphs unchanged. ✓

### 5.7 Module-level mutable container check
- **`_VALID_ACTION_TYPES: Final[list[str]]`** at [mailbot_api/verbs/propose_action.py:30](../../mailbot_api/verbs/propose_action.py#L30) — see §3 LOW concern. Mutable list at module level; Final annotates name-binding only. **Note:** reviewer escalation candidate for tuple defense-in-depth.
- **`_ACTION_TYPE_SYNONYMS_REJECTED: Final[list[str]]`** at [mailbot_api/mcp_server.py:905](../../mailbot_api/mcp_server.py#L905) — same shape; same concern; same disposition.

### 5.8 Dev-fixture seed-vs-production-shape parity
The new unit test fixture `_db_path` runs `apply_pending_migrations(db_path)` — same as Story 4-7 / Story 6-20 test patterns. Production seed shape (`emails` table columns) matches `_seed_email` helper. ✓

### 5.9 grep-verify-cited-figures
- **"23 ActionType members"** — `len(list(ActionType))` = 23. ✓ (verified via test 4.2: `assert len(result.error.valid_action_types) == 23`)
- **"1126 passed + 2 skipped + 3 deselected"** — verified via full pytest run output: "1126 passed, 2 skipped, 3 deselected, 1 warning in 218.34s". ✓
- **"+15 net from 1111 baseline"** — Story 6-20 closed at 1111; 1111 + 15 = 1126. ✓ Note: AC-4 spec text said "+9 net" but actual count is 15 because pytest counts parametrized variants individually (5 base unit + 7 parametrized + 4 integration = 16 collected; minus 1 since 5 base includes one parametrized variant — actual 11 unit + 4 integration = 15 net). The spec's "+9 net" was an undercount; the actual gate evidence is +15.
- **"mypy strict clean (123 files)"** — verified. ✓

### 5.10 Producer-boundary contract enforcement
- **Verb-shim is the right producer-boundary** for valid_action_types — the FIRST point where the agent's input string is validated. Polluting `_propose_action_impl` would be semantically wrong (Section §"Why the verb-shim path, NOT the actions/propose.py path" in story Dev Notes covers this).
- **MCP resource registration** is the right boundary for the discoverability hint — sits alongside the tool registration loop in `build_mcp_server`, not embedded in any verb.
- **Resource body construction** is a pure function (`_build_action_types_resource_body()`) — no DB I/O, idempotent, deterministic.

### 5.11 Git-evidence consistency
- **5.11.a File-List-vs-working-tree:** verified in §2. All 10 entries map to expected status (` M`, `MM`, or `??` for new files). Zero strays.
- **5.11.b Test-to-code production ratio:** Story 6-19 ships 15 new tests + ~140 production LOC (verb shim extension, MCP resource builder + registration, ProposeActionError field). Ratio ≈ 1 test per 9-10 LOC — within the project's healthy norm.
- **5.11.c No-later-commits-under-attribution:** verified — no Story 6-19 commits yet (story stages but doesn't commit per autonomous-epic-run contract).

### 5.12 CR-cadence-mandatory surface classification

**Verdict: `MANDATORY-CR`.**

Two §5.12 criteria fire:

1. **External transport / contract surface (criterion 1).** The MCP resource at `mailbot://action-types` is a NEW external Hermes-facing contract. Once shipped, the resource URI + JSON schema become a stable contract with Hermes-side code. Schema drift would break agents. The `valid_action_types` field on `ProposeActionError` is similarly external (returned to the agent across the MCP boundary).
2. **Cross-story load-bearing seam (criterion 6).** Touches Stories 4-1 (ActionType enum + ACTION_PROPERTIES + EMAIL_LESS_ACTIONS + is_send_family), 4-2 (propose_action verb + ProposeActionError model), 5-2 (MCP server tool registration pattern; resource registration extends it), 5-5 (Hermes-config SKILL.md propose_action flow). Four prior stories' invariants must continue holding.

**Reviewer focus areas (pre-spec'd in AC-6 of the story file):**

- (a) `_VALID_ACTION_TYPES` module-level constant — see §3 LOW concern about Final[list] vs Final[tuple]
- (b) `ProposeActionError.valid_action_types` default None preserves existing call sites
- (c) MCP resource JSON shape is additive-only / extensible
- (d) `synonyms_rejected` is a hint not a gate
- (e) Verb-shim is the ONLY populator; actions/propose.py paths are NOT polluted

## Summary table

| Section | Status |
|---|---|
| 1. AC-vs-code drift | ✅ MATCH (all 6 ACs) |
| 2. File-List-vs-git | ✅ Clean (10/10 entries accounted for) |
| 3. Adversarial self-review | ✅ 5 issues caught |
| 4. Issues remediated | ✅ 4 ACCEPT, 1 ESCALATE-TO-REVIEWER |
| 5.1 Lockfile | N/A — no dep changes |
| 5.2 Cross-doc | ✅ 3 pairs verified |
| 5.2.1 Schema-doc | N/A — no schema changes |
| 5.3 Lifecycle strings | ✅ No collisions (new field, new URI, new resource name all unique) |
| 5.4 Multi-consumer | ✅ All consumers backwards-compatible |
| 5.5 Screenshot perception | N/A — no graphical UI |
| 5.6 Upstream-contract | ✅ Stories 4-1 / 4-2 / 5-2 / 5-5 preserved |
| 5.7 Module-mutable state | ⚠️ 2 Final[list] candidates for tuple-hardening (reviewer escalation) |
| 5.8 Fixture-vs-production parity | ✅ Match |
| 5.9 grep-verify-cited-figures | ✅ All figures verified |
| 5.10 Producer-boundary | ✅ Verb-shim + MCP server build are correct architectural seams |
| 5.11 Git-evidence | ✅ Consistent |
| 5.12 **Cadence verdict: `MANDATORY-CR`** | ✅ 2 criteria fire |
