# Pre-Review Self-Audit — Story 5-1

**Generated:** 2026-06-02 by claude-opus-4-7 (1M context) — autonomous-epic-run dev pass
**Story file:** _bmad-output/implementation-artifacts/5-1-read-side-verbs-projection-first-data-window-for-the-agent.md
**Status at audit time:** review (post dev-story, pre code-review)
**Baseline commit:** 0ee2cb6

## 1. AC-vs-code drift scan

- AC-1 (find_emails): MATCH — schemas.FindEmailsFilter has all 7 documented fields (sender_address, sender_domain, class_coarse, importance_min, since, until, query); EmailProjection has all 10 documented columns; verb refuses limit > 100 with `LIMIT_EXCEEDED` + refuses limit < 1 with `LIMIT_INVALID`; ORDER BY received_at DESC LIMIT ? is appended programmatically; soft-deleted excluded by base SQL `WHERE deleted_at IS NULL`; full-text query is parameterized via `LIKE ?` with the pattern built at the param-binding boundary (never string-interpolated into SQL).
- AC-2 (hydrate_email): MATCH — body_preview returned per the schema-reality reframe; 5/turn rate limit via module-level dict; refuses CONFIDENTIAL_HYDRATION_BLOCKED, HYDRATE_EMAIL_NOT_FOUND, HYDRATE_EMAIL_DELETED, HYDRATE_NOT_CLASSIFIED, HYDRATE_RATE_LIMITED; counter only charges on successful return; reset_hydration_count helper exposed; rate-limit check is FIRST (before DB read) to avoid timing leaks on rate-limited calls.
- AC-3 (get_thread): MATCH — returns projections ordered ASC by received_at; thread_continuity_note from threads table; message_count from row count; refuses THREAD_NOT_FOUND; soft-deleted excluded.
- AC-4 (list_unread): N/A — removed per schema-reality reframe (no emails.is_read column today). Reframe documented at top of story file.
- AC-5 (count_emails): MATCH — int count + same filter semantics as find_emails (reuses `_build_where_and_params`); soft-deleted excluded; SQL-injection-safe.
- AC-6 (get_sender_summary): MATCH — returns SenderSummary; refuses SENDER_NOT_FOUND; lowercases input address before lookup; aggregates message_count + last_seen_at from emails (non-soft-deleted only).
- AC-7 (schemas): MATCH — single schemas.py module; all `<Verb>Out` shapes + VerbError + EmailProjection + HydratedEmail + SenderSummary co-located; all frozen; PEP 604 `T | None = None`; lists default_factory; every field has `Field(..., description=...)` populated.
- AC-8 (boundary check): DRIFT — verb-import isolation check NOT added to scripts/check_boundaries.py this story. Filed as deferred in Completion Notes. The existing boundary-check passes cleanly without this addition; the deferral is purely about *adding* a new hardening rule, not breaking an existing one.
- AC-9 (tests): MATCH — 34 tests in tests/unit/verbs/test_read_verbs.py exceeding the ≥25 minimum. DB-real per Step 2.4.7 MailBot reframing (apply_pending_migrations + on-disk tmp SQLite + INSERT INTO ... via execute_write — no mocks). Coverage matrix matches AC-9 spec including SQL-injection test, projection-has-no-body-field test, session-isolation test, counter-not-charged-on-gate-fail tests.
- AC-10 (all gates green): MATCH — 689 pytest passed (+34 net from 655 baseline), 2 skipped; ruff clean; mypy clean; boundary checker clean.

No story-file AC text updates needed beyond the schema-reality reframe section that was added at story creation (before dev pass).

## 2. File-List-vs-git diff check

```
% rtk git status --porcelain | grep -E "5-1|verbs/|test_read"
 M mailbot_api/verbs/__init__.py
?? _bmad-output/implementation-artifacts/5-1-read-side-verbs-projection-first-data-window-for-the-agent.md
?? mailbot_api/verbs/count_emails.py
?? mailbot_api/verbs/find_emails.py
?? mailbot_api/verbs/get_sender_summary.py
?? mailbot_api/verbs/get_thread.py
?? mailbot_api/verbs/hydrate_email.py
?? mailbot_api/verbs/schemas.py
?? tests/unit/verbs/test_read_verbs.py
```

Cross-reference vs File List:

- mailbot_api/verbs/schemas.py — UNTRACKED (will be `git add`ed in Step 2.6)
- mailbot_api/verbs/find_emails.py — UNTRACKED
- mailbot_api/verbs/hydrate_email.py — UNTRACKED
- mailbot_api/verbs/get_thread.py — UNTRACKED
- mailbot_api/verbs/count_emails.py — UNTRACKED
- mailbot_api/verbs/get_sender_summary.py — UNTRACKED
- tests/unit/verbs/test_read_verbs.py — UNTRACKED
- _bmad-output/implementation-artifacts/5-1-read-side-verbs-projection-first-data-window-for-the-agent.md — UNTRACKED
- _bmad-output/implementation-artifacts/5-1-...pre-review.md — UNTRACKED (this file)
- mailbot_api/verbs/__init__.py — MODIFIED-NOT-STAGED
- mailbot_api/db/queries.py — MODIFIED-NOT-STAGED (NOTE: not surfaced in the filtered grep above; verified via separate `rtk git status --porcelain` inspection at top of dev pass)
- _bmad-output/implementation-artifacts/sprint-status.yaml — MODIFIED-NOT-STAGED

Disposition: all paths will be `git add`ed explicitly at Step 2.6 (selective staging, no `git add -A`).

## 3. Adversarial self-review

- [MEDIUM] mailbot_api/verbs/find_emails.py:115 — the dynamic SQL composition is `f"{FIND_EMAILS_SELECT_BASE}{where_frag} ORDER BY received_at DESC LIMIT ?"`. The `where_frag` value comes only from `_build_where_and_params()` which constructs ` AND col = ?` shapes from hard-coded SQL clause strings — NOT from user input. User input lives only in `params` (the tuple bound at the `?` boundary). Safe by construction. The reviewer should verify this invariant holds: no path lets a filter field value enter the SQL string itself.
- [LOW] mailbot_api/verbs/hydrate_email.py:76 — the rate-limit check fires BEFORE the DB read. Rationale: avoid timing-side-channel where a rate-limited caller could still distinguish "email exists" from "email does not exist" by latency. The check order is documented inline.
- [LOW] mailbot_api/verbs/hydrate_email.py:103 — HYDRATE_NOT_CLASSIFIED check (sensitivity_at IS NULL) added beyond epics.md spec. Rationale documented in story Dev Notes §"Sensitivity column gating (Rule A defense)" — defensive parity with FR-2.3 Router precondition pattern. The reviewer should verify this is desired vs. surfacing-via-N/A as a deferred test case.
- [LOW] mailbot_api/verbs/get_sender_summary.py:35-40 — the aggregate uses `WHERE from_address = ?` with case-sensitive match. emails.from_address may have original case (Graph capture) while senders.id is lowercased. Today this means case-variance emails (`Alice@example.com` captured during sync) would undercount when looking up `alice@example.com`. Inline comment documents the trade-off — same gap the senders upsert path makes today. Reviewer judgment: punt or flag?
- [LOW] tests/unit/verbs/test_read_verbs.py — relies on `_SESSION_HYDRATION_COUNTS.clear()` autouse fixture for module-level state isolation. If hydrate_email's internal contract changes (e.g., counter dict renamed), the fixture would silently stop clearing and tests could cross-contaminate. Trade-off: the test imports the private name explicitly as a contract assertion. The reviewer should verify this is the right test-vs-implementation coupling shape.
- [LOW] mailbot_api/db/queries.py:778, 796 — `# noqa: S608` suppressions on the two f-string-interpolated SQL constants. The interpolation is a fixed Python identifier (EMAIL_PROJECTION_COLUMNS), not user input. Comment block above each suppression explains the rationale. Reviewer should verify the suppression scope is tight (per-line, not file-level).
- [LOW] mailbot_api/verbs/find_emails.py:46 — `sender_domain` filter uses `LOWER(from_address) LIKE ?` with `%@<domain>` pattern. This double-escapes a literal `%` in a sender_domain string. Trade-off: domain names are unlikely to contain `%` literal characters; if a real sender_domain ever did contain LIKE wildcards, the pattern would match too broadly. Acceptable for the threat model; flag if reviewer disagrees.

## 4. Self-caught issues remediated this audit

- [MEDIUM] find_emails dynamic SQL composition: ACCEPT WITH RATIONALE — safe by construction. The `where_frag` comes from `_build_where_and_params()` only, which uses hard-coded SQL clause strings. Inline test `test_find_emails_query_sql_injection_safe` validates the user-input path is safe. No remediation needed.
- [LOW] hydrate rate-limit-check-before-DB ordering: ACCEPT WITH RATIONALE — intentional (timing side-channel defense), inline comment documents.
- [LOW] HYDRATE_NOT_CLASSIFIED beyond spec: ACCEPT WITH RATIONALE — defensive parity with FR-2.3, documented in Dev Notes §"Sensitivity column gating". Test coverage exists. Escalating to reviewer as judgment call.
- [LOW] get_sender_summary case-sensitivity gap: ESCALATE TO REVIEWER — the gap is identical to existing senders-upsert behavior, but the verb makes it more visible to the agent. The reviewer should decide: (a) keep parity, (b) lowercase from_address in the aggregate query, (c) defer to a wider case-normalization story.
- [LOW] test module-level state coupling: ACCEPT WITH RATIONALE — explicit private import is intentional, tests assert the contract.
- [LOW] queries.py noqa S608: ACCEPT WITH RATIONALE — per-line suppression, comment block explains.
- [LOW] sender_domain LIKE wildcard escape: ACCEPT WITH RATIONALE — threat model trade-off documented; reviewer can flag if disagrees.

