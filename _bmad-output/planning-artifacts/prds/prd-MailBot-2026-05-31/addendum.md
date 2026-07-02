---
title: MailBot PRD — Addendum
description: User-contributed depth and technical-how that belongs downstream of the PRD (architecture, solution design, build order) — preserved here so it isn't lost.
parent: prd.md
created: 2026-05-31
---

# MailBot PRD — Addendum

The PRD frames *what* MailBot does and *what makes MVP valid*. This addendum preserves the *how* — depth that earned its place but lives downstream of the PRD: architecture choices with rejected alternatives, the routing-policy table with hypotheses, the Hermes-primitive map, and pointers to the brainstorming artifacts.

---

## A1 — Runtime Architecture (committed)

```text
┌───────── VPS (Hostinger KVM 2, 8 GB / 2 vCPU, no GPU) ──────┐
│                                                              │
│  Docker network: mailbot-net                                │
│                                                              │
│  Container: mailbot-hermes  (nousresearch/hermes-agent)     │
│    Volume /opt/data:                                        │
│      .env, config.yaml, SOUL.md, AGENTS.md                  │
│      skills/mailbot/SKILL.md                                │
│      cron/jobs.json, sessions/, memories/                   │
│    Gateway: Discord adapter                                 │
│    Provider config: custom → http://mailbot-api:8000/v1     │
│                                                              │
│  Container: mailbot-api  (Python + MCP + Router + sync)     │
│    Endpoints:                                               │
│      POST /v1/chat/completions  (Hermes's LLM provider)     │
│      POST /v1/embeddings                                    │
│      GET  /health, /v1/health                               │
│      MCP server (Hermes connects as MCP client)             │
│    Internal:                                                │
│      Router (policy.yaml, budget, router_calls log)         │
│      Verb library (find_emails, hydrate_email, …)           │
│      Sync worker (called by Hermes cron, no_agent=True)     │
│      pending_actions queue drainer                          │
│    Holds: ANTHROPIC_API_KEY (Rule F.1)                      │
│    Volume /data: SQLite DB, logs                            │
│                                                              │
│  Container: ollama  (ollama/ollama)                         │
│    Pre-pulled: qwen2.5:3b-instruct-q4_K_M                   │
│                nomic-embed-text                             │
│    Volume /root/.ollama: model files                        │
└──────────────────────────────────────────────────────────────┘
```

### Data-flow architecture

```text
Outlook (Graph API)
        ▲ │
        │ ▼  (Python sync layer — cron-driven, every 4m)
        │
   ┌────┴───────────────────────────────────────┐
   │  Local SQL DB (SQLite, WAL mode)           │
   │  - emails (raw + derived fields)           │
   │  - threads, senders                        │
   │  - derivations history                     │
   │  - pending_actions queue                   │
   │  - router_calls audit log                  │
   │  - benchmark_runs                          │
   │  - response_cache                          │
   └────┬───────────────────────────────────────┘
        ▲
        │  (Tailored Python verb API → exposed via MCP)
        ▼
   Hermes Agent  ◀──▶  Router (cost discipline)  ──▶  Qwen 3B (Ollama)
                                                  └▶  Claude Haiku 4.5
                                                  └▶  Claude Opus 4.7
                                            (API key only here — Rule F.1)
```

---

## A1b — Why the Router Is the Architectural Center

The Router's centrality is not a stylistic preference — it falls out of Rule F.1.

**Causal chain:**

1. **Rule F.1 — Anthropic API key isolation.** The decision was made that the API key must live in *one process only*, not in Hermes (which is third-party code that can update, ship bugs, or be reconfigured) and not in any verb that the agent can call directly.
2. **Consequence:** that process is `mailbot-api`. Any code that needs to call Anthropic must go through `mailbot-api`.
3. **Consequence:** since the only path to a high-grade model is through `mailbot-api`, *that* is where the cost decisions get made. Where else could they live?
4. **Consequence:** the same process becomes the natural home for:
   - Per-call cost accounting (model, tokens in/out, $ estimate, caller verb, task type)
   - Anthropic prompt caching (system-prompt reuse → large savings)
   - Response caching keyed by `hash(prompt + model + temp)` → identical calls free on repeat
   - Cascading / fallback (try local → API only if low confidence or unparseable)
   - Budget guardrails (daily/monthly cap → refuse or downgrade past threshold)
   - Routing-policy enforcement
   - Sanitized error returns (Rule F teeth — exceptions never bubble raw to the agent)
   - Trajectory/audit log of every LLM call

