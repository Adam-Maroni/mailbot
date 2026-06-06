---
name: 6-20 pre-review self-audit
description: Step 2.3.5 gate artifact for Story 6-20 (F28 closure)
type: pre-review
---

# Pre-Review Self-Audit — 6-20

**Generated:** 2026-06-06 by claude-opus-4-7 (autonomous-epic-run pickup)
**Story file:** `_bmad-output/implementation-artifacts/6-20-sensitivity-token-handshake-gate-relocation-to-dispatch-tool-call-f28-closure.md`
**Status at audit time:** review (post dev-story, pre code-review)

## 1. AC-vs-code drift scan

For each AC: verdict + evidence.

- **AC-1 (email-id resolver helper):** **MATCH.** Implemented `_resolve_email_ids_from_messages(messages) -> set[str]` at [mailbot_api/router/router.py:1053-1138](../../mailbot_api/router/router.py#L1053-L1138). Pure function (no DB I/O). Walks (a) `assistant.tool_calls[].function.arguments` (both dict and Pydantic-model shapes via `.get`/`getattr` polyfill), (b) `tool`-role `content`. Recursive `_walk` traverses dicts + lists at any nesting depth. Dedupes via `set`. Malformed JSON → silently skipped + DEBUG log with `event="dispatch_tool_call.arg_parse_failed"`. All 5 resolver unit tests in AC-5.1–5.5 green.
- **AC-2 (multi-id gate firing):** **MATCH.** `dispatch_tool_call` precondition extended at [mailbot_api/router/router.py:1288-1442](../../mailbot_api/router/router.py#L1288-L1442) (replacing the legacy single-id path). Builds `_audit_ids = ({param_email_id} if email_id else ∅) ∪ _resolve_email_ids_from_messages(messages)`. Iterates `sorted(_audit_ids)` for determinism. 3-state logic: NOT_CLASSIFIED / CONFIDENTIAL (unconditional) / SENSITIVE (with single-token consume against first sensitive id in sorted order; subsequent sensitive ids fall through to BLOCKS_API). Multi-id messages include `eid` substring; single-legacy-id messages preserve historical wording.
- **AC-3 (audit row carries grant fields):** **MATCH.** The existing `_sensitivity_grant_id` / `_sensitivity_grant_minted_at` locals (Story 6-9) thread through the new branch unchanged. On successful consume + dispatch, the `finally` block at line 1602-1623 writes `sensitivity_grant_id = grant_id` and `sensitivity_grant_minted_at = mint_time_iso`. Verified by AC-5.8 test `test_dispatch_tool_call_allows_sensitive_email_when_valid_token_supplied` which asserts `grant_id == minted.grant_id` and `minted_at.endswith("Z")`.
- **AC-4 (Story 4-7 gate preserved):** **MATCH.** `ask_router(...)` precondition layer at [mailbot_api/router/router.py:262-372](../../mailbot_api/router/router.py#L262-L372) is **unchanged** in this story. The existing `tests/integration/test_router_sensitivity_handshake.py` (6 tests covering Story 4-7's original AC matrix) stays green unmodified — verified in the gate sweep (55 tests across Story 4-7 + Story 6-9 all green).
- **AC-5 (12 regression tests):** **MATCH.** `tests/integration/test_dispatch_tool_call_sensitivity_gate_f28.py` ships exactly 12 tests; `pytest --collect-only -q` confirms 12 tests collected. Test names map 1:1 to AC-5.1–5.12. All 12 green on first run.
- **AC-6 (cross-doc updates):** **MATCH.** SOUL.md gained "Banned anti-pattern 3.5". AGENTS.md gained "Rule Q — Sensitivity-Gate Enforcement Boundary" between Rule P and Rule R. hermes-config/skills/mailbot/SKILL.md gained "Inline-drafting variant — F28 awareness" subsection. epic-6-run-flags.md gained "## F28 — RESOLVED" closing block with implementation summary + test evidence + cross-doc inventory.
- **AC-7 (MANDATORY-CR):** **MATCH (verdict-only — actual CR runs at Step 2.4 of the orchestrator).** §5.12 of this audit produces `MANDATORY-CR` verdict (3 criteria fire — privacy-invariant, cross-story load-bearing seam, state-machine seam). Reviewer focus areas pre-spec'd in story Dev Notes.

**Net drift:** zero. No story AC was reframed, narrowed, or punted to a follow-up beyond the explicitly-deferred multi-token-handshake (which the story's Dev Notes call out as the future expansion, not a missing AC).

## 2. File-List-vs-git diff check

Running `git status --porcelain` against the story's File List (computed at audit time):

| Path | Status | Verdict |
|---|---|---|
| `mailbot_api/router/router.py` | ` M` (modified, not staged) | **TRACKED** |
| `tests/integration/test_dispatch_tool_call_sensitivity_gate_f28.py` | `??` (untracked, new) | **UNTRACKED — expected (new file)** |
| `hermes-config/SOUL.md` | ` M` | **TRACKED** |
| `hermes-config/AGENTS.md` | ` M` | **TRACKED** |
| `hermes-config/skills/mailbot/SKILL.md` | ` M` | **TRACKED** |
| `_bmad-output/implementation-artifacts/epic-6-run-flags.md` | ` M` | **TRACKED** |
| `_bmad-output/implementation-artifacts/6-20-sensitivity-token-handshake-gate-relocation-to-dispatch-tool-call-f28-closure.md` | `??` (untracked, new) | **UNTRACKED — expected (new file)** |
| `_bmad-output/implementation-artifacts/6-20-sensitivity-token-handshake-gate-relocation-to-dispatch-tool-call-f28-closure.pre-review.md` | `??` (untracked, will exist after this write) | **UNTRACKED — expected (new file)** |
| `_bmad-output/implementation-artifacts/sprint-status.yaml` | ` M` (row 180 backlog → in-progress → review) | **TRACKED** |

**No surprise files in the story's scope.** Pre-existing `??` entries (skill installs, `.archive/`, `hermes-config/.local/`, etc.) and other modified files (`epics.md`, `settings.json`) are out of scope for Story 6-20 — Step 2.6 selective staging will use explicit `git add <path>` per the orchestrator contract.

## 3. Adversarial self-review

Self-caught issues, with severity:

- **[MEDIUM]** [mailbot_api/router/router.py:1378-1394](../../mailbot_api/router/router.py#L1378-L1394) — token-consume binds to "first sensitive id" via `_consumed_for_eid is not None` guard. **Concern:** an agent that supplies a token meant for `e_X` but the sorted order resolves `e_W` first will see `e_W` consume the token (if `e_W` is sensitive) and `e_X` refuse, OR `e_W` not match the token (mismatched email_id) and the WHOLE call refuse at NEEDS_SENSITIVITY_CONFIRMATION — even though `e_X` was the intended target. The agent's "correct" token may now be unusable on a re-attempt. **Mitigation considered & rejected:** trying all `_audit_ids` against the token would leak which id the token belongs to via timing (which `consume()` succeeded). Documented in the story's "first sensitive id only" Dev Notes; multi-token shape is the proper future fix. Acceptable for v1 given Hermes single-email-per-call dominant pattern.
- **[MEDIUM]** [mailbot_api/router/router.py:1416-1427](../../mailbot_api/router/router.py#L1416-L1427) — `WARNING` log fires once per `normal`-sensitivity email when token supplied, in a multi-id call. **Concern:** a chat completion referencing 5 normal emails + 1 sensitive will emit 5 WARNING events for the normal ids plus the one legitimate consume. **Mitigation considered:** suppress the warning when `_consumed_for_eid is not None` (a sensitive consume already happened on this call). Did NOT apply — the observability signal "token passed for normal id" is per-id forensic; correlating across the call is a downstream concern, not a logging-call concern. Accept as-is. Defer-with-rationale candidate for CR.
- **[LOW]** [mailbot_api/router/router.py:1364-1374](../../mailbot_api/router/router.py#L1364-L1374) — `SENSITIVITY_BLOCKS_API` message branches on `eid == email_id and len(_audit_ids) == 1` to preserve historical single-id wording. **Concern:** a caller passing the same id as parameter AND in messages (`email_id="e1"` + tool result references `e1`) sees `len(_audit_ids) == 1` (set-dedupe) and gets the historical message — but logically that IS a multi-source reference. **Verdict:** correct behavior — `len(_audit_ids) == 1` means there's only one id in scope, regardless of how many sources mentioned it. The branch is correct; the concern is theoretical.
- **[LOW]** [tests/integration/test_dispatch_tool_call_sensitivity_gate_f28.py:5.5 malformed-JSON test](../../tests/integration/test_dispatch_tool_call_sensitivity_gate_f28.py#L260-L280) — `caplog` assertion checks substring match on log message OR `extra` field; passes if either matches. **Concern:** brittle if logger format changes. Acceptable — `extra=dict` is the standard observability shape; the structured field check is the load-bearing assertion.
- **[LOW]** Single-token v1 contract is undocumented in the public `dispatch_tool_call` docstring (vs. only in story Dev Notes). **Concern:** future Router callers may pass a token expecting all-or-nothing semantics. **Mitigation:** the public docstring at line 1173 cites Story 4-7 + Story 6-20 for the gate description but doesn't enumerate the consume contract. Defer-with-rationale candidate; the source-level docstring should grow when multi-token v2 ships.

5 self-caught issues. None ESCALATE-TO-REVIEWER — but the [MEDIUM] log-per-normal-id and the [MEDIUM] sorted-order-token-binding are worth surfacing to the CR for second-opinion validation.

## 4. Self-caught issues remediated this audit

- **[MEDIUM] sorted-order-token-binding:** ACCEPT WITH RATIONALE. Documented in story Dev Notes as deferred multi-token v2; Hermes single-email-per-call pattern makes v1 correct for the production surface.
- **[MEDIUM] per-id WARNING on normal in multi-id call:** ACCEPT WITH RATIONALE. Per-id forensic observability outweighs noise concern; correlation is a downstream consumer concern.
- **[LOW] historical-message branch on `len==1`:** ACCEPT WITH RATIONALE. Branch is logically correct; concern was theoretical.
- **[LOW] caplog assertion brittleness:** ACCEPT WITH RATIONALE. `extra=dict` is standard; substring fallback adds robustness without weakening the check.
- **[LOW] consume contract not in public docstring:** ESCALATE TO REVIEWER. Worth deciding whether to land a 4-line note in `dispatch_tool_call`'s docstring NOW or wait for the multi-token v2 story to expand the surface.

## 5. Posture Audit

### 5.1 Lockfile hygiene
**N/A — no dependency changes.** `requirements.txt` unmodified; no `pip install` invoked. Verified: `git diff requirements.txt` produces zero output (file unmodified per `git status --porcelain`).

### 5.2 Cross-doc pair verification
- SOUL.md ↔ defender-persona Story 4-7 contract: updated; "Banned anti-pattern 3.5" extends the existing sensitivity-content discipline rules.
- AGENTS.md ↔ Story 4-7 sensitivity-token handshake: extended with Rule Q covering the second enforcement layer.
- hermes-config/skills/mailbot/SKILL.md ↔ Story 5-5 propose_action draft-reply flow: updated with the F28-aware inline-drafting variant.
- epic-6-run-flags.md ↔ F28 finding text: updated with the RESOLVED block + closure summary.

### 5.2.1 Schema-touching schema-doc verification
**N/A — no schema changes.** Migration 022 already added `sensitivity_grant_id` + `sensitivity_grant_minted_at` to `router_calls` per Story 4-7; Story 6-20 only WRITES into existing columns. Verified: no new `mailbot_api/db/migrations/NNN_*.sql` files in `git status --porcelain` output.

### 5.3 Lifecycle string-uniqueness check
**N/A — no new lifecycle strings.** Story 6-20 does NOT add new `ErrorCode` enum members; reuses `SENSITIVITY_NOT_CLASSIFIED`, `SENSITIVITY_BLOCKS_API`, `NEEDS_SENSITIVITY_CONFIRMATION` from Story 4-7. New log events `dispatch_tool_call.arg_parse_failed`, `sensitivity.token.consume_crash`, `sensitivity.token.unexpected` are already used elsewhere (consume_crash + unexpected are Story 4-7 verbatim; arg_parse_failed is the new addition). Verified via `Grep "dispatch_tool_call.arg_parse_failed"` — only 2 hits (one per branch in `_resolve_email_ids_from_messages`).

### 5.4 Multi-consumer impact scan
Production callers of `dispatch_tool_call`:
- **`mailbot_api/main.py:670` (`_chat_completions_tools_dispatch`)** — single production caller. Does NOT pass `email_id` parameter (line 670-681 does not include `email_id=`). The new multi-id branch is the SOLE path by which F28's surface gets gated — the caller doesn't need any signature change. ✓

Test callers (unit + integration):
- `tests/integration/test_chat_completions_tool_calling.py` — 49 tests, dispatches via `TestClient` against the FastAPI endpoint → `_chat_completions_tools_dispatch` → `dispatch_tool_call`. All 49 stayed green post-change. ✓
- `tests/integration/test_dispatch_tool_call_sensitivity_gate_f28.py` (new) — 12 tests directly against `dispatch_tool_call`. ✓

**No production caller passes `email_id` directly today** — the new branch is operationally activated by `_chat_completions_tools_dispatch`'s message-resolution path. Future direct callers (e.g., a verb dispatching tool-calls) would benefit from the same gate without code change.

### 5.5 Screenshot-based perception check
**N/A — no UI changes.** `<frontend-src>` is N/A per PORTING.md.

### 5.6 Upstream-contract spec coverage
- Story 4-7 contract (`ask_router` precondition): preserved UNCHANGED. Existing tests prove preservation.
- Story 6-9 (F11) contract (`dispatch_tool_call` signature, audit-row shape, tool_calls_count/summary): preserved UNCHANGED. The new multi-id branch slots into the existing precondition block without changing the function signature, return shape, or audit-row column list.
- Story 6-9 CR-2/CR-4 contract (`is_force_override` semantics + degraded-mode opus block): UNCHANGED. The new branch sits AFTER the degraded-mode block, so `model` may have been demoted before the gate iterates `_audit_ids`. Audit row's `model_chosen_reason="degraded"` is preserved.

### 5.7 Module-level mutable container check
New module-level state introduced by Story 6-20: **NONE.** The `_resolve_email_ids_from_messages` helper is pure; `_audit_ids` is a function-local set; `_consumed_for_eid` is a function-local string flag; `_sensitivity_grant_id` / `_sensitivity_grant_minted_at` are function-local strings (the same pre-existing locals from Story 6-9). Verified by `Grep "^_[A-Z][A-Z_]* = " mailbot_api/router/router.py` — no new module-level mutable constants/dicts/lists added in this story.

### 5.8 Dev-fixture seed-vs-production-shape parity
Test fixtures use the canonical Story 4-7 `_seed_email` shape (INSERT INTO emails with `sensitivity, sensitivity_at, sensitivity_prompt_v, sensitivity_conf, sensitivity_model`). Verified: matches the production `EMAIL_SENSITIVITY_SELECT` query's expected column shape (`emails.sensitivity`, `emails.sensitivity_at`). No fixture-vs-production divergence.

### 5.9 grep-verify-cited-figures
Cited figures in story Completion Notes / pre-review:
- **"12 tests collected"** — verified via `pytest --collect-only -q` output above: "12 tests collected in 3.27s". ✓
- **"1111 passed + 2 skipped + 3 deselected"** — verified via full pytest run output above: "1111 passed, 2 skipped, 3 deselected, 1 warning in 271.16s". ✓
- **"+12 net from baseline 1099+2+3"** — verified: Story 6-17's closing entry recorded "1099 + 2 skipped + 3 deselected" as baseline; 1099 + 12 = 1111. ✓
- **"55 / 55 Story 4-7 + Story 6-9 tests green unmodified"** — verified via `pytest test_router_sensitivity_handshake.py test_chat_completions_tool_calling.py` output above: "55 passed, 1 warning in 59.86s". ✓
- **"mypy strict clean (123 files)"** — verified via `mypy --strict mailbot_api` output above: "Success: no issues found in 123 source files". ✓

### 5.10 Producer-boundary contract enforcement
The producer boundary for sensitivity gating is `dispatch_tool_call`'s precondition layer — verified correct architectural placement:
- **Right layer:** above the adapter dispatch, below the policy/budget/pause checks. Refusal does NOT write a `router_calls` row (verified by AC-5.12 test).
- **Not at the endpoint:** the FastAPI endpoint `_chat_completions_tools_dispatch` does NOT do sensitivity logic — it delegates to the router. Endpoint-layer gating would split the enforcement surface across HTTP + non-HTTP callers; router-layer gating covers both.
- **Not at the adapter:** the `AnthropicAdapter.call_with_tools` does NOT do sensitivity logic — it's a pure adapter. Adapter-layer gating would couple privacy enforcement to provider-specific code.
- **The resolver is pure:** `_resolve_email_ids_from_messages` has zero DB I/O. The DB I/O happens in the dispatcher's loop (one `fetchone(EMAIL_SENSITIVITY_SELECT)` per resolved id). This separation is testable in isolation (resolver) and integration (full dispatcher loop).

### 5.11 Git-evidence consistency
- **5.11.a File-List-vs-working-tree consistency:** verified in §2 above. All 9 File List entries map to either ` M` (tracked modified) or `??` (new untracked, expected for the 3 new files). Zero strays.
- **5.11.b Test-to-code production ratio:** Story 6-20 ships 12 new tests + ~90 production LOC (the resolver helper + the gate extension). Ratio ≈ 1 test per 7-8 LOC of production change — within the project's healthy norm for security-invariant surfaces.
- **5.11.c No-later-commits-under-attribution:** verified — `git log --oneline -5` shows the latest commit is `aa87929` (Adam's option-A decision); no Story 6-20 commits exist yet (story stages but doesn't commit per autonomous-epic-run contract).

### 5.12 CR-cadence-mandatory surface classification

**Verdict: `MANDATORY-CR`.**

Three §5.12 criteria fire:

1. **Privacy invariant / security surface (criterion 1).** F28 is a documented CRITICAL privacy-invariant violation. The fix relocates the enforcement boundary for a load-bearing privacy contract (NFR-PRIV-1 — cautious-bias floor; NFR-PRIV-2 — confidential admits no override; FR-2.3 — sensitivity precondition). MANDATORY by default for any privacy-invariant surface.
2. **Cross-story load-bearing seam (criterion 6).** Touches the contracts of Stories 3-3 (sensitivity precondition AC-5), 4-7 (handshake gate at ask_router), 5-1 (hydrate_email body exposure), 5-2 (MCP transport), 5-9 (draft_reply orchestrator), 6-9 (F11 dispatch_tool_call sibling). Six prior stories' invariants must continue holding. The reviewer's job is to verify each.
3. **State-machine seam (criterion 3).** Adds a new branch to the routing-side state machine (paused → policy → degraded → sensitivity → dispatch). The multi-id iteration + token consume on first-sensitive-id + audit-row threading is non-trivial state-machine extension.

**Adam-decided 2026-06-02 (option A, Epic 4 retro action item #1):** MANDATORY-CR is non-negotiable. Step 2.4 of the orchestrator MUST dispatch the CR subagent under a different model from the dev model (Sonnet 4.6 per Phase 1 of autonomous-epic-run).

**Reviewer focus areas (pre-spec'd in AC-7 of the story file):**

- (a) Resolver pure-function correctness — deeply nested JSON edge cases, malformed-JSON skip behavior, multi-tool-call assistant messages
- (b) Multi-id iteration order determinism — test stability across runs
- (c) NO sensitive payload ever logged — token value, email body, email subject
- (d) Story 4-7 contract verbatim preservation at `ask_router`
- (e) F28 reproducer test actually fails against pre-fix code AND passes against post-fix code (forensic correctness)

## Summary table

| Section | Status |
|---|---|
| 1. AC-vs-code drift | ✅ MATCH (all 7 ACs) |
| 2. File-List-vs-git | ✅ Clean (9/9 entries accounted for) |
| 3. Adversarial self-review | ✅ 5 issues caught |
| 4. Issues remediated | ✅ 4 ACCEPT, 1 ESCALATE-TO-REVIEWER |
| 5.1 Lockfile | N/A — no dep changes |
| 5.2 Cross-doc | ✅ 4 docs updated |
| 5.2.1 Schema-doc | N/A — no schema changes |
| 5.3 Lifecycle strings | N/A — no new lifecycle strings |
| 5.4 Multi-consumer | ✅ 1 prod caller, 49+12 test callers |
| 5.5 Screenshot perception | N/A — no graphical UI |
| 5.6 Upstream-contract | ✅ Story 4-7 + 6-9 contracts preserved |
| 5.7 Module-mutable state | ✅ Zero new module-level state |
| 5.8 Fixture-vs-production parity | ✅ Match |
| 5.9 grep-verify-cited-figures | ✅ All 5 figures verified |
| 5.10 Producer-boundary | ✅ Right architectural layer |
| 5.11 Git-evidence | ✅ Consistent |
| 5.12 **Cadence verdict: `MANDATORY-CR`** | ✅ 3 criteria fire |
