---
stepsCompleted: [1, 2, 3, 4]
inputDocuments: []
session_topic: 'MailBot — designing the planning & optimization layer (hybrid LLM routing + pre-deployment measurement) around a Hermes Agent-powered personal Outlook mailbox defender'
session_goals: 'Generate architecture & decision-framework ideas for: (1) hybrid local/API LLM routing under cost+quality+privacy constraints, (2) pre-deployment measurement & optimization process that minimizes API spend during development, (3) everything Hermes will need at deploy-time (skills, memory schema, prompts, tools, guardrails) with cost-awareness baked in.'
selected_approach: 'progressive-flow'
techniques_used: ['Phase1: Task Decomposition + What If Constraint Reversal', 'Phase2: Morphological Analysis (routing axes)', 'Phase3: Pre-Mortem + Minimum-Viable-Instrumentation', 'Phase4: Decision Tree Mapping → Hermes deliverables']
ideas_generated: []
context_file: ''
---

# Brainstorming Session Results

**Facilitator:** Adam
**Date:** 2026-05-31

## Session Overview

**Topic:** MailBot — designing the planning & optimization layer (hybrid LLM routing + pre-deployment measurement) around a Hermes Agent-powered personal Outlook mailbox defender, running on a VPS.

**Goals:** Architecture & decision-framework ideas for hybrid local/API LLM routing, pre-deployment measurement & optimization process, and the full set of Hermes deploy-time artifacts (skills, memory, prompts, tools, guardrails) — all designed with cost-awareness from day one.

### Context Guidance

- **Workload:** personal Outlook mailbox, defender role (clean, filter, suggest, monitor, notify), chat-driven control
- **Runtime target:** Hermes Agent on a VPS (currently planning on local machine)
- **LLM constraints:** local LLM (cheap, limited capability, private) vs. API LLM (Claude Opus 4.7-class — strong, expensive); hybrid routing needed
- **Pain anchor:** too much email noise; user wants conversational control of inbox
- **Engineering anchor:** don't waste API money; instrument before optimizing
- **Hermes affordances:** persistent memory + full-text search, autonomous skill creation, cron, subagents, MCP, 60+ tools, 20+ messaging platforms

### Session Setup

Progressive Flow approach with bias toward constraint-driven / decompositional techniques (task taxonomy, cost-quality-privacy axes, pre-mortem, minimum-viable-instrumentation).

## Technique Selection

**Approach:** Progressive Technique Flow (engineering / cost-constraint bias)

**Progressive Techniques:**

- **Phase 1 — Expansive Exploration:** Task Decomposition + "What If" Constraint Reversal (atomize the workload, surface cost-sensitivity per task)
- **Phase 2 — Pattern Recognition:** Morphological Analysis on routing axes (build routing decision matrix: quality / latency / privacy / volume / frequency / reversibility)
- **Phase 3 — Idea Development:** Pre-Mortem + Minimum-Viable-Instrumentation (design telemetry & local dev harness backwards from probable failure modes)
- **Phase 4 — Action Planning:** Decision Tree Mapping → concrete Hermes deliverables checklist (skills, memory schema, prompts, tools, guardrails, kill-switches)

**Journey Rationale:** This is engineering-under-constraint, not pure ideation. The sequence forces decomposition before routing, routing before measurement, measurement before deliverables — so every Hermes artifact is cost-aware by construction.

---

## Phase 1 — Expansive Exploration: Task Decomposition + Constraint Reversal

**Goal:** Generate 30–50 atomic mailbox-agent operations, each provisionally tagged with cost-sensitivity.

### Architectural Commitments Made During Phase 1

These are now hard rules for the whole design:

#### 🔒 Rule A — Derived-Field Caching (cost discipline)

**Every piece of information an LLM ever produces about an email gets written back to the SQL row for that email, and is never recomputed.**

Implications:

- The runtime/chat-time agent **reads** derived fields; it does not re-derive
- Every chat-time LLM call must answer: *"Could this have been pre-computed at ingest?"* → if yes, it MUST be
- Expensive work is pushed into a predictable, batchable, off-peak ingest pipeline that runs once per email, ever
- Required machinery: prompt versioning (`*_prompt_v` columns), confidence storage (`*_conf`), pipeline versioning (`processed_pipeline_v`), idempotency on re-runs, optional targeted re-derive passes when prompt/user-model changes
- Limits acknowledged: cross-email synthesis and drafting are not precomputable — but their inputs (per-email summaries, classifications) are

#### 🔒 Rule B — Local SQL as the Agent's Only World

The agent never talks to Microsoft Graph directly. It reads from a local SQL DB and writes intents that a separate Python sync layer translates to Graph calls.

#### 🔒 Rule C — Tailored Python Verb API (no raw SQL for the agent)

The agent's only window into the data is a hand-crafted toolbox of Python verbs (likely exposed as MCP tools or Hermes skills). No `SELECT *`. Benefits: controlled vocabulary, built-in cost ceilings per call (pagination, max chars), swappable backend, natural audit log of every agent action.

#### 🔒 Rule D — Cron-Pull Sync (no webhooks)

Sync is periodic cron-based pull from Graph. Trade: freshness in minutes (acceptable for a defender role); benefit: no public endpoint, no webhook complexity.

#### 🔒 Rule E — Write-Back via Queued Intents

Agent writes proposed actions to a `pending_actions` table. A Python worker drains, applies to Graph, and records results. Benefits: retry, audit, dry-run, undo, decoupling.

#### 🔒 Rule F — Secrets Isolation

