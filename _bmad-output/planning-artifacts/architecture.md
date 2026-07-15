---
stepsCompleted: [1, 2, 3, 4, 5, 6, 7, 8]
inputDocuments:
  - _bmad-output/planning-artifacts/prds/prd-MailBot-2026-05-31/prd.md
  - _bmad-output/planning-artifacts/prds/prd-MailBot-2026-05-31/addendum.md
  - _bmad-output/planning-artifacts/prds/prd-MailBot-2026-05-31/reconcile-policy-v0.md
  - _bmad-output/planning-artifacts/prds/prd-MailBot-2026-05-31/reconcile-brainstorming.md
  - _bmad-output/planning-artifacts/prds/prd-MailBot-2026-05-31/reconcile-build-order.md
  - _bmad-output/planning-artifacts/prds/prd-MailBot-2026-05-31/review-rubric.md
  - _bmad-output/brainstorming/brainstorming-session-2026-05-31-1430.md
workflowType: 'architecture'
project_name: 'MailBot'
user_name: 'Adam'
date: '2026-05-31'
lastStep: 8
status: 'complete'
completedAt: '2026-05-31'
---

# MailBot — Architecture Decision Document

_This document builds collaboratively through step-by-step discovery. Sections are appended as we work through each architectural decision together._

## Project Context Analysis

### Requirements Overview

**Functional Requirements:** 62 FRs across 8 capability areas (F1–F8).

- **F1 Outlook Sync (FR-1.1..7)** — cron-pull from Microsoft Graph every 4 min, delta-only, soft-delete preservation, idempotent re-runs, sync-health alerts, headless OAuth via copied refresh token, `has_attachments` boolean only at v1.
- **F2 Ingest Pipeline (FR-2.1..7)** — derived-field columns + companion metadata (`*_prompt_v/_conf/_model/_at`), idempotency keyed on `sha256(body)+prompt_v+model+task`, fixed pipeline ordering (sensitivity first — hard Router-enforced invariant), 100-batch chunking with backpressure at queue > 500, local-only sensitivity classification, opt-in targeted re-derivation, sender + thread upserts with one-line `sender_reputation_summary` cached forever.
- **F3 Router & Tiered LLM (FR-3.1..10)** — single source of truth for every LLM call (Rule I). 3-tier model stack (Qwen 3B / Haiku 4.5 / Opus 4.7), single agent verb `ask_router`, static `policy.yaml` with per-call override, layered failure handling (timeout → schema → retry → escalate → structured error), lane separation (interactive preempts batch), Anthropic prompt caching with cache warmer, SQL-backed response cache, anti-loop kill-switch, full audit log in `router_calls`. Hermes auxiliary tasks (compression, title generation) ALSO route through here.
- **F4 Conversational Control (FR-4.1..8)** — Discord-only UI, Hermes adapter as gateway, natural-language verb-backed queries within p95 ≤ 5s, reference resolution gated by ≥ 90% accuracy on a dedicated eval slice, full draft-reply flow (Opus → show → edit/approve → cooling-off → send), slash commands (`/cost`, `/pause`, `/resume`, `/cancel`, `/mute`, `/label`), defender persona, chat-input redactor.
- **F5 Authorized Actions (FR-5.1..7)** — 4-tier authorization model enforced by the verb API (not the agent), scoped time-bounded grants minted in chat, 60s cooling-off on sends, hard 20-send/day cap, queued-intent write-back with second auth check at drain, per-session confirmation token for sensitive-to-API escalation.
- **F6 Cost Governance (FR-6.1..7)** — 4-layer budget guard: per-call `max_tokens_out` cap, daily $2 soft warn, monthly $30 hard cap → degraded mode (demotion chain Opus→Haiku→Qwen), per-call $0.20 refusal threshold. Hourly anomaly detection, default-cheapest with annotated DEMOTION HYPOTHESIS for every escalation, `/cost` transparency.
- **F7 Observability & Trust (FR-7.1..7)** — `mailbot status` CLI returning full picture in 10s, structured JSON logs, 4 notification tiers (urgent / important / informational / silent), quiet hours 22:00–08:00, anti-fatigue (dedup, mute, self-reflection at < 30% response rate, urgent-only posture until any slash command), daily 08:00 digest from pre-computed projections.
- **F8 Eval & Calibration (FR-8.1..7)** — frozen 100-email corpus across 8 task families, `force_model`-driven benchmark runner with cost confirmation gate, objective + subjective scoring (20 anchor examples + auto-eval calibration), report with Pareto frontier and DEMOTE/PROMOTE suggestions, weekly production sampling growing the corpus, weekly KL-divergence drift report, shadow-mode rollout for subjective prompt versions.

**Non-Functional Requirements:** 24 NFRs across 6 categories.

- **Privacy (NFR-PRIV-0..4)** — VPS itself is the trust boundary; 3-tier sensitivity (normal/sensitive/confidential) with strict routing/memory/logging implications per tier; user-configurable forcing patterns; chat-input redactor on all input/export paths.
- **Security (NFR-SEC-1..6)** — `.env` only with `chmod 600`; Anthropic key isolated to `mailbot-api` process; filesystem denylist denies agent access to secret paths; sanitized error returns; `get_secret(name)` indirection; backups exclude secrets.
- **Reliability/Ops (NFR-OPS-1..6)** — Docker dev-prod parity; single-command deploy; state on named volumes; `/health` endpoints; nightly backups (14 daily + 8 weekly); Hermes `fallback_providers` as emergency safety net.
- **Performance (NFR-PERF-1..4)** — chat p95 ≤ 5s (Qwen/Haiku); Opus drafts p95 ≤ 15s; 4-min sync cadence aligned to 5-min Anthropic cache TTL; Qwen 3B p95 ≤ 5s on 2-vCPU CPU-only; 100 emails/batch ingest, backpressure at 500.
- **Hardware (NFR-HW-1..3)** — Hostinger KVM 2 (2 vCPU / 8 GB / no GPU); 4.5–5.5 GB RAM budget for LLM after OS+SQL+Python+Hermes; no 7B fallback at v1.
- **Persona/Voice (NFR-PERSONA-1..3)** — defender (not assistant); 4 behavioral anti-patterns enumerated; operational rules manifested in `SOUL.md` + `AGENTS.md`.

**Scale & Complexity:**

- Primary domain: **Python backend service stack + local LLM serving + Hermes agent runtime, containerized.**
- Complexity level: **medium-to-high** — single-user keeps data model simple; cost discipline + tier authorization + sensitivity routing + first-class evals stack significant cross-cutting machinery.
- Estimated architectural components: **3 containers** (`mailbot-hermes`, `mailbot-api`, `ollama`), ~8 internal modules inside `mailbot-api` (Router, verb library, sync worker, pending-actions drainer, ingest pipeline, MCP server, HTTP API, eval/benchmark runner), 1 SQLite DB with ~10 core tables.

### Technical Constraints & Dependencies

**Locked constraints (§8 of PRD):**

- No GPU on VPS — single-3B-model commitment, no 7B fallback.
- $30/month API budget — drives Rule Ω, 4-layer budget guard, default-cheapest policy.
- Cron-pull only (no webhooks) — no public endpoint, freshness in minutes.
- Single user — single-grantor authorization model, single notification surface, single memory subject.
- Anthropic direct (no OpenRouter) — simpler accounting.
- SQLite (no Postgres) — single-host system of record.

**External dependencies:**

- Microsoft Graph API (Outlook delta sync, OAuth refresh-token-copy auth).
- Anthropic API (Claude Haiku 4.5 and Opus 4.7).
- Discord (bot gateway via Hermes).
- Hermes Agent runtime (`nousresearch/hermes-agent`) — Discord gateway, cron, memory, fallback providers, prompt caching, context compression, MCP client.
- Ollama (model serving for Qwen 2.5 3B Instruct Q4_K_M + bge-small/nomic-embed-text).

**Internal contracts (committed):**

- All LLM calls flow through the Router (Rule I) — no direct provider calls anywhere, including the eval runner.
- The agent's only data window is the verb API (Rule C) — no raw SQL, no Graph access.
- The agent never holds the Anthropic API key (Rule F.1).
- Sensitivity-class precondition is Router-enforced (FR-2.3 invariant): no Router call for any other task on `email_id` until `sensitivity_at IS NOT NULL`.

### Cross-Cutting Concerns Identified

1. **Cost discipline (Rule Ω)** — every Router decision, every policy.yaml entry, every Hermes aux task, every prompt design, every feature scoping.
2. **Sensitivity-aware routing (Rule Q)** — Router precondition layer, ingest pipeline ordering, `sensitivity_patterns.yaml`, per-session token handshake.
3. **Authorization tiers (Rule P)** — verb API contracts, pending_actions queue, drain worker, slash-commands, cooling-off, 20/day cap.
4. **Idempotency & caching (Rules A, K, M)** — derived-field columns, ingest idempotency keys, response cache, Anthropic prompt cache.
5. **Observability (Rule W)** — structured JSON logging, `router_calls`, `mailbot status` CLI, health endpoints, anomaly/drift detection.
6. **Dev-prod parity (Rules S/T/V)** — Docker stack, named volumes, single-command deploy, env-var handling, `restore.sh` flow.

### Open architectural questions surfaced

- **OQ-2 (PRD §9)** — Sync conflict resolution: what happens when an email is moved/deleted between a sync and a `pending_actions` drain?
- **Sensitivity override handshake mechanism** — header vs. chat token, persistence/scope/single-use semantics.
- **Hermes aux-task routing enforcement** — config-only or process-level network policy?
- **Daily digest composer** — agent-orchestrated (calls `list_unread()`) vs. dedicated assembler verb?
- **Write-back retry contract** — 3 retries + exponential backoff → `failed`, currently unstated.
- **Action-type roster** — tiers named but specific action types (mark_read, archive, etc.) not enumerated per tier.

## Starter Template Evaluation

### Primary Technology Domain

Python backend service stack + local LLM serving (Ollama) + MCP server + containerized agent runtime (Hermes), all running as a 3-container Docker Compose stack on a single Hostinger KVM 2 VPS. Not a web/SPA/mobile project — the starter-template ecosystem (Next.js, T3, RedwoodJS, Vite) doesn't fit this shape.

### Starter Options Considered

1. **FastAPI cookiecutter (e.g., `fastapi-template`, `full-stack-fastapi-template`)** — provides project skeleton, ruff/black, pytest, Dockerfile. Rejected: assumes a generic CRUD web service; MailBot's 3-container architecture, MCP server, and Router-as-cost-discipline-center are too specific. More time deleting assumptions than typing the right ones.
2. **MCP Python SDK reference server** — useful as _reading material_ during Build-order M5 Hermes integration, but it's a single MCP server example, not the shell of an entire production service.
3. **Hermes skill scaffold** — relevant for the `hermes-config/skills/mailbot/SKILL.md` artifact specifically, but does not shape the `mailbot-api` service.
4. **Hand-bootstrap (selected)** — the 3-container architecture diagram in addendum A1 + Build-order M1's deliverables list IS the starter. Matches the "Boring technology for stability" principle and Build-order M1's explicit plan.

### Selected Starter: Hand-bootstrap (no template generator)

**Rationale for Selection:**

- MailBot's constraints (single-3B-local, MCP server, Router-as-cost-discipline-center, sensitivity-aware routing, four-tier authorization, Hermes-native primitives) are too specific for any general-purpose starter. Every starter would require more deletion than addition.
- Build-order M1 already plans the bootstrap as task #1.1; we document it here.
- "Boring technology for stability" — `pip + venv`, FastAPI, SQLite, Docker Compose are all proven defaults for the target shape.

### Foundational Dependency Versions (verified May 2026)

