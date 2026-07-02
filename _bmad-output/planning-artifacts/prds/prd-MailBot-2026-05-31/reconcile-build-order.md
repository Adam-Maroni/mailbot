---
title: MailBot PRD — Build-Order Reconciliation
status: review
created: 2026-05-31
source: _bmad-output/brainstorming/phase-4-build-order.md
targets:
  - _bmad-output/planning-artifacts/prds/prd-MailBot-2026-05-31/prd.md
  - _bmad-output/planning-artifacts/prds/prd-MailBot-2026-05-31/addendum.md
---

# MailBot PRD — Build-Order Reconciliation

## Header

This reconciliation compares the canonical **Phase-4 build-order checklist** against the produced PRD + addendum. The build-order is downstream of the PRD (PRD = WHAT, build-order = HOW), so this reconciliation deliberately **does not** flag implementation depth (T-shirt sizes, dep graphs, task IDs, Alembic-vs-create_all debates, repo skeleton choices, container Dockerfile contents, Makefile targets) as PRD gaps.

It does flag any **product-level capability**, **ship-criterion verification anchor**, or **deliberately-deferred item** in the build-order that has no PRD counterpart.

---

## Per-milestone capability coverage

### M1 — Foundation & scaffold

Build-order delivers: repo skeleton, `.env` discipline, Docker Compose stack, SQLite schema, Outlook Graph auth (read-only), sync layer with delta queries, write-back queue worker, structured logging, `mailbot` CLI.

| Build-order capability                                   | PRD coverage                          | Status |
| -------------------------------------------------------- | ------------------------------------- | ------ |
| 3-container Docker stack                                 | §6, A1 architecture diagram           | covered |
| SQLite schema with derived columns                       | FR-2.1 + addendum A1 data-flow        | covered |
| Outlook Graph delta sync (cron-pull, read-only)          | FR-1.1, FR-1.2                        | covered |
| Sync-state delta link persistence                        | FR-1.2                                | covered |
| Soft-delete preservation                                 | FR-1.3                                | covered |
| Idempotent re-runs                                       | FR-1.4                                | covered |
| Headless OAuth via refresh-token copy                    | FR-1.6                                | covered |
| Write-back action queue (`pending_actions`)              | FR-5.5                                | covered |
| Action types: mark_read, mark_unread, move_to_folder, archive, delete, send_reply | FR-5.1 tier ladder (named at the tier level, not by action type list) | partial — action-type roster is implicit |
| Retry with exponential backoff (3 retries → failed)      | not in PRD                            | **gap** (operational; arguably NFR territory) |
| Structured JSON logging                                  | FR-7.3                                | covered |
| `mailbot` CLI (status / logs / sync-now)                 | FR-7.1, FR-7.2                        | covered (sync-now command implicit) |
| Pre-commit hook against `.env` commits                   | NFR-SEC-1 (spirit), not by mechanism  | covered in spirit |

**Capability gaps at M1 product-level:** none critical. The retry-with-backoff policy on the write-back worker is a reliability behavior that arguably belongs as an NFR; currently the PRD covers `pending_actions` as a queue but does not name the retry contract.

---

### M2 — Router & local LLM

Build-order delivers: Ollama in compose with pre-pulled models, pricing table, `router_calls` write helper, prompt module registry, policy loader (with hot-reload), Ollama adapter, Router core with response-cache + single-retry chain, OpenAI-compatible `/v1/chat/completions`, loop detection + rate limits + admin pause/resume, embedding endpoint.

