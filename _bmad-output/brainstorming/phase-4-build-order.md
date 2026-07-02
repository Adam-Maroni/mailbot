# MailBot — Phase 4: Build-Order Checklist

**Companion to:** [brainstorming-session-2026-05-31-1430.md](brainstorming-session-2026-05-31-1430.md) · [policy-v0.yaml](policy-v0.yaml)
**Date:** 2026-05-31
**Author:** Adam (brainstorming with assistant)

---

## How to use this document

This is the **prioritized build plan** for MailBot. Six milestones, sequential, each shippable. Inside each milestone, tasks have IDs (`M1.1`, `M1.2`, …) and explicit dependencies.

**Conventions:**

- **Effort:** T-shirt sizes — **S** (≤ half day), **M** (1–2 days), **L** (3–5 days), **XL** (1–2 weeks). Don't believe them too literally; they're for relative ordering.
- **Rules:** which architectural rules (Ω, A–X) the task implements.
- **Deps:** which earlier tasks must be done first.
- **MVP:** `must` (ship blocker), `should` (strong default, can defer if pressed), `nice` (v1.1).
- **Verify:** the concrete observable that says "done."
- **⚠ Bite:** thing that will trip you up if you don't plan for it.

**MVP line:** End of **M5**. M6 (VPS deploy) is the real launch. Everything tagged `nice` can land post-MVP.

**Total scope:** ~80 tasks across 6 milestones. The shape of "real work, no padding."

---

## Quick map

| Milestone                         | Goal                                                 | Ship criterion                                                                |
| --------------------------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------- |
| **M1 — Foundation & scaffold**    | Local repo, Docker, SQLite schema, Outlook sync      | `docker compose up` locally; sync runs; emails in SQL                         |
| **M2 — Router & local LLM**       | Ollama + Qwen 3B + Router with `/v1/chat/completions` | `curl` returns Qwen response, logged to `router_calls`                        |
| **M3 — Anthropic tier + budget**  | Add Haiku/Opus; budget guards; cache; sensitivity    | `policy.yaml` switches a task between tiers; budget gate fires                |
| **M4 — Eval system**              | Corpus + runner + scorer + report; first calibration | Benchmark report shows accuracy/latency/cost per (task, model)                |
| **M5 — Hermes integration**       | MCP verbs; SOUL/AGENTS; Discord; cron sync           | Discord message to MailBot → coherent reply that queried email via verbs     |
| **M6 — VPS deployment**           | Hostinger deploy; backups; observability             | Running on VPS unattended for 1 week, you trust it                           |

---

## M1 — Foundation & scaffold

**Goal:** A working local dev environment that talks to Outlook (read-only) and stores emails in SQLite. No LLM yet. This is the *least glamorous* milestone — do not skip it.

### M1.1 — Repo skeleton & tooling

- **Effort:** S · **Deps:** none · **MVP:** must · **Rules:** —
- Create directory layout: `mailbot_api/`, `docker/`, `scripts/`, `evals/`, `hermes-config/`, `tests/`.
- Initialize Python project: `pyproject.toml` with pinned deps (`fastapi`, `uvicorn`, `sqlmodel` or `sqlalchemy`, `pydantic>=2`, `httpx`, `msal`, `mcp`, `ollama`, `anthropic`).
- `.gitignore` blocking `.env`, `*.key`, `__pycache__`, `data/`, `.venv/`, `*.db`.
- `Makefile` skeleton: `make build`, `make local`, `make logs`, `make status`, `make deploy`, `make backup` (most are stubs at this point).
- `README.md` with one-paragraph description + how to run locally.
- **Verify:** `make local` exits cleanly (even as a no-op).

### M1.2 — `.env` discipline (Rule U)

- **Effort:** S · **Deps:** M1.1 · **MVP:** must · **Rules:** F, U
- Create `.env.example` listing every required variable with comments, no values:
  - `ANTHROPIC_API_KEY` — Anthropic API key (mailbot-api process only)
  - `OUTLOOK_CLIENT_ID`, `OUTLOOK_CLIENT_SECRET`, `OUTLOOK_TENANT_ID`, `OUTLOOK_REFRESH_TOKEN` — Microsoft Graph auth
  - `DISCORD_BOT_TOKEN` — Discord bot (M5)
  - `MAILBOT_DB_PATH=/data/mailbot.db`
  - `MAILBOT_ROUTER_KEY` — internal API key Hermes uses to call our Router
  - `OLLAMA_URL=http://ollama:11434`
  - `MAILBOT_TZ=Europe/Paris`
- `scripts/check_env.py` reads `.env.example`, walks every key, refuses startup if any are missing or empty.
- Wire `check_env.py` into the `mailbot-api` container entrypoint.
- **Verify:** removing any var from `.env` makes startup fail with a clear "missing X" message.
- **⚠ Bite:** never let yourself commit `.env`. Add a pre-commit hook that aborts on `.env` in staged files if you want belt-and-braces.

### M1.3 — Docker Compose skeleton (Rule S, V)

- **Effort:** M · **Deps:** M1.1 · **MVP:** must · **Rules:** S, V
- `docker-compose.yml` with three services: `mailbot-hermes` (placeholder image for now), `mailbot-api`, `ollama`.
- Shared bridge network `mailbot-net`.
- Named volumes: `mailbot_db`, `mailbot_ollama`, `mailbot_hermes_data`, `mailbot_logs`.
- `docker-compose.override.yml` for local dev: source code bind-mount on `mailbot-api`, expose dev ports (8000 mailbot-api, 11434 ollama).
- `docker/Dockerfile.mailbot-api`: python:3.12-slim base, copy code, install deps, run uvicorn.
- `.dockerignore` blocking `.env`, `.venv`, `__pycache__`, `*.db`, tests/, evals/.
- **Verify:** `make local` brings up 3 containers, all healthy, but mailbot-api just returns "hello world" on `/health`.
- **⚠ Bite:** Windows line-ending differences in shell scripts inside containers. Add `*.sh text eol=lf` to `.gitattributes`.

### M1.4 — SQLite schema (Rule A, E, K)