So the Router is not a layer we *chose* to build. It is the architectural shape that **falls out of holding the API key in one place**. Rule I ("Router as Single Source of Truth") is a downstream observation — every LLM call must already go through the Router because that is the only process that has the key.

This is why the Router gets so much surface area in the PRD: it is doing the work of secrets isolation, cost discipline, and routing all at once — and one is consequence of the other.

---

## A2 — Rule Inventory (Ω, A–X)

All 21 rules from the brainstorming session, ratified 2026-05-31. The PRD's FRs and NFRs are the user-facing projection of these rules.

| Rule | Name                                  | Where it shows in PRD                   |
| ---- | ------------------------------------- | --------------------------------------- |
| Ω    | Cost Minimality (meta-principle)      | §2, FR-6.6, all model routing           |
| A    | Derived-Field Caching                 | FR-2.1, FR-2.6                          |
| B    | Local SQL as Agent's Only World       | §6, NFR-OPS-3                           |
| C    | Tailored Python Verb API              | §6, FR-3.2                              |
| D    | Cron-Pull Sync                        | FR-1.1, §8 trade-off                    |
| E    | Write-Back via Queued Intents         | FR-5.5                                  |
| F    | Secrets Isolation                     | NFR-SEC-1..6                            |
| G    | Local for Batch, API for Interactive  | FR-3.5, NFR-PERF-3                      |
| H    | Eval-Driven Routing                   | F8 (FR-8.1..7)                          |
| I    | Router as Single Source of Truth      | FR-3.2, FR-3.9                          |
| J    | Hydration Discipline                  | FR-3.5 (verbs), build-order M3.8        |
| K    | Lane Separation + Backpressure        | FR-3.5, FR-2.4                          |
| L    | Continuous Eval Through Sampling      | FR-8.5, FR-8.6                          |
| M    | Cache Discipline                      | FR-3.6                                  |
| N    | Rate-Limits + Loop Detection + Kill   | FR-3.8, FR-6.x                          |
| O    | Production Outcome Tracking           | FR-8.7                                  |
| P    | Action Authorization Tiers            | F5 (FR-5.1..6)                          |
| Q    | Sensitivity-Aware Routing             | NFR-PRIV-1..3, FR-2.5                   |
| R    | Notification Discipline               | FR-7.4, FR-7.5                          |
| S    | Dev-Prod Parity via Containers        | NFR-OPS-1                               |
| T    | Single-Command Deploy                 | NFR-OPS-2                               |
| U    | Secrets Never in Source Control       | NFR-SEC-1                               |
| V    | Data Survives the Container           | NFR-OPS-3                               |
| W    | Observability From Day One on VPS     | FR-7.1..3                               |
| X    | Hermes-Native Integration             | §6, FR-4.1, NFR-OPS-6                   |

### A2b — Pre-Mortem: the six failure modes that produced Rules J–O

The brainstorming session ran a pre-mortem walking backwards from a single scenario: *"September 2026 — the bill arrived and it was $340 instead of $30."* Six distinct failure modes were named, and each produced one of Rules J–O. These rationales are load-bearing — the rules don't make sense without the threats they answer.

| Rule | Failure mode the rule prevents                                                                                                                                  |
| ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| J    | **Context bloat via verbs.** Agent dumps 47 full email bodies into one Opus call. Without hydration discipline (projections + rate-limited `hydrate_email`), the agent has no incentive to reason about which emails matter before paying for full content. |
| K    | **Backlog death loop + idempotency bugs + cascade-escalation storms.** Without lane separation, batch backlog starves the interactive lane. Without strict idempotency keys, re-runs after a crash duplicate calls. Without per-task escalation budgets, one prompt change cascades the whole policy to higher tiers. |
| L    | **Eval/production drift.** The corpus is hand-labeled in May. In August, GitHub starts sending notification emails Qwen has never seen. Coarse-class accuracy quietly collapses; the eval suite says it's fine because the eval suite doesn't have GitHub notifications. Without continuous sampling, you don't notice for weeks. |
| M    | **The prompt-cache miss cliff.** You design assuming 85% Anthropic cache hits → 10× cost reduction on high-volume tasks. In production the cache never warms because sync cadence misaligns with the 5-min TTL, or a small prompt edit invalidates everything. You discover this when the bill arrives. |
| N    | **The runaway-agent loop.** An agent bug or prompt regression causes a tight loop: 8,000 small Haiku calls overnight, $50 burned. Without rate limits, loop detection, or a kill-switch reachable from outside the agent's own control flow, you wake up to a charge. |
| O    | **Silent quality regression on subjective tasks.** v3 of the draft prompt is subtly worse than v2 — slightly worse tone, slightly more hallucinated names. There's no auto-eval that catches it because drafts can't be scored objectively. Without production-outcome telemetry (what did Adam edit? did the recipient reply?) you don't notice for 5 weeks. |