| Build-order capability                                                                | PRD coverage                       | Status |
| ------------------------------------------------------------------------------------- | ---------------------------------- | ------ |
| Three-tier model stack (Qwen / Haiku / Opus)                                          | FR-3.1                             | covered |
| `policy.yaml` as routing source-of-truth                                              | FR-3.3                             | covered |
| Pricing table per model                                                               | FR-3.9 (cost field) + addendum A3  | covered |
| `router_calls` audit log                                                              | FR-3.9                             | covered |
| Prompt module registry with versions                                                  | FR-3.3 (prompt_version), addendum A3 | covered |
| Policy loader validates references + hot-reload                                       | not in PRD                          | low-priority gap (operational ergonomics) |
| Ollama adapter with JSON mode                                                         | FR-3.1                             | covered |
| Router single-retry on parse fail                                                     | FR-3.4 ("single retry with stricter prompt") | covered |
| Response cache                                                                        | FR-3.7                             | covered |
| OpenAI-compatible `/v1/chat/completions`                                              | §6 (Router as single source), addendum A1 endpoint list | covered |
| `MAILBOT_ROUTER_KEY` Bearer auth to Router                                            | NFR-SEC family (implied), addendum A1 | covered in spirit |
| Loop detection (prompt-hash repeat > 10 in 5 min)                                     | FR-3.8                             | covered |
| Per-lane rate limits (chat 60/hr, ingest 300/hr)                                      | FR-3.5                             | covered |
| Admin pause/resume kill-switch                                                        | FR-3.8 + FR-7.2 (`mailbot pause/resume`) | covered |
| Embedding endpoint                                                                    | FR-2.1 (embedding as derived column), addendum A1 endpoint list | covered |

**Capability gaps at M2 product-level:** none critical. Policy hot-reload is a "should" in the build-order; absence from the PRD is acceptable.

---

### M3 — Anthropic tier + budget + cache + sensitivity

Build-order delivers: Anthropic adapter with ephemeral cache marking, escalation logic with circuit-breaker, 4-layer budget enforcement, sensitivity classifier + override-pattern config, sensitivity-aware routing with override mechanism, response cache + cache warmer, ingest pipeline orchestrator, verb library skeleton.

| Build-order capability                                                                                            | PRD coverage                  | Status |
| ----------------------------------------------------------------------------------------------------------------- | ----------------------------- | ------ |
| Anthropic SDK adapter, ephemeral cache marking                                                                    | FR-3.6                        | covered |
| API key only in `mailbot-api` process                                                                             | NFR-SEC-2                     | covered |
| Escalation logic (parse-fail → next tier, max 20/hr)                                                              | FR-3.4 + FR-3.5 (rate limits) | covered |
| Layer 1 budget — `max_tokens_out` per call                                                                        | FR-6.1                        | covered |
| Layer 2 budget — daily soft warning $2                                                                            | FR-6.2                        | covered |
| Layer 3 budget — monthly hard cap $30 + degraded mode                                                             | FR-6.3                        | covered |
| Layer 4 budget — per-call refusal at $0.20                                                                        | FR-6.4                        | covered |
| Hourly anomaly detection                                                                                          | FR-6.5                        | covered (build-order is silent on this; PRD adds it — bonus) |
| Sensitivity classifier (Qwen-only, ingest-time)                                                                   | FR-2.3, FR-2.5, NFR-PRIV-1    | covered |
| `sensitivity_patterns.yaml` regex + sender-domain forcing                                                          | NFR-PRIV-3                    | covered |
| Sensitivity-aware routing — `sensitive`/`confidential` overrides policy to Qwen                                    | FR-2.5, NFR-PRIV-2            | covered |
| **Sensitivity override mechanism — header `X-MailBot-Sensitive-Override: yes` (M3) → chat token (M5)**             | NFR-PRIV-2 names per-session confirmation; mechanism not described | **partial gap** — PRD names the policy ("API allowed only with `force_model` + per-session chat confirmation") but doesn't anchor the override mechanism as an FR |
| `confidential` is API-blocked, period                                                                              | NFR-PRIV-2                    | covered |
| Response cache TTL configurable per task                                                                          | FR-3.7                        | covered |
| Cache warmer pings every 4 min                                                                                    | FR-3.6                        | covered |
| Ingest pipeline ordering (sensitivity → coarse → fine → summary → importance → action → embedding)                 | FR-2.3                        | covered |
| Idempotency key `sha256(body)+prompt_v+model+task`                                                                | FR-2.2                        | covered |
| Backpressure: queue > 500 → 100-batch + pauses                                                                    | FR-2.4                        | covered |
| Verb library: `find_emails`, `hydrate_email`, `get_thread`, `list_unread`, `count_emails`, `propose_action`, `apply_action`, `get_sender_summary` | Addendum A5                    | covered |
| Hydration rate limit 5/session                                                                                    | Addendum A5                   | covered |

