# Pre-Review Self-Audit — 7-0-c24

**Generated:** 2026-06-13 by claude-opus-4-7
**Story file:** _bmad-output/implementation-artifacts/7-0-c24-hermes-flow-signal-expressivity-architecture.md
**Status at audit time:** review (post dev-story, pre code-review)

## 1. AC-vs-code drift scan

- AC §1 (design document): MATCH — `7-0-c24-design-decision.md` shipped with 7 sections including full 14-row surface enumeration + envelope shape + back-compat convention + MVP scope-cleave decision.
- AC §2 (RecoveryAction Pydantic shape): MATCH — `mailbot_api/actions/recovery_action.py` with frozen `ConfigDict` + 3 fields + Field descriptions; re-exported via `mailbot_api/actions/__init__.py`.
- AC §3 (ProposeActionError.INVALID_ACTION_TYPE envelope migration): MATCH — `mailbot_api/actions/propose.py:78-81` adds `recovery_action: RecoveryAction | None = None`; `mailbot_api/verbs/propose_action.py` populates the envelope on the INVALID_ACTION_TYPE refusal arm WHILE retaining `valid_action_types`.
- AC §4 (ProposeActionOut.success-return envelope): MATCH — `mailbot_api/actions/propose.py:96-102` adds the field; success-return populates when `requires_grant(action_type)=True` with mint_grant template + email_ids + 60s expires_at ISO timestamp.
- AC §5 (SKILL.md + AGENTS.md): MATCH — new `## Recovery Actions` section in SKILL.md (before `## End-to-end turn structures`) + new `## Rule S` in AGENTS.md (before the tiebreaker); tiebreaker reference updated `R` → `R / S`.
- AC §6 (back-compat convention): MATCH — design doc §4 documents the convention; both `valid_action_types` and `requires_grant`/`requires_per_action_confirmation` retained alongside the new envelope.
- AC §7 (integration tests): MATCH — `tests/integration/test_recovery_action_envelope_coverage.py` ships 5 tests; all pass.
- AC §8 (carry-forward stories): MATCH — `epic-7-run-flags.md` created with C24-FU-1 / C24-FU-2 / C24-FU-3 / C24-FU-4 named follow-ups.
- AC §9 (live re-walk): MATCH — explicitly deferred to Adam-scheduled walk per Epic 6.5 precedent.
- AC §10 (MANDATORY-CR per §5.12): MATCH (in progress — this artifact gates the dispatch).

## 2. File-List-vs-git diff check

Per `git status --porcelain`:

