---
title: MailBot — Product Requirements Document
status: final
created: 2026-05-31
updated: 2026-05-31
author: Adam (facilitated by John, BMad PM)
sources:
  - _bmad-output/brainstorming/brainstorming-session-2026-05-31-1430.md
  - _bmad-output/brainstorming/policy-v0.yaml
  - _bmad-output/brainstorming/phase-4-build-order.md
---

# MailBot — Product Requirements Document

## 1. Vision & North-Star

### 1.1 What MailBot is

**MailBot is a personal mailbox defender.** It's a single-user agentic system that filters, classifies, and proposes actions on Adam's Outlook inbox via a Discord chat interface, runs continuously on a small VPS, and operates under a hard $30/month API budget. It is not an inbox assistant — it is a defender of attention.

### 1.2 Who it's for

**One user: Adam.** Not "single-user first." Not "scoped for solo with a path to teams." Single-user, period. Every design choice that would survive scaling assumes Adam is the only authenticated identity, the only memory subject, the only authorization grantor, and the only consumer of notifications.

### 1.3 North-star metric

> **"I trust it enough to leave it running unattended for a week."**

Operational decomposition:

- **Cost trust:** monthly API spend ≤ $30 with no manual intervention
- **Data trust:** no email destroyed without explicit consent
- **Send trust:** no email sent on Adam's behalf without explicit consent
- **Privacy trust:** no sensitive/confidential content leaves the VPS without explicit per-session consent
- **Signal trust:** notifications stay sparse and meaningful; user-response rate ≥ 30% week-over-week
- **Availability trust:** sync runs continuously; recoverable failure modes; ≤ 1 hour stale before user is notified

If any of the six trusts breaks during a 7-day unattended run, MVP has not been reached.

### 1.4 Counter-metrics (named explicitly)

The metrics above are positive; these are the things whose *absence* defines success:

- **Cost overrun rate:** months where spend exceeded $30 (target: 0)
- **Unauthorized-action incidents:** sends or deletes performed without a matching authorization grant (target: 0, by construction not by behavior)
- **Sensitivity leakage incidents:** emails classified `sensitive` or `confidential` whose body reached the Anthropic API without per-session confirmation (target: 0)
- **Silent failure window:** longest period sync was broken before Adam was notified (target: ≤ 1 hour)
- **Notification fatigue:** weeks where Adam's response rate to MailBot drops below 30% (target: 0; self-corrective mechanism specified in FR-7.5)

### 1.5 Out of scope (deferred deliberately)

- Multi-account, multi-user, sharing
- Calendar integration as a separate signal stream
- Attachment handling beyond a `has_attachments` boolean
- Postgres (SQLite is the chosen system of record)
- Webhook sync (cron-pull only — Rule D)
- Web UI (Discord is the UI — Rule X)
- OpenRouter / multi-provider routing (Anthropic direct only)
- Voice / TTS
- Browser-automated unsubscribe
- Honcho-backed user model (Hermes default memory first; upgrade only if needed)

---

## 2. Strategic Foundation — Rule Ω as Product Principle

This PRD is built around one product principle, lifted from the brainstorming session and elevated here:

> **Rule Ω — Cost Minimality.** Never use a distant LLM if the local one can do the task. Never use a high-grade distant LLM if a lower-grade one can do the task. Cost management is a first-class system property, on par with correctness.

### 2.1 Economic anchor

Rule Ω is not abstract. The economic shape of the three-tier stack drives it:

- **Qwen 3B (free, local)** is the dominant cost lever. Every task kept on Qwen is **pure savings** — zero marginal cost, no daily-cap erosion, no monthly-cap risk.
- **The 3B↔Opus capability gap is large.** There is no graceful cheap escalation between them — they sit at opposite ends of the cost-quality curve.
- **Claude Haiku 4.5 was deferred during the brainstorm and re-introduced into v1** (~1/30th Opus price) because the gap above was big enough that some tasks needed a measured middle tier.
- The combination — large gap, no native fallback, hard $30/month cap on a personal budget — means every task assignment in `policy.yaml` is a *budgetary decision*. Default-cheapest is not a preference; it is a survival rule for the budget envelope.

### 2.2 What this means for the product

Every functional area below is shaped by Rule Ω. Most user-facing features have a free local default, a measured-escalation path, and a budget-bounded ceiling. The PRD's success criteria, NFRs, and authorization model all reduce to "make Rule Ω safe to honor."

> *"Rule Ω is what gives the system its soul. Everything else flows from it."* — session principle, ratified 2026-05-31.

---

## 3. Capability Map

MailBot's capabilities are grouped into seven feature areas, each backed by a stable FR namespace:

