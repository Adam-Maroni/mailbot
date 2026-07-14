# Story 10.6.5: Hermes per-turn tool-surface fidelity — the MailBot email verbs must reach the chat turn

---
baseline_commit: 71b154eb6470f3a3bb3781160497293371fa5461
---

Status: done (spawned 2026-07-14 from WALK-10-6-4-F1. Dev + MANDATORY-CR + AC-1 live walk complete. DONE at the scope it owns — tool-surface fidelity: two pollution channels closed [built-ins + `skills`], `find_emails` demonstrably reaches qwen's function list [ListTools proof]. Epic 10.6 done-flip clause 3b stays PENDING — the last mile [qwen actually SELECTING find_emails + emitting a well-formed call] is a qwen-fidelity residual [F-10-6-5-W1] deferred to a dedicated qwen-management epic per Adam 2026-07-14)
Epic: 10.6 (Capability Reachability) — sprint-status key `10-6-5-hermes-tool-surface-fidelity`

**Spawned by Adam (2026-07-14):** the 10-6-4 Adam-typed Discord walk proved the latency fix (a qwen chat turn completes within budget on the real persona path — done-flip clause 3a) but exposed that the turn's tool surface is polluted by unrelated Hermes skills, so the MailBot email verbs never reach the model. This story closes done-flip **clause 3b** (tool fidelity). Epic 10.6 cannot done-flip without it.

## Story

As Adam,
I want a real Discord chat turn ("find my unread emails") to actually invoke the MailBot email verb (a `find_emails`/peer tool-call), not zero-tool-call improvisation,
So that the cheap lane is genuinely *usable* — the qwen turn reaches the mailbox, closing the "REACHED → USABLE" gap end-to-end (10-6-4 made it fast; this makes it useful).

## Diagnosis (measured live at the 10-6-4 walk — see WALK-10-6-4-F1)

Full evidence: [WALK-10-6-4-F1-hermes-tool-surface-pollution.md](WALK-10-6-4-F1-hermes-tool-surface-pollution.md).

- Adam typed "find my unread emails" → bot replied `qwen (local, free)`: "None of the provided functions can be used to find unread emails... these functions are related to text-to-speech, managing task lists, analyzing images, writing files..." then improvised generic Gmail instructions.
- DB `router_calls`: `2026-07-14T08:50:21Z, task=chat_completions_tool_call, model_chosen=qwen2.5:3b, outcome=ok, tool_calls_count=0`. The turn RAN + completed on qwen (latency fix works) but **zero tool calls** — wrong tools on the surface.
- **The MailBot verbs ARE registered + reachable** (rules out missing-capability): `mailbot-api` FastMCP `ToolManager` exposes 26 tools incl. `find_emails`, `hydrate_email`, `count_emails`, `get_sender_summary`, `propose_action`, `draft_reply` (introspected live); api served a `ListToolsRequest` on the fresh MCP session at 08:50:39Z.
- **Hermes registered a swarm of unrelated user skills this session:** songsee, gif-search, spotify, heartmula, spike, debugging-hermes-tui-commands, node-inspect-debugger, jupyter-live-kernel, python-debugpy, xurl, writing-plans, etc. These crowd out / replace the mailbot-api MCP tools on the persona's per-turn surface.
- **Isolating contrast:** the agent-driven endpoint probe (same code, same qwen) supplied its OWN correct 4-tool email surface → `tool_calls_count=1`, `find_emails` picked, 1.7–4.9s. The ONLY difference is which tools were on the surface → pins the defect to the Hermes tool-registration layer.

**Root cause:** Hermes-side tool-SELECTION/SURFACE problem in this container, NOT a MailBot code defect. Fix locus is `hermes-config/` (this container's skill + MCP registration), NOT `mailbot_api`.

## Scope

Hermes-config only. Do NOT touch `mailbot_api` (the 26 verbs are correct + registered). Two candidate approaches (pick at dev time after inspecting the actual Hermes tool-surface assembly):

### Approach A — prune the Hermes skill/MCP registration
Disable the unrelated user-installed skills (songsee, spotify, gif-search, dev-tooling, TTS/image, etc.) for the MailBot deploy profile so the `mailbot-api` MCP server's tools dominate the per-turn surface. Likely the `hermes-config/` skill registration / `.hub` config or the reconcile profile.

### Approach B — per-turn tool allow-list scoped to the mailbot-api server
If Hermes supports server-scoped or persona-scoped tool filtering for a channel, restrict a MailBot chat turn to only offer the mailbot-api verbs (+ any essential Hermes built-ins). More surgical; survives future skill installs.

Verify against Hermes's real tool-surface assembly (RECONCILIATION-NOTES §6 item 1 — the skill-bundle-under-`hermes-config/skills/mailbot/` migration is adjacent territory).

## Tasks / Subtasks

Dev-pass live investigation (2026-07-14, this run) pinned the exact fix locus — **Approach B, expressed as a repo-tracked config key**:

- The Hermes runtime resolves the per-turn Discord tool surface from `config.yaml`'s **`platform_toolsets.discord`** key (`hermes_cli/tools_config.py:_get_platform_tools` / `_save_platform_tools`). When that key holds an explicit list of configurable toolset names, `has_explicit_config=True` and **only** the listed toolsets are enabled by direct membership; MCP-server names (`mailbot-api`) listed alongside are preserved separately.
- Live `hermes tools list --platform discord` proved the pollution: built-in toolsets `web, browser, terminal, file, code_execution, vision, image_gen, tts, skills, todo, delegation, computer_use, …` are all ENABLED on the Discord surface (these are the "TTS/task/image/write-file tools" qwen named in WALK-10-6-4-F1), while `mailbot-api  all tools enabled`. The 26 MailBot verbs are present but drowned.
- Fix = add a `platform_toolsets.discord` allow-list to the **tracked** `hermes-config/config.yaml` that keeps only the toolsets a MailBot email turn needs (+ the `mailbot-api` MCP server), dropping the noise built-ins. This is repo-trackable (Approach B) — NOT a runtime-only op — because `config.yaml` is bind-mounted at `/opt/data/config.yaml` and is one of the four git-tracked files under `hermes-config/`.

- [x] **Task 1 (AC-2) — Add the `platform_toolsets.discord` allow-list to `hermes-config/config.yaml`.** DONE — allow-list `[mailbot-api, messaging, cronjob, memory, clarify, skills]` added with rationale comment + verify-runbook note. Live-resolver proof: `_get_platform_tools(cfg,"discord")` → `{clarify,cronjob,kanban,mailbot-api,memory,messaging,skills}`, noise leaked=none, mailbot-api present=True. (RED: extend `tests/integration/test_hermes_config.py` with a failing assertion that `config["platform_toolsets"]["discord"]` exists, contains the `mailbot-api` MCP server, contains the minimal keep-set, and EXCLUDES the noise toolsets `tts`/`image_gen`/`vision`/`video`/`file`/`browser`/`terminal`/`code_execution`/`web`/`todo`/`delegation`/`computer_use`.) GREEN: write the `platform_toolsets: {discord: [...]}` block. Keep-set: `memory`, `clarify`, `messaging`, `cronjob`, `skills` (skills toolset kept so the MailBot SKILL.md discovery/`list,view` tools remain), plus the `mailbot-api` MCP server name. REFACTOR: inline a comment block explaining the allow-list rationale + the `hermes tools list --platform discord` verification path (runbook carry-forward for CP-1 deploy).
- [x] **Task 2 (AC-2) — Structural drift test.** DONE — 3 offline YAML-shape drift gates in `test_hermes_config.py`: `test_hermes_config_has_discord_toolset_allowlist` (key exists + explicit list), `..._keeps_mailbot_verbs` (required keep-set incl. `mailbot-api` present), `..._excludes_noise_toolsets` (12-toolset forbidden set absent). Red-gates re-pollution. Assert the allow-list shape in `test_hermes_config.py`: `mailbot-api` present, noise-toolsets absent, `platform_toolsets` is a mapping keyed by platform. Red-gates a regression that re-pollutes the surface (mirrors 10-5-6's `test_recognized_phrase_dispatch.py` drift-gate pattern).
- [x] **Task 3 (AC-3, AC-4) — No-regression assertions on the safety + sensitivity gates.** DONE — config-only change touches zero `mailbot_api` source; gate suites green: `test_mint_requires_user_confirmation.py` + `test_sensitive_escalation_handshake.py` + `test_authorization.py` = 65 passed. The `mailbot-api` MCP server stays fully enabled in the allow-list (proven by the live resolver), so `propose_action`/`mint_sensitivity_token`/`draft_reply` remain reachable; gates are model- and tool-surface-independent. The drain safety gate (`pending_actions`/`action_grants` key on `(action_type, email_id)`, no model column) and the sensitivity gate (NFR-PRIV-2) are BOTH model-independent and tool-surface-independent — a config-only toolset allow-list cannot touch them. Add/confirm a test that the `mailbot-api` MCP server stays fully enabled (so `propose_action`/`mint_sensitivity_token`/`draft_reply` remain reachable) and reference the existing gate coverage (`test_mint_requires_user_confirmation.py`, `test_sensitive_escalation_handshake.py`, `test_authorization.py`) as the standing proof the gates are unaffected. No `mailbot_api` code change → those suites stay green.
- [x] **Task 4 (AC-5) — Gates.** DONE — ruff (full repo) clean; mypy-strict `mailbot_api` clean (134 files); full pytest 1940 passed / 3 skipped / 3 deselected (+3 net = the 3 new drift tests). MANDATORY-CR (reviewer sonnet-5 ≠ dev opus-4-8) pending Step 2.4.

**Out of scope (do NOT do):** any `mailbot_api/` change (the 26 verbs are correct + registered — confirmed live via `mailbot-api  all tools enabled`); pruning the gitignored `hermes-config/skills/` bundled-skill tree (that's runtime container state, not repo-trackable; the toolset allow-list is the load-bearing tracked fix and dominates the surface without touching the bundle). AC-1/AC-6 live Discord walk = Adam-hands-on Phase 3.5 (closes done-flip clause 3b).

## Dev Notes

### Technical requirements / architecture compliance

- **Fix locus (verified live 2026-07-14):** `hermes-config/config.yaml` — the git-tracked, bind-mounted (`/opt/data/config.yaml`) Hermes container config. One of only four tracked files under `hermes-config/` (`AGENTS.md`, `SOUL.md`, `config.yaml`, `skills/mailbot/`); the whole `skills/` tree except `skills/mailbot/` is gitignored runtime state (root `.gitignore:65-71`).
- **Mechanism:** `platform_toolsets.<platform>` is Hermes's per-platform tool allow-list. Semantics confirmed by reading `/opt/hermes/hermes_cli/tools_config.py` in the live container: an explicit list of configurable toolset keys → only those toolsets enabled (direct membership, `has_explicit_config` branch); MCP server names in the same list are preserved via `_save_platform_tools`'s `preserved_entries`. `CONFIGURABLE_TOOLSETS` names: `web, browser, terminal, file, code_execution, vision, video, image_gen, video_gen, x_search, moa, tts, skills, todo, memory, context_engine, session_search, clarify, delegation, cronjob, messaging, homeassistant, spotify, discord, discord_admin, yuanbao, computer_use`.
- **Keep-set rationale:** `mailbot-api` (the 26 email verbs — the whole point); `messaging` (Rule R cross-platform notification send); `cronjob` (Story 6-10 digest/notification-pull jobs run attached skills); `memory` + `clarify` (defender-persona hygiene — ask-for-clarification tiebreaker in AGENTS.md); `skills` (📚 `list/view/manage` — keep so the MailBot SKILL.md remains discoverable; its tools are meta not noise, and the skill-PROMPT injection is a separate snapshot mechanism). Drop everything else — the built-in `tts/image_gen/vision/video/file/browser/terminal/code_execution/web/todo/delegation/computer_use` toolsets are the exact noise WALK-10-6-4-F1 saw qwen enumerate.
- **This mirrors the `hermes fallback add` carry-forward pattern:** the config KEY is repo-tracked, but a first-deploy operator may also want to run `hermes tools disable <noise> --platform discord` interactively OR the config.yaml key applies at container restart. Capture the config-key path as the durable, testable fix; note the live-verification command (`hermes tools list --platform discord`) in the runbook for CP-1.

### File structure requirements

- Config: `hermes-config/config.yaml` (add top-level `platform_toolsets:` block).
- Test: `tests/integration/test_hermes_config.py` (add drift-gate assertions; offline YAML-shape, no Docker/Discord/Anthropic dependency — matches the file's existing contract).
- No `mailbot_api/` source files. No migrations. No new deps.

### Testing requirements

- pytest (offline shape test in `test_hermes_config.py`); ruff + mypy-strict gates (config + test only — the `mailbot_api` suite is unchanged since no source module is touched).
- Live Discord L3 (AC-1/AC-6) is Adam-hands-on Phase 3.5; MCP session-drop caveat (F-10-5-1-W2): restart hermes after any api restart before the re-walk.

### References

- Source of truth: [WALK-10-6-4-F1-hermes-tool-surface-pollution.md](WALK-10-6-4-F1-hermes-tool-surface-pollution.md); epics.md § Epic 10.6 roster addendum (10.6.5 row + clause 3b).
- Live-container investigation (this run): `/opt/hermes/hermes_cli/tools_config.py` (`_get_platform_tools`, `_save_platform_tools`, `CONFIGURABLE_TOOLSETS`, `_DEFAULT_OFF_TOOLSETS`); `hermes tools list --platform discord`; `hermes-config/.skills_prompt_snapshot.json` + `skills/.bundled_manifest` (88-skill pollution set).
- Pattern precedents: 10-5-6 `test_recognized_phrase_dispatch.py` (structural drift gate); RECONCILIATION-NOTES §1.4 (skills auto-registration), §6 item 1 (skill-bundle migration territory).
- Memory: [[project_reached_not_equal_usable]], [[project_hermes_mcp_namespaces_and_session_drop]].

## Acceptance Criteria

- **AC-1** — On a live Discord "find my unread emails" turn, the DB `router_calls` row shows `tool_calls_count ≥ 1` with a MailBot verb (`find_emails` or peer), NOT `tool_calls_count=0` improvisation. (This is the WALK-10-6-4-F1 reproduction, now passing.)
- **AC-2** — The per-turn tool surface presented to the model contains the MailBot email verbs and is NOT dominated by unrelated skills (TTS/image/task/dev-tooling). Evidence: config diff + the tool list actually sent on a turn (Hermes debug log or a captured request).
- **AC-3** — No regression to the model-independent drain safety gate (reversible executes / irreversible prompts) — unaffected by tool-surface changes, but confirm the confirmation machinery still fires on an irreversible verb.
- **AC-4** — Sensitivity gate preserved (a confidential/sensitive email tool-call still routes per NFR-PRIV-2).
- **AC-5** — MANDATORY-CR reviewer ≠ dev (persona/tool-registration seam). Any `mailbot_api` tests stay green (this should be a Hermes-config-only change; if truly zero `mailbot_api` change, the suite is unchanged).
- **AC-6** — Phase 3.5 live Discord re-walk (Adam-hands-on, $0): "find my unread emails" → qwen invokes `find_emails` → the bot returns actual unread emails. **Closes done-flip clause 3b.** Then a follow-up chained turn ("mark the first one as read") exercises the reversible-execute path live.

## Risks / Notes

- **Config-only, container-scoped.** The fix likely lives in this Hermes container's skill/MCP registration, which may not be a clean repo-tracked file (`hermes-config/` has a large vendored `.hub`/skills tree). Capture the exact change locus + whether it's repo-trackable or a container-runtime setting; if runtime-only, document the setup step for CP-1/deploy (like the `hermes fallback add` runbook carry-forward).
- **Do NOT chase the model.** qwen behaved correctly given the wrong tools — this is not a qwen fidelity issue (contrast the 10-6-1 argument-fidelity work). The 3B model refusing to hallucinate email tools it wasn't given is arguably correct behavior.
- **MCP session-drop (F-10-5-1-W2):** restart hermes after any api restart before the re-walk.
- Relationship: closes WALK-10-6-4-F1. Inside Epic 10.6 done-flip **clause 3b** (Adam split clause 3 into 3a-latency [10-6-4, done] / 3b-tool-fidelity [this story] on 2026-07-14). Sibling to 10-6-4 (latency, clause 3a) and 10-6-2 (draft reach, clause 4). Memory: [[project_reached_not_equal_usable]], [[project_hermes_mcp_namespaces_and_session_drop]].
- **Repo-trackability resolved (dev-pass finding):** the Risks note above hedged "may not be a clean repo-tracked file." The live investigation resolved it: the load-bearing fix IS repo-trackable — `platform_toolsets.discord` in the tracked `hermes-config/config.yaml`. Pruning the gitignored bundled-skill tree is a secondary, runtime-only lever that the config allow-list makes unnecessary (the allow-list dominates the surface regardless of what's bundled).

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (dev); review pass: claude-sonnet-5 (Step 2.4, reviewer ≠ dev).

### Debug Log

- **Fix-locus discovery was the load-bearing dev work.** The spawn spec offered two approaches (prune skills / per-turn allow-list) and flagged the fix "may not be repo-trackable." Live investigation of the running `mailbot-hermes` container resolved it: read `/opt/hermes/hermes_cli/tools_config.py`, found `platform_toolsets.<platform>` is Hermes's per-platform tool allow-list with explicit-membership semantics + MCP-server preservation. This is a repo-tracked `config.yaml` key → Approach B, dev-codeable.
- `hermes tools list --platform discord` reproduced the pollution live: web/browser/terminal/file/code_execution/vision/image_gen/tts/todo/skills/… all enabled alongside `mailbot-api  all tools enabled` — the email verbs present but drowned. Matches WALK-10-6-4-F1's "TTS/task/image/write-file" qwen enumeration exactly.
- Verified the fix through the REAL Hermes resolver (not just YAML shape): loaded the candidate `config.yaml` into `_get_platform_tools(cfg,"discord")` inside the container → `{clarify,cronjob,kanban,mailbot-api,memory,messaging,skills}`; noise-set leaked = none; `mailbot-api` present = True. `kanban` is a Hermes-preserved non-configurable entry (collaboration board, not tool noise; not in the forbidden set).
- Decided to KEEP the `skills` toolset (📚 list/view/manage): its tools are skill-discovery meta-tools, and the MailBot SKILL.md prompt injection is a separate snapshot mechanism — dropping `skills` would risk the persona losing its own verb reference. The noise was the built-in `tts/image_gen/vision/file/todo/…` schemas, which the allow-list drops.

### Completion Notes List

- **AC-2 (surface not dominated by unrelated skills):** repo-tracked `platform_toolsets.discord` allow-list in `hermes-config/config.yaml` keeps only `[mailbot-api, messaging, cronjob, memory, clarify, skills]`; live resolver confirms the 12 noise built-ins (tts/image_gen/vision/video/file/browser/terminal/code_execution/web/todo/delegation/computer_use) are OFF and `mailbot-api` (26 verbs) is ON. Config-diff + live tool-list both captured.
- **AC-3 (drain safety gate) + AC-4 (sensitivity gate):** unaffected — config-only, zero `mailbot_api` source touched; gates are model- and tool-surface-independent (`pending_actions`/`action_grants` key on `(action_type, email_id)`, no model column; NFR-PRIV-2 enforced at the router precondition layer). 65 gate-suite tests green; `mailbot-api` MCP server stays fully enabled so all verbs remain reachable.
- **AC-5:** ruff/mypy/pytest green; MANDATORY-CR reviewer ≠ dev (Step 2.4).
- **AC-1 / AC-6 (live Discord walk):** Adam-hands-on Phase 3.5 — "find my unread emails" → qwen invokes `find_emails` (`tool_calls_count ≥ 1`), then a chained "mark first as read" reversible-execute. Closes done-flip clause 3b. NOT dev-codeable (real Discord + real qwen).

### File List

- `hermes-config/config.yaml` (modified — added `platform_toolsets.discord` allow-list block + rationale/verify-runbook comment)
- `tests/integration/test_hermes_config.py` (modified — +4 drift-gate tests [3 dev + 1 CR-added mcp-server guard] + `_discord_allowlist` helper + 2 module-level frozenset constants; `skills` added to the forbidden set at the AC-1 walk)
- `_bmad-output/implementation-artifacts/10-6-5-hermes-tool-surface-fidelity.md` (this file — augmented Tasks/Dev-Notes/Dev-Agent-Record)
- `_bmad-output/implementation-artifacts/10-6-5.pre-review.md` (pre-review self-audit)

### Change Log

- 2026-07-14 — Config-only tool-surface fidelity fix: `platform_toolsets.discord` allow-list in `hermes-config/config.yaml` scopes the Discord per-turn surface to the MailBot email verbs (+ essential built-ins), dropping the noise toolset swarm that drowned them (WALK-10-6-4-F1). +4 offline drift tests. Suite 1937→1941. AC-1/AC-6 live walk owed at Phase 3.5.

## Review Findings (MANDATORY-CR — reviewer claude-sonnet-5 ≠ dev claude-opus-4-8)

3-hunter adversarial review of the config-only diff + the ESCALATED §4 item (does keeping `skills` re-admit noise). 4 findings, all dispositioned:

- **CR-10-6-5-1 (test-coverage gap — future 2nd MCP server auto-injects) — FIXED.** A future entry under `mcp_servers` would be Hermes-preserved onto the Discord surface (`_save_platform_tools.preserved_entries`) and could re-pollute without any test catching it. Added `test_hermes_config_every_mcp_server_is_on_the_discord_allowlist` — forces every registered MCP server to be an explicit, reviewed member of `platform_toolsets.discord`.
- **CR-10-6-5-2 (KeyError vs descriptive AssertionError) — FIXED.** Drift gates indexed `config["platform_toolsets"]["discord"]` directly → bare `KeyError` on regression, obscuring triage. Extracted `_discord_allowlist(config)` helper with a descriptive `platform_toolsets`-mapping assert.
- **CR-10-6-5-3 (YAML scalar silently char-iterates) — FIXED.** If `discord` were authored as a string, `set(discord_list)` iterated characters silently. The helper now asserts `isinstance(discord_list, list)` with a clear type-error message before any `set()`.
- **CR-10-6-5-4 (skills-toolset sufficiency rests on live Hermes behavior) — RESOLVED BY REMOVAL at the AC-1 walk.** Initially ACCEPT-WITH-RATIONALE (not offline-testable). The 2026-07-14 AC-1 live walk DISPROVED the "skills is safe meta-tools only" assumption — `skills` resolved a competing `gmail_get_unread_emails` onto the surface and qwen picked it (walk 1). Per the CR's own fallback ("if a future walk shows noise back, drop `skills`"), `skills` was removed from the allow-list; the drift forbidden-set now red-gates its return. Residual closed by removal, not acceptance.

Post-CR: config drift suite 9→10 tests; ruff (full)/mypy-strict(134)/pytest all green; live `_get_platform_tools` resolver re-verified clean (noise leaked=none, mailbot-api present). No production-logic change (test-hardening + config comment only) → no round-2 review warranted.

## Completion Notes

### 2026-07-14 — Dev pass + MANDATORY-CR (autonomous-story-run; dev=opus-4-8, review=sonnet-5)

DONE at L1/L2 (code-complete + self-verified via the live Hermes resolver). Config-only tool-surface fidelity fix closing WALK-10-6-4-F1 / done-flip clause 3b.

**Shipped (final, post-walk):** `platform_toolsets.discord` allow-list in the git-tracked `hermes-config/config.yaml` — `[mailbot-api, messaging, cronjob, memory, clarify]` (**`skills` dropped at the AC-1 walk** — see the AC-1 LIVE WALK note below) — scopes the Discord per-turn tool surface so the 26 registered MailBot MCP verbs dominate, dropping the 12 noise built-in toolsets (`tts/image_gen/vision/video/file/browser/terminal/code_execution/web/todo/delegation/computer_use`) that WALK-10-6-4-F1 saw qwen enumerate ("TTS/task/image/write-file"). Approach B (per-turn allow-list) expressed as a repo-tracked config key — the dev-pass investigation resolved the spec's "may not be repo-trackable" hedge by reading `/opt/hermes/hermes_cli/tools_config.py` live and confirming `platform_toolsets.<platform>` is Hermes's per-platform allow-list with explicit-membership semantics + MCP-server preservation.

**Verification (L2):** loaded the candidate config into the container's own `_get_platform_tools(cfg,"discord")` → resolved `{clarify,cronjob,kanban,mailbot-api,memory,messaging,skills}`, noise leaked=none, mailbot-api present. This is the real Hermes code path, not just YAML shape. 4 offline drift gates in `test_hermes_config.py` red-gate re-pollution (incl. the CR-added guard that any future MCP server must be an explicit allow-list member).

**Gates:** ruff (full repo) clean; mypy-strict `mailbot_api` clean (134 files); pytest 1941+3skip+3desel (+4 net vs 10-6-4's 1937). AC-3/AC-4 safety+sensitivity gates unaffected (config-only, zero `mailbot_api` source; 65 gate-suite tests green; mailbot-api MCP server stays fully enabled).

**MANDATORY-CR (sonnet-5 ≠ opus-4-8):** 4 findings → 3 FIXED (MCP-server auto-inject guard test; KeyError→descriptive assert; YAML-scalar type guard) + 1 ACCEPT-WITH-RATIONALE (skills-toolset sufficiency rests on live Hermes behavior, not offline-testable — documented at fix site, guarded by AC-6 walk + CP-1 runbook check).

### 2026-07-14 — AC-1 LIVE WALK (Adam-typed, orchestrator DB-verified) → surface fix PROVEN, done-flip clause 3b NOT closed (qwen fidelity residual → new epic)

Two Adam-typed "find my unread emails" walks against the live stack. The walks did their job: they proved the surface fix works AND surfaced that the remaining blocker is qwen tool-call **fidelity**, not tool-surface — a different class that Adam has decided to own in a dedicated **qwen-management epic**, not by further iterating this story.

**Infra fix during the walk (not a code defect):** the first turn hit `PermissionError: /opt/data/sessions/sessions.json` — the mid-run `docker restart mailbot-hermes` had left `/opt/data/sessions|gateway|logs|cron` owned `root:root` (0700) so the `hermes` uid-10000 process couldn't write session state. Fixed in-container via `chown -R hermes:hermes` on those runtime dirs. This is a DEPLOY/ops note (the image's cont-init chown vs a manual restart), captured for the CP-1 runbook — NOT a repo code change.

**Walk 1 (allow-list still included `skills`):** qwen selected `gmail_get_unread_emails` + `skills_list` (router_calls id=14913/14914, `tool_calls_count=1`) and NEVER reached `find_emails`. Root cause: the `skills` toolset resolves the installed 88-skill catalog's tools onto the turn surface at runtime (incl. a competing Google-Workspace `gmail_get_unread_emails`) — a SECOND pollution channel, distinct from the built-ins and invisible to `hermes tools list` (which shows toolset NAMES, not their turn-time tool expansion). This is exactly the CR-10-6-5-4 residual, now CONFIRMED live. **FIX APPLIED:** dropped `skills` from the allow-list (`[mailbot-api, messaging, cronjob, memory, clarify]`); forbidden-set drift test extended to red-gate `skills`; live resolver + `hermes tools list` re-confirmed `skills` off, `mailbot-api` on.

**Walk 2 (skills dropped):** surface pollution GONE — no more gmail/skills tools. But qwen (a) picked `send_message` (from the `messaging` toolset) instead of `find_emails`, AND (b) emitted the call as literal `<tool_call>{"name":"send_message",...}</tool_call>` TEXT instead of a structured function call → the harness couldn't dispatch it → router_calls id=14937 `tool_calls_count=0`. api logs confirm hermes DID `ListToolsRequest` the mailbot-api MCP server that turn (so `find_emails` WAS on qwen's function list). This is a qwen tool-SELECTION + tool-call-FORMAT fidelity problem on a clean surface — the sibling class to 10-6-1 (arg fidelity) / 10-6-4 (latency), NOT a tool-surface defect.

**Adam decision (2026-07-14):** stop iterating here — "save current advancement and wrap up this story; we will plan a whole epic toward qwen management." This story's scope ("the MailBot email verbs must REACH the chat turn") is L3-DONE: the surface is clean and `find_emails` demonstrably reaches qwen's function list (ListTools proof). Closing the last mile (qwen actually SELECTING it + emitting a well-formed call) is deferred to the qwen-management epic.

**Story disposition:** DONE at the scope it owns (tool-surface fidelity — email verbs reach the turn; two pollution channels closed: built-ins + `skills`). Epic 10.6 done-flip **clause 3b stays PENDING** — it requires a real turn where qwen INVOKES `find_emails` (`tool_calls_count ≥ 1`), which is now blocked on qwen fidelity, not surface. Filed follow-up: **F-10-6-5-W1 (qwen tool-selection/format fidelity on a clean surface)** → qwen-management epic. Candidate next lever (untested, for that epic): `messaging` also exposes a plausible-but-wrong `send_message`; trimming the allow-list further toward `mailbot-api`-only may reduce mis-selection, but the text-not-structured-call format bug is a model/harness issue independent of surface.

**Staged, nothing committed.** Live `mailbot-hermes` currently runs the `skills`-dropped config (restarted + perms-fixed this session).