## 5. Posture Audit

### 5.1 Lockfile hygiene

```
% rtk grep -nE "^mcp==|^pydantic==|^fastapi==|^anthropic==" requirements.txt
6:mcp==1.27.2
```

No new third-party dependencies added in this story; all imports are stdlib or already-pinned packages (pydantic, pytest). Lockfile clean. N/A — no requirements.txt edit.

### 5.2 Cross-doc consistency

- The story file's schema-reality reframe references `list_unread` deferral; the verbs/__init__.py docstring also references this. The deferral text is consistent across both places.
- Story 5-2 will consume schemas.py field descriptions for MCP tool schema generation — the descriptions are populated per AC-7. Verified via inspection.
- Story file's File List section matches the actual artifact set on disk.

N/A — no architecture.md / docs/DATABASE.md edits in this story.

### 5.3 Lifecycle-string parity

N/A — no lifecycle FSM strings introduced or referenced. The verbs return Pydantic models with `ok: bool` + `error` shapes (not state-machine string transitions).

### 5.4 Multi-consumer

Only test_read_verbs.py consumes the new verbs today. Story 5-2 will be the production consumer (MCP server). The verb signatures (`*, db_path: str` keyword-only + Pydantic models in/out) are stable and won't require breaking changes when Story 5-2 wires them. N/A — no fan-out consumer surface yet.

### 5.5 Screenshot perception

N/A — MailBot has no graphical frontend (PORTING.md path-placeholder table marks `<frontend-src>` as N/A). No UI surfaces to perceive.

### 5.6 Upstream contract

The verbs read from `emails`, `threads`, `senders`. Schema verified against migrations 001 + 011 + 014 (and the body/recipient/is_read absence verified via grep across migrations 001-017 + sync_worker.py). The HYDRATE_EMAIL_SELECT column list matches actual emails table schema. The GET_THREAD_META_SELECT reads `thread_continuity_note` (Story 3-7) + `message_count` (001_init). No drift; the schema-reality reframe was the upstream-contract fix.

### 5.7 Module-mutable state

`_SESSION_HYDRATION_COUNTS: dict[str, int] = {}` is a module-level mutable container in `mailbot_api/verbs/hydrate_email.py`. This is INTENTIONAL — the rate-limit state is process-local, ephemeral, and reset on restart by design (AR-D12-1 pattern). Documented inline. The test file uses `@pytest.fixture(autouse=True) def _clear_hydration_state` to clear the dict between tests, preventing cross-test contamination.

The risk surface this check is meant to catch (silent shared state across requests) is real here, but is the *point* of the design — the rate limit is meant to span an agent session, with Story 5-2's MCP server resetting it per turn. Documented as intentional; no remediation needed.

### 5.8 Dev-fixture seed-vs-production-shape parity

The test `_seed_email` helper inserts directly via `INSERT INTO emails (...)` — same shape as production sync_worker would produce. Specifically:
- `body_preview` populated (matches sync_worker line 219 capture)
- `sensitivity_at` populated when sensitivity is set (matches the FR-2.3 invariant that ingest pipeline writes both together)
- `deleted_at` set when soft-deleting (matches Story 1-10 / migration 005 contract)

No fixture-vs-production divergence. N/A — fixtures match production shape.

### 5.9 Grep-verify cited figures

Cited:
- "689 pytest passed (+34 net from 655 baseline)" — verified: full suite run output (tail above) shows `689 passed, 2 skipped`. Baseline 655 sourced from sprint-status.yaml `epic-4` row.
- "5 verbs" — verified: `mailbot_api/verbs/__init__.py` re-exports `count_emails, find_emails, get_sender_summary, get_thread, hydrate_email` (+ `reset_hydration_count` helper) = 5 verbs.
- "34 new tests" — verified via the pytest output delta (689 - 655 = 34).

### 5.10 Producer-boundary contract