- All secrets live in `.env` (with strict file perms — `chmod 600`, owned by service user). Never in agent prompts, skills, configs, memory, or source files.
- Secrets are referenced by name only. Injected as env vars to processes at startup.
- The agent has **no filesystem path** to `.env`, `*.key`, `*.pem`, SSH dirs, or the SQL DSN. Tool-layer denylist, enforced outside the agent's control.
- The Python verb API is the **only** code that touches secrets (including the Anthropic API key — wrapped behind an `ask_strong_model(...)` verb). Verbs sanitize all error messages and return values before they reach the agent.
- A **chat-input redactor** scrubs token-shaped strings (JWT, `sk-…`, hex blobs, etc.) before any user message enters agent memory or is forwarded to an external LLM API.
- **Memory exports / trajectory dumps** run through the same redactor.
- Secrets rotation is a Python-API concern, not an agent concern. The agent never re-authenticates anything itself.
- **F.2 decision:** `.env` is sufficient. Design the Python API with a single `get_secret(name)` indirection so swapping to a vault (pass / age / Vault) later is a small, localized change.
- **F.1 decision:** Anthropic API key is held by the **Python verb API process**. The agent calls an `ask_strong_model(...)` verb; only that verb's process reads `os.environ["ANTHROPIC_API_KEY"]`. Hermes never has the key in its own process memory. This makes the **router a first-class Python component** (where cost discipline, model selection, caching, retry, and observability live) and keeps a Hermes bug/update from being able to exfiltrate the key.

#### Consequence of F.1(a): the Python Router becomes a major architectural component

Both LLM call paths flow through Python code we own. The router is now the natural home for:

- Per-call cost accounting (model, tokens in/out, $ estimate, caller verb, task type)
- Anthropic prompt caching (system-prompt reuse → large savings)
- Response caching keyed by `hash(prompt + model + temp)` → identical calls free on repeat
- Cascading / fallback (try local → API only if low confidence or unparseable)
- Budget guardrails (daily/monthly cap → refuse or downgrade past threshold)
- Routing-policy enforcement (the Phase 2 matrix actually executes here)
- Sanitized error returns (Rule F teeth — exceptions never bubble raw to the agent)
- Trajectory/audit log of every LLM call (for post-hoc cost analysis)

Updated runtime architecture:

```text
Hermes Agent
     │
     ▼   (verb calls)
Python Toolbox API   ───▶   SQL DB (Rule B/C — read/write via verbs)
     │
     │   (LLM-routing verbs: ask_router / ask_local / ask_strong)
     ▼
Python Router (cost discipline, caching, budget, routing policy)
     │
     ├─▶ Local LLM endpoint (on VPS)
     └─▶ Anthropic API   ◀── ANTHROPIC_API_KEY read only here
```

### Architecture (as currently designed)

```text
Outlook (Graph API)
        ▲ │
        │ ▼  (Python sync layer — cron-driven)
        │
   ┌────┴───────────────────────────────────────┐
   │  Local SQL DB                              │
   │  - emails (raw + derived fields)           │
   │  - threads, senders, derivations history   │
   │  - pending_actions queue                   │
   └────┬───────────────────────────────────────┘
        ▲
        │  (Tailored Python verb API — MCP tools/Hermes skills)
        ▼
   Hermes Agent  ◀──▶  Routing layer  ──▶  Local LLM
                                       └▶  API LLM (Claude)
```

### Atomic Operations Inventory (Phase 1 output)

**Inbound per-message processing:**

1. Fetch & parse (no LLM — sync layer)
2. Sender reputation lookup (no LLM — DB)
3. Coarse class: transactional / newsletter / human / notification / spam-like / unknown (local LLM, small prompt)
4. Fine class within "human" (local LLM, API on uncertainty)
5. Importance scoring (needs user-model context — contested)
6. Action extraction: deadlines, asks, calendar, payment, password reset (API for ambiguous; regex/local for obvious)
7. Thread continuity check (memory + small LLM)
8. Auto-file decision (local LLM)
9. Auto-unsubscribe candidate (local LLM)
10. Notification decision (rules + LLM tiebreaker)

**Chat interface operations:**

- **(11)** Intent parsing (local LLM)
- **(12)** Reference resolution: "that one", "the lawyer" (memory + local LLM)
- **(13)** Draft reply generation (API — quality matters)
- **(14)** Tone/style mirroring (API + persistent style memory)
- **(15)** Multi-turn refinement (API)
- **(16)** Summarize a thread on demand (local for short, API for long/important)
- **(17)** Bulk action proposals (local LLM)

**Background / cron / monitoring:**

- **(18)** Daily digest generation (local — quality flexible)
- **(19)** Promised-reply tracking (small LLM + memory)
- **(20)** Anomaly detection: unknown-country login, currency mismatch (rules + local LLM)
- **(21)** Subscription audit (API — synthesis-heavy, infrequent)
- **(22)** User-model refresh (API, rare, batched)

**Sync layer & architecture decisions:**

- **(23)** Sync trigger model → **cron**
- **(24)** Sync scope per cycle → delta only (Graph delta query) — TBD details
- **(25)** Write-back model → **queued intents** (`pending_actions`)
- **(26)** Conflict resolution: stale-state handling when email moved/deleted between sync and action
- **(27)** Attachment policy: store BLOB / on disk / lazy-fetch — TBD

**Schema decisions (Rule A machinery):**

- **(28)** Derived-field caching columns → **committed (Rule A)**
- **(29)** Idempotency keys: `(email_id, prompt_version, model)` so re-runs are free
- **(30)** Soft vs hard schema for derived fields (strict columns vs JSON meta) — TBD
- **(31)** History/audit table for derivations vs latest-only — TBD

**Agent ↔ data contract:**

- **(32)** Read API surface → **tailored Python verbs (Rule C)**
- **(33)** Pagination & context-budget contract (verbs enforce, not LLM)
- **(34)** Pre-filtering before LLM (SQL/regex narrows candidates, LLM only sees survivors)

