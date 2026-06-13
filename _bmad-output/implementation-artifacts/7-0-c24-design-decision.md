# Story 7-0-c24 — Design Decision: `RecoveryAction` envelope architecture

**Status:** approved (autonomous-epic-run MVP scope; full propagation via C24-FU-1..4 carry-forwards)
**Authored:** 2026-06-13 by claude-opus-4-7

## 1. Problem statement

Hermes (the operator-facing Discord agent) consumes mailbot-api responses across many surfaces: verb errors, router refusals, propose_action returns, terminal action states, mint operations. Across Epic 6.5's sixth-pass walk we observed a consistent failure-class: **when a response carries terminal state (refused / blocked / requires-next-action), Hermes has to INFER the recovery path from SKILL.md + AGENTS.md + SOUL.md + main-inference Haiku's training prior**. Inference works most of the time. When it fails, the failures are non-obvious because the agent stays plausible (drafts a reply that looks reasonable, picks an action_type that looks reasonable, gives up at a stall point that looks reasonable).

Concrete F-finding evidence:

- **F29 (Story 6-19):** Hermes hallucinated `action_type='SEND_EMAIL'` instead of canonical `send_reply`; verb refused with INVALID_ACTION_TYPE; no in-band recovery hint until Story 6-19 added `valid_action_types: tuple[str, ...] | None` as a special-case field.
- **F30 (Story 7-0-f30-f31):** Hermes called `propose_action(send_reply)` correctly, drainer reverted to `pending_grant` because no grant existed, Hermes never knew to `mint_grant`; operator manually unstuck via `docker exec`. Story 7-0-f30-f31 added bare booleans `requires_grant` + `requires_per_action_confirmation` as in-band signals.
- **F31 (Story 7-0-f30-f31):** Hermes treated user's "send" as fresh propose, duplicate `pending_actions` rows resulted.
- **CP-C tone-drift sub-finding:** Hermes drafted reply in main-inference Haiku tone rather than user-mimic tone; no in-band hint to call `tone_style_mirror` before `draft_reply`.
- **CP-B mint-then-stall:** Hermes minted sensitivity-token but didn't follow through with the dispatch turn; the verb's success-return carried no "next step is to call ask_router with the token" signal.

The **shape of the fix is consistent**: every refusal/blocked/terminal response should carry a `recovery_action` structured envelope. Hermes parses it; the agent acts on it; no inference required.

## 2. Envelope shape

```python
class RecoveryAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str | None = None
    args_hint: dict[str, Any] = Field(default_factory=dict)
    user_facing_guidance: str | None = None
```

**Field rationale:**

- **`tool_name`** — the verb / MCP tool / Router task_type the agent SHOULD call next. `None` when the recovery path is "ask the user" (no machine-driven next-call). Examples: `"mint_grant"`, `"mint_sensitivity_token"`, `"propose_action"`, `"list_resources"`, `"ask_router"`.
- **`args_hint`** — opaque-to-the-envelope keyword arguments the agent should interpolate into the next call. Stored as `dict[str, Any]` because the Pydantic model can't statically type the union of every possible verb's parameter set. Documented per-surface in SKILL.md + AGENTS.md.
- **`user_facing_guidance`** — canonical wording for the agent to relay in chat IF the recovery path requires user input (e.g., "ask the user to type `/confirm <id>`"). `None` when the agent can auto-recover without user-visible explanation.

## 3. Enumerated surfaces (full propagation target)

