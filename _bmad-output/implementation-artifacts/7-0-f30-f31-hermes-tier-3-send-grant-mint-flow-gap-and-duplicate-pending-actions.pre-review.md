# Pre-Review Self-Audit — 7-0-f30-f31

**Generated:** 2026-06-13 by claude-opus-4-7
**Story file:** _bmad-output/implementation-artifacts/7-0-f30-f31-hermes-tier-3-send-grant-mint-flow-gap-and-duplicate-pending-actions.md
**Status at audit time:** review (post dev-story, pre code-review)

## 1. AC-vs-code drift scan

- AC §1 (investigation finding): MATCH — Dev Notes documents Story 4-2 vs SKILL.md drift; SKILL.md line 102 was aspirational ahead of schema, story closes the gap.
- AC §2 (ProposeActionOut schema extension): MATCH — `requires_grant: bool = False` + `requires_per_action_confirmation: bool = False` added (propose.py:96-97); success-return populated via `requires_grant(action_type)` + `is_send_family(action_type)` registry helpers at propose.py:291-292.
- AC §3 (SKILL.md amendment): MATCH — new H4 subsection `#### Tier-3 SEND flow` added between `#### Canonical action_type values` and `### mint_grant`; covers the 4 documented rules (flow, mint_grant timing, failure mode, per-action confirmation distinction from Tier-2 BATCH).
- AC §4 (parameterized unit tests on signal-field population): MATCH — 19 tests across Tier-1/Tier-2/Tier-3 SEND-family/Tier-3 admin/DELETE/refusal paths.
- AC §5 (F31 pragmatic guardrail): MATCH — scope-reframe documented inline; SEND-family confirmation signal test ships as the in-band recovery contract.
- AC §6 (live re-walk): MATCH — deferred per Epic 6.5 precedent.
- AC §7 (MANDATORY-CR per §5.12): MATCH (in progress — this artifact is the gate; CR dispatch follows).

## 2. File-List-vs-git diff check

`git status --porcelain` cross-reference against story File List:

- `_bmad-output/implementation-artifacts/7-0-f30-f31-...md` — TRACKED (Added, staged at Story 7-0-f30-f31 done-gate)
- `mailbot_api/actions/propose.py` — MODIFIED-NOT-STAGED (will stage at done-gate)
- `hermes-config/skills/mailbot/SKILL.md` — MODIFIED-NOT-STAGED (will stage at done-gate)
- `tests/unit/actions/test_propose_action_requires_grant_signal.py` — UNTRACKED (will stage at done-gate)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — MODIFIED-NOT-STAGED (will flip row at done-gate, then stage)

All paths will be explicitly `git add`'d at Step 2.6 selective staging.

## 3. Adversarial self-review

- [LOW] propose.py:96-97 — the new fields are bare `bool` with no `Field(description=...)`. Pydantic field docstrings don't propagate to FastMCP tool schemas the way Field descriptions do (Story 5-2 contract). The agent reading the MCP tool surface won't see in-band documentation of `requires_grant` / `requires_per_action_confirmation` semantics. Mitigation: SKILL.md's new H4 subsection IS the agent-facing doc — but a Field description would also help any future MCP-tool-schema consumer.
- [MEDIUM] propose.py:283-301 — the `# Story 7-0-f30-f31:` comment block explains the populate-from-registry choice but doesn't cite the F30/F31 failure modes. A reviewer auditing this code path 3 months from now should be able to see WHY the field-derivation choice was made, not just WHAT it does.
- [LOW] test file's `test_send_new_email_email_less_path_signals_per_action_confirmation` — the test seeds no email and relies on the EMAIL_LESS_ACTIONS membership for SEND_NEW_EMAIL. If a future refactor removes SEND_NEW_EMAIL from EMAIL_LESS_ACTIONS without updating this test, the test would fail with a misleading EMAIL_NOT_FOUND error. Mitigation: document the EMAIL_LESS_ACTIONS dependency in the test docstring (already partially done; could be sharper).
- [LOW] SKILL.md H4 — the "F31 failure mode" framing in the per-action-confirmation rule says "do NOT issue a fresh `propose_action` call" but doesn't tell the agent HOW to discover the existing pending row. AC §5 acknowledged that `find_emails` doesn't currently surface `pending_actions_pending` — but the SKILL.md text doesn't redirect to the actual discovery path (e.g., look at the most recent `propose_action` return in your conversation memory). This is a UX gap for the agent.
- [MEDIUM] test file lacks a counter-test for `test_send_family_signals_per_action_confirmation` proving that switching to a non-SEND Tier-3 (DELETE / MODIFY_INBOX_RULE) flips `requires_per_action_confirmation` to False. The `test_delete_grant_yes_confirmation_no` test does this for DELETE, so the counter-coverage is present — but it would be sharper as an explicit parametrize on the SEND vs non-SEND boundary.

