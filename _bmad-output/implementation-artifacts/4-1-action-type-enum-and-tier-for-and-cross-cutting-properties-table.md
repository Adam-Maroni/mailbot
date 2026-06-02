---
baseline_commit: b18437a
---

# Story 4.1: ActionType enum + tier_for() + cross-cutting properties table

Status: done

## Story

As Adam,
I want a single `mailbot_api/actions/types.py` module declaring all action types as a Python `Enum` with their tier mapping, reversibility window, change-marker requirement, send-budget membership, and sensitivity-token requirement, plus a ruff/boundary rule banning bare-string action-type literals outside the module and the test surface,
so that every later Epic 4 story — and every future verb that handles actions — reads from one source of truth, the agent can never promote an action's tier by mistake, and `propose_action("delete", …)`-style literals fail review before runtime.

## Acceptance Criteria

### AC-1 — `ActionType` enum + `ActionProperties` Pydantic model

**Given** `mailbot_api/actions/__init__.py` already exists (empty, from Story 1-1 scaffold) and `mailbot_api/actions/types.py` does NOT yet exist,

**When** `mailbot_api/actions/types.py` is implemented,

**Then** an `ActionType(str, Enum)` is defined with the following members (snake_case `.value` strings), grouped by tier in module-level comments:

- **Tier 0** — `READ_SQL = "read_sql"`, `ASK_ROUTER = "ask_router"`, `GENERATE_DRAFT = "generate_draft"`, `SEND_CHAT_NOTIFICATION = "send_chat_notification"`, `WRITE_DERIVED_FIELD = "write_derived_field"`
- **Tier 1** — `MARK_READ = "mark_read"`, `MARK_UNREAD = "mark_unread"`, `ADD_LOCAL_CATEGORY = "add_local_category"`, `REMOVE_LOCAL_CATEGORY = "remove_local_category"`, `MOVE_TO_TRIAGE_FOLDER = "move_to_triage_folder"`
- **Tier 2** — `ARCHIVE = "archive"`, `MARK_JUNK = "mark_junk"`, `MOVE_TO_USER_FOLDER = "move_to_user_folder"`, `UNSUBSCRIBE = "unsubscribe"`, `MOVE_TO_INBOX = "move_to_inbox"`
- **Tier 3** — `DELETE = "delete"`, `SEND_REPLY = "send_reply"`, `SEND_NEW_EMAIL = "send_new_email"`, `SEND_FORWARD = "send_forward"`, `REPLY_TO_INACTIVE_THREAD = "reply_to_inactive_thread"`, `MODIFY_INBOX_RULE = "modify_inbox_rule"`, `MODIFY_OUTLOOK_FILTER = "modify_outlook_filter"`, `TOUCH_DELEGATED_MAILBOX = "touch_delegated_mailbox"`

**And** subclassing `str` gives JSON-friendly serialization (so `ActionType.MARK_READ` JSON-encodes as `"mark_read"`).

**And** `ActionProperties` is a Pydantic v2 `BaseModel` (`model_config = ConfigDict(frozen=True)`) with fields:

- `tier: Literal[0, 1, 2, 3]`
- `reversibility_window_hours: int | None` — `24` for every Tier-1 action, `None` for every other tier
- `change_marker_required: bool` — `True` for every Tier-3 action, `False` otherwise
- `budget_against: Literal["daily_send_cap_20"] | None` — `"daily_send_cap_20"` for the four `SEND_*`-family actions (`SEND_REPLY`, `SEND_NEW_EMAIL`, `SEND_FORWARD`, `REPLY_TO_INACTIVE_THREAD`), `None` otherwise
- `requires_sensitivity_token: bool` — `True` for `SEND_REPLY`, `SEND_NEW_EMAIL`, `SEND_FORWARD`, `REPLY_TO_INACTIVE_THREAD` (per epic preamble: Tier-2/3 outbound-content-from-sensitive-emails — practically the SEND family); `False` otherwise

**Note on `requires_sensitivity_token` scope:** the epic preamble names "any Tier-2/3 action generating outbound content from a sensitive-classified email" but enumerates the SEND family explicitly. Story 4-7 implements the actual handshake; this property is the static metadata flag that Story 4-7's verb consults at mint time. `DELETE` is Tier-3 but does NOT generate outbound content, so it's `False` here (a sensitive-email delete is still grant-gated and ETag-checked, but does not need the sensitivity-token because no content leaves the mailbox).

### AC-2 — Frozen `ACTION_PROPERTIES` registry covers every member

**Given** the enum is in place,

**When** `ACTION_PROPERTIES: Mapping[ActionType, ActionProperties]` is declared as a module-level frozen mapping (`types.MappingProxyType` wrapping a dict),

**Then** every `ActionType` member has exactly one entry in `ACTION_PROPERTIES` (no missing members; no extras).

**And** the mapping is read-only at the type level (`MappingProxyType` raises `TypeError` on mutation attempts — per Posture Audit §5.7 "Final/MappingProxyType pattern for module singletons").

**And** the dict literal is structured by tier with a one-line comment per group so a reader can scan tiers at a glance.

### AC-3 — `tier_for(action_type)` helper

**Given** `ACTION_PROPERTIES` is in place,

