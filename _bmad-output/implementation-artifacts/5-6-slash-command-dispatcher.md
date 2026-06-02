---
baseline_commit: 260004f
---

# Story 5.6: Slash command dispatcher

Status: done

## Story

As Adam,
I want Discord slash commands `/cost`, `/pause`, `/resume`, `/cancel <action_id>`, `/mute <category>`, `/label <recent> <label>`, `/budget reset`, and `/confirm <email_id> <task_type>` registered with the Hermes Discord adapter and dispatched to their corresponding MCP verbs — with the new `mute_category` verb shipped as a stub (Epic 6 dispatcher will read from it), the four router-control verbs (`cost_breakdown`, `reset_degraded_mode`, `pause_router`, `resume_router`) registered on the MCP server alongside the existing 11 (closing the Story 5-2 deferral), and `hermes-config/config.yaml` extended with the slash command registry,
so that every slash command promised in Stories 2.8 / 2.9 / 2.10 / 4.6 / 4.7 finally has a human-facing surface in Discord, identical in DM and shared-server channel (FR-4.8).

## Acceptance Criteria

### AC-1 — Migration `018_notification_mutes.sql`

NEW migration file `mailbot_api/db/migrations/018_notification_mutes.sql` defines:

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS notification_mutes (
    category TEXT PRIMARY KEY,
    muted_until TEXT NULL,  -- ISO-8601 UTC Z; NULL = indefinite mute
    muted_at TEXT NOT NULL  -- ISO-8601 UTC Z
);
```

The migration file MUST include a leading comment block citing Story 5-6 + Epic 6 (the consumer is Epic 6's notification-tier dispatcher, which reads from this table when classifying outgoing notifications).

The migration applies cleanly on top of migration 017. The migrations runner from Story 1-3 picks it up by filename ordering. No data migration needed — the table starts empty; the dispatcher populates rows on `/mute` invocation.

### AC-2 — New `mute_category` verb (stub)

NEW file `mailbot_api/verbs/mute_category.py` exposes:

```python
async def mute_category(
    category: str,
    *,
    db_path: str,
    muted_until: str | None = None,
) -> MuteCategoryOut: ...
```

Behavior:

- `MuteCategoryOut` is a frozen Pydantic model with `ok: bool`, `category: str`, `muted_until: str | None`, `previously_muted: bool`, `message: str`.
- Inserts (or upserts) a row into `notification_mutes` with the supplied `category` + `muted_until` (NULL = indefinite). `muted_at` is set to UTC ISO-8601 Z at write time.
- `category` is a free-form string; validation (which categories are valid) is the dispatcher's responsibility, not this verb's. Story 6-3 may add a CHECK constraint to migration 018 if a closed taxonomy emerges; for now any string is acceptable.
- Returns `previously_muted=True` when the row already existed pre-write; `False` otherwise.
- Returns `message` as a defender-toned human-readable string: e.g., `"category 'newsletters' muted until 2026-06-09T00:00:00Z"` or `"category 'newsletters' muted indefinitely"`.
- The verb does NOT read from `notification_mutes`; Epic 6's dispatcher does. This verb is the write-side only.

This is a verb stub in the sense that Epic 6's dispatcher contains the logic to ACT on the mute (silence notifications in the matching category). Story 5-6's verb just persists the user's intent.

### AC-3 — Extend `mailbot_api/verbs/__init__.py` to export `mute_category`

Add `from mailbot_api.verbs.mute_category import mute_category` and `mute_category` to `__all__`.

### AC-4 — Extend the MCP server to register the 4 deferred router-control verbs + the new `mute_category` verb

`mailbot_api/mcp_server.py` MUST register five additional MCP tools alongside the existing 11:

1. `cost_breakdown` — wraps `mailbot_api.verbs.cost.cost_breakdown` (already exists from Story 2-10).
2. `reset_degraded_mode` — wraps `mailbot_api.verbs.budget_admin.reset_degraded_mode` (already exists from Story 2-8).
3. `pause_router` — wraps `mailbot_api.verbs.router_control.pause_router` (already exists from Story 2-9).
4. `resume_router` — wraps `mailbot_api.verbs.router_control.resume_router` (already exists from Story 2-9).
5. `mute_category` — wraps the new verb from AC-2.

Specific changes required:

- `_TOOL_DESCRIPTIONS` gains 5 new entries with constraint-hint strings consistent with the existing style (per-verb constraint hint as Story 5-2 AC-1 documents).
- `_EXPECTED_TOOL_COUNT = 11` becomes `_EXPECTED_TOOL_COUNT = 16`.
- `_build_wrappers(server_ctx)` gains 5 new wrappers using the same `db_path` injection pattern as the existing 11 (no per-wrapper session_id; only `hydrate_email` needs `ctx.session_id`).
- Each new wrapper logs via `_log_ok` / `_log_error_as_data` / `_log_crash` per AC-8 of Story 5-2 (session_id, latency_ms, error_code where applicable).
- The module docstring's "Verbs intentionally NOT registered" section MUST be updated: the cost/pause/resume/reset_degraded_mode entries MUST move OUT of the "deferred to 5-6" sub-section (since 5-6 is registering them now). The `ask_router` entry stays. `reset_hydration_count` stays. Document this change at the top of the docstring with a "Story 5-6" annotation.

Description hint suggestions:

- `cost_breakdown`: "Return Router cost breakdown for the period (today | month). Per-task / per-model / per-caller_origin aggregations + cache hit rate."
- `reset_degraded_mode`: "Flip degraded_mode_state to inactive. Slash-command surface: `/budget reset` (Story 5-6)."
- `pause_router`: "Pause the Router lane scheduler with a reason. Slash-command surface: `/pause` (Story 5-6)."
- `resume_router`: "Resume the Router lane scheduler. Slash-command surface: `/resume` (Story 5-6)."
- `mute_category`: "Mute a notification category until a timestamp (or indefinitely). Slash-command surface: `/mute` (Story 5-6); Epic 6's dispatcher reads from notification_mutes."

### AC-5 — Extend `_VERBS_IMPORT_ALLOW` in the boundary checker

`scripts/check_boundaries.py`'s `_VERBS_IMPORT_ALLOW` MUST gain one new entry for the new verb file:

- `mailbot_api/verbs/mute_category.py`

No other allowlist entries change. The boundary check remains clean post-edit.

### AC-6 — Extend `hermes-config/config.yaml` with the slash command registry

Append a new top-level block to `hermes-config/config.yaml`:

```yaml
gateway:
  discord:
    # ... existing fields from Story 5-4 unchanged ...
    slash_commands:
      - name: "cost"
        description: "Show Router cost breakdown for the period."
        options:
          - name: "period"
            type: "string"
            choices: ["today", "month"]
            required: false
        verb: "cost_breakdown"
        ephemeral: true  # responses are not visible to other server members
      - name: "pause"
        description: "Pause the Router lane scheduler with a reason."
        options:
          - name: "reason"
            type: "string"
            required: false
        verb: "pause_router"
        ephemeral: false
      - name: "resume"
        description: "Resume the Router lane scheduler."
        verb: "resume_router"
        ephemeral: false
      - name: "cancel"
        description: "Cancel a pending action by action_id (during cooling-off only)."
        options:
          - name: "action_id"
            type: "integer"
            required: true
        verb: "cancel_action"
        ephemeral: false
      - name: "mute"
        description: "Mute a notification category."
        options:
          - name: "category"
            type: "string"
            required: true
          - name: "muted_until"
            type: "string"
            description: "ISO-8601 UTC Z; omit for indefinite."
            required: false
        verb: "mute_category"
        ephemeral: false
      - name: "label"
        description: "Apply a local-category label to recent emails."
        options:
          - name: "recent"
            type: "integer"
            description: "How many recent emails to label."
            required: true
          - name: "label"
            type: "string"
            required: true
        verb: "propose_action"  # dispatched as ActionType.ADD_LOCAL_CATEGORY per AC-7
        ephemeral: false
      - name: "budget"
        description: "Budget admin commands."
        subcommands:
          - name: "reset"
            description: "Reset degraded mode (exit) and clear the in-memory flag."
            verb: "reset_degraded_mode"
            ephemeral: true
      - name: "confirm"
        description: "Mint a sensitivity token for a sensitive email + task_type."
        options:
          - name: "email_id"
            type: "string"
            required: true
          - name: "task_type"
            type: "string"
            required: true
        verb: "mint_sensitivity_token"
        ephemeral: true
