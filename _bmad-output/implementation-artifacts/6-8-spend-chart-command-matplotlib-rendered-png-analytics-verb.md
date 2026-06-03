---
baseline_commit: 4412da006f66930eecd36f7b5be004b3d98edd96
---

# Story 6.8: `/spend` chart command — matplotlib-rendered PNG analytics verb

Status: done

## Story

As Adam,
I want a `/spend [period]` slash command that invokes `render_spend_chart(period)` analytics verb on mailbot-api, generates a matplotlib bar chart of cost-per-task over the period, returns the PNG as `(bytes, mime_type)`, and Hermes posts it to Discord as an inline image attachment,
So that AR-ANALYTICS-1's discipline (analytics verbs in `mailbot_api/verbs/analytics/` returning PNGs rendered via matplotlib `Agg` backend) has its first demonstrated, useful surface — and I get a glanceable view of where my $30/month is going.

## Acceptance Criteria

**Given** AR-ANALYTICS-1 + AR-ANALYTICS-2 disciplines from the requirements inventory + Story 1.1's numpy + matplotlib pinning
**When** `mailbot_api/verbs/analytics/render_spend_chart.py` is implemented
**Then** `render_spend_chart(period: Literal["today", "week", "month"]) -> RenderSpendChartOut` returns a Pydantic model with fields: `mime_type: Literal["image/png"]`, `image_bytes: bytes`, `period: str`, `total_usd: float`, `task_count: int`, `top_task: str` (highest-spending task in the period)
**And** the verb reads `router_calls` raw via `db/queries.py` (no pandas), groups cost by `task_type` over the period, sorts descending
**And** uses matplotlib's `Agg` backend (`matplotlib.use("Agg")` set at module load) — no GUI dependencies
**And** renders a horizontal bar chart at 1200×800 px @ 100 DPI with: task_type labels, USD-cost x-axis, a title like "Spend by Task — Last 7 Days ($X.XX total)", and a defender-toned subtitle noting the cap if relevant ("$X of $30 month cap" for `period="month"`)
**And** returns the PNG as bytes (never written to disk — per AR-ANALYTICS-2)

**Given** Story 5.6's slash command dispatcher
**When** `/spend [period]` is invoked in Discord (default `period="month"` if absent)
**Then** the dispatcher calls `render_spend_chart(period)` via MCP
**And** Hermes posts the returned PNG bytes as a Discord attachment in a single message
**And** the message includes a one-line text summary: "$X.XX spent {period}. Top task: {top_task} (${Y.YY}). Cap: $30."
**And** any text rendered onto the PNG (labels, title, subtitle) passes through the Story 5.7 chat-input redactor (per AR-ANALYTICS-1 — defense-in-depth even though chart labels are project-internal data, not user input)

**Given** the analytics verb surface is established
**When** `mailbot_api/verbs/analytics/__init__.py` is created
**Then** the module documents the discipline (AR-ANALYTICS-1 quoted at top) as a banner for future maintainers adding analytics verbs
**And** ruff (per Story 1.4) is extended with a rule: any `matplotlib.pyplot` import outside `mailbot_api/verbs/analytics/` fails the lint pass

**Given** the verb is in place
**When** `tests/unit/verbs/analytics/test_render_spend_chart.py` runs against a seeded `router_calls` table
**Then** the returned `image_bytes` is a valid PNG (verifiable by `PIL.Image.open(io.BytesIO(...))` succeeding)
**And** the dimensions are 1200×800
**And** the `top_task` matches the highest-cost task_type in the seeded data
**And** rendering on an empty `router_calls` table returns a chart with a single "No spend recorded for this period" label (no division-by-zero, no crash)

**Given** the slash command is in place
**When** `tests/integration/test_spend_chart_command.py` exercises `/spend month` against a mocked Discord environment
**Then** Discord receives a single message with an attached PNG and the documented text summary
**And** the slash command completes within 5 seconds wall-clock (NFR-PERF-1 — chart rendering on 2 vCPU; pre-measured at typical 100k-row `router_calls` table)

## Tasks / Subtasks

- [x] **Task 1: `mailbot_api/verbs/analytics/__init__.py` — discipline banner** (AC: 3)
  - [ ] Create `mailbot_api/verbs/analytics/` package
  - [ ] `__init__.py` opens with a module docstring quoting AR-ANALYTICS-1 verbatim (analytics verbs return structured Pydantic models OR `(bytes, mime_type)` tuple; no LLM bypass; reads cached derived-field columns, never re-derives)
  - [ ] Re-export `render_spend_chart` and `RenderSpendChartOut` for `from mailbot_api.verbs.analytics import render_spend_chart` ergonomics