| #  | Feature Area                  | Namespace | Lifeline                                                                            |
| -- | ----------------------------- | --------- | ----------------------------------------------------------------------------------- |
| F1 | Outlook Sync                  | FR-1.x    | The system has fresh, complete email data without polling Microsoft directly        |
| F2 | Ingest Pipeline               | FR-2.x    | Every email gets pre-computed derived fields once, cached forever (Rule A)          |
| F3 | Router & Tiered LLM           | FR-3.x    | All LLM calls flow through one cost-disciplined Router (Rule I)                     |
| F4 | Conversational Control        | FR-4.x    | Discord chat is the only UI for human interaction                                   |
| F5 | Authorized Actions            | FR-5.x    | The agent can never act outside Adam's permission grants (Rule P)                   |
| F6 | Cost Governance               | FR-6.x    | The system enforces a hard monthly budget at four layers (Rule N)                   |
| F7 | Observability & Trust         | FR-7.x    | Adam can see what MailBot is doing and stop it instantly                            |
| F8 | Eval & Calibration            | FR-8.x    | Routing decisions are backed by measured benchmarks, not intuition (Rule H)         |

Cross-cutting concerns (privacy/sensitivity, secrets, persona) appear as NFRs in §5, not as their own feature areas.

---

## 4. Functional Requirements

> **FR ID convention:** `FR-<area>.<n>`. IDs are stable — never renumber, only deprecate.

### 4.1 F1 — Outlook Sync (FR-1.x)

The system reads from Microsoft Graph on a cron schedule, never via webhooks, and never lets the agent touch Graph directly (Rules B, D).

- **FR-1.1 — Cron-pull sync.** A scheduled job runs every 4 minutes (aligned to Anthropic cache TTL — Rule M), fetches Graph delta since last sync, writes new/changed/deleted email rows to local SQLite.
- **FR-1.2 — Delta-only fetch.** The sync layer stores the Graph delta link in a `sync_state` row and requests only deltas. First-time sync of a large inbox may take 10–30 minutes; subsequent syncs are seconds.
- **FR-1.3 — Soft-delete preservation.** Deleted emails are marked `deleted_at` in SQL rather than hard-deleted. Original raw fields preserved for audit.
- **FR-1.4 — Idempotent re-runs.** Running sync twice with no inbox changes produces zero writes and zero LLM calls. Idempotency keyed on `(graph_id, change_marker)`.
- **FR-1.5 — Sync-health surfacing.** If sync fails to complete for > 1 hour, Adam receives an urgent Discord notification (Rule R). The condition is detectable by the `mailbot status` CLI inside 10 seconds.
- **FR-1.6 — Headless OAuth via refresh-token copy.** First-time auth happens once on the dev box; the refresh token is hand-copied into the VPS `.env`. Re-auth procedure is documented in `docs/auth-recovery.md` for the eventual token expiry. `[ASSUMPTION]` The 90-day refresh-window concern is mitigated by continuous sync activity; no monitoring requirement beyond FR-1.5.
- **FR-1.7 — `has_attachments` only at v1.** Attachment metadata (boolean + count) is stored; attachment bodies are not fetched. Full attachment policy is deferred (open question #27 in Phase 1).

### 4.2 F2 — Ingest Pipeline (FR-2.x)

Rule A in action: every piece of LLM-derived information about an email is computed once at ingest and written back to SQL. The runtime/chat-time agent **reads** derived fields; it does not recompute (Rule A is binding).

- **FR-2.1 — Derived-field columns are first-class.** Each derived signal lands in dedicated SQL columns: classification (coarse + fine), importance score, short summary, sensitivity, suggested action, embedding. Each carries `*_prompt_v`, `*_conf`, `*_model`, and `*_at` companion columns.
- **FR-2.2 — Idempotency on re-runs.** Pipeline keys derivations on `sha256(body) + prompt_version + model + task_type` (Rule K). Running the pipeline twice on the same email at the same prompt version is free.
- **FR-2.3 — Pipeline ordering is fixed.** Per email: `sensitivity_class → coarse_class → (fine_class if human) → summary_short → importance_scoring → action_extraction → embedding`. Sensitivity is **first** so downstream tasks know whether API is allowed (Rule Q). **Hard invariant:** no Router call for any other task on a given `email_id` is permitted until `emails.sensitivity_at IS NOT NULL`. The Router enforces this at the precondition layer, refusing with `RouterError(code="sensitivity_not_classified")` if violated.
- **FR-2.4 — Backpressure ceiling.** If unprocessed queue exceeds 500 emails, pipeline processes in 100-batch chunks with pauses to keep the interactive lane responsive (Rule K).
- **FR-2.5 — Sensitivity is local-only.** The sensitivity classifier never escapes Qwen 3B, regardless of policy. Hard-coded in Router enforcement (Rule Q).
- **FR-2.6 — Targeted re-derivation.** When a prompt version is bumped or a user-model refresh changes context, an opt-in batch can re-derive selected columns for affected rows. Off by default; explicit invocation from `mailbot` CLI.
- **FR-2.7 — Senders and threads upsert.** Each new email upserts its sender and thread rows. On first sender contact, a one-line `sender_reputation_summary` is generated by Qwen and cached forever (Rule A).

### 4.3 F3 — Router & Tiered LLM (FR-3.x)

The Router is the **single source of truth for every LLM call in the system** (Rule I). It owns cost discipline, escalation, caching, budget, and sensitivity enforcement.

- **FR-3.1 — Three-tier model stack at v1.**
  - **Free:** Qwen 2.5 3B Instruct (Q4_K_M) via Ollama, plus bge-small/nomic-embed for embeddings
  - **Cheap:** Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)
  - **Premium:** Claude Opus 4.7 (`claude-opus-4-7`)
  - Adding a fourth model is a single `policy.yaml` config change, not a refactor.