| Surface | Refusal/terminal trigger | `tool_name` | `args_hint` template | `user_facing_guidance` | Story shipping it |
|---|---|---|---|---|---|
| `ProposeActionError.INVALID_ACTION_TYPE` | unknown action_type string | `"propose_action"` | `{"action_type": "<one of valid_action_types>"}` | `None` (silent self-correct) | **7-0-c24 (this story)** |
| `ProposeActionOut.success + requires_grant=True` | Tier-2/3 propose | `"mint_grant"` | `{"action_type": <value>, "email_ids": [<id>], "ttl_seconds": 60}` (CR-2 relative TTL) | `None` (silent next-call) | **7-0-c24 (this story)** |
| `ProposeActionError.SENSITIVITY_NOT_CLASSIFIED` | email row missing sensitivity_at | `None` | `{}` | "the email hasn't been classified yet; please wait for the ingest pipeline to catch up" | C24-FU-1 (HydrateEmailError + ProposeActionError sensitivity branch) |
| `ProposeActionError.SENSITIVITY_BLOCKS_API` | sensitive content + no token | `"mint_sensitivity_token"` | `{"email_id": <id>, "task_type": <intent>}` | "I need to confirm before processing sensitive content; please type `/confirm <email_id>`" | C24-FU-1 |
| `ProposeActionError.GRANT_REQUIRED` (future) | propose attempted without grant | `"mint_grant"` | `{"action_type": <value>, "email_ids": [<id>], "expires_at": "<ISO>"}` | `None` | C24-FU-1 (if/when GRANT_REQUIRED becomes a propose-time refusal) |
| `ProposeActionError.BUDGET_CAP_HIT` (future) | per-call refusal threshold | `None` | `{}` | "the budget cap has been reached for this operation" | C24-FU-1 |
| `HydrateEmailError.CONFIDENTIAL_HYDRATION_BLOCKED` | confidential email hydrate refused | `None` | `{}` | "confidential emails cannot be hydrated; the body is not exposed to the agent" | C24-FU-1 |
| `RouterRefusal.SENSITIVITY_BLOCKS_API` | ask_router refused for sensitive | `"mint_sensitivity_token"` | `{"email_id": <id>, "task_type": <task>}` | (canonical wording per persona) | C24-FU-2 |
| `RouterRefusal.DEGRADED_MODE` | degraded mode (Story 2-8) | `None` | `{}` | "operating in degraded mode; some operations are unavailable" | C24-FU-2 |
| `RouterRefusal.PAUSED` | manual /pause | `None` | `{}` | "the router is paused; resume with `/resume` to continue" | C24-FU-2 |
| `pending_actions.terminal_reason='pending_grant_reverted'` | drainer reverted (Story 6-13 F22) | `"mint_grant"` | `{"action_type": <value>, "email_ids": [<id>], "expires_at": "<ISO>"}` | `None` (silent re-mint) | C24-FU-3 |
| `pending_actions.terminal_reason='budget_cap_hit'` | drainer hit per-call refusal | `None` | `{}` | "budget cap was hit; the action will retry tomorrow" | C24-FU-3 |
| `pending_actions.terminal_reason='expired'` | grant expired before drain | `"mint_grant"` | `{"action_type": <value>, "email_ids": [<id>], "expires_at": "<ISO>"}` | `None` | C24-FU-3 |
| `MintSensitivityTokenOut.success` | token minted | `"ask_router"` | `{"task_type": <task>, "email_id": <id>, "confirmation_token": <value>}` | (canonical wording per persona) | C24-FU-4 |

**MVP propagation (this story — 7-0-c24):** rows 1 + 2.
**Carry-forward propagation:** rows 3-14 across C24-FU-1..4.

## 4. Back-compatible expansion convention

**Convention statement:** when promoting a bare boolean or special-case field (e.g., `valid_action_types`, `requires_grant`) to a structured `recovery_action` envelope, **retain the original field for one full epic** to give Hermes-side consumers time to migrate.

Concrete invocation for this story:

- **Story 6-19's `valid_action_types: tuple[str, ...] | None` on `ProposeActionError`** — RETAINED. The new `recovery_action` envelope is ADDED alongside it; both are populated on the INVALID_ACTION_TYPE path. Deprecation timing: drop no earlier than Epic 8.
- **Story 7-0-f30-f31's `requires_grant: bool` + `requires_per_action_confirmation: bool` on `ProposeActionOut`** — RETAINED. The new `recovery_action: RecoveryAction | None = None` field is ADDED alongside them; populated when `requires_grant=True`. Deprecation timing: drop no earlier than Epic 8.

The convention also implies: Hermes-side code that ONLY consumes the legacy fields (e.g., reads `valid_action_types` directly) continues to work without modification. New Hermes-side code SHOULD prefer the structured envelope (consistent shape across all surfaces).

## 5. MVP vs full-propagation scope-cleave decision

Within the autonomous-epic-run loop, the orchestrator elected the MVP path: ship the architectural foundation + 2 high-traffic proof-out cases + cross-doc + back-compat convention, then file the remaining ~8 surfaces as named carry-forward stories (C24-FU-1..4). Rationale:

1. **Context budget** — propagation across ~15 files would consume the run's remaining budget, blocking the MANDATORY-CR dispatch needed to validate the architectural shape.
2. **CR risk hedge** — getting the envelope SHAPE wrong is the load-bearing risk. Once the shape is reviewed against 2 concrete cases (this story), the carry-forward stories can be mechanical ports.
3. **Honest re-scope** — per the Disposition-Story Pattern documented in autonomous-epic-run skill, MVP scope with named carry-forwards preserves audit-trail integrity and avoids half-finished propagation.

Adam decides at next session whether C24-FU-1..4 ship under Epic 7 (Production Calibration) or merge into Epic 9 sequencing.

## 6. Live-walk verification deferral

AC §9 defers the live walk to Adam-scheduled operator time (mirrors Epic 6.5 carry-forward pattern). The walk will exercise the 2 MVP surfaces against Hermes's main-inference Haiku to confirm: (a) Hermes self-corrects on INVALID_ACTION_TYPE via the envelope without operator intervention; (b) Hermes calls `mint_grant` automatically after a Tier-3 SEND propose returns `recovery_action.tool_name="mint_grant"`. Walk evidence captured in epic-7-run-flags.md per project convention.

## 7. MANDATORY-CR cadence per §5.12

4 of 6 criteria fire (boundary-introducing + external-facing + critical-path-partial + cross-story-collision + load-bearing-orchestrator). Privacy-invariant criterion (5) does NOT fire in MVP (sensitivity-handshake surfaces scope-cleaved to C24-FU-1+2+4). MANDATORY-CR dispatched against sonnet-4-6 reviewer.
