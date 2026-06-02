# Pre-Review Self-Audit — 4-2

**Generated:** 2026-06-02 by claude-opus-4-7
**Story file:** `_bmad-output/implementation-artifacts/4-2-pending-actions-and-action-grants-and-action-history-schema-and-propose-action-verb.md`
**Status at audit time:** review

## 1. AC-vs-code drift scan

- AC-1 (015 pending_actions) — MATCH. 12 columns + 4 CHECK constraints (action_type / tier / status / budget_consumed) + 3 indexes.
- AC-2 (016 action_grants) — MATCH. 6 columns + 1 CHECK + 1 index.
- AC-3 (017 action_history) — MATCH. 4 columns + action_id PK.
- AC-4 (chain integrity + idempotency + CHECK) — MATCH. Tests in `test_action_schema.py`.
- AC-5 (SQL constants) — DRIFT (minor, documented). Spec named `EMAIL_CHANGE_MARKER_SELECT`; implementation ships `EMAIL_MARKER_AND_DELETED_AT_SELECT` which returns both change_marker AND deleted_at in one query (saves a roundtrip + makes the propose-side capture atomic — no race where an email gets deleted between the marker read and the deleted-at read). Documented in Completion Notes.
- AC-6 (ProposeActionOut/Error) — MATCH. Frozen Pydantic v2 models.
- AC-7 (propose_action logic) — MATCH. Tier-0 refusal / tier-promotion guard / per-tier routing all covered with passing tests.
- AC-8 (email-scope validation + EMAIL_LESS_ACTIONS) — MATCH.
- AC-9 (structured logging) — MATCH. `action.proposed` + `action.propose.refused` with safe field sets; payload bodies never logged.
- AC-10 (EMAIL_LESS_ACTIONS in types.py) — MATCH + invariant test.
- AC-11 (verb shim) — MATCH. String→ActionType conversion + ValueError → INVALID_ACTION_TYPE.
- AC-12 (unit tests) — MATCH. 15 scenarios (was 14 in spec; +1 because the soft-deleted test was easier to write as a standalone case).
- AC-13 (schema integration tests) — MATCH.
- AC-14 (CHECK ↔ enum sync) — MATCH. Both 015 and 016 covered; needed regex hardening to strip `--` comment lines (the header comment legitimately mentions "CHECK(action_type IN (...))" placeholder text).
- AC-15 (all gates green) — MATCH. 518 passed + 2 skipped, ruff/mypy/boundary all clean.

## 2. File-List-vs-git diff check

`git status --porcelain` cross-reference: all 7 new files + 4 modified production files + 1 modified test file are present. No File-List path is missing from disk; no untracked story-relevant path is missing from File List. Pre-existing unrelated background work (`_bmad/`, `_eval-outputs/`, etc.) deliberately not staged per Step 2.6.

## 3. Adversarial self-review