Rule Ω was articulated in the same session as the meta-principle that gives the rest their shape: *"never use a distant LLM if local can do the task; never use a high-grade distant if a low-grade one can."* All six failure modes above are downstream of taking Ω seriously: the rules are the operational machinery that lets Ω be safe to follow.

---

## A3 — Routing Policy v0 (full task table)

This is `policy-v0.yaml` as of 2026-05-31. **Status: DRAFT — every non-Qwen assignment is a HYPOTHESIS** to be validated by the benchmark system (FR-8.2..4) before status moves past `v0`.

### Tier distribution

- **Opus (premium) — 3 tasks:** `draft_reply`, `tone_style_mirror`, `user_model_refresh`
- **Haiku (cheap) — 8 tasks:** `action_extraction`, `importance_scoring`, `intent_parsing_chat`, `reference_resolution`, `subscription_audit`, `bulk_action_proposals`, `summarize_long_thread`, plus escalation target for several 3B tasks
- **Qwen 3B (free) — 14 tasks:** all ingest pipeline, all background/cron, simple chat, sensitivity classification (Rule Q: local-only by definition)
- **Embedding-only — 1 task:** `embedding` (bge-small / nomic-embed-text)

### Per-task assignments (with `max_tokens_out` ceilings — Rule N Layer 1)

#### Opus (premium)

| Task                 | Prompt | Escalate    | Lane        | Max tokens out | Demotion hypothesis                                            |
| -------------------- | ------ | ----------- | ----------- | -------------- | -------------------------------------------------------------- |
| `draft_reply`        | v1     | false       | interactive | 800            | Very weak — only on edit-distance parity from Haiku (Rule O)   |
| `tone_style_mirror`  | v1     | false       | interactive | 600            | Medium — Haiku may match with style examples in SYSTEM         |
| `user_model_refresh` | v1     | false       | batch       | 2000           | Weak — synthesis quality matters; runs ≤1×/month               |

#### Haiku (cheap)

| Task                    | Prompt | Escalate     | Lane        | Max tokens out | Demotion hypothesis                                  |
| ----------------------- | ------ | ------------ | ----------- | -------------- | ---------------------------------------------------- |
| `action_extraction`     | v1     | true → opus  | batch       | 300            | Medium — bench 3B; demote if ≥ 90% on dates + asks   |
| `importance_scoring`    | v1     | false        | batch       | 50             | Weak — likely stays on Haiku                         |
| `intent_parsing_chat`   | v1     | false        | interactive | 100            | **STRONG** — demote if 3B p95 < 1.5s + ≥ 95% labels  |
| `reference_resolution`  | v1     | false        | interactive | 50             | Medium                                               |
| `subscription_audit`    | v1     | false        | batch       | 1500           | Medium — viable on 3B if pre-classified              |
| `bulk_action_proposals` | v1     | false        | interactive | 800            | **STRONG** — 3B may handle if summaries are clean    |
| `summarize_long_thread` | v1     | true → opus  | interactive | 600            | Weak — 3B context too small for long threads         |

#### Qwen 3B (free, default per Rule Ω)