- **FR-3.2 — Single agent verb interface.** Hermes calls the Router exclusively through `ask_router(task_type, content, force_model=None, max_cost_usd=None) → RouterResult`. No direct Ollama or Anthropic calls from anywhere in the system, including the eval runner.
- **FR-3.3 — Static policy table with override.** `policy.yaml` is the source of truth: per-task `{model, prompt_version, escalate, max_tokens_out, lane, sensitivity}`. Per-call overrides are allowed but always logged with `model_chosen_reason="override"`.
- **FR-3.4 — Layered failure handling.** Call → timeout (30s local / 60s API) → schema validation → single retry with stricter prompt → escalate-to-next-tier (if `escalate=true`) → return `RouterResult(ok=False, error=RouterError(...))`. Errors are structured data with a stable code set: `schema_validation_failed`, `timeout`, `budget_exceeded`, `per_call_threshold_exceeded`, `provider_error`, `monthly_budget_exceeded`, `degraded_mode_blocked`, `loop_detected`, `sensitivity_blocks_api`.
- **FR-3.5 — Lane separation.** Router maintains `interactive` and `batch` lanes; interactive preempts batch. Per-lane rate limits enforced (chat 60/hr, ingest 300/hr, escalations 20/hr — Rule N).
- **FR-3.6 — Anthropic prompt caching is primary.** All API calls mark the SYSTEM block as `cache_control: ephemeral`. A cache warmer pings high-volume tasks every 4 minutes (aligned to 5-min TTL — Rule M). Per-task `cache_hit_rate` is tracked; regressions alert.
- **FR-3.7 — Response cache.** Identical `hash(prompt+model+temp)` calls return cached results. SQL-backed, TTL configurable per task in `policy.yaml`.
- **FR-3.8 — Anti-loop kill-switch.** Prompt-hash repeated > 10× in 5 min refuses with `loop_detected`. `/pause` chat command halts the Router until `/resume`.
- **FR-3.9 — Audit log.** Every call writes one `router_calls` row: `task_type`, `prompt_version`, `model_chosen`, `model_chosen_reason`, `tokens_in/out/cached_in`, `cost_usd_estimated`, `latency_ms`, `outcome`, `caller_verb`, `email_id`. This table is the ground truth for cost analysis, drift detection, and routing tuning.
- **FR-3.10 — Hermes auxiliary tasks route through the Router.** Hermes's own internal LLM work (context compression, title generation, and any other auxiliary tasks) is configured to call MailBot's `/v1/chat/completions` endpoint, not Anthropic directly. Rule Ω extends to Hermes's own work, not just MailBot verbs — the budget envelope and routing policy apply to *every* LLM call the system makes.

### 4.4 F4 — Conversational Control (FR-4.x)

Discord is the only human interface — chat-driven control of the inbox is the experience anchor.

- **FR-4.1 — Discord adapter as gateway.** Hermes's Discord adapter is bound to a private bot in a server Adam shares with MailBot. No web UI, no email replies to MailBot itself.
- **FR-4.2 — Conversational queries.** Adam can ask: "show me unread from today", "what's important this week", "anything from the lawyer", "summarize that thread" — and MailBot responds via Router-routed verb calls within the latency bound stated in NFR-PERF-1 (p95 ≤ 5s for verb-call + Qwen/Haiku queries; Opus-bound responses governed separately).
- **FR-4.3 — Reference resolution.** Pronouns and ellipsis ("that one", "the lawyer", "Marc's last email") resolve against recent context + memory. Acceptance bound is calibrated by F8: a dedicated reference-resolution slice (~20 items) is added to `email_corpus_v1.jsonl` at M4.1; the production threshold is **≥ 90% correct resolution** on that slice. Tasks failing the threshold trigger the PROMOTION HYPOTHESIS in `policy.yaml`.
- **FR-4.4 — Draft reply flow.** "Draft a reply to that" → Opus drafts → MailBot shows the draft → Adam edits or approves → cooling-off → send. The draft generation, tone mirroring, and multi-turn refinement are tier-1 product capabilities, not edge cases.
- **FR-4.5 — Slash commands.** `/cost`, `/pause`, `/resume`, `/cancel <action_id>`, `/mute <category>`, `/label <recent>`. These are explicit, terse, and bypass natural-language ambiguity.
- **FR-4.6 — Persona consistency.** MailBot speaks as a defender: conservative, quiet, asks before destructive actions. Persona is encoded in `SOUL.md` and consistent across all chat surfaces (DM, digest, alerts, slash-command replies).
- **FR-4.7 — Chat input redactor.** Adam's chat messages are scrubbed for token-shaped strings (JWTs, `sk-…`, hex blobs) before entering agent memory or being forwarded to API. Same redactor runs on memory exports.
- **FR-4.8 — `[ASSUMPTION]` Slash command parity in DM and channel.** Slash commands work identically whether sent via DM or in a shared server channel. To resolve at Finalize.