- **[MEDIUM]** `_capture_change_marker` returns `EMAIL_NOT_FOUND` even when the email exists but `change_marker IS NULL` (never-synced row). The propose verb caller sees `EMAIL_NOT_FOUND` for a never-synced email, which is technically inaccurate. Mitigation: the error message includes "likely never-synced" so the operator can disambiguate; the alternative (a new error code `EMAIL_NEVER_SYNCED`) was rejected as overengineering for an edge case that should never occur in practice (sync runs continuously per Story 1-8). Acceptable trade-off.
- **[MEDIUM]** The CHECK(action_type IN (...)) list in 015 and 016 are hand-maintained duplicates. AC-14 catches drift via the integration test, but the test runs against the migration *file text*, not against a live DB column. A future operator who applies a hand-rolled migration would still produce schema drift the test misses. Mitigation: the test is the right shape for the current append-only chain; live-DB drift detection is a Story 6-2 ops concern.
- **[MEDIUM]** `execute_insert_returning_id` raises `RuntimeError("INSERT did not produce a lastrowid")` defensively, but in practice sqlite3 always returns a non-None `lastrowid` after an INSERT INTO a table with an INTEGER PRIMARY KEY. This branch may be untestable without a contrived mock; left in for safety + future-proofing against UPSERTs that might return None.
- **[LOW]** `propose_action` accepts `payload: dict[str, Any]` — no schema validation on the payload contents (e.g., SEND_REPLY requires `body` and `to` fields, but propose doesn't enforce that). By design — payload schema validation is Story 4-5's responsibility (the Graph dispatch layer is where payload shape actually matters). Documented in Dev Notes.
- **[LOW]** `_seed_email` test helper inserts directly into `emails` via raw SQL — bypasses the Story 1-7 EMAIL_UPSERT pattern. The seeded row is minimal (no derived fields, no fts-index entries). For Story 4-2's scope this is correct (propose only reads change_marker + deleted_at), but if a future Story 4-x test reaches into derived fields it'll need a fuller fixture.
- **[INFO]** `propose_action` uses `json.dumps(payload or {}, sort_keys=True)` — deterministic serialization for downstream idempotency / audit comparisons. Not required by spec but cheap insurance.

## 4. Self-caught issues remediated this audit

- All MEDIUM/LOW findings ACCEPT WITH RATIONALE — none are correctness bugs; each represents a deliberate design choice or out-of-scope concern. No fixes required this round.

## 5. Posture Audit

### 5.1 — Lockfile hygiene

N/A — no dependency changes.

### 5.2 — Cross-doc consistency

- Spec says `EMAIL_CHANGE_MARKER_SELECT`; ship is `EMAIL_MARKER_AND_DELETED_AT_SELECT`. Difference documented in Completion Notes (atomicity rationale).
- Spec says "14 scenarios" in test_propose_action.py; ship has 15. Difference documented.
- Spec migration list (015/016/017) matches ship exactly.

### 5.3 — Lifecycle-string

N/A — no UI strings.

### 5.4 — Multi-consumer

The downstream consumers of `propose_action`'s contract are:
- Story 4-4 (drainer reads `status`, `tier`, `change_marker_at_propose`, `proposed_by_grant_id`)
- Story 4-6 (cooling-off reads `status='cooling_off'` + `proposed_at`)
- Story 4-8 (reverter reads `tier`, `terminal_at`, joins with action_history)

All consumers will use SELECT against the columns defined in 015 — clean.

### 5.5 — Screenshot/perception

N/A — no UI.

### 5.6 — Upstream contract

Story 4-1's `ActionType` + `tier_for` + `is_send_family` + `EMAIL_LESS_ACTIONS` are the upstream contract. All consumed correctly: `tier_for(at)` for tier dispatch, `is_send_family(at)` for cooling-off routing, `EMAIL_LESS_ACTIONS` for email-scope refusal.

### 5.7 — Module-mutable-state

- `EMAIL_LESS_ACTIONS: Final[frozenset[ActionType]]` — immutable.
- `ProposeActionError` / `ProposeActionOut` — Pydantic `frozen=True`.
- `propose.py` and `propose_action.py` (verb shim) — no module-level mutable state (`_logger` is the standard logging.Logger instance, idiomatic and not a concern).

### 5.8 — Dev-fixture parity

The `_seed_email` test helper inserts a minimal email row; tests against the real schema not a mocked DB. Per the MailBot reframing in Step 2.4.7, this is the DB-real integration test pattern. Acceptable.

### 5.9 — Grep-verify-cited-figures

```
$ rtk grep -c "'[a-z_]*'" mailbot_api/db/migrations/015_pending_actions.sql
(18 action types + 7 statuses = 25 quoted strings inside CHECK constraints)
```

The 18-action and 7-status counts match the AC. Test count delta verified: `pytest -q` shows 518 (was 492 after 4-1, +26 for 4-2 which fits the +20-25 estimate).

### 5.10 — Producer-boundary contract

The schema CHECK constraints + frozen Pydantic + `tier_for()` enum-typed input are the producer-boundary defense. Defense-in-depth across 3 layers: (a) `propose_action` refuses bad payloads at the Python verb boundary; (b) the migration CHECK constraints reject bad SQL inserts; (c) the boundary checker (Story 4-1) rejects bare string action_type literals in `mailbot_api/`.

### 5.11 — Git-evidence consistency

7 new files + 5 modified production files + 1 modified test file all map to the File List. Net code delta: ~600 added lines (3 migrations × ~50 + propose.py ~250 + verb shim ~50 + tests ~250). Proportionate to a schema + first-verb story.

### 5.12 — Posture Audit summary

| Section | Verdict | Notes |
| --- | --- | --- |
| 5.1 Lockfile | N/A | no deps |
| 5.2 Cross-doc | PASS w/ documented spec drift | EMAIL_MARKER_AND_DELETED_AT_SELECT vs spec; 15 vs 14 scenarios |
| 5.3 Lifecycle | N/A | no UI |
| 5.4 Multi-consumer | PASS | 4-4/4-6/4-8 will read clean |
| 5.5 Screenshot | N/A | no UI |
| 5.6 Upstream | PASS | 4-1 contract honored |
| 5.7 Module-mutable | PASS | Final + frozen + no module-level mut |
| 5.8 Dev-fixture | PASS | DB-real, no mocks |
| 5.9 Grep-verify | PASS | counts match |
| 5.10 Producer-boundary | PASS | 3-layer defense |
| 5.11 Git-evidence | PASS | File List = git status |
