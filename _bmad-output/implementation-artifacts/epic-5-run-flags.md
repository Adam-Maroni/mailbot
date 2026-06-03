# Epic 5 — Autonomous Run Flags + Phase 3.5 Walk Record

**Generated:** 2026-06-02 by autonomous-epic-run
**Dev model:** claude-opus-4-7 (1M context)
**Review model:** claude-sonnet-4-6 (dispatched per §5.12 MANDATORY-CR verdicts)
**Final test count:** 845 (+131 net from 714 baseline)
**Stories completed (code-level):** 5-2 (carry-over close), 5-3, 5-4, 5-5, 5-6, 5-7, 5-8, 5-9

**Phase 3.5 outcome:** PASS at the mailbot-api boundary; **architectural mismatch surfaced for Hermes runtime (Stories 5-4 / 5-5 / 5-6 runtime side)** — carried forward to Epic 6 per Adam decision.

> NOTE on filename: this file is `epic-5-run-flags.md` (versioned) because
> the generic `epic-run-flags.md` is already the Epic 1 final-flags artifact
> at HEAD.

---

## Per-story summary table

| Story | Status | Tests delta | CR cadence | CR findings (applied / found) | Applied % | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| 5-2 | done (carry-over close) | n/a (prior session) | MANDATORY-CR (prior) | 7/7 | 100% | Row truncated by this run; story file already `done` |
| 5-3 | done | +35 | GATE-COVERAGE-ELIGIBLE → CR dispatched | 5/5 actionable + 3 DEFER | 100% | Patch CR-1: `tone_signals_used` required-field → default_factory=list |
| 5-4 | done (code-level) | +11 | GATE-COVERAGE-ELIGIBLE → CR SKIPPED | n/a | n/a | **Phase 3.5 surfaced architectural mismatch — see Phase 3.5 record below.** Code shipped works; the assumed runtime contract with Hermes does not. |
| 5-5 | done (code-level) | +18 | GATE-COVERAGE-ELIGIBLE → CR SKIPPED | n/a | n/a | Pure-docs SOUL.md + AGENTS.md + skills/mailbot/SKILL.md. Files exist + content verified at code-level. Whether Hermes actually loads them depends on 5-4 carry-forward. |
| 5-6 | done (code-level) | +17 | MANDATORY-CR | 7/7 PATCH + 3 DEFER | 100% | mailbot-api side (MCP server bump 11→16, mute_category verb, migration 018) all live + tested. Discord-side dispatch depends on 5-4 carry-forward. |
| 5-7 | done | +22 | MANDATORY-CR (privacy) | 6/6 actionable + 1 DEFER | 100% | **CRITICAL CR-3 fix**: Bearer token base64 `==` padding was leaking into "redacted" output. Privacy regression caught + fixed via lookahead. |
| 5-8 | done | +14 | MANDATORY-CR (orchestrator) | 6/6 actionable + 1 DEFER | 100% | **CRITICAL CR-3 fix**: null projection fields rendering as `from=None` in LLM context (FR-4.3 accuracy degradation risk). Fixed with "unknown" sentinels. |
| 5-9 | done | +14 | MANDATORY-CR (load-bearing + privacy + cost — 3 §5.12 criteria fire) | 7/7 | 100% | **CRITICAL F1 fix**: sensitivity tokens are task_type-bound; orchestrator was passing the draft_reply-scoped token to tone_style_mirror Router call → would have broken EVERY sensitive draft in production. Fix: tone gets `confirmation_token=None`. |

**Aggregate applied rate:** 38 / 38 actionable CR findings applied = **100%**.

---

## Phase 3.5 walk record

Adam requested the agent walk Phase 3.5 itself. The agent first walked offline + DB-real surrogates (all PASS — Section A below), then Adam joined for live operator-only checkpoints (Section B). Section B surfaced two operationally-trivial fixes (F1, F2) and one architectural finding (F3-F5) that closes the epic at the mailbot-api boundary with Hermes-side runtime as carry-forward.

### Section A — Offline + DB-real surrogates (agent-walked, all PASS)