### LLM Handling Decisions

#### VPS reality

- **Spec:** KVM 2 / 2 vCPU / 8 GB RAM / 100 GB NVMe / 8 TB bandwidth, no GPU. Upgrade declined.
- **RAM budget for LLM:** ~4.5–5.5 GB after OS, SQL, Python services, and Hermes.
- **CPU-only inference reality:** 3B at ~10 t/s is usable; 7B at ~2–5 t/s is too slow for interactive chat.

#### 🔒 Rule G — Local for Batch, API for Interactive

- **Background / ingest / cron tasks** → local LLM is the default. Latency doesn't matter when nobody's watching.
- **Interactive chat tasks** → API LLM is the default. Sub-5-second response is a UX requirement.
- **Exceptions both ways:** trivial chat intents (sub-second 3B calls) can stay local; rare expensive batch syntheses can go API.
- **Why:** matches the VPS hardware honestly. Forcing 7B for chat would make the tool unusable.

#### Local LLM stack (committed)

- **Engine:** **Ollama** (simplicity over the ~10% perf cost vs raw llama.cpp; revisit if perf hurts)
- **Primary local model:** **Qwen 2.5 3B Instruct (Q4_K_M)** — always-on, ~2 GB resident. Workhorse for coarse classification, intent parsing, simple summaries, action extraction.
- **Embedding model:** **bge-small-en-v1.5** or **nomic-embed-text** via Ollama (~100–150 MB resident). Embed every email at ingest; enables semantic search over the SQL mailbox.
- **No 7B fallback.** Single-model local layer. Anything 3B can't handle reliably → escalate to API.
- **Privacy posture:** VPS-local is sufficient. The local Qwen process is allowed to see all email categories.

#### API LLM stack (committed)

- **Provider:** Anthropic
- **Model:** **Claude Opus 4.7** (id: `claude-opus-4-7`) — premium tier
- **No middle tier (yet):** no Sonnet, no Haiku. Binary choice: free-local-3B or premium-Opus-API.
- **Implication:** the 3B↔Opus capability gap is large; there is no graceful cheap escalation. Every task kept on 3B is pure savings.
- **Deferred decision:** **Claude Haiku 4.5** (id: `claude-haiku-4-5-20251001`, ~1/30th Opus price) may be added later as a middle tier if benchmarks show 3B failing on tasks where Haiku succeeds. The Router will be designed so **adding a third model is a single config change, not a refactor**.

#### 🔒 Rule H — Eval-Driven Routing

> No task is assigned to a model based on intuition. Every routing decision in the policy table is backed by a benchmark run on the eval corpus, with quality, latency, and cost numbers recorded. **The benchmark system is built BEFORE the production router is tuned**, not after.

#### Benchmark system (committed as a first-class deliverable)

Four moving parts:

1. **Eval corpus** — frozen, versioned, hand-labeled set of representative emails. MVP target: ~100 real (anonymized) emails covering the 5 most common task types. Stored as `evals/email_corpus_v1.jsonl`. Owner: Adam, manual, one-time ~3–6 h.
2. **Runner** — `benchmark/runner.py`. For every `(eval_item × model × prompt_version)`, executes the call, records output / tokens-in / tokens-out / latency / cost into a `benchmark_runs` SQL table.
3. **Scorer** — `benchmark/scorer.py`. Per task type:
   - Classification → exact match → accuracy, precision/recall, confusion matrix
   - Structured extraction → field-level match
   - Subjective (summary / draft) → hybrid approach: **~20 anchor examples scored manually by Adam (1–5 axes)**, then **strong-model auto-eval calibrated against those anchors** for the remaining items
4. **Report** — `benchmark/report.py`. Generates markdown / HTML dashboard: accuracy × latency × cost per (task, model), Pareto frontier per task, list of 3B failure modes with examples.

Eval system properties:

- **Not a production component** — runs on-demand, separately from the live agent
- **Not real-time** — triggered when prompts change, models change, or before any routing decision is committed
- **Drives the routing matrix** (Phase 2 output): every cell of the matrix cites a benchmark run

#### LLM-handling deliverables (added to Phase 4 list)

- `evals/email_corpus_v1.jsonl` — hand-labeled test set
- `evals/scoring_rubrics/*.md` — human-readable scoring criteria
- `benchmark/runner.py`, `benchmark/scorer.py`, `benchmark/report.py`
- `benchmark_runs` table in SQL DB
- Router design that exposes `ask_local(...)`, `ask_strong(...)`, `ask_router(task_type, ...)` verbs and supports adding new models via config

### Router Decision Logic (Topic #3 — all 6 sub-decisions committed)

#### Model stack — 3 tiers from day one

| Tier    | Model                       | ID                             | Role                                                  |
| ------- | --------------------------- | ------------------------------ | ----------------------------------------------------- |
| Free    | Qwen 2.5 3B (local, Ollama) | `qwen2.5:3b-instruct-q4_K_M`   | Bulk classification, intent parsing, simple summaries |
| Cheap   | Claude Haiku 4.5            | `claude-haiku-4-5-20251001`    | Middle ground when 3B fails or Opus is overkill       |
| Premium | Claude Opus 4.7             | `claude-opus-4-7`              | Drafts, tone mirroring, high-stakes synthesis         |

#### Decision 1 — Strategy: Option E (static table + override + budget guard)

- `policy.yaml` is the source of truth: per-task `{model, prompt_version, escalate, max_tokens_out}`
- Per-call override available (`force_model=...`); always logged
- Budget guard applies a **demotion chain: Opus → Haiku → 3B** under degraded mode
- **No cascading at v1.** Defer cascading to post-MVP, only add per-task once benchmarks justify it

#### Decision 2 — Agent interface: Option γ (single verb with optional override)

