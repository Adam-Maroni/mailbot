---
baseline_commit: aa87929
---

# Story 6.19: action_type discoverability and SKILL.md constraint strengthening — F29 closure

Status: done

> **Filed 2026-06-06** during Story 6-6.5 fifth-pass live walk. **F29 HIGH** — Hermes's Haiku-4.5 main-inference hallucinated `action_type='SEND_EMAIL'` instead of the canonical `SEND_REPLY` when filling `propose_action` tool-call parameters. The verb correctly refused with `INVALID_ACTION_TYPE`, but no discoverability path existed for Hermes to recover: `list_resources` + `list_prompts` were probed and returned no canonical action_type enumeration. SKILL.md's instruction `ActionType.SEND_REPLY` was not load-bearing enough to override Haiku's parameter-generation prior.
>
> **Severity HIGH.** Not blocking Story 6-6.5 re-walk independently of Story 6-20, but **CP-A and CP-D cannot pass** without it — the agent must successfully fill `propose_action(action_type='SEND_REPLY')` for those checkpoints to clear.

## Story

As Adam,
I want every Hermes-driven `propose_action` call to either succeed on first attempt OR receive a structured error response carrying the canonical enum members AND a discoverable MCP resource enumerating the 23 canonical action types AND a strengthened SKILL.md constraint that's load-bearing against Haiku's parameter-generation prior,
So that an action_type hallucination (F29's surface) is self-correcting in a single turn instead of an opaque dead-end that requires the agent to give up.

## Acceptance Criteria

### AC-1 — `propose_action` verb error response carries `valid_action_types` recovery hint

The `propose_action` verb shim at [mailbot_api/verbs/propose_action.py](../../mailbot_api/verbs/propose_action.py) SHALL include the full canonical enum-member list in the `INVALID_ACTION_TYPE` error path. The recovery hint MUST:

1. Carry the 23 action_type string values (e.g., `"send_reply"`, `"archive"`, `"mark_read"`, etc. — the snake_case `.value` of each `ActionType` enum member, not the UPPER_SNAKE name).
2. Sort the list deterministically: `sorted(at.value for at in ActionType)` so test assertions are stable and forensic queries are reproducible.
3. Surface as a NEW Pydantic field `valid_action_types: list[str] | None` on `ProposeActionError`. The field SHALL be `None` for every error code OTHER than `INVALID_ACTION_TYPE` (the hint is only relevant to that specific failure mode; carrying it on every error pollutes the contract).
4. Populate ONLY in the verb-shim path (`mailbot_api/verbs/propose_action.py`), NOT in the action implementation's `ProposeActionError` raise paths (`mailbot_api/actions/propose.py`) — those errors have different semantics (TIER_PROMOTION_ATTEMPT, EMAIL_NOT_FOUND, etc.) and shouldn't carry the recovery hint.

**Implementation outline (illustrative, dev adapts to fit conventions):**

```python
# mailbot_api/verbs/propose_action.py
from mailbot_api.actions.types import ActionType

# Module-level constant — computed once at import, immutable.
_VALID_ACTION_TYPES: Final[list[str]] = sorted(at.value for at in ActionType)

async def propose_action(email_id, action_type, payload=None, *, db_path):
    try:
        at = ActionType(action_type)
    except ValueError:
        return ProposeActionOut(
            ok=False,
            error=ProposeActionError(
                code="INVALID_ACTION_TYPE",
                message=(
                    f"unknown action_type {action_type!r}; "
                    f"must be one of {_VALID_ACTION_TYPES}"
                ),
                valid_action_types=_VALID_ACTION_TYPES,
            ),
        )
    return await _propose_action_impl(email_id, at, payload=payload, db_path=db_path)
```

The error MESSAGE also embeds the full list so any agent reading only the message field (not the structured field) still gets the recovery hint. The structured field is the load-bearing surface for agents that parse the error correctly.

### AC-2 — NEW MCP resource `mailbot://action-types` enumerating the canonical ActionType enum

`mailbot_api/mcp_server.py`'s `build_mcp_server` SHALL register a new MCP resource at URI `mailbot://action-types` so any Hermes-side `list_resources` discovery probe returns it. The resource MUST:

1. Use URI `mailbot://action-types` (matching the stub's spec verbatim).
2. Be a `TextResource` (mime_type `application/json`) carrying a JSON object with the canonical enum + per-action tier + per-action sensitivity-token requirement. Shape:

```json
{
  "action_types": [
    {
      "value": "send_reply",
      "tier": 3,
      "requires_sensitivity_token": true,
      "is_send_family": true,
      "is_email_less": false
    },
    {
      "value": "archive",
      "tier": 2,
      "requires_sensitivity_token": false,
      "is_send_family": false,
      "is_email_less": false
    },
    ... (one entry per ActionType member, sorted by `value`)
  ],
  "synonyms_rejected": [
    "send_email", "sendReply", "send", "SEND_EMAIL", "reply",
    "send-reply", "delete_email", "trash", "remove"
  ],
  "constraint": "Pass the canonical snake_case `value` field as `action_type` (e.g., \"send_reply\"). Synonyms / variants / UPPER_SNAKE names are rejected with INVALID_ACTION_TYPE."
}
```

3. Be retrievable via the standard MCP `read_resource` flow — the JSON body returned exactly as authored.
4. Carry a `description` field on the Resource registration (visible in `list_resources` output): `"Canonical mailbot ActionType enumeration with tier + sensitivity-token requirement per action. Pass the `value` field as `propose_action(action_type=...)`."`
5. Carry a `name` field: `"action-types"`.

**Why `synonyms_rejected` matters:** F29's specific failure was `SEND_EMAIL`. Listing the rejected synonyms inline gives the agent's parameter generator a "things-that-look-right-but-aren't" signal at the same point in the prompt as the canonical list. Anti-anchoring discipline.

**Where to insert in `mcp_server.py`:** after the `for tool_name, wrapper in wrappers.items()` registration loop (line 965-967), add a `server.add_resource(TextResource(...))` call with the constructed JSON body. Build the body once at module level (or inside `build_mcp_server`) — it never changes after import.

### AC-3 — Hermes-config SKILL.md amended with explicit constraint

[hermes-config/skills/mailbot/SKILL.md](../../hermes-config/skills/mailbot/SKILL.md) — the `### propose_action` section (line 88-105) SHALL gain a load-bearing constraint subsection. The wording MUST:

1. Be explicit about uppercase/lowercase: "Pass `action_type='send_reply'` (lowercase snake_case, literal). The verb rejects `SEND_REPLY`, `SEND_EMAIL`, `sendReply`, `send-reply`, or any other variant."
2. Include a "User-intent → canonical action_type" table at minimum for the 3 highest-collision intents:
   - User says "send" / "reply" / "send this" → `send_reply`
   - User says "delete" / "trash" / "remove" → `delete`
   - User says "archive" / "file away" → `archive`
3. Include a discoverability note pointing to the new MCP resource: "If unsure, call `read_resource(mailbot://action-types)` to fetch the canonical enum + synonyms_rejected list."

**Where to insert:** add a `#### Canonical action_type values` H4 subsection inside the existing `### propose_action` H3 section, between the "Tier-handling responsibility" paragraph (line 101-105) and the next `### mint_grant` (line 107). Keep the existing content unchanged.

### AC-4 — Regression test for the hallucinated-action_type recovery path

`tests/unit/verbs/test_propose_action_invalid_action_type_recovery.py` (new file; per project convention of per-finding test files):

1. **`test_unknown_action_type_returns_invalid_action_type_code`** — invoke `propose_action(email_id="e1", action_type="SEND_EMAIL", db_path=db_path)`. Assert `result.ok is False`, `result.error.code == "INVALID_ACTION_TYPE"`, `result.error.message` contains `"SEND_EMAIL"` (the offending value, for forensic clarity).
2. **`test_invalid_action_type_error_carries_valid_action_types_field`** — same invocation; assert `result.error.valid_action_types` is a list of length 23, contains `"send_reply"` and `"archive"` and `"delete"` and `"mark_read"`, is `sorted()` (deterministic order).
3. **`test_invalid_action_type_error_message_embeds_full_list`** — same invocation; assert the error message string contains `"send_reply"` and `"archive"` so an agent parsing only the message (not the structured field) still has the recovery hint.
4. **`test_valid_action_types_field_is_none_on_other_error_codes`** — pick a non-`INVALID_ACTION_TYPE` failure (e.g., `EMAIL_NOT_FOUND` by passing a bogus `email_id` with a valid `action_type="archive"`). Assert `result.error.code == "EMAIL_NOT_FOUND"` AND `result.error.valid_action_types is None`. The field is scoped to the specific failure mode only.
5. **`test_known_synonyms_all_rejected`** — parametrize over `["SEND_REPLY", "send-reply", "sendReply", "SEND_EMAIL", "reply", "delete_email", "trash"]`. For each, assert `INVALID_ACTION_TYPE` + `valid_action_types` populated. Locks in the synonym-rejection invariant against future enum drift.

`tests/integration/test_mcp_server_action_types_resource.py` (new file):

6. **`test_action_types_resource_registered`** — invoke `build_mcp_server(db_path=...)`. Assert via `await server.list_resources()` that a resource with URI `mailbot://action-types` is present with name `"action-types"` and description containing `"Canonical mailbot ActionType enumeration"`.
7. **`test_action_types_resource_payload_shape`** — invoke `await server.read_resource("mailbot://action-types")`. Parse as JSON. Assert:
   - Top-level keys `action_types`, `synonyms_rejected`, `constraint` all present
   - `action_types` is a list of 23 dicts
   - Each dict has keys `value`, `tier`, `requires_sensitivity_token`, `is_send_family`, `is_email_less`
   - `action_types[0].value` (sorted-first) matches `min(at.value for at in ActionType)` — proves determinism
   - `synonyms_rejected` is a list containing at least `"send_email"`, `"sendReply"`, `"send"`, `"SEND_EMAIL"`
8. **`test_action_types_resource_includes_send_reply_with_correct_metadata`** — assert the entry for `"send_reply"` has `tier=3`, `requires_sensitivity_token=True`, `is_send_family=True`, `is_email_less=False`. Direct correctness against `ACTION_PROPERTIES`.
9. **`test_action_types_resource_includes_send_new_email_as_email_less`** — assert the entry for `"send_new_email"` has `is_email_less=True` (per `EMAIL_LESS_ACTIONS`). Edge-case lockdown.

### AC-5 — Live walk re-test verification (deferred to Story 6-6.5 re-walk; out of scope here)

The live walk re-test confirming Hermes successfully fills `SEND_REPLY` after Story 6-19 ships is **explicitly deferred to Story 6-6.5's re-walk**. This story does NOT run the live walk — it ships the code-level closure (AC-1 through AC-4) + the cross-doc updates (AC-3). The re-walk verdict is the operational verification, but the autonomous-epic-run skill cannot execute it (manual walk; requires Adam in Discord). Documented in story Completion Notes.

### AC-6 — MANDATORY-CR per §5.12

The §5.12 cadence verdict is **`MANDATORY-CR`**. Two criteria fire:

1. **Cross-story load-bearing seam (criterion 6).** Touches Stories 4-1 (ActionType enum + ACTION_PROPERTIES registry), 4-2 (propose_action verb + tier-promotion guard at verb boundary), 5-2 (MCP server tool registration), 5-5 (Hermes-config SKILL.md propose_action flow). Four prior stories' invariants must continue holding.
2. **External transport / contract surface (criterion 1).** The MCP resource at `mailbot://action-types` is a NEW external Hermes-facing contract. Once shipped, Hermes-side code (the agent's recovery loop) becomes dependent on the resource's URI + JSON schema. Schema drift would break agents — reviewer must scrutinize the schema's stability.

Minimum one CR pass before done-flip. Review model: Sonnet 4.6 (different from dev Opus 4.7).

**Reviewer focus areas:**

- (a) `_VALID_ACTION_TYPES` module-level constant is immutable (use `Final[list[str]]` or `Final[tuple[str, ...]]`)
- (b) `ProposeActionError.valid_action_types: list[str] | None` default `None` doesn't break the existing frozen-Pydantic model + existing callers that don't pass the field
- (c) MCP resource JSON shape is stable + extensible (additive-only schema evolution; no field renames)
- (d) Synonyms_rejected list isn't load-bearing for correctness — verify it can be empty without breaking the contract (it's a hint, not a gate)
- (e) The verb-shim path is the ONLY place that populates `valid_action_types`; the actions/propose.py error paths are NOT polluted (AC-1 §4)

## Tasks / Subtasks

- [x] **Task 1 — Extend `ProposeActionError` model** — shipped at [mailbot_api/actions/propose.py:54-66](../../mailbot_api/actions/propose.py#L54-L66) with `valid_action_types: list[str] | None = None`. Default None preserves existing call-sites. Frozen Pydantic model semantics preserved.
- [x] **Task 2 — Update `propose_action` verb shim** — shipped at [mailbot_api/verbs/propose_action.py:27-60](../../mailbot_api/verbs/propose_action.py#L27-L60). Module-level `_VALID_ACTION_TYPES: Final[list[str]] = sorted(at.value for at in ActionType)` populated on INVALID_ACTION_TYPE only; error message also embeds full list inline for agents reading only the message field.
- [x] **Task 3 — Register the `mailbot://action-types` MCP resource** — shipped at [mailbot_api/mcp_server.py:893-1056](../../mailbot_api/mcp_server.py#L893-L1056). Helper `_build_action_types_resource_body()` builds JSON body with sorted-by-value entries + 5 per-entry fields + `synonyms_rejected` anti-anchor + `constraint` string. Registered via `server.add_resource(TextResource(...))` after tool registration loop.
- [x] **Task 4 — Amend hermes-config SKILL.md** — shipped at [hermes-config/skills/mailbot/SKILL.md:106-127](../../hermes-config/skills/mailbot/SKILL.md#L106-L127). New `#### Canonical action_type values` H4 subsection inside `### propose_action`. Covers literal lowercase snake_case + 3-row user-intent → canonical-value table + pointer to `read_resource("mailbot://action-types")`.
- [x] **Task 5 — Write 5 unit tests** — shipped 11 unit assertions (5 base + 7 parametrized synonym variants minus 1 dedup) in `tests/unit/verbs/test_propose_action_invalid_action_type_recovery.py`. All green.
- [x] **Task 6 — Write 4 integration tests** — shipped in `tests/integration/test_mcp_server_action_types_resource.py`. All 4 green.
- [x] **Task 7 — Cross-doc updates:**
  - [x] `_bmad-output/implementation-artifacts/epic-6-run-flags.md § F29` — "## F29 — RESOLVED (2026-06-06, Story 6-19)" closing block shipped with implementation summary + 3-layer recovery design + test evidence + live-walk dependency note.
  - [x] hermes-config/skills/mailbot/SKILL.md (covered by Task 4)
- [x] **Task 8 — Pre-Review Self-Audit Gate (Step 2.3.5)** — `6-19-action-type-discoverability-and-skill-md-constraint-strengthening-f29-closure.pre-review.md` shipped. All 5 sections + 12-check §5 Posture Audit. §5.12 verdict: **`MANDATORY-CR`** (2 criteria fire: external transport contract + cross-story load-bearing seam). §5.3 lifecycle-string check: zero collisions on `valid_action_types` field name, `mailbot://action-types` URI, `action-types` resource name.
- [x] **Task 9 — MANDATORY-CR pass** per AC-6 / §5.12 COMPLETE. Sonnet 4.6 reviewer, 7 findings: 6 actionable APPLIED (CR-1 tuple defense-in-depth for both module constants, CR-2 ProposeActionError field tuple typing, CR-3 parametrize expansion to cover all anti-anchor entries, CR-4 module-level resource body cache, CR-5 per-entry key check tightened from >= to ==, CR-6 not-in assertion in parametrized test); 1 defer-with-rationale (CR-7 FastMCP API coupling — pre-existing pattern). Post-CR 4 gates re-verified green at 1129+2+3-deselected.
- [x] **Task 10 — All gates green** at baseline +15 net: ruff clean, mypy --strict clean (123 files), boundary clean, pytest **1126 passed + 2 skipped + 3 deselected** (vs Story 6-20 baseline 1111+2+3 → +15 net). Story 4-1 + Story 4-2 + Story 5-2 + Story 5-5 existing tests stay green unmodified — AC-6 cross-story preservation verified.

### Review Findings

(Sonnet 4.6 MANDATORY-CR pass — 2026-06-06. 3 decision_needed, 3 patch, 1 defer, 1 dismissed.)

- [x] [Review][Patch] **CR-1 (Decision-resolved → APPLIED): `_VALID_ACTION_TYPES` and `_ACTION_TYPE_SYNONYMS_REJECTED` → `Final[tuple[str, ...]]`** — APPLIED at [mailbot_api/verbs/propose_action.py:30-40](../../mailbot_api/verbs/propose_action.py#L30-L40) and [mailbot_api/mcp_server.py:905-915](../../mailbot_api/mcp_server.py#L905-L915). Both module-level constants now tuple-typed with `tuple(sorted(...))` / parenthesized literal. Mutation attempts surface as TypeError. Inline comments cite CR-1 rationale. Resource body's JSON serialization unaffected (tuple → JSON array conversion is automatic via `list(_ACTION_TYPE_SYNONYMS_REJECTED)`).
- [x] [Review][Patch] **CR-2 (Decision-resolved → APPLIED): `ProposeActionError.valid_action_types: tuple[str, ...] | None`** — APPLIED at [mailbot_api/actions/propose.py:55-77](../../mailbot_api/actions/propose.py#L55-L77). Field type changed from `list[str] | None` to `tuple[str, ...] | None`. Test 2 (`test_invalid_action_type_error_carries_valid_action_types_field`) now asserts `isinstance(result.error.valid_action_types, tuple)` to lock the invariant in regression coverage. Inline docstring expanded to cite CR-2 rationale.
- [x] [Review][Patch] **CR-3 (Decision-resolved → APPLIED): parametrize list extended to cover all 9 entries in `_ACTION_TYPE_SYNONYMS_REJECTED`** — APPLIED at [tests/unit/verbs/test_propose_action_invalid_action_type_recovery.py:128-145](../../tests/unit/verbs/test_propose_action_invalid_action_type_recovery.py#L128-L145). Added `"send_email"`, `"send"`, `"remove"` to bring the parametrize list to 10 entries (covers all 9 anti-anchor synonyms + `SEND_REPLY` UPPER_SNAKE foot-gun). Inline comment cites CR-3 rationale. Test count: +3 parametrized variants.
- [x] [Review][Patch] **CR-4 (APPLIED): cache `_ACTION_TYPES_RESOURCE_BODY: Final[str]` at module level** — APPLIED at [mailbot_api/mcp_server.py:950-955](../../mailbot_api/mcp_server.py#L950-L955). Module-level cache eliminates the redundant per-`build_mcp_server()` serialization; pattern mirrors the existing `_TOOL_DESCRIPTIONS` module-level dict. `build_mcp_server` now references the cached string instead of calling the function.
- [x] [Review][Patch] **CR-5 (APPLIED): tighten per-entry key check from `>=` to `==`** — APPLIED at [tests/integration/test_mcp_server_action_types_resource.py:69-83](../../tests/integration/test_mcp_server_action_types_resource.py#L69-L83). Per-entry shape now strictly enforced (`set(entry.keys()) == required_fields`); top-level body check stays subset (`>=`) per AC-6(c) additive-evolution rationale. Typos producing extra unexpected per-entry keys now fail the test. Inline comment explains the asymmetry.
- [x] [Review][Patch] **CR-6 (APPLIED): explicit not-in assertion in parametrized test** — APPLIED at [tests/unit/verbs/test_propose_action_invalid_action_type_recovery.py:165-167](../../tests/unit/verbs/test_propose_action_invalid_action_type_recovery.py#L165-L167). Added `assert bad_action_type not in result.error.valid_action_types`. Self-documents the synonym-rejection invariant beyond the 23-length guard. Trivial addition; non-load-bearing safety net.
- [x] [Review][Defer] **CR-7: Test uses FastMCP internal `ReadResourceContents.content` attribute** [`tests/integration/test_mcp_server_action_types_resource.py:55`] — `contents_list[0].content` accesses the FastMCP internal attribute by name; if FastMCP renames the attribute (e.g., to `.text` or `.data`), test breaks silently at the assertion. Pre-existing FastMCP API coupling pattern in this project; not introduced exclusively by Story 6-19. Defer for a future FastMCP-upgrade story. — deferred, pre-existing FastMCP API surface assumption

## Dev Notes

### Why this story exists (root-cause from F29 evidence)

During Story 6-6.5 fifth-pass live walk (2026-06-06), Hermes's Haiku-4.5 main-inference was asked to "send the reply" by Adam. Haiku populated the `propose_action` tool-call with `action_type='SEND_EMAIL'` instead of the canonical `send_reply`. The verb correctly refused at `mailbot_api/verbs/propose_action.py:35-43`:

```python
try:
    at = ActionType(action_type)
except ValueError:
    return ProposeActionOut(
        ok=False,
        error=ProposeActionError(
            code="INVALID_ACTION_TYPE",
            message=f"unknown action_type {action_type!r}",
        ),
    )
```

The error message `"unknown action_type 'SEND_EMAIL'"` is NOT load-bearing enough for the agent to recover. Hermes probed `list_resources` and `list_prompts` looking for a canonical enumeration — found nothing — and gave up. The user-visible outcome was an opaque dead-end.

The fix is a 3-layer recovery design:

1. **Error-time recovery (AC-1):** the verb's error response carries the canonical list inline so the agent's next tool call can self-correct without further discovery.
2. **Discovery-time recovery (AC-2):** a new MCP resource at `mailbot://action-types` so any `list_resources` probe — including the one Hermes already tried — returns the canonical enumeration.
3. **Prompt-time prevention (AC-3):** SKILL.md gains a load-bearing constraint subsection with explicit lowercase/snake_case rule + user-intent → canonical mapping table + pointer to the new MCP resource. Anti-anchoring against Haiku's parameter-generation prior.

### Why include `synonyms_rejected` in the MCP resource

Pure enum-list responses don't help when the model's prior STRONGLY pulls toward a specific wrong value. Listing `SEND_EMAIL`, `sendReply`, etc. as `synonyms_rejected` at the same prompt-context location as the canonical list creates an anti-anchor — the model sees "X is wrong; Y is right" co-located. This is the same anti-anchoring discipline applied in Story 6-18 (qwen v1→v2 prompt) and prefigures Story 6-21 (qwen borderline classification).

### Why the verb-shim path, NOT the actions/propose.py path

`mailbot_api/actions/propose.py` raises errors for TIER_PROMOTION_ATTEMPT, EMAIL_NOT_FOUND, EMAIL_NEVER_SYNCED, EMAIL_DELETED, INVALID_PAYLOAD. None of these are "agent mistyped the enum name" — they are real-state errors. Polluting their error payload with a `valid_action_types` field would be:

1. **Semantically wrong:** the hint is irrelevant to those failure modes.
2. **Schema-bloating:** every error response carries N+1 fields where N would suffice.
3. **Untestable:** the field's presence-vs-absence becomes meaningless if it's always set.

The verb-shim is the FIRST point where the agent's input string is validated against the enum. That's the exact moment when the recovery hint is load-bearing.

### What MUST NOT change

- **`ActionType` enum membership** stays at 23 members verbatim.
- **`ACTION_PROPERTIES` registry** stays unchanged — no new field, no new entry.
- **`EMAIL_LESS_ACTIONS` frozenset** stays at the 4 current members (`MODIFY_INBOX_RULE`, `MODIFY_OUTLOOK_FILTER`, `TOUCH_DELEGATED_MAILBOX`, `SEND_NEW_EMAIL`).
- **`mailbot_api/actions/propose.py`'s `_propose_action_impl` error paths** stay unchanged — only the verb shim populates `valid_action_types`.
- **`ProposeActionOut` shape** stays — only `ProposeActionError` gets a new optional field.
- **MCP server tool registration loop** stays — resource registration is ADDITIONAL, not a replacement.
- **Story 6-9's `mailbot://action-types`-like patterns** — N/A, no such resource existed before; this is the first MCP resource MailBot registers (tools-only prior).

### References

- [mailbot_api/actions/types.py](../../mailbot_api/actions/types.py) — `ActionType` enum (23 members) + `ACTION_PROPERTIES` registry + `EMAIL_LESS_ACTIONS` + `is_send_family()` (Story 4-1)
- [mailbot_api/actions/propose.py:54-60](../../mailbot_api/actions/propose.py#L54-L60) — `ProposeActionError` (Pydantic frozen; needs `valid_action_types` field)
- [mailbot_api/verbs/propose_action.py](../../mailbot_api/verbs/propose_action.py) — verb shim (where the recovery hint is populated)
- [mailbot_api/mcp_server.py:884-969](../../mailbot_api/mcp_server.py#L884-L969) — `build_mcp_server` (where the resource is registered)
- [hermes-config/skills/mailbot/SKILL.md:88-105](../../hermes-config/skills/mailbot/SKILL.md#L88-L105) — `propose_action` SKILL.md section
- [tests/integration/test_mcp_server.py:176-249](../../tests/integration/test_mcp_server.py#L176-L249) — existing MCP server test patterns (tool-registration, schema, set_db_path)
- `_bmad-output/implementation-artifacts/epic-6-run-flags.md § F29` — full F29 finding text (CP-A walk evidence)

## Dev Agent Record

### Agent Model Used

- Dev: claude-opus-4-7 (Opus 4.7, 1M context) via autonomous-epic-run
- Code Review: claude-sonnet-4-6 (Sonnet 4.6, MANDATORY-CR per §5.12 — 2 criteria fire: external transport contract + cross-story load-bearing seam) — to be dispatched at Step 2.4

### Debug Log References

- Pre-review self-audit: `6-19-action-type-discoverability-and-skill-md-constraint-strengthening-f29-closure.pre-review.md` (5 sections + 12-check §5 posture audit; §5.12 cadence verdict = MANDATORY-CR with 2 criteria firing).
- AC-4 test 4 (EMAIL_NOT_FOUND counter-test) required `action_type='delete'` instead of `'archive'` to surface the change_marker-capture path; Tier-1/Tier-2 propose paths bypass `_capture_change_marker`. Inline comment documents the dependency.
- 3-layer recovery design rationale: error-time recovery (verb shim) + discovery-time recovery (MCP resource) + prompt-time prevention (SKILL.md). Layer redundancy is intentional — F29's specific failure was that the agent didn't discover the recovery path. Multiple discovery surfaces (in-band error + out-of-band resource + system-prompt constraint) maximize the chance of self-correction without falling back to a brittle single point.

### Completion Notes List

- **F29 root cause closed via 3-layer recovery design.** F29's surface was `INVALID_ACTION_TYPE` returned with an opaque message — no recovery path. The fix gives the agent THREE discoverability surfaces: (1) the error response itself carries the canonical 23 values inline + as a structured field; (2) the MCP resource `mailbot://action-types` carries the same data + an anti-anchor `synonyms_rejected` list for `list_resources` discovery; (3) SKILL.md amendment with user-intent → canonical-value table + pointer to the MCP resource for prompt-time prevention.
- **Verb-shim is the right producer-boundary for `valid_action_types`.** The hint is scoped to the specific failure mode (INVALID_ACTION_TYPE only). Polluting the actions/propose.py error paths would be semantically wrong + schema-bloating + untestable. Story Dev Notes "Why the verb-shim path, NOT the actions/propose.py path" covers the design rationale.
- **MCP resource is the FIRST resource MailBot registers.** The project previously shipped tools-only via the MCP transport. Adding a resource exercised the FastMCP `add_resource` + `TextResource` API; pattern is documented in mcp_server.py for future resource additions.
- **`synonyms_rejected` anti-anchor list is hand-curated.** 9 entries covering F29's actual hallucination (`SEND_EMAIL`) + 8 common variant forms. Not load-bearing for correctness (the gate is the enum lookup); pure discoverability signal. Future story may auto-expand from `router_calls` forensic data if hallucination patterns shift.
- **`_VALID_ACTION_TYPES: Final[list[str]]` mutable-list concern flagged for reviewer.** `Final` annotates name binding, not object immutability. A caller could append to the list. ESCALATE TO REVIEWER for tuple defense-in-depth decision (pre-review self-audit §3 + §5.7).
- **Story 4-1 / 4-2 / 5-2 / 5-5 contracts preserved.** Existing test files (`test_propose.py`, `test_mcp_server.py`, `test_mcp_server_extended_tools.py`) stay green unmodified — verified via full sweep at 1126+2+3-deselected.
- **All 4 gates green:** ruff clean (1 import-cleanup autofix on test file), mypy --strict clean (123 files), boundary clean, pytest **1126 passed + 2 skipped + 3 deselected** (+15 net from Story 6-20 baseline 1111+2+3 — matches the actual 11 unit + 4 integration tests added; the AC-4 spec text's "+9 net" was an undercount, the gate evidence is +15 because parametrized variants count individually).
- **MANDATORY-CR pass scheduled** for Step 2.4 of orchestrator (Sonnet 4.6 reviewer, different model from dev). Findings + dispositions will land in Review Findings section above.

### File List

- `mailbot_api/actions/propose.py` (modified) — added `valid_action_types: list[str] | None = None` field to `ProposeActionError` model with docstring explaining the Story 6-19 scope
- `mailbot_api/verbs/propose_action.py` (modified) — added module-level `_VALID_ACTION_TYPES: Final[list[str]]` constant; populated `valid_action_types` + embedded full list inline in error message on INVALID_ACTION_TYPE path only
- `mailbot_api/mcp_server.py` (modified) — added `_ACTION_TYPE_SYNONYMS_REJECTED` constant + `_build_action_types_resource_body()` helper + `server.add_resource(TextResource(...))` registration after the tool registration loop; imports extended for `TextResource`, `AnyUrl`, `Final`, `json`, `ActionType`, `ACTION_PROPERTIES`, `EMAIL_LESS_ACTIONS`, `is_send_family`
- `hermes-config/skills/mailbot/SKILL.md` (modified) — added `#### Canonical action_type values` H4 subsection inside `### propose_action` with literal-snake_case requirement + user-intent → canonical-value table + MCP resource discovery pointer
- `_bmad-output/implementation-artifacts/epic-6-run-flags.md` (modified) — added "## F29 — RESOLVED (2026-06-06, Story 6-19)" closing block with 3-layer recovery design + test evidence + live-walk dependency note
- `tests/unit/verbs/test_propose_action_invalid_action_type_recovery.py` (new) — 5 base unit tests + 7 parametrized synonym tests (11 unit assertions) covering AC-4 tests 1-5
- `tests/integration/test_mcp_server_action_types_resource.py` (new) — 4 integration tests covering AC-4 tests 6-9
- `_bmad-output/implementation-artifacts/6-19-action-type-discoverability-and-skill-md-constraint-strengthening-f29-closure.md` (this file — story spec + Dev Agent Record + Tasks/Subtasks checks + Review Findings placeholder)
- `_bmad-output/implementation-artifacts/6-19-action-type-discoverability-and-skill-md-constraint-strengthening-f29-closure.pre-review.md` (new) — 5-section pre-review self-audit per Step 2.3.5
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified) — row 179 status: backlog → ready-for-dev → in-progress → review

### Change Log

- 2026-06-06 — Story 6.19 filed as STUB during Story 6-6.5 fifth-pass live walk (sprint-status.yaml row 179). F29 HIGH discoverability gap surfaced.
- 2026-06-06 — autonomous-epic-run create-story pickup: context-engineered AC structure (6 ACs + 10 tasks), 3-layer recovery design (verb error + MCP resource + SKILL.md constraint), synonyms_rejected anti-anchoring rationale, MANDATORY-CR criteria enumerated (2 §5.12 criteria — cross-story load-bearing seam + external transport contract), baseline `aa87929`.
- 2026-06-06 — autonomous-epic-run dev-story pickup: Tasks 1-8 + 10 shipped (verb shim extension, MCP resource registration, SKILL.md amendment, 11 unit + 4 integration tests, cross-doc updates, pre-review self-audit, all 4 gates green at 1126+2+3-deselected). Story flips ready-for-dev → in-progress → review. Task 9 (MANDATORY-CR) awaits Step 2.4 of orchestrator.
- 2026-06-06 — autonomous-epic-run Step 2.4 MANDATORY-CR complete via Sonnet 4.6 subagent. 7 findings: 6 actionable APPLIED (CR-1 + CR-2 tuple defense-in-depth for module constants + Pydantic field, CR-3 parametrize coverage extension, CR-4 module-level resource body cache, CR-5 per-entry key check tightened to ==, CR-6 not-in self-documenting assertion); 1 defer-with-rationale (CR-7 FastMCP API coupling — pre-existing). Post-CR 4 gates re-verified green at 1129+2+3-deselected (+3 from CR-3 parametrize expansion). Story flips review → done.