| # | Surrogate | Verdict | Evidence |
| --- | --- | --- | --- |
| CP2 | `resolve_prompt(...)` for the 5 chat-side prompts | PASS | All 5 (`intent_parsing_chat`, `reference_resolution`, `draft_reply`, `tone_style_mirror`, `multi_turn_refinement`) resolve via the AR-PAT-5 registry with VERSION="v1". |
| CP3 (offline half) | `scripts/check_hermes_config.py` config-shape walk | PASS at the schema-we-wrote level | Verifier exits 0; documented fields all present. **Important caveat**: schema is what Story 5-4 invented, NOT what Hermes actually expects. See F5. |
| CP4 (file-level) | Defender-voice persona file walk | PASS | SOUL.md / AGENTS.md / SKILL.md present + structural markers verified. Whether Hermes consumes them at runtime depends on F3-F5 carry-forward. |
| CP5 (offline half) | Slash registry vs MCP tool set | PASS at the inventory level | 8 commands registered; cost/confirm/budget-reset all ephemeral; MCP server registers exactly 16 tools. **Important caveat**: the slash_commands block shape is Story 5-6's invention; runtime registration is gated on F3-F5. |
| CP6 | Live redactor walk on exact Anthropic key shape | PASS | `sk-ant-api03-DEADBEEF1234567890ABCDEF` → `[REDACTED:anthropic_key]`; key body gone. CR-3 Bearer `==` padding regression also verified fixed. |
| CP7 | Reference-resolution against real DB | PASS | `resolved_email_ids=('g-norm',)`, `ambiguous=False`. |
| CP8 | Draft-reply capstone happy path (normal email) | PASS | `state='draft_presented'`, body populated; `accept_draft` wrote `pending_actions` row with `status='cooling_off'`. |
| CP9a | Sensitive email without token | PASS | `state='needs_sensitivity_token'`; defender_message contains `/confirm` and `draft_reply`. |
| CP9b | Sensitive email + token with CONSUME-AWARE Router (Story 4-7 task_type-binding) | **PASS — CRITICAL F1 fix verified live** | Consume-aware mock rejects any token reaching tone_style_mirror. With F1 fix in place (token=None passed to tone), the run reaches `state='draft_presented'`. Without F1 fix this would have failed. |
| CP10 | Confidential email refused without dispatch | PASS | `state='confidential_refused'`; Router was NEVER called. |

### Section B — Live operator-walked checkpoints (Adam-side)

#### Finding 1 — `:ro` mount crashes Hermes container — **FIXED**

The bind-mount `./hermes-config:/opt/data:ro` from Story 5-4 AC-2 crashed the Hermes container at init time with `OSError: [Errno 30] Read-only file system: '/opt/data/cron'`. Hermes treats `/opt/data` as its HOME directory and needs to `mkdir cron/` (and chown the tree) on first run.

**Fix applied:** drop `:ro` flag from the bind-mount in `docker-compose.yml`. Added `hermes-config/cron/`, `data/`, `state/`, `logs/`, `.hermes/` patterns to `.gitignore` so Hermes's runtime writes don't pollute the repo. Updated the docker-compose shape test to assert the new no-`:ro` form. Result: Hermes container now starts past init and reaches its supervised-services phase.

This was the failure mode Story 5-4 Dev Notes explicitly anticipated as "verify against the image; Phase 3.5 catches the mismatch." Phase 3.5 caught it; the fix is mechanical.

#### Finding 2 — MCP startup log hardcoded `tools=11` — **FIXED**

`mailbot_api/main.py:222` had a hardcoded `"tools": 11` in the `mcp.startup.live` log line. Story 5-6 bumped `_EXPECTED_TOOL_COUNT` from 11 to 16 but missed this observability line. The live MCP server has 16 tools registered (verified offline at CP5 + via post-fix live log), but the startup log was reporting 11.

**Fix applied:** pull the count from the canonical source (`mailbot_api.mcp_server._EXPECTED_TOOL_COUNT`) instead of hardcoding. Live log now correctly reports `"tools": 16`.

This is a low-severity observability drift, not a functional bug, but it's a Story 5-6 CR miss worth flagging.

#### Finding 3 — Hermes image runs an interactive TUI, not a daemon — **RESOLVED 2026-06-02 (Story 6-0)**

**Resolution:** the image's CMD passes through `/opt/hermes/docker/main-wrapper.sh` which routes non-executable first args as `hermes` subcommands. Setting `command: ["gateway", "run"]` in docker-compose.yml routes to `hermes gateway run` — the documented Docker daemon mode that auto-engages s6 supervision with auto-restart on crash. The "interactive-only by design" framing was wrong; the image is multi-mode and Epic 5 used the wrong mode. See [docs/external/hermes-agent/RECONCILIATION-NOTES.md](../../docs/external/hermes-agent/RECONCILIATION-NOTES.md) §2.3 and the Story 6-0 walk record in `epic-6-run-flags.md`.