| Task                        | Prompt | Escalate     | Lane        | Max tokens out | Notes                                                |
| --------------------------- | ------ | ------------ | ----------- | -------------- | ---------------------------------------------------- |
| `coarse_class`              | v1     | false        | batch       | 100            | 6 categories: transactional/newsletter/human/notification/spam_like/unknown |
| `fine_class`                | v1     | true → haiku | batch       | 100            | 4 sub-classes within "human": personal/professional/cold-outreach/automated-but-human-looking. PROMOTION HYPOTHESIS: cold-outreach vs real prospect may need Haiku. |
| `sensitivity_class`         | v1     | false        | batch       | 30             | **local_only** — hard Rule Q. Cautious bias: uncertain → `sensitive`. |
| `auto_file_decision`        | v1     | false        | batch       | 50             | Tier 1/2 action proposer                             |
| `unsubscribe_candidate`     | v1     | false        | batch       | 50             | Tier 2 proposer                                      |
| `notification_decision`     | v1     | false        | batch       | 30             | Rules + 3B tiebreaker                                |
| `thread_continuity`         | v1     | false        | batch       | 50             | Memory + small LLM tiebreaker                        |
| `summary_short`             | v1     | false        | batch       | 200            | Per-email summary, computed at ingest, cached forever (Rule A). Foundation of Rule J hydration. |
| `summarize_short_thread`    | v1     | true → haiku | interactive | 400            | ≤3 emails, ≤2K tokens                                |
| `sender_reputation_summary` | v1     | false        | batch       | 100            | One-line description, generated on first contact, cached forever |
| `daily_digest`              | v1     | false        | batch       | 800            | Templating + light synthesis from pre-computed columns |
| `anomaly_detection`         | v1     | false        | batch       | 100            | Rules-first; 3B tiebreaker on ambiguous signals      |
| `promised_reply_check`      | v1     | false        | batch       | 100            | Memory + recent emails                               |
| `multi_turn_refinement`     | v1     | true → haiku; opus only on `force_model` | interactive | 600 | Simple edits on already-produced text |

#### Embedding

`embedding` → `bge-small-local`. Embed every email at ingest. ~100 MB resident, near-free CPU.

### Operational settings (in policy.yaml header/footer)

- **Budget:** `monthly_cap_usd=30`, `daily_warn=2`, `per_call_refusal=0.20`, demotion chain Opus→Haiku→3B
- **Rate limits:** chat 60/hr, ingest 300/hr (backpressure at queue > 500), escalations 20/hr (circuit-breaker)
- **Anti-loop:** prompt-hash repeat window 10 / 5 min
- **Sensitivity routing:** normal = policy as-is; sensitive = qwen-3b default, API requires per-session confirm; confidential = qwen-3b only, always
- **Cache warmer:** every 4 min (cache TTL = 5 min, ingest cron aligned)
- **Continuous eval:** weekly 5-call sampling + weekly drift report

### Calibration cadence

1. Build eval corpus v1 (~100 hand-labeled emails) — one-time, manual
2. Run `benchmark/runner.py` over ALL tasks × ALL models
3. Generate dashboard: accuracy × latency × cost per (task, model)
4. For each Haiku/Opus row: check DEMOTION HYPOTHESIS — if 3B meets threshold, demote, bump prompt version
5. For each 3B row with `escalate=true`: monitor escalation rate after first week of prod data — if > 30%, PROMOTION HYPOTHESIS won, bump tier
6. Repeat at every prompt version change and quarterly

---

## A4 — Hermes Primitives In Use

What we use from Hermes vs. what we build. Every "use Hermes" was a deliberate choice (Rule X).

| Hermes feature       | Our use                                                                                |
| -------------------- | -------------------------------------------------------------------------------------- |
| Discord gateway      | Chat UI for the user                                                                   |
| `cron` (no_agent)    | Outlook sync (script-only, zero LLM cost)                                              |
| `cron` (with agent)  | Daily digest, weekly drift report, weekly eval-sampling prompts                        |
| `wakeAgent: false`   | Sync script suppresses agent wake when no new emails (anti-loop / cost protection)     |
| `context_from`       | Chain sync → classify → digest cron jobs                                               |
| `enabled_toolsets`   | Per-cron-job toolset narrowing (cost control)                                          |
| `fallback_providers` | Direct Anthropic safety net if our Router is down (emergency only)                     |
| Persistent memory    | Adam's preferences, user model, learned senders                                        |
| `SOUL.md`            | Persona — defender, conservative, asks before destructive actions                      |
| `AGENTS.md`          | Operational rules (Rules J/N/P/R as agent behavior)                                    |
| MCP server (ours)    | Verb library exposed to Hermes via Model Context Protocol                              |
| Prompt caching       | Built-in; we configure cacheable SYSTEM blocks in our Router                           |
| Context compression  | Built-in; `auxiliary.compression` pointed at our Router → Qwen                         |