## 4. Self-caught issues remediated this audit

- [LOW] Field description gap (issue 1): **ACCEPT WITH RATIONALE** — SKILL.md is the canonical agent-facing doc per Story 5-5's persona-architecture; FastMCP propagation gap is a Story 5-2 contract concern best addressed in a future polish-pass. The reviewer (sonnet-4-6) will catch this if it's load-bearing.
- [MEDIUM] Comment block citing F30/F31 (issue 2): **FIX NOW** — add a 1-line citation of F30 + F31 in the comment block.
- [LOW] EMAIL_LESS_ACTIONS dependency in test (issue 3): **ACCEPT WITH RATIONALE** — test already has informative assertion failure message; refactor risk is low (Story 4-2 CR-1 baked SEND_NEW_EMAIL into EMAIL_LESS_ACTIONS).
- [LOW] SKILL.md discovery path gap (issue 4): **ESCALATE TO REVIEWER** — the discovery-path gap IS the F31 contract surface that AC §5 scope-reframed away from; the reviewer should decide whether the SKILL.md text needs to be sharper.
- [MEDIUM] SEND vs non-SEND boundary parametrize (issue 5): **ACCEPT WITH RATIONALE** — counter-coverage via DELETE + Tier-3 admin tests is sufficient for this story; tighter boundary test is polish.

## 5. Posture Audit

- **5.1 Lockfile** — N/A. No dependency changes.
- **5.2 Cross-doc** — applied. Verified by grep: `requires_grant=True` mention now refers to a real Python field, not aspirational documentation. SKILL.md amendment lands at hermes-config/skills/mailbot/SKILL.md line 121+.
- **5.3 Lifecycle-string** — N/A.
- **5.4 Multi-consumer** — applied. Existing `ProposeActionOut` consumers identified via grep: `mailbot_api/actions/propose.py:78` (definition), `mailbot_api/verbs/propose_action.py` (verb shim), `tests/unit/actions/test_propose_action.py` (8+ tests). All existing consumers destructure only the previously-existing fields; the new fields' default-False makes the schema change purely additive.
- **5.5 Screenshot-perception** — N/A. No graphical frontend.
- **5.6 Upstream-contract** — applied. `model_config = ConfigDict(frozen=True)` preserved; pydantic v2 BaseModel constructor accepts the additive fields without breaking change.
- **5.7 Module-mutable-state** — N/A.
- **5.8 Dev-fixture seed/production parity** — applied. Tests use real on-disk SQLite via `apply_pending_migrations(db_path)`; the `_seed_email` helper mirrors `test_propose_action.py:26-40` exactly.
- **5.9 Grep-verify-cited-figures** — applied. `requires_grant(action_type)` confirmed at types.py:329; `is_send_family(action_type)` confirmed at types.py:318. Verified via Read.
- **5.10 Producer-boundary contract** — applied. `propose_action` is the sole producer of `ProposeActionOut(ok=True, ...)` via the explicit return at propose.py:283-301. No other call sites construct success-return values.
- **5.11 Git-evidence consistency** — applied. Baseline `4232519`; staged after Story 7-0-prep commit-equivalent (no commit yet, but selective staging shows 7-0-prep's 4 files + 7-0-f30-f31's 4 files).
- **5.12 CR-cadence-mandatory surface classification** — `MANDATORY-CR` per the 4-of-6-criteria evaluation in story file §5.12 (Boundary-introducing + External-facing + Critical-path + Cross-story-collision + Load-bearing-orchestrator FIRE; only Privacy-invariant doesn't fire — but that's the criterion that mattered most for Epic 6.5's F28 surface, not this one).

**Cadence verdict: MANDATORY-CR**

## Posture Audit Summary

| Check | Verdict |
|---|---|
| 5.1 Lockfile | N/A |
| 5.2 Cross-doc | applied |
| 5.3 Lifecycle-string | N/A |
| 5.4 Multi-consumer | applied |
| 5.5 Screenshot-perception | N/A |
| 5.6 Upstream-contract | applied |
| 5.7 Module-mutable-state | N/A |
| 5.8 Dev-fixture seed/production parity | applied |
| 5.9 Grep-verify-cited-figures | applied |
| 5.10 Producer-boundary contract | applied |
| 5.11 Git-evidence consistency | applied |
| 5.12 CR-cadence verdict | **MANDATORY-CR** |