**Original finding follows for audit trail:**


After Finding 1 was fixed and Hermes initialized cleanly, the container printed its splash screen ("Hermes Agent v0.15.1 ... 26 tools · 86 skills ... Welcome to Hermes Agent! Type your message or /help for commands.") and then exited with `Warning: Input is not a terminal (fd=0). Goodbye! ⚕`.

The `nousresearch/hermes-agent:latest` image's default entrypoint runs the interactive TUI (`hermes`), which exits cleanly on detached stdin. It is NOT designed as a long-running Discord-listener daemon under docker-compose detach.

This invalidates Story 5-4's core architectural assumption.

#### Finding 4 — `command:` override is swallowed by s6 supervisor — **RESOLVED 2026-06-02 (Story 6-0)**

**Resolution:** the framing was wrong. Docker-level `command:` is NOT swallowed; it's routed through `main-wrapper.sh` (the image's CMD entrypoint), which dispatches non-executable first args as `hermes` subcommands. Epic 5 tried `command: ["hermes", "gateway", "start"]` — `start` is the systemd/launchd subcommand, not Docker. The correct subcommand is `hermes gateway run` (or simply `command: ["gateway", "run"]` because the wrapper prefixes `hermes`). Per `hermes gateway run --help`: *"Inside the s6-overlay Docker image, normally `gateway run` is automatically redirected to the supervised s6 service (so the gateway gets auto-restart on crash)."* See [docs/external/hermes-agent/RECONCILIATION-NOTES.md](../../docs/external/hermes-agent/RECONCILIATION-NOTES.md) §2.2 and §2.3.

**Original finding follows for audit trail:**


Per the upstream README ([github.com/NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)), `hermes gateway start` is the long-running messaging daemon (Discord, Telegram, etc.). The dev pass attempted to override the container `command:` to `["hermes", "gateway", "start"]` to redirect to the daemon entrypoint.

The override had no effect. The image is supervised by s6-overlay; the managed service `main-hermes` runs Hermes via the s6 service definition (under `/etc/services.d/main-hermes/run` or similar), and docker-level `command:` overrides do not reach it. After applying the override and rebuilding, Hermes restart-loops with no error output — s6 starts `main-hermes`, the underlying process exits (presumably the TUI hitting detached stdin again), s6 brings the container down, the container restarts, the loop repeats.

**Action taken:** the `command: ["hermes", "gateway", "start"]` override was reverted from `docker-compose.yml` and the corresponding test (`test_compose_mailbot_hermes_runs_gateway_not_tui`) was removed. Leaving the no-op override in the repo would be misleading. The docker-compose.yml now carries an explicit comment documenting the architectural mismatch and the Epic 6 carry-forward.

#### Finding 5 — `hermes-config/config.yaml` schema is fabricated — **RESOLVED 2026-06-02 (Story 6-0)**

**Resolution:** `hermes-config/config.yaml` rewritten against the documented Hermes schema. Top-level keys are now `model`, `auxiliary`, `mcp_servers`, `discord`, `streaming`, `group_sessions_per_user` (real schema), replacing the invented `provider`, `auxiliary` (kept by coincidence — same field name but no headers), `fallback_providers`, `gateway`, `mcp_clients`. The `scripts/check_hermes_config.py` verifier was also rewritten to assert the new shape. See [docs/external/hermes-agent/RECONCILIATION-NOTES.md](../../docs/external/hermes-agent/RECONCILIATION-NOTES.md) §3 (divergence table) and §5 (rewrite action plan).

Two architectural side-effects of the corrective:

1. **Slash commands move from config-YAML to Hermes skills** — real Hermes auto-registers installed skill bundles as Discord application commands. The Story 5-6 8-command surface (cost / pause / resume / cancel / mute / label / budget / confirm) needs a follow-up story that ports the registry to `hermes-config/skills/mailbot/` as a Hermes-loadable skill bundle. Filed as RECONCILIATION-NOTES §6 item 1.
2. **NFR-OPS-6 fallback chain moves from config-YAML to CLI** — real Hermes manages fallback chains via `hermes fallback add ...` CLI, not file-driven. Operator setup: at first deploy, exec into mailbot-hermes and run `hermes fallback add anthropic claude-opus-4-7`. Captured for Story 6-7's setup_vps.sh runbook (RECONCILIATION-NOTES §6 item 3).