| Component | Choice | Version | Source |
| --- | --- | --- | --- |
| Python | CPython | 3.12 baseline | recommended 2026 baseline (PEP 695, perf) |
| Package manager | `pip` + `venv` | stdlib | user preference |
| HTTP framework | FastAPI | 0.136.1 (2026-04-23) | [release notes](https://fastapi.tiangolo.com/release-notes/) |
| ASGI server | uvicorn | latest | FastAPI default |
| Data validation | Pydantic v2 | bundled with FastAPI | |
| MCP server | `mcp` (Python SDK) | 1.27.2 | [PyPI](https://pypi.org/project/mcp/) — Anthropic-maintained |
| Local LLM client | `ollama` (Python) | 0.6.2 (2026-04-29) | [PyPI](https://pypi.org/project/ollama/) |
| Anthropic SDK | `anthropic` (Python) | 0.105.2 (2026-05-29) | [PyPI](https://pypi.org/project/anthropic/) |
| Database | SQLite (WAL) | stdlib `sqlite3` | locked by PRD |
| Schema mgmt | plain SQL migration files | N/A | Alembic deferred |
| LLM serving | Ollama (Docker) | `ollama/ollama:latest` | pinned in compose |
| Agent runtime | Hermes (Docker) | `nousresearch/hermes-agent:latest` | per addendum A1 |
| Containers | Docker Compose v2 | latest | 3 services, named volumes |
| Test framework | pytest + pytest-asyncio | latest | |
| Lint / format | ruff | latest | replaces black+isort+flake8 |
| Type check | mypy (or pyright) | latest | strict mode in CI |

### Initialization Sequence

There is no single CLI command — this is the hand-bootstrap that becomes Build-order M1.1:

```bash
# 1. Repo + venv
mkdir mailbot && cd mailbot
git init
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\Activate.ps1 on Windows

# 2. Pin runtime deps
cat > requirements.txt <<'EOF'
fastapi==0.136.1
uvicorn[standard]
pydantic>=2
anthropic==0.105.2
ollama==0.6.2
mcp==1.27.2
httpx
pyyaml
pytest
pytest-asyncio
ruff
mypy
EOF
pip install -r requirements.txt

# 3. Scaffold the package layout (see below)
# 4. Drop in docker-compose.yml + Dockerfile.mailbot-api (addendum A1 diagram)
# 5. Drop in .env.example, .gitignore, Makefile
# 6. Smoke test: docker compose up; curl localhost:8000/health
```

### Architectural Decisions Provided by the Bootstrap

**Language & Runtime:**

- Python 3.12 baseline; `pip + venv` for dependency management; `requirements.txt` (consider `requirements.in` + `pip-compile` if pin churn becomes painful).

**HTTP framework:**

- FastAPI 0.136.1 + uvicorn. Exposes `/v1/chat/completions`, `/v1/embeddings`, `/health`, `/v1/health` (addendum A1). Pydantic v2 models for every verb input/output.

**MCP server:**

- `mcp` Python SDK 1.27.2, `FastMCP` decorator interface. Each verb in `mailbot_api/verbs/` is decorated as an MCP tool. Hermes connects as MCP client.

**LLM clients (Router-internal only — Rule I):**

- `ollama` 0.6.2 for local (Qwen 3B + bge-small/nomic-embed-text).
- `anthropic` 0.105.2 for Haiku 4.5 + Opus 4.7, with `cache_control={"type": "ephemeral"}` on the SYSTEM block of every call (Rule M, FR-3.6).
- Both isolated behind a common `ModelAdapter` interface in `router/models.py` so a third provider is a config change, not a refactor.

**Data layer:**

- SQLite WAL mode, single file at `MAILBOT_DB_PATH`. Plain SQL migration files in `mailbot_api/db/migrations/` numbered `001_*.sql`, applied at startup if not yet recorded in a `_migrations` table. Alembic deferred until/unless migration churn justifies it.

**Code organization — `mailbot-api` package layout:**

```text
mailbot/
  mailbot_api/
    __init__.py
    main.py                       # FastAPI app, /v1 endpoints, /health
    config.py                     # env vars, paths, get_secret() indirection
    db/
      schema.sql                  # initial schema
      migrations/                 # 001_*.sql, 002_*.sql, ...
      connection.py               # WAL mode, connection pool
    router/
      __init__.py
      router.py                   # the Router itself (Rule I center)
      policy.py                   # policy.yaml loader + lookup
      pricing.py                  # token -> USD per model
      budget.py                   # daily/monthly tracking, degraded mode
      lanes.py                    # interactive vs batch
      limits.py                   # rate limits, anti-loop, kill-switch
      cache_warmer.py             # Anthropic prompt cache pinger
      response_cache.py           # SQL-backed hash(prompt+model+temp)
      errors.py                   # RouterResult, RouterError, stable codes
      models.py                   # ModelAdapter, OllamaAdapter, AnthropicAdapter
    prompts/
      __init__.py                 # registry: (task_type, version) -> module
      coarse_class/v1.py
      sensitivity_class/v1.py
      draft_reply/v1.py
      ...                          # vN.py exports VERSION, SYSTEM, USER_TEMPLATE, OUTPUT_SCHEMA
    verbs/
      __init__.py
      find_emails.py
      hydrate_email.py
      get_thread.py
      list_unread.py
      count_emails.py
      get_sender_summary.py
      propose_action.py
      apply_action.py
      ask_router.py
    mcp_server.py                 # FastMCP server exposing verbs as tools
    sync/
      graph_client.py             # Microsoft Graph wrapper
      sync_worker.py              # cron-callable, no_agent=True
    ingest/
      pipeline.py                 # sensitivity -> coarse -> ... -> embedding
      idempotency.py              # sha256(body)+prompt_v+model+task
    actions/
      drainer.py                  # pending_actions queue worker, second auth check
      authorization.py            # tier check, grant cache, session token
      cooling_off.py              # pending_send window + /cancel
    sensitivity/
      classifier.py
      patterns.py                 # loads sensitivity_patterns.yaml
    observability/
      logging.py                  # structured JSON to stdout
      audit.py                    # router_calls writes
      anomaly.py                  # hourly call-volume baseline
    notifications/
      tiers.py                    # urgent / important / informational / silent
      digest.py                   # daily 08:00 digest assembler
  evals/
    email_corpus_v1.jsonl
    scoring_rubrics/
    anchors/
  benchmark/
    runner.py
    scorer.py
    report.py
  scripts/
    mailbot                       # CLI: status / logs / pause / resume / sync-now
    setup_vps.sh
    deploy.sh
    backup.sh
    restore.sh
    check_env.py
  hermes-config/
    config.yaml
    SOUL.md
    AGENTS.md
    skills/mailbot/SKILL.md
    cron/jobs.json
  docker/
    Dockerfile.mailbot-api
  router/
    policy.yaml                   # source of truth - Rule I
    sensitivity_patterns.yaml
  docker-compose.yml
  docker-compose.override.yml     # local dev overrides
  .env.example
  .gitignore
  .dockerignore
  Makefile
  requirements.txt
  pyproject.toml                  # ruff, mypy, pytest config
  README.md
  tests/
    unit/
    integration/
```

**Build tooling:**

- `Makefile` targets: `build`, `deploy`, `logs`, `status`, `local`, `backup`, `test`, `lint`. Single entrypoint per developer task (Rule T).

**Testing framework:**

- pytest + pytest-asyncio. Unit tests on Router/policy/budget/sensitivity/verbs. Integration tests on the full FastAPI app via `httpx.AsyncClient`. The benchmark runner (FR-8.2) is separate from pytest — it's a production tool that uses the Router with `force_model`.

**Code organization patterns:**

- Each `mailbot_api/<area>/` package owns one bounded responsibility.
- The Router is the only code that can call Ollama or Anthropic adapters (Rule I, NFR-SEC-2).
- Verbs are the only code that touches SQL on behalf of the agent (Rule C).
- Sync code is the only code that touches Microsoft Graph (Rule B).
- Pydantic models on every boundary (verb in/out, prompt OUTPUT_SCHEMA, FastAPI request/response).
- Errors-as-data (`RouterResult` / `RouterError` with stable codes), never raw exceptions to the agent (Rule F).

**Development experience:**

- `docker-compose.override.yml` bind-mounts source so dev iteration doesn't require image rebuilds.
- Hot reload via `uvicorn --reload` in dev (not prod).
- `.env.example` lists every required key with comments; `scripts/check_env.py` refuses to start the service if any required key is missing (Rule U).
- Structured JSON logging from day one (Rule W).

**Note:** Project initialization using this sequence should be the first implementation story (Build-order M1.1 — Repo scaffold).

## Core Architectural Decisions

### Decision Priority Analysis

**Already decided by PRD / Addendum / Brainstorm / Starter (recorded, not re-debated):**

- Data architecture: SQLite WAL, derived-field columns + companion metadata, idempotency keys, soft-delete preservation, named volumes for persistence. (PRD §6, addendum A1, FR-2.x)
- Security: Anthropic API key isolated to `mailbot-api` process; `.env` 0600; filesystem denylist on secret paths; `get_secret(name)` indirection; sanitized error returns. (NFR-SEC-1..6, Rule F)
- Authorization: 4-tier authorization model (Tier 0/1/2/3); scoped time-bounded grants; 60s cooling-off on sends; 20/day send cap; queued-intent write-back with second auth check at drain time. (F5)
- API style: OpenAI-compatible `/v1/chat/completions` + `/v1/embeddings` (FastAPI); MCP server for verb tools (FastMCP); structured `RouterResult`/`RouterError` error-as-data; Pydantic on every boundary. (addendum A1, A5, FR-3.4)
- Frontend: N/A — Discord is the UI via Hermes adapter. (FR-4.1)
- Infrastructure: 3-container Docker Compose stack (`mailbot-hermes` + `mailbot-api` + `ollama`) on Hostinger KVM 2; named volumes; single-command `make deploy`; `/health` endpoints; nightly backups 14d+8w; Hermes `fallback_providers` emergency safety net; structured JSON logging; `mailbot status` CLI. (NFR-OPS-1..6, Rules S/T/V/W)

**Critical decisions made in this section:**

- D1 / D12 — Sensitivity-override handshake mechanism + token storage
- D2 / D10 / D11 — Hermes aux-task routing enforcement + lane scheduling + policy reload
- D4 / D5 / D9 — Sync conflict resolution + write-back retry contract + OAuth refresh-token rotation
- D6 — Action-type roster per authorization tier
- D3 / D7 / D8 / D13 / D14 — Daily digest composer + concurrency model + SQLite contention + cron ownership + DB access pattern

**Deferred decisions (post-MVP backlog):**

- `pause_sender` action (defender-flavor Tier-2 primitive; defer until post-MVP demand)
- Cascading routing per task (Rule N future-state; M6.8)
- Per-lane WRR scheduling instead of strict priority (only if batch starvation bites)
- Migration to SQLAlchemy or `aiosqlite` (only if raw SQL churn becomes painful)

### Privacy Mechanism (D1 + D12)

**Sensitivity-override handshake mechanism (D1):**

- Inline `confirmation_token` parameter on `ask_router(task_type, content, force_model=None, confirmation_token=None, max_cost_usd=None) -> RouterResult`. The Router precondition layer checks the token against a server-side mint registry keyed by `(token, email_id, task_type)`; marks consumed on call; refuses sensitive-to-API calls without a valid token.
- Tokens are minted via an explicit `mint_sensitivity_token(email_id, task_type) -> token` Tier-0 verb. The mint verb gates on a recent in-chat user confirmation event recorded by Hermes (a `/confirm <email_id> <task_type>` slash command or natural-language affirmation that Hermes maps to the verb call). The mint event is logged structured-JSON; the consume event becomes a row write on `router_calls`.
- `confidential` emails admit no override — the verb refuses to mint, the Router refuses to consume, and no chat path exists to override.

**Session-token storage (D12):**

- In-memory dict in the `mailbot-api` worker process (the Router lives there), keyed by token string, with TTL eviction (default 10 min from mint).
- Tokens die on process restart by design — this forces re-confirmation, which is correct behavior.
- Audit trail lives on `router_calls` via two new columns: `sensitivity_grant_id` (nullable, present only when the call consumed a grant) and `sensitivity_grant_minted_at`. Mint events emit a structured log line; consume events become the row write.

**Rationale:** The token is a single-use, narrowly scoped capability — not a long-lived secret. The chat-input redactor (FR-4.7) already scrubs token-shaped strings from logs and memory exports. Explicit mint + inline consume gives clean provenance: every sensitive-to-API call has a one-to-one mint/consume audit pair. The mint-via-verb path keeps the authorship chain visible.

### Routing Discipline (D2 + D10 + D11)

**Hermes aux-task routing enforcement (D2):**

- **Config-only enforcement.** Hermes is configured with `provider.base_url = http://mailbot-api:8000/v1` and `auxiliary.compression.provider = custom`, `auxiliary.title_generation.provider = custom`. All Hermes-internal LLM work flows through the Router by configuration.
- **Drift detection** rather than network policy: `mailbot status` includes a "Hermes aux traffic last 24h" line; if zero aux calls are recorded from Hermes for ≥ 24h, raise an informational alert. The Router records `caller_origin` (`hermes-aux-compression`, `hermes-aux-title`, `verb-ask-router`, `benchmark-runner`, `cache-warmer`) on every `router_calls` row to make this trivially queryable.
- **Why not network policy:** blocking Hermes from `api.anthropic.com` would also break the `fallback_providers` emergency safety net (NFR-OPS-6), which is the one path that _should_ be able to bypass our Router. Defense-in-depth with a punched-through hole is bad design.

**Router lane scheduling (D10):**

- **Two asyncio queues, strict priority.** `interactive_q` (high) and `batch_q` (low). A single worker pool always drains `interactive_q` first; only pulls from `batch_q` when `interactive_q` is empty.
- **Rate limits enforced at enqueue.** Chat 60/hr, ingest 300/hr, escalations 20/hr — exceeded → immediate refusal with `RouterError(code="rate_limited")`.
- **Per-provider concurrency semaphore** (default 4 concurrent Anthropic calls) to avoid surprise 429s independent of lane priority.
- **Batch starvation is acceptable.** On 2 vCPU with bursty chat (≤ 60/hr) and steady ingest (every 5 min, 100/batch), interactive cannot saturate the worker pool for sustained periods. If WRR scheduling ever becomes necessary, it's a localized dequeue-function change.

**`policy.yaml` reload semantics (D11):**

- **File-watch hot-reload via `watchfiles`** with validation-or-no-swap. On change: re-read → validate against the `PolicyTable` Pydantic schema → atomic swap of the in-memory policy only on success. Invalid YAML or schema mismatch leaves the running policy in place and logs loudly.
- **Mid-call race acceptable:** each Router call captures its policy snapshot at dispatch, so in-flight calls finish under the pre-swap policy. `router_calls` records `prompt_version` and `model_chosen`, making the swap observable post-hoc.

### Sync ↔ Actions (D4 + D5 + D9)

**Sync conflict resolution (D4):**

- **Hybrid policy:** Tier-3 actions enforce strict ETag (`change_marker`) match at drain time — if state drifted, the user's authorization may no longer match intent, so refuse with `RouterError(code="state_drift_etag")` and notify urgently. Tier-1 and Tier-2 actions apply lenient rules per the action-type roster (see D6 cascading column `change_marker_required`).
- **Three lenient rules for Tier-1/2:**
  1. Target deleted (`emails.deleted_at IS NOT NULL`) → action moves to `status="failed"` with `failure_reason="target_deleted"`; silent log (Tier-1) or next digest (Tier-2); no urgent notification.
  2. Target moved but exists → execute (idempotent actions like `mark_read` are still valid).
  3. Target moved AND action is a folder-move → re-resolve target folder; execute if still semantically valid (target ≠ current), else log `failure_reason="state_drift_noop"`.
- **No Graph round-trip** to check existence — local `emails.deleted_at` (FR-1.3 soft-delete) is authoritative.

**Write-back retry contract (D5):**

- **Error-classified retry chain:** Graph 429/503/timeout → exponential backoff (1s, 4s, 16s), max 3 retries. Graph 4xx (non-429) → immediate `failed`, no retry. Graph 5xx (non-503) → 1 retry then `failed`. Network errors treated as transient.
- **Delta-token invalidation recovery:** `410 Gone` (synchronization reset per [delta-query-overview.md](../../docs/external/learn-microsoft-azure/pages/graph/delta-query-overview.md) § Synchronization reset) and `404` with body code `syncStateNotFound` (delta token evicted from Graph's internal cache per § Token duration) clear `sync_state.delta_link` and fire a one-shot urgent notification ("delta token reset — full resync in progress"); the next worker tick performs a fresh delta from scratch. Story 1-10 owns this handler.
- **Tier-3 circuit breaker:** failed Tier-3 sends consume the daily 20-send budget at terminal-fail, never silently. The `pending_actions.budget_consumed` boolean flips on either successful leave or terminal fail.
- **`status="failed"` rows stay in `pending_actions`** for audit and manual replay. `mailbot status` reports counts; `mailbot replay <action_id>` re-queues. No separate dead-letter table.
- **Failure notification tiers:** Tier-1 silent log; Tier-2 in next daily digest; Tier-3 urgent immediately.

**Access model:**

- MailBot uses **delegated access** via the OAuth 2.0 Authorization Code flow with the `offline_access` scope (required to receive a refresh token). App-only access was ruled out because the design uses the `/me` alias throughout — `/me` is delegated-only per Microsoft's [auth concepts](../../docs/external/learn-microsoft-azure/pages/graph/auth/auth-concepts.md).
- Tenant value depends on the target mailbox: `consumers` for personal Microsoft accounts (Outlook.com, Hotmail), the directory GUID for a single work/school tenant, `common` for mixed-mode apps. MailBot's primary target is personal — `consumers` is the default in `.env.example`.
- Required delegated permissions: `User.Read`, `Mail.Read`, `Mail.ReadWrite`, `Mail.Send`, `offline_access`.

**OAuth refresh-token rotation (D9):**

- **Bootstrap refresh token is minted via a one-time interactive browser flow on a dev machine** — see Story 1-9's `scripts/mint_refresh_token.py` and `docs/entra-app-registration.md`. The VPS itself is never a redirect URI target. The minted token is hand-copied into the VPS `.env`.
- **Rotated tokens persist to a new `oauth_state` SQLite table** with single row keyed by `provider="microsoft_graph"`. Columns: `refresh_token`, `access_token`, `access_expires_at`, `last_rotated_at`, `rotation_count`. The sync layer reads from `oauth_state` if present, falls back to `.env` only on first run.
- **`.env` becomes a bootstrap seed** — used once to populate the row, then `oauth_state` is the runtime source of truth. Documented explicitly in `docs/auth-recovery.md`.
- **Rotation events** emit a structured log line (info-tier). Rotation _failures_ (e.g., `invalid_grant`) escalate to urgent chat alert, picked up by FR-1.5's sync-health alarm if recovery takes > 1h.
- **Backups include `oauth_state`** automatically (NFR-OPS-5 already excludes only `.env`).

### Authorization Detail (D6)

**Action-type roster — authoritative table.** All action types in `mailbot_api/actions/types.py` as a single `ActionType` enum with a `tier_for(action_type)` lookup. The `propose_action(email_id, action_type, **payload)` verb consults this lookup at insert and refuses any agent-claimed tier override (FR-5.6 in code).

| Action type | Tier | Notes |
| --- | --- | --- |
| `read_sql`, `ask_router`, `generate_draft`, `send_chat_notification`, `write_derived_field` | 0 | Verb-level capabilities, not user-visible actions |
| `mark_read` | 1 | Auto-revertible; idempotent |
| `mark_unread` | 1 | Auto-revertible |
| `add_local_category` | 1 | Local SQL only, not synced to Outlook |
| `remove_local_category` | 1 | Local SQL only |
| `move_to_triage_folder` | 1 | Single `MailBot-Triage` folder only |
| `archive` | 2 | Batch approval via grant |
| `mark_junk` | 2 | aka `mark_spam` |
| `move_to_user_folder` | 2 | Any non-Triage folder |
| `unsubscribe` | 2 | Form submission or list-unsubscribe header |
| `move_to_inbox` | 2 | Reverse of archive |
| `delete` | 3 | Per-action confirmation; ETag-strict |
| `send_reply` | 3 | Cooling-off + 20/day budget |
| `send_new_email` | 3 | Cooling-off + 20/day budget |
| `send_forward` | 3 | Cooling-off + 20/day budget |
| `reply_to_inactive_thread` | 3 | Inactive > N days; same budget as send |
| `modify_inbox_rule` | 3 | Server-side rules |
| `modify_outlook_filter` | 3 | Server-side filters |
| `touch_delegated_mailbox` | 3 | Shared/delegated accounts |

**Cross-cutting properties per action type:**

- `reversibility_window_hours` — 24h for Tier-1 actions (pre-state snapshot in `action_history` enables `mailbot revert <action_id>`); not auto-revertible for Tier-2/3.
- `change_marker_required` — true for Tier-3 only (strict ETag match per D4); false for Tier-1/2 (lenient policy applies).
- `budget_against` — `daily_send_cap_20` for all `send_*` and `reply_to_inactive_thread`; null otherwise.
- `requires_sensitivity_token` — true for any Tier-2/3 action that generates outbound content from a `sensitive`-classified email; `confidential` emails admit no Tier-2/3 outbound action at all.

**Grant model (FR-5.2 made concrete):**

- New `action_grants` table: `(id, action_type, email_ids JSON, expires_at, minted_at, revoked_at)`. Grants scoped to a specific action type — a `delete` grant does not authorize `send_reply`.
- Drainer performs second auth check at drain time (FR-5.5): grant must still be valid AND, for Tier-3, change_marker must match (D4).

**Naming convention:** `snake_case_verb_noun`; single source in `mailbot_api/actions/types.py`; verb API, drainer, audit logger, and notification tier-mapping all reference the same constants.

### Runtime Mechanics (D3 + D7 + D8 + D13 + D14)

**Daily digest composer (D3):**

- **Hybrid: structured payload verb + agent intro.** A `compose_digest()` verb on `mailbot-api` returns a structured payload (unread groups by importance, pending Tier-2 batch counts, weekly drift/sampling artifacts if scheduled) by reading cached projections only — no body re-derivation, summaries come from `summary_short` (Rule A enforced).
- **Hermes cron-with-agent at 08:00** calls `compose_digest()`, then makes 1 Qwen call routed via `policy.yaml[daily_digest]` to produce a persona-voiced intro paragraph (≤ 200 tokens out). The intro is wrapped around the structured payload and posted to Discord.
- Response-cached against the input hash so a re-run within TTL is free.

**Internal concurrency model (D7):**

- **Two processes inside the `mailbot-api` container:**
  1. `uvicorn mailbot_api.main:app` — FastAPI HTTP + MCP server (chat-serving)
  2. `python -m mailbot_api.worker` — background tasks (sync, ingest pipeline, drainer, cache warmer)
- Both processes started by the Dockerfile entrypoint (worker backgrounded; uvicorn in foreground). One container, one Docker service, deployment story unchanged.
- **Inter-process status** via `worker_health` SQLite table; FastAPI reads it for `mailbot status` and `/v1/health`.
- **Cross-process signaling** (e.g., "policy.yaml changed, reload") via SQLite event row or filesystem signal file; both processes pick up reloads independently.
- **Why two processes:** sync first-pull (10–30 min per FR-1.2) and 100-email ingest batches must not stall the chat-serving event loop (NFR-PERF-1 p95 ≤ 5s).

**SQLite write contention strategy (D8):**

- **WAL mode + `busy_timeout=5000` + all writes through `run_in_executor`.** Reads stay on the asyncio event loop (sub-ms in WAL); writes go through the executor so a slow write or checkpoint doesn't stall chat.
- **Pragmas applied on every connection:** `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`, `foreign_keys=ON`.
- **Connection management:** one connection per task (no shared connections across awaits); short-lived; closed promptly.
- If contention ever bites (unlikely on personal-scale traffic), upgrading to a single-writer queue is a localized refactor.

**Cron-job runner ownership (D13):**

- **Split between Hermes and `mailbot-api` internal scheduler:**
  - **Hermes cron (agent-involving):** daily digest at 08:00, weekly drift report Sunday 09:00, weekly sampling Sunday 09:30.
  - **`mailbot-api` internal scheduler (LLM-free critical infra):** sync every 4 min, cache warmer every 4 min, ingest pipeline every 5 min, pending_actions drainer (continuous loop, not cron).
- **Why split:** the sync worker is the single most reliability-sensitive job ("availability trust: sync runs continuously" — PRD §1.3). Coupling it to Hermes uptime adds risk for no benefit. The cache warmer is reliability-sensitive too (Rule M).
- **Mild Rule X drift acknowledged:** we relax "all scheduling lives in Hermes" to "agent-involving scheduling lives in Hermes; LLM-free critical infra scheduling lives in `mailbot-api`." Documented as a deliberate departure.

**Database access pattern (D14):**

- **stdlib `sqlite3` + `run_in_executor` for writes.** No SQLAlchemy, no `aiosqlite`, no ORM.
- **Schema-as-code in `schema.sql`** + numbered migration files (`001_init.sql`, `002_oauth_state.sql`, …) in `mailbot_api/db/migrations/`. Migrations applied at startup if not recorded in a `_migrations` table.
- **Pydantic models on data boundaries** (verb in/out, prompt OUTPUT_SCHEMA, FastAPI request/response); raw SQL for internal queries centralized in `mailbot_api/db/queries.py`.

### Schema implications introduced in this section

These extend the schema implied by FR-1..8 — full table inventory lands in the Data Architecture step:

- **`router_calls`** gains `caller_origin`, `sensitivity_grant_id` (nullable), `sensitivity_grant_minted_at` (nullable).
- **`emails`** gains `change_marker` column (already implicit in FR-1.4's idempotency on `(graph_id, change_marker)`). **Despite the column name, the stored value is Graph's `changeKey` field on the message resource — `@odata.etag` does not exist on the message resource.** Story 1-10 documents the semantic alignment without renaming the column (avoids destructive migration). `emails` also gains `removed_reason TEXT NULL` (Story 1-10): `'changed'` (recoverable from deletedItems) or `'deleted'` (permanent), per the Graph `@removed.reason` contract — used by Epic 4's Tier-1 reverter to know whether restoration is even possible.
- **`pending_actions`** schema: `id`, `email_id`, `action_type` (enum), `tier` (1/2/3, derived from action_type at insert), `payload` (JSON), `proposed_at`, `proposed_by_grant_id` (nullable), `change_marker_at_propose`, `status` (`pending` / `cooling_off` / `draining` / `applied` / `failed`), `retry_count`, `failure_reason`, `terminal_at`, `budget_consumed` (bool).
- **`action_grants`** (new): `(id, action_type, email_ids JSON, expires_at, minted_at, revoked_at)`.
- **`action_history`** (new): `(action_id, pre_state JSON, applied_at, reverted_at nullable)` — supports Tier-1 24h revert.
- **`oauth_state`** (new): single row keyed by `provider`; `(refresh_token, access_token, access_expires_at, last_rotated_at, rotation_count)`.
- **`worker_health`** (new): `(component, last_heartbeat_at, last_outcome, last_error)` — components: `sync`, `cache_warmer`, `drainer`, `ingest_pipeline`.

#### Embedding-column binary contract (W-5 resolution, Epic 2 §13 postscript)

The `emails.embedding` column stores nomic-embed-text vectors as raw bytes (768-dim float32 = 3072 bytes per row). The byte representation is **load-bearing** because cross-architecture portability matters (dev box may be x86_64, VPS may be aarch64; SQLite files travel between them via backup/restore). The contract:

- **Storage format:** little-endian float32 (`numpy.dtype("<f4")`). NumPy's native byte order on x86_64 IS little-endian, but the dtype string is fixed regardless of host so the same bytes round-trip identically on any architecture.
- **Companion metadata columns:** `embedding_dtype TEXT NOT NULL` and `embedding_shape TEXT NOT NULL` (JSON-encoded shape tuple, e.g. `"[768]"`). Stored alongside every embedding row so the reader can validate the contract before deserializing. Added in migration 011 (renumbered from spec's 010 due to cumulative migration-chain shift — see migration-numbering policy below).
- **Writer monopoly:** `mailbot_api/ingest/embedding.py` is the SOLE writer of `emails.embedding` (`write_embedding(email_id, vector)`); the boundary checker (`scripts/check_boundaries.py` `_EMBEDDING_WRITE_ALLOW`) enforces this with positive-pass + f-string-bypass + keyword-arg-bypass coverage per the writer-monopoly canonical pattern (Rule G).
- **Portability test (Story 3-4):** `test_write_embedding_cross_architecture_portability` asserts `numpy.asarray([1.0, 2.0, 3.0], dtype="<f4").tobytes()` round-trips byte-for-byte through the writer → SQLite TEXT → reader path. If this test fails, the W-5 contract is broken; STOP and reconcile before any production deploy.
- **Rationale:** SQLite stores blobs without interpretation; "byte-exact" cross-architecture parity is the only contract that doesn't require parsing on every read. The dtype + shape companion columns make the contract self-describing — a future story changing the embedding model + dimensionality only touches the columns (not migration or reader code).

#### Migration numbering policy

- **Files:** `mailbot_api/db/migrations/NNN_short_kebab_description.sql`, 3-digit zero-padded prefix, monotonically increasing across all epics. The `_migrations` table records `applied_at` per prefix.
- **Renumber discipline:** if an epic spec assigns numbers `006–010` but a prior epic's late story (e.g., 1-10 retro patch) lands a migration in the same range first, the next epic's migrations **shift up by the cumulative offset**. The shift is recorded inline in each affected story's "Disposition" section + the epic spec's preamble. No story has been retroactively renumbered; the migration order in `mailbot_api/db/migrations/` is the canonical source.
- **Gap tolerance:** the `_migrations` table accepts gaps cleanly. A skipped or deleted prefix (e.g., a migration written but rolled back before commit) does NOT corrupt the runner — `apply_pending_migrations()` reads filesystem and applies any prefix not in `_migrations` regardless of gaps.
- **CHECK-constraint enum sync:** any migration that adds a `CHECK(col IN ('a', 'b', ...))` constraint MUST have a unit test (e.g., `tests/integration/test_action_schema.py`) that asserts the constraint's value set matches the Python enum's value set. A drift between Python enum and SQL CHECK is a silent data-corruption surface (insert succeeds in Python tests, fails in production).
- **Cumulative numbering observed in MailBot through Epic 4:** Epic 1 = 001–005 (final 005 actually shipped as 005_immutable_id_and_change_marker_rename + 1-10's 004_worker_health, ordering inverted at ship time but both run idempotently). Epic 2 = 006–010. Epic 3 = 011–014. Epic 4 = 015–017. Total chain: 17 migrations.

### New stable error codes introduced

Added to the Router's stable code set (FR-3.4 extension):

- `rate_limited` — lane rate limit exceeded at enqueue (D10).
- `state_drift_etag` — Tier-3 change_marker mismatch at drain (D4).
- `target_deleted` — drain found target removed; treated per tier per D4.
- `state_drift_noop` — lenient-policy resolution decided to no-op (D4).
- `needs_sensitivity_confirmation` — sensitive-to-API call attempted without a valid token (D1).

### Decision Impact Analysis

**Implementation sequence (informs Epics/Stories ordering):**

1. **M1 (foundation):** Bootstrap repo, Docker stack, SQLite schema (with WAL + pragmas), Outlook sync into `oauth_state` (D9), structured logging.
2. **M2 (Router + local LLM):** Router with two-queue lane scheduling (D10), policy.yaml + Pydantic `PolicyTable` schema + watchfiles reload (D11), `caller_origin` on `router_calls`, stable error codes including `rate_limited`.
3. **M3 (API tier + budget + sensitivity):** Anthropic adapter with ephemeral cache, 4-layer budget, sensitivity classifier, `mint_sensitivity_token` verb + in-memory grant registry + `confirmation_token` flow (D1, D12), `needs_sensitivity_confirmation` error path.
4. **M4 (eval system):** Benchmark runner uses Router with `force_model` (Rule I); no changes from this section.
5. **M5 (Hermes integration):** Discord adapter, SOUL/AGENTS, Hermes cron for digest/drift/sampling, `compose_digest()` verb (D3), `caller_origin="hermes-aux-*"` tagging, drift detection in `mailbot status`.
6. **M6 (VPS deployment):** Two-process container entrypoint (D7), `worker_health` polling, OAuth rotation under live load, action-failure notification tiers.

**Cross-component dependencies:**

- D1 (sensitivity token) depends on D12 (storage) and Round D action-types `requires_sensitivity_token` flag.
- D4 (sync conflicts) depends on D6 (tier mapping) for the change_marker_required decision per action.
- D5 (retry contract) depends on D6 for `budget_against` consumption semantics.
- D7 (two processes) depends on D8 (SQLite contention) and D13 (cron ownership) for clean separation of work.
- D13 (split cron) depends on D7 (worker process exists to host the internal scheduler).
- D11 (policy hot-reload) depends on D7 (cross-process signaling) so both processes pick up reloads.

## Implementation Patterns & Consistency Rules

### Scope notes

Several standard categories from the pattern playbook do not apply to MailBot: React component naming, event-payload format for a frontend bus, frontend state management, loading-state UI patterns. Discord is the UI and Hermes owns conversational state. The patterns below focus on the categories that genuinely produce conflict for two AI agents (or you-on-Monday vs. you-on-Friday) working on this codebase.

### Naming Patterns

**Database:**

- Tables: `snake_case`, **plural** (`emails`, `router_calls`, `pending_actions`, `action_grants`, `oauth_state`). Single-row tables stay plural for consistency.
- Columns: `snake_case` (`email_id`, `proposed_at`, `change_marker`, `cost_usd_estimated`).
- Foreign keys: `<referenced_table_singular>_id` (`email_id`, `thread_id`, `sender_id`, `grant_id`).
- Companion metadata columns for derived fields (Rule A): `<field>_prompt_v`, `<field>_conf`, `<field>_model`, `<field>_at` — mandated by FR-2.1.
- Timestamps: `*_at` for absolute instants (UTC), `*_ttl_seconds` for durations, `*_window_minutes` for human-readable windows. Avoid bare `created` / `updated` — always `_at`.
- Booleans: `is_*` or `has_*` (`is_deleted`, `has_attachments`, `is_consumed`).
- Indexes: `ix_<table>_<col1>_<col2>` (`ix_emails_thread_id_received_at`).
- Migration files: `NNN_short_kebab_description.sql` (`001_init.sql`, `002_oauth_state.sql`, `017_add_caller_origin.sql`).

**Python code:**

- Modules + packages: `snake_case` (`router/`, `mailbot_api/actions/`, `verbs/find_emails.py`).
- Functions: `snake_case` (`mint_sensitivity_token`, `ask_router`, `compose_digest`).
- Classes: `PascalCase` (`RouterResult`, `PolicyTable`, `Email`, `PendingAction`).
- Constants: `UPPER_SNAKE_CASE` for module-level constants (`DEFAULT_MAX_TOKENS = 4000`); `PascalCase` enum class with `UPPER_SNAKE_CASE` members (`ActionType.MARK_READ`).
- Private helpers: `_leading_underscore`.
- Pydantic models: `<Noun>In` and `<Noun>Out` for verb boundaries (`FindEmailsIn`, `FindEmailsOut`); plain `<Noun>` for domain rows (`Email`, `RouterCall`).

**MCP tool names** (Hermes-facing surface): `snake_case` matching the verb function name exactly — `find_emails`, `hydrate_email`, `ask_router`, `mint_sensitivity_token`. No prefixes; the MCP server itself is namespaced.

**Action types** (D6 enum): `snake_case_verb_noun` — `mark_read`, `move_to_user_folder`. Listed centrally in `mailbot_api/actions/types.py`. Single source of truth.

**Stable error codes** (Router): `snake_case`, descriptive — `rate_limited`, `state_drift_etag`, `needs_sensitivity_confirmation`. Each declared in `mailbot_api/router/errors.py`. Using a string outside the enum is a lint failure.

**Prompt task types** (`policy.yaml` keys): `snake_case` matching the directory under `prompts/` exactly — `coarse_class`, `sensitivity_class`, `draft_reply`, `summary_short`. The task type is the contract; deviating breaks the Router's lookup.

### Structure Patterns

Repository layout is pinned in the Starter Template Evaluation section. The invariants enforced here:

- **One bounded responsibility per package.** No cross-package shortcuts.
  - The Router is the only code that calls Ollama or Anthropic adapters (Rule I).
  - Verbs are the only code that touches SQL for the agent's benefit (Rule C).
  - Sync is the only code that touches Microsoft Graph (Rule B).
- **Prompt versions** live in `prompts/<task_type>/vN.py` and only there. Each `vN.py` exports exactly four names: `VERSION` (str), `SYSTEM` (str, cacheable), `USER_TEMPLATE` (str), `OUTPUT_SCHEMA` (Pydantic class).
- **SQL queries** live in `mailbot_api/db/queries.py` (or `db/queries/*.py` if it grows). Not inline in verbs. Verbs call query functions.
- **Tests** live in `tests/unit/` and `tests/integration/`, mirroring the source layout (`tests/unit/router/test_router.py` ↔ `mailbot_api/router/router.py`). Co-located test files (e.g. `router_test.py` next to `router.py`) are forbidden — clean separation makes Docker image filtering trivial.
- **Hermes config artifacts** (`SOUL.md`, `AGENTS.md`, `SKILL.md`, `config.yaml`, `cron/jobs.json`) live under `hermes-config/` and only there.
- **No code in the repo root** except packaging files (`requirements.txt`, `pyproject.toml`, `Makefile`, `docker-compose.yml`, `.env.example`).

### Format Patterns

**Router result shape** (every LLM call returns this):

```python
class RouterResult(BaseModel):
    ok: bool
    output: BaseModel | None      # parsed against OUTPUT_SCHEMA
    error: RouterError | None     # populated when ok=False
    cost_usd: float
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cached_tokens_in: int
    model_used: str
```

**Router error shape:**

```python
class RouterError(BaseModel):
    code: ErrorCode               # stable enum, never free string
    message: str                  # sanitized, never includes URLs/keys/stacks (Rule F)
    model_attempted: list[str]
    retryable: bool
```

**FastAPI HTTP error response:**

- OpenAI-shape on the OpenAI-compatible endpoints (so Hermes treats us like a real provider): `{"error": {"type": "...", "message": "...", "code": "..."}}`.
- MailBot-shape on admin/internal endpoints (`/health`, future `/admin/*`): `{"ok": false, "error": {"code": "...", "message": "..."}}`.

**Verb error returns** (MCP-facing, agent-consumed):

- **Never raise to the agent.** Verbs return `<Noun>Out` always; failures populate an `error: RouterError | None` field on the response model. The agent sees structured data, not exceptions (Rule F + error-as-data principle).

**Datetime convention:**

- All instants stored and exchanged as **UTC ISO-8601 strings** with `Z` suffix (`2026-05-31T08:00:00Z`).
- Python: `datetime.now(timezone.utc)` always; never `datetime.utcnow()` (deprecated and naive).
- SQLite: stored as `TEXT` in ISO-8601 UTC; never `INTEGER` epoch.
- Adam's display timezone resolves at the Discord/Hermes presentation boundary only — never in the data layer.

**JSON casing on API boundaries:**

- **`snake_case` everywhere** — internal Python, SQL columns, JSON fields, Pydantic field names, MCP tool args, FastAPI request/response models. One convention end-to-end means no camelCase/snake_case adapters anywhere.
- Exception: the OpenAI-compatible `/v1/chat/completions` endpoint follows OpenAI's spec (which is also `snake_case`, so no conflict).

**Structured log line shape** (Rule W, FR-7.3):

```json
{
  "ts": "2026-05-31T08:00:00.123Z",
  "level": "info",
  "module": "mailbot_api.router.router",
  "event": "router.call.ok",
  "task_type": "coarse_class",
  "model": "qwen2.5:3b-instruct-q4_K_M",
  "caller_origin": "verb-ask-router",
  "email_id": "AAMkAGI…",
  "cost_usd": 0.0,
  "latency_ms": 1234
}
```

- One JSON object per line, stdout only.
- `event` namespace is dotted: `router.call.ok`, `router.call.failed`, `sync.completed`, `sensitivity.token.minted`, `action.proposed`, `action.applied`, `action.failed`. Stable codes; downstream tooling keys on `event`.
- Never log secrets, full email bodies, or raw Graph URLs (Rule F). The structured logger runs a sanitizer pass.

### Communication Patterns

**Verb input/output schemas (Pydantic):**

- Every verb has `<VerbName>In` and `<VerbName>Out` models. No bare types in or out.
- Optional fields use `field: T | None = None`, never `Optional[T]` (PEP 604 preferred in Python 3.12).
- Lists default to `Field(default_factory=list)` to avoid mutable-default trap.
- Field descriptions are populated — they propagate to MCP tool schema and into the Hermes agent's prompt context. Better descriptions = better agent behavior.

**MCP tool descriptions:**

- One sentence, present tense, what-it-does ("Return up to `limit` emails matching `filter`, projection only (Rule J — use `hydrate_email` for full bodies).").
- Mention cost-relevant constraints explicitly ("Rate-limited to 5 calls per chat turn") — agent can read them and behave.

**What MCP is here — and what it is NOT (clarification, Story 10.7.0):**

- **MCP is a _surface_ of `mailbot-api`, not the whole container.** `mailbot-api` is a Python application with several doors: (1) the **HTTP/REST API** (FastAPI — `/v1/chat/completions`, `/v1/embeddings`, `/health`, admin endpoints); (2) the **Router** (model selection, budget guards, audit log); (3) **LLM-free background workers** (sync loop, ingest pipeline, pending-actions drainer); and (4) the **MCP server** (`mcp_server.py`, FastMCP), which advertises the verbs in `mailbot_api/verbs/` as tools. So "`mailbot-api` is an MCP server" is _partly_ right — the MCP server is the LLM-tool-facing surface layered on top of the real logic (Graph/Azure wrapper + SQLite), not the entire container.
- **MCP advertises and transports tools — it does NOT choose them.** MCP's job is to publish the tool list + JSON schemas to the client (Hermes) and carry the chosen call over the wire. **Which** tool the model invokes is 100% the LLM's decision, made from the descriptions + the user turn. A wrong tool pick is a _model/prompt/description_ problem, never an MCP-transport problem. Story 10.7.0 proved this concretely: MCP faithfully handed local qwen all 26 verbs, and qwen still mis-picked `pull_pending_notifications` over `find_emails` — MCP did its job; the model chose wrong.
- **Consequence — tool selection is engineered on the MCP surface, not inside MCP.** The levers that fix mis-selection all shape _what MCP advertises and how the model reasons over it_: sharpen tool descriptions (see below), scope/trim the per-turn tool menu, hierarchical (category-then-leaf) tool presentation, and a selection system prompt. None of these change MCP itself.

**Tool descriptions measurably drive selection (Story 10.7.0 evidence):** the "better descriptions = better agent behavior" principle above is not a hunch — it was measured. On the live local qwen (`qwen2.5:3b`, temp 0): a 26-tool flat surface → 0/N correct (fixated on a distractor whose description over-matched the user's words); a 4-category surface with sharp plain-English descriptions → 20/20; a 5-tool email-branch surface with `find_emails`'s _real_ jargon description ("email **projections** matching `filter` … Rule J") → 0/20 (qwen picked siblings or asked a clarifying question instead of acting), recovering to 15/20 only once a selection prompt was added. **Lesson for verb authors:** a small local model reads the description literally — lead with the plain user-facing verb (find / search / unread / inbox), not the internal data model ("projections", "Rule J"); keep the constraint note _after_ the plain what-it-does. See `_bmad-output/implementation-artifacts/10-7-0-spike-finding.md` §1/§4.2/§4.3 and memory `feedback_measure_real_tool_surface_at_every_level`.

**Error-as-data discipline (Rule F + brainstorm Decision 3):**

- Verbs and Router never raise to the agent. They return models with an optional `error` field.
- Exceptions inside `mailbot-api` are fine internally, but **caught at the verb/Router boundary** and converted to `RouterError` / `<VerbName>Out(error=...)`.
- `AGENTS.md` tells the agent to inspect `result.error` after every call.

**Audit-log writes:**

- One row per LLM call, written by `mailbot_api/observability/audit.py`'s `record_router_call(...)` function.
- Written **after** the call completes (success or failure), as part of the Router's `finally` block — never lost.
- Writing happens through the same `run_in_executor` write path as other DB writes (D8 discipline).

### Process Patterns

**Error handling layers:**

- **Boundary catches:** every FastAPI route handler, every MCP tool handler, every background-task entrypoint, every verb function has a `try/except` at its boundary that converts exceptions to error-as-data.
- **Internal exceptions are fine** within a function — Python idioms, not Java-style "catch everything." The discipline is "no exceptions cross the boundary to the agent."
- **Sanitization** is a single helper `sanitize_error(exc) -> str` in `mailbot_api/router/errors.py`. Strips URLs with tokens, file paths to secrets, full stack frames. Called automatically when building `RouterError.message`.

**Retry discipline:**

- **Router internal retries** (FR-3.4): single retry with stricter prompt on schema-validation failure; per-task `escalate` flag for tier escalation. Centralized in `router.py`.
- **Graph write-back retries** (D5): error-classified, exponential backoff (1s / 4s / 16s), max 3 retries. Centralized in `mailbot_api/actions/drainer.py`. No ad-hoc retry loops elsewhere.
- **Cache warmer retries:** none — the warmer is best-effort; a missed warm period costs cache-miss latency, not correctness. Log info-level on failure.

**Validation timing:**

- **At system boundaries only.** FastAPI request bodies validated by Pydantic on entry; LLM outputs validated against `OUTPUT_SCHEMA` in the Router; YAML configs validated at load.
- **Internal calls trust their types.** No defensive re-validation between verb → Router → adapter. mypy + tests do that work.

**Idempotency keys:**

- Ingest pipeline: `sha256(body) + prompt_version + model + task_type` (FR-2.2, Rule K). Centralized helper `compute_idempotency_key(...)` in `mailbot_api/ingest/idempotency.py`.
- Sync: `(graph_id, change_marker)` (FR-1.4). Centralized in sync layer.
- Response cache: `hash(prompt + model + temperature)` (FR-3.7). Centralized in `router/response_cache.py`.
- **No ad-hoc idempotency**; use the right central helper.

**Secrets access:**

- All secret reads through `get_secret(name: str) -> str` in `mailbot_api/config.py` (Rule F, NFR-SEC-5). Never `os.environ["..."]` directly outside this module.
- `get_secret` reads `.env` today; the indirection allows swapping in pass/age/Vault later (NFR-SEC-5).

**Database access:**

- Read: `await db.fetchone(query, params)` / `await db.fetchall(query, params)` — connection acquired per-call from a pool, sync sqlite3 driver, on the event loop (sub-ms in WAL).
- Write: `await db.execute_write(query, params)` — same shape, but the executor path (D8). Centralized in `mailbot_api/db/connection.py`.
- **No raw `cursor.execute()` outside `db/`.** Every query lives in `queries.py`.

**Background task heartbeats (D7 + worker_health):**

- Every background task (sync, ingest, drainer, cache warmer) writes a row to `worker_health` on every successful iteration. `mailbot status` reads these.
- Heartbeat format: `(component, last_heartbeat_at, last_outcome, last_error)`.

**Default behaviors (Rule Ω + safety defaults made operational):**

- **All Router calls default to Qwen 3B** unless `policy.yaml` says otherwise.
- **All actions default to Tier 0/1** unless their action_type maps higher in `mailbot_api/actions/types.py` (D6).
- **All notifications default to silent** unless they match an explicit tier rule in `mailbot_api/notifications/tiers.py` (FR-7.4).
- **All sensitivity defaults to `sensitive`** when classifier confidence is below threshold (NFR-PRIV-1 cautious-bias).

**Writer-monopoly canonical pattern (Rule G):**

A "writer-monopoly" boundary exists when exactly ONE module in the codebase is allowed to write to a specific resource — a SQL column, a YAML file, an action's `pending_actions.tier` field, a `router_calls` audit row — and every other module is structurally forbidden from doing so. Established in MailBot by Story 2-1 (`router_calls` writer = `observability/audit.py`), Story 3-1 (idempotency-key formula = `ingest/idempotency.py`), Story 3-4 (`emails.embedding` writer = `ingest/embedding.py`), Story 4-1 (Tier-1/2/3 action_type bare-string-literal lint).

Every writer-monopoly ships with the same 5-part recipe:

1. **The writer module** — a single Python module that owns the resource. Exports the write function (e.g., `write_embedding`, `record_router_call`, `compute_idempotency_key`). No other public surface.
2. **The boundary check** — an entry in `scripts/check_boundaries.py` (typically a path allowlist set like `_EMBEDDING_WRITE_ALLOW`) + an AST walker that flags any occurrence of the resource's signature pattern (e.g., a `cursor.execute` whose first positional arg matches `r"^\s*UPDATE\s+emails\s+SET\s+embedding"`) outside the allowlisted paths. Both positional and keyword arguments must be scanned (post-CR-5 on Story 3-1).
3. **A violation fixture** — a deliberately-violating fixture under `tests/fixtures/lint_violations/violates_<resource>.py.fixture` that the boundary check is asserted to FAIL on. Without this, "the check works" is unprovable.
4. **A positive-pass test** — a fixture (or the writer module itself) where the resource IS written correctly + the boundary check is asserted to PASS. Without this, a broken check that flags EVERYTHING (false positive on the writer itself) ships green.
5. **A specificity test** — a benign call that LOOKS like the resource pattern but is semantically different (e.g., `hashlib.sha256(...)` outside the idempotency-key formula context; an f-string that constructs an UPDATE-looking string but never executes it). The boundary check MUST allow these. Without this, the check is too coarse and developers will start adding the resource module to the allowlist for unrelated reasons.

Additional invariants (learned the hard way through Epic 2/3/4):

- **F-string bypass coverage** — the AST walker must descend into `ast.JoinedStr` nodes; a writer pattern wrapped in an f-string is otherwise invisible to the lint.
- **Docstring tolerance** — module/class/function docstrings frequently contain the resource pattern as an example; the walker must pre-filter docstring nodes (collected via `_collect_docstring_node_ids`) or the boundary check false-positives on its own documentation.
- **Sync-check test** — when the writer monopoly's value set is derived from an enum (e.g., the Tier-1/2/3 action_type lint draws values from `ActionType`), an explicit test asserts the lint's hardcoded set equals the enum's subset. Drift between them silently breaks enforcement.

**Defense-in-depth pattern for invariants (Rule H):**

When the system MUST enforce an invariant — privacy ("sensitive bodies never reach Anthropic without a confirmation handshake", FR-2.5 + AR-D12-1), authorization ("the agent cannot promote an action's tier", FR-5.6), data shape ("the embedding column always carries little-endian float32") — the enforcement is layered across THREE independent layers, each independently sufficient.

The three layers, in order from outermost (closest to the developer/agent) to innermost (closest to the data):

1. **Lint / boundary layer.** A `scripts/check_boundaries.py` rule, a ruff rule, an mypy `--strict` setting, or a writer-monopoly (Rule G) entry that refuses the violation at static-analysis time. Catches the violation BEFORE the code runs. Example: bare-string `"delete"` outside `mailbot_api/actions/types.py` is a lint failure (Story 4-1).
2. **Verb / boundary-input layer.** A runtime guard inside the verb function (or other boundary-input handler) that validates the input and refuses with `<Verb>Out(ok=False, error=...)`. Catches the violation when the call IS made but BEFORE it touches state. Example: `propose_action` rejects any payload containing a `tier` field with `TIER_PROMOTION_ATTEMPT` BEFORE the tier is computed (Story 4-2).
3. **Data / SQL layer.** A SQL `CHECK` constraint, a Pydantic `frozen=True` model, a Python `MappingProxyType`-wrapped dict, a database trigger. Catches the violation if it somehow reaches the data layer. Example: `pending_actions.tier CHECK (tier IN (1,2,3))` — Tier-0 cannot enter the queue even if Layers 1 and 2 are bypassed (Story 4-2 migration 015).

Why all three: any single layer can be bypassed (linter not run; verb routed around via a direct SQL write; SQL constraint dropped in a migration). Three independent layers means three independent things have to fail before the invariant breaks. Each layer is also independently testable, so a regression in one is caught in isolation rather than by the combined effect.

Currently-defended invariants and their three layers:

- **FR-2.5 (Qwen-only sensitivity classification):** Lint = none (policy is data, not code); Verb = `_assert_qwen_only_per_call()` in `mailbot_api/sensitivity/classifier.py` reads the dispatch-time policy snapshot and refuses if the model isn't Qwen; Data = `mailbot_api/main.py` lifespan calls `assert_qwen_only(policy)` at startup to fail-fast on a drifted `policy.yaml`. (Two of three layers; the lint layer is N/A because the binding is data, not code.)
- **FR-2.3 (sensitivity precondition hard invariant):** Lint = none; Verb = `mailbot_api/router/router.py` precondition layer at `ask_router` entry refuses any non-sensitivity-task call on `email_id` where `sensitivity_at IS NULL`; Data = `emails.sensitivity_at` column is the canonical source — no parallel store can disagree.
- **FR-5.6 (agent cannot promote action tier):** Lint = `scripts/check_boundaries.py` rejects bare-string Tier-1/2/3 action_type literals outside `mailbot_api/actions/types.py`; Verb = `propose_action` rejects any payload containing a `tier` field with `TIER_PROMOTION_ATTEMPT`; Data = `pending_actions.tier CHECK (tier IN (1,2,3))` migration 015.
- **AR-D12-1 (sensitivity-token handshake):** Lint = none (registry is in-memory, not code); Verb = `mint_sensitivity_token` refuses confidential + refuses normal; `ask_router(confirmation_token=...)` re-validates against the registry with email-id + task-type binding + single-use + 10-min TTL; Data = `router_calls.sensitivity_grant_id` audit row records every consume.

When adding a new invariant: identify the layer that fits each enforcement axis (some invariants have N/A layers — privacy invariants typically lack a lint layer because the binding is runtime state, not code), add a guard at each non-N/A layer, ship a regression test per layer. **Three layers, each independently sufficient, no single point of failure.**

### Enforcement

**All AI agents (and human contributors) MUST:**

1. Read `policy.yaml` only via the loader in `router/policy.py`. Never parse YAML elsewhere.
2. Call LLMs only via `ask_router()` (Rule I). Direct `ollama.chat()` or `anthropic.messages.create()` outside `router/models.py` is a fail-the-PR violation.
3. Touch Microsoft Graph only via `mailbot_api/sync/graph_client.py`. Direct `requests.get("https://graph.microsoft.com/...")` outside this module fails review. All Graph requests from `graph_client.py` carry `Prefer: IdType="ImmutableId"` to prevent message-ID rotation on folder moves (Story 1-10).
4. Touch SQL only via `mailbot_api/db/queries.py` (or its successor modules). Inline SQL anywhere else is a violation.
5. Read secrets only via `get_secret(name)`. Direct `os.environ` reads outside `config.py` fail review.
6. Use `UTC datetime.now(timezone.utc)`. Naive datetimes anywhere fail review.
7. Use the central error codes enum (`ErrorCode`). String error codes fail review.
8. Use the central action types enum (`ActionType`). String action_type values fail review.
9. Match prompt module structure exactly (`VERSION`, `SYSTEM`, `USER_TEMPLATE`, `OUTPUT_SCHEMA`).
10. Run `ruff check` + `ruff format` + `mypy --strict` clean before committing.
11. Ship every new writer-monopoly with the full 5-part recipe (writer module + boundary check + violation fixture + positive-pass test + specificity test + f-string-bypass coverage + docstring tolerance + sync-check test if enum-derived). See Rule G.
12. When introducing or modifying enforcement of an invariant (privacy / authorization / data shape), enumerate the three Rule H layers (lint / verb / data) — add guards at each non-N/A layer + a regression test per layer.

**Enforcement mechanism:**

- **ruff** lint rules forbid `os.environ` outside `config.py`, forbid `print()` outside `scripts/`, forbid raw `requests.*` outside `sync/`, forbid `sqlite3.connect()` outside `db/`.
- **mypy --strict** catches missing field types, ungated `None` access, untyped function defs.
- **CI** runs both on every push (later step).
- **Pattern violations are PR blockers,** not warnings.

### Concrete examples

**Good:**

```python
from mailbot_api.router import ask_router

async def classify_email_coarse(email_id: str) -> str:
    result = await ask_router(
        task_type="coarse_class",
        content=fetch_email_body(email_id),
    )
    if not result.ok:
        log.error("router.call.failed", code=result.error.code, email_id=email_id)
        return "unknown"
    return result.output.category
```

**Anti-patterns:**

```python
# WRONG: direct provider call, bypasses Router/budget/audit/sensitivity
from ollama import chat
def classify(body):
    return chat(model="qwen2.5:3b", messages=[...])["message"]["content"]

# WRONG: raises to agent
def find_emails(filter):
    raise ValueError("invalid filter")  # use FindEmailsOut(error=...)

# WRONG: naive datetime
ts = datetime.utcnow()  # use datetime.now(timezone.utc)

# WRONG: ad-hoc string code
return RouterError(code="bad_thing", ...)  # use ErrorCode.SCHEMA_VALIDATION_FAILED
```

## Project Structure & Boundaries

### Complete Project Directory Structure

```text
mailbot/
  README.md
  Makefile
  requirements.txt
  pyproject.toml                   # ruff + mypy + pytest config
  docker-compose.yml               # 3 services: mailbot-hermes, mailbot-api, ollama
  docker-compose.override.yml      # local dev: source bind-mount, dev ports
  .env.example                     # all keys listed; no values
  .gitignore                       # blocks .env, *.key, *.pem, __pycache__, .venv, *.db
  .dockerignore
  .editorconfig

  docker/
    Dockerfile.mailbot-api         # multi-stage; ENTRYPOINT runs worker + uvicorn
    entrypoint.sh                  # backgrounds python -m mailbot_api.worker, foregrounds uvicorn

  mailbot_api/                     # the Python package — F1..F8 implementation
    __init__.py
    main.py                        # FastAPI app: /v1/chat/completions, /v1/embeddings, /health, /v1/health
    worker.py                      # second process: sync, ingest, drainer, cache warmer loops
    config.py                      # get_secret(name), env loading, paths, constants
    mcp_server.py                  # FastMCP server, exposes verbs as MCP tools

    db/                            # the ONLY place SQL lives (Rule C boundary)
      __init__.py
      connection.py                # WAL pragmas, pool, async wrappers, execute_write via executor
      queries.py                   # all SELECT/INSERT/UPDATE/DELETE — verbs/workers call these
      schema.sql                   # full initial schema (replaced by migrations after 001)
      migrations/
        001_init.sql               # emails, threads, senders, router_calls, response_cache, derivations, sync_state
        002_pending_actions.sql    # pending_actions, action_grants, action_history (D6 + D4)
        003_oauth_state.sql        # oauth_state (D9)
        004_worker_health.sql      # worker_health (D7)
        005_benchmark_runs.sql     # benchmark_runs (F8)
        006_caller_origin.sql      # caller_origin column on router_calls (D2)
        007_sensitivity_grants.sql # sensitivity_grant_id columns on router_calls (D1)

    router/                        # the ONLY place Ollama/Anthropic adapters live (Rule I + F.1 boundary)
      __init__.py                  # public API: ask_router(), get_router(), policy reload hook
      router.py                    # call orchestration: precondition, dispatch, retry, escalate
      policy.py                    # PolicyTable schema, YAML loader, watchfiles reload (D11)
      models.py                    # ModelAdapter base, OllamaAdapter, AnthropicAdapter
      pricing.py                   # tokens -> USD per model
      budget.py                    # 4-layer budget guard, degraded mode, anomaly detection
      lanes.py                     # interactive_q, batch_q, worker pool (D10)
      limits.py                    # rate limits, anti-loop, kill-switch
      cache_warmer.py              # Anthropic ephemeral-cache keep-warm pinger
      response_cache.py            # hash(prompt+model+temp) -> result, SQL-backed
      errors.py                    # ErrorCode enum, RouterError, RouterResult, sanitize_error()

    prompts/                       # the ONLY place prompt text lives
      __init__.py                  # registry: (task_type, version) -> module
      coarse_class/v1.py           # VERSION, SYSTEM, USER_TEMPLATE, OUTPUT_SCHEMA
      fine_class/v1.py
      sensitivity_class/v1.py
      summary_short/v1.py
      summarize_short_thread/v1.py
      summarize_long_thread/v1.py
      importance_scoring/v1.py
      action_extraction/v1.py
      intent_parsing_chat/v1.py
      reference_resolution/v1.py
      draft_reply/v1.py
      tone_style_mirror/v1.py
      multi_turn_refinement/v1.py
      bulk_action_proposals/v1.py
      subscription_audit/v1.py
      auto_file_decision/v1.py
      unsubscribe_candidate/v1.py
      notification_decision/v1.py
      thread_continuity/v1.py
      anomaly_detection/v1.py
      promised_reply_check/v1.py
      sender_reputation_summary/v1.py
      user_model_refresh/v1.py
      daily_digest/v1.py

    verbs/                         # the ONLY agent-facing data window (Rule C boundary)
      __init__.py                  # exports for MCP server registration
      find_emails.py               # projection + filter (Rule J)
      hydrate_email.py             # full body, rate-limited 5/turn
      get_thread.py
      list_unread.py
      count_emails.py
      get_sender_summary.py
      propose_action.py            # tier-checked at insert (D6)
      apply_action.py              # requires fresh grant for Tier 2/3
      ask_router.py                # the LLM verb; takes confirmation_token (D1)
      mint_sensitivity_token.py    # Tier-0 verb (D1, A1a)
      compose_digest.py            # structured payload for daily digest (D3)
      schemas.py                   # FindEmailsIn/Out, HydrateEmailIn/Out, etc.

    sync/                          # the ONLY place Microsoft Graph is touched (Rule B boundary)
      __init__.py
      graph_client.py              # MS Graph wrapper, OAuth token refresh -> oauth_state (D9)
      sync_worker.py               # cron-callable cycle: delta fetch -> upsert -> health row
      oauth.py                     # token rotation logic; reads/writes oauth_state

    ingest/                        # the pipeline (Rule A + FR-2 fixed ordering)
      __init__.py
      pipeline.py                  # sensitivity -> coarse -> fine -> summary -> importance -> action -> embedding
      idempotency.py               # sha256(body)+prompt_v+model+task_type (Rule K, FR-2.2)
      backpressure.py              # queue > 500 -> chunked, paused (FR-2.4)
      embedding.py                 # bge-small/nomic-embed via Ollama adapter

    actions/                       # write-back queue + tier system (Rule E + Rule P)
      __init__.py
      types.py                     # ActionType enum, tier_for(), reversibility props (D6)
      authorization.py             # grant minting, in-memory grant cache, second-check helper
      drainer.py                   # pending_actions drain loop, retry chain (D5), Tier-3 ETag (D4)
      cooling_off.py               # pending_send 60s window, /cancel handling
      sensitivity_tokens.py        # in-memory token registry (D12), mint/consume/expire
      reverter.py                  # Tier-1 undo via action_history (D6 reversibility)

    sensitivity/                   # Rule Q implementation
      __init__.py
      classifier.py                # local-only Qwen call wrapper
      patterns.py                  # sensitivity_patterns.yaml loader + match
      routing.py                   # decide allowed models per sensitivity class

    observability/                 # Rule W + FR-7
      __init__.py
      logging.py                   # structured JSON logger, sanitizer pass
      audit.py                     # record_router_call() — the ONLY writer to router_calls
      anomaly.py                   # hourly call-volume baseline + alert
      status.py                    # mailbot status data assembler (read worker_health, etc.)

    notifications/                 # FR-7.4 + FR-7.5
      __init__.py
      tiers.py                     # urgent / important / informational / silent classifier
      digest.py                    # invoked by compose_digest verb; builds structured payload
      dedup.py                     # collapse same-kind 5+/hour -> one
      fatigue.py                   # response-rate self-monitor, urgent-only posture

  router/                          # configuration artifacts (separate from python package "router/")
    policy.yaml                    # the source of truth for routing (Rule I)
    sensitivity_patterns.yaml      # regex / domain / keyword forcing rules (NFR-PRIV-3)

  evals/                           # F8 corpus + scoring rubrics
    email_corpus_v1.jsonl          # frozen, hand-labeled
    scoring_rubrics/
      coarse_class.md
      action_extraction.md
      draft_reply.md
      summary_short.md
      reference_resolution.md      # >= 90% threshold per FR-4.3
    anchors/
      draft_reply_anchors.jsonl    # 20 hand-anchored examples + Adam's scores
      summary_anchors.jsonl
    policy-history/                # v0/v1/v2 snapshots after calibrations
      policy-v0.yaml
      policy-v1.yaml               # post-M4 calibration

  benchmark/                       # F8 runner/scorer/report (uses Router with force_model)
    __init__.py
    runner.py                      # iterates (item x task x model x prompt_v), writes benchmark_runs
    scorer.py                      # objective + subjective (anchor-calibrated auto-eval)
    report.py                      # Pareto frontier, DEMOTE/PROMOTE suggestions
    sampler.py                     # weekly production-call sampler (FR-8.5)
    drift_report.py                # KL-divergence on coarse_class distribution (FR-8.6)
    shadow_runner.py               # shadow-mode prompt rollouts (FR-8.7)

  scripts/                         # operator-facing CLIs + ops
    mailbot                        # bash entry: status / logs / pause / resume / sync-now / replay / revert
    setup_vps.sh                   # one-time VPS bootstrap (Docker, user, volumes, perms)
    deploy.sh                      # docker save + scp + docker load + rolling restart of mailbot-api
    backup.sh                      # nightly SQLite .backup + config tarball + optional B2 rsync
    restore.sh                     # restore from a backup tarball
    check_env.py                   # startup env-var validator (refuse start if missing)

  hermes-config/                   # Hermes container's mounted /opt/data
    config.yaml                    # provider: custom -> mailbot-api:8000/v1; fallback_providers; aux routing
    SOUL.md                        # defender persona (NFR-PERSONA-1)
    AGENTS.md                      # operational rules (J/N/P/R as agent behavior)
    skills/
      mailbot/
        SKILL.md                   # how MailBot uses its verbs
    cron/
      jobs.json                    # daily_digest_0800, weekly_drift_sun_0900, weekly_sampling_sun_0930
    sessions/                      # Hermes-managed runtime state
    memories/                      # Hermes-managed memory store

  tests/
    unit/
      router/
        test_router.py
        test_policy.py
        test_budget.py
        test_lanes.py
        test_response_cache.py
      verbs/
        test_find_emails.py
        test_propose_action.py
        test_ask_router_token.py   # D1 confirmation_token path
      actions/
        test_drainer.py            # D4 conflict resolution, D5 retry classification
        test_authorization.py
        test_sensitivity_tokens.py # D12 in-memory TTL
      sensitivity/
        test_classifier.py
        test_patterns.py
      ingest/
        test_pipeline.py
        test_idempotency.py
      notifications/
        test_tiers.py
        test_fatigue.py
    integration/
      test_chat_completions_endpoint.py
      test_mcp_server.py
      test_end_to_end_classify.py  # sync mock -> ingest -> router -> SQL
      test_oauth_rotation.py       # D9 rotated-token persistence
      test_policy_hot_reload.py    # D11 watchfiles + validation
    fixtures/
      mock_graph_responses.json
      sample_emails.jsonl
      ephemeral_db.py              # in-mem SQLite fixture
    conftest.py

  docs/
    auth-recovery.md               # FR-1.6 OAuth re-auth procedure (manual recovery)
    deployment-runbook.md          # SSH-in, status, logs, common ops
    incident-playbook.md           # budget breach, sync stuck, sensitivity leak
    external/                      # vendored docs (FastAPI archive already here)
      fastapi/

  _bmad-output/                    # BMad planning artifacts (already exists)
    planning-artifacts/
      prds/
      architecture.md              # this document
    brainstorming/
```

### Architectural Boundaries

**Process boundaries (3 containers + 2 internal processes):**

| Container | Process(es) | Reads | Writes | Holds |
| --- | --- | --- | --- | --- |
| `mailbot-hermes` | hermes runtime | mailbot-api (HTTP + MCP), Discord | Discord, mailbot-api | Discord token, Hermes-internal state |
| `mailbot-api` | `uvicorn main:app` + `python -m mailbot_api.worker` | SQLite, Ollama, Anthropic, MS Graph | SQLite, structured logs (stdout) | **ANTHROPIC_API_KEY** (Rule F.1) |
| `ollama` | ollama serve | model files (volume) | nothing external | nothing |

**Network boundary:**

- Internal: `mailbot-net` Docker network connects all 3 containers. Hermes → `mailbot-api:8000`. mailbot-api → `ollama:11434`.
- External (outbound only): mailbot-api → MS Graph, mailbot-api → Anthropic API, mailbot-hermes → Discord, mailbot-hermes → Anthropic (fallback_providers only — NFR-OPS-6).
- External (inbound): none in production. SSH to the VPS host only.

**Code boundaries enforced by patterns (Implementation Patterns rules 1–4):**

- `router/models.py` is the only file that imports `ollama` or `anthropic`. (Rule I.)
- `mailbot_api/sync/graph_client.py` is the only file that imports `requests` for `graph.microsoft.com`. (Rule B.) All requests carry the `Prefer: IdType="ImmutableId"` header per Story 1-10.
- `mailbot_api/db/queries.py` is the only file with SQL literals. (Rule C.)
- `mailbot_api/config.py` is the only file that reads `os.environ`. (Rule F.)
- `mailbot_api/observability/audit.py` is the only file that writes to `router_calls`.

**Verb API boundary (the agent's data window):**

- Hermes (as MCP client) ↔ `mailbot_api.mcp_server` (FastMCP). Verbs are the public surface.
- Verbs return `<Noun>Out` Pydantic models. Errors-as-data via `error: RouterError | None` field. No exceptions cross this boundary.

**Router boundary (Rule I single source of truth):**

- All LLM calls flow through `router.ask_router(...)`. The benchmark runner and cache warmer count.
- Hermes auxiliary tasks (compression, title generation) call via `/v1/chat/completions` — Router receives them as ordinary calls tagged `caller_origin="hermes-aux-*"` (D2).

**Data boundary (SQLite is the agent's world — Rule B):**

- SQLite is the system of record for everything the agent sees: emails, threads, senders, derivations, pending_actions, grants, router_calls, sensitivity grants (audit only), worker_health, oauth_state.
- Microsoft Graph data only flows into SQL via `sync/`. No verb queries Graph live.
- Anthropic / Ollama responses only flow into SQL via Router (audit + response cache + derived-field writes). No verb writes to provider state.

### Requirements-to-Structure Mapping

| FR area | Primary location | Supporting locations |
| --- | --- | --- |
| **F1 Outlook Sync** (FR-1.1..7) | `mailbot_api/sync/` | `db/migrations/001_init.sql` (emails, sync_state), `db/migrations/003_oauth_state.sql`, `scripts/mailbot sync-now` |
| **F2 Ingest Pipeline** (FR-2.1..7) | `mailbot_api/ingest/` | `prompts/<task_type>/v1.py` (sensitivity, coarse, fine, summary, importance, action, embedding), `db/queries.py` (derived-field writes) |
| **F3 Router & Tiered LLM** (FR-3.1..10) | `mailbot_api/router/` | `router/policy.yaml`, `prompts/`, `db/migrations/001_init.sql` (router_calls, response_cache), `observability/audit.py` |
| **F4 Conversational Control** (FR-4.1..8) | `hermes-config/` (Discord, persona, skills) + `mailbot_api/verbs/` | `prompts/intent_parsing_chat`, `prompts/reference_resolution`, `prompts/draft_reply`, `prompts/multi_turn_refinement`, `actions/cooling_off.py` (FR-4.5 /cancel) |
| **F5 Authorized Actions** (FR-5.1..7) | `mailbot_api/actions/` | `verbs/propose_action.py`, `verbs/apply_action.py`, `verbs/mint_sensitivity_token.py`, `db/migrations/002_pending_actions.sql`, `db/migrations/007_sensitivity_grants.sql` |
| **F6 Cost Governance** (FR-6.1..7) | `mailbot_api/router/budget.py` + `router/limits.py` | `router/pricing.py`, `observability/anomaly.py`, `verbs/ask_router.py` (force_model), `policy.yaml` |
| **F7 Observability & Trust** (FR-7.1..7) | `mailbot_api/observability/` + `mailbot_api/notifications/` | `scripts/mailbot`, `verbs/compose_digest.py`, `hermes-config/cron/jobs.json` (8am digest), `db/migrations/004_worker_health.sql` |
| **F8 Eval & Calibration** (FR-8.1..7) | `benchmark/` + `evals/` | Uses Router with `force_model` (Rule I); `db/migrations/005_benchmark_runs.sql`, `evals/policy-history/` |

**Cross-cutting concerns → location:**

- **Cost discipline (Rule Ω):** `router/policy.yaml` + `router/budget.py` + `router/pricing.py` + `benchmark/` + policy.yaml annotations on every escalation
- **Sensitivity routing (Rule Q):** `sensitivity/` + `router/router.py` (precondition layer) + `actions/sensitivity_tokens.py` + `verbs/mint_sensitivity_token.py`
- **Authorization (Rule P):** `actions/types.py` + `actions/authorization.py` + `actions/drainer.py` + `verbs/propose_action.py`
- **Idempotency & caching (Rules A/K/M):** `ingest/idempotency.py` + `router/response_cache.py` + `router/cache_warmer.py` + derived-field companion columns
- **Observability (Rule W):** `observability/` + `scripts/mailbot` + structured logging in every module
- **Dev-prod parity (Rules S/T/V):** `docker-compose.yml` + `docker-compose.override.yml` + `Makefile` + `scripts/setup_vps.sh` + `scripts/deploy.sh` + named volumes

### Integration Points

**Internal communication:**

- **Hermes → mailbot-api HTTP:** `POST /v1/chat/completions` (Hermes's LLM provider), `POST /v1/embeddings`, `GET /health` (deploy gate).
- **Hermes → mailbot-api MCP:** verb invocations as MCP tools (stdio or HTTP transport depending on Hermes config; MCP SDK supports both).
- **mailbot-api uvicorn ↔ worker:** SQLite shared state. Cross-process signals via SQLite event row (rare) or filesystem watch (policy.yaml — D11).
- **mailbot-api → ollama:** HTTP to `http://ollama:11434` for chat completions + embeddings (via `ollama` Python client).
- **mailbot-api → Anthropic:** HTTPS to `api.anthropic.com` (via `anthropic` Python client). **Only from the Router process** (Rule F.1).

**External integrations:**

- **Microsoft Graph (sync only):** OAuth 2.0 with rotated refresh tokens persisted to `oauth_state` (D9). Delta queries every 4 min.
- **Anthropic API:** Direct, no proxy. Ephemeral prompt caching on SYSTEM blocks. Models pinned: `claude-haiku-4-5-20251001`, `claude-opus-4-7`.
- **Discord:** Hermes-managed bot in a private server Adam shares.
- **(Optional) Backblaze B2:** Nightly rsync of backup tarballs (`scripts/backup.sh --b2`).

**Data flow (chat query, end-to-end):**

```text
Adam (Discord)
  -> Hermes Discord adapter
    -> Hermes intent parsing (Qwen via Router /v1/chat/completions)
      -> mailbot-api Router: classify "show me unread"
        -> Qwen (Ollama)
        -> router_calls row written via observability/audit.py
      -> Hermes decides to call MCP tool list_unread()
        -> mailbot-api MCP server
          -> verbs/list_unread.py
            -> db/queries.py (projection only - Rule J)
              <- SQLite (WAL read, sub-ms)
          <- ListUnreadOut payload
        <- MCP response
      -> Hermes voices the response in defender persona
    <- Discord message to Adam
```

**Data flow (ingest of a new email):**

```text
Cron (mailbot-api internal scheduler, every 4 min) [D13]
  -> sync/sync_worker.py
    -> graph_client.py (delta fetch)
      <- MS Graph
    -> db/queries.py (upsert emails, threads, senders)
  -> ingest/pipeline.py (drains unprocessed queue, 100/batch) [FR-2.4]
    For each email_id, in order [FR-2.3]:
      -> router.ask_router(task_type="sensitivity_class", ...)  [Qwen, local-only Rule Q]
        -> router_calls row + emails.sensitivity column write
      -> router.ask_router(task_type="coarse_class", ...)        [Qwen]
      -> router.ask_router(task_type="fine_class", ...)          [Qwen, escalate -> Haiku]
      -> router.ask_router(task_type="summary_short", ...)        [Qwen]
      -> router.ask_router(task_type="importance_scoring", ...)  [Haiku]
      -> router.ask_router(task_type="action_extraction", ...)   [Haiku, escalate -> Opus]
      -> router.ask_router(task_type="embedding", ...)           [bge-small via Ollama]
    -> worker_health heartbeat row [D7]
```

**Data flow (Tier-3 send):**

```text
Adam (Discord): "draft a reply to that and send it"
  -> Hermes -> Router (Opus via /v1/chat/completions for draft_reply)
  -> Hermes shows draft via Discord
  -> Adam: "yes, send"
  -> Hermes -> MCP propose_action(email_id, action_type="send_reply", payload={body, to})
    -> verbs/propose_action.py
      -> actions/types.tier_for("send_reply") == 3
      -> INSERT pending_actions (status="cooling_off", change_marker_at_propose=...)
      -> respond with action_id
  -> Hermes: "60s to /cancel"
  -> 60s elapses
  -> actions/drainer.py picks up action
    -> re-checks grant for action_type="send_reply"
    -> Tier 3: ETag match check vs current emails.change_marker [D4]
    -> if pass: graph_client.send_reply(...)
      -> On 2xx: pending_actions.status="applied", budget_consumed=true (1 of 20)
      -> On 429/503/timeout: retry (1s/4s/16s, 3 retries) [D5]
      -> On 4xx non-429: status="failed", reason=..., budget_consumed=true, urgent chat alert
```

### File Organization Patterns (recap of Implementation Patterns invariants)

- **Configuration files** all live at repo root or in `hermes-config/`. No nested configs scattered through `mailbot_api/`. Pydantic loads + validates them at startup.
- **Source organization** follows bounded-responsibility-per-package — every package is named for what it owns, and only that package owns it.
- **Tests** mirror source layout under `tests/unit/` and `tests/integration/`. No co-located tests. Fixtures shared via `tests/fixtures/` and `conftest.py`.
- **Assets:** no static assets in v1 (no web UI). Would land in `assets/` at repo root if added later.

### Development Workflow Integration

**Development server:**

- `make local` runs `docker compose -f docker-compose.yml -f docker-compose.override.yml up`.
- Override file bind-mounts `mailbot_api/`, `verbs/`, `prompts/`, `router/` into the `mailbot-api` container so edits hot-reload via uvicorn's `--reload` flag.
- Override exposes dev ports for direct curl: `8000:8000` (mailbot-api HTTP), `11434:11434` (ollama).

**Build process:**

- `make build` runs `docker compose build mailbot-api` against `docker/Dockerfile.mailbot-api` (multi-stage: builder installs deps, runtime copies only what's needed).
- Hermes and ollama use upstream images — never rebuilt locally (Rule T).

**Deploy:**

- `make deploy` runs `scripts/deploy.sh`: build → `docker save` → `scp` to VPS → `docker load` → rolling restart of `mailbot-api` only → `/health` check → 30s log tail.
- Hermes and ollama updated separately via `docker compose pull` on VPS.

**State survival:**

- Named volumes per addendum A1: `mailbot_db`, `mailbot_ollama`, `mailbot_hermes_data`, `mailbot_logs`. `docker compose down && up` is a non-event (Rule V).
- `oauth_state` row in SQLite means token rotation survives container restarts (D9).
- All migrations applied at `mailbot-api` startup before serving traffic.

## Architecture Validation Results

### Coherence Validation

**Decision compatibility:** All 14 architectural decisions (D1–D14) work together without contradiction. The Router-centered model (Rule I + F.1) is reinforced by every downstream choice — verb boundary, two-process container, split cron, and policy reload all flow through or around the Router as the single source of LLM-call truth. The one deliberate relaxation (D13 split cron) is documented as a trade between Rule X centralization and FR-1.x sync reliability.

**Pattern consistency:** Naming conventions (snake_case throughout), the bounded-responsibility-per-package rule, and the error-as-data discipline align with every architectural decision. The 10 enforcement rules in Implementation Patterns directly support the 5 hard boundaries (Router / verbs / sync / config / audit) named in Project Structure.

**Structure alignment:** Every file in the directory tree has an architectural justification traceable to a PRD FR or to a D1–D14 decision. No orphan modules.

### Requirements Coverage Validation

**Functional requirements:** 62 / 62 FRs covered with concrete location. Spot-checks: FR-1.6 → `sync/oauth.py` + `oauth_state` (D9); FR-2.3 sensitivity-first invariant → Router precondition layer + ingest ordering; FR-3.6 cache warmer → internal scheduler (D13); FR-4.3 reference-resolution gate → F8 calibration; FR-5.7 per-session confirmation → D1 + D12; FR-7.5 anti-fatigue posture → `notifications/fatigue.py`; FR-7.7 daily digest → D3 hybrid; FR-8.x eval system → `benchmark/` + Hermes weekly crons.

**Non-functional requirements:** 24 / 24 NFRs addressed.

- NFR-PRIV-0 (VPS-as-trust-boundary): implicit in network boundary (Anthropic key isolated to mailbot-api; Rule Q gates egress).
- NFR-SEC-1..6: Router boundary + config.py boundary + secrets-in-.env-only + sanitized errors all in place.
- NFR-OPS-1..6: Docker dev-prod parity + single-command deploy + named volumes + health endpoints + nightly backups + Hermes fallback all named with file locations.
- NFR-PERF-1..4: chat p95 ≤ 5s served by D7 two-process split (sync can't block chat) + D8 WAL+executor (writes can't block reads) + D10 strict priority (chat preempts batch).
- NFR-HW-1..3: 2 vCPU / 8 GB / no-GPU is the load-bearing constraint behind D7, the no-7B commitment, and the single-3B-local Qwen choice.
- NFR-PERSONA-1..3: SOUL.md + AGENTS.md + 4 behavioral anti-patterns are deliverables in `hermes-config/`.

**Open Questions:** OQ-1 (attachments) and OQ-5 (cascading routing) remain deferred per PRD §1.5/§9 — architecture explicitly does not implement them at v1. OQ-2 (sync conflicts) is _closed_ by D4. OQ-3, OQ-4, OQ-6, OQ-7 remain as documented PRD open questions; OQ-6 (Honcho) is implicit in the user-model storage clarification below.

### Implementation Readiness Validation

**Decision completeness:** D1–D14 fully documented with chosen option, rationale, cascading implications, and file locations. Five new stable error codes named. Four new tables (`oauth_state`, `action_grants`, `action_history`, `worker_health`) named with column lists.

**Structure completeness:** Full directory tree pinned to leaf-file granularity. Eight FR areas mapped to primary + supporting locations. Three end-to-end data flow diagrams (chat query, ingest, Tier-3 send).

**Pattern completeness:** 10 enforceable invariants with concrete good/anti-pattern examples. Lint rules named for ruff + mypy enforcement.

### Gap Analysis Results

**Critical gaps:** none.

**Important gaps:**

1. **User-model storage location.** The `user_model_refresh` task (policy v0, Opus, batched) refreshes Adam's user model, but where the refreshed model lands is not pinned. **Resolution:** Adam's user model lives in Hermes persistent memory (matches Rule X, lets `tone_style_mirror` and `importance_scoring` access it via Hermes context compression). MailBot does not maintain a parallel SQL `user_models` table. The output of the `user_model_refresh` task is written via Hermes memory APIs from the agent's own task handling.

**Minor gaps (nice-to-have, non-blocking):**

1. `PolicyTable` Pydantic schema not formally defined in this document — will be derived from policy v0 task table and addendum A3 during M2 implementation.
2. `worker_health` columns named but no DDL stub included — will land with `004_worker_health.sql` migration in M1.
3. First-pull SQLite bulk-insert tuning (10–30 min first sync per FR-1.2) not addressed — acceptable to defer until M1 measures it.
4. `/cancel` race window at the 60s drainer boundary — `UPDATE pending_actions SET status='cancelled' WHERE id=? AND status='cooling_off'` resolves it; will be enforced in the drainer code path.

### Validation Issues Addressed

The Important gap (user-model storage) is closed by the resolution above: Adam's user model lives in Hermes memory, not in a MailBot SQL table. This aligns with Rule X (Hermes-native integration) and avoids inventing a parallel memory store. All minor gaps are accepted as implementation-phase details, not blocking.

### Architecture Completeness Checklist

#### Requirements Analysis

- [x] Project context thoroughly analyzed
- [x] Scale and complexity assessed
- [x] Technical constraints identified
- [x] Cross-cutting concerns mapped

#### Architectural Decisions

- [x] Critical decisions documented with versions
- [x] Technology stack fully specified
- [x] Integration patterns defined
- [x] Performance considerations addressed

#### Implementation Patterns

- [x] Naming conventions established
- [x] Structure patterns defined
- [x] Communication patterns specified
- [x] Process patterns documented

#### Project Structure

- [x] Complete directory structure defined
- [x] Component boundaries established
- [x] Integration points mapped
- [x] Requirements to structure mapping complete

### Architecture Readiness Assessment

**Overall Status:** **READY FOR IMPLEMENTATION** — all 16 checklist items confirmed; one Important gap closed inline; no Critical gaps remain.

**Confidence Level:** **High.** The PRD is unusually decision-dense (21 ratified rules; comprehensive reconciliation reports already filed before architecture), the policy v0 task table provides concrete routing decisions ready for benchmark validation, and every architectural decision in this document maps to a specific file or module with a named bounded responsibility.

**Key strengths:**

- **Rule Ω made operational at every layer** — policy.yaml as cost-discipline artifact, 4-layer budget guard, default-Qwen escalation requiring benchmark citation, Hermes aux-task routing under the same discipline, weekly drift + sampling closing the loop.
- **Single Router as architectural center** — falls out of Rule F.1, not chosen for its own sake; means cost accounting, prompt caching, budget guards, sensitivity gating, audit log, and routing policy all converge naturally.
- **Authorization is verb-API enforced (Rule P), not agent-trusted** — the 4-tier model + scoped grants + cooling-off + 20/day cap + Tier-3 ETag is built such that "agent decides to skip a check" is structurally impossible.
- **Sensitivity routing has provenance** — D1 + D12 give every sensitive-to-API call a single mint/consume audit pair on `router_calls`.
- **Reliability isolated from agent runtime** — D13 split cron + D7 two-process container means sync and cache warming survive Hermes crashes, preserving the "availability trust" of §1.3.
- **First-class evals from day one (F8)** — corpus, runner, scorer, report, weekly sampling, drift detection, shadow rollout — built before policy.yaml is trusted.

**Areas for future enhancement (post-MVP backlog):**

- Cascading routing per task (OQ-5; revisit once benchmark data lands in M6.8)
- Honcho memory upgrade if Hermes default memory turns out shallow (OQ-6)
- Attachment handling beyond `has_attachments` boolean (OQ-1)
- `pause_sender` Tier-2 action (deferred from D6)
- Per-lane WRR if batch starvation ever bites (deferred from D10)

### Implementation Handoff

**AI Agent Guidelines:**

- Follow all architectural decisions exactly as documented.
- Use implementation patterns consistently — the 10 enforcement rules are PR blockers, not suggestions.
- Respect bounded-responsibility-per-package and the 5 hard code boundaries (Router / verbs / sync / config / audit).
- Refer to this document and the PRD as joint sources of truth. When they disagree, this document wins for _how_; the PRD wins for _what_.
- For every escalation to a non-Qwen model in code or policy.yaml, cite a benchmark run (Rule Ω discipline made operational).

**First implementation priority:**

Bootstrap M1 per the initialization sequence in Starter Template Evaluation:

1. Create the directory tree
2. Pin `requirements.txt` with the verified May 2026 versions
3. Stand up `docker-compose.yml` for the 3-container stack
4. Apply migration `001_init.sql` (emails, threads, senders, sync_state, router_calls, response_cache, derivations)
5. Implement `sync/sync_worker.py` and `sync/graph_client.py` end-to-end with a real Outlook sync
6. Smoke test: `make local`, run a sync, see emails appear in SQLite, `mailbot status` returns within 10s.

This unblocks M2 (Router + local LLM), which unblocks M3 (Anthropic tier + sensitivity), which unblocks M4 (evals + first calibration), which unblocks M5 (MVP).

## Reference Material

Authoritative external documentation lives in [`docs/external/`](../../docs/external/) (locally archived, paths mirror upstream URL structure):

- **Microsoft Graph + Azure** — [`docs/external/learn-microsoft-azure/`](../../docs/external/learn-microsoft-azure/). Entry point is [`SITE-MAP.md`](../../docs/external/learn-microsoft-azure/SITE-MAP.md). Tier-S pages cover the load-bearing sync surface: delegated auth (`graph/auth-v2-user.md`, `graph/auth/auth-concepts.md`), delta query semantics (`graph/delta-query-overview.md`), message resource properties + immutable IDs (`graph/api/resources/message.md`), MIME content (`graph/outlook-get-mime-message.md`), and the Python SDK tutorial (`graph/tutorials/python-email.md`). These are the authoritative reference for any sync-layer or OAuth-layer change.
- **FastAPI** — [`docs/external/fastapi/`](../../docs/external/fastapi/).

When implementing or modifying any code that touches Microsoft Graph, Outlook, or Microsoft Entra, **consult the archived docs first**. The post-Epic-1 review of these archives surfaced four correctness gaps in Stories 1-5/1-7 (refresh-token bootstrap missing, `changeKey` vs `@odata.etag`, message-ID rotation on folder moves, missing 410/syncStateNotFound recovery) that became Stories 1-9 and 1-10. The pattern is: archived docs > web fetch > guesswork.
