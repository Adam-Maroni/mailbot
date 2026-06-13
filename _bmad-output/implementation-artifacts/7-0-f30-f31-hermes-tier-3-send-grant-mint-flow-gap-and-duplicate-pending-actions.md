# Story 7-0-f30-f31 — Hermes Tier-3 SEND grant-mint flow gap (F30 HIGH) + duplicate pending_actions on send confirmation (F31 LOW)

**Status:** done

## Summary

Both findings surfaced live during Story 6-6.5 sixth-pass walk CP-A (2026-06-06). F30 HIGH: Hermes called `propose_action(send_reply)` correctly, row inserted as `status='cooling_off'`, cooling-off ticker promoted to `pending`, drainer claimed, no valid `action_grants` row existed, drainer reverted to `pending_grant` (Story 6-13 F22 behavior) — but Hermes never called `mint_grant("send_reply", [email_ids], expires_at)` to satisfy the Tier-3 grant requirement. Without operator intervention, both rows would have stayed stuck in `pending_grant` forever. Adam manually minted a grant via `docker exec` to unstick. F31 LOW: Hermes treated the user's `send` confirmation as a fresh "draft a reply" request instead of confirming the existing cooling-off row — 2 identical `pending_actions` rows were created for the same email_id + action_type.

**Root cause class (shared between F30 + F31):** `ProposeActionOut` doesn't expose `requires_grant` / `requires_per_action_confirmation` boolean signals so Hermes has no in-band signal that a grant is required or that "send" should confirm an existing pending action. SKILL.md line 102 already DOCUMENTS the contract Adam expects ("if the verb returns `requires_grant=True`, you mint a grant") — but the actual return shape doesn't ship those fields.

## Acceptance Criteria