- `_bmad-output/implementation-artifacts/7-0-c24-hermes-flow-signal-expressivity-architecture.md` — UNTRACKED (will stage)
- `_bmad-output/implementation-artifacts/7-0-c24-design-decision.md` — UNTRACKED (will stage)
- `_bmad-output/implementation-artifacts/epic-7-run-flags.md` — UNTRACKED (will stage)
- `mailbot_api/actions/recovery_action.py` — UNTRACKED (will stage)
- `mailbot_api/actions/__init__.py` — MODIFIED-NOT-STAGED (will stage)
- `mailbot_api/actions/propose.py` — MODIFIED-NOT-STAGED (will stage; carries this story's edits ON TOP OF Story 7-0-f30-f31's edits which were staged at f30-f31's done-gate)
- `mailbot_api/verbs/propose_action.py` — MODIFIED-NOT-STAGED (will stage)
- `hermes-config/skills/mailbot/SKILL.md` — MODIFIED-NOT-STAGED (will stage; carries this story's edits ON TOP OF 7-0-f30-f31's edits already staged)
- `hermes-config/AGENTS.md` — MODIFIED-NOT-STAGED (will stage)
- `tests/integration/test_recovery_action_envelope_coverage.py` — UNTRACKED (will stage)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — MODIFIED-NOT-STAGED (will flip row + stage at done-gate)

All paths will be explicitly `git add`'d at Step 2.6.

## 3. Adversarial self-review

- [MEDIUM] `args_hint` carries a placeholder string `"<one of valid_action_types>"` for INVALID_ACTION_TYPE — this is a SENTINEL, not a real value. If a Hermes-side consumer naively interpolates `args_hint["action_type"]` as the next `propose_action` argument, the verb will reject the literal string `"<one of valid_action_types>"` (it's not a canonical enum value). The agent MUST consult the parallel `valid_action_types` tuple. SKILL.md documents this — but the structural risk is that the envelope LOOKS like it's enough on its own.
- [LOW] `expires_at` in the GRANT_REQUIRED args_hint is computed at propose-time. If the agent delays calling `mint_grant` significantly (slow conversation flow), the hint will already be in the past by the time it's used. The hint is documented as a HINT not a contract, but the failure mode if Hermes treats it as a contract is: `mint_grant` accepts the past timestamp and the grant is immediately invalid. Risk-mitigation: SKILL.md says "Hermes can pass a longer or shorter expiration to mint_grant" — but new code might not read that.
- [LOW] `email_ids: []` for email-less Tier-3 admin actions (MODIFY_INBOX_RULE / MODIFY_OUTLOOK_FILTER / TOUCH_DELEGATED_MAILBOX) — these are valid Tier-3 propose calls per Story 4-2's email-less branch. The envelope's args_hint sends an empty list. Need to confirm Hermes-side `mint_grant` accepts empty `email_ids` for these admin actions (should it? the grant doesn't bind to a specific email). The test parametrize for email-less Tier-3 in `test_propose_action_requires_grant_signal.py` asserts `requires_grant=True` but doesn't assert envelope shape — gap in MVP coverage.
- [MEDIUM] AC §7's 5-test coverage doesn't include an email-less Tier-3 admin envelope test (caught by issue 3 above). Missing test would assert `recovery_action.args_hint["email_ids"] == []` for `MODIFY_INBOX_RULE` etc. This is an MVP completeness gap.
- [LOW] AGENTS.md Rule S says "your next call should match `recovery_action.tool_name` with `recovery_action.args_hint` interpolated as keyword arguments" — but doesn't address the case where `tool_name=None` but `args_hint` is non-empty (rare; design doc doesn't enumerate such a case explicitly). The Rule could be sharper: when `tool_name=None`, IGNORE args_hint and follow user_facing_guidance only.
- [LOW] `mailbot_api/actions/__init__.py` re-exports `RecoveryAction` but doesn't re-export `ProposeActionError` or `ProposeActionOut` (those have always been imported via `mailbot_api.actions.propose`). Inconsistent module surface — defensible per existing convention (actions package level re-exports types only; propose-specific shapes stay one level deeper). No code change.

## 4. Self-caught issues remediated this audit

- [MEDIUM] `args_hint` placeholder sentinel risk (issue 1): **ACCEPT WITH RATIONALE** — SKILL.md `## Recovery Actions` section explicitly documents "consult the parallel `valid_action_types` list" for INVALID_ACTION_TYPE; the structural risk is mitigated by documentation. The reviewer should flag if this is insufficient.
- [LOW] `expires_at` time-of-flight risk (issue 2): **ESCALATE TO REVIEWER** — the hint contract is fundamentally racy; an alternate design is "envelope carries TTL in seconds" so consumers re-compute. Trade-off worth a CR opinion.
- [LOW] email-less admin args_hint empty email_ids (issue 3): **ACCEPT WITH RATIONALE** — `mint_grant`'s contract accepts empty email_ids for admin actions per Story 4-3; the envelope correctly emits empty list. Test gap covered next.
- [MEDIUM] MVP test coverage gap on email-less Tier-3 admin (issue 4): **FIX NOW** — add a 6th test to `test_recovery_action_envelope_coverage.py` covering `MODIFY_INBOX_RULE` → `args_hint.email_ids == []`.
- [LOW] AGENTS.md Rule S unclear `tool_name=None + args_hint != {}` case (issue 5): **DEFER** — design doc explicitly enumerates the use cases; not a Story 7-0-c24 MVP gap.
- [LOW] `mailbot_api/actions/__init__.py` re-export inconsistency (issue 6): **DISMISS** — pre-existing convention.

## 5. Posture Audit

- **5.1 Lockfile** — N/A. No dependency changes.
- **5.2 Cross-doc** — applied. SKILL.md + AGENTS.md updated; design doc + epic-7-run-flags.md authored; this story file is canonical.
- **5.3 Lifecycle-string** — N/A.
- **5.4 Multi-consumer** — applied. `ProposeActionError` consumers (Stories 4-2, 6-19) read `code` + `message` + `valid_action_types`; new envelope field is additive (None default) — no breaking change. `ProposeActionOut` consumers (Stories 4-2, 5-2, 6-9, 6-19, 7-0-f30-f31) read existing fields + booleans; new envelope is additive.
- **5.5 Screenshot-perception** — N/A.
- **5.6 Upstream-contract** — applied. `model_config = ConfigDict(frozen=True)` preserved on `RecoveryAction` and the modified models; Pydantic v2 accepts additive optional fields under frozen contracts.
- **5.7 Module-mutable-state** — N/A.
- **5.8 Dev-fixture seed/production parity** — applied. Tests use real on-disk SQLite via `apply_pending_migrations`; seed helper mirrors `test_propose_action_requires_grant_signal.py`.
- **5.9 Grep-verify-cited-figures** — applied. `_VALID_ACTION_TYPES` at `mailbot_api/verbs/propose_action.py:39` verified via Read. `requires_grant(action_type)` at `types.py:329` verified.
- **5.10 Producer-boundary contract** — applied. INVALID_ACTION_TYPE envelope built at exactly one site (verb shim); success-return envelope built at exactly one site (actions/propose.py).
- **5.11 Git-evidence consistency** — applied. Baseline `4232519`; this story builds on Stories 7-0-prep (staged) + 7-0-f30-f31 (staged).
- **5.12 CR-cadence-mandatory surface classification** — `MANDATORY-CR` per story file §5.12 (4-of-6 criteria fire: boundary-introducing + external-facing + critical-path-partial + cross-story-collision + load-bearing-orchestrator).

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