### 4.5 F5 — Authorized Actions (FR-5.x)

The agent **cannot** act outside Adam's permissions. This is enforced by the verb API, not by the agent's behavior (Rule P).

- **FR-5.1 — Four-tier authorization model.**
  - **Tier 0 (free):** read SQL, run LLM calls, generate drafts (unsent), send chat notifications, write derived fields.
  - **Tier 1 (auto-revertible, logged):** mark read/unread, add/remove local categories, move to single `MailBot-Triage` folder.
  - **Tier 2 (batch approval):** archive, mark junk, move to user folders, unsubscribe.
  - **Tier 3 (per-action confirmation):** delete anything, send any email, modify rules/filters, touch delegated accounts.
- **FR-5.2 — Tier-jumping by scoped grant.** Adam can grant authorization in chat: *"you may delete the 47 spam emails from Acme; valid for 1 hour."* Grant is cached against `(action_type, email_ids, expiry)`. After expiry, grant is invalid.
- **FR-5.3 — Cooling-off on sends.** Approved outbound emails sit in `pending_send` for 60 seconds (configurable) before leaving. `/cancel <action_id>` during the window kills the send.
- **FR-5.4 — Hard daily send cap.** MailBot sends at most 20 outbound emails per day regardless of authorization. Hijack-resistance.
- **FR-5.5 — Queued-intent write-back.** All actions enter `pending_actions` and are drained by a separate Python worker. The worker performs a **second** authorization check at drain time — refuses if no fresh grant. Benefits: retry, audit, dry-run, undo.
- **FR-5.6 — Tier enforcement is verb-API, not agent.** The agent cannot promote an action's tier — the verb that creates the pending action refuses tier upgrades. Authorization is a property of the verb call, not the agent prompt.
- **FR-5.7 — Sensitive-content API override handshake.** When the agent needs to escalate a `sensitive`-classified email to Anthropic (drafting a reply to a medical email, summarizing a legal thread), the user explicitly confirms in chat — *"yes, send this one to Opus"* — which mints a **per-session confirmation token** scoped to `(email_id, task_type)`. The token is consumed by a single Router call; subsequent calls require a fresh confirmation. The Router refuses sensitive-to-API calls without a valid token. `confidential` emails admit no such override.

### 4.6 F6 — Cost Governance (FR-6.x)

The system enforces its budget at four independent layers so a single failure can't blow the cap (Rule N).

- **FR-6.1 — Per-call output cap.** Every Router call enforces `max_tokens_out` from `policy.yaml`. Default 4000; task-overridable.
- **FR-6.2 — Daily soft warning.** When today's cumulative spend exceeds $2, MailBot sends a one-time chat warning. Does not block calls. Threshold is in `policy.yaml`.
- **FR-6.3 — Monthly hard cap.** When the month's cumulative spend exceeds $30, the system enters **degraded mode**: Opus calls demote to Haiku; Haiku demote to Qwen; `force_model="claude-opus-4-7"` requires explicit chat confirmation; one urgent notification fires once. Degraded mode persists until the next month rolls over OR Adam manually clears it via slash command. `[ASSUMPTION]` Manual override slash command for degraded mode is `/budget reset` — to confirm at Finalize.
- **FR-6.4 — Per-call refusal threshold.** Any call estimated at > $0.20 is refused with `per_call_threshold_exceeded` unless `force=true` is passed. Catches "agent stuffed the entire inbox into one prompt" bugs.
- **FR-6.5 — Hourly anomaly detection.** Hourly call volume baselined; significant deviations alert Adam in chat before a budget breach occurs. Acts before FR-6.2.
- **FR-6.6 — Default-cheapest with annotated escalation.** Every task in `policy.yaml` defaults to the cheapest tier (Qwen 3B). Each escalation to Haiku or Opus carries an inline `notes` justification *and* a "DEMOTION HYPOTHESIS" to be tested by F8 benchmarks. Every Opus assignment must cite a benchmark run.
- **FR-6.7 — `/cost` transparency.** Adam can query spend at any time: today's $, this month's $, this month's cap, per-task breakdown, per-model breakdown, cache hit rate. Data sourced from `router_calls`.

### 4.7 F7 — Observability & Trust (FR-7.x)

Adam can see what MailBot is doing and stop it instantly. Trust is built through visibility (Rule W).

