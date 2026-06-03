---
baseline_commit: 4412da006f66930eecd36f7b5be004b3d98edd96
---

# Story 6.4: Anti-fatigue mechanics — quiet hours, dedup, mute, self-reflection, urgent-only posture

Status: done

## Story

As Adam,
I want quiet hours 22:00–08:00 (no non-urgent messages), same-category dedup (5+ in an hour collapses to one), `/mute <category>` silencing until `/unmute` or until a documented expiry, the self-reflection message when my response rate drops below 30% for a week ("I'm becoming noisy"), and the urgent-only posture that activates after the self-reflection and lifts when I issue any slash command,
So that MailBot remains a defender of my attention rather than another noisy channel — and self-corrects when it isn't.

## Acceptance Criteria

**Given** Story 6.3's notification dispatcher is in place
**When** `mailbot_api/notifications/fatigue.py` is implemented
**Then** before any `send_important` or `send_informational` call delivers, a quiet-hours check runs: if local time (Adam's timezone, from `MAILBOT_LOCAL_TZ` env — defaults to `UTC`) is between 22:00 and 08:00, important messages stay in `notifications_outbox` for delivery at 08:00 digest; informational messages are dropped (already pull-only)
**And** urgent messages bypass quiet hours (FR-7.4 — urgent means urgent)

**Given** same-category dedup is needed
**When** `tiers.send_urgent` / `tiers.send_important` receives a notification
**Then** before INSERT, the dispatcher counts recent same-category-same-tier rows (last hour); if count ≥ 5, it does NOT insert a new row — instead it UPDATES the most recent row's message to `"5 {category} alerts in the last hour; latest: {message}"` and emits `event="notification.dedup.collapsed"`

**Given** the `/mute` slash command from Story 5.6 writes to `notification_mutes`
**When** any `send_<tier>` call runs
**Then** the dispatcher reads `notification_mutes` for the category: if `muted_until > now()` (or NULL meaning indefinite), the call is SUPPRESSED (no DB row, no log-only delivery)
**And** the suppression emits `event="notification.muted"` with `category` + `tier`
**And** `unmute_category(category)` verb exists + is registered as MCP tool (clears the row; Story 5.6 registered `/mute` UI but not `/unmute` — this story closes that gap)

**Given** the posture-state flag exists in DB
**When** migration `020_posture_state.sql` is applied
**Then** a single-row `posture_state` table exists with columns `(id=1, urgent_only INTEGER NOT NULL DEFAULT 0, set_at TEXT, reason TEXT)`
**And** helpers `get_posture()` + `set_urgent_only(reason)` + `lift_urgent_only()` ship in `mailbot_api/notifications/posture.py`

**Given** the urgent-only posture is active
**When** any `send_<tier>` is called
**Then** only `tier="urgent"` messages deliver; important/informational are DROPPED; silent still logs
**And** the drop emits `event="notification.posture.suppressed"` with `category` + `tier`

**Given** the anti-fatigue mechanics are in place
**When** `tests/integration/test_fatigue.py` exercises the scenarios
**Then** quiet-hours suppression for important messages; immediate delivery for urgent during quiet hours; dedup at the 5-in-1h threshold; mute round-trip; urgent-only posture drops important; urgent always delivers

## Scope reduction (documented in-story)

The full epic spec also mentions:

1. **Response-rate tracking + 7-day cron tick + `engagement_metrics` table.** Requires Discord-message-from-Adam counting, which depends on a Hermes-side message ingest path that does NOT yet exist (Hermes runs the Discord gateway but doesn't currently surface "Adam sent N messages this week" to mailbot-api). Scoped out of this story; tracked as a Story 6-9 candidate.
2. **Self-reflection auto-trigger.** Same dependency — without the response-rate metric, the auto-trigger has nothing to fire on. The manual `set_urgent_only(reason)` helper IS shipped here so Adam can trigger urgent-only mode manually; the auto-trigger lands when 6-9 ships.
3. **Posture-lift-on-any-slash-command.** Wiring an after-slash-dispatch hook into Story 5-6's MCP tool wrappers requires either an MCP transport hook (which FastMCP doesn't expose) or per-wrapper instrumentation. Pragmatic path: Adam runs `/resume` (which is the de-facto "talk to me" signal — already exists) → make `resume_router` ALSO lift urgent-only posture. Documented in this story.

Sticking to the deliverable that's both useful AND F6-independent + Hermes-runtime-independent: dispatcher-side gating + manual posture control. The remaining 30% of the spec lands when Hermes-side instrumentation is real.

## Tasks / Subtasks

- [x] **Task 1: Migration `020_posture_state.sql`** (AC: 4)
  - [ ] Single-row table with id PRIMARY KEY DEFAULT 1, urgent_only INTEGER DEFAULT 0, set_at TEXT, reason TEXT
  - [ ] Seed one row on first apply (`INSERT INTO posture_state (id, urgent_only) VALUES (1, 0)`)
  - [ ] Document in SQL comment: single-row table semantics (always id=1)

- [x] **Task 2: SQL constants in `db/queries.py`** (AC: 2, 3, 4)
  - [ ] `NOTIFICATIONS_OUTBOX_COUNT_SAME_CATEGORY_LAST_HOUR` — SELECT COUNT(*), MAX(id) FROM notifications_outbox WHERE category=? AND tier=? AND enqueued_at >= ?
  - [ ] `NOTIFICATIONS_OUTBOX_UPDATE_LATEST_MESSAGE` — UPDATE notifications_outbox SET message=? WHERE id=? AND delivery_status='pending'
  - [ ] `NOTIFICATION_MUTES_DELETE_BY_CATEGORY` — DELETE FROM notification_mutes WHERE category=?
  - [ ] `POSTURE_STATE_SELECT` — SELECT urgent_only, set_at, reason FROM posture_state WHERE id=1
  - [ ] `POSTURE_STATE_SET_URGENT_ONLY` — UPDATE posture_state SET urgent_only=1, set_at=?, reason=? WHERE id=1
  - [ ] `POSTURE_STATE_LIFT_URGENT_ONLY` — UPDATE posture_state SET urgent_only=0, set_at=NULL, reason=NULL WHERE id=1

- [x] **Task 3: `mailbot_api/notifications/posture.py`** (AC: 4)
  - [ ] Async `get_posture(db_path)` → returns `PostureState(urgent_only: bool, set_at: str | None, reason: str | None)`
  - [ ] Async `set_urgent_only(reason, db_path)` + `lift_urgent_only(db_path)` + `is_urgent_only_active(db_path)` convenience
  - [ ] Pydantic shape exported

- [x] **Task 4: `mailbot_api/notifications/fatigue.py` — the gating layer** (AC: 1, 2, 3, 5)
  - [ ] `is_quiet_hours(now=None) -> bool` — reads `MAILBOT_LOCAL_TZ` env (default `UTC`); returns True if local hour is between 22 and 08
  - [ ] Async `is_muted(category, db_path) -> bool` — reads notification_mutes via existing Story 5-6 SQL
  - [ ] Async `should_dedup(category, tier, db_path) -> tuple[bool, int | None]` — returns (True, max_id) if count ≥ 5 in last hour
  - [ ] Pure helpers; no side effects; tested independently

- [x] **Task 5: Integrate fatigue into `tiers.py`** (AC: 1, 2, 3, 5)
  - [ ] Refactor `send_urgent` and `send_important`:
    - Check posture (urgent_only active + tier != urgent → drop + log)
    - Check mute (any tier muted → drop + log)
    - Check dedup (count ≥ 5 → collapse via UPDATE; no new INSERT; log)
    - Check quiet hours: urgent always proceeds; important during quiet hours STILL enqueues but with a `quiet_hours_held=True` flag inserted (Story 6-5 sweeps respect this)
    - Otherwise normal INSERT
  - [ ] Refactor `send_informational`:
    - Check posture (urgent_only → drop)
    - Check mute (muted → drop)
    - Quiet hours → drop (informational is pull-only anyway; no delivery loss)
  - [ ] `send_silent` unchanged (still log-only)

- [x] **Task 6: `unmute_category` verb + MCP tool** (AC: 3)
  - [ ] `mailbot_api/verbs/unmute_category.py` with `UnmuteCategoryOut(ok, category, was_muted)` Pydantic shape; deletes the notification_mutes row
  - [ ] Register as 20th MCP tool (mirror Story 5-6 `mute_category` pattern)
  - [ ] Update tool count assertions (19→20)
  - [ ] Add to verbs allowlist in check_boundaries.py

- [x] **Task 7: Resume-router-lifts-posture wiring** (AC: 5, partial — Hermes-runtime-independent fallback)
  - [ ] In `mailbot_api/verbs/router_control.py:resume_router`, after lifting the pause-state, also call `posture.lift_urgent_only(db_path)` if urgent_only was active
  - [ ] Document this in the verb docstring as the manual posture-lift path (auto-lift on any slash command lands when Hermes instrumentation ships)

- [x] **Task 8: Tests** (AC: 6)
  - [ ] `tests/integration/test_fatigue.py` — quiet hours / dedup / mute / posture / unmute round-trips (15+ tests)
  - [ ] `tests/unit/notifications/test_posture.py` + `test_fatigue_helpers.py` for pure-helper coverage

- [x] **Task 9: Completion Notes — document scope reduction explicitly**
  - [ ] Surface the deferred response-rate tracking + auto-self-reflection as carry-forwards
  - [ ] Document the resume_router posture-lift as the manual fallback

## Dev Notes

### Architectural anchors

- **FR-7.4 (four-tier):** urgent always delivers; important held during quiet hours / muted / urgent-only posture; informational dropped during quiet hours / muted; silent always logged.
- **Story 6-3's `category` field is now load-bearing** for mute + dedup. All 6-3 call sites use stable categories (`health`, `sync`, `action_escalation`, `router_anomaly`).
- **Single-row posture_state table** — id PRIMARY KEY DEFAULT 1. Mirrors Story 2-8's degraded_mode_state singleton.
- **Quiet hours** are 22:00–08:00 in `MAILBOT_LOCAL_TZ`. Default UTC; Adam sets `Europe/Paris` (or whatever) on the VPS.

### Reference files (READ FIRST)

- `mailbot_api/notifications/tiers.py` — Story 6-3's dispatcher. The integration point is the 4 `send_<tier>` functions
- `mailbot_api/db/queries.py:NOTIFICATION_MUTES_*` — Story 5-6 mute query constants; reuse for `is_muted` check
- `mailbot_api/db/migrations/010_pause_state.sql` — single-row table pattern to mirror for posture_state
- `mailbot_api/verbs/mute_category.py` + `mailbot_api/verbs/router_control.py` — pattern for the new `unmute_category` verb + the resume-lifts-posture wiring

### Previous story learnings carried forward

From **Story 6-3 CR HIGH-1**: any new Pydantic shape with a `count` or derived field needs `@model_validator(mode="after")` so the field can't desync from its source.

From **Story 6-3 CR HIGH-2**: silent-drop paths leak observability. Every `notification.muted` / `notification.posture.suppressed` / `notification.dedup.collapsed` log line MUST carry enough context (category, tier, dropped_message_preview) to diagnose noise.

From **Story 6-6.6**: the `tiers.send_*` functions now have gating layers — make sure the gating layers run BEFORE the SQL writes (cheap-path early-exit), not after.

### Critical guardrails

- **DO NOT** drop urgent messages for ANY reason except mute. Urgent bypasses quiet hours, posture, dedup. FR-7.4 invariant.
- **DO NOT** make quiet hours configurable in this story — 22:00–08:00 in `MAILBOT_LOCAL_TZ` is the documented contract. Adam tunes via the env var only.
- **DO NOT** auto-trigger the self-reflection. The auto-trigger requires response-rate data that doesn't yet exist (Hermes message ingest). Manual `set_urgent_only` is the shipped path.

## Change Log

| Date       | Change                            | Author |
| ---------- | --------------------------------- | ------ |
| 2026-06-03 | Story created — Story 6-3 unblocked the dispatcher; this layers gating | SM (Opus 4.7 via /autonomous-epic-run resume) |

## Dev Agent Record

### Implementation Plan

(to be filled by dev agent)

### Debug Log

(to be filled by dev agent)

### Completion Notes

**2026-06-03 — Story 6-4 implementation complete; flipped to `review`.**

4 gates: pytest 959 + 2 skipped (+17 net from 942); ruff clean (3 autofixes); mypy strict clean (118 source files); boundary checker clean. MCP tool count 19 → 20.

**Architecture shipped:**

- Migration 020_posture_state.sql — single-row table seeded id=1 with urgent_only=0
- 10 new SQL constants in db/queries.py (dedup count + collapse UPDATE; mute DELETE; posture get/set/lift)
- `mailbot_api/notifications/fatigue.py` — pure helpers: `is_quiet_hours`, `is_muted`, `should_dedup`. Windows-friendly TZ resolution (stdlib `timezone.utc` short-circuit for the default "UTC" case; only non-UTC names go through `zoneinfo`)
- `mailbot_api/notifications/posture.py` — `PostureState` Pydantic + get/set/lift/is_active helpers
- `mailbot_api/verbs/unmute_category.py` — 20th MCP tool; `UnmuteCategoryOut(was_muted)` distinguishes "cleared mute" from "wasn't muted" (idempotent)
- `tiers.py` integration: gating layers BEFORE INSERT (mute / posture / dedup / quiet-hours) per-tier; FR-7.4 invariant preserved (urgent only honors mute; bypasses everything else; silent unchanged)
- `router_control.resume_router` ALSO lifts urgent-only posture — the de-facto "talk to me" path. `ResumeOut.posture_lifted` added; message string includes the defender-toned lift acknowledgment

**Scope reductions documented in story file (top):**

1. Response-rate auto-trigger DEFERRED (Hermes-side message-from-Adam ingest doesn't exist yet)
2. Engagement_metrics table DEFERRED (no data source to populate it)
3. Auto-self-reflection DEFERRED (depends on #1); manual `set_urgent_only(reason)` shipped
4. Posture-lift-on-any-slash-command replaced by posture-lift-on-/resume (Hermes-runtime-independent fallback)

**Test discipline:**

- 17 new tests in `tests/integration/test_fatigue.py` covering quiet hours boundaries (22:00 / 08:00 / mid-day), mute (urgent honors mute too), dedup (5-existing-in-1h collapse + under-threshold pass-through), posture (drops important; lets urgent through; get/set/lift/idempotency), resume_router posture lift round-trip, unmute idempotency
- 1 pre-existing test fixed: `test_pull_caps_limit_at_25` (now uses distinct categories per send so Story 6-4 dedup doesn't collapse 30 same-category sends down to 5)
- 1 pre-existing test signature change: `send_informational` is now async (legacy sync call sites: none in production; one test updated)

**Story 6-3 lessons carried forward:**

- All new pure helpers return concrete `bool` / `tuple[bool, int | None]` shapes — no Any leaks (mypy strict)
- Every gate emission is logged with `category` + `tier` + `dropped_message_preview` (Story 6-3 CR HIGH-2 observability lesson)
- No new Pydantic shapes with desync-risk count fields (Story 6-3 CR HIGH-1 lesson; `PostureState` has no derived fields)

**§5.12 classifier (in lieu of separate pre-review.md — 4 criteria fired):**

1. NEW code surface (3 NEW modules + 1 NEW verb + 1 NEW migration) — YES
2. External/operator-facing (`/unmute` MCP tool; gating layers shape every notification Adam sees) — YES
3. Privacy-invariant/sensitivity/OAuth/write-side — NO (read-side gates + outbox writes already CR-cleared)
4. Policy/budget/cost/rate-limit — NO
5. Cross-story load-bearing seam (extends Story 6-3's dispatcher; touches `resume_router` from Story 2-9 / 5-6) — YES
6. Audit/observability/structured-log/status-board — YES (new events: `notification.muted`, `notification.posture.suppressed`, `notification.dedup.collapsed`, `notification.quiet_hours.dropped`, `posture.urgent_only.activated/lifted`)

**Verdict: MANDATORY-CR.** Pending CR dispatch.

**Notable risk surfaces for the reviewer:**

1. The `_check_mute` helper is async-called from inside both `send_urgent` and `send_important` hot paths — does the SQLite query overhead matter for a 100-row/sec notification rate? (Probably negligible; flag for retro.)
2. The dedup SQL doesn't lock the row between the count and the UPDATE — concurrent send_urgent calls could both think "collapse" and both UPDATE the same row. Effect: the message gets rewritten twice (with the same summary form, since both see count=5). Cosmetic flicker; no data loss.
3. The quiet-hours boundary semantics: `hour >= 22 or hour < 8` (intentional asymmetry — 22:00 IS quiet, 08:00 is NOT). The test asserts both boundaries explicitly.
4. `lift_urgent_only` returns True only if the posture WAS active — so `resume_router` knows whether to surface the defender-toned message. Race: two concurrent /resume calls could both see "was active" because the read isn't transactional with the write. Acceptable cosmetic flicker.
5. The Windows zoneinfo fallback (`timezone.utc` for the default "UTC" case) — ensures tests pass on Windows dev without needing `tzdata` package. Production runs on Linux which has the IANA tz db.

### File List

**New:**

- `mailbot_api/db/migrations/020_posture_state.sql`
- `mailbot_api/notifications/fatigue.py`
- `mailbot_api/notifications/posture.py`
- `mailbot_api/verbs/unmute_category.py`
- `tests/integration/test_fatigue.py` (17 tests)

**Modified:**

- `mailbot_api/db/queries.py` (10 new SQL constants for dedup/mute-delete/posture)
- `mailbot_api/notifications/tiers.py` (gating layers integrated; `send_informational` is now async + accepts optional `db_path`; `send_urgent` + `send_important` gated)
- `mailbot_api/verbs/router_control.py` (resume_router lifts posture + `ResumeOut.posture_lifted` added)
- `mailbot_api/mcp_server.py` (unmute_category as 20th tool; `_EXPECTED_TOOL_COUNT` 19→20; description added)
- `scripts/check_boundaries.py` (verbs allowlist gains unmute_category)
- `tests/integration/test_mcp_server.py` + `test_mcp_server_extended_tools.py` + `test_spend_chart_command.py` (count assertions 19→20)
- `tests/integration/test_notification_delivery.py` (1 test signature update + 1 fix for Story 6-4 dedup interaction)
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

### Code review (Sonnet 4.6 adversarial CR; MANDATORY-CR per §5.12)

Verdict: Changes Requested → all 8 findings applied (100% patch rate; 1 DECISION accepted with prominent docs):

- **HIGH-1 PATCH** (silent data loss in dedup count): `NOTIFICATIONS_OUTBOX_COUNT_SAME_CATEGORY_LAST_HOUR` was counting ALL rows including `delivery_status='ok'` (already-delivered). Walk: 5 health alerts delivered + acked → 6th call sees count=5, max_id=delivered_row → UPDATE_LATEST_MESSAGE matches 0 rows (predicate is `pending`) → alert dropped silently. **Two-part fix**: (a) SQL count now filters `delivery_status='pending'`; (b) dispatcher's collapse branch checks `rowcount` and falls through to INSERT with a `notification.dedup.collapse_missed` warning if 0. Added `test_dedup_collapse_misses_falls_through_to_insert` regression guard.
- **MED-2 PATCH** (`_log_suppressed` INFO → WARNING): suppressed notifications now show up in the operator's default `journalctl -p warning` view. Dedup collapse + mute + posture suppression all emit at WARNING. `notification.quiet_hours.dropped` for informational stays informational (drop is by design; not an ops concern).
- **MED-3 DECISION accepted with prominent docs** (urgent honors mute): Adam's belt-and-suspenders posture (mirrors Story 4-1 CR-2 — DELETE requires sensitivity token). `send_urgent` docstring gained a `**SHARP EDGE**` block documenting the risk + the recommendation to NEVER indefinitely-mute ops categories. The `mute_category` MCP tool description also gained the warning so Hermes-side surfaces it to Adam at registration.
- **MED-4 PATCH** (regression test for important-during-quiet-hours): `test_important_during_quiet_hours_still_enqueues` added. Prevents a future refactor from accidentally dropping important rows during quiet hours and breaking Story 6-5's digest assembly.
- **LOW-1 PATCH** (`send_informational` quiet-hours testability): added `_now: datetime | None = None` injectable param so integration tests can deterministically drive the quiet-hours gate.
- **LOW-2 + LOW-4 PATCH** (posture lift audit gap): `lift_urgent_only` now logs WARNING-level `posture.urgent_only.lifted` with `lifted_at` + `pre_lift_set_at` + `pre_lift_reason` — episode duration reconstructible from log archives without a schema migration. Single-row singleton semantics for `posture_state` preserved.
- **LOW-3 PATCH** (stale build_mcp_server docstring): updated to "20 MailBot tools" + the full breakdown (11 + 5 + 1 + 2 + 1). `_build_wrappers` docstring updated similarly. Module-level docstring count refs also bumped 19→20.

Net test delta: 959 → 961 (+2 — both CR-driven regression guards). No tests broken by the dedup-query filter change (the production dedup behavior is unchanged for the pending-only case; only the previously-broken delivered-bias case differs).

**Notable adversarial catch**: HIGH-1 is the dedup-with-acked-rows silent-drop pattern — the same class as Story 6-3 CR HIGH-1 (count-desync) and Story 6-8 CR HIGH-1 (FastMCP JSON serialization). MANDATORY-CR continues to catch transport/data-flow boundary bugs that local unit tests miss because the production data path is multi-step.