**Capability gaps at M3 product-level:** the sensitivity-override mechanism (how the per-session confirmation token is presented) is named at the policy level but not as a concrete FR. Build-order M3.5 makes this a hard requirement; PRD treats it as a contract without naming the user-facing handshake.

---

### M4 — Eval system & first calibration

Build-order delivers: eval corpus (~100 hand-labeled), scoring rubrics with anchors, benchmark runner with cost confirmation, scorer (objective + subjective with Mode A manual / Mode B auto-judge), report generator with calibration suggestions, first calibration of policy-v0 → policy-v1.

| Build-order capability                                                       | PRD coverage           | Status |
| ---------------------------------------------------------------------------- | ---------------------- | ------ |
| Eval corpus v1 (~100 hand-labeled, frozen)                                   | FR-8.1                 | covered |
| Distribution mix specified (10 transactional, 10 newsletter, 20 personal, ...) | FR-8.1 mentions 8 task families | covered (less prescriptive about exact counts; acceptable) |
| Scoring rubrics + 20 anchor examples                                         | FR-8.3                 | covered |
| Benchmark runner with `force_model` and resumability                          | FR-8.2                 | covered |
| Cost confirmation prompt at > $5                                              | FR-8.2                 | covered |
| `benchmark_runs` table                                                       | FR-8.2 (table named)   | covered |
| Scorer Mode A (manual) + Mode B (auto-judge with calibration)                | FR-8.3                 | covered |
| Report generator with Pareto frontier + calibration suggestions               | FR-8.4                 | covered |
| First calibration → policy-v1, historical snapshot in `evals/policy-history/` | §7.3 (continuous-improvement criteria mentions v0→v1→v2+) | covered |

**Capability gaps at M4 product-level:** none.

---

### M5 — Hermes integration (MVP ship line)

Build-order delivers: MCP server with verbs as tools, Hermes container + config (Router as primary provider, fallback safety net, auxiliary tasks), MCP wiring, SOUL.md persona, AGENTS.md operational rules, skill description, Discord gateway, three cron jobs (sync, ingest, daily digest), drift + sampling crons, `pending_send` cooling-off + 20/day cap, slash commands.

| Build-order capability                                                            | PRD coverage                      | Status |
| --------------------------------------------------------------------------------- | --------------------------------- | ------ |
| MCP server exposing verbs as tools                                                | Addendum A4 (MCP), A5             | covered |
| Hermes Router-as-primary-provider config                                          | §6, addendum A4                   | covered |
| Hermes `fallback_providers` safety net                                            | NFR-OPS-6                         | covered |
| Hermes auxiliary tasks (compression, title_generation) routed via Router          | Addendum A4 (`context_from`, "context compression — built-in"), but not explicitly that AUX tasks flow through MailBot's Router | **partial gap** — Rule Ω discipline of routing AUX through MailBot Router is in addendum-only narrative; not pinned as FR |
| SOUL.md persona                                                                    | NFR-PERSONA-1, NFR-PERSONA-2      | covered |
| AGENTS.md operational rules (J/N/P/R as behavior)                                 | NFR-PERSONA-3                     | covered |
| Hermes skill description (`SKILL.md`)                                              | Addendum A1 (skills/mailbot/SKILL.md mentioned in volume layout) | covered in spirit, not as FR |
| Discord gateway, private bot in shared server                                      | FR-4.1                            | covered |
| Cron: Outlook sync every 4m (`no_agent=True`, `wakeAgent` suppression)             | FR-1.1 (sync cadence), addendum A4 (wakeAgent: false) | covered |
| Cron: ingest pipeline every 5m, batched at 100                                    | FR-2.4, NFR-PERF-4                | covered |
| Cron: daily digest at 08:00                                                       | FR-7.7                            | covered |
| **Daily digest content: unread grouped by importance + Tier 2 awaiting approval** | FR-7.7 specifies content          | covered |
| Cron: weekly drift report (Sunday 09:00, KL divergence)                            | FR-8.6                            | covered |
| Cron: weekly sampling (Sunday 09:30, 5 random calls)                              | FR-8.5                            | covered |
| Sampled answers append to `evals/email_corpus_v2.jsonl`                            | FR-8.5                            | covered |
| `pending_send` cooling-off 60s                                                    | FR-5.3                            | covered |
| 20/day send cap                                                                    | FR-5.4                            | covered |
| `/cancel <action_id>` during cool-off                                              | FR-4.5, FR-5.3                    | covered |
| **`/pause` slash command**                                                         | FR-4.5, FR-3.8, FR-7.2            | covered |
| **`/resume` slash command**                                                        | FR-4.5                            | covered |
| **`/cost` slash command**                                                          | FR-4.5, FR-6.7                    | covered |
| **`/cancel <action_id>` slash command**                                            | FR-4.5, FR-5.3                    | covered |
| **`/mute <category>` slash command**                                               | FR-4.5, FR-7.5                    | covered |
| **`/label <recent>` slash command**                                                | FR-4.5                            | covered |