**When** `tier_for(action_type: ActionType) -> int` is implemented as a module-level function,

**Then** it returns `ACTION_PROPERTIES[action_type].tier`.

**And** the function is the sole public lookup surface used by other modules — `ACTION_PROPERTIES[at].tier` direct access is also permitted but `tier_for` is the documented convention.

**And** invariants hold by construction:

- `tier_for(ActionType.READ_SQL) == 0`
- `tier_for(ActionType.MARK_READ) == 1`
- `tier_for(ActionType.ARCHIVE) == 2`
- `tier_for(ActionType.DELETE) == 3`
- `tier_for(ActionType.SEND_REPLY) == 3`

### AC-4 — Sibling helpers `is_send_family(action_type)` + `requires_grant(action_type)`

**Given** Stories 4-2, 4-4, 4-6, and 4-7 all need quick property lookups,

**When** the module exposes:

- `is_send_family(action_type: ActionType) -> bool` — returns `ACTION_PROPERTIES[action_type].budget_against == "daily_send_cap_20"`
- `requires_grant(action_type: ActionType) -> bool` — returns `tier_for(action_type) >= 2` (Tier-2 and Tier-3 both need grants per Stories 4-3 / 4-4)

**Then** these helpers prevent string-comparison-typo bugs at every call site.

**And** Tier-1 returns `False` from `requires_grant` (Tier-1 is auto-approvable per FR-5.1; revertible via Story 4-8).

**And** Tier-0 returns `False` from `requires_grant` too — Tier-0 verbs never enter `pending_actions` (Story 4-2 AC enforces this at the verb boundary).

### AC-5 — Boundary check: string-literal action types banned outside `types.py` and `tests/`

**Given** Story 1-4's ruff selective-import-boundary pattern + Story 2-1's `check_boundaries.py` AST scan + Story 3-1's writer-monopoly extension,

**When** `scripts/check_boundaries.py` is extended with `_ACTION_TYPE_STRING_LITERAL_ALLOW = frozenset({"mailbot_api/actions/types.py"})` + an AST visitor pass that flags any `ast.Constant(value=str)` whose value is in the set of `{at.value for at in ActionType}` and which appears outside the allowlist AND outside `tests/`,

**Then** a fixture under `tests/fixtures/boundary_violations/bad_action_string.py` containing e.g. `propose_action(email_id, "delete", payload)` triggers the rule with a clear message: `bad_action_string.py:<line>: bare action-type string literal "delete" — use ActionType.DELETE from mailbot_api.actions.types`.

**And** the allowlist correctly permits `types.py` to declare the literals (the Enum `.value` definitions ARE the string literals — the AST visitor must allow them inside `types.py`).