What we explicitly do **not** reimplement: chat UI, scheduler, memory store, secret-management UI, fallback retry loops, session persistence, prompt-caching primitives, context compression.

---

## A5 — Verb API (Adam's contract with the agent, via MCP)

The agent's data window is hand-crafted Python verbs, exposed as MCP tools. No `SELECT *`. No raw SQL. Built-in cost ceilings (pagination, max_chars). Audit log of every call.

Initial verb set (M3.8 in build order):

- **Read-side (projection only, per Rule J):**
  - `find_emails(filter, limit=20)` — lightweight projection: ID + metadata + `summary_short`
  - `hydrate_email(email_id)` — full body, **rate-limited 5 per chat turn**
  - `get_thread(thread_id)` — all emails in thread (projections)
  - `list_unread(folder=None)` — projection
  - `count_emails(filter)` — count only
  - `get_sender_summary(address)` — projection
- **Write-side (queued, tier-checked per Rule P):**
  - `propose_action(email_id, action_type, **payload)` — inserts into `pending_actions`, tier-checked at insert
  - `apply_action(action_id, authorization_token=None)` — drains a pending action, requires fresh authorization for Tier 2/3
- **LLM-side (all routed):**
  - `ask_router(task_type, content, force_model=None, max_cost_usd=None) → RouterResult`

Every verb has Pydantic input + output schemas. Errors sanitized per Rule F before reaching the agent.

---

## A6 — Decision Provenance (rejected alternatives)

Choices the brainstorming session weighed and rejected. Preserved here so the rationale doesn't rot.

- **Webhooks for sync:** rejected → cron-pull (no public endpoint, no webhook complexity, freshness in minutes is acceptable for defender role). Rule D.
- **Raw SQL for agent access:** rejected → tailored Python verbs (controlled vocabulary, cost ceilings, swappable backend, audit log). Rule C.
- **API key in Hermes process:** rejected → Anthropic key held by `mailbot-api` Python process only (Hermes bug/update can't exfiltrate). Rule F.1.
- **Routing intuition in policy.yaml:** rejected → every non-Qwen assignment is a benchmark-backed hypothesis (Rule H + Rule Ω).
- **Cascading routing at v1 (try Qwen → escalate to Haiku on every call):** rejected → static policy table with per-task `escalate` flag; cascading added post-MVP only where benchmarks justify it (M6.8).
- **Middle-tier from day 1 (Sonnet or always-on Haiku):** rejected → binary Qwen-or-Opus is the starting position; Haiku enters via `policy.yaml` per benchmark evidence. (Note: Haiku is now part of the v1 stack — this is a 2026-05-31 update vs. the early-session position.)
- **GPU upgrade for local 7B:** rejected → no GPU on VPS, no upgrade, single-3B-model commitment forces design discipline.
- **OpenRouter for provider routing:** rejected → Anthropic direct (simpler accounting, easier cost reasoning).
- **Hermes plugin / HTTP-via-skill for tool integration:** rejected → MCP (clean separation, standard protocol).
- **Honcho memory from day 1:** rejected → Hermes default memory first; upgrade only if shallow (avoid premature complexity).

---

## A7 — Build-Order Pointer

Full implementation plan: `_bmad-output/brainstorming/phase-4-build-order.md` — 6 milestones, ~80 tasks, T-shirt sizes, dependencies, MVP cuts, verification criteria, and "things that will bite you" callouts.

| #  | Milestone                       | Goal                                                  | MVP? |
| -- | ------------------------------- | ----------------------------------------------------- | ---- |
| M1 | Foundation & scaffold           | Repo, Docker, SQLite schema, Outlook sync (no LLM)    | must |
| M2 | Router & local LLM              | Ollama + Qwen + `/v1/chat/completions` + router_calls | must |
| M3 | Anthropic tier + budget         | 3-tier routing, budget guards, cache, sensitivity     | must |
| M4 | Eval system                     | Corpus + runner + scorer + first calibration          | must |
| M5 | Hermes integration              | MCP verbs, SOUL/AGENTS, Discord, cron sync            | must |
| M6 | VPS deployment                  | Hostinger deploy, backups, observability, 1-week run  | must |

**MVP line:** end of M5. **Real launch:** M6.7 (first prod deploy + 1-week unattended run). **Estimated:** ~10 weeks part-time to MVP, +2 weeks to launch.