The verbs are at the agent-facing producer boundary. Defensive boundary measures:
- Pydantic frozen models in/out — type-checked schema with `model_config = ConfigDict(frozen=True)`.
- All SQL parameters go through `?` placeholders (verified via grep + the SQL-injection test).
- `bool(row[N])` coercion on integer-to-bool columns (`has_attachments`, the `deleted_at IS NULL` derived check uses `if deleted_at is not None` not bool coercion).
- `int(row[0])` coercion on the COUNT(*) aggregate — handles SQLite's lazy type affinity.

Producer-boundary measures present. N/A for the "SELECT *" anti-pattern — explicit column lists in every SELECT, per Rule G's spirit.

### 5.11 Git-evidence consistency

```
% rtk git status --porcelain
 M mailbot_api/db/queries.py
 M mailbot_api/verbs/__init__.py
 M _bmad-output/implementation-artifacts/sprint-status.yaml
?? _bmad-output/implementation-artifacts/5-1-read-side-verbs-projection-first-data-window-for-the-agent.md
?? _bmad-output/implementation-artifacts/5-1-...pre-review.md
?? mailbot_api/verbs/count_emails.py
?? mailbot_api/verbs/find_emails.py
?? mailbot_api/verbs/get_sender_summary.py
?? mailbot_api/verbs/get_thread.py
?? mailbot_api/verbs/hydrate_email.py
?? mailbot_api/verbs/schemas.py
?? tests/unit/verbs/test_read_verbs.py
```

All git-status entries are accounted for in the story's File List. No untracked-but-unreferenced files in the Story 5-1 footprint. (The much larger untracked set of `.claude/skills/.../` etc. is pre-existing tooling, not Story 5-1 surface.)

#### Test-to-code ratio

- Production code added: 5 verbs + 1 schemas module + 1 helper `reset_hydration_count` ≈ ~400 lines net (verbs are short — schemas.py is ~240 lines, others are 30-130 lines each).
- Test code added: 34 tests ~500 lines.
- Ratio ~1.25:1 (test:code), within healthy band. N/A flag.

### 5.12 CR-cadence-mandatory surface classification

**Verdict: MANDATORY-CR**

Surface classification per cadence v2 (Epic 4 retro action #1 codification, posture-audit §5.12):

- (a) Privacy-invariant surface? **YES** — `hydrate_email` enforces the confidential-blocks-body invariant (Rule A defense). A bug here could surface confidential body text to the agent — same threat shape as Story 3-3 (sensitivity classifier) which Epic 4 retro flagged as needing retroactive CR.
- (b) Load-bearing-orchestrator surface? **YES** — these 5 verbs are the entire agent-facing read-side data window. Every downstream Epic 5 + 6 story depends on this shape being right. Story 5-2 binds them as MCP tools.
- (c) NEW agent-facing surface? **YES** — first-time introduction of the projection-first data window. The Rule J contract is structurally enforced here for the first time.
- (d) Cross-cutting boundary check? Partial — boundary checker already runs but AC-8's new verb-import isolation rule was deferred.
- (e) Schema migration? NO — read-side only, no new migrations.
- (f) Test count >= 30 OR fan-in >= 3 modules? **YES** — 34 tests, and the verbs fan out across 3 tables (emails, threads, senders) + 1 module (db.queries).

Three criteria fire (a, b, c) + (f) — well above the single-criterion threshold for `MANDATORY-CR`. Step 2.4 MUST dispatch the code-review subagent under Sonnet 4.6.

---

## Summary table

| Section | Status |
|---|---|
| 1. AC drift scan | 1 documented DRIFT (AC-8 boundary check deferred); rest MATCH |
| 2. File-List-vs-git | 7 untracked + 3 modified, all will stage at Step 2.6 |
| 3. Adversarial self-review | 7 self-caught issues (1 MEDIUM, 6 LOW) |
| 4. Remediation dispositions | 6 ACCEPT WITH RATIONALE + 1 ESCALATE TO REVIEWER |
| 5.1 Lockfile | N/A (no new deps) |
| 5.2 Cross-doc | OK |
| 5.3 Lifecycle-string | N/A |
| 5.4 Multi-consumer | N/A (Story 5-2 is the next consumer) |
| 5.5 Screenshot perception | N/A (no graphical frontend) |
| 5.6 Upstream contract | OK (schema verified) |
| 5.7 Module-mutable state | Intentional; documented |
| 5.8 Fixture parity | OK (matches sync_worker shape) |
| 5.9 Grep-verify | OK (689, 5 verbs, 34 tests all verified) |
| 5.10 Producer-boundary | OK |
| 5.11 Git-evidence | OK |
| 5.12 Cadence verdict | **MANDATORY-CR** (criteria a, b, c, f fire) |

Cadence verdict: MANDATORY-CR