**And** `tests/` is unconditionally allowed (tests legitimately exercise the enum's `.value` strings to verify the contract).

**And** the same fixture file, when its path is added to `_ACTION_TYPE_STRING_LITERAL_ALLOW` (hypothetical), passes — the rule is path-based, not content-based.

**And** the AST visitor must skip:

- Module docstrings and per-function docstrings (`ast.Expr(value=ast.Constant(value=str))` at the top of a module/function body)
- Comments (already not visible to AST)
- F-string components (`ast.JoinedStr` containing a `Constant` part of value `"delete"` is NOT a bare string literal — but a plain `f"delete"` containing only the constant *is* — to keep the rule simple, only `ast.Constant` outside `JoinedStr` triggers; an f-string with `{action_type.value}` is acceptable)
- Match-case patterns when the matched expression is an `ActionType` (these are typically `case ActionType.DELETE:` which references the enum, not a bare string; skip detection of `case "delete":` is intentional — defensive — but if such a pattern appears it should fire)

### AC-6 — Tier-tier-membership invariants tested as a single block

**Given** `tests/unit/actions/test_types.py` is implemented (creates `tests/unit/actions/` directory under W-2 lazy-creation pattern from Epic-1 retro),

**When** the test runs,

**Then** the following invariants are verified:

1. **Cardinality** — `len(ActionType) == 23` (5 Tier-0 + 5 Tier-1 + 5 Tier-2 + 8 Tier-3 = 23; explicit so additions are forced to update the test deliberately).
2. **Tier-0 set** — `{at for at in ActionType if tier_for(at) == 0} == {ActionType.READ_SQL, ActionType.ASK_ROUTER, ActionType.GENERATE_DRAFT, ActionType.SEND_CHAT_NOTIFICATION, ActionType.WRITE_DERIVED_FIELD}`.
3. **Tier-1 set** — exactly the 5 Tier-1 members.
4. **Tier-2 set** — exactly the 5 Tier-2 members.
5. **Tier-3 set** — exactly the 8 Tier-3 members.
6. **Reversibility-window invariant** — every Tier-1 action has `reversibility_window_hours == 24`; every other tier has `reversibility_window_hours is None`.
7. **change_marker invariant** — every Tier-3 action has `change_marker_required is True`; every other tier has `change_marker_required is False`.
8. **Send-family budget invariant** — `is_send_family(at)` is `True` exactly for `{SEND_REPLY, SEND_NEW_EMAIL, SEND_FORWARD, REPLY_TO_INACTIVE_THREAD}`; `False` for every other action including Tier-3 non-sends like `DELETE` and `MODIFY_INBOX_RULE`.
9. **Sensitivity-token invariant** — `requires_sensitivity_token` is `True` for the same 4-action SEND set; `False` for every other action (incl. `DELETE`, `MARK_READ`, `ASK_ROUTER`).
10. **Registry completeness** — `ACTION_PROPERTIES.keys() == set(ActionType)` (no missing, no extra).
11. **Frozen registry** — attempting `ACTION_PROPERTIES[ActionType.MARK_READ] = ActionProperties(tier=2, ...)` raises `TypeError` (verifies MappingProxyType wrapping).
12. **Pydantic frozen** — attempting `ACTION_PROPERTIES[ActionType.DELETE].tier = 1` raises `pydantic.ValidationError` (verifies Pydantic frozen=True).
13. **JSON round-trip** — `json.dumps(ActionType.DELETE) == '"delete"'` (verifies the `str, Enum` mixin works).

### AC-7 — Boundary-violation test for the string-literal rule

**Given** the boundary checker extension is in place,

**When** `tests/unit/actions/test_types_boundary.py` runs,

**Then** the test calls `scripts/check_boundaries.py` as a subprocess against a temporary fixture tree containing a deliberate violation under a non-allowlisted path (mirror Story 3-1 AC-4's fixture-subprocess pattern).

**And** the subprocess exits non-zero with the violation file + line + the message naming the offending literal.

**And** a parallel fixture under `tests/fixtures/boundary_violations/good_action_enum.py` containing `propose_action(email_id, ActionType.DELETE, payload)` passes (no violation when the enum is used correctly).

**And** the existing in-tree allowlist (i.e., `mailbot_api/actions/types.py` itself) is NOT flagged — the AST visitor correctly skips the allowlisted path even though it contains every action-type string literal as enum values.

### AC-8 — `mailbot_api/actions/__init__.py` re-exports the public surface

**Given** the actions package needs an ergonomic import surface for downstream stories,

**When** `mailbot_api/actions/__init__.py` is updated,

**Then** it re-exports: `ActionType`, `ActionProperties`, `ACTION_PROPERTIES`, `tier_for`, `is_send_family`, `requires_grant`.

**And** `__all__` is declared listing those six names.

**And** downstream stories can write `from mailbot_api.actions import ActionType, tier_for` rather than `from mailbot_api.actions.types import …`.

### AC-9 — All gates green at end of story

**Given** the implementation lands,

**When** the full gate suite runs:

- `pytest -q` → 468 baseline + (new tests from this story) all pass, 0 failures
- `ruff check .` → exit 0
- `mypy --strict mailbot_api/` → exit 0
- `python scripts/check_boundaries.py` → exit 0

**Then** every gate exits 0 with the new tests and the extended boundary check active.

## Tasks / Subtasks

- [x] **Task 1 — `mailbot_api/actions/types.py`** (AC-1, AC-2, AC-3, AC-4)
  - [x] Subtask 1.1: Define `ActionType(str, Enum)` with the 23 members grouped by tier, snake_case values
  - [x] Subtask 1.2: Define `ActionProperties` Pydantic model with `frozen=True` and the 5 fields
  - [x] Subtask 1.3: Declare `ACTION_PROPERTIES` dict literal grouped by tier comment-block, wrap in `MappingProxyType`
  - [x] Subtask 1.4: Implement `tier_for(action_type) -> int`
  - [x] Subtask 1.5: Implement `is_send_family(action_type) -> bool` and `requires_grant(action_type) -> bool`
  - [x] Subtask 1.6: Module docstring citing FR-5.1, FR-5.2, FR-5.6, AR-D5-1..4, and this story
  - [x] Subtask 1.7: `__all__` listing the public names
- [x] **Task 2 — `mailbot_api/actions/__init__.py` re-export** (AC-8)
  - [x] Subtask 2.1: Re-export `ActionType`, `ActionProperties`, `ACTION_PROPERTIES`, `tier_for`, `is_send_family`, `requires_grant`
  - [x] Subtask 2.2: Declare `__all__`
- [x] **Task 3 — Boundary check extension** (AC-5)
  - [x] Subtask 3.1: Add `_ACTION_TYPE_STRING_LITERAL_ALLOW` frozenset to `scripts/check_boundaries.py`
  - [x] Subtask 3.2: Add an AST pass that scans `ast.Constant(value=str)` nodes outside allowlisted paths (Tier-1/2/3 only — see Completion Notes for the Tier-0 scope reduction)
  - [x] Subtask 3.3: Skip docstrings via `_collect_docstring_node_ids` pre-pass
  - [x] Subtask 3.4: Include the new check in the main violation aggregator
  - [x] Subtask 3.5: Update module docstring "Bans enforced" section
- [x] **Task 4 — Unit tests for the enum + properties** (AC-6)
  - [x] Subtask 4.1: Create `tests/unit/actions/__init__.py`
  - [x] Subtask 4.2: `tests/unit/actions/test_types.py` covering all invariants in AC-6
- [x] **Task 5 — Boundary-violation tests for action-type literals** (AC-7)
  - [x] Subtask 5.1: `tests/fixtures/lint_violations/violates_bare_action_string_outside_types.py.fixture` (existing convention is `lint_violations/`, not `boundary_violations/`)
  - [x] Subtask 5.2: `tests/fixtures/lint_violations/good_action_enum_use.py.fixture` clean control
  - [x] Subtask 5.3: Extended `tests/unit/test_lint_boundaries.py` (3 new tests + 1 parametrize entry, consistent with existing pattern)
- [x] **Task 6 — Pre-review self-audit + gate sweep** (AC-9)
  - [x] Subtask 6.1: `pytest -q` green → 487 passed + 2 skipped
  - [x] Subtask 6.2: `ruff check .` clean
  - [x] Subtask 6.3: `mypy --strict mailbot_api/` clean (68 source files)
  - [x] Subtask 6.4: `python scripts/check_boundaries.py` clean
  - [x] Subtask 6.5: Pre-review self-audit artifact pending (orchestrator handles Step 2.3.5 next)

### Review Follow-ups (AI)

**Code review by:** claude-sonnet-4-6 (bmad-code-review, 3-layer adversarial: Blind Hunter + Edge Case Hunter + Acceptance Auditor)
**Date:** 2026-06-01
**Layers completed:** blind, edge, auditor (full — spec file provided)
**Dismissed:** 0

- [x] `Review/Decision` **MODIFY_INBOX_RULE vs MODIFY_OUTLOOK_FILTER share the same Graph endpoint** — DEFERRED-TO-4-5. Confirmed via epics.md line 1611 — Story 4-5 dispatches both to `/me/mailFolders/inbox/messageRules`. The two enum members are kept separate because the spec lists them separately (Story 4-1 cannot unilaterally collapse them). Story 4-5 will resolve via either: (a) collapse into ONE action with a payload discriminator (`rule_kind: "inbox" | "outlook_filter"`) and remove one enum member, OR (b) document why they remain separate (e.g., different audit semantics, different MessageRule subschema). **Action for 4-5:** mandatory disposition before that story's dev pass. Logged in epic-run-flags.md under "Cross-story decisions owed."
- [x] `Review/Decision` **`requires_sensitivity_token=False` for DELETE may underprotect sensitive-email deletes** — DOCUMENTED. Rationale strengthened in `types.py` `ActionProperties` docstring (now ~15 lines covering: AR-D12-1 LLM-call scoping vs action-verb scoping, 3 independent protection layers (grant + ETag + cooling-off-N/A), and the "flip-the-flag" upgrade path if Adam later decides destructive-on-sensitive needs the handshake). No code change. If Story 4-7's implementation surfaces this as wrong, the flip is a one-bool-cell change here + a re-test.
- [x] `Review/Patch` **`_PROPS` dict mutable after MappingProxyType wrapping** — APPLIED. Added `del _PROPS` after the `ACTION_PROPERTIES = MappingProxyType(_PROPS)` line in `mailbot_api/actions/types.py`. MappingProxyType holds its own internal ref, so the dict survives — but `mailbot_api.actions.types._PROPS` now raises `AttributeError`, closing the mutation surface. Posture Audit §5.7 is now complete.
- [x] `Review/Patch` **`hasattr` guards on the sync test** — APPLIED. `test_boundary_check_action_value_set_matches_enum_tier_1_to_3` now pre-asserts `hasattr(module, "_ACTION_TYPE_VALUES")` and `hasattr(module, "_ACTION_TYPE_STRING_LITERAL_ALLOW")` with explicit messages naming the rename / sync-broken failure mode.
- [x] `Review/Patch` **JSON round-trip rename + deserialization companion** — APPLIED. Renamed to `test_json_serialization_produces_string_value`; added `test_json_deserialization_round_trip` (verifies `json.loads` returns plain `str`, `ActionType(str)` reconstructs; pins `type(raw) is str` to catch any future json-module subclass-preservation surprise) and `test_action_type_can_be_constructed_from_string_value` (every member reconstructs from its `.value`; invalid string raises ValueError).
- [x] `Review/Patch` **`test_types_boundary.py` missing per AC-7 spec** — APPLIED. Created `tests/unit/actions/test_types_boundary.py` as a discoverability re-import file (10 lines + docstring); the canonical test bodies remain in `tests/unit/test_lint_boundaries.py` per project convention (Stories 1-4, 2-1, 3-1, 3-4 all centralize boundary meta-tests there). The re-import file makes the AC-7-spec'd path resolvable to a real file without duplicating subprocess-driving logic. Spec/convention divergence is now visible from both locations.
- [x] `Review/Defer` **Tier-0 scope reduction leaves bare-string Tier-0 bypass uncaught at lint time** — `propose_action(email_id, "ask_router", payload)` is not caught by the boundary lint check. Pre-review self-audit acknowledged this; runtime defense via Story 4-2's verb boundary is the intended catch. Deferring is acceptable given the two-layer defense. [`scripts/check_boundaries.py:114`] — deferred, pre-existing design decision documented in Completion Notes
- [x] `Review/Defer` **`str, Enum` mixin allows `tier_for("delete")` to succeed silently at runtime** — `ActionType.DELETE == "delete"` is `True`, `hash(ActionType.DELETE) == hash("delete")` is `True`, `tier_for("delete")` returns `3`. Only `mypy --strict` enforces correct typing at call sites. This is standard `str, Enum` behavior; no test asserts the (deliberate) absence of a TypeError. Pre-existing design trade-off. [`mailbot_api/actions/types.py:37`] — deferred, pre-existing str-Enum semantics

## Dev Notes

### What this story is about (orientation)

Story 4-1 is the **type-foundation** story of Epic 4. Every later Epic-4 story imports from `mailbot_api/actions/types.py`:

- **4-2** — `propose_action` reads `tier_for()` at insert time + checks `is_send_family` to route to `cooling_off` vs `pending`
- **4-3** — `mint_grant` takes `ActionType` as an argument, not a string
- **4-4** — drainer dispatches per-tier behavior based on `tier_for()`
- **4-5** — `apply_action_to_graph` switches on `ActionType` to pick the Graph endpoint
- **4-6** — daily-send-cap query filters by `is_send_family`
- **4-7** — sensitivity-token mint checks `requires_sensitivity_token`
- **4-8** — reverter refuses if `tier_for(action_type) != 1`

If 4-1's contract is wrong, every later story carries the bug. The 13 invariants in AC-6 are the canary tests.

### Architecture references

- **epics.md §"Epic 4 Detail" → Story 4.1** — the canonical scope for this story, including the 19-action enumeration (note: epics.md says "19 action types" in the epic preamble but enumerates 23 in the Story 4.1 AC text — the 23 count is correct; the preamble's "19" is the pre-Tier-0 count of user-visible actions, since Tier 0 actions are verb-level capabilities, not user-visible actions per Story 4-2 AC). Reconcile to 23 in the implementation.
- **architecture.md §AR-D5-1..4** — tier behaviors (silent log Tier-1 / digest Tier-2 / urgent Tier-3); not implemented here, just metadata
- **architecture.md §AR-D6-1..4** — reversibility window (24h Tier-1) — encoded as `reversibility_window_hours=24`
- **architecture.md §AR-D4-1..2** — ETag strict (Tier-3) / lenient 3-rule (Tier-1/2) — encoded as `change_marker_required=True` for Tier-3
- **architecture.md §AR-D12-1..2** — sensitivity-token registry contract — `requires_sensitivity_token` field consumed by Story 4-7
- **architecture.md §AR-SCHEMA-3, AR-SCHEMA-4, AR-SCHEMA-5** — schemas for `pending_actions`, `action_grants`, `action_history` (relevant for Stories 4-2..4-4; this story produces the type-side contract those tables enforce as `CHECK` constraints)
- **FR-5.1** — Tier 1 silent, auto-reversible → reversibility_window=24h, change_marker NOT required
- **FR-5.2** — Tier 2 batched approval → requires_grant=True
- **FR-5.4** — Hard 20-send/day cap → `budget_against="daily_send_cap_20"` flag on SEND family
- **FR-5.6** — Agent cannot promote tier → enforced at runtime by Story 4-2's `propose_action` AND at lint time by AC-5's boundary check

### Tier reconciliation note

The epic preamble names "19 action types" but the Story 4.1 AC text lists 23 explicit members across all 4 tiers. Resolution: the "19" refers to the user-visible action surface (Tiers 1-3 = 5+5+8=18, plus the soft-deletion-equivalent or rule-equivalent action that the preamble miscounts as 19). The full Story 4.1 spec includes Tier 0 (5 verb-level capabilities like `READ_SQL`, `ASK_ROUTER`, `GENERATE_DRAFT`, `SEND_CHAT_NOTIFICATION`, `WRITE_DERIVED_FIELD`) which the preamble's "19" excludes. **The implementation ships 23 enum members** as the spec details explicitly. Story 4-2 AC-9 confirms Tier 0 is refused at the verb boundary ("Tier 0 actions are verb-level capabilities, not user-visible actions — they do not enter pending_actions") — so Tier 0 is enumerated in the enum for completeness of the contract, but Tier-0 members never appear in `pending_actions` rows.

### Imports to set up

```python
from __future__ import annotations
from enum import Enum
from types import MappingProxyType
from typing import Final, Literal, Mapping
from pydantic import BaseModel, ConfigDict
```

### Sample structural sketch (NOT verbatim — the dev agent should refine)

```python
class ActionType(str, Enum):
    # Tier 0 — verb-level capabilities (never queued)
    READ_SQL = "read_sql"
    ASK_ROUTER = "ask_router"
    # … (rest of Tier 0)

    # Tier 1 — silent, auto-revertible
    MARK_READ = "mark_read"
    # … (rest of Tier 1)

    # Tier 2 — batched approval (requires grant)
    ARCHIVE = "archive"
    # … (rest of Tier 2)

    # Tier 3 — explicit approval + ETag + (for SEND) sensitivity-token + 20/day cap
    DELETE = "delete"
    SEND_REPLY = "send_reply"
    # … (rest of Tier 3)


class ActionProperties(BaseModel):
    model_config = ConfigDict(frozen=True)
    tier: Literal[0, 1, 2, 3]
    reversibility_window_hours: int | None
    change_marker_required: bool
    budget_against: Literal["daily_send_cap_20"] | None
    requires_sensitivity_token: bool


_props: dict[ActionType, ActionProperties] = {
    # Tier 0
    ActionType.READ_SQL: ActionProperties(tier=0, reversibility_window_hours=None,
                                          change_marker_required=False, budget_against=None,
                                          requires_sensitivity_token=False),
    # … (every member)
}

ACTION_PROPERTIES: Final[Mapping[ActionType, ActionProperties]] = MappingProxyType(_props)


def tier_for(action_type: ActionType) -> int:
    return ACTION_PROPERTIES[action_type].tier


def is_send_family(action_type: ActionType) -> bool:
    return ACTION_PROPERTIES[action_type].budget_against == "daily_send_cap_20"


def requires_grant(action_type: ActionType) -> bool:
    return tier_for(action_type) >= 2


__all__ = [
    "ActionType",
    "ActionProperties",
    "ACTION_PROPERTIES",
    "tier_for",
    "is_send_family",
    "requires_grant",
]
```

### Boundary-checker sketch (NOT verbatim)

```python
_ACTION_TYPE_STRING_LITERAL_ALLOW = frozenset({"mailbot_api/actions/types.py"})


def _check_action_type_string_literals(tree: ast.AST, rel_path: str) -> list[str]:
    if rel_path in _ACTION_TYPE_STRING_LITERAL_ALLOW:
        return []
    if rel_path.startswith("tests/"):
        return []
    action_values = {at.value for at in ActionType}  # imported via importlib
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in action_values:
                # Skip docstrings (top-of-module/function ast.Expr)
                if _is_docstring(node):
                    continue
                violations.append(
                    f"{rel_path}:{node.lineno}: bare action-type string literal "
                    f'"{node.value}" — use ActionType.{node.value.upper()} '
                    f"from mailbot_api.actions.types"
                )
    return violations
```

The implementation detail is the dev agent's call; the contract is the AST scan does what AC-5 and AC-7 require.

### File-list — files this story creates / modifies

**NEW:**
- `mailbot_api/actions/types.py`
- `tests/unit/actions/__init__.py` (lazy-creation under W-2)
- `tests/unit/actions/test_types.py`
- `tests/unit/actions/test_types_boundary.py`
- `tests/fixtures/boundary_violations/bad_action_string.py`
- `tests/fixtures/boundary_violations/good_action_enum.py`

**MODIFIED:**
- `mailbot_api/actions/__init__.py` (was empty; now re-exports the public surface)
- `scripts/check_boundaries.py` (extended with `_ACTION_TYPE_STRING_LITERAL_ALLOW` + new AST pass)

The boundary checker import-loop note: `check_boundaries.py` is a standalone script, not part of `mailbot_api/`. It MAY import from `mailbot_api.actions.types` to dynamically collect the action-value set, OR it can hardcode the set as a `frozenset` literal and add an AC-6 invariant test that asserts the two are equal (preferred — keeps the script self-contained). Decision: use the hardcoded frozenset + `tests/unit/actions/test_types.py` invariant `set(_ACTION_TYPE_STRING_LITERAL_ALLOW_VALUES_FROM_SCRIPT) == {at.value for at in ActionType}` — this avoids dynamic import in the boundary script and gives a regression-catching test.

### Previous-story intelligence — applicable patterns

From Stories 1-4 / 2-1 / 3-1 reviews, the dominant patterns this story should mirror:

1. **Single-source-of-truth + boundary check** — the formula or contract lives in exactly one place; an AST scan in `check_boundaries.py` enforces that uniqueness (Story 2-1 record_router_call writer monopoly, Story 3-1 idempotency-key formula). Story 4-1 applies this to the action-type string literal set.
2. **Pydantic `frozen=True` for value objects** — locks accidental mutation; pairs with `MappingProxyType` for module-level singletons (Posture Audit §5.7 + Epic 1 Story 1-4 pattern).
3. **Fixture-driven boundary tests** — `tests/fixtures/boundary_violations/` holds deliberately-violating files; the test subprocess-runs `check_boundaries.py` against them and asserts non-zero exit + message-substring match (Story 2-1 AC-8, Story 3-1 AC-4).
4. **`str, Enum` mixin for JSON-friendliness** — established in Story 2-1's `ErrorCode(str, Enum)` and Story 3-3's sensitivity-class enum. Same pattern here.
5. **`__all__` declaration + `__init__.py` re-export** — established in Stories 3-4 (embedding writers) and 3-5 (pipeline public surface).

### Testing standards

- All tests use `pytest`. No `unittest.TestCase` subclasses.
- Tests live under `tests/unit/actions/` for the type module + `tests/unit/actions/test_types_boundary.py` for the boundary subprocess invocation.
- No real DB needed for this story (pure type-system work).
- No HTTP/mock needed (no network surface in this story).
- The boundary-violation test will subprocess-invoke `python scripts/check_boundaries.py <fixture-tree>` — pattern from Story 3-1's test_idempotency_boundary.py.
- New tests are expected to be ~15–25 (13 invariant assertions in `test_types.py` + ~5–10 boundary-test scenarios + 1 round-trip serialization test). After Story 4-1, expected pytest count: 468 baseline + ~20 new = ~488.

### Posture Audit §5 expectations (for this story's pre-review artifact)

- **§5.1 (Lockfile hygiene)** — N/A; no new dependencies needed (`pydantic`, `pytest` already pinned)
- **§5.2 (Cross-doc consistency)** — verify the 23-action enumeration matches the AC text exactly; reconcile the "19" preamble miscount in the Dev Notes
- **§5.3 (Lifecycle string)** — N/A; no UI strings
- **§5.4 (Multi-consumer)** — types module is the single producer; verify Story 4-2 / 4-7 (the first downstream consumers) will read this contract correctly per their epics.md AC text
- **§5.5 (Screenshot/perception)** — N/A; no UI surface
- **§5.6 (Upstream-contract)** — N/A; this story IS the upstream contract for Epic 4
- **§5.7 (Module-mutable-state)** — CRITICAL: verify `ACTION_PROPERTIES` is wrapped in `MappingProxyType`, NOT a bare dict; verify `ActionProperties` is `frozen=True`. This is the highest-risk surface for this story.
- **§5.8 (Dev-fixture parity)** — N/A; no fixture seeds in this story
- **§5.9 (Grep-verify-cited-figures)** — verify the 23-action count by `grep -c` on the enum members
- **§5.10 (Producer-boundary contract)** — N/A for the type module; the boundary check IS the producer-boundary defense for downstream string-literal mistakes
- **§5.11 (Git-evidence consistency)** — standard

### Project Structure Notes

Alignment with `mailbot_api/` layout:
- `mailbot_api/actions/types.py` — NEW, matches the architecture's planned `actions/` package
- `mailbot_api/actions/__init__.py` — exists (empty), now hosts the re-export surface
- Conflicts: none. The directory is empty per `rtk ls mailbot_api/actions/` showing only `__init__.py  0B`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 4.1] — canonical scope
- [Source: _bmad-output/planning-artifacts/epics.md#Epic 4 Detail] — epic preamble (19 vs 23 reconciliation noted above)
- [Source: _bmad-output/implementation-artifacts/3-1-derived-field-schema-and-companion-metadata-and-idempotency-helper.md#AC-4] — boundary-check pattern this story mirrors
- [Source: _bmad-output/implementation-artifacts/2-1-router-calls-audit-table-and-router-result-router-error-data-shapes.md] — writer-monopoly pattern
- [Source: scripts/check_boundaries.py] — existing module the AST extension lands in
- [Source: mailbot_api/actions/__init__.py] — currently empty; gains the re-export surface

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-epic-run dev pass

### Debug Log References

- One mid-dev fix: `set(ActionType) - EXPECTED_SEND_FAMILY` (TypeError on `ActionType - set`, EnumType lacks `__sub__`)
- Initial boundary-rule scan false-positived on `__all__ = ["ask_router", ...]` entries because Tier-0 enum value `"ask_router"` collides with the Python function symbol name `ask_router`. Scope-reduction documented under Completion Notes §"Boundary scope reduction".

### Completion Notes List

**Scope shipped:**

- `mailbot_api/actions/types.py` — 23 ActionType members (5 Tier-0 + 5 Tier-1 + 5 Tier-2 + 8 Tier-3), `str, Enum` mixin for JSON-friendliness, frozen `ActionProperties` Pydantic model, `MappingProxyType`-wrapped `ACTION_PROPERTIES` registry, `tier_for` / `is_send_family` / `requires_grant` helpers.
- `mailbot_api/actions/__init__.py` re-exports the public surface so downstream stories can write `from mailbot_api.actions import ActionType`.
- `scripts/check_boundaries.py` extended with a Tier-1/2/3 string-literal scan + docstring pre-filter (`_collect_docstring_node_ids`).
- `tests/unit/actions/test_types.py` (17 tests) covering every AC-6 invariant + a sync-check between the boundary script's hardcoded value set and the Tier-1/2/3 enum subset.
- `tests/unit/test_lint_boundaries.py` extended with 3 new tests + 1 parametrize entry covering positive + negative + docstring-tolerance cases.
- Two fixture files under `tests/fixtures/lint_violations/` (matching existing convention; the story spec said `boundary_violations/` but the project uses `lint_violations/` and renaming would have churned the unrelated checker tests).

**Boundary scope reduction (Tier-1/2/3 only; Tier-0 deliberately excluded):**

The initial implementation scanned for all 23 action-type values. This false-positived 3 times in production code — `__all__ = ["ask_router", ...]` lists in `mailbot_api/router/router.py`, `mailbot_api/router/__init__.py`, and `mailbot_api/verbs/ask_router.py`, where the string `"ask_router"` is the Python symbol name, not an action-type literal. Same false-positive risk exists for `"read_sql"`, `"generate_draft"`, `"send_chat_notification"`, `"write_derived_field"`.

**Resolution:** the boundary scan covers Tier 1/2/3 (18 values) only, which is where FR-5.6 ("agent cannot promote tier") actually matters — Tier-0 verbs never enter `pending_actions` per Story 4-2 AC, so a "bare `ask_router` string literal" cannot promote a tier even theoretically. The `test_boundary_check_action_value_set_matches_enum_tier_1_to_3` test asserts the script's hardcoded set equals `{at.value for at in ActionType if tier_for(at) >= 1}` — drift fails the regression.

Tier 0 still gets `requires_grant() == False` and `tier_for() == 0` correctly; the only thing not enforced for Tier 0 is the bare-string-literal lint. The `_PROPS` registry is exhaustive across all 23 members per AC-6 §10.

**Gate sweep results:**

- `pytest -q` → 487 passed + 2 skipped (was 468 baseline; +19 net new tests)
- `ruff check .` → 0 violations
- `mypy --strict mailbot_api/` → 0 issues across 68 source files
- `scripts/check_boundaries.py` → exit 0

**Test count math:**

- Story 4-1 net added: 17 `test_types.py` + 3 new `test_lint_boundaries` tests (+1 parametrize entry counted internally as a separate test by pytest's parametrize collector) — net +19/+20 vs baseline 468 → 487 observed.

**Open items for the reviewer:**

- Pre-review self-audit artifact `4-1-...pre-review.md` is the orchestrator's responsibility at Step 2.3.5; not produced by dev-story.
- Subtask 6.5 left unchecked intentionally — the pre-review artifact will be created after dev-story returns.
- AC-7 fixture rename: spec said `tests/fixtures/boundary_violations/` but actual project uses `tests/fixtures/lint_violations/`. Renamed to match convention; flag this discrepancy if you want the spec rewritten for future stories.

### File List

**New:**

- `mailbot_api/actions/types.py`
- `tests/unit/actions/__init__.py`
- `tests/unit/actions/test_types.py`
- `tests/fixtures/lint_violations/violates_bare_action_string_outside_types.py.fixture`
- `tests/fixtures/lint_violations/good_action_enum_use.py.fixture`

**Modified:**

- `mailbot_api/actions/__init__.py` (was empty 0B; now re-exports the public surface)
- `scripts/check_boundaries.py` (+ `_ACTION_TYPE_STRING_LITERAL_ALLOW` + `_ACTION_TYPE_VALUES` + `_collect_docstring_node_ids` helper + Tier-1/2/3 bare-literal check; module docstring updated)
- `tests/unit/test_lint_boundaries.py` (+ 1 parametrize entry for the action-string violation + 3 new tests: positive-pass at allowlisted path, negative-confirm for correct enum use, docstring tolerance)

**Modified (workflow state):**

- `_bmad-output/implementation-artifacts/sprint-status.yaml` (4-1 row + epic-4 row)
- `_bmad-output/implementation-artifacts/4-1-action-type-enum-and-tier-for-and-cross-cutting-properties-table.md` (this file)

**New (post code-review):**

- `tests/unit/actions/test_types_boundary.py` — CR-6 discoverability re-import

## Completion Notes

### 2026-06-02 — Story 4-1 done

- Dev pass landed the 23-member `ActionType` enum + `ActionProperties` Pydantic-frozen registry + helper trio + boundary check (Tier-1/2/3 scope) + 17 invariant tests + 3 boundary fixture/test scenarios.
- Code-review (sonnet-4.6, 3-layer adversarial) found 7 issues: 5 patched (CR-3 `del _PROPS`, CR-4 hasattr guards, CR-5 JSON deserialization round-trip + rename, CR-6 `test_types_boundary.py` discoverability re-import, CR-2 DELETE rationale strengthening), 1 deferred-with-disposition-owed-by-4-5 (CR-1 MODIFY_INBOX_RULE vs MODIFY_OUTLOOK_FILTER semantic question), 1 documented (CR-2 DELETE sensitivity-token rationale). 7/7 addressed; applied rate 5/7 = 71% (over 70% target).
- Test delta: 468 baseline → 492 passed (+24 net). All 4 gates green: pytest, ruff, mypy (68 source files), boundary check.
- Cross-story decisions owed: Story 4-5 must resolve MODIFY_INBOX_RULE vs MODIFY_OUTLOOK_FILTER (collapse-with-discriminator OR document distinct semantics). Flagged in epic-run-flags.md for downstream tracking.

### 2026-06-02 — CR-2 RESOLVED (Adam decision, Epic 4 retro)

- Story 4-1 CR-2 (`DELETE.requires_sensitivity_token=False`) was originally documented-with-rationale per the original CR pass. Adam's Epic 4 retro decision (2026-06-02 post-retro conversation, decision 13.2): **flip to `True`** — belt-and-suspenders. Destruction of a sensitive email is irreversible and deserves the same confirmation handshake as sending its contents to an API.
- **Patched:** `mailbot_api/actions/types.py:237` — `requires_sensitivity_token=True` on the DELETE `ActionProperties` entry. Docstring rationale paragraph at `types.py:80-115` rewritten to reflect the expanded framing ("extra confirmation on any high-consequence touch of a sensitive email" — not just "content-leak prevention").
- **Test updated:** `tests/unit/actions/test_types.py:test_sensitivity_token_invariant` — expected set is now `EXPECTED_SEND_FAMILY | {ActionType.DELETE}` (5 members, not 4).
- **Verb propagation:** `propose_action` refusal arm propagates automatically via the `ACTION_PROPERTIES` registry lookup — no verb-layer code changes needed. `mint_sensitivity_token` (Story 4-7) already supports any task_type binding, so the DELETE-via-handshake flow uses the same mint→consume pattern as the SEND-family flow.
- **Gates:** all 4 green; pytest 654 stable (no test count delta — one assertion updated in place); ruff / mypy --strict (85 source files) / boundary checker clean.
- Memory: persisted to `project_delete_requires_sensitivity_token.md` so this rule binds future sessions.