**AC §1 — Investigation finding: Story 4-2 vs SKILL.md documentation drift**
**Given** Story 4-2's `propose_action` verb returns `ProposeActionOut` and Story 4-1's `ACTION_PROPERTIES` registry declares per-action `tier` + `is_send_family` metadata
**When** the return shape is investigated
**Then** the implementation history is checked first AND the finding is documented in Dev Notes
**Verdict:** **Documentation drift confirmed.** [mailbot_api/actions/propose.py:78-88](../../mailbot_api/actions/propose.py#L78-L88) defines `ProposeActionOut` as `(ok, action_id, tier, status, error)` — no `requires_grant` / `requires_per_action_confirmation` fields. Meanwhile [hermes-config/skills/mailbot/SKILL.md:101-105](../../hermes-config/skills/mailbot/SKILL.md#L101-L105) tells the agent: "If the verb returns `requires_grant=True`, you mint a grant. If it returns `requires_per_action_confirmation=True`, you ask the user to confirm." Story 4-2's ACs did NOT actually require these fields on the return shape (verified by grep against epics.md Story 4.2 detail block) — the SKILL.md contract was aspirational documentation written ahead of the implementation. This story closes the drift.

**AC §2 — `ProposeActionOut` schema extension**
**Given** `ProposeActionOut` does not currently populate `requires_grant` / `requires_per_action_confirmation`
**When** the schema is extended
**Then** `requires_grant: bool` is added, populated from `ACTION_PROPERTIES[action_type].tier >= 2` (Tier-2 BATCH + Tier-3 SEND-family both require grants) — reuse the existing `requires_grant(action_type)` helper at [mailbot_api/actions/types.py:329](../../mailbot_api/actions/types.py#L329)
**And** `requires_per_action_confirmation: bool` is added, populated from `ACTION_PROPERTIES[action_type].is_send_family` (Tier-3 SEND-family requires per-action `send` confirmation following the cooling-off window; Tier-2 BATCH grants cover N actions of the same type without per-action re-confirmation) — reuse the existing `is_send_family(action_type)` helper at [mailbot_api/actions/types.py:318](../../mailbot_api/actions/types.py#L318)
**And** the fields default to `False` (back-compat — existing refusal-arm code paths return `ok=False` with no need to populate the booleans)
**And** existing call sites that destructure `ProposeActionOut` continue to work (the new fields are added without removing existing ones; existing tests don't reference the new fields and stay green)

**AC §3 — SKILL.md amendment: Tier-3 SEND flow + per-action confirmation rule**
**Given** `hermes-config/skills/mailbot/SKILL.md` `### propose_action` section
**When** the SKILL.md amendment is shipped
**Then** the section gains a new `#### Tier-3 SEND flow` H4 subsection covering:
  - after `propose_action(send_reply, email_id, payload)` returns with `requires_grant=True`, the agent MUST call `mint_grant(action_type="send_reply", email_ids=[email_id], expires_at=<60s from now>)` BEFORE the cooling-off window closes
  - the rationale: Tier-3 SEND grants are per-action (single email_id, single action_type) by design — the cooling-off window is the cancel-affordance, the grant is the "yes really send this specific email" signal
  - the failure mode if mint_grant is missed: drainer reverts the row to `pending_grant`, no operator-visible error, no automatic recovery (manual `mint_grant` via `docker exec` is the only unstick path)
  - the per-action confirmation rule: when the user types "send" after a `propose_action` cooling-off, the agent MUST recognize this as confirming the existing `pending_actions` row, NOT as a fresh `propose_action` call
**And** the existing line 102 reference ("If the verb returns `requires_grant=True`, you mint a grant") is retained — it's now load-bearing rather than aspirational

**AC §4 — Unit tests on `requires_*` field population**
**Given** the verb response shape change
**When** `tests/unit/actions/test_propose_action_requires_grant_signal.py` is implemented
**Then** the tests cover (parameterized by action_type):
  - Tier-1 LOCAL actions (e.g., MARK_READ, MARK_UNREAD, ADD_LOCAL_CATEGORY): `requires_grant=False, requires_per_action_confirmation=False`
  - Tier-2 BATCH actions (e.g., ARCHIVE, MOVE_TO_USER_FOLDER, MOVE_TO_TRIAGE_FOLDER): `requires_grant=True, requires_per_action_confirmation=False`
  - Tier-3 SEND-family actions (SEND_REPLY, SEND_NEW_EMAIL, SEND_FORWARD, REPLY_TO_INACTIVE_THREAD): `requires_grant=True, requires_per_action_confirmation=True`
  - DELETE (post-7-0-prep, Tier-3 non-SEND): `requires_grant=True, requires_per_action_confirmation=False` (Tier-2/3 semantics for grant; sensitivity-token covers the destructive-touch invariant separately)

**AC §5 — F31 pragmatic guardrail (scope-reduced from original AC)**
**Original AC §5 framing:** "F31 regression test against the `find_emails` projection contract verifies that `pending_actions_pending` lookup is the canonical way the agent discovers existing cooling-off rows on a follow-up confirmation turn"
**Discovered scope-reframe:** [mailbot_api/verbs/find_emails.py](../../mailbot_api/verbs/find_emails.py) does NOT currently surface a `pending_actions_pending` projection (confirmed by grep). Adding one is a Story 5-1 amendment, out of scope here. **Pragmatic scope:** AC §5 ships as the SKILL.md documentation rule (in AC §3 above) PLUS a regression test asserting `ProposeActionOut.requires_per_action_confirmation` correctly fires `True` for the SEND-family on the FIRST `propose_action` call (the signal Hermes needs to learn the per-action-confirmation contract). Discovery-side projection added if/when the F31 contract is exercised live.

**Given** the SEND-family per-action-confirmation signal
**When** `tests/unit/actions/test_propose_action_requires_grant_signal.py::test_send_family_signals_per_action_confirmation` runs
**Then** every SEND-family `propose_action` call on a seeded sensitive (or non-sensitive) email returns `ProposeActionOut.requires_per_action_confirmation=True` AND `requires_grant=True` — the in-band signal Hermes needs to recognize the next user-turn "send" as a confirmation rather than a fresh propose

**AC §6 — Live re-walk verification (deferred to operator)**
**Given** the work is complete
**When** Story 6-6.5 is RE-walked (operator-scheduled, no Adam-side new content needed — same fixtures)
**Then** the F30 reproduction sequence (sixth-pass CP-A `router_calls.id=8685 → 8686`) is repeated; the drainer dispatches both replies without operator intervention; no `pending_grant` revert observed; no duplicate `pending_actions` row created on the "send" confirmation
**Verdict:** **Deferred to Adam-scheduled live walk** (mirrors Story 6-19 + 6-20 + 6-21 pattern from Epic 6.5 — code+tests ship; live verification lands at the next walk).

**AC §7 — MANDATORY-CR per §5.12**
**Given** the cross-story load-bearing seam (Story 4-2 ProposeActionOut + Story 6-9 dispatch_tool_call + Story 6-20 sensitivity-gate + Story 4-3/4-4 grant-state-machine)
**When** CR cadence is evaluated per the 6 criteria
**Then** criteria 4 (capstone — cross-story-collision touching ProposeActionOut consumers across Stories 4-2, 4-7, 5-2, 6-9, 6-19, 6-20) + criteria 6 (load-bearing-orchestrator — ProposeActionOut is the contract every Hermes-flow chat dispatch decodes) BOTH fire → **MANDATORY-CR per §5.12** with sonnet-4-6 reviewer

## Open Questions

None — disposition path is locked. AC §5 scope-reframe documented inline; AC §6 deferred per Epic 6.5 precedent.

## Tasks / Subtasks

- [x] AC §1 — investigate shipped vs spec; document drift in Dev Notes
- [x] AC §2 — extend `ProposeActionOut` with `requires_grant` + `requires_per_action_confirmation` fields, populate in success-path returns
- [x] AC §3 — amend SKILL.md `### propose_action` section with Tier-3 SEND flow + per-action confirmation rule
- [x] AC §4 — write parameterized unit tests in `tests/unit/actions/test_propose_action_requires_grant_signal.py`
- [x] AC §5 — pragmatic test on SEND-family `requires_per_action_confirmation=True` signal
- [x] AC §6 — deferred to Adam live walk; note in Completion Notes
- [x] AC §7 — MANDATORY-CR dispatched per §5.12

## Dev Notes

### AC §1 — Implementation history finding

The SKILL.md contract at line 102 ("If the verb returns `requires_grant=True`, you mint a grant") was aspirational documentation written ahead of the actual schema. Story 4-2's epic spec at [epics.md L1565+](../planning-artifacts/epics.md) does not require `requires_grant` / `requires_per_action_confirmation` fields on `ProposeActionOut`. Story 6-19 (F29) extended the refusal shape with `valid_action_types` but not the success shape. This story closes the contract gap by shipping the documented fields.

### Architecture choice — derive from registry, not from `propose_action` arguments

Rather than computing `requires_grant` / `requires_per_action_confirmation` from local logic in `propose_action`, this story derives both from the existing `requires_grant(action_type)` + `is_send_family(action_type)` helpers in `mailbot_api/actions/types.py`. This keeps the registry as the single source of truth and means adding a new ActionType later automatically gets correct signal-field population.

### Back-compatibility

Both fields default to `False` and exist as `bool` (non-Optional). Existing `ProposeActionOut(ok=False, ...)` refusal returns continue to construct without needing to specify the new fields — they get the safe default of `False` (no signal on failure path). Existing success-path `ProposeActionOut(ok=True, action_id=..., tier=..., status=..., error=None)` constructions get updated to populate the two new fields.

## §5.12 CR-Cadence Self-Audit

**Cadence verdict:** `MANDATORY-CR` per AC §7 — sonnet-4-6 reviewer.

Evaluation of the 6 mandatory-CR criteria:

1. **Boundary-introducing** — YES partial. `ProposeActionOut` schema gains 2 new fields; the boundary contract changes. (FIRES)
2. **External-facing / operator-facing** — YES. SKILL.md is the agent-facing contract Hermes consults; amendment changes documented behavior. (FIRES)
3. **New code in critical path** — YES partial. Every `propose_action` call now populates 2 new fields. (FIRES)
4. **Capstone / cross-story-collision** — YES. Touches consumers in Stories 4-2, 4-7, 5-2, 6-9, 6-19, 6-20 (chat_completions_tool_call decoders, MCP tool exposure, sensitivity-handshake path). (FIRES — AC §7)
5. **Privacy-invariant** — NO. No sensitivity / confidentiality semantic touched here.
6. **Load-bearing orchestrator** — YES. `ProposeActionOut` is the contract every Hermes-flow chat dispatch decodes; this is the canonical signal-expressivity layer. (FIRES — AC §7)

4 of 6 criteria fire → MANDATORY-CR.

### Posture Audit (5.1-5.12)

- **5.1 Lockfile** — N/A. No dependency changes.
- **5.2 Cross-doc** — applied. SKILL.md updated; this story file is canonical.
- **5.3 Lifecycle-string** — N/A. No status-string changes.
- **5.4 Multi-consumer** — applied. `ProposeActionOut` consumers identified across 6 stories (4-2, 4-7, 5-2, 6-9, 6-19, 6-20); all existing destructuring continues to work because the new fields are additive with safe defaults.
- **5.5 Screenshot-perception** — N/A. No graphical frontend per project memory.
- **5.6 Upstream-contract** — applied. The Pydantic `ConfigDict(frozen=True)` is preserved; `model_config` unchanged.
- **5.7 Module-mutable-state** — N/A.
- **5.8 Dev-fixture seed/production parity** — applied. Tests use real DB via `apply_pending_migrations` (no mocked DB).
- **5.9 Grep-verify-cited-figures** — applied. Helper function line numbers (`requires_grant(action_type)` at `types.py:329`, `is_send_family(action_type)` at `types.py:318`) verified via Read.
- **5.10 Producer-boundary contract** — applied. `propose_action` is the sole producer; the verb's success-return is the sole site where the new fields are populated.
- **5.11 Git-evidence consistency** — applied. Baseline `4232519`.
- **5.12 CR-cadence-mandatory surface classification** — `MANDATORY-CR` per the 4-criteria-fire evaluation above.

## Dev Agent Record

### Agent Model Used
claude-opus-4-7 (1M context) — autonomous-epic-run orchestrator, Epic 7 prep tranche.

### Completion Notes List
- AC §1 verified shipped-vs-spec drift; documented finding in Dev Notes (SKILL.md line 102 was aspirational ahead of schema).
- AC §2 extended `ProposeActionOut` with `requires_grant: bool` + `requires_per_action_confirmation: bool`, both default-False, populated from registry helpers `requires_grant(action_type)` + `is_send_family(action_type)`.
- AC §3 SKILL.md `### propose_action` gained `#### Tier-3 SEND flow` H4 subsection covering the 4 documented rules.
- AC §4 + AC §5 parameterized tests across Tier-1 / Tier-2 / Tier-3 SEND-family / DELETE.
- AC §6 deferred to Adam live walk per Epic 6.5 precedent.
- AC §7 MANDATORY-CR dispatched; findings triaged.

### File List
- `_bmad-output/implementation-artifacts/7-0-f30-f31-hermes-tier-3-send-grant-mint-flow-gap-and-duplicate-pending-actions.md` (new — this file)
- `mailbot_api/actions/propose.py` (modified — `ProposeActionOut` schema + success-return population)
- `hermes-config/skills/mailbot/SKILL.md` (modified — `### propose_action` H4 subsection added)
- `tests/unit/actions/test_propose_action_requires_grant_signal.py` (new — parameterized test file)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (modified — row flipped to `done`)

## Completion Notes

### 2026-06-13 — Story 7-0-f30-f31 DONE

Headline: F30 HIGH + F31 LOW closures shipped via `ProposeActionOut` schema extension + SKILL.md `### propose_action` H4 amendment + Tier-3 SEND flow documentation. MANDATORY-CR pass complete (sonnet-4-6 reviewer): 6 findings — 3 PATCH APPLIED (CR-1 Turn structure 3 step 3 contradiction, CR-2 preamble fictional `requires_sensitivity_token` clause, CR-6 test docstring `pending_grant` vs `pending` correction), 1 DEFER (CR-3 helper-vs-field name shadow cosmetic), 1 DISMISS (CR-4 parametrize breadth — covered by `test_types.py` registry exhaustive test), 1 DECISION-NEEDED-RESOLVED (CR-5 discovery-path gap — resolved by adding conversation-memory + `find_emails` + `read_sql` fallback discovery sentence to the new H4 subsection step 3, preserves AC §5 scope-reframe). Biggest CR catch: CR-1 + CR-2 surfaced **multi-step fictional contract in SKILL.md** — Turn structure 3 (DELETE flow) referenced `propose_action(confirmation_token=<token>)` parameter that doesn't exist on the verb signature, plus claimed `propose_action` returns `requires_sensitivity_token=True` (the field lives on the `ActionProperties` registry, not on `ProposeActionOut`). Turn structure 3 fully rewritten to reflect actual contract: `mailbot://action-types` resource for sensitivity-token discoverability + 6-step flow with separate sensitivity-token mint + grant mint + propose. Test delta: +19 (1143 → 1162). 4 gates green: ruff clean, mypy --strict clean (124 files), boundary clean, pytest 1162 + 2 skipped + 3 deselected.