**Capability gaps at M5 product-level:** the routing-discipline rule that **Hermes auxiliary tasks (compression, title_generation) flow through MailBot's Router** is described as a Rule Ω commitment in the build-order (M5.3 config example) and mentioned in addendum A4, but is not pinned as an FR in the PRD. Without it, a future change could quietly bypass cost discipline for aux traffic. The slash commands are well-covered.

---

### M6 — VPS deployment

Build-order delivers: `setup_vps.sh`, `deploy.sh`, `backup.sh` with retention, `mailbot status`, notification discipline polish (all 4 tiers + quiet hours + self-monitoring), headless Outlook OAuth, first production deploy, iteration backlog.

| Build-order capability                                                          | PRD coverage                       | Status |
| ------------------------------------------------------------------------------- | ---------------------------------- | ------ |
| One-time VPS bootstrap (`setup_vps.sh`)                                          | NFR-OPS-1, NFR-OPS-2 (deploy story); bootstrap not an FR | implementation detail, acceptable |
| `make deploy` end-to-end with rolling restart of mailbot-api only                | NFR-OPS-2                          | covered |
| Health check + log tail on deploy                                                | NFR-OPS-4                          | covered |
| **Nightly backups: SQLite `.backup` + config tarball + optional B2 rsync**       | NFR-OPS-5                          | covered |
| **Backup retention: 14 daily + 8 weekly**                                        | NFR-OPS-5 ("Retention 14 daily + 8 weekly") | covered |
| Backups exclude `.env`                                                           | NFR-SEC-6, NFR-OPS-5               | covered |
| `restore.sh` works against fresh DB                                              | not in PRD as FR                   | low-priority gap (operational; arguably belongs in runbook, not PRD) |
| `mailbot status` returns full picture in 10s                                     | FR-7.1                             | covered |
| Four notification tiers (urgent / digest / pull-only / silent)                   | FR-7.4                             | covered |
| Quiet hours 22:00–08:00                                                          | FR-7.5                             | covered |
| Self-monitoring: response rate < 30% for a week → self-reflection message        | FR-7.5                             | covered |
| Trust-signal opt-out                                                             | FR-7.6                             | covered (PRD-introduced refinement) |
| Headless OAuth on VPS via refresh-token copy                                     | FR-1.6                             | covered |
| First production deploy + 1-week unattended run                                  | §7.2 launch criterion              | covered |
| Iteration backlog (Honcho, cascading routing, shadow-mode, draft-edit telemetry) | OQ-5, OQ-6 + FR-8.7                | covered |

**Capability gaps at M6 product-level:** none critical. `restore.sh` is operational detail.

---

## Ship-criteria coverage (M1–M6 mapped to PRD success criteria)