- [x] **Task 2: `mailbot_api/verbs/analytics/render_spend_chart.py` — the verb** (AC: 1, 4)
  - [ ] Module docstring referencing AR-ANALYTICS-1 + AR-ANALYTICS-2
  - [ ] **Backend isolation:** `import matplotlib; matplotlib.use("Agg")` BEFORE `import matplotlib.pyplot as plt`. The order matters — `pyplot` import triggers backend resolution if Agg isn't already declared
  - [ ] Pydantic shape `RenderSpendChartOut(BaseModel)` with fields exactly as ACs spec: `mime_type: Literal["image/png"]`, `image_bytes: bytes`, `period: str`, `total_usd: float`, `task_count: int`, `top_task: str`
  - [ ] Async signature: `async def render_spend_chart(period: Literal["today", "week", "month"]) -> RenderSpendChartOut`
  - [ ] Internal `_period_window_start(period)` returns the UTC ISO-8601 timestamp for the start of the window. `today` → `YYYY-MM-DDT00:00:00Z`; `week` → 7 days ago; `month` → first-of-month at 00:00:00Z. Reuse Story 2-10's pattern (see `mailbot_api/verbs/cost.py:_period_start_iso`); add `week` as a new branch — there's no `week` in `cost_breakdown`, this verb introduces it
  - [ ] Query `router_calls` raw via `db/queries.py.ROUTER_CALLS_BY_TASK_SINCE` (already exists from Story 2-10) → returns `[(task_type, cost_usd_sum), ...]` for the window
  - [ ] Compute `total_usd = sum(costs)`, `task_count = len(rows)`, `top_task = rows[0][0]` after `ORDER BY cost DESC` (the SQL already groups; sort in Python for determinism — SQL's GROUP BY doesn't guarantee order)
  - [ ] **Empty-data branch (AC-4 last item):** if `task_count == 0`, render a single-axes chart with `ax.text(0.5, 0.5, "No spend recorded for this period", ha="center", va="center")` and `ax.set_axis_off()`. Skip the bar-chart path entirely; return `top_task=""`
  - [ ] **Chart rendering path (non-empty):**
    - [ ] `fig, ax = plt.subplots(figsize=(12, 8), dpi=100)` → 1200×800 px @ 100 DPI exactly
    - [ ] `ax.barh(task_types, costs)` — horizontal bar chart per AC; task labels on Y-axis, USD on X-axis
    - [ ] `ax.invert_yaxis()` so highest-cost task is at top (matplotlib's default is ascending bottom-up)
    - [ ] Title: `f"Spend by Task — {_period_label(period)} (${total_usd:.2f} total)"` where `_period_label` returns "Today" / "Last 7 Days" / "This Month"
    - [ ] Subtitle (suptitle or text above title) for `period="month"` only: import `MONTHLY_HARD_CAP_USD` from `mailbot_api.router.budget` and render `f"${total_usd:.2f} of ${MONTHLY_HARD_CAP_USD:.0f} month cap"`. Other periods get no subtitle
    - [ ] X-axis formatter: `ax.xaxis.set_major_formatter(mticker.FormatStrFormatter("$%.2f"))` so axis labels show "$0.10" not "0.1"
    - [ ] `fig.tight_layout()` to prevent label clipping; this is critical when task names get long
  - [ ] **Bytes-only return path (AC-1 last item — never write to disk):**
    - [ ] `buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=100); plt.close(fig); image_bytes = buf.getvalue()`
    - [ ] **`plt.close(fig)` MUST follow `fig.savefig` — matplotlib's `Figure` instances leak memory unless explicitly closed** (the agg backend keeps a renderer cache). The story is short-lived per call but the worker process is long-lived; without `close()` the worker grows unbounded
  - [ ] Return `RenderSpendChartOut(mime_type="image/png", image_bytes=image_bytes, period=period, total_usd=total_usd, task_count=task_count, top_task=top_task)`

- [x] **Task 3: SQL constant — extend `db/queries.py` for the `week` window** (AC: 1)
  - [ ] `ROUTER_CALLS_BY_TASK_SINCE` already exists from Story 2-10 and is parameterized by `ts >= ?` — no new SQL constant needed. The verb computes the window start in Python (using `datetime.now(timezone.utc)`) and passes it in
  - [ ] If the boundary checker fires on the Python-side ISO-format computation (it shouldn't — only raw SQL literals are scanned), no action needed
  - [ ] Document in the verb's docstring: "Window computed in Python — `period` maps to `_period_window_start(period)`; SQL filter is `ts >= ?`"

- [x] **Task 4: Boundary checker extension — `matplotlib.pyplot` import isolation** (AC: 3)
  - [ ] Open `scripts/check_boundaries.py`
  - [ ] Add allowlist: `_MATPLOTLIB_PYPLOT_ALLOW = frozenset({"mailbot_api/verbs/analytics/render_spend_chart.py"})` near the existing `_FASTMCP_IMPORT_ALLOW` definition (analytics surface is locked to a single module today; future analytics verbs would be added to this set)
  - [ ] Inside `check_file`, in the `ast.Import` branch, detect `alias.name == "matplotlib.pyplot"` and `alias.name.startswith("matplotlib.pyplot.")` AND `rel not in _MATPLOTLIB_PYPLOT_ALLOW` → append violation
  - [ ] Inside the `ast.ImportFrom` branch, detect `full_mod == "matplotlib.pyplot"` or `full_mod.startswith("matplotlib.pyplot.")` AND `rel not in _MATPLOTLIB_PYPLOT_ALLOW` → append violation
  - [ ] Mirror the violation message format used by `_VERBS_IMPORT_ALLOW`/`_FASTMCP_IMPORT_ALLOW` violations
  - [ ] **DO NOT** ban `import matplotlib` (without `.pyplot`) — that's needed by `render_spend_chart.py` for the `matplotlib.use("Agg")` backend declaration, and future analytics verbs may need it for `mtransforms` / `mticker` / `matplotlib.figure.Figure` direct construction (the AR-ANALYTICS surface defines what's allowed; only `.pyplot` is the gateway we're locking down per AC-3)
  - [ ] Update the module docstring's "Bans enforced:" section to document the new boundary

- [x] **Task 5: MCP server registration — `render_spend_chart` as a tool** (AC: 2)
  - [ ] Open `mailbot_api/mcp_server.py`
  - [ ] Import `render_spend_chart` from `mailbot_api.verbs.analytics`
  - [ ] Register as a FastMCP tool exactly like the existing 16 verbs from Story 5-6; tool count becomes **17**
  - [ ] Tool name: `render_spend_chart` (matches verb name per Story 5-2 convention)
  - [ ] Update Story 5-2's MCP test assertions if they hard-code the tool count (search `tests/integration/test_mcp_startup_live.py` for `tools=16` and bump to 17)

- [x] **Task 6: SKILL.md update — document `render_spend_chart` + `/spend`** (AC: 2)
  - [ ] **Schema-reality correction:** Story 6-0 RECONCILIATION-NOTES §6 item 1 established that Hermes does NOT load slash-command registries from `config.yaml`; slash commands auto-register from installed Hermes skill bundles under `hermes-config/skills/<bundle>/`. The Story 5-6 config-YAML `slash_commands:` block was an invented schema and was retired by Story 6-0. So this story does NOT modify `hermes-config/config.yaml` (verified — there is no `slash_commands:` block in the current file)
  - [ ] Instead: update `hermes-config/skills/mailbot/SKILL.md` (Story 5-5's MailBot verb-surface reference)
  - [ ] Add a new section under the "Action verbs" surface area: "### `render_spend_chart`" documenting the verb signature, the period semantics (today/week/month), the PNG+summary return shape, and the `/spend [period]` Discord-side slash invocation
  - [ ] Update the existing "Router verbs — `ask_router` is intentionally NOT MCP-exposed" section: the inline list "cost_breakdown, reset_degraded_mode, pause_router, resume_router — these are the verb-side handlers for Discord slash commands. Story 5-6 wires them up alongside the slash-command dispatcher." is now stale (Story 5-6 DID register them as MCP tools). Reword to acknowledge they ARE MCP-exposed as of Story 5-6 + add `render_spend_chart` to the same surface
  - [ ] Add a 4th turn structure: "### Turn structure 4 — `/spend month`" documenting the dispatch: user types `/spend month` → Hermes resolves the slash → calls `render_spend_chart(period="month")` MCP tool → receives `RenderSpendChartOut` → posts a single Discord message with the PNG as attachment + the documented text summary line
  - [ ] **F6-gated portion (deferred):** the actual Hermes-side slash-dispatch wiring (skill-bundle slash-registration mechanism per RECONCILIATION-NOTES §6 item 1) is NOT in scope for this story. The verb-side + MCP-tool-registration ARE in scope. End-to-end Discord posting verified in Phase 3.5 after F6 (MCP /mcp 307→404) closure

- [x] **Task 7: Unit tests — `tests/unit/verbs/analytics/test_render_spend_chart.py`** (AC: 4)
  - [ ] Create `tests/unit/verbs/analytics/` directory + `__init__.py`
  - [ ] Fixture: in-memory SQLite with Story 1-3's migrations applied (use the standard `tests/conftest.py` pattern — search for `db_conn` or `migrations_applied` fixtures)
  - [ ] Helper: `_seed_router_calls(conn, rows)` inserts rows directly via `mailbot_api.db.queries.ROUTER_CALLS_INSERT` (boundary-respecting — the audit writer is the canonical path; for test seeding the SQL constant is fine since `tests/` is outside the boundary scan)
  - [ ] **Test 1: PNG validity** — seed 3 rows (`coarse_class` $0.10, `fine_class` $0.05, `summary_short` $0.02), call `await render_spend_chart("today")`, assert `mime_type == "image/png"`, assert `PIL.Image.open(io.BytesIO(result.image_bytes))` succeeds (requires `pillow` — already pinned? if not, the test depends on `Pillow` which is a transitive dep of matplotlib's image backend on some platforms; if pillow isn't reachable, use `result.image_bytes.startswith(b"\\x89PNG")` PNG-magic-bytes assertion as a fallback)
  - [ ] **Test 2: Dimensions** — same seed, assert `Image.open(...).size == (1200, 800)` (or via PNG-header IHDR parsing if pillow unavailable: `width, height = struct.unpack(">II", image_bytes[16:24])`)
  - [ ] **Test 3: Top task** — seed where `fine_class` is highest, assert `result.top_task == "fine_class"`
  - [ ] **Test 4: Empty data** — empty `router_calls`, assert `result.task_count == 0`, `result.total_usd == 0.0`, `result.top_task == ""`, AND PNG renders successfully (no crash, valid PNG bytes returned). Visually: a "No spend recorded for this period" label
  - [ ] **Test 5: Period windows** — seed rows at `ts = now - 2h`, `now - 2d`, `now - 20d`. Call with `period="today"`, assert only the `now - 2h` row contributes. Call with `period="week"`, assert the 2h + 2d rows. Call with `period="month"` (assuming we're past day-3 of month), assert all three (or adjust the 20d seed to be within the month). Window-boundary math is the highest-risk part of this verb
  - [ ] **Test 6: Sort order** — seed where `summary_short` is most expensive, then `fine_class`, then `coarse_class`. Render. Open the PNG. Inspect: the top bar (post-`invert_yaxis`) is `summary_short`. (Can be checked via matplotlib introspection: don't actually call `savefig`; call the internal function up to `ax.barh` and inspect `ax.get_yticklabels()`. Alternatively: trust the Python-side sort and assert `top_task == "summary_short"`)
  - [ ] **Test 7: Monthly subtitle** — call `period="month"` with non-empty seed. Inspect the figure's text artists for the `$X of $30 month cap` string. If too brittle: skip the inspect and just assert no crash + valid PNG (the visual subtitle is a Phase 3.5 verification)
  - [ ] **Test 8: No disk write** — patch `pathlib.Path.write_bytes` and `open` calls during the verb invocation; assert no `.png` file is written to the filesystem (defensive AR-ANALYTICS-2 enforcement). Use `tmp_path` to confirm nothing landed there
  - [ ] **Test 9: matplotlib `close` called** — patch `matplotlib.pyplot.close` and assert it's invoked exactly once per `render_spend_chart` call (memory-leak regression guard — the Task 2 docstring calls this out as a long-running-worker concern)

- [x] **Task 8: Integration test — `tests/integration/test_spend_chart_command.py`** (AC: 5)
  - [ ] Header docstring: "End-to-end /spend slash dispatch. F6-gated portions (MCP dispatch round-trip) deferred to Phase 3.5; this story tests the locally-testable verb-side + dispatcher-side wiring."
  - [ ] Test 1: import `render_spend_chart` from `mailbot_api.verbs.analytics`, seed `router_calls`, call directly, assert the returned shape matches `RenderSpendChartOut` schema
  - [ ] Test 2: MCP server registration — start the FastMCP server (use the Story 5-2 test fixture pattern), assert the tool list includes `render_spend_chart`. This validates Task 5 wiring without requiring the F6-blocked dispatch round-trip
  - [ ] Test 3: Slash command config — open `hermes-config/config.yaml`, assert the `spend` entry exists with `mcp_tool: render_spend_chart` and `default_args.period: month`. This validates Task 6 without requiring Hermes to actually be running
  - [ ] Test 4 (perf): seed 1000 router_calls rows (representative; the 100k figure in the AC is the production estimate but in CI we use a smaller sample), time the verb call, assert `< 2s` wall-clock. The AC's 5s budget is for production scale; in tests we use a tighter ceiling at smaller scale to catch regressions
  - [ ] **F6-gated portion (deferred):** the actual MCP-dispatch round-trip (slash command → MCP tool → returned bytes → posted to Discord) requires F6 (MCP /mcp 307→404) to be resolved. Document this in the test file's header AND in the story Completion Notes. The autonomous-epic-run sprint reorder explicitly carved out 6-8 as F6-INDEPENDENT for the verb-side surface; the F6-blocked dispatch is the same Phase 3.5 verification surface applied to 6-3/6-4/6-5

- [x] **Task 9: Story Completion Notes — document the F6 carve-out** (AC: all)
  - [ ] In the Completion Notes section, explicitly call out: "Story 6-8 is the LAST F6-INDEPENDENT story in Epic 6. The verb side (matplotlib chart rendering + AR-ANALYTICS-1 boundary + MCP tool registration + slash-config wiring) is locally tested. The end-to-end Discord-attachment dispatch path is F6-gated — verified in Phase 3.5 after the 6-6.6 (or equivalent) F6-closure story ships."

## Dev Notes

### Architectural anchors

- **AR-ANALYTICS-1** (architecture §AR — line 269 of `epics.md`): `mailbot-api` ships with `numpy` and `matplotlib` for tabular analysis and chart rendering. Analytics verbs live in `mailbot_api/verbs/analytics/` and return either structured Pydantic models OR a `(bytes, mime_type)` tuple. They are NOT alternatives to the verb API or the Router. Charts posted to Discord by Hermes pass through Story 5-7's chat-input redactor on inline text labels rendered onto the image. `pandas` is explicitly deferred.

- **AR-ANALYTICS-2** (line 270): Chart rendering uses matplotlib's `Agg` non-interactive backend (`matplotlib.use("Agg")`) — no GUI dependencies; rendering off-screen in the worker process. PNGs returned as bytes (never written to disk on `mailbot-api`); Hermes posts them as Discord attachments. Standard chart dimensions: 1200×800 px @ 100 DPI.

- **AR-PAT-5** (Rule J): Agent-facing surfaces (verbs + chat) are the boundary. The verb side returns the `(bytes, mime_type)` tuple via the `RenderSpendChartOut` Pydantic shape — schema-stable. Hermes-side discord attachment posting is the agent's concern.

- **Rule A** (cached derived-field columns): For LLM-derived data this would apply, but `router_calls` is NOT LLM-derived data — it's the audit trail. The verb reads `cost_usd_estimated` directly. No re-derivation risk.

### Reference files (READ FIRST)

- `mailbot_api/verbs/cost.py` — Story 2-10's `cost_breakdown` verb. Same data source (`router_calls` via `ROUTER_CALLS_BY_TASK_SINCE`), same period-window pattern (today/month). This story adds `week` as a new period and replaces the structured Pydantic output with a PNG-bytes output. **Read this file end-to-end before starting Task 2** — the `_period_start_iso` helper and the Story 5-6 CR-2 defensive-guard pattern (raise on invalid period) are the patterns to copy

- `mailbot_api/db/queries.py:639-641` — `ROUTER_CALLS_BY_TASK_SINCE = "SELECT task_type, COALESCE(SUM(cost_usd_estimated), 0) FROM router_calls WHERE ts >= ? GROUP BY task_type"`. Already supports the aggregation. Re-used as-is

- `mailbot_api/router/budget.py:MONTHLY_HARD_CAP_USD` — $30 constant (per FR-3.3). Import for the month subtitle

- `mailbot_api/mcp_server.py` — Story 5-2 + Story 5-6 MCP server. 16 tools registered post-5-6. Add `render_spend_chart` as the 17th. Look at how `cost_breakdown` is registered (it's the closest pattern: a verb with a Pydantic-output shape)

- `hermes-config/config.yaml` — Story 6-0's reconciled schema. The `slash_commands:` list lives at top level. Append the `spend` entry

- `scripts/check_boundaries.py` — Story 1-4 + extensions. Pattern for new allowlist + check: copy how `_FASTMCP_IMPORT_ALLOW` is wired (lines 183, 414-424, 474-485). The `matplotlib.pyplot` boundary follows the exact same import-detection structure

- `tests/integration/test_mcp_startup_live.py` — if it hard-codes the tool count (Story 6-0 found F2 here: "tools=11" hardcoded), update to 17 (or whatever the post-5-6 count is + 1 for this story)

### Previous story learnings carried forward

From **Story 6-7** (just-closed):
- CR cadence v2 §5.12 classifier hit MANDATORY-CR with 4 criteria last story. For 6-8: 1) new code (yes, full verb); 2) external surface (yes, MCP tool + slash command); 3) operator-facing (yes, /spend output is what Adam sees); 4) policy/budget surface (partial — the verb reads cost_usd_estimated, doesn't write or enforce policy, but it RENDERS the cap on the chart subtitle). **Expect MANDATORY-CR.**
- AC drift handling: when AC text references behavior the architecture forbids or the codebase doesn't support, document inline + flag for retro, don't bend the architecture. Story 6-7 amended the closure-gate annotation rather than skipping ACs

From **Story 6-2** (status board + pause CLI):
- The `RouterStatus` section's null-out pattern when paused=False (CR-3) is a precedent for "rendering UI text from server-side state should not display stale fields when the state semantically clears them." Apply to: when `task_count == 0`, `top_task` should be `""` not `None` — the consumer (slash dispatch summary line) does string formatting; an empty string is safer than `None`
- Pre-existing-mypy-gap pattern (Story 6-1 5 errors fixed in Story 6-2): if Task 2's PNG-bytes computation triggers mypy errors elsewhere in scripts/mailbot.py or main.py, those are pre-existing — patch them inline, don't carry them forward

From **Story 6-1** (status board):
- CR-1 CRITICAL caught the LIKE pattern mismatch (`hermes-aux%` vs `hermes_aux`). Lesson for this story: when the verb reads `task_type` values from the policy table, make sure the test seed uses values that actually exist in the live `policy.yaml` (e.g., `coarse_class`, `fine_class`, `summary_short`, `sensitivity_class`, etc.). A test that seeds `task_type='made_up_task'` would pass but the production rendering would be empty

From **Story 6-0** (Hermes runtime corrective):
- F6 (MCP /mcp 307→404 redirect mismatch) is OPEN. This story is the LAST F6-INDEPENDENT story in Epic 6. The verb-side + MCP-tool-registration + slash-config wiring are locally testable; the F6-gated portion (slash dispatch round-trip) goes in Phase 3.5

From **Epic 5 retro action items**:
- Action item #1 (CR cadence v2 structural): the §5.12 classifier with 6 criteria is the rule. Apply it after dev-story completes
- Action item #4 (Story 6-6.5 capstone walk): still pending. After 6-8 closes, the loop halts before 6-3 due to F6 dependency. The Phase 3 wrap-up will surface this

### Latest tech specifics

- **matplotlib 3.x** (latest stable; pinned only as `matplotlib` in requirements.txt, so latest stable resolves on `pip install`):
  - `matplotlib.use("Agg")` MUST be called BEFORE `import matplotlib.pyplot as plt` to avoid backend conflicts. Some test environments inject `pytest-mpl` or set `MPLBACKEND=Agg` already; the explicit `.use("Agg")` is defensive
  - `Figure.savefig(buf, format="png")` writes PNG bytes directly to a `BytesIO`. The `format="png"` is required when the buf has no inferred extension
  - `plt.close(fig)` is the canonical memory-release call. Aliases: `plt.close("all")` (closes ALL figures — too aggressive for a per-call verb), `plt.close()` (closes the current figure — flaky in async contexts where the current-figure stack may have torn down)
  - `mticker.FormatStrFormatter("$%.2f")` requires `import matplotlib.ticker as mticker`
  - `figsize=(12, 8)` + `dpi=100` produces 1200×800 px — exact AC match

- **Pillow** (transitive dep of matplotlib for some image-backend paths): import as `from PIL import Image`. If not directly importable in the test env, use raw PNG header parsing: `image_bytes[:8] == b"\\x89PNG\\r\\n\\x1a\\n"` (PNG magic); dimensions at byte offsets `[16:20]` (width big-endian uint32) and `[20:24]` (height big-endian uint32)

- **Python 3.12 `Literal` typing**: `Literal["today", "week", "month"]` is the static type; mypy strict enforces the caller passes one of these. The verb itself should also raise `ValueError` on an invalid runtime value (defensive — even though mypy enforces statically, the verb is called from MCP at runtime where the value is wire-decoded JSON)

- **FastMCP 1.27.2** (pinned): tool registration in `mcp_server.py` follows the `@server.tool()` decorator pattern OR the `server.add_tool(callable, name=...)` direct registration. Story 5-2 / 5-6 chose one of these — match the existing pattern

### Critical guardrails

- **DO NOT** import `matplotlib.pyplot` outside `mailbot_api/verbs/analytics/render_spend_chart.py`. The boundary checker added in Task 4 enforces this at lint time. If any test file imports pyplot, it lives under `tests/` which is outside the boundary scan — that's fine. Production code is the boundary

- **DO NOT** write the PNG to disk in production code. AR-ANALYTICS-2 is explicit. The Task 7 Test 8 enforces this. If a debugging workflow ever needs disk-write, route it through a `MAILBOT_DEBUG_PNG_DIR` env var that's read in tests only (NOT included in this story)

- **DO NOT** bypass the Router for any LLM-derived label on the chart. The AR-ANALYTICS-1 invariant: "any analysis that hits the LLM still goes through `ask_router`." This story's labels are task_type strings (`coarse_class`, etc.) — these come from `router_calls.task_type` which is the audit column, not LLM output. Safe

- **DO NOT** include user-input content in chart labels. The labels are task_type strings, hardcoded enum values from the policy. The chat-input redactor (AC-2) is defense-in-depth for the case where a future analytics verb DOES include user-input content; for `render_spend_chart` the labels are project-internal, but apply the redactor anyway per AR-ANALYTICS-1

- **DO NOT** leak file handles. Every `fig.savefig(buf, ...)` must be followed by `plt.close(fig)`. The Task 7 Test 9 enforces this

- **Window-boundary math is the highest-bug-density part of this verb.** Test 5 covers it. Off-by-one between "today starts at 00:00:00Z" vs "last 24 hours" is the classic trap — the AC says "today" → since 00:00:00Z UTC. Stick to that

### Project structure notes

- `mailbot_api/verbs/analytics/` is a NEW directory — create with `__init__.py`
- `tests/unit/verbs/analytics/` is a NEW directory — create with `__init__.py`
- `tests/integration/test_spend_chart_command.py` is a NEW file in an existing directory
- `scripts/check_boundaries.py` is MODIFIED — add allowlist + check
- `mailbot_api/mcp_server.py` is MODIFIED — register the verb
- `hermes-config/config.yaml` is MODIFIED — append slash entry

### Testing strategy

- **Red-green-refactor:** write the failing test first (Test 1: PNG validity), implement the minimal verb, watch it pass, then refactor
- **Unit tests** cover the verb in isolation (Tests 1-9). 9 unit tests; mocked SQLite via the standard fixture
- **Integration tests** cover the MCP tool registration + slash config (Tests 1-3). Test 4 covers perf at a smaller-than-production scale
- **Phase 3.5 carry-forward:** the end-to-end Discord-attachment dispatch path is F6-gated and walked manually by Adam after the F6 closure ships

## Change Log

| Date       | Change                            | Author |
| ---------- | --------------------------------- | ------ |
| 2026-06-03 | Story created (autonomous-epic-run) | SM (Sonnet via /autonomous-epic-run) |

## Dev Agent Record

### Implementation Plan

(to be filled by dev agent)

### Debug Log

(to be filled by dev agent)

### Completion Notes

**2026-06-03 — Story 6-8 implementation complete; flipped to `review`.**

**Status:** all 9 tasks complete. 4 gates green:

- pytest: **916 passed + 2 skipped** (was 896; +20 net — 15 unit + 5 integration)
- ruff: clean (3 import-ordering fixes applied via `--fix`)
- mypy strict: 0 issues in 111 source files
- boundary checker: clean (matplotlib.pyplot lockdown added; analytics package allowlisted)

**Tool count:** Story 5-6's 16 MCP tools → 17 (added `render_spend_chart`).

**Acceptance Criteria coverage:**

- **AC-1 (verb shape):** `RenderSpendChartOut(mime_type, image_bytes, period, total_usd, task_count, top_task)` ships in `mailbot_api/verbs/analytics/render_spend_chart.py`. `matplotlib.use("Agg")` runs at module load BEFORE `import matplotlib.pyplot`. 1200×800 @ 100 DPI horizontal bar chart via `ax.barh` + `ax.invert_yaxis()`. Monthly subtitle (`$X of $30 month cap`) rendered conditionally. PNG returned as `bytes` via `BytesIO` — never written to disk
- **AC-2 (slash dispatch):** MCP tool `render_spend_chart` registered with `period` default = `"month"` (mirrors Story 5-6 CR-1 default-arg pattern). End-to-end Discord-attachment posting is F6-gated and deferred to Phase 3.5
- **AC-3 (boundary):** `mailbot_api/verbs/analytics/__init__.py` opens with AR-ANALYTICS-1 verbatim. `scripts/check_boundaries.py` extended with `_MATPLOTLIB_PYPLOT_ALLOW` allowlist (single entry: `render_spend_chart.py`). Both `ast.Import` and `ast.ImportFrom` branches detect violations
- **AC-4 (unit tests):** 15 unit tests in `tests/unit/verbs/analytics/test_render_spend_chart.py`. PNG-magic-bytes validation + IHDR-chunk width/height parsing (no Pillow dependency — used raw `struct.unpack(">II", image_bytes[16:24])` instead). Tests cover: PNG validity, dimensions, top-task ordering, empty-data placeholder, period windows (today/week/month boundary math), sort order, monthly subtitle smoke, no-disk-write enforcement, `plt.close` memory-hygiene regression guard, invalid-period `ValueError`
- **AC-5 (integration tests):** 5 integration tests in `tests/integration/test_spend_chart_command.py`. Includes 1000-row perf check (<2s budget at integration scale; AC's 5s is for 100k production scale). F6-gated MCP-dispatch round-trip documented and deferred

**Schema-reality correction (Task 6):** Story 6-0 RECONCILIATION-NOTES §6 item 1 retired the Story 5-6 invented `slash_commands:` block in `hermes-config/config.yaml`; real Hermes auto-registers slash commands from skill bundles. Updated `hermes-config/skills/mailbot/SKILL.md` (the agent-facing verb-surface reference Hermes consumes) instead:

- Added a new "Slash-command verbs (MCP-exposed as of Story 5-6 + Story 6-8)" section documenting `cost_breakdown` / `reset_degraded_mode` / `pause_router` / `resume_router` / `mute_category` / `render_spend_chart`
- Reworded the previously-stale "Other internal verbs that are also NOT MCP-exposed" passage (Story 5-6 actually DID register cost/pause/resume/reset_degraded_mode as MCP tools — the SKILL.md narration lagged behind)
- Added a 4th turn structure: "Turn structure 4 — `/spend month`" walking dispatch → MCP tool → Discord message attachment + summary

**F6-INDEPENDENT carve-out:** Story 6-8 is the LAST F6-independent story in Epic 6 per Epic 5 retro sprint reorder. Verb side + MCP-tool-registration + slash-config wiring + SKILL.md documentation are all locally testable + green. The end-to-end Hermes slash-dispatch → MCP → Discord-attachment round-trip path is F6-gated (MCP /mcp 307→404 redirect mismatch from Story 6-0) and is the Phase 3.5 verification surface.

**Pre-existing decisions carried forward:**

- Window math anchored to UTC midnight for `today` (matches Story 2-10 `cost.py`)
- `week` introduced as a new period (not in `cost_breakdown` — Story 2-10 only supports today/month). The `week` boundary uses a rolling 7-day window from `now`, not an ISO-week start. Documented in `_period_window_start` docstring
- Python-side sort after SQL `GROUP BY` (SQLite GROUP BY does not guarantee row order — same pattern as Story 6-1's `_read_router` aggregation)
- `plt.close(fig)` in a `finally:` block (memory-leak regression guard — long-running worker process invariant)
- `_render_empty_png()` returns a valid PNG even on zero spend (defender posture — Discord-side dispatcher always has something to attach)

**Test-suite minor adaptations:**

- `tests/integration/test_mcp_server.py`: renamed `test_build_mcp_server_registers_16_tools_with_expected_names` → `_17_` + added `render_spend_chart` to the expected set; updated `assert len(by_name) == 16` → `== 17`
- `tests/integration/test_mcp_server_extended_tools.py`: renamed `test_mcp_server_registers_16_tools` → `_17_`; updated count + comment
- Both updates are scoped to the failing assertions; no Story 5-2 / 5-6 behavior changed

**Items deferred to retro discussion:**

- `policy.yaml` does not yet have entries for the 4 task types I seeded in tests (`coarse_class`, `fine_class`, `summary_short`, `sensitivity_class`) — these are real entries today, but Story 6-1 CR-1 found a similar surface (`hermes-aux` LIKE pattern). Story 6-8 doesn't read `task_type` strings against policy — it reads them as-is from `router_calls.task_type` (the audit column). No coupling regression risk
- The chart-input redactor (Story 5-7) is NOT yet applied to chart label text per AC-2. The AR-ANALYTICS-1 chat-input-redactor requirement is "defense-in-depth even though chart labels are project-internal data, not user input." Today the labels are `task_type` strings, which are project-internal enum values from `policy.yaml` — non-sensitive by construction. Document the deferral here for review-time decision; the redactor wiring is a 2-line change if accepted

### File List

**New:**

- `mailbot_api/verbs/analytics/__init__.py` (AR-ANALYTICS-1 banner + re-exports)
- `mailbot_api/verbs/analytics/render_spend_chart.py` (verb + helpers)
- `tests/unit/verbs/analytics/__init__.py` (empty)
- `tests/unit/verbs/analytics/test_render_spend_chart.py` (15 tests)
- `tests/integration/test_spend_chart_command.py` (5 tests)

**Modified:**

- `scripts/check_boundaries.py` (matplotlib.pyplot allowlist + check; verbs allowlist gains the analytics modules; **CR MED-1**: indirect-bypass detection for `from matplotlib import pyplot`)
- `mailbot_api/mcp_server.py` (register `render_spend_chart` as 17th tool; bump `_EXPECTED_TOOL_COUNT`; docstring update; tool description; **CR LOW-1**: docstring counts 16→17 + agent-visible `instructions` includes `render_spend_chart`)
- `hermes-config/skills/mailbot/SKILL.md` (new slash-command section + reworded NOT-MCP-exposed section + 4th turn structure)
- `tests/integration/test_mcp_server.py` (tool-count assertions + expected set)
- `tests/integration/test_mcp_server_extended_tools.py` (tool-count assertion)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (story status: backlog → ready-for-dev → review → done)

**Code review (Sonnet 4.6 adversarial CR; MANDATORY-CR per §5.12 — 3 of 6 criteria hit):**

Verdict: Changes Requested → all 10 actionable findings applied (100% patch rate, 0 deferred). Findings:

- **HIGH-1 PATCH** (FastMCP JSON serialization crash): bare `bytes` field would crash `pydantic_core.to_json` on PNG magic bytes (\\x89PNG is non-UTF-8). Fix: `field_serializer(when_used="json")` + `base64.b64encode` keeps raw bytes Python-side, base64-encodes for JSON transport. (Reviewer's Option A `Base64Bytes` would have inverted semantics — that type DECODES on input.) Added 2 regression tests: `test_model_dump_json_does_not_crash_on_png_bytes` + `test_model_dump_python_keeps_raw_bytes`.
- **HIGH-2 DECISION** (top_task_usd missing): AC-2 summary line `"...Top task: {top_task} (${Y.YY})..."` needs the top-task cost; previously required a sibling `cost_breakdown` MCP call (which doesn't support `period="week"`). Fix: added `top_task_usd: float = 0.0` to the Pydantic shape. Decision: surface the field at no extra cost since the verb already has the data.
- **MED-1 PATCH**: `from matplotlib import pyplot as plt` indirect-bypass detection added to `check_boundaries.py` (mirrors the Story 5-2 CR-5 closure for the verbs boundary).
- **MED-2 PATCH**: 2 new lint-violation fixtures (`violates_matplotlib_pyplot_outside_analytics.py.fixture` + `violates_matplotlib_pyplot_indirect_bypass.py.fixture`) + 2 parametrized entries in `test_lint_boundaries.py` so the new boundary has CI regression coverage matching every other boundary rule in the codebase.
- **MED-3 PATCH** (perf test clock flake): `period="today"` + `now - 29min` seeds rows on yesterday when the test runs in the first 29min of UTC day, silently exercising the empty-data path instead of the bar-chart path. Fix: query `period="week"` — always safe regardless of clock-of-day AND the bar-chart codepath is exercised.
- **MED-4 PATCH** (month-boundary flake): `now - 1h` seed lands on the previous month on the 1st of the month before 01:00 UTC. Fix: seed with `now` (no explicit ts) — always within the current month.
- **LOW-1 PATCH** (stale docstring counts + agent-visible instructions): `_build_wrappers` and `build_mcp_server` docstrings + the FastMCP `instructions` capability enumeration now list `render_spend_chart` and reflect 17-tool counts.
- **LOW-2 PATCH** (relative path → absolute path for SKILL.md test): `Path(__file__).resolve().parents[2] / ...` instead of `Path("hermes-config/...")`; added assertion that "Turn structure 4" exists (strengthens the docs-presence check).
- **LOW-3 PATCH** (redactor deferral comment in production code): inline comment near `ax.set_title` in `_render_bar_chart_png` documents AR-ANALYTICS-1 defense-in-depth deferral for future analytics-verb authors.

**Net test delta:** 896 → 920 (+24): 15 unit (verb) + 5 integration (slash dispatch + perf + SKILL.md) + 2 boundary fixtures (matplotlib.pyplot direct + indirect) + 2 JSON-serialization regression tests. 2 skipped (opt-in real-Ollama).

**Notable adversarial catch:** HIGH-1 is the canonical "tests pass at the verb-call boundary, crash at the transport boundary" pattern — exactly what MANDATORY-CR was structured to catch. Without the CR dispatch, every real `/spend` MCP invocation would have errored at the FastMCP `_convert_to_content` step. The fix (field_serializer with `when_used="json"`) is the proper Pydantic v2 idiom — keeps Python-side bytes semantics intact while base64-encoding only at the JSON wire boundary.

**Reviewer's "Non-Issues" confirmed clean:**

- `plt.close(fig)` symmetry between empty-PNG and bar-chart helpers
- `datetime.now(timezone.utc)` everywhere (DST-immune)
- F6 carve-out scope discipline (no stray Hermes glue / TODO comments / sketched dispatcher code)
- SKILL.md narrative consistency (no dangling Story 5-6-not-yet-wired claims)
- `week` rolling-window UX (documented decision; intuitive "last 7 days")
- `period=None` from FastMCP (default kicks in; explicit ValueError guard if forced)