```python
ask_router(
    task_type: str,
    content: str,
    force_model: str | None = None,
    max_cost_usd: float | None = None,
) -> RouterResult
```

- One verb in the agent's toolbox
- Router decides by default (Rule H)
- Override is explicit, audited
- When user (in chat) says "use the strong model," agent passes `force_model="claude-opus-4-7"`

#### Decision 3 — Failure handling: layered + error-as-data + per-task escalation flag

Chain:

1. Call with policy model (Ollama JSON mode for local; response_format / prompt cache for API; `max_tokens_out` enforced)
2. Hard timeout (30s local / 60s API) → terminal error
3. Pydantic schema validation on output
4. On parse fail: single retry with same model + stricter "must be valid JSON" prompt
5. On persistent fail: per-task `escalate` flag in `policy.yaml`:
   - `escalate=true` → call next-tier model (3B→Haiku, Haiku→Opus), log `escalated_from=...`, flag for benchmark review
   - `escalate=false` → return `RouterResult(error=...)`, agent decides

Agent sees terminal failure as **structured error-as-data**:

```python
RouterResult(
    ok=False,
    output=None,
    error=RouterError(
        code="schema_validation_failed",   # stable code set
        message="...sanitized...",          # Rule F: no traces, no URLs
        model_attempted=[...],
        retryable=False,
    ),
    cost_usd=...,
    latency_ms=...,
    tokens_in=...,
    tokens_out=...,
)
```

Stable error codes: `schema_validation_failed`, `timeout`, `budget_exceeded`, `per_call_threshold_exceeded`, `provider_error`, `monthly_budget_exceeded`, `degraded_mode_blocked`.

#### Decision 4 — Budget enforcement: all 4 layers

- **Layer 1 — per-call ceiling:** `max_tokens_out` enforced per call (default 4000, task-overridable)
- **Layer 2 — daily soft warning:** target ~$1.50/day, warn at $2/day. Chat notification, no blocking.
- **Layer 3 — monthly hard cap: $30/month.** On breach: demotion chain (Opus → Haiku → 3B), one-time chat notice, `force_model` requires explicit chat confirmation
- **Layer 4 — per-call refusal threshold: $0.20.** Catches "agent stuffed entire mailbox into prompt" bugs. Refuse with `per_call_threshold_exceeded` unless explicit `force=true`

Numbers are starting placeholders — tune after first month of real `router_calls` data.

#### Decision 5 — Prompt management: Python module files + Anthropic prompt caching

Layout:

```text
prompts/
  __init__.py                  # registry: task_type → versions available
  coarse_class/
    __init__.py
    v1.py, v2.py, v3.py        # ← current per policy.yaml
  draft_reply/
    v1.py, v2.py
  intent_parsing/
    v1.py
  summary_short/
    v1.py
```

Each `vN.py` exports: `VERSION` (string), `SYSTEM` (cacheable block), `USER_TEMPLATE`, `OUTPUT_SCHEMA` (Pydantic class).

Router behavior:

- Loads all prompts at startup → registry `(task_type, version) → (SYSTEM, USER_TEMPLATE, schema)`
- For API calls: marks `SYSTEM` block with `cache_control={"type": "ephemeral"}` → repeated calls hit cache at ~10% input cost. **This is the single largest cost lever for high-frequency tasks.**
- Benchmark runner iterates `(task × all versions × all models)` automatically

`policy.yaml` ties prompts to models:

```yaml
coarse_class:
  model: qwen-3b
  prompt: v3
  escalate: false
  max_tokens_out: 100

draft_reply:
  model: claude-opus-4-7
  prompt: v2
  escalate: false
  max_tokens_out: 800

action_extraction:
  model: claude-haiku-4-5
  prompt: v1
  escalate: true       # → opus on parse fail
  max_tokens_out: 300
```

#### 🔒 Rule I — Router as Single Source of Truth for LLM Calls

> Every LLM call in the system goes through the Router. No direct calls to Ollama or Anthropic from anywhere else (sync layer, verb API, ad-hoc scripts, eval runner all included — the eval runner uses the Router with `force_model`).

`router_calls` table schema:

- `id`, `timestamp`
- `task_type`, `prompt_version`
- `model_chosen`, `model_chosen_reason` (`policy` / `override` / `degraded` / `escalated_from_<X>`)
- `tokens_in`, `tokens_out`, `cached_tokens_in` (Anthropic prompt cache hit count)
- `cost_usd_estimated`
- `latency_ms`
- `outcome` (`ok` / `retry_recovered` / `escalated` / `failed`)
- `caller_verb` (which Python verb made the call — for attribution)
- `email_id` (nullable; for tracing derived fields back to the call that produced them)

This table is the **single ground truth** for cost analysis, eval-vs-prod drift detection, and routing-policy tuning.

#### Router-related deliverables (added to Phase 4)

- `router/policy.yaml` — the routing table
- `router/router.py` — the Router itself: policy lookup, budget guard, cache, call execution, schema validation, retry, escalation, logging
- `router/models.py` — model adapters (Ollama client, Anthropic client) behind a common interface
- `router/pricing.py` — token-to-USD cost estimator per model
- `router/budget.py` — daily/monthly tracking, degraded-mode state
- `router/response_cache.py` — `hash(prompt+model+temp) → response` cache, SQL-backed
- `router/errors.py` — `RouterResult`, `RouterError`, stable error codes
- `prompts/<task>/vN.py` — versioned prompt modules
- `router_calls` table in SQL DB
- Chat notification hook (for degraded mode, daily warnings)

## Phase 3 — Pre-Mortem + Minimum-Viable-Instrumentation