**Original finding follows for audit trail:**


The config file Story 5-4 shipped at `hermes-config/config.yaml` (provider / auxiliary / fallback_providers / gateway.discord.slash_commands / mcp_clients blocks) was the dev pass's invention. Story 5-4 Dev Notes explicitly hedged this as "verify against the image; if Hermes's actual config parser uses a different schema, the dev pass MUST verify... if unverifiable without running the image, document the assumed schema."

The hedge was honest, the schema was wrong. Hermes's actual config schema lives at [hermes-agent.nousresearch.com/docs/user-guide/configuration](https://hermes-agent.nousresearch.com/docs/user-guide/configuration) and [hermes-agent.nousresearch.com/docs/user-guide/messaging](https://hermes-agent.nousresearch.com/docs/user-guide/messaging) — neither was consulted during Story 5-4 authoring. The image's slash-command registration is likely runtime-managed (`hermes gateway` slash registry), not config-file-driven; `mcp_clients` is a real feature but the field name and shape are unverified; `provider.base_url` is plausibly close but unverified.

The shipped config is internally consistent and parseable as YAML, but its runtime contract with Hermes is hallucinated. Stories 5-5 (persona files) and 5-6 (slash dispatcher) ride on Hermes consuming this config; until F5 is resolved their runtime side is unverified.

### Decision (Adam-decided, Phase 3.5 walk close): Option C — accept and document

Three options were considered:
- **(A)** Keep probing the s6 service definition + env vars to find Hermes's daemon-mode entry point.
- **(B)** Install Hermes natively per the README's PowerShell one-liner, run `hermes gateway setup` interactively to learn the actual config schema, then port that config back. Forget the Docker image for now.
- **(C)** Accept the architectural finding, document the Hermes-side runtime as carry-forward, close Epic 5 at the mailbot-api boundary which IS healthy and tested.

Adam picked **(C)**. This is the honest scope. The mailbot-api side (verbs, MCP server with 16 tools, prompts, redactor, reference-resolution orchestrator, draft-reply capstone orchestrator) is real and tested against the documented contracts. The Hermes-side runtime (image deploy shape, config schema, slash-command registration, persona file consumption) needs a separate investigation that is out of scope for autonomous-epic-run's loop.

### Net Phase 3.5 verdict

**PASS at the mailbot-api boundary. The five Hermes-side runtime findings (F1 fixed, F2 fixed, F3 + F4 + F5 documented as carry-forward) are explicit Epic 6 work items.**

The mailbot-api stack is healthy and exercised end-to-end. Specifically — and these are the load-bearing claims for Epic 5's actual deliverables:

- MCP server `/mcp` is mounted, serving all 16 tools, integration-tested by Story 5-2 and Story 5-6 round-trip tests, and reachable on the live container at `http://localhost:8000/mcp`.
- Outlook sync is working against the real Microsoft Graph tenant — the live log shows real OAuth token rotation + a real delta sync that touched 13 messages.
- Sensitivity routing is intact: confidential refuses without Router dispatch, sensitive requires the task_type-bound token, normal proceeds.
- The Story 5-9 capstone orchestrator dispatches the right Router call sequence including the F1 task_type-binding fix (verified live with a consume-aware Router mock).
- The redactor catches every documented credential shape including the CR-3 Bearer `==` padding regression.

The Hermes side is what needs a follow-up epic.

---

## Aggregated `[deferred:*]` items

- **5-4 AC-7** — `hermes-config/config.yaml` boundary checker extension; deferred per AC's explicit deferral clause. Filed as follow-up if a Python consumer appears.
- **5-4 Phase 3.5 F3/F4/F5** — Hermes deploy shape + config schema (see Phase 3.5 walk record above). **Carry-forward to Epic 6.**
- **5-6 Defer 1** — TOCTOU on `mute_category` upsert. Single-user system; low risk.
- **5-6 Defer 2** — Discord choices schema (subsumed by 5-4 F5 carry-forward).
- **5-6 Defer 3** — authorization gate on `pause_router` / `resume_router` / `reset_degraded_mode` at MCP layer. Dispatcher-side per Rule P.
- **5-7 Defer** — SSH lazy-scan on unterminated key block on very large inputs. No exponential backtracking; fix requires max-input-size policy.
- **5-8 Defer** — single-turn recent_context duplication. Per-spec per Story 5-3 USER_TEMPLATE design.
- **5-9 F5** — story AC-1 state Literal omits `"send_proposed"`. Editorial; code's dataclass Literal is authoritative.