```

The block extends `gateway.discord` — the existing `bot_token` and `intents` fields stay intact.

### AC-7 — `/label` dispatch via `propose_action` (documentation-only in this story)

The `/label` slash command is documented in `hermes-config/config.yaml` as dispatching to `propose_action`, but its specific dispatch pattern (find recent emails → loop `propose_action(email_id, ActionType.ADD_LOCAL_CATEGORY, payload={label})` per email_id) is the Hermes-side dispatcher's responsibility, not this story's MCP-server work. The dispatcher needs to:

1. Run a Tier-2 mint_grant first (ADD_LOCAL_CATEGORY is Tier-1, so technically not required — but the user implicitly authorized the scope by typing the command, so the orchestrator may auto-execute without a mint_grant step).
2. Resolve "the N most recent emails" via `find_emails(filter={}, limit=N)`.
3. Loop `propose_action(email_id, ActionType.ADD_LOCAL_CATEGORY, payload={"label": <label>})`.

This dispatch sequence is documented in `hermes-config/skills/mailbot/SKILL.md` (Story 5-5) as part of the verb-surface walkthrough. No new code in THIS story for the `/label` path beyond the config registration.

### AC-8 — `/confirm` defender-toned response for confidential emails

When the `/confirm` slash command's verb call (`mint_sensitivity_token`) returns `SENSITIVITY_BLOCKS_API` (per Story 4-7 — `confidential` emails admit no API override), the slash-command dispatcher's response MUST be the defender-toned message: "Confidential emails admit no API override. The body stays on your VPS, period."

This is Hermes-side dispatcher logic — but the message text MUST be documented in `hermes-config/skills/mailbot/SKILL.md` (Story 5-5 already includes it as part of the turn-structure-3 documentation). The verifier from Story 5-5 AC-4 already catches drift. NO change needed in THIS story for AC-8; the dependency is already satisfied. Document this fact in Dev Notes.

### AC-9 — Integration tests

NEW file `tests/integration/test_slash_command_registry.py`:

- Test `test_hermes_config_slash_commands_registered`: parse `hermes-config/config.yaml`, assert `gateway.discord.slash_commands` is a list with at least 8 entries; assert each entry has `name`, `description`, and `verb` fields.
- Test `test_hermes_config_slash_command_verb_targets_resolve`: for each registered slash command, assert its `verb` field is one of the 16 MCP-exposed tools (or `propose_action` for `/label`'s tier-1 dispatch shape). Drift fails loudly.
- Test `test_hermes_config_slash_command_names`: assert the 8 documented commands (`cost`, `pause`, `resume`, `cancel`, `mute`, `label`, `budget`, `confirm`) all appear by `name`.
- Test `test_hermes_config_confirm_is_ephemeral`: `/confirm` must have `ephemeral: true` so sensitivity tokens are not visible to other server members.
- Test `test_hermes_config_cost_is_ephemeral`: `/cost` must have `ephemeral: true` so cost data is not visible to other server members (FR-4.8 sensitivity).

NEW file `tests/integration/test_mute_category_verb.py` (or extension of an existing verb-test module):

- Test `test_mute_category_inserts_row`: real SQLite, real migration 018, call `mute_category("newsletters", muted_until="2026-06-09T00:00:00Z")`, assert one row in `notification_mutes`.
- Test `test_mute_category_indefinite_uses_null`: call without `muted_until`, assert the persisted row has `muted_until IS NULL`.
- Test `test_mute_category_upsert_overwrites_existing`: call twice on the same category, assert `previously_muted=True` on the second call AND the row's `muted_until` reflects the SECOND call's value.

NEW file `tests/integration/test_mcp_server_extended_tools.py` (or extension of `tests/integration/test_mcp_server.py`):

- Test `test_mcp_server_registers_16_tools`: build server, assert exactly 16 tools registered.
- Test `test_mcp_server_lists_5_new_tools`: assert `cost_breakdown`, `reset_degraded_mode`, `pause_router`, `resume_router`, `mute_category` all appear in `list_tools` with non-empty descriptions.
- Test `test_mcp_server_mute_category_round_trip`: client call → real DB → assert ok=True + row written.
- Test `test_mcp_server_cost_breakdown_round_trip`: client call → assert ok=True (or at least no MCP-level error) with the expected aggregation shape.

### AC-10 — All four quality gates green

- Pytest: previous baseline (778 from Story 5-5) + new tests. Net rise ≥ **12** (per AC-9 minimums: 5 + 3 + 4 = 12).
- Ruff clean.
- Mypy clean on the new `mute_category` verb + the MCP server edits.
- Boundary check clean (AC-5 allowlist extension).

## Tasks / Subtasks

- [ ] Write migration `018_notification_mutes.sql` per AC-1
- [ ] Write `mailbot_api/verbs/mute_category.py` per AC-2
- [ ] Extend `mailbot_api/verbs/__init__.py` per AC-3
- [ ] Extend `mailbot_api/mcp_server.py` per AC-4 (5 new wrappers + 5 new descriptions + count bump to 16 + docstring update)
- [ ] Extend `scripts/check_boundaries.py` per AC-5
- [ ] Extend `hermes-config/config.yaml` per AC-6
- [ ] Confirm AC-7 + AC-8 dispatch-pattern + defender-message documentation already lands in Story 5-5's SKILL.md (no THIS-story change)
- [ ] Write integration tests per AC-9
- [ ] Run gate sweep per AC-10

### Review Findings

- [x] Review/Patch: `cost_breakdown` MCP wrapper had no default for `period` — APPLIED: signature is now `cost_breakdown(ctx, period: str = "today")`. `/cost` with no arg defaults to today's breakdown per the YAML `required: false` contract. New regression test `test_mcp_server_cost_breakdown_defaults_to_today_when_period_omitted` pins the behavior.
- [x] Review/Patch: `_period_start_iso` silently returned month-start for any non-"today" string — APPLIED: added explicit `if period == "month"` branch + `raise ValueError(...)` for anything else. Bad input now surfaces loudly instead of silently aggregating wrong rows.
- [x] Review/Patch: `_build_wrappers` docstring stale at "11 tool wrappers" — APPLIED: now "16 tool wrappers (11 Story-5-2 baseline + 5 Story-5-6 slash-command surface)".
- [x] Review/Patch: `build_mcp_server` docstring stale at "all 11 MailBot tools" — APPLIED: now "all 16 MailBot tools" with the same baseline+surface split.
- [x] Review/Patch: `build_mcp_server` `instructions` string omitted the 5 new tools — APPLIED: added a slash-command-surface paragraph naming all 5 new tools so agents see them at `list_tools` time.
- [x] Review/Patch: `test_slash_command_registry.py` subcommand validation missed `description` assertion — APPLIED: subcommand loop now asserts `name` + `description` + `verb` per AC-9.
- [x] Review/Patch: No test for `cost_breakdown` without a period argument — APPLIED: added `test_mcp_server_cost_breakdown_defaults_to_today_when_period_omitted` which empty-args calls and asserts `period=="today"` in the response.
- [x] Review/Defer: TOCTOU window in `mute_category`: `fetchone` pre-check and `execute_write` upsert are two separate DB operations with no transaction wrapping; a concurrent second `/mute` call could return `previously_muted=False` incorrectly `mailbot_api/verbs/mute_category.py:67-75` — deferred, single-user system, extremely low risk; fixing requires transaction API refactor
- [x] Review/Defer: YAML `choices: ["today", "month"]` for `/cost period` option uses a flat string-list format that may not match Discord's application-command choices schema (Discord uses typed choice objects with `name`+`value` pairs); Hermes config parser behaviour unverified `hermes-config/config.yaml:91-94` — deferred, documented Phase 3.5 manual-verification item
- [x] Review/Defer: No authorization gate on `pause_router`, `resume_router`, `reset_degraded_mode` at the MCP tool level; any MCP client (including the agent itself) can pause or reset budget state without a grant `mailbot_api/mcp_server.py:447-497` — deferred, design decision documented in Dev Notes (Rule P alignment: dispatcher is responsible; agent-facing slash commands are owner-only by Discord ACL)

## Dev Notes

### Why the verbs already exist but weren't MCP-exposed

`cost_breakdown` (Story 2-10), `reset_degraded_mode` (Story 2-8), `pause_router` / `resume_router` (Story 2-9) were shipped as Python async functions but deliberately NOT registered on the MCP server in Story 5-2 — the Story 5-2 docstring + AC-1 explicitly defer them to THIS story so that the slash-command dispatcher and the MCP tool registration ship together (one coherent set of mutation surfaces, with consistent authorization documentation in `hermes-config/skills/mailbot/SKILL.md`). This story closes that deferral.

### Why `/mute` ships as a verb stub, not a full feature

Epic 6's notification tier dispatcher (Story 6-3) reads from `notification_mutes` when classifying outgoing notifications into urgent / important / informational / silent. This story ships the WRITE side (the verb) + the SCHEMA (migration 018); Epic 6 ships the READ side (the dispatcher consults the table). Splitting the work this way:

1. Lets Adam type `/mute newsletters` today and have his intent persist, even before Epic 6 ships.
2. Keeps Story 5-6's scope tight (a slash dispatcher story, not a notification-tier story).
3. Avoids the temptation to wire half of the dispatcher in 5-6 and the other half in 6-3 — clean boundary.

### Slash-command "registration" vs "dispatch"

Discord slash commands are registered via Discord's REST API on bot startup; the Hermes container handles the actual REST call given the `slash_commands` block in `hermes-config/config.yaml`. THIS story documents the slash commands in the config file; it does NOT write Discord-REST-API code.

Dispatch (translating a slash-command invocation into a verb call) is the Hermes-side runtime responsibility. THIS story documents which verb each command targets; it does NOT write the dispatcher code in Python.

The integration tests are offline: they verify the YAML shape and the verb stubs. The actual Discord round-trip is a Phase 3.5 manual-verification surface (env-gated on a live `DISCORD_BOT_TOKEN`).

### MCP tool count: 11 → 16

The `_EXPECTED_TOOL_COUNT` assertion in `mcp_server.py` is a fail-fast guardrail (Story 5-2's CR-8 finding). Bumping it from 11 to 16 in THIS story is a deliberate, audited change — the assertion fires immediately if a future contributor adds a wrapper without updating the count, or vice versa.

### Hermes-config slash-command schema

The schema used in `hermes-config/config.yaml` (`name` / `description` / `options` / `verb` / `ephemeral`) is THIS story's invention — it's not Discord's native shape (Discord uses richer JSON), it's the simplified shape Hermes's config parser is expected to translate to Discord-REST-API calls. If `nousresearch/hermes-agent:latest` uses a different config schema for slash commands, the dev pass MUST verify and adjust (similar to Story 5-4's path-and-substitution-syntax verification clause). If unverifiable without running the image, document the assumed schema in Dev Notes and let Phase 3.5 catch the mismatch.

### Rule P alignment

Slash commands invoke verbs directly. The verbs themselves enforce Rule P (Authorization Tiers): `/cancel` calls `cancel_action` which only succeeds during cooling-off; `/confirm` calls `mint_sensitivity_token` which refuses confidential emails; `/mute` is purely additive (no destructive surface, no authorization gate needed). The dispatcher does NOT make tier decisions — it just hands the user's command to the right verb.

### MailBot has no graphical frontend

Per PORTING.md: `<frontend-src>` is N/A. Step 2.4.5 N/A. Step 2.4.7 MailBot-reframing: the new `mute_category` verb writes to SQLite (DB-real integration test boundary); AC-9 tests against a real on-disk SQLite per the reframing.

### References

- [Source: epics.md Story 5.6](../planning-artifacts/epics.md)
- [Source: Story 5-2 — MCP tool registration pattern + 11-verb baseline](./5-2-mcp-server-exposing-verbs-as-tools.md)
- [Source: Story 5-4 — hermes-config layout + bind-mount + slash-command registration surface](./5-4-hermes-container-config-and-discord-adapter-and-mcp-client-wiring.md)
- [Source: Story 5-5 — SKILL.md verb-surface walkthrough + defender messages for confidential](./5-5-soul-md-defender-persona-and-agents-md-operational-rules-and-skill-md.md)
- [Source: Story 2-8 — reset_degraded_mode verb](./2-8-4-layer-budget-guard-and-degraded-mode-and-per-call-refusal-threshold.md)
- [Source: Story 2-9 — pause_router / resume_router verbs](./2-9-hourly-anomaly-detection-and-anti-loop-kill-switch-and-pause-resume.md)
- [Source: Story 2-10 — cost_breakdown verb](./2-10-cost-slash-command-and-hermes-aux-routing-via-v1-chat-completions-and-caller-origin-tracking.md)
- [Source: Story 4-7 — mint_sensitivity_token verb + SENSITIVITY_BLOCKS_API refusal](./4-7-sensitive-content-api-override-handshake-mint-sensitivity-token-and-confirmation-token-parameter-and-in-memory-registry.md)

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-epic-run dev pass

### Completion Notes List

- Shipped migration `018_notification_mutes.sql` (3-column schema + index on muted_until; consumer is Epic 6's Story 6-3 dispatcher).
- Shipped `mailbot_api/verbs/mute_category.py` write-side stub with frozen `MuteCategoryOut`, defender-toned message, `previously_muted` field.
- Extended `mailbot_api/mcp_server.py` from 11 to 16 tools — registered `cost_breakdown`, `reset_degraded_mode`, `pause_router`, `resume_router`, `mute_category`. Closes Story 5-2's explicit deferral. Updated module docstring + `build_mcp_server` instructions + `_build_wrappers` docstring + `_EXPECTED_TOOL_COUNT`.
- Shipped 8-command slash registry in `hermes-config/config.yaml` under `gateway.discord.slash_commands` (cost / pause / resume / cancel / mute / label / budget / confirm). cost/confirm/budget-reset marked `ephemeral: true` per FR-4.8 sensitivity.
- Extended `scripts/check_boundaries.py` allowlist for `mute_category.py`. Boundary check stays clean.
- CR (Sonnet 4.6) returned 10 findings: 7 PATCH (all applied — 7/7 = 100%) + 3 DEFER (TOCTOU on mute_category, Discord choices format uncertainty, missing slash-command authorization gate). Critical fix: `cost_breakdown` MCP wrapper now defaults `period="today"` so `/cost` with no arg works end-to-end; the missing-default would have been a functional regression on the most common /cost invocation. `_period_start_iso` gained a defensive `ValueError` for any non-{today,month} period (was silently taking month branch). Three stale docstrings updated. FastMCP `instructions` now names all 16 tools.
- Pre-review §5.12 verdict: MANDATORY-CR (criterion 1 load-bearing-orchestrator + criterion 6 migration + criterion 3 partial cost_breakdown exposure). CR dispatched per Adam-decided Epic 4 retro action item #1 cadence rule; all 7 actionable findings closed.
- 795 tests pass (+17 net from 778 baseline). Ruff clean. Mypy clean. Boundary clean.

### File List

NEW:

- mailbot_api/db/migrations/018_notification_mutes.sql
- mailbot_api/verbs/mute_category.py
- tests/integration/test_slash_command_registry.py
- tests/integration/test_mute_category_verb.py
- tests/integration/test_mcp_server_extended_tools.py
- _bmad-output/implementation-artifacts/5-6-slash-command-dispatcher.md
- _bmad-output/implementation-artifacts/5-6.pre-review.md

UPDATED:

- mailbot_api/mcp_server.py — 5 new tool wrappers + 5 new descriptions + count 11→16 + docstring + instructions + cost_breakdown default-period fix (CR-1).
- mailbot_api/verbs/cost.py — `_period_start_iso` defensive `ValueError` for invalid period (CR-2).
- mailbot_api/db/queries.py — NOTIFICATION_MUTES_SELECT_BY_CATEGORY + NOTIFICATION_MUTES_UPSERT constants.
- mailbot_api/verbs/__init__.py — mute_category export + __all__ update.
- scripts/check_boundaries.py — `_VERBS_IMPORT_ALLOW` gains `mailbot_api/verbs/mute_category.py`.
- hermes-config/config.yaml — gateway.discord.slash_commands block appended (8 commands).
- tests/integration/test_mcp_server.py — 3 existing tests updated to 16-tool count; forbidden set narrowed (cost/pause/resume/reset_degraded_mode no longer forbidden).
- tests/integration/test_slash_command_registry.py — subcommand validator now asserts name + description + verb (CR-6).
- _bmad-output/implementation-artifacts/sprint-status.yaml — 5-6 row backlog → in-progress → done.

## Completion Notes

### 2026-06-02 — autonomous-epic-run close

Story 5-6 closed by autonomous-epic-run. §5.12 MANDATORY-CR cadence honored — Sonnet 4.6 CR dispatched, 7 PATCH findings applied (7/7 = 100%), 3 DEFER documented with rationale (TOCTOU low-risk single-user / Discord choices schema unverified pending Phase 3.5 / authorization-gate is dispatcher responsibility per Rule P). Final test count: 795 (+17 net from 778 baseline). All 4 gates green. Story `done`.

Phase 3.5 manual-verification items: (1) Hermes config schema verification — does `nousresearch/hermes-agent:latest` actually parse the documented slash_commands shape? (2) Discord choices array vs object format — does Discord accept the flat string list `["today", "month"]` or does Hermes need to translate to `[{name, value}, ...]` choice objects? Both are documented in story file and flagged for the Phase 3.5 walk.