Six failure modes walked back from a "September 2026 — bill was $340 instead of $30" scenario. Six new rules (J–O) added to address them. Above them all, one meta-principle (Rule Ω) was articulated by Adam that gives the whole system its soul.

### 🔒 Rule Ω — Cost Minimality (the meta-principle)

> **Two cascading prohibitions, in strict order:**
>
> 1. **Never use a distant LLM if the local one can do the task.** (Local-first.)
> 2. **Never use a high-grade distant LLM if a lower-grade one can do the task.** (Cheapest-tier-first within distant.)
>
> Cost management is a **first-class system property**, on par with correctness. Any design choice that violates these prohibitions requires explicit justification recorded in `policy.yaml` (as a comment) or in the audit log.

Operational consequences:

- **Default for every task is `qwen-3b`.** A task escalates to Haiku only when benchmarks prove 3B cannot do it acceptably.
- **Default for "API-required" tasks is Haiku.** A task escalates to Opus only when benchmarks prove Haiku cannot do it acceptably.
- Every Opus assignment in `policy.yaml` carries a benchmark citation in a comment.
- **Promotion (cheaper → expensive) ratchets only when benchmarks demand it.**
- **Demotion (expensive → cheaper) ratchets whenever benchmarks allow it.** Every prompt improvement that brings a task within 3B's reach moves it down the cost ladder.
- Features whose only justification is "would be nice" but require unjustified API spend are rejected.
- "Acceptable" must be defined per task in the eval rubrics — Rule Ω forces Rule H's rubrics to actually exist.

### 🔒 Rule J — Hydration Discipline

> Retrieval verbs return **lightweight projections** (ID + metadata + pre-computed summary). Full email bodies require explicit `hydrate_email(id)` calls. Hydration is **rate-limited per agent turn** (default: 5). This forces the agent to reason about which emails matter before paying for full content.

Captures: context bloat through verbs (the "agent dumps 47 full emails into one Opus call" failure).

### 🔒 Rule K — Lane Separation + Backpressure

> Router maintains two execution lanes (`interactive` / `batch`) with interactive preempting batch. Batch queue has a hard ceiling (refuse + warn). Escalations have an hourly circuit-breaker (pause + notify on excess). Idempotency key for derived fields is `sha256(body) + prompt_version + model + task_type`.

Captures: backlog death loops, idempotency bugs, cascade-escalation storms.

### 🔒 Rule L — Continuous Eval Through Sampling

> The eval corpus is not frozen. Each week the Router samples a small batch of production calls (stratified, confidence-weighted), prompts the user for ground-truth labels via chat (5–10 clicks), and grows the corpus automatically. A weekly drift report flags significant distribution shifts in inbox composition.

Captures: eval/production drift (the "GitHub notifications appeared in August, 3B was never trained for them" failure).

### 🔒 Rule M — Cache Discipline

> Anthropic prompt caching is a primary cost lever, not a bonus. The router tracks `cache_hit_rate` per task and alerts on regressions. High-volume tasks have a keep-warm pinger (cache TTL is 5 min — sync cadence is aligned to 4 min, not 15 min). Prompt version changes are previewed for cache-reset cost impact before rollout.

Captures: the prompt-cache miss cliff (you thought you had 85% cache hits; you have 10%).

### 🔒 Rule N — Rate-Limits + Loop Detection + Kill-Switch