- **FR-7.1 — `mailbot status` CLI.** SSH into VPS; `mailbot status` returns within 10 seconds: container health, last successful sync, unprocessed email count, pending actions awaiting auth, today's spend vs. cap, cache hit rate this week, last 5 errored `router_calls`.
- **FR-7.2 — `mailbot logs` and `mailbot pause/resume`.** Tail Docker logs; emergency stop from the VPS shell. `/pause` from chat does the same.
- **FR-7.3 — Structured JSON logging.** All services log structured JSON to stdout with timestamp, level, module, message, context. All errors carry sanitized stacks (no API keys, no Graph URLs with tokens — Rule F).
- **FR-7.4 — Notification tiers.** Every chat message from MailBot is one of: **urgent** (push immediately — Tier 3 auth, anomaly, kill-switch, budget breach, failed sync > 1h), **important** (batched into daily 8am digest — Tier 2 approvals, drift report, sampling requests), **informational** (pull-only via slash commands), **silent** (log-only — routine classifications, cache pings, sync events).
- **FR-7.5 — Anti-fatigue mechanisms.** Quiet hours 22:00–08:00 (no non-urgent messages); same-kind notifications firing 5+ times in an hour collapse to one; `/mute <category>` silences until `/unmute`; if Adam's response rate drops below 30% for a week, MailBot sends ONE self-reflection message ("I'm becoming noisy") then enters **urgent-only posture** — only the *urgent* notification tier (FR-7.4) is delivered until any slash command is issued by Adam, at which point normal notification tiers resume.
- **FR-7.6 — Trust-signal opt-out.** Adam can permanently mute the trust-signal self-reflection if desired (configurable in `policy.yaml`). `[ASSUMPTION]` Default is enabled.
- **FR-7.7 — Daily digest.** At 08:00 (Adam's timezone), MailBot generates a digest scheduled via Hermes cron-with-agent. The agent calls `list_unread()` and similar verbs to **read** pre-computed columns (Rule A — no body re-derivation; summaries come from the ingest-time `summary_short` field), then assembles the digest as light templating + light synthesis. Routing for the agent's own digest call is governed by `policy.yaml[daily_digest]` (Qwen 3B in v0). Contents: unread grouped by importance, pending Tier 2 batches awaiting approval, weekly drift/sampling artifacts when scheduled.

### 4.8 F8 — Eval & Calibration (FR-8.x)

Every routing decision is backed by measured data, not intuition (Rule H). The eval system is a **first-class deliverable**, not a nice-to-have.

- **FR-8.1 — Frozen, versioned eval corpus.** `evals/email_corpus_v1.jsonl` — ~100 hand-labeled real emails covering the 8 task families (transactional, newsletter, human-personal, human-professional, cold outreach, spam-like, notification, edge cases — calendar invites, password resets). Personally labeled by Adam, one-time effort ~3–5 hours.
- **FR-8.2 — Benchmark runner.** `benchmark/runner.py` executes every `(eval_item × task × model × prompt_version)` combo through the Router with `force_model`. Records full result in `benchmark_runs` table. Resumable; estimates cost upfront; asks confirmation if > $5.
- **FR-8.3 — Scorer (objective + subjective).** Classification → exact match → accuracy/precision/recall/confusion. Structured extraction → field-level match. Subjective (drafts, summaries) → 20 hand-anchored examples + strong-model auto-eval calibrated against anchors.
- **FR-8.4 — Report generator.** Per-task table of model × (accuracy, p95 latency, cost per 100 calls); 3B failure modes with examples; Pareto frontier per task; **calibration suggestions** flagging each row in `policy.yaml` as "DEMOTE valid / invalid / PROMOTE needed."
- **FR-8.5 — Continuous eval through production sampling.** Every Sunday: sample 5 random `router_calls` (low-confidence weighted), DM Adam in Discord with "did I get this right?" emoji-reaction prompts. Answers append to `evals/email_corpus_v2.jsonl`. Corpus grows weekly.
- **FR-8.6 — Drift detection.** Every Sunday: distribution of this week's `class_coarse` outputs compared to eval corpus distribution. KL divergence > threshold → drift alert in chat.
- **FR-8.7 — Shadow-mode rollout for subjective tasks.** New prompt versions for draft/summary tasks generate alongside production version (not used) for a configurable window; compared later. Catches silent quality regressions (Rule O).

---

## 5. Non-Functional Requirements

### 5.1 Privacy & Sensitivity

- **NFR-PRIV-0 — Privacy posture: VPS-local is the trust boundary.** The Qwen 3B process running on the Hostinger VPS is allowed to see every email category, including sensitive and confidential. The trust boundary is **the VPS itself** — what crosses to Anthropic is what Rule Q gates. This premise is load-bearing for the sensitivity-routing rules below; if it changes (e.g., shared hosting, untrusted infra), Rule Q's allowances must be re-evaluated.
- **NFR-PRIV-1 — Three-tier sensitivity model.** Every email is classified at ingest as `normal` / `sensitive` / `confidential` (FR-2.3, FR-2.5). When in doubt, default to `sensitive` (Rule Ω cautious bias).
- **NFR-PRIV-2 — Routing by sensitivity.**
  - `normal`: Qwen / Haiku / Opus all allowed. Full body indexed and logged.
  - `sensitive`: Qwen-only by default. API allowed only with `force_model` + per-session chat confirmation. Memory stores summary + IDs; full body purged after derivation. Logs hash content.
  - `confidential`: Qwen-only, no exception. Memory stores metadata only; body purged after derivation. Logs metadata only.
- **NFR-PRIV-3 — User-configurable sensitivity patterns.** Regex / sender-domain / keyword rules in `sensitivity_patterns.yaml` *force* `sensitive` or `confidential` regardless of classifier output (e.g., `*@bank.com` → always sensitive).
- **NFR-PRIV-4 — Chat-input redactor.** Token-shaped strings scrubbed from inputs (FR-4.7); same redactor applies to memory exports and trajectory dumps.

### 5.2 Secrets Management (Rule F)

- **NFR-SEC-1 — Secrets in `.env` only.** `chmod 600`, owned by service user. Never in source, prompts, skills, configs, memory.
- **NFR-SEC-2 — Anthropic API key isolated to Router process.** Hermes never has the key in its process memory. Only the `ask_strong_model` verb's process reads `os.environ["ANTHROPIC_API_KEY"]`.
- **NFR-SEC-3 — Agent has no filesystem path to secrets.** Tool-layer denylist on `.env`, `*.key`, `*.pem`, SSH dirs, the SQL DSN file — enforced outside the agent's control.
- **NFR-SEC-4 — Sanitized error returns.** Verbs sanitize all error messages and return values before they reach the agent. No raw stack traces, no URLs with tokens.
- **NFR-SEC-5 — `get_secret(name)` indirection.** Single function for all secret reads; swapping `.env` → vault (pass / age / Vault) later is a localized change.
- **NFR-SEC-6 — Backups exclude secrets.** Automated backups never include `.env`.

### 5.3 Reliability & Operations

- **NFR-OPS-1 — Dev-prod parity via containers.** Local dev and VPS prod run the same Docker images via `docker compose`. Only volume bind paths and `.env` values differ (Rule S).
- **NFR-OPS-2 — Single-command deploy.** `make deploy` does build → save → scp → load → rolling restart of `mailbot-api` only → health check → log tail. Hermes and Ollama containers updated separately via `docker compose pull` (Rule T).
- **NFR-OPS-3 — State survives containers.** All state on named volumes (`mailbot_db`, `mailbot_ollama`, `mailbot_hermes_data`, `mailbot_logs`). `docker compose down && up` is a non-event (Rule V).
- **NFR-OPS-4 — Health endpoints.** `mailbot-api` exposes `/health` and `/v1/health`. Deploy aborts on health check failure (Rule W).
- **NFR-OPS-5 — Nightly backups.** Host cron on VPS does SQLite `.backup`, tarballs config, optionally rsyncs to off-site B2. Retention 14 daily + 8 weekly. Backups exclude `.env`.
- **NFR-OPS-6 — Resilience via Hermes fallback.** Hermes `fallback_providers` configured with direct Anthropic Opus as a safety net if our Router is down. Bypasses cost discipline by design — emergency only (Rule X).

### 5.4 Performance

- **NFR-PERF-1 — Chat response p95 ≤ 5s** for typical queries (verb call + Qwen/Haiku response). Opus draft generation exempt (target p95 ≤ 15s, set by Anthropic latency).
- **NFR-PERF-2 — Sync cadence: 4 minutes.** Aligned to Anthropic 5-min cache TTL (Rule M). Inbox freshness floor is therefore ~4 min.
- **NFR-PERF-3 — Qwen 3B latency budget on 2-vCPU CPU-only.** Interactive tasks routed to Qwen must show p95 ≤ 5s on the VPS hardware; otherwise PROMOTION HYPOTHESIS to Haiku is validated by FR-8.2 benchmarks.
- **NFR-PERF-4 — Ingest throughput.** Pipeline processes 100 emails per batch, max 100 emails per 5-min ingest cron run, with backpressure if queue > 500 (FR-2.4).

### 5.5 Deployability & Hardware

- **NFR-HW-1 — Target: Hostinger KVM 2 (2 vCPU, 8 GB RAM, 100 GB NVMe, 8 TB bandwidth, no GPU).** Hardware upgrade declined; design must fit.
- **NFR-HW-2 — Local LLM RAM budget: 4.5–5.5 GB** after OS, SQL, Python services, Hermes. Determines single 3B model commitment.
- **NFR-HW-3 — No 7B fallback at v1.** Binary local-or-API design. Adding a middle model is `policy.yaml` change, not refactor.

### 5.6 Persona & Voice

- **NFR-PERSONA-1 — Defender, not assistant.** MailBot's voice is conservative, quiet, asks before destructive actions, shows reasoning when proposing actions. Anchored in `SOUL.md`.
- **NFR-PERSONA-2 — Behavioral anti-patterns.** Never send without per-message authorization; never delete without per-action authorization; never quote sensitive content outside chat; never produce noisy notifications.
- **NFR-PERSONA-3 — Operational rules in `AGENTS.md`.** How Rules J/N/P/R manifest as agent behavior (hydration discipline, tier-aware proposals, notification tiering, cost-aware verb choice).

---

## 6. Architecture Anchors (read-only here)

This PRD does not specify architecture in depth — those decisions are already made and live in the brainstorming session + addendum. This section names them so dependent documents (architecture, epics) can ground against them.

- **Local SQLite as the agent's only world** (Rule B). Agent never touches Graph directly.
- **Tailored Python verb API** (Rule C). Agent's data window is hand-crafted verbs with built-in cost ceilings, exposed via MCP.
- **Router as single source of truth for LLM calls** (Rule I). No direct provider calls anywhere.
- **Hermes-native integration** (Rule X). Discord, cron, memory, fallback_providers, prompt caching, context compression — all Hermes primitives. MailBot only builds the mailbox-specific intelligence layer.
- **3-container Docker stack:** `mailbot-hermes` (Discord gateway, cron, memory, agent) + `mailbot-api` (Router, verbs, MCP server, sync worker) + `ollama` (local model serving).

Full implementation detail in `addendum.md` and the Phase 4 build order.

---

## 7. Success Criteria & MVP Definition

### 7.1 MVP scope (end of Milestone 5 in build order)

MailBot is "MVP-reached" when, locally:

- A Discord message at 10pm — "show me unread from today" — yields a coherent response in < 5s, sourced from verb calls, with no notification fatigue.
- "Draft a reply to that one" invokes Opus, returns a draft, waits for explicit send confirmation, queues with 60s cooling-off, and is cancellable mid-window.
- The 8am daily digest arrives and contains the day's unread grouped by importance plus any Tier 2 pending batches.
- Sensitivity-classified emails route correctly (confidential bodies never reach Anthropic, sensitive ones gate on session confirmation).
- All seven trusts (§1.3) hold for a 24-hour test run.

### 7.2 Launch criterion (end of Milestone 6)

MailBot is "launched" when, on the Hostinger VPS, it runs unattended for 7 consecutive days with:

- Monthly API spend tracking ≤ $30 (proportional check at day 7)
- Zero unauthorized sends or deletes
- Zero sensitivity-leakage incidents
- Continuous sync (no > 1h outages without notification)
- Notification rate stays under Adam's fatigue threshold (response rate ≥ 30%)
- Adam reports increased trust at day 7 vs. day 1 (qualitative, captured in `LOG.md`)

### 7.3 Continuous-improvement criteria (post-launch)

The eval/calibration loop (F8) runs continuously: weekly drift report, weekly production sampling. policy.yaml versions are bumped from `v0` (current draft) → `v1` (after first calibration in M4) → `v2+` as the corpus grows. The policy file is the **agent's cost-discipline artifact** — every change is a deliberate, evidence-backed act.

---

## 8. Constraints & Trade-Offs

- **No GPU on VPS** — locked. Drives single-3B-model commitment.
- **$30/month budget** — locked. Drives Rule Ω, the 4-layer budget guard, and policy-table default-cheapest.
- **Cron-pull only (no webhooks)** — locked. Trades freshness in minutes for no public endpoint + simplicity.
- **Single user** — locked. Drives the single-grantor authorization model, single notification surface, single memory subject.
- **Anthropic direct, no OpenRouter** — locked. Simpler accounting; cost discipline easier to reason about.
- **No 7B local at v1** — locked. Revisit only if benchmarks prove specific tasks need it AND a VPS upgrade is justifiable.

---

## 9. Open Questions

These are real gaps the build order also flagged. The PRD lists them so they're visible at planning time; none block MVP authoring but several need decisions before they bite.

- **OQ-1 — Attachment policy (Phase 1 #27):** store BLOB / on disk / lazy-fetch. Deferred past MVP; `has_attachments` boolean only at v1.
- **OQ-2 — Sync conflict resolution (Phase 1 #26):** what happens when an email is moved/deleted between a sync and an in-flight action draining from `pending_actions`?
- **OQ-3 — Soft vs hard schema for derived fields (Phase 1 #30):** strict columns vs JSON meta. M1.4 committed to strict columns; revisit if column churn becomes painful.
- **OQ-4 — History vs latest-only derivation audit (Phase 1 #31):** `derivations` table currently stores latest per task; do we want full history?
- **OQ-5 — Cascading routing (Rule N, future-state):** v1 has no cascade (try local first, then API on failure). Phase 4 M6.8 adds per-task cascade once benchmarks justify it.
- **OQ-6 — Honcho memory upgrade:** Hermes default memory first; upgrade to Honcho only if shallow.
- **OQ-7 — `[ASSUMPTION]` clean-up (Finalize step 4):** every `[ASSUMPTION]` tag in this PRD needs ratification or correction before status → final.

---

## 10. Decision Provenance

This PRD codifies decisions made in `_bmad-output/brainstorming/brainstorming-session-2026-05-31-1430.md` (2026-05-31). All 21 architectural rules (Ω, A–X) were ratified by Adam on 2026-05-31 ("ratify everything"). Companion artifacts:

- `policy-v0.yaml` — initial routing policy, every assignment annotated with DEMOTION HYPOTHESIS
- `phase-4-build-order.md` — 6-milestone, ~80-task build plan with verification criteria

These are inputs to downstream documents (architecture, epics, stories), not inputs to this PRD's structure. The PRD's job is to frame *what MailBot does for Adam* and *what makes MVP/launch valid*; the build order's job is to plan *how it gets built*.

---

## Appendix A — Glossary

Definitions for terms that appear repeatedly in this PRD and downstream documents. Glossary entries override informal usage anywhere else in the document.

- **Cost tier** — A position in the LLM cost ladder. Three values: **Free** (Qwen 3B local), **Cheap** (Claude Haiku 4.5), **Premium** (Claude Opus 4.7). Used in F3 and policy.yaml. *Not* the same as authorization tier.
- **Authorization tier** — A category of action that determines what user authorization is required before the action executes. Four values: **Tier 0** (free), **Tier 1** (auto-revertible, logged), **Tier 2** (batch approval), **Tier 3** (per-action confirmation). Defined in F5. *Not* the same as cost tier.
- **Verb** — A Python function in `mailbot_api/verbs/` exposed to the agent via MCP. The agent's only data window. Each verb has Pydantic input/output schemas, built-in cost ceilings, and sanitized error returns. Examples: `find_emails`, `hydrate_email`, `propose_action`, `apply_action`, `ask_router`.
- **Lane** — A Router execution channel. Two values: **interactive** (chat-driven, preempts batch) and **batch** (ingest, cron, background). Each task in `policy.yaml` is assigned a lane (Rule K).
- **Grant** — A scoped, time-bounded authorization issued by Adam in chat, cached against `(action_type, email_ids, expiry)`. Authorizes Tier 2/3 actions for the duration of the grant. Verified again at queue-drain time (FR-5.5).
- **Session token** — Per-session confirmation token minted when Adam approves API escalation for a `sensitive` email. Scoped to `(email_id, task_type)`. Single-use. Defined at FR-5.7. *Distinct from* a grant: a session token authorizes *model use*, a grant authorizes *action execution*.
- **Force model** — A per-call override allowing the agent (or Adam, via chat) to specify a model that differs from `policy.yaml`'s default for the task. Always logged with `model_chosen_reason="override"`. Use is constrained by sensitivity routing and budget guards.
- **Degraded mode** — A persistent Router state entered when the monthly cap is breached. Opus demotes to Haiku; Haiku demotes to Qwen. Force-Opus requires explicit chat confirmation. Persists until month rollover or manual reset (FR-6.3).
- **`RouterResult`** — The structured return type of every Router call. Contains `ok` (bool), `output` (parsed data or None), `error` (structured `RouterError` with stable code + sanitized message), `cost_usd`, `latency_ms`, `tokens_in/out`, `model_used`.
- **Sensitivity class** — A property of every email, written at ingest by Qwen-only classification. Three values: **normal**, **sensitive**, **confidential**. Defined at NFR-PRIV-1; routing implications at NFR-PRIV-2.
- **DEMOTION HYPOTHESIS / PROMOTION HYPOTHESIS** — Annotations in `policy.yaml` for non-default tier assignments. A demotion hypothesis predicts a task can be moved to a cheaper tier given evidence; a promotion hypothesis predicts a task on Qwen will need escalation given observed failure rates. Both are validated by F8 benchmarks.
- **Derived field** — A column on the `emails` table populated once at ingest by an LLM, cached forever (Rule A). Has companion columns: `*_prompt_v`, `*_conf`, `*_model`, `*_at`. Read at chat time; never recomputed except by explicit re-derivation pass.

---

## Appendix B — Assumptions Index

Inline `[ASSUMPTION]` tags collected for Finalize-step-4 ratification (OQ-7).

| Location | Tag content | Finalize disposition |
| -------- | ----------- | -------------------- |
| FR-1.6   | 90-day refresh-token expiry mitigated by continuous sync — no monitoring requirement beyond FR-1.5 | Adam to confirm |
| FR-4.8   | Slash commands work identically in DM and shared-server channel | Adam to confirm or defer |
| FR-6.3   | Manual override for degraded mode is `/budget reset` | Adam to confirm command name |
| FR-7.6   | Trust-signal self-reflection (FR-7.5) defaults to enabled | Adam to confirm default |
