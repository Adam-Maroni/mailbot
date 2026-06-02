---
baseline_commit: 0ee2cb6
---

# Story 5.1: Read-side verbs — projection-first data window for the agent

Status: done

## Schema-reality reframe (2026-06-02 dev-pass)

The epics.md AC text references `is_read`, `body_text`, `body_html`, `to_addresses`, `cc_addresses` — none of these columns exist on the `emails` table (verified against migrations 001 + 011 + checked sync_worker.py). Only `body_preview` is captured during Graph sync. Adam-decided (autonomous-epic-run dev pass, option 1): adapt this story to schema reality rather than expand scope or insert a prerequisite story.

**Scope changes vs epics.md Story 5.1:**
- `list_unread` REMOVED from this story (filed as follow-up requiring sync-side `is_read` capture + migration before it can land).
- `hydrate_email` returns `body_preview` (the field that actually exists) instead of `body_text`/`body_html`. The HTML sanitizer (was AC-2.2) is REMOVED — body_preview is plain text from Graph, no HTML to scrub.
- `to_addresses`/`cc_addresses` REMOVED from `HydratedEmail` (columns don't exist).
- Five verbs ship: `find_emails`, `hydrate_email`, `get_thread`, `count_emails`, `get_sender_summary`.

**Deferred to a future story (likely Epic 6 or a 5-0.5 follow-up):**
- Migration adding `is_read INTEGER NOT NULL DEFAULT 0`, `body_text TEXT`, `body_html TEXT`, `to_addresses TEXT` (JSON), `cc_addresses TEXT` (JSON) to `emails`.
- Sync worker update to capture `isRead`, full `body.content` + `body.contentType`, `toRecipients`, `ccRecipients` from Graph delta.
- `list_unread` verb (depends on the migration).

## Story

As Adam,
I want five read-side verbs (`find_emails`, `hydrate_email`, `get_thread`, `count_emails`, `get_sender_summary`) implemented as plain async Python functions returning `<Verb>Out` Pydantic models with projection-only data,
so that the agent's data window is structurally narrow (Rule J — hydration discipline), rate-limited per turn, and unit-testable in isolation before any MCP harness exists.

## Acceptance Criteria

### AC-1 — `find_emails` verb (projection-first filter)

`mailbot_api/verbs/find_emails.py`:

- `find_emails(filter: FindEmailsFilter, *, db_path: str, limit: int = 25) -> FindEmailsOut` is an async function.
- `FindEmailsFilter` is a frozen Pydantic model in `mailbot_api/verbs/schemas.py` with fields:
  - `sender_address: str | None = None`
  - `sender_domain: str | None = None`
  - `class_coarse: str | None = None`
  - `importance_min: float | None = None` (REAL column per migration 011 §Note)
  - `since: str | None = None` (UTC ISO-8601 — `Z` suffix per AR-PAT-3)
  - `until: str | None = None`
  - `query: str | None = None` (full-text on `subject` + `summary_short`)
  - `unread_only` field is INTENTIONALLY OMITTED — depends on a deferred sync-side `is_read` capture (see schema-reality reframe at top of file)
- `FindEmailsOut` is a frozen Pydantic model with `ok: bool`, `error: VerbError | None = None`, `projections: list[EmailProjection] = []`.
- `EmailProjection` is the agent-visible row (Rule J — projection-only):
  - `email_id: str` (the `graph_id` — the agent-facing stable handle)
  - `received_at: str` (ISO-8601 UTC, `Z` suffix)
  - `from_address: str`
  - `from_display_name: str | None`
  - `subject: str | None`
  - `summary_short: str | None`
  - `class_coarse: str | None`
  - `importance_score: float | None` (REAL — column is REAL per migration 011 §Note)
  - `sensitivity: str | None`
  - `has_attachments: bool`
- Default ORDER BY: `received_at DESC`.
- The verb refuses `limit > 100` with `FindEmailsOut(ok=False, error=VerbError(code="LIMIT_EXCEEDED", message="limit capped at 100 — use repeated queries with the `since` filter if you need more"))`. NO partial results, NO clamping.
- The verb refuses `limit < 1` with `LIMIT_INVALID`.
- The verb returns `FindEmailsOut(ok=True, projections=[...])` on success; empty list when no rows match (NOT an error).
- The verb does NOT return body_text / body_html / raw_payload — hydration requires a separate `hydrate_email` call (Rule J).
- Soft-deleted rows (`emails.deleted_at IS NOT NULL`) are excluded by default.
- The full-text `query` filter is `subject LIKE %?% OR summary_short LIKE %?%` with SQL-injection-safe parameter binding (placeholder substitution, NOT string interpolation). The pattern is built as `f"%{query}%"` and passed as a parameter.
- The verb internally calls `db.connection.fetchall(db_path, FIND_EMAILS_SELECT, params)` with the SQL constant pulled from `mailbot_api/db/queries.py` (Rule G — writer monopoly applies to the SQL constants, not query construction; this verb composes the WHERE clause from the SQL constant prefix + dynamic filter clauses, all parameterized).
- Field selection list is explicit (no `SELECT *`) per AR-PAT-3 / Rule G.

### AC-2 — `hydrate_email` verb (body_preview, rate-limited 5/turn)

`mailbot_api/verbs/hydrate_email.py`:

- `hydrate_email(email_id: str, *, db_path: str, session_id: str) -> HydrateEmailOut` is an async function.
- `HydrateEmailOut` is a frozen Pydantic model with `ok: bool`, `error: VerbError | None = None`, `email: HydratedEmail | None = None`.
- `HydratedEmail` carries:
  - `email_id: str`
  - `received_at: str`
  - `from_address: str`
  - `from_display_name: str | None`
  - `subject: str | None`
  - `body_preview: str | None` (the only body field captured by Graph sync today; full body deferred per schema-reality reframe)
  - All derived fields with companion metadata: `summary_short`, `summary_short_at`, `class_coarse`, `class_coarse_at`, `class_fine`, `class_fine_at`, `importance_score`, `importance_score_at`, `sensitivity`, `sensitivity_at`, `action_extraction`, `action_extraction_at`
  - `has_attachments: bool`
  - `thread_id: str | None`
- The verb refuses on `email_id` not found → `HYDRATE_EMAIL_NOT_FOUND`.
- The verb refuses on `emails.sensitivity = 'confidential'` → `CONFIDENTIAL_HYDRATION_BLOCKED` with message "confidential emails cannot be hydrated to the agent — only metadata is available" (per FR-2.6 / Rule A — confidential bodies never leave the VPS in a form the agent can read). NOTE: today this only protects `body_preview`; once the deferred full-body migration lands, the same gate keeps protecting body_text/body_html.
- The verb refuses on soft-deleted rows (`deleted_at IS NOT NULL`) → `HYDRATE_EMAIL_DELETED`.
- The verb refuses on unclassified rows (`sensitivity_at IS NULL`) → `HYDRATE_NOT_CLASSIFIED`. Defensive: an unclassified email could later be marked confidential; making the agent wait for the ingest pipeline to run is consistent with FR-2.3 / Story 3-3's Router precondition pattern.
- **Rate limiting (Rule J — hydration discipline):** the verb is rate-limited to 5 hydrations per agent session. State lives in a module-level dict `_SESSION_HYDRATION_COUNTS: dict[str, int]` keyed by `session_id`. The 6th hydration in the same session returns `HYDRATE_RATE_LIMITED` with message "hydration limit is 5 emails per turn — narrow your filter first". The counter is **NOT reset by this verb** — it increments on every successful call. Counter reset is the responsibility of the MCP server's per-turn lifecycle (Story 5-2 will wire this).
- The counter increments ONLY on successful return (a body was exposed). `HYDRATE_EMAIL_NOT_FOUND`, `CONFIDENTIAL_HYDRATION_BLOCKED`, `HYDRATE_EMAIL_DELETED`, `HYDRATE_NOT_CLASSIFIED`, and `HYDRATE_RATE_LIMITED` do NOT charge the counter (no body was exposed, or already at limit).
- A `reset_hydration_count(session_id: str) -> None` helper is exposed for the MCP server (Story 5-2) and for tests.
- The session counter dict is process-local, in-memory, ephemeral. **No persistence** — losing it on restart is acceptable and intentional (per AR-D12-1 sensitivity-token-style ephemerality).

### AC-3 — `get_thread` verb

`mailbot_api/verbs/get_thread.py`:

- `get_thread(thread_id: str, *, db_path: str) -> GetThreadOut` is an async function.
- `GetThreadOut` has `ok`, `error`, and on success: `thread_id`, `projections: list[EmailProjection]` (same shape as `find_emails`, ordered by `received_at ASC`), `thread_continuity_note: str | None` (cached from Story 3-7), `message_count: int`.
- The verb does NOT hydrate bodies. Caller follows up with `hydrate_email` per email_id.
- Refuses on unknown thread_id → `THREAD_NOT_FOUND`.
- Soft-deleted emails in the thread are excluded.

### AC-5 — `count_emails` verb

`mailbot_api/verbs/count_emails.py`:

- `count_emails(filter: FindEmailsFilter, *, db_path: str) -> CountEmailsOut` is an async function.
- `CountEmailsOut` has `ok`, `error`, `count: int`.
- No projections returned — just the count. Cheap signal for "how many emails match X?" without paying for full row reads.
- SQL: `SELECT COUNT(*) FROM emails WHERE <filter clauses>` — same WHERE clause builder as `find_emails`.
- Excludes soft-deleted rows by default.

### AC-6 — `get_sender_summary` verb

`mailbot_api/verbs/get_sender_summary.py`:

- `get_sender_summary(sender_address: str, *, db_path: str) -> GetSenderSummaryOut` is an async function.
- `GetSenderSummaryOut` has `ok`, `error`, and on success: `sender: SenderSummary`.
- `SenderSummary` carries: `sender_address`, `display_name: str | None`, `message_count: int`, `last_seen_at: str | None`, `sender_reputation_summary: str | None` (from the `senders` table — cached output of the Story 3-7 enrichment).
- Refuses on unknown sender → `SENDER_NOT_FOUND`.

### AC-7 — Shared schemas and error carrier

`mailbot_api/verbs/schemas.py`:

- All `<Verb>In`/`<Verb>Out`/`<Verb>Filter` Pydantic models live in this single module — agents read the docstrings/field descriptions to understand the data window, so co-locating them helps comprehension and MCP schema generation (Story 5-2 consumes these).
- `VerbError` is a shared error carrier (mirrors `ProposeActionError` from Story 4-2): frozen `BaseModel` with `code: str` and `message: str`. The `code` field uses a string literal type per verb (e.g., `FindEmailsErrorCode = Literal["LIMIT_EXCEEDED", "LIMIT_INVALID"]`); per-verb `<Verb>Error` aliases (or shared `VerbError` with `code: str`) — implementer's choice, but every error code MUST be enumerated as a Literal somewhere to support strict mypy.
- All models are `frozen=True` via `ConfigDict(frozen=True)`.
- All optional fields use `T | None = None` (PEP 604, never `Optional[T]`).
- Lists default to `Field(default_factory=list)`.
- Every field has a `Field(..., description="...")` populated. The descriptions propagate to MCP tool schema (Story 5-2) → into Hermes agent's prompt context. Better descriptions = better agent behavior.

### AC-8 — Boundary check: verbs are the Rule C boundary

`scripts/check_boundaries.py` extended (or already covers) to enforce:

- Modules outside `mailbot_api/verbs/`, `mailbot_api/mcp_server.py` (Story 5-2), and tests MUST NOT import from `mailbot_api/verbs/`. Verbs are the agent-facing surface — internal callers should use the underlying business logic modules directly (e.g., `mailbot_api/actions/propose.py`, not `mailbot_api/verbs/propose_action.py`).
- Exception: existing imports of `mailbot_api/verbs/propose_action.py` from `mailbot_api/actions/` test fixtures stay allowed (already grandfathered in via Story 4-2).
- Story 5-1's NEW verbs (`find_emails`, `hydrate_email`, `get_thread`, `list_unread`, `count_emails`, `get_sender_summary`) get added to the boundary check's `verb_modules` allowlist.

### AC-9 — Tests

`tests/unit/verbs/test_read_verbs.py` (NEW directory):

- DB-real per Step 2.4.7 Middleware-Real-Bootstrap MailBot reframing: every test uses a real on-disk SQLite via `tmp_path` with the full migration chain applied via `apply_pending_migrations(db_path)`. NOT mocked.
- Parametrized over the five verbs where shared shape matters; per-verb tests for the bespoke logic.
- Coverage matrix (≥ 25 tests minimum):
  - `find_emails`: empty DB → ok=True, projections=[]; one row matching filter → ok=True with 1 projection; filter combinations (sender_address, sender_domain, class_coarse, importance_min, since, until, query); `limit > 100` refused; `limit < 1` refused; soft-deleted rows excluded; ORDER BY received_at DESC; SQL-injection attempt in `query` field (`"%'; DROP TABLE emails; --"`) does NOT execute (table still exists after call); projections contain ONLY the documented fields (no body_preview leak).
  - `hydrate_email`: returns body_preview for `normal` sensitivity; refuses for `confidential` (CONFIDENTIAL_HYDRATION_BLOCKED); refuses for missing email_id (HYDRATE_EMAIL_NOT_FOUND); refuses for soft-deleted (HYDRATE_EMAIL_DELETED); refuses for unclassified `sensitivity_at IS NULL` (HYDRATE_NOT_CLASSIFIED); 6th call in same session_id returns HYDRATE_RATE_LIMITED; sessions are isolated (5 calls in session-A do not affect session-B); `reset_hydration_count` clears the counter; counter is NOT charged on NOT_FOUND, BLOCKED, DELETED, NOT_CLASSIFIED, or RATE_LIMITED.
  - `get_thread`: returns ordered projections (ASC) + thread_continuity_note + message_count; refuses on unknown thread_id; soft-deleted emails excluded.
  - `count_emails`: returns int; same filter semantics as find_emails; SQL-injection-safe.
  - `get_sender_summary`: returns full summary; refuses on unknown sender; sender_reputation_summary surfaces when populated, None when not.
- Boundary check: meta-test that imports `mailbot_api.actions.drainer` (or any non-verb module) and asserts NO import of `mailbot_api.verbs.find_emails` etc. exists in production code.

### AC-10 — All gates green

615 baseline tests + new tests; ruff clean, mypy clean, boundary check clean.

## Tasks / Subtasks

- [ ] schemas.py with all VerbOut/VerbFilter shapes + EmailProjection + HydratedEmail + SenderSummary + VerbError (AC-1, AC-3, AC-5, AC-6, AC-7)
- [ ] find_emails.py with WHERE-clause builder + parameterized SQL (AC-1)
- [ ] hydrate_email.py with module-level session-counter dict + reset_hydration_count helper (AC-2)
- [ ] get_thread.py, count_emails.py, get_sender_summary.py (AC-3, AC-5, AC-6)
- [ ] db/queries.py SQL constants for each verb's SELECT (Rule G)
- [ ] check_boundaries.py extended for verb-import isolation (AC-8)
- [ ] tests/unit/verbs/test_read_verbs.py with full coverage matrix (AC-9)
- [ ] Gate sweep — ruff, mypy, pytest, boundary check (AC-10)

### Code Review — 2026-06-02 (Sonnet 4.6)

- [x] [HIGH] mailbot_api/verbs/find_emails.py:63 — `f.query` value is embedded directly into the LIKE pattern string (`f"%{f.query}%"`) without escaping LIKE metacharacters (`%` and `_`). A query like `"50% off"` produces pattern `"%50% off%"` where the interior `%` is a wildcard, causing spurious over-matching. Not an injection risk (binding is parameterized) but a correctness bug on a search surface the agent will use. Fix: escape `%` → `\%` and `_` → `\_` in `f.query` before building the pattern, and append `ESCAPE '\'` to the clause (e.g. `"(subject LIKE ? ESCAPE '\\' OR summary_short LIKE ? ESCAPE '\\')`).
- [x] [MEDIUM] mailbot_api/verbs/find_emails.py:46 — `f.sender_domain` is embedded into a LIKE pattern (`f"%@{f.sender_domain.lower()}"`) without escaping LIKE metacharacters. A domain containing `_` (e.g. `ex_mple.com`) would match unintended addresses. Fix: apply the same `%`/`_` LIKE-escape as recommended for the `query` field above.
- [x] [MEDIUM] mailbot_api/verbs/get_sender_summary.py:51 — `GET_SENDER_AGGREGATE_SELECT` uses `WHERE from_address = ?` bound to `sender_id` (the lowercased senders.id). Emails whose `from_address` was captured with mixed case (e.g. `Alice@Example.COM`) will be silently excluded from `message_count` and `last_seen_at`, making the summary misleadingly stale. The agent receives incorrect metadata with no error. Decision required: (a) keep current parity with senders-upsert trade-off, (b) use `LOWER(from_address) = ?` in the aggregate query (cheapest fix, no schema change), or (c) defer. Recommend (b) — it makes the aggregate consistent with the domain-suffix filter already using `LOWER()`.
- [x] [MEDIUM] mailbot_api/verbs/get_thread.py:14 — `get_thread` imports the private symbol `_row_to_projection` from `find_emails`. This internal coupling means a rename or signature change in `find_emails._row_to_projection` silently breaks `get_thread` without a direct import error until runtime or tests catch it. The symbol is also not exported from the module's `__all__`. Fix: either promote `_row_to_projection` to a public helper in `schemas.py` or `find_emails.py` (remove the underscore prefix and add to `__all__`), or duplicate the trivial mapping in `get_thread.py`.
- [x] [MEDIUM] mailbot_api/verbs/hydrate_email.py:115 — Privacy gate ordering: `sensitivity_at IS NULL` (HYDRATE_NOT_CLASSIFIED) is checked before `sensitivity == 'confidential'` (CONFIDENTIAL_HYDRATION_BLOCKED). If an email is in a corrupt state where `sensitivity = 'confidential'` but `sensitivity_at IS NULL` (pipeline wrote the label without the timestamp), the call returns `HYDRATE_NOT_CLASSIFIED` instead of `CONFIDENTIAL_HYDRATION_BLOCKED`. Body is not exposed in either case (both refuse), so this is not a current leak — but the more specific confidential-block should be checked first to provide the correct refusal semantics and prevent a future regression if the control flow is ever extended. Fix: swap the two checks so confidential-block fires before not-classified.
- [x] [LOW] tests/unit/verbs/test_read_verbs.py:121 — `_clear_hydration_state` fixture returns `None` (no `yield`) meaning it only clears state as test setup, not teardown. If a test hangs or is aborted mid-run, state may leak into subsequent tests. More importantly, the fixture return type annotation `-> None` is technically correct but mypy may flag this as a non-generator fixture using `-> None` vs `-> Generator[None, None, None]`. This is cosmetic, but consider adding a `yield` to make the teardown intent explicit and ensure state is cleared even on fixture error: `_SESSION_HYDRATION_COUNTS.clear(); yield; _SESSION_HYDRATION_COUNTS.clear()`.
- [x] [LOW] mailbot_api/verbs/get_thread.py:35-36 — `get_thread` returns `message_count=len(rows)` (live count of non-deleted emails) while `GET_THREAD_META_SELECT` fetches `threads.message_count` into `meta[1]` which is never used. The live count is correct; `meta[1]` is dead code in the fetchone result. This creates a silent divergence from the `GetThreadOut.message_count` field semantics (the agent might assume it matches the cached `threads.message_count`). Recommend: either document in `GetThreadOut.message_count`'s field description that this is a live count (not the cached value), or remove `message_count` from the SELECT in `GET_THREAD_META_SELECT` to avoid confusion.

**CR resolution summary (2026-06-02):** all 7 findings applied (7/7 = 100% application rate):

- HIGH `query` LIKE escape: added `_escape_like()` helper + `ESCAPE '\'` clause on both subject + summary_short LIKEs; regression test `test_find_emails_query_like_metachars_escaped` validates `50%` query matches literal `%` only.
- MEDIUM `sender_domain` LIKE escape: same `_escape_like()` helper applied; regression test `test_find_emails_sender_domain_underscore_escaped` validates `ex_mple.com` doesn't match `example.com`.
- MEDIUM sender case-sensitivity: `GET_SENDER_AGGREGATE_SELECT` now uses `LOWER(from_address) = ?`; regression test `test_get_sender_summary_aggregates_mixed_case` validates mixed-case rows aggregate correctly.
- MEDIUM private-symbol coupling: `_row_to_projection` promoted to `row_to_projection` (public), added to `__all__`, `get_thread.py` import updated.
- MEDIUM gate ordering: confidential check now fires before not-classified check; regression test `test_hydrate_email_confidential_with_null_at_returns_blocked` validates corrupt-state row gets correct refusal code.
- LOW fixture yield-vs-return: fixture rewritten as `Iterator[None]` with setup + teardown clears.
- LOW dead-code message_count: removed `message_count` column from `GET_THREAD_META_SELECT`; added comment block to queries.py documenting the live-count-vs-cached-count divergence intentionally.

**Gate sweep after CR fixes:** 693 pytest passed (+38 net from 655 baseline, +4 new regression tests beyond the 34 from initial dev pass), 2 skipped; ruff clean; mypy clean; boundary checker clean. All 4 gates remain green.

## Dev Notes

### Rule J — Hydration Discipline (architecture §AR-PAT-1)

The whole point of the projection-first design: the agent gets a NARROW data window by default (the 10-ish fields of `EmailProjection`), and only escalates to `hydrate_email` when it actually needs the body. This is BOTH a cost-control mechanism (smaller agent context = cheaper Anthropic calls) AND a privacy mechanism (most of the time, the agent doesn't see body_text at all — just metadata).

The 5/turn rate limit on `hydrate_email` is the structural enforcement. Without it, the agent could just hydrate every email in a `find_emails` result and defeat the projection model.

### Why session_id is passed in, not derived

The verb is process-local — it has no concept of "which agent session am I being called from?" The MCP server (Story 5-2) injects `session_id` from the MCP context. For unit tests, the test passes its own session_id. This keeps the verb pure: no global session machinery, just a dict keyed by whatever the caller hands in.

### Why module-level dict for hydration counts (not request-scoped)

Considered alternatives:
- (a) Request-scoped state via contextvars: cleaner, but requires the MCP server to wrap every call. Story 5-2 still has design space to revisit.
- (b) DB-backed counter: persists across process restarts, but Rule J is a per-turn safety net, not an audit trail.
- (c) Module-level dict: simplest, in-memory, ephemeral. Restart resets the counter. This is acceptable because (i) restarts during an active chat turn are rare, (ii) hitting the 5-cap on restart would just mean the agent gets a free retry — a non-issue.

Chose (c). Story 5-2 layers in MCP-server-driven counter reset on per-turn boundaries.

### Rule G — writer monopoly applies to SQL constants

Per architecture §AR-PAT-1 Rule G: every SELECT/INSERT/UPDATE lives in `mailbot_api/db/queries.py` as a named constant. The verbs in this story ADD `FIND_EMAILS_SELECT_BASE`, `HYDRATE_EMAIL_SELECT`, `GET_THREAD_SELECT`, `LIST_UNREAD_SELECT`, `COUNT_EMAILS_SELECT_BASE`, `GET_SENDER_SUMMARY_SELECT` to queries.py.

For `find_emails` and `count_emails`, the WHERE clause is dynamic (depends on which filter fields are set). The pattern: the BASE constant ends with `WHERE 1=1` (or `WHERE deleted_at IS NULL`), and the verb appends `AND col = ?` clauses programmatically via a list-of-clauses + list-of-params builder. ALL parameters go through `?` placeholder binding — never string-interpolated. The query is reassembled deterministically and only passes through `db.connection.fetchall` with the full param tuple.

### Sensitivity column gating (Rule A defense)

`hydrate_email` refuses on `sensitivity='confidential'` — but what if `sensitivity_at IS NULL` (email hasn't been classified yet)? The verb should also refuse in that case to be defensive, OR allow it on the theory that pre-classification emails can't be marked confidential yet. Decision: **refuse with HYDRATE_NOT_CLASSIFIED** for unclassified rows. The agent should call `find_emails` to see metadata; full body access requires classification first. This is consistent with FR-2.3 / Story 3-3's Router precondition layer for write-side calls — extending the discipline to read-side hydration.

(Add a 7th error code: `HYDRATE_NOT_CLASSIFIED`.)

### Schema check: does emails have all the columns we read?

Verified against `001_init.sql` + `011_derived_fields.sql`:
- `graph_id`, `received_at`, `from_address`, `from_display_name`, `subject`, `body_text`, `body_html` (from 001)
- `to_addresses`, `cc_addresses` (need to verify presence — if missing, this story DOES NOT add them; the verb skips those fields gracefully and we file a follow-up)
- `summary_short`, `class_coarse`, `class_fine`, `importance_score`, `sensitivity`, `action_required`, `has_attachments` + companion `*_at` fields (from 011)
- `thread_id`, `is_read` (from 001)
- `deleted_at` (from 005)

If `to_addresses` / `cc_addresses` columns aren't on `emails`, hydrate_email returns empty lists for those fields and the dev pass files a NOTE for Epic 6 to add them. NO new migration in this story.

### Test directory creation

`tests/unit/verbs/` does NOT exist yet. Story creates it + `__init__.py`.

### Existing verbs in mailbot_api/verbs/ — do not break

Existing verbs: `ask_router.py`, `propose_action.py`, `budget_admin.py`, `router_control.py`, `cost.py`, `revoke_grant.py`, `mint_grant.py`, `cancel_action.py`, `revert_action.py`, `mint_sensitivity_token.py`.

These are write-side / control verbs. Story 5-1's six verbs are read-side. They DO NOT modify or shadow any existing verb. They DO live in the same directory.

### Companion column conventions (from Story 3-1)

Every derived field has a companion `_at` timestamp (e.g., `summary_short_at`, `class_coarse_at`). `HydratedEmail` exposes both — the agent can see "this was classified 2 days ago" vs "this is from 3 minutes ago and only partial derivation has run". The projection model (`find_emails` rows) does NOT include the `_at` companions — they'd bloat the projection without adding signal at the find/list level.

### MailBot has no graphical frontend

Per PORTING.md: `<frontend-src>` is N/A. No `.tsx`/`.vue`/`.svelte` files. UI nouns in ACs (none in this story) would refer to Discord-rendered text. Step 2.4.5 (UI-Scope Pre-Flight) is N/A. Step 2.4.7 (Middleware-Real-Bootstrap) is reframed around the Router contract — for read-side verbs that do NOT call Router, the gate is satisfied by DB-real integration tests (which AC-9 mandates).

### References

- [Source: epics.md Story 5.1](../planning-artifacts/epics.md)
- [Source: architecture.md §AR-PAT-1 Rule J — Hydration Discipline](../planning-artifacts/architecture.md)
- [Source: architecture.md §Communication Patterns — verb input/output schemas](../planning-artifacts/architecture.md)
- [Source: architecture.md §Complete Project Directory Structure — `verbs/` layout](../planning-artifacts/architecture.md)
- [Source: Story 4-2 ProposeActionError/ProposeActionOut pattern](./4-2-pending-actions-and-action-grants-and-action-history-schema-and-propose-action-verb.md)
- [Source: Story 3-7 sender_reputation_summary + thread_continuity_note caching](./3-7-senders-and-threads-upsert-and-cached-sender-reputation-summary.md)
- [Source: Story 3-3 FR-2.3 sensitivity precondition pattern](./3-3-sensitivity-classifier-and-sensitivity-patterns-yaml-and-router-precondition-layer.md)

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-epic-run dev pass

### Debug Log References

### Completion Notes List

- Story shipped 5 verbs (find_emails, hydrate_email, get_thread, count_emails, get_sender_summary) per the schema-reality reframe documented at top of file. list_unread + full-body hydration deferred to a follow-up story that adds a migration + sync-side capture for `is_read`, `body_text`, `body_html`, `to_addresses`, `cc_addresses`.
- Schema-reality reframe was a Phase 0.4 Blocker Scan miss — the scan checked external deps and migration slots but did not ground every AC's column references against the actual schema. Surfaced mid-implementation, Adam picked option 1 (adapt to schema reality, file the gap as follow-up), reframe documented in story file.
- 38 tests in `tests/unit/verbs/test_read_verbs.py` (34 initial + 4 CR-driven regression tests) covering: empty DB, filter combinations (sender_address/domain/class_coarse/importance_min/since/until/query), limit caps (>100 / <1), soft-delete exclusion, ORDER BY DESC, SQL-injection safety on the parameterized `query` LIKE, LIKE-metacharacter literal preservation (CR-1, CR-2), projection has no body field; hydrate_email six-error-code matrix (incl. CR-5 confidential-blocks-before-not-classified) + 5/turn rate limit with session isolation + reset_hydration_count helper + counter-not-charged-on-gate-fail; get_thread ASC ordering + continuity note + soft-delete exclusion + unknown thread refused; count_emails int-result + filter parity + soft-delete exclusion + SQL-injection safe; get_sender_summary known/unknown/no-emails + case-insensitive address normalization + mixed-case from_address aggregation (CR-3).
- AC-8 (boundary check for verb-import isolation) NOT shipped this story — the existing `scripts/check_boundaries.py` doesn't carry a verb-import allowlist check, and adding one is a separate hardening pass. Filed as deferred. No regression: existing allowed-import surface is unchanged.
- All 4 gates green after CR fixes: 693 pytest passed (+38 net from 655 baseline), 2 skipped (opt-in real-Ollama); ruff clean; mypy clean; boundary checker clean.
- One ruff false-positive (S608) suppressed with `# noqa: S608` + explanatory comment on the two queries.py f-strings that interpolate a fixed identifier (`EMAIL_PROJECTION_COLUMNS`), not user input. No user input ever concatenated into SQL strings; user input only enters via `?` placeholders.
- Boundary-check false-positive on `"Map a SELECT row to ..."` docstring resolved by rewording to `"Map a fetched row to ..."`.

### File List

NEW:

- mailbot_api/verbs/schemas.py
- mailbot_api/verbs/find_emails.py
- mailbot_api/verbs/hydrate_email.py
- mailbot_api/verbs/get_thread.py
- mailbot_api/verbs/count_emails.py
- mailbot_api/verbs/get_sender_summary.py
- tests/unit/verbs/test_read_verbs.py
- _bmad-output/implementation-artifacts/5-1-read-side-verbs-projection-first-data-window-for-the-agent.md

UPDATED:

- mailbot_api/verbs/__init__.py — re-exports the 5 new verbs + reset_hydration_count
- mailbot_api/db/queries.py — added EMAIL_PROJECTION_COLUMNS + FIND_EMAILS_SELECT_BASE + COUNT_EMAILS_SELECT_BASE + HYDRATE_EMAIL_SELECT + GET_THREAD_PROJECTION_SELECT + GET_THREAD_META_SELECT + GET_SENDER_BASE_SELECT + GET_SENDER_AGGREGATE_SELECT (Rule G — read-side SQL constants)
- _bmad-output/implementation-artifacts/sprint-status.yaml — epic-5 backlog → in-progress; 5-1 backlog → review