> Router enforces per-(task, caller_verb) rate limits and detects prompt-hash repetition loops. Hourly call-volume anomalies trigger immediate chat alerts (don't wait for budget breach). A `pause_agent(reason)` kill-switch verb is exposed to a separate watchdog process and to user chat command, allowing emergency stop without killing Hermes itself.

Captures: the runaway-agent-loop failure ($50 overnight from 8000 small calls in a loop).

### 🔒 Rule O — Production Outcome Tracking for Subjective Tasks

> For subjective-quality tasks (drafts, summaries, tone-sensitive synthesis), the Router stores enough metadata to allow **post-hoc quality assessment from production data**: original output, user edits, downstream outcome signals (did recipient reply?). New prompt versions for these tasks roll out in **shadow mode first** (generated alongside the production version, not used; compared later).

Captures: silent quality regressions (v3 of draft prompt is subtly worse than v2; you don't notice for 5 weeks).

### 🔒 Rule P — Action Authorization Tiers

Every action the agent can take on the mailbox is classified into one of four authorization tiers. The agent cannot upgrade an action's tier; the verb API enforces it.

- **Tier 0 — Free** (no authorization needed):
  - Read anything in SQL
  - Run LLM calls
  - Generate drafts (in *draft* state, not sent)
  - Send chat notifications to user
  - Write derived fields to SQL

- **Tier 1 — Auto-revertible** (logged, agent does autonomously):
  - Mark as read / unread
  - Add/remove user-defined categories/tags in local SQL only (not synced to Outlook)
  - Move to a single "MailBot-Triage" folder (easy to inspect)

- **Tier 2 — Authorized batches** (agent proposes, user approves a batch via chat):
  - Archive emails (multiple at once)
  - Mark as junk / spam
  - Move to user folders (other than Triage)
  - Unsubscribe (clicking a link / submitting a form)

- **Tier 3 — Per-action confirmation** (agent proposes, user approves each one):
  - **Delete** anything (even though Outlook retains for 30 days)
  - **Send any email** (replies, new emails, forwards)
  - Modify Outlook rules / filters
  - Touch shared mailboxes or delegated accounts
  - Reply on behalf of a thread inactive >N days

**Tier-jumping mechanism:** user can grant **scoped, time-bounded authorization** via chat (e.g. *"You may delete the 47 emails you just identified as spam from Acme Corp; valid for 1 hour"*). Grant cached against `(action_type, email_ids, expiry)`. After expiry, grant invalid.

**Sending-specific additions:**

- Outbound emails flow through `pending_actions` queue (Rule E). The drain worker performs a **second authorization check** — refuses if no fresh grant.
- **Cooling-off period:** approved sends sit in `pending_send` state for N seconds (default 60s) before actually leaving. Catches "wait, not that one" moments. Configurable to 0.
- **Hard limit: max 20 outbound emails/day** from MailBot, regardless of authorization. Hijack-resistance.

### 🔒 Rule Q — Sensitivity-Aware Routing

Every email is classified at ingest with a `sensitivity` label by qwen-3b (Tier-0, local-only operation):

- **`normal`** — default
- **`sensitive`** — financial, legal, medical, personal/family, password-reset, health insurance, official ID documents, anything matching user-configured patterns
- **`confidential`** — work-confidential, NDA-bound, anything explicitly marked

Routing rules per sensitivity:

| Sensitivity  | Allowed models                                                                              | Memory storage                              | Logging                |
| ------------ | ------------------------------------------------------------------------------------------- | ------------------------------------------- | ---------------------- |
| normal       | qwen-3b, Haiku, Opus                                                                        | full body, indexed                          | full content           |
| sensitive    | qwen-3b only (default); API allowed ONLY with `force_model` + per-session chat confirmation | summary + IDs only; full body purged        | content hashed in logs |
| confidential | qwen-3b only, period                                                                        | metadata only; body purged after derivation | metadata only          |

- User-configured sensitivity patterns (regex / sender domain / keyword) stored in a config file, applied at ingest.
- The classifier may mark uncertain cases as `sensitive` (Rule-Ω-style: when in doubt, more cautious).
- Chat input redactor (Rule F) is expanded: when the user pastes sensitive-looking content into chat, the response is routed according to the inferred sensitivity tier.

### 🔒 Rule R — Notification Discipline

Every chat message from MailBot is categorized by urgency tier with strict delivery rules.

- **Urgent — push immediately:**
  - Tier 3 authorization requests (with deadline; auto-decline after N minutes)
  - Anomaly / runaway-loop / kill-switch events
  - Budget-cap breach entering degraded mode
  - Failed sync >1 hour

- **Important — batched into daily digest (e.g. 08:00):**
  - Tier 2 batch approval requests
  - Weekly drift report
  - Production-sample labeling requests (Rule L)

- **Informational — pull-only (user asks):**
  - Cost / spend dashboard (`/cost`)
  - Classification stats
  - Cache hit rates
  - Any "check when you feel like it" data

- **Silent — log-only:**
  - Routine classifications
  - Cache warmer pings
  - Normal escalations within rate limits
  - Sync events

**Anti-fatigue rules:**

- **Quiet hours:** no non-urgent messages 22:00–08:00 (user's timezone)
- **Digest dedup:** same-kind notification firing 5+ times in an hour collapses into one
- **Notification mute:** `/mute <category>` silences a category until `/unmute`
- **Trust signal:** if user doesn't reply to a Tier 3 auth request within N minutes, MailBot **does not re-send** — records auto-decline, moves on
- **Self-monitoring:** MailBot tracks user response rate to its messages. If response rate drops below 30% for a week, sends ONE "I'm becoming noisy" reflection message offering self-tuning, then goes further quiet until user engages

### Phase 3 deliverables (added to Phase 4 list)

- `router/lanes.py` — interactive vs batch lane separation
- `router/limits.py` — per-task rate limits, loop detection, kill-switch
- `router/cache_warmer.py` — Anthropic cache keep-warm pinger
- `router/anomaly.py` — call-volume baseline + alerting
- `eval/sampler.py` — weekly production-call sampler for human review
- `eval/drift_report.py` — distribution drift detector
- `eval/shadow_runner.py` — shadow-mode prompt rollout machinery
- Schema additions: `cache_hit_rate` derived metric; `draft_edits` table (original, sent, edit_distance); `production_samples` queue for human labeling
- Chat commands: `/pause`, `/resume`, `/label <recent>`, `/drift_report`
- Cron: 4-min ingest cadence (not 15-min); weekly sampler; weekly drift report

## Phase 2 (trimmed) — Initial Policy Draft

**Artifact:** [policy-v0.yaml](policy-v0.yaml)

The draft applies **Rule Ω rigorously**: every task defaults to `qwen-3b` unless there's a defensible a-priori reason to escalate, and every escalation is annotated with a **DEMOTION HYPOTHESIS** that the benchmark system will validate or refute.

### Tier distribution (starting positions)

- **Opus (premium) — 3 tasks:** `draft_reply`, `tone_style_mirror`, `user_model_refresh`
- **Haiku (cheap) — 8 tasks:** `action_extraction`, `importance_scoring`, `intent_parsing_chat`, `reference_resolution`, `subscription_audit`, `bulk_action_proposals`, `summarize_long_thread`, plus serving as escalation target for several 3B tasks
- **qwen-3b (free) — 14 tasks:** all ingest pipeline, all background/cron, simple chat, sensitivity classification (Rule Q: local-only by definition)
- **Embedding-only — 1 task:** `embedding` (bge-small-local)

## Deployment & Hermes Integration (Rules S–X)

The local-dev → VPS-prod transition is a first-class concern. The Hermes Agent docs were read carefully (Docker, architecture, programmatic integration, provider routing, fallback providers, cron, adding tools, personality) and the design adjusts to use Hermes-native primitives wherever possible. The 19 prior rules all still apply; they are now implemented atop Hermes primitives instead of reinvented.

### 🔒 Rule S — Dev-Prod Parity via Containers

> Both dev and prod run the same Docker images via `docker compose`. No "works on my machine" path. The local Windows laptop hosts the same Linux containers the Hostinger VPS will run, only the volume bind paths and `.env` values differ.

### 🔒 Rule T — Deployment is a Single Command

> Going from "code change committed" to "running on VPS" is one command (`make deploy` or `./scripts/deploy.sh`). No multi-step procedures. The deploy script handles: image build (or pull), `docker save`+`scp`+`docker load` (option-1 distribution), restart in dependency order (ollama → mailbot-api → mailbot-hermes), health check.

### 🔒 Rule U — Secrets Never Travel Through Source Control

> `.env` is never committed. `.env.example` IS committed (all keys, no values, with comments). `.gitignore` blocks `.env`, `*.key`, `*.pem`. A `check_env.py` startup script refuses to start if any required key is missing. On VPS, `.env` is created once during setup, mode 0600, owned by service user. Backups exclude it.

### 🔒 Rule V — Data Survives the Container

> Containers are disposable. All state lives on named volumes mounted from the VPS host: `mailbot_db` (SQLite), `mailbot_ollama` (pre-pulled models), `mailbot_hermes_data` (`/opt/data` = SOUL, AGENTS, config, sessions, memory, cron jobs), `mailbot_logs`. `docker compose down && docker compose up` is a non-event.

### 🔒 Rule W — Observability From Day One on VPS

> The VPS deployment includes: structured JSON logs to stdout (captured by Docker), `/health` and `/v1/health` endpoints on mailbot-api, a `mailbot` CLI installed on VPS exposing `mailbot status` (DB last-sync, queue depth, today's API spend, last 5 router_calls errors), `mailbot logs`, `mailbot pause`, `mailbot resume`. SSH-in-and-know-in-10-seconds bar.

### 🔒 Rule X — Hermes-Native Integration (NEW)

> MailBot uses Hermes's native primitives wherever they exist:
>
> - **Chat UI** → Hermes Discord adapter (`gateway`). No custom UI built.
> - **Scheduling** → Hermes `cron`. The Outlook sync runs as a `no_agent=True` script-only cron job — zero LLM tokens spent on ingest. The sync script uses the `wakeAgent: false` gate to skip waking the agent on empty syncs.
> - **Memory** → Hermes persistent memory + Honcho.
> - **Resilience** → Hermes `fallback_providers` configured with direct Anthropic as the safety net if our Router is down.
> - **Personality** → `SOUL.md` carries MailBot's identity (defender posture, conservative bias on destructive actions). `AGENTS.md` carries operational rules (Rules J/N/P/R behavior).
> - **Tool integration → MCP.** Our verb API exposes an **MCP server**. Hermes connects as an MCP client. This is the chosen integration path (over Hermes plugin or HTTP-via-skill).
> - **Router as primary provider:** mailbot-api exposes an OpenAI-compatible `/v1/chat/completions` endpoint. Hermes is configured with `model: { provider: custom, base_url: http://mailbot-api:8000/v1 }`. Hermes's auxiliary tasks (compression, title generation, etc.) ALSO point at the same endpoint — so Rule Ω extends to Hermes's internal work, not just our verbs.
> - **What we do NOT reimplement:** chat UI, scheduler, memory store, secret management UI, fallback retry loops, session persistence, prompt caching primitives, context compression. All present in Hermes.

### Deployment architecture (committed)

```text
┌───────── VPS (Hostinger KVM 2, 8 GB / 2 vCPU) ─────────┐
│                                                          │
│  Docker network: mailbot-net                            │
│                                                          │
│  Container: mailbot-hermes  (nousresearch/hermes-agent) │
│    Volume /opt/data:                                    │
│      .env, config.yaml, SOUL.md, AGENTS.md              │
│      skills/mailbot/SKILL.md                            │
│      cron/jobs.json, sessions/, memories/               │
│    Gateway: Discord adapter                             │
│    Provider config: custom → http://mailbot-api:8000/v1 │
│                                                          │
│  Container: mailbot-api  (our Python + MCP + Router)    │
│    Endpoints:                                           │
│      POST /v1/chat/completions  (Hermes's LLM provider) │
│      POST /v1/embeddings                                │
│      GET  /health, /v1/health                           │
│      MCP server (Hermes connects as MCP client)         │
│    Internal:                                            │
│      Router (policy.yaml, budget, router_calls log)     │
│      Verb library (find_emails, hydrate_email, …)       │
│      Sync worker (called by Hermes cron, no_agent=True) │
│      pending_actions queue drainer                      │
│    Holds: ANTHROPIC_API_KEY (Rule F.1)                  │
│    Volume /data: SQLite DB, logs                        │
│                                                          │
│  Container: ollama  (ollama/ollama)                     │
│    Pre-pulled: qwen2.5:3b-instruct-q4_K_M               │
│                nomic-embed-text                         │
│    Volume /root/.ollama: model files                    │
└──────────────────────────────────────────────────────────┘
```

### Hermes primitives we are explicitly using

| Hermes feature       | Our use                                                                                       |
| -------------------- | --------------------------------------------------------------------------------------------- |
| Discord gateway      | Chat UI for the user                                                                          |
| `cron` (no_agent)    | Outlook sync (script-only, zero LLM cost)                                                     |
| `cron` (with agent)  | Daily digest, weekly drift report, weekly eval-sampling prompts                               |
| `wakeAgent: false`   | Sync script suppresses agent wake when no new emails (Rule N: anti-loop / cost protection)    |
| `context_from`       | Chain sync → classify → digest cron jobs                                                      |
| `enabled_toolsets`   | Per-cron-job toolset narrowing (cost control)                                                 |
| `fallback_providers` | Direct Anthropic safety net if our Router is down                                             |
| Persistent memory    | Adam's preferences, user model, learned senders                                               |
| SOUL.md              | MailBot identity (defender, conservative, asks before destructive actions)                    |
| AGENTS.md            | Operational rules (verbs, hydration, authorization tiers, notification tiers)                 |
| MCP server (us)      | Our verb library exposed to Hermes via Model Context Protocol                                 |
| Prompt caching       | Built-in (we configure cacheable system blocks in our Router)                                 |
| Context compression  | Built-in (auxiliary.compression → pointed at our Router → Qwen)                               |

### Deployment deliverables (added to Phase 4)

- `docker/Dockerfile.mailbot-api` — Python + MCP + Router + sync worker
- `docker-compose.yml` — production stack (3 services + network + volumes)
- `docker-compose.override.yml` — local dev overrides (source bind-mount, dev ports)
- `.env.example` — DISCORD_BOT_TOKEN, ANTHROPIC_API_KEY, OUTLOOK_*, MAILBOT_DB_PATH, OLLAMA_URL, MAILBOT_ROUTER_KEY
- `.dockerignore`, `.gitignore` — block `.env`, `__pycache__`, build artifacts
- `Makefile` — `make build`, `make deploy`, `make logs`, `make status`, `make local`, `make backup`
- `scripts/setup_vps.sh` — one-time VPS bootstrap (Docker install, user, volumes, perms)
- `scripts/deploy.sh` — `docker save` + `scp` + `docker load` + rolling restart
- `scripts/check_env.py` — startup env-var validation
- `scripts/backup.sh` / `scripts/restore.sh` — SQLite dump + config archive
- `scripts/mailbot` — CLI installed on VPS (`status`, `logs`, `pause`, `resume`)
- `hermes-config/config.yaml` — Hermes config with `provider: custom`, fallback_providers, auxiliary task routing
- `hermes-config/SOUL.md` — MailBot persona
- `hermes-config/AGENTS.md` — MailBot operational rules
- `hermes-config/skills/mailbot/SKILL.md` — how MailBot uses its verbs
- `hermes-config/cron/jobs.json` — initial cron jobs (sync, digest, drift, sampling)
- `mailbot_api/mcp_server.py` — MCP server exposing verbs to Hermes

## Phase 4 — Build-Order Checklist

**Artifact:** [phase-4-build-order.md](phase-4-build-order.md) — full 6-milestone, ~80-task plan with T-shirt-size estimates, explicit dependencies, MVP cuts, verification criteria, and "things that will bite you" callouts.

### Six milestones

| # | Milestone                       | Goal                                                  | MVP? |
| - | ------------------------------- | ----------------------------------------------------- | ---- |
| 1 | Foundation & scaffold           | Repo, Docker, SQLite schema, Outlook sync (no LLM)    | must |
| 2 | Router & local LLM              | Ollama + Qwen + `/v1/chat/completions` + router_calls | must |
| 3 | Anthropic tier + budget         | 3-tier routing, budget guards, cache, sensitivity     | must |
| 4 | Eval system                     | Corpus + runner + scorer + first calibration          | must |
| 5 | Hermes integration (MVP line)   | MCP verbs, SOUL/AGENTS, Discord, cron sync            | must |
| 6 | VPS deployment                  | Hostinger deploy, backups, observability, 1-week run  | must |

**MVP line:** end of M5 — that's when MailBot becomes usable.
**Real launch:** M6.7 — first production deploy + 1-week unattended run.
**Estimated:** ~10 weeks part-time to MVP, +2 weeks to launch.

## Session Summary

This brainstorming session produced:

- **21 architectural rules** (Ω, A–X) consolidating all design decisions with explicit rationale
- **A policy starter artifact:** [policy-v0.yaml](policy-v0.yaml) — every routing decision with demotion/promotion hypotheses to test
- **A build-order plan:** [phase-4-build-order.md](phase-4-build-order.md) — 6 milestones, ~80 tasks
- **A deployment architecture** — 3-container Docker stack on Hostinger KVM 2 (Hermes + mailbot-api + Ollama) with full Hermes-native primitive use (Discord, cron, MCP, memory, fallback_providers)
- **Cost discipline as a first-class system property** (Rule Ω + Router + benchmarks + 4-layer budget guards)
- **Safety as construction, not behavior** (Rule P tiers + Rule Q sensitivity + Rule R notifications + queued intents + cooling-off + per-action authorization)

The defining feature of this design: **Rule Ω** — never use a distant LLM if the local one can do the task; never use a high-grade distant LLM if a lower-grade one can do the task. Everything else flows from that principle.

Workflow status: **complete.**

Total: 26 distinct tasks (collapsed a few overlapping items from Phase 1's 34 — e.g. `summary_short` and `summarize_short_thread` are separate now; `intent_parsing` split into chat-interactive vs. background).

### Operational settings encoded in policy file

- **Budget:** `monthly_cap_usd=30`, `daily_warn=2`, `per_call_refusal=0.20`
- **Rate limits:** chat 60/hr, ingest 300/hr, escalations 20/hr
- **Anti-loop:** prompt-hash repeat window 10 calls / 5 min
- **Cache warmer:** every 4 min (cache TTL = 5 min, ingest cron aligned to 4 min)
- **Continuous eval:** weekly sampling + weekly drift report

### Calibration process built into the artifact

The policy file contains a **Calibration Process** section at the bottom that documents:

1. Build eval corpus v1 (~100 hand-labeled emails)
2. Run benchmark over all (task × model) combinations
3. Generate dashboard
4. For each Haiku/Opus row: test DEMOTION HYPOTHESIS — if 3B meets threshold, demote and bump prompt version
5. For each 3B row with `escalate=true`: monitor escalation rate after first week of prod data — if > 30%, the PROMOTION HYPOTHESIS won, bump default tier
6. Repeat at every prompt version change and quarterly

The file itself is the agent's cost-discipline artifact. Every change to it must be deliberate and evidence-backed.