- **Effort:** M · **Deps:** M1.3 · **MVP:** must · **Rules:** A, E, K
- SQLAlchemy / SQLModel models, plus an Alembic-equivalent migration story (or just `Base.metadata.create_all` if you accept manual migrations for now — for a personal project that's fine).
- Tables:
  - `senders` (id, address, display_name, reputation, first_seen, summary, summary_prompt_v)
  - `threads` (id, subject_normalized, first_seen, last_activity, importance)
  - `emails` — raw fields + **derived columns** per Rule A:
    - raw: `graph_id`, `received_at`, `from_id`, `subject`, `body_text`, `body_hash`, `thread_id`
    - derived: `class_coarse`, `class_coarse_conf`, `class_coarse_prompt_v`, `class_coarse_at`, `class_coarse_model`
    - same shape repeated for: `class_fine`, `importance_score`, `summary_short`, `sensitivity`, `suggested_action`, `embedding` (BLOB or separate table)
    - `processed_at`, `processed_pipeline_v`
  - `derivations` (id, email_id, task_type, prompt_v, model, output_raw, output_parsed, confidence, ts) — audit trail per Rule A
  - `pending_actions` (id, email_id, action_type, payload_json, tier, status, created_at, drained_at, result) — Rule E queue
  - `router_calls` schema as documented in Rule I (filled later in M2, table created now)
- Idempotency key implementation: `sha256(body) + prompt_v + model + task_type` per Rule K.
- **Verify:** Python REPL can create + insert + query a fake email row with full derived-field shape.
- **⚠ Bite:** SQLite + WAL mode is required if you want concurrent reads while sync writes. Set `PRAGMA journal_mode=WAL` on init.

### M1.5 — Outlook Graph auth (read-only)

- **Effort:** L · **Deps:** M1.2, M1.4 · **MVP:** must · **Rules:** D, F
- Register an Azure AD app (yes, you'll do this in the Azure portal once). Permissions: `Mail.Read`, `User.Read`. Note client_id, tenant_id, generate a secret.
- Headless OAuth flow: use the **device code flow** the first time to obtain a refresh token, store in `.env` (manual one-time copy). After that, `msal` refreshes silently.
- `mailbot_api/outlook/auth.py` — thin wrapper around MSAL; exposes `get_access_token()` that auto-refreshes.
- **Verify:** Python script prints your inbox folder count via Graph.
- **⚠ Bite:** Microsoft refresh tokens can expire after 90 days of inactivity. On VPS, the daily sync running prevents this; in dev, if you stop syncing for months you'll need to re-auth. Set a calendar reminder.

### M1.6 — Sync layer (Rule D, K — read-only first)

- **Effort:** L · **Deps:** M1.5, M1.4 · **MVP:** must · **Rules:** D, K
- `mailbot_api/sync/sync.py` — function `sync_once()`:
  - Use Graph **delta query** (`/me/mailFolders/Inbox/messages/delta`) — stores the delta link in a `sync_state` table, fetches only new/changed since last call.
  - For each new message: insert into `emails` (raw fields only — derivations come in M2/M3).
  - For each modified message: update mutable fields (isRead, parentFolderId).
  - For each deleted message: mark `deleted_at` rather than hard-delete (audit trail).
  - Sender upsert into `senders`.
  - Thread upsert into `threads` keyed by `conversationId`.
- CLI entrypoint: `python -m mailbot_api.sync.sync_once` runs one sync.
- Make it idempotent — running twice with no inbox changes does nothing.
- **Verify:** run `sync_once` against your real inbox; SQL `SELECT COUNT(*) FROM emails` matches roughly your inbox size; running again is a no-op.
- **⚠ Bite:** Graph delta queries return up to 250 items per page with a `@odata.nextLink`. Paginate properly. First-time sync of a large inbox can take 10–30 min.
- **⚠ Bite:** Don't attempt to backfill attachments yet — Rule's TBD #27. For now, skip them. Store `has_attachments` boolean only.

### M1.7 — Write-back queue worker (Rule E)

- **Effort:** M · **Deps:** M1.6 · **MVP:** must · **Rules:** E
- `mailbot_api/sync/drain.py` — polls `pending_actions WHERE status='pending'`, applies each via Graph, records result.
- Supports actions: `mark_read`, `mark_unread`, `move_to_folder`, `archive`, `delete`, `send_reply` (most enforced as Tier 3 in M5).
- Failure handling: 3 retries with exponential backoff, then `status='failed'` with error stored.
- For M1 this is a stub that just *handles* mark_read and move_to_folder — the rest are scaffolded with TODO + Tier 3 refusal.
- **Verify:** insert a `mark_read` action manually into SQL, run drain worker, see the email marked read in Outlook.

### M1.8 — Logging foundation (Rule W)

- **Effort:** S · **Deps:** M1.3 · **MVP:** must · **Rules:** W
- Structured JSON logging via `structlog` or stdlib `logging` with JSON formatter.
- Every log line has: timestamp, level, module, message, plus context-specific fields.
- All errors logged with sanitized stack (no API keys, no Graph URLs with tokens) per Rule F.
- Logs go to stdout (Docker captures); also tee'd to `/data/logs/mailbot-api.log` (rotated by Docker `--log-opt`).
- **Verify:** `docker compose logs mailbot-api` shows JSON-formatted lines.

### M1.9 — `mailbot` CLI scaffolding (Rule W)

- **Effort:** S · **Deps:** M1.6 · **MVP:** should · **Rules:** W
- `scripts/mailbot` — a thin Click/Typer CLI exposing: `status` (DB last sync, email count, queue depth, no LLM stats yet), `logs` (tails Docker logs), `sync-now` (manually trigger sync). More commands added in later milestones.
- **Verify:** `mailbot status` from your laptop prints DB stats.

**M1 ship criterion:** `docker compose up` starts cleanly, `make sync-now` populates the SQL DB with real emails from your Outlook inbox, `mailbot status` reports the count. No LLM, no Hermes yet.

---

## M2 — Router & local LLM

**Goal:** The Router exists as an OpenAI-compatible service, talks to Qwen 3B via Ollama, logs every call. Single-tier for now (no Anthropic yet) so you validate the routing + logging plumbing before adding paid models.

### M2.1 — Ollama in compose, models pre-pulled

- **Effort:** S · **Deps:** M1.3 · **MVP:** must · **Rules:** —
- Add `ollama/ollama` image to compose, mount `mailbot_ollama:/root/.ollama`.
- Init script: `scripts/init_ollama.sh` — runs once after first container start, `docker exec ollama ollama pull qwen2.5:3b-instruct-q4_K_M`, `docker exec ollama ollama pull nomic-embed-text`.
- Add to `Makefile`: `make init` runs this once.
- **Verify:** `curl http://localhost:11434/api/generate -d '{"model":"qwen2.5:3b","prompt":"hello"}'` returns a response.
- **⚠ Bite:** Model pull is 2 GB. Slow over residential internet. Do it once, the volume preserves it forever after.

### M2.2 — Pricing table (Rule I)

- **Effort:** S · **Deps:** M1.1 · **MVP:** must · **Rules:** I
- `mailbot_api/router/pricing.py` — dict mapping model_id → `(input_per_mtok, output_per_mtok, cached_input_per_mtok)`.
- Initial values: qwen-3b = (0, 0, 0); claude-haiku-4-5 ≈ (1, 5, 0.1); claude-opus-4-7 ≈ (15, 75, 1.5). These are starting estimates; verify against the real Anthropic pricing page when you wire M3.
- Function `estimate_cost_usd(model, tokens_in, tokens_out, cached_in=0) -> float`.
- **Verify:** unit test for each model: known token counts → expected USD.

### M2.3 — `router_calls` write helper (Rule I)

- **Effort:** S · **Deps:** M1.4, M2.2 · **MVP:** must · **Rules:** I
- `mailbot_api/router/log.py` — `log_router_call(...)` writes a row per call. Async write; never block the response on logging failure.
- All columns per Rule I (model_chosen, reason, tokens, cost, latency, outcome, caller, email_id).
- **Verify:** call helper from REPL, row appears in SQL.

### M2.4 — Prompt module registry (Rule A, H, M)

- **Effort:** M · **Deps:** M1.1 · **MVP:** must · **Rules:** A, H, M
- Directory layout: `mailbot_api/prompts/<task_type>/v<N>.py` with `VERSION`, `SYSTEM`, `USER_TEMPLATE`, `OUTPUT_SCHEMA`.
- Registry: walk the `prompts/` directory at startup, build `dict[(task_type, version)] -> PromptModule`.
- Each PromptModule has `render(args) -> (system, user)` for assembly.
- Implement v1 of these tasks for M2: `coarse_class`, `intent_parsing_chat`, `summary_short`. Three is enough to test the plumbing.
- **Verify:** `python -c "from mailbot_api.prompts import registry; print(registry.list())"` shows the prompts.

### M2.5 — Policy loader

- **Effort:** S · **Deps:** M2.4 · **MVP:** must · **Rules:** H, Ω
- Copy `_bmad-output/brainstorming/policy-v0.yaml` into the codebase as `mailbot_api/router/policy.yaml`.
- Loader validates: every referenced `prompt: vN` exists in registry; every `model` is known to pricing table; required fields present.
- Hot-reload on file change (optional but cheap with `watchfiles`).
- **Verify:** edit policy.yaml with an invalid prompt version, startup fails with a clear error pointing at the line.

### M2.6 — Ollama adapter

- **Effort:** M · **Deps:** M2.1 · **MVP:** must · **Rules:** —
- `mailbot_api/router/models/ollama_adapter.py` — async function `call_ollama(model, system, user, schema=None, timeout=30) -> dict`.
- Use Ollama's `/api/generate` with `format: "json"` and the Pydantic schema's `model_json_schema()` if `schema` is given (Ollama's JSON mode).
- Returns `{output_raw, output_parsed_or_None, tokens_in, tokens_out, latency_ms}`.
- **Verify:** call with `coarse_class` prompt against a sample email row, returns parseable JSON.
- **⚠ Bite:** Ollama's JSON mode is real but can occasionally fail on Qwen 3B. Always have a single retry with stricter "must output valid JSON" prompt (Rule N failure-handling chain).

### M2.7 — Router core (Rule I)

- **Effort:** L · **Deps:** M2.3, M2.4, M2.5, M2.6 · **MVP:** must · **Rules:** I, K, N
- `mailbot_api/router/router.py` — `async def route(task_type, content, force_model=None, max_cost_usd=None) -> RouterResult`.
- Pipeline:
  1. Look up `policy.yaml[task_type]` → (model, prompt_v, escalate, max_tokens_out)
  2. Apply `force_model` override if set (logged with `reason="override"`)
  3. Check response cache (`hash(prompt+model)` in `response_cache` table) — return cached if hit
  4. Render prompt from registry
  5. Call model adapter (only Ollama for now; Anthropic in M3)
  6. Validate output against `OUTPUT_SCHEMA`
  7. On parse fail → single retry with stricter prompt
  8. On persistent fail → return `RouterResult(ok=False, error=RouterError(code="schema_validation_failed", ...))`
  9. Write `router_calls` row + response cache entry
  10. Return `RouterResult(ok=True, output, model_used, cost, latency, tokens, cached)`
- **Verify:** `router.route("coarse_class", "...email content...")` returns a structured class label and writes a logged row.

### M2.8 — OpenAI-compatible `/v1/chat/completions` (Rule X)

- **Effort:** L · **Deps:** M2.7 · **MVP:** must · **Rules:** X
- FastAPI route accepting OpenAI Chat Completions format.
- Translate to internal `route()` call:
  - If the request has a `task_type` extension header (`X-MailBot-Task`), use that
  - Else fall back to a generic `chat` task type
- Translate `route()` result back to OpenAI response format (`choices`, `usage`).
- Auth: require `Authorization: Bearer ${MAILBOT_ROUTER_KEY}` header — Hermes sends it; reject without it.
- **Verify:** `curl -H "Authorization: Bearer $MAILBOT_ROUTER_KEY" -d '{"model":"any","messages":[...]}' http://localhost:8000/v1/chat/completions` returns a valid OpenAI-format response sourced from Qwen.
- **⚠ Bite:** Hermes's `model` field in the request will say whatever you put in `config.yaml` — typically a placeholder like "mailbot-router". Don't use it for routing logic; we route by task_type or fall back to default.

### M2.9 — Loop detection & rate limits (Rule N)

- **Effort:** M · **Deps:** M2.7 · **MVP:** should · **Rules:** N
- In-memory sliding-window rate limiter per `(task_type, caller_verb)`: 60/hr default for chat, 300/hr for ingest.
- Prompt-hash repetition detector: same hash > 10 times in 5 min → refuse with `RouterError(code="loop_detected")`.
- Kill-switch: `POST /admin/pause` (auth required) sets a process-local flag → router refuses all calls until `/admin/resume`.
- **Verify:** unit tests for each — fire 60 calls in a tight loop, the 61st refuses.

### M2.10 — Embedding endpoint

- **Effort:** S · **Deps:** M2.1 · **MVP:** should · **Rules:** —
- `POST /v1/embeddings` — proxies to Ollama bge-small / nomic-embed-text.
- Used by ingest pipeline (later) to embed every new email.
- **Verify:** `curl /v1/embeddings` returns a 384-dim vector.

**M2 ship criterion:** Call `/v1/chat/completions` with any of the 3 implemented prompts via curl. Get back a Qwen response. See it logged in `router_calls` with cost=$0, model=qwen-3b. Loop detection blocks abuse.

---

## M3 — Anthropic tier + budget + cache + sensitivity

**Goal:** Three-tier model stack. Real cost discipline. Sensitivity-aware routing. This is where Rule Ω fully comes online.

### M3.1 — Anthropic adapter (Rule F.1)

- **Effort:** M · **Deps:** M2.7 · **MVP:** must · **Rules:** F.1, M
- `mailbot_api/router/models/anthropic_adapter.py` — async call to `client.messages.create(...)`.
- Mark SYSTEM block as `cache_control={"type": "ephemeral"}` (Rule M).
- Reads `ANTHROPIC_API_KEY` from env at startup; if not set, refuses to register the adapter (degrades to qwen-only).
- Returns `{output_raw, output_parsed, tokens_in, tokens_out, cached_tokens_in, latency_ms}`.
- **Verify:** `router.route("draft_reply", ..., force_model="claude-haiku-4-5")` works and logs `cached_tokens_in=0` on first call, then non-zero on the second within 5 min.
- **⚠ Bite:** Anthropic SDK's exception types are specific. Catch + re-raise as `RouterError(code="provider_error")` with sanitized message. Never let an `anthropic.APIError` bubble to the user.

### M3.2 — Escalation logic (Rule N)

- **Effort:** M · **Deps:** M3.1, M2.7 · **MVP:** must · **Rules:** N, Ω
- When `policy[task].escalate=true` and parse retry fails on Qwen → call next-tier model (Haiku for 3B-failure; Opus for Haiku-failure).
- Log `model_chosen_reason="escalated_from_<X>"`.
- Bound escalations: max 20 per hour per task (circuit-breaker per Rule N); over the limit → return error, alert.
- **Verify:** force a parse failure on Qwen for `action_extraction` (which has `escalate=true`), confirm Haiku is called and row is logged correctly.

### M3.3 — Budget enforcement (4 layers, Rule N)

- **Effort:** L · **Deps:** M3.1, M2.3 · **MVP:** must · **Rules:** N, Ω
- `mailbot_api/router/budget.py`:
  - **Layer 1** — `max_tokens_out` already enforced per request
  - **Layer 2** — daily soft warning: cron-aggregated check of today's `router_calls.cost_usd_estimated SUM`; if > $2 → log warning + send Discord notification (wired in M5; for M3, just log)
  - **Layer 3** — monthly hard cap: if month sum > $30 → enter `degraded_mode`, swap Opus→Haiku→Qwen in policy lookups, refuse `force_model="claude-opus-4-7"` without explicit chat confirmation token
  - **Layer 4** — per-call refusal: estimate cost before making the call; if > $0.20 → refuse with `RouterError(code="per_call_threshold_exceeded")` unless `force=true`
- All thresholds in `policy.yaml` so you can tune without code change.
- **Verify:** seed `router_calls` with fake $31 of usage, next API-bound call refuses with `monthly_budget_exceeded`.

### M3.4 — Sensitivity classifier (Rule Q)

- **Effort:** M · **Deps:** M2.7 · **MVP:** must · **Rules:** Q, Ω
- New prompt: `prompts/sensitivity_class/v1.py` — Qwen-only, runs at ingest.
- Add `sensitivity` column to emails table (if not done in M1.4 — add now).
- Config file `mailbot_api/config/sensitivity_patterns.yaml`: regex + sender domain rules that *force* `sensitive` or `confidential` regardless of classifier output (e.g., `bank.com` → always sensitive).
- **Verify:** seed a fake medical email, classifier returns `sensitivity="sensitive"`.

### M3.5 — Sensitivity-aware routing (Rule Q)

- **Effort:** M · **Deps:** M3.4, M2.7 · **MVP:** must · **Rules:** Q
- In `route()`: if `email_id` is set and the email's sensitivity is `sensitive` or `confidential` → override `policy[task].model` to `qwen-3b`.
- For `sensitive`: API still allowed if `force_model` is set AND a per-session confirmation token is presented (M5 will plumb this from chat; for M3, just require a header `X-MailBot-Sensitive-Override: yes`).
- For `confidential`: API blocked, period.
- **Verify:** call `route("draft_reply", ..., email_id=<confidential_id>)` — refuses with `RouterError(code="sensitivity_blocks_api")`.

### M3.6 — Response cache + cache warmer (Rule M)

- **Effort:** M · **Deps:** M2.7, M3.1 · **MVP:** should · **Rules:** M
- Response cache table: `(prompt_hash, model, response, hit_count, last_used_at)`. TTL configurable per task in policy.yaml; default 24h.
- Cache warmer: `mailbot_api/router/cache_warmer.py` — every 4 min, fires a dummy ping for high-volume tasks (coarse_class) using the cached SYSTEM block. Costs ~0 tokens; keeps Anthropic ephemeral cache warm.
- **Verify:** identical successive calls hit the cache (logged with `cached_tokens_in > 0` and lower cost).

### M3.7 — Ingest pipeline orchestrator (Rule A, K)

- **Effort:** L · **Deps:** M3.4, M3.5, M2.7 · **MVP:** must · **Rules:** A, K
- `mailbot_api/ingest/pipeline.py` — for each new email row, runs in batch lane (Rule K):
  - sensitivity_class → write column
  - coarse_class → write columns
  - if `class_coarse == "human"`: fine_class
  - summary_short
  - importance_scoring
  - action_extraction (if class != newsletter/spam)
  - embedding
- Skips already-processed emails by checking idempotency key.
- Resumes from interruptions (queue-style).
- **Verify:** trigger pipeline against 50 unprocessed emails, all derived columns populate, costs < $0.10.
- **⚠ Bite:** Don't run unbounded. If `len(unprocessed) > 500`, process 100 then pause (Rule K backpressure).

### M3.8 — Verb library skeleton (Rule C, J)

- **Effort:** L · **Deps:** M1.4, M3.7 · **MVP:** must · **Rules:** C, J
- `mailbot_api/verbs/` — Python functions:
  - `find_emails(filter, limit=20)` — returns lightweight projections per Rule J (ID + metadata + summary_short, NOT body)
  - `hydrate_email(email_id)` — returns full body; rate-limited per session
  - `get_thread(thread_id)` — projections of all emails in thread
  - `list_unread(folder=None)` — projection
  - `count_emails(filter)` — just a count
  - `propose_action(email_id, action_type, **payload)` — inserts into `pending_actions`, tier-checked (Rule P)
  - `apply_action(action_id, authorization_token=None)` — drains a single pending action, requires authorization for Tier 2/3 (Rule P)
  - `get_sender_summary(address)` — projection
- Every verb has explicit input schema (Pydantic) and output schema.
- Verb errors are sanitized per Rule F.
- Hydration rate limit: 5 per session (track in memory keyed by session_id).
- **Verify:** unit tests for each verb. `find_emails` never returns full bodies.

**M3 ship criterion:** Edit `policy.yaml` to switch `intent_parsing_chat` from haiku to qwen-3b → next call uses qwen-3b. Force a $35 fake bill via test fixtures → Router enters degraded mode, Opus calls refused. Sensitivity column populated correctly on real emails.

---

## M4 — Eval system & first calibration

**Goal:** Hand-build the labeled corpus, run benchmarks, recalibrate policy.yaml from data. The point of this milestone is to convert hypotheses into measurements.

### M4.1 — Eval corpus (manual labeling)

- **Effort:** L · **Deps:** M3.7 · **MVP:** must · **Rules:** H, L
- Sample ~100 real emails from your inbox (`SELECT * FROM emails ORDER BY RANDOM() LIMIT 100`).
- Anonymize if you plan to share the project: replace people names/addresses with placeholders.
- Hand-label each in `evals/email_corpus_v1.jsonl`:

  ```json
  {
    "id": "eval_001",
    "graph_id": "AAMkAGI...",
    "from": "anon@example.com",
    "subject": "...",
    "body_excerpt": "...",
    "labels": {
      "coarse_class": "newsletter",
      "fine_class": null,
      "importance_score": 1,
      "sensitivity": "normal",
      "has_actions": false,
      "action_extraction": [],
      "ideal_summary_short": "Weekly digest from X about Y.",
      "ideal_draft_reply": null
    },
    "rationale": "Mass-send marketing, no personal addressing"
  }
  ```

- Budget ~3–5h for this. Boring but the most leveraged hours in the project.
- **Verify:** `jq length evals/email_corpus_v1.jsonl` returns 100.
- **⚠ Bite:** Pick a representative mix, not just newsletters. Hand-include at least: 10 transactional, 10 newsletter, 20 human-personal, 20 human-professional, 10 cold outreach, 10 spam-like, 10 notifications, 10 edge cases (calendar invites, password resets, etc.).

### M4.2 — Scoring rubrics

- **Effort:** M · **Deps:** M4.1 · **MVP:** must · **Rules:** H
- `evals/scoring_rubrics/coarse_class.md` — exact-match definition + how to score confusions
- `evals/scoring_rubrics/draft_reply.md` — manual 1–5 scale on dimensions: accuracy, tone, length, helpfulness, no-hallucination
- `evals/scoring_rubrics/summary_short.md` — manual 1–5 on faithfulness, completeness, brevity
- For drafts/summaries, label ~20 anchor examples manually (Rule L hybrid approach).
- **Verify:** rubrics readable, anchor scores filled in for ~20 of the 100.

### M4.3 — Benchmark runner

- **Effort:** L · **Deps:** M4.1, M3.7 · **MVP:** must · **Rules:** H
- `benchmark/runner.py` — `python -m benchmark.runner --tasks=coarse_class,action_extraction --models=qwen-3b,claude-haiku-4-5,claude-opus-4-7`
- For each `(eval_item × task × model × prompt_version)` combo:
  - Calls Router with `force_model`
  - Records full result in `benchmark_runs` table (same schema as `router_calls` plus `eval_id`, `ground_truth`)
- Resumable: skips already-completed runs.
- Estimates total cost upfront, prints, asks for confirmation if > $5.
- **Verify:** run on 10 eval items × 3 models for `coarse_class`, see 30 rows.
- **⚠ Bite:** First full benchmark (100 × ~10 tasks × 3 models for objective tasks; 20 × 3 tasks × 3 models for subjective) is the most expensive eval call you'll make. Budget ~$3–5 of API spend the first time. Subsequent runs are smaller because you only re-run what changed.

### M4.4 — Scorer

- **Effort:** M · **Deps:** M4.3, M4.2 · **MVP:** must · **Rules:** H
- `benchmark/scorer.py`:
  - For classification tasks: exact match → accuracy, per-class precision/recall, confusion matrix
  - For structured extraction: field-level match (date right? party right?)
  - For subjective tasks (drafts, summaries):
    - **Mode A** (manual): print pair side-by-side, ask user to rate 1–5; persist to `manual_scores.jsonl`
    - **Mode B** (auto): use Claude Opus as judge, given the rubric + ground truth + candidate, asked for 1–5; persist to `auto_scores.jsonl`
    - Calibrate B against A on the 20 anchors → confidence interval on auto scores
- Writes scored rows into `benchmark_runs` (adds `score`, `score_mode`, `notes`).
- **Verify:** scorer produces a number for every benchmark_run row.

### M4.5 — Report generator

- **Effort:** M · **Deps:** M4.4 · **MVP:** must · **Rules:** H
- `benchmark/report.py --out=evals/reports/2026-MM-DD.md` — generates markdown with:
  - Per-task table: model × (accuracy, p95 latency, cost per 100 calls)
  - 3B failure modes section: misclassification examples
  - Pareto frontier per task: cost vs. quality
  - **Calibration suggestions:** for each Haiku/Opus row in policy.yaml, "DEMOTE HYPOTHESIS valid: 3B at X% accuracy, considered acceptable" or "DEMOTE HYPOTHESIS invalid: 3B at X% accuracy, keep on Haiku"
- **Verify:** open the .md in a viewer; you can immediately tell which policy.yaml rows need to change.

### M4.6 — First calibration of policy-v0.yaml → policy-v1.yaml

- **Effort:** S · **Deps:** M4.5 · **MVP:** must · **Rules:** Ω, H
- Sit with the report. For each task, decide: demote? keep? promote?
- Edit `policy.yaml`, bump prompt versions if you also tuned prompts during this milestone.
- Commit `policy-v0.yaml` as a historical snapshot in `evals/policy-history/`.
- Document decisions inline as comments in the new policy.yaml.
- **Verify:** at least 2–3 demotions happen (this is expected — Qwen 3B is stronger than people expect on classification).

**M4 ship criterion:** Benchmark report exists. policy.yaml has been edited based on real data. You can show someone "here's why coarse_class is on Qwen and why draft_reply is on Opus" and point at the numbers.

---

## M5 — Hermes integration (the MVP ship line)

**Goal:** MailBot is reachable via Discord, runs continuously, executes verbs through MCP, syncs via Hermes cron, has personality via SOUL.md. This is the line where you cross from "infrastructure" to "actually have a mailbox agent."

### M5.1 — MCP server (Rule X)

- **Effort:** L · **Deps:** M3.8 · **MVP:** must · **Rules:** C, X
- `mailbot_api/mcp_server.py` — uses Python `mcp` library to expose verbs as MCP tools.
- One MCP tool per verb (M3.8 list). Each tool's schema = verb's input schema; result = JSON output.
- Auth: tokens in MCP server config; Hermes presents the token.
- Transport: stdio (Hermes spawns) or HTTP (Hermes connects). HTTP is easier for our container setup.
- **Verify:** `mcp-inspector` (or similar) connects to our server, lists tools, calls `find_emails`, returns rows.
- **⚠ Bite:** MCP is young; the Python SDK is evolving. Pin a specific version of `mcp` in pyproject.toml. Document the version in the README.

### M5.2 — Hermes container set up

- **Effort:** M · **Deps:** M1.3 · **MVP:** must · **Rules:** X
- Replace placeholder Hermes service in compose with `nousresearch/hermes-agent:latest`.
- Mount `mailbot_hermes_data:/opt/data`.
- Set `HERMES_DASHBOARD=1` (optional; nice during dev).
- Ports: 8642 (gateway), 9119 (dashboard) — only expose dashboard on localhost in prod.
- First-boot run: `docker compose run --rm mailbot-hermes setup` — walks through Hermes setup wizard, writes initial `/opt/data/.env`.
- **Verify:** `docker compose logs mailbot-hermes` shows the gateway started.

### M5.3 — Hermes config: Router as primary provider

- **Effort:** S · **Deps:** M5.2, M2.8 · **MVP:** must · **Rules:** X, I, Ω
- Edit `/opt/data/config.yaml`:

  ```yaml
  model:
    provider: custom
    model: mailbot-router
    base_url: http://mailbot-api:8000/v1
    api_key: ${MAILBOT_ROUTER_KEY}

  fallback_providers:
    - provider: anthropic
      model: claude-opus-4-7    # safety net if our Router is down

  auxiliary:
    compression:
      base_url: http://mailbot-api:8000/v1
      api_key: ${MAILBOT_ROUTER_KEY}
      model: mailbot-router
    title_generation:
      base_url: http://mailbot-api:8000/v1
      api_key: ${MAILBOT_ROUTER_KEY}
      model: mailbot-router
    # ...all aux tasks pointed at our Router for Rule Ω discipline
  ```

- **Verify:** Hermes makes a call; you see it appear in `router_calls`.

### M5.4 — MCP wiring to Hermes

- **Effort:** M · **Deps:** M5.1, M5.2 · **MVP:** must · **Rules:** X
- Edit `/opt/data/config.yaml` MCP section to connect to our MCP server at `http://mailbot-api:8000/mcp` with `MAILBOT_ROUTER_KEY` auth.
- Verify tools appear in Hermes: `docker exec mailbot-hermes hermes mcp list` (or equivalent).
- **Verify:** in a CLI session inside Hermes, agent can call `find_emails` and get results.

### M5.5 — SOUL.md (Rule X, persona)

- **Effort:** M · **Deps:** M5.2 · **MVP:** must · **Rules:** Ω, P, R, X
- `hermes-config/SOUL.md` content:

  ```markdown
  # MailBot — Adam's mailbox defender

  You are MailBot. Your one job is to defend Adam's attention from email noise
  while never destroying anything important and never sending email without
  explicit permission.

  ## Your posture
  - Defender, not assistant. Filter, summarize, propose. Adam decides.
  - Conservative. When in doubt, do nothing and ask.
  - Quiet. You speak only when something matters.
  - Cost-aware. You always prefer the cheapest path that does the job.

  ## How you think
  - Read first, act later. Never act on an email without reading its summary.
  - Group similar things. Don't ask 10 questions when 1 batch question works.
  - Show your reasoning when proposing actions — Adam needs to trust the call.

  ## What you never do
  - Send email without explicit per-message authorization
  - Delete anything without explicit per-action authorization
  - Quote sensitive email content (medical, legal, financial) outside this chat
  - Make Adam feel like he's getting noisy notifications
  ```

- **Verify:** load Hermes interactively, ask "who are you?" → reply matches the persona.

### M5.6 — AGENTS.md (operational rules)

- **Effort:** L · **Deps:** M5.5, M5.1 · **MVP:** must · **Rules:** J, K, N, P, R, X
- `hermes-config/AGENTS.md` is where the per-project operational rules live. This is where Rules J/N/P/R express themselves as actual agent behavior. Examples:

  ```markdown
  # MailBot Operations

  ## Finding emails
  - Always call `find_emails()` first to get summaries. NEVER request bodies upfront.
  - When you need a body, call `hydrate_email(id)`. You have a budget of 5 hydrations
    per chat turn. If you need more, ask Adam.

  ## Acting on emails
  - Tier 1 actions (mark_read, move_to_triage) — you may do directly, then report.
  - Tier 2 actions (archive, junk, unsubscribe) — propose as a batch via
    `propose_action()`, ask Adam to approve.
  - Tier 3 actions (delete, send_reply, modify_rules) — propose ONE AT A TIME,
    show full context, await explicit "yes" per action.

  ## Notification discipline
  - Routine ingest events: never notify.
  - Tier 2 batch waiting for approval: include in daily digest (8am).
  - Tier 3 awaiting authorization: notify immediately.
  - Anomaly / kill-switch / budget breach: notify immediately.
  - Quiet hours: 22:00–08:00 Adam-time. No non-urgent messages.

  ## Cost discipline
  - Default to qwen-3b for anything not requiring deep reasoning.
  - When you need to draft a reply, that's Opus territory — use it.
  - When summarizing one short email, qwen-3b suffices.
  - You don't choose the model directly; the Router does. But you choose which
    verbs to call, and that's where cost gets made.
  ```

- Iterate the wording as you discover what the model actually obeys vs. ignores.
- **Verify:** ask MailBot "delete that one" — refuses, explains the tier requirement.

### M5.7 — Skill description (Rule X)

- **Effort:** S · **Deps:** M5.1 · **MVP:** must · **Rules:** X
- `hermes-config/skills/mailbot/SKILL.md` — describes how/when to use the MCP verbs. Hermes uses skills to load contextual guidance.
- **Verify:** `hermes skills list` shows mailbot skill; loading it surfaces the verbs in agent context.

### M5.8 — Discord gateway

- **Effort:** M · **Deps:** M5.2 · **MVP:** must · **Rules:** X
- Create a Discord application and bot at discord.com/developers.
- Set `DISCORD_BOT_TOKEN` in Hermes `.env`.
- Configure Hermes Discord adapter to bind the bot to a specific Discord server + channel for MailBot DMs.
- **Verify:** message the bot in Discord, agent responds.
- **⚠ Bite:** Discord bots need either to be DMed in a server they share with you, or you need to enable DMs explicitly. Hermes docs cover this.

### M5.9 — Cron: Outlook sync (no-agent, Rule K + X)

- **Effort:** M · **Deps:** M5.4, M1.6 · **MVP:** must · **Rules:** D, K, X
- Write `~/.hermes/scripts/outlook_sync.sh` — calls our sync API (`docker exec mailbot-api python -m mailbot_api.sync.sync_once`).
- Register Hermes cron job:

  ```python
  cronjob(
    action="create",
    name="outlook_sync",
    schedule="every 4m",
    script="outlook_sync.sh",
    no_agent=True,
    deliver="local",   # silent unless something to say
  )
  ```

- Sync script outputs `{"wakeAgent": false}` when no new emails, `{"wakeAgent": true, "context": {"new_count": N}}` otherwise.
- **Verify:** Hermes cron status shows job; emails arriving in Outlook appear in SQL within 4 min; no Discord pings when nothing happens.

### M5.10 — Cron: ingest pipeline trigger

- **Effort:** S · **Deps:** M5.9, M3.7 · **MVP:** must · **Rules:** K
- Separate cron job, `every 5m`, runs ingest pipeline on unprocessed emails.
- Also `no_agent=True` — pure script call to `mailbot_api.ingest.pipeline.run_batch(max=100)`.
- **Verify:** new emails get classifications within minutes of arriving.

### M5.11 — Cron: daily digest

- **Effort:** M · **Deps:** M5.10, M5.6 · **MVP:** should · **Rules:** L, R
- Hermes cron job WITH agent, `0 8 * * *`:

  ```python
  cronjob(
    action="create",
    name="daily_digest",
    schedule="0 8 * * *",
    prompt="Generate Adam's daily mailbox digest. Use list_unread() and the
            new-since-yesterday filter to get summaries. Group by importance.
            Surface anything Tier 2 awaiting approval. Keep it scannable.",
    deliver="discord",
  )
  ```

- **Verify:** at 8am you get a digest on Discord.

### M5.12 — Cron: weekly drift + sampling (Rule L)

- **Effort:** M · **Deps:** M5.10 · **MVP:** should · **Rules:** L
- Two cron jobs (or one combined):
  - Sunday 09:00 — drift report: compares this week's distribution of `class_coarse` to eval corpus distribution, alerts if KL > threshold
  - Sunday 09:30 — sampling: picks 5 random `router_calls` from past week (low-confidence weighted), DMs them to Adam in Discord: "Did I get this right?" with quick-reply buttons (or just emoji reactions if buttons are too complex initially)
- Labeled answers get appended to `evals/email_corpus_v2.jsonl` automatically.
- **Verify:** trigger manually, get the sampling DM.

### M5.13 — `pending_send` cooling-off + 20/day cap (Rule P)

- **Effort:** S · **Deps:** M3.8 · **MVP:** must · **Rules:** P
- `apply_action` for `send_*` actions: insert with `status="pending_send"`, scheduled for `now() + 60s`.
- A separate worker drains `pending_send` after the cool-off; counts today's sends; refuses if > 20.
- User can cancel via chat command (`/cancel <action_id>`) during the cool-off.
- **Verify:** ask MailBot to send something, see it in pending_send, cancel it during the 60s window.

### M5.14 — Chat slash commands

- **Effort:** M · **Deps:** M5.8, M5.13 · **MVP:** should · **Rules:** N, P, R
- Implement as Hermes hooks / skill commands:
  - `/pause` — calls Router admin pause
  - `/resume` — undoes
  - `/cost` — shows today's and this month's spend (queries `router_calls`)
  - `/cancel <action_id>` — kills a pending_send during cool-off
  - `/mute <category>` — silences a notification category
  - `/label <recent>` — manually label the last N classifications (feeds eval corpus)
- **Verify:** `/cost` returns numbers; `/pause` blocks further LLM calls; `/resume` unblocks.

**M5 ship criterion:** Message MailBot on Discord at 10pm: "show me unread from today." It calls `list_unread()`, summarizes, replies in <5s, no notification fatigue. Ask it to draft a reply to one — it drafts via Opus, shows you, waits for your "send" confirmation, sends with 60s cool-off, you can cancel. Tomorrow 8am: digest arrives. **You actually use this thing for a week of dev testing.**

---

## M6 — VPS deployment

**Goal:** What works locally works on Hostinger. You walk away for a week and it still works.

### M6.1 — `setup_vps.sh`

- **Effort:** M · **Deps:** M5 (all) · **MVP:** must · **Rules:** S, T, U, V
- One-time bootstrap script that runs on a fresh VPS:
  - Install Docker Engine + Compose plugin
  - Create `mailbot` user (uid 10000 to match Hermes container convention)
  - mkdir + chown the volume mount points
  - Install `mailbot` CLI script to `/usr/local/bin/`
  - Install systemd unit for `docker compose up` on boot (`mailbot.service`)
  - Print "next steps" — create `.env`, run `make deploy`
- **Verify:** spin up a throwaway VPS, run the script, end state matches expectations.
- **⚠ Bite:** Hostinger's default Debian/Ubuntu images may already have Docker; check, don't reinstall.

### M6.2 — `deploy.sh`

- **Effort:** M · **Deps:** M6.1 · **MVP:** must · **Rules:** T
- The one-command deploy:
  1. Bump version in `pyproject.toml`, tag commit
  2. `docker compose build mailbot-api` locally
  3. `docker save mailbot-api:latest | gzip > /tmp/mailbot-api.tgz`
  4. `scp` to VPS
  5. SSH and: `docker load < mailbot-api.tgz` (keep volumes), `docker compose up -d --no-deps mailbot-api` (rolling restart of just our service)
  6. Health check: poll `/health` until ok (or timeout/abort)
  7. Tail logs for 30 seconds, print errors if any
- Hermes container and Ollama are updated separately by `docker compose pull` (we don't ship those).
- **Verify:** `make deploy` works end-to-end against the VPS.
- **⚠ Bite:** don't `docker compose down` — that recreates containers and may lose ephemeral state. Use `up -d --no-deps <service>`.

### M6.3 — Backups (`backup.sh`)

- **Effort:** S · **Deps:** M6.1 · **MVP:** must · **Rules:** V
- Nightly cron on VPS (not Hermes cron — host cron):
  - `sqlite3 /data/mailbot.db ".backup /backups/mailbot-$(date +%F).db"`
  - tar config: `tar czf /backups/config-$(date +%F).tgz /opt/data/SOUL.md /opt/data/AGENTS.md /opt/data/config.yaml /opt/data/cron/jobs.json /opt/data/skills/mailbot`
  - rsync `/backups` to Backblaze B2 (or just keep local for v1)
  - rotate: keep daily for 14 days, weekly for 8 weeks
- Backups exclude `.env`.
- **Verify:** `restore.sh` works against a fresh DB.

### M6.4 — VPS observability (`mailbot status`)

- **Effort:** M · **Deps:** M1.9, M5.14 · **MVP:** must · **Rules:** W
- Polished `mailbot status` on the VPS:
  - Container health (all 3 up?)
  - Last successful sync
  - Unprocessed email count
  - Pending actions awaiting auth
  - Today's spend ($X / $30 cap)
  - Cache hit rate this week (%)
  - Last 5 errors from `router_calls.outcome='failed'`
- **Verify:** SSH into VPS, `mailbot status`, get full picture in 10 sec.

### M6.5 — Notification discipline polish (Rule R)

- **Effort:** M · **Deps:** M5.11, M5.14 · **MVP:** must · **Rules:** R
- Implement all four tiers from Rule R: urgent push, daily digest batching, pull-only stats, silent log-only.
- Quiet hours enforcement (22:00–08:00).
- Self-monitoring: track Discord message read rate / reaction rate; after 1 week below 30% engagement, send the "I'm becoming noisy" reflection message.
- **Verify:** during a 24h test, count messages MailBot sends — should feel sparse and meaningful, not chatty.

### M6.6 — Outlook OAuth on VPS (headless)

- **Effort:** M · **Deps:** M1.5 · **MVP:** must · **Rules:** —
- The first-time auth on a headless box needs the device code flow OR a one-time refresh-token copy from your dev box.
- Recommended: do initial auth on your laptop, copy the refresh token to the VPS `.env`. After that, MSAL refreshes silently as long as it's used.
- Document the re-auth procedure in `docs/auth-recovery.md` for when the refresh token eventually expires.
- **Verify:** the VPS can sync without manual intervention.

### M6.7 — First production deploy

- **Effort:** M · **Deps:** all prior · **MVP:** must · **Rules:** all
- Cut the first real deploy. Run for a week.
- Track in a `LOG.md` (or just notes): every notification you got, every action MailBot did, every place it surprised you (good or bad).
- After 7 days, sit down and review:
  - Cost vs. budget — did it stay under?
  - Notification rate — too quiet, too noisy?
  - Failures — any patterns?
  - Trust — would you let it auto-send something? Auto-delete?
- **Verify:** end of week 1, you're still using it AND you trust it more than at day 1.
- **⚠ Bite:** the first week will reveal 10 things to tune. Don't ship M6.7 to "polished" — ship it to "live, watched closely."

### M6.8 — Iterate (post-MVP, nice-to-haves)

- **Effort:** ongoing · **Deps:** M6.7 · **MVP:** nice · **Rules:** all
- Likely things you'll add post-launch:
  - Honcho memory upgrade if Hermes default memory is too shallow
  - Cascading routing (Rule N: try Qwen first then Haiku on parse fail) if benchmarks show specific tasks benefit
  - Shadow-mode prompt rollout (Rule O)
  - Per-task draft-edit telemetry (Rule O)
  - More aggressive Anthropic prompt caching tuning
  - Maybe Honcho-backed user-model — only if needed
  - Maybe upgrade VPS to 16 GB and try Qwen 7B if benchmarks suggest it helps
- Treat this as continuous, not a milestone.

**M6 ship criterion:** Production deploy on Hostinger. Running unattended for 7 days. You trust it. Budget stayed under $30 for the month. No data was destroyed without your consent. No email was sent without your consent. No sensitive content leaked to Anthropic.

---

## Things this plan deliberately defers

These are real, but they're not the bottleneck for "personal mailbox defender that works."

- **Multi-account support** — your inbox only, period
- **Calendar integration** — Outlook calendar items as separate signal
- **Attachment handling beyond `has_attachments` boolean**
- **Postgres** — SQLite is fine for your scale
- **Webhook-based sync** (Rule D explicitly: cron pull only)
- **A web UI** — Discord IS the UI
- **Sharing MailBot with others** — single-user assumption baked in
- **OpenRouter routing** — Anthropic direct only, simpler accounting
- **Voice / TTS** — not relevant for email defender
- **Browser automation** for unsubscribe — manual mailto:unsubscribe is enough for v1
- **Honcho memory** — Hermes default memory first; upgrade only if needed

Each is a real "could do" but every one of them violates the principle that this milestone plan ships M5 before any nice-to-have lands.

---

## Total scope sanity check

- 6 milestones, ~80 tasks, ~3 months of evenings/weekends if you work steadily
- ~40 of those tasks are S/M; the L/XL ones cluster in: SQLite schema (M1.4), sync (M1.6), Router core (M2.7), `/v1/chat/completions` (M2.8), pipeline (M3.7), verbs (M3.8), eval corpus (M4.1), MCP server (M5.1), AGENTS.md (M5.6)
- MVP line at end of M5 — 5 of 6 milestones — call it ~10 weeks for a part-time evening project
- M6 is the final ~2 weeks polish + first prod week

If your time available is much smaller, the answer is the same plan, just slower. The dependencies don't bend — you can't get a Router before you have prompts before you have a schema.

---

## A note on what success looks like at the end

When this is done, the artifact you've built is:

- A **personal defender** that quietly filters your inbox without you babysitting it
- A **cost-disciplined system** running for under $30/month of API spend
- A **measurable system** — every routing decision is backed by data, not vibes
- A **trustworthy system** — it cannot destroy data or send mail without your permission, by *construction*, not by good behavior
- A **honest system** — it tells you when it's degraded, drifted, or in trouble
- A **portable system** — entirely in Docker, three containers, swappable models, your code

That's a lot for a personal project. The reason it's achievable is that we used Hermes for everything Hermes already does, and only built the mailbox-specific intelligence layer ourselves. Rule X earned its keep.

Now go build it. 🛡