| Milestone | Build-order ship criterion                                                                                                | PRD success-criterion anchor                                                |
| --------- | ------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| M1        | `docker compose up` clean; sync populates SQL with real emails; `mailbot status` reports count                            | §7.1 (implicit foundation); FR-1.1..6; FR-7.1                              |
| M2        | `/v1/chat/completions` returns a Qwen response logged to `router_calls`; loop detection blocks abuse                      | FR-3.1, FR-3.5, FR-3.8, FR-3.9                                              |
| M3        | `policy.yaml` switches task between tiers; budget gate fires; sensitivity column populated                                | FR-3.3, FR-6.3, FR-2.3, FR-2.5                                              |
| M4        | Benchmark report exists; `policy.yaml` edited based on real data with citable Pareto                                       | FR-8.1..4, §7.3                                                             |
| M5 (MVP)  | "Discord 10pm: show me unread → reply <5s with verb calls"; draft reply via Opus with cooling-off + cancel; 8am digest; sensitivity routing works; 24h test holds | §7.1 MVP scope (mirrors verbatim — FR-4.2, FR-4.4, FR-5.3, FR-7.7, NFR-PRIV-2) |
| M6 (launch) | Production on Hostinger, 7-day unattended; budget < $30; no unauthorized sends/deletes; no sensitivity leakage             | §7.2 launch criterion (mirrors verbatim — §1.3 six trusts)                  |

**Verdict on ship-criteria pattern:** the build-order's "concrete verifiable observable" pattern (every milestone has a "Verify:" anchor at task level and a milestone-level ship criterion) is fully reflected in the PRD's §7.1 / §7.2 / §1.3 trust decomposition. The PRD's "north-star metric" (§1.3) IS the M6 ship criterion translated to product language. The "what success looks like at the end" final section of the build-order maps cleanly to §1.3 six-trust list + §7.2 launch criterion — its essence is preserved.

---

## "Deliberately deferred" cross-check

Build-order's deferred list (lines 770–786) vs. PRD §1.5:

| Build-order deferred item                                       | PRD §1.5 entry                                                  | Status |
| --------------------------------------------------------------- | --------------------------------------------------------------- | ------ |
| Multi-account support                                           | "Multi-account, multi-user, sharing"                            | covered |
| Calendar integration                                            | "Calendar integration as a separate signal stream"              | covered |
| Attachment handling beyond `has_attachments` boolean            | "Attachment handling beyond a `has_attachments` boolean"        | covered |
| Postgres                                                        | "Postgres (SQLite is the chosen system of record)"              | covered |
| Webhook-based sync                                              | "Webhook sync (cron-pull only — Rule D)"                        | covered |
| A web UI                                                        | "Web UI (Discord is the UI — Rule X)"                           | covered |
| Sharing MailBot with others                                     | folded into "Multi-account, multi-user, sharing"                | covered |
| OpenRouter routing                                              | "OpenRouter / multi-provider routing (Anthropic direct only)"   | covered |
| Voice / TTS                                                     | "Voice / TTS"                                                   | covered |
| Browser automation for unsubscribe                              | "Browser-automated unsubscribe"                                 | covered |
| Honcho memory                                                   | "Honcho-backed user model (Hermes default memory first; upgrade only if needed)" | covered |

**Deferred coverage:** 11 of 11 items represented. No gap.

---

## FR-level slash-command / mechanism gaps

Concrete gap audit against the slip-points flagged by the reconciliation rubric:

| Gap candidate                          | PRD location                                              | Status |
| -------------------------------------- | --------------------------------------------------------- | ------ |
| `/cost` slash command                  | FR-4.5 (list), FR-6.7 (semantics)                         | covered |
| `/pause` slash command                 | FR-4.5, FR-3.8 (effect), FR-7.2 (CLI parity)              | covered |
| `/resume` slash command                | FR-4.5                                                    | covered |
| `/cancel <action_id>` slash command    | FR-4.5, FR-5.3                                            | covered |
| `/mute <category>` slash command       | FR-4.5, FR-7.5                                            | covered |
| `/label <recent>` slash command        | FR-4.5                                                    | covered |
| M3.5 sensitivity override mechanism (per-session token / header) | NFR-PRIV-2 (policy named), but the user-facing handshake mechanism is not pinned as FR | **gap — high** |
| M6.3 backup retention policy (14 daily + 8 weekly, exclude `.env`) | NFR-OPS-5, NFR-SEC-6                                      | covered |
| M5.11 daily digest content (unread by importance + Tier 2 awaiting approval) | FR-7.7                                                    | covered |
| Hermes AUX tasks routed through MailBot Router (Rule Ω discipline) | Addendum A4 narrative only; not pinned as FR              | **gap — medium** |
| Write-back worker retry contract (3 retries + exponential backoff → `failed`) | Not explicitly stated                                     | **gap — low** |
| Policy hot-reload (`watchfiles`)       | Not in PRD                                                | acceptable (build-order tags this "optional but cheap"; non-essential) |
| `restore.sh` working against fresh DB  | Not in PRD                                                | acceptable (runbook detail, not PRD scope) |
| Action-type roster (mark_read, mark_unread, move_to_folder, archive, delete, send_reply) | FR-5.1 tiers named at category level, individual action types implicit | low-priority gap (could be enumerated for clarity, but tiering captures intent) |

---

## Severity-ordered gap list

### Critical (blocks MVP authoring or correctness)
- *(none)*

### High (PRD should add before final)
1. **Sensitivity override handshake mechanism is policy-named but FR-unpinned.** Build-order M3.5 makes the contract concrete: the M3 mechanism is `X-MailBot-Sensitive-Override: yes` header; the M5 mechanism is a per-session chat confirmation token. PRD NFR-PRIV-2 names the policy ("API allowed only with `force_model` + per-session chat confirmation") but does not anchor the mechanism as an FR. **Recommend:** add `FR-4.x` or `FR-5.x` for "session sensitivity override token" so the verb API contract is unambiguous, or strengthen NFR-PRIV-2 to specify the handshake surface.

### Medium (worth tightening, not blocking)
2. **Hermes auxiliary-task routing through MailBot Router is rule-driven discipline but not an FR.** Build-order M5.3 explicitly routes Hermes `compression`, `title_generation`, and other aux tasks through `mailbot-router` as a Rule Ω commitment. PRD addendum A4 mentions this in narrative form (`auxiliary.compression` row) but the PRD body has no FR enforcing it. **Recommend:** add to FR-3 family — "All Hermes auxiliary LLM tasks route through the MailBot Router (Rule Ω/X discipline)."
3. **Daily-digest source-of-truth.** PRD FR-7.7 says "generated from pre-computed columns (Rule A — no Opus synthesis, just templating)". Build-order M5.11 actually wires it as a Hermes cron *with agent* (uses `list_unread()` verb). Mild tension: PRD-as-written says templating-only; build-order treats it as agent-driven. **Recommend:** reconcile — either tighten PRD to "agent-orchestrated from cached projections, no Opus" or relax to allow Qwen/Haiku synthesis on cached fields.

### Low (nice to add, acceptable as-is)
4. **Write-back worker retry contract is unstated.** 3 retries + exponential backoff → `status='failed'` with error captured. Add as an NFR-OPS reliability bullet.
5. **Action-type roster not enumerated in FR-5.1.** Tiering by category is clear; spelling out the specific actions (mark_read / mark_unread / move_to_folder / archive / delete / send_reply / unsubscribe / move_to_junk) tied to tiers would harden the contract.
6. **Policy hot-reload not mentioned.** Optional in build-order; acceptable to omit.
7. **`restore.sh` not named.** Runbook detail; acceptable to omit from PRD.

---

## Verdict

The PRD covers **virtually all product-level capabilities, ship criteria, and deferred items** named in the build-order. The two real gaps worth addressing are:

- **(high)** The sensitivity-override **mechanism** — policy is named but the FR-level surface contract (header vs. chat token) is not pinned.
- **(medium)** **Hermes aux-task routing discipline** — Rule Ω commitment lives in narrative addendum, not as a pinned FR.

Everything else is either covered, captured in addendum-with-appropriate-pointer, or correctly omitted as implementation depth. The "what success looks like at the end" essence is fully preserved in §1.3 (six trusts) and §7.2 (launch criterion).

**Overall verdict: acceptable** — with two targeted FR additions, the PRD reaches **complete**.