---

## UX Advisory

**Step 3.1 N/A** — project has no graphical frontend per PORTING.md. The equivalent quality gate IS Phase 3.5 walk above. Section B uncovered the Hermes-side runtime gap; documented as Epic 6 carry-forward.

---

## Self-grading scorecard (Step 3.2)

| Item | Verdict | Notes |
| --- | --- | --- |
| A1 — UI scope check passed for every story | ☑ | UI-gate N/A per PORTING.md; Discord-rendered text is the UI surface. File-level structural verification PASS; runtime verification gated on Epic 6 carry-forward. |
| A2 — end-of-epic dev-env verification ran (or N/A) | ☑ | Docker stack brought up; mailbot-api healthy; Hermes architectural mismatch documented. |
| A4 — `<flags-file>` exists with all `[deferred:*]` aggregated | ☑ | This file. |
| A5 — ≥ 70% applied rate on CR findings | ☑ | **100%** (38/38). |
| A7 — UX advisory invoked or N/A | ☑ (N/A) | No graphical frontend. |
| B1 — File-List-vs-git gate passed cleanly for every story | ☑ | Selective staging at every Step 2.6; never `git add -A`. |
| B2 — Phase 3.5 manual-verification gate | ☑ (with carry-forward) | Mailbot-api boundary PASS; Hermes runtime documented as Epic 6 carry-forward per Adam-decided Option C. |

**Net:** 7/7 ☑ at the mailbot-api boundary; Hermes-side runtime is honestly accounted as Epic 6 work.

---

## Recommendations for the next retrospective

(The retrospective is **always interactive** — Adam runs it manually with the SM agent in a separate session. These are the autonomous run's suggested talking points.)

1. **The Hermes runtime mismatch (F3 / F4 / F5) is the single most important retro item.** The dev pass invented a config schema without consulting Hermes's actual documentation. The hedge in Story 5-4 Dev Notes ("verify against the image") was honest — but autonomous-epic-run treated it as a sufficient excuse to ship the speculation. It wasn't. Architecture decision AR-DEPLOY-1 (`nousresearch/hermes-agent:latest`) was made on the assumption that the image is a daemon; the image is actually built for interactive use. This is the kind of failure mode autonomous-epic-run is structurally vulnerable to — it has no mechanism to consult external documentation, so it speculates and Phase 3.5 catches the speculation. Worth a process-level discussion: do we need a "real docs consulted" gate before shipping a container-config story?

2. **Story 5-9 F1 deserves its own retro section.** The token-task_type-binding bug would have broken every sensitive-email draft in production. The orchestrator's CR-driven fix (don't propagate the token to non-sensitive Router calls) is correct, but the failure mode — Story 4-7's task_type-binding wasn't surfaced in the orchestrator's calling contract until the CR caught it — is worth a process-level discussion. Should new Router callers see a token-propagation cheat-sheet?

3. **MANDATORY-CR cadence (Adam-decided Epic 4 retro action #1, option A) held perfectly.** 5 of 8 stories triggered MANDATORY-CR; 0 were silently skipped. The §5.12 binary verdict made the cadence decision mechanical. No retroactive-CR debt this epic.

4. **CR catches in this epic that would have shipped bugs to production:**
   - 5-3 CR-1: `tone_signals_used` required-field would have raised ValidationError on first-contact drafts.
   - 5-6 CR-1: `cost_breakdown` MCP wrapper missing `period` default would have failed `/cost` with no arg.
   - 5-7 CR-3: Bearer regex `\b` truncating base64 `==` padding — credential fragments leaking into "redacted" output.
   - 5-8 CR-3: Null projection fields rendering as `from=None` in LLM context.
   - 5-9 F1: token task_type-binding mismatch breaking sensitive-email drafts.

5. **Phase 3.5 was walked together (agent + Adam).** Agent walked offline + DB-real surrogates first; Adam joined for live operator-only checkpoints. The collaboration shape works for this kind of integration boundary — agent can probe a lot but can't reach Discord/Outlook/Anthropic from inside the session, and can't access external documentation. Worth keeping for future epics.

6. **Permission-prompt count: zero observed.**

---

## Permission-prompt summary

No permission log configured on the target. Zero prompts observed during the run.
