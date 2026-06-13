# Epic 7 — Run Flags

**Created:** 2026-06-13 during autonomous-epic-run of Epic 7 prep tranche (Stories 7-0-prep + 7-0-f30-f31 + 7-0-c24). This file aggregates carry-forward debt for Epic 7's main tranche (Stories 7-5/7-6/7-7) and downstream propagation tasks.

## Autonomous-epic-run summary (Epic 7 prep tranche)

**Run date:** 2026-06-13
**Orchestrator:** claude-opus-4-7 (1M context)
**Code-review subagent:** claude-sonnet-4-6 (used for Stories 7-0-f30-f31 + 7-0-c24)
**Run status:** **COMPLETE** — all 3 prep-tranche stories `done`. **Epic 7's main tranche (Stories 7-5/7-6/7-7) NOT run** — those hard-depend on Epic 9 (Manual Model Control & Benchmark Harness) per the 2026-06-07 scope cleave. **Epic 9 is the next legitimate autonomous-run target.**

### Per-story summary

| Story | Status | Tests added (net) | CR cadence | CR issues found | CR issues applied | Applied rate | Notes |
| ----- | ------ | ----------------- | ---------- | --------------- | ----------------- | ------------ | ----- |
| 7-0-prep | done | +3 | §5.12 self-audit (GATE-COVERAGE-ELIGIBLE) | N/A | N/A | N/A | Disposition close (superseded-by-e4dac69 from 2026-06-02); docs-trail + AC §3 smoke test still shipped |
| 7-0-f30-f31 | done | +19 | MANDATORY-CR (sonnet-4-6) | 6 | 3 PATCH applied + 1 DECISION-NEEDED resolved + 1 DEFER + 1 DISMISS | 100% (3/3 actionable) | Biggest catch: CR-1 + CR-2 surfaced multi-step fictional SKILL.md contract (Turn structure 3 DELETE flow referenced `propose_action(confirmation_token=...)` parameter that doesn't exist on the verb signature) — fully rewritten to match reality |
| 7-0-c24 | done | +6 | MANDATORY-CR (sonnet-4-6) | 7 | 3 PATCH applied + 1 DECISION-NEEDED resolved + 3 DEFER | 100% (3/3 actionable) | MVP scope-cleave (β over α): architectural foundation + 2 high-traffic surfaces; 4 named follow-ups (C24-FU-1..4 below). Biggest catch: CR-1 placeholder-sentinel infinite-loop risk + CR-2 expires_at race condition; both fixed inline |

**Total tranche test delta:** **+28 net** (1140 → 1168 + 2 skipped + 3 deselected).
**MANDATORY-CR apply rate:** 6/6 actionable applied = **100%** across both CR-dispatched stories (continues 5-epic streak).

## Story 7-0-c24 carry-forward stories — `RecoveryAction` envelope propagation

Story 7-0-c24 shipped the MVP architectural envelope + propagation to 2 high-traffic surfaces (INVALID_ACTION_TYPE recovery via Story 6-19 valid_action_types migration + GRANT_REQUIRED next-call hint via Story 7-0-f30-f31 requires_grant boolean). The remaining ~8 surfaces are named carry-forwards:

### C24-FU-1 — `ProposeActionError` + `HydrateEmailError` envelope propagation

**Scope:** populate `recovery_action: RecoveryAction | None` on the remaining `ProposeActionError` codes (SENSITIVITY_NOT_CLASSIFIED, SENSITIVITY_BLOCKS_API, GRANT_REQUIRED-when-it-becomes-a-propose-time-refusal, BUDGET_CAP_HIT) and on `HydrateEmailError.CONFIDENTIAL_HYDRATION_BLOCKED`. Per-surface tool_name + args_hint templates documented in `7-0-c24-design-decision.md` §3.

**Criticality:** MEDIUM. Sensitivity-handshake surfaces are privacy-invariant; CR criterion 5 will fire on this story. Adam decides whether this lands under Epic 7 or merges into Epic 9.

### C24-FU-2 — Router refusal envelope propagation

**Scope:** populate the envelope on the 3 Router refusal codes (SENSITIVITY_BLOCKS_API, DEGRADED_MODE, PAUSED) at the `ask_router` precondition layer. Touches `mailbot_api/router/router.py` and `mailbot_api/router/errors.py`. Per-surface templates in design doc §3.

**Criticality:** MEDIUM. SENSITIVITY_BLOCKS_API is the canonical sensitive-content refusal path; F28's reproduction surface in Epic 6.5. CR criterion 5 will fire.

### C24-FU-3 — Terminal action-state envelope propagation

**Scope:** add a new `recovery_action_json: TEXT NULL` column to `pending_actions` (or expose via a SELECT projection at drainer terminate time) carrying the envelope for `terminal_reason='pending_grant_reverted'` / `'budget_cap_hit'` / `'expired'`. Touches the drainer (Story 4-4) + the action-history query surface (Story 6-1's status board).

**Criticality:** LOW. Terminal-state visibility is already populated via `notification` rows + status board; this is signal-expressivity sharpening.

### C24-FU-4 — `MintSensitivityTokenOut` envelope propagation

**Scope:** populate the envelope on the `MintSensitivityTokenOut(ok=True)` success path with `tool_name="ask_router"` + `args_hint={"task_type": ..., "email_id": ..., "confirmation_token": ...}` so Hermes has the structured next-call shape for "you minted a token; now dispatch the actual task".

**Criticality:** LOW. The mint→ask_router pattern is documented in SKILL.md's Turn structures; this is signal-expressivity sharpening.

### Sequencing notes

- All 4 follow-ups are mechanical ports once the envelope SHAPE is validated by Story 7-0-c24's MANDATORY-CR.
- Recommended sequencing: C24-FU-1 → C24-FU-2 → C24-FU-3 → C24-FU-4 (privacy-invariant surfaces first; cosmetic-sharpening surfaces last).
- Adam-decision: merge into Epic 7 main tranche, defer to Epic 8, or relocate to Epic 9 sequencing.

## Story 7-0-prep + 7-0-f30-f31 carry-forwards

No new carry-forwards filed from those two stories (both shipped clean per their MANDATORY-CR or §5.12 self-audit cadence). 7-0-f30-f31's MANDATORY-CR surfaced 3 PATCH-applied findings (CR-1+CR-2+CR-6) and 1 DECISION-NEEDED that was resolved inline (CR-5 — SKILL.md discovery-path fallback sentence).

## Self-grading scorecard

```text
☑ A1 — UI scope check passed for every story (N/A — no graphical frontend per PORTING.md)
☑ A2 — end-of-epic dev-env verification — N/A (no <dev-env-skill> configured for MailBot)
☑ A4 — epic-7-run-flags.md exists with all deferred-items aggregated (this file)
☑ A5 — issues-found-vs-applied tracked: 6/6 actionable = 100% across both CR-dispatched stories (≥70% target met)
☑ A7 — UX advisory invoked — N/A (no graphical frontend)
☑ B1 — File-List-vs-git gate passed cleanly for every story
☐ B2 — Phase 3.5 manual-verification gate: N/A for backend-only tranche; live-walk verification deferred to next Story 6-6.5 re-walk per Epic 6.5 precedent (Adam-scheduled)
```

## Outstanding Adam-decisions surfaced

1. **C24-FU-1..4 sequencing** — merge into Epic 7 main tranche, defer to Epic 8, or relocate to Epic 9? (Story 7-0-c24 design doc §5 scope-cleave.)
2. **`expires_at` → `ttl_seconds` envelope contract migration** — applies retroactively to Story 4-3 `mint_grant` consumers if/when they read the envelope's `args_hint.ttl_seconds` instead of computing absolute timestamps. No code change today; documented for the Hermes-side migration.
3. **SKILL.md Turn structure 3 (DELETE flow) rewrite verification** — the 6-step flow rewritten by Story 7-0-f30-f31 CR-1/CR-2 should be verified against Hermes's actual main-inference Haiku behavior at the next Story 6-6.5 re-walk. The original 7-step flow contained fictional `propose_action(confirmation_token=...)` parameter calls; the rewrite eliminates those but the operator should confirm Hermes self-corrects on the corrected flow.
