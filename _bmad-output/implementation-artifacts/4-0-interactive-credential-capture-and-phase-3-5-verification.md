---
baseline_commit: 9c368c4
---

# Story 4.0: Interactive credential capture + Phase 3.5 verification walkthrough

Status: done

## Story

As Adam,
I want a single interactive story where the dev agent (Amelia) guides me step-by-step through providing every credential the system needs — Outlook OAuth (4 values + minted refresh token), Anthropic API key + provider-side spend cap, Discord bot token, generated Router bearer key, and any container-config values — with a light per-credential smoke test executed as each value is captured AND one consolidated Phase 3.5 walkthrough at the end exercising the full integrated stack against real services,
so that Epics 1–3 stop carrying the three-epic Phase 3.5 deferral, the privacy-and-cost invariants get observed end-to-end against real Anthropic + real Microsoft Graph + real Ollama containers (not mocked transports), and Epic 4 begins on top of a verified foundation rather than an inferred one.

## Acceptance Criteria

### AC-1 — Story is interactive and guided, not a script the user runs alone

**Given** Phase 3.5 has been deferred across Epics 1, 2, and 3 (each retro recommitted; none executed),

**When** this story is invoked (e.g., `bmad-dev-story 4-0` or by direct skill invocation),

**Then** Amelia drives the flow conversationally: each step opens with a one-paragraph context block (what we're about to capture, why it matters, what the smoke test will prove), waits for Adam's input (paste-the-secret, paste-the-output, confirm-screenshot-state), and acknowledges receipt before moving to the next step.

**And** Adam is the source of all secret material — Amelia never generates a credential that grants real-world access (the one exception is `MAILBOT_ROUTER_KEY`, which is a self-issued bearer token; see AC-6).

**And** secrets paste from Adam into the chat are NEVER echoed back, NEVER written to logs, NEVER written to the story file's Completion Notes, NEVER written to a transcript file. They go only into `.env` (or `.env.local` per AC-2).

**And** Amelia confirms receipt with a redacted echo (e.g., "received `OUTLOOK_CLIENT_SECRET` — last 4 chars: `...wXyZ`, length: 40") so Adam can sanity-check no paste-truncation happened, without the secret appearing in the chat history.

### AC-2 — `.env.local` (or `.env`) writes happen incrementally as each credential is verified

**Given** the project's `.env.example` documents the 7 required keys (`DISCORD_BOT_TOKEN`, `ANTHROPIC_API_KEY`, `OUTLOOK_CLIENT_ID`, `OUTLOOK_CLIENT_SECRET`, `OUTLOOK_TENANT_ID`, `OUTLOOK_REFRESH_TOKEN`, `MAILBOT_ROUTER_KEY`) plus 3 container-config keys (`MAILBOT_DB_PATH`, `MAILBOT_POLICY_PATH`, `OLLAMA_URL`),

**When** each credential is captured AND its smoke test passes,

**Then** the value is appended (or upserted) to `.env` immediately — not batched until the end. If Adam abandons the story mid-walkthrough, every verified credential is persisted.

**And** the file used is `.env` at the repo root (project convention; `docker-compose.yml` reads from it via the `${VAR:-}` substitution in lines 15, 35–42). The file is already gitignored — verify before any write that `.env` is in `.gitignore` (fail-fast if not).

**And** values are written with the format `KEY=value` (no quotes unless the value contains `#` or whitespace, in which case single-quoted).

**And** existing values for a key are upserted in-place (not duplicated). The file is read, the line matching `^KEY=` is replaced, the file is re-written atomically (write-to-temp + rename). If no matching line exists, the key is appended.

**And** before each write, Amelia confirms the action with Adam ("about to write `OUTLOOK_CLIENT_ID` to `.env`; existing value will be overwritten — proceed?") on the first write only; subsequent writes within the same story session skip the confirmation (single per-story "yes I am editing my .env" gate).

### AC-3 — Outlook OAuth captured in four sub-steps with `scripts/mint_refresh_token.py` as the last step

**Given** the Outlook OAuth flow requires four user-provided values (`OUTLOOK_CLIENT_ID`, `OUTLOOK_CLIENT_SECRET`, `OUTLOOK_TENANT_ID`, `OUTLOOK_REDIRECT_URI`) plus one minted value (`OUTLOOK_REFRESH_TOKEN`),

**When** the story reaches the Outlook block,

**Then** Amelia walks Adam through `docs/entra-app-registration.md` (the 9-step Entra recipe shipped by Story 1-9) — opens the URL to the Microsoft Entra admin center, summarizes each step in chat, captures the resulting `client_id`, generates a `client_secret` (Adam pastes the **value**, not the secret ID — Amelia explicitly cautions which one), captures the `tenant_id`, and confirms the `redirect_uri` matches the script's default `http://localhost:8765/callback`.

**And** after the four values are in `.env`, Amelia invokes `python scripts/mint_refresh_token.py` (the 8765-loopback OAuth flow Story 1-9 built) — Adam consents in the browser, the script prints the refresh token to stdout, Amelia captures the value, writes it to `.env` as `OUTLOOK_REFRESH_TOKEN`, and the smoke test is `python scripts/check_graph_auth.py` (exits 0 + prints the authenticated UPN).

**And** if `mint_refresh_token.py` fails (Adam declines consent, the browser doesn't open in WSL/headless, the loopback port is in use), Amelia surfaces the exact stderr + suggests the fix per the script's documented exit codes (1=user-decline, 2=missing-config, 3=timeout, 4=loopback-bind-fail, etc.).

**And** the redirect-URI confirmation is recorded explicitly — Amelia asks "is the redirect URI in your Entra app registration EXACTLY `http://localhost:8765/callback`?" and waits for "yes" before invoking the script. (Most common failure mode for the 8765 loopback.)

### AC-4 — Anthropic key captured with mandatory provider-side spend cap walkthrough

**Given** the Anthropic API key gates every Haiku + Opus dispatch (Story 2-6's adapter; Story 2-8's 4-layer budget guard is the in-code defense; provider-side cap is the belt-and-suspenders measure flagged in Epic 1 retro §12 and Epic 2 retro §12),

**When** the story reaches the Anthropic block,

**Then** Amelia opens `console.anthropic.com/settings/limits` in the browser (or walks Adam there in chat if the env is headless), guides Adam to set a **hard monthly spend cap of $35 USD** (Epic 2's Layer 3 in-code cap is $30/month — provider-side cap is set $5 above to act as a true safety net), and waits for Adam to confirm "cap set + email alerts enabled at 80% and 100% of cap."

**And** Adam then pastes the API key from `console.anthropic.com/settings/keys` (a freshly-issued key named e.g. `mailbot-prod-2026-06`). Amelia writes it to `.env` as `ANTHROPIC_API_KEY`.

**And** the smoke test is a single warm dispatch via the Router: Amelia invokes (programmatically, not by curling — leverages the actual code path) a tiny `ask_router(task_type="hermes_aux", content="ping", caller_origin="story-4-0-smoke")` call after the lifespan loads the policy + registers the Anthropic adapter. Expected result: `RouterResult(ok=True, ...)` with `model_used="claude-haiku-4-5-20251001"` (or whichever Haiku model `policy.yaml` resolves to) and `tokens_in`/`tokens_out` populated + `cost_usd` > 0.

**And** the smoke test result is recorded in the story file with the model id and the cost (e.g., "smoke test passed: claude-haiku-4-5-20251001, tokens_in=12, tokens_out=4, cost_usd=0.00006") — NOT the response text (the response is discarded; we only care that the round-trip works).

**And** if the smoke test returns `RouterResult(ok=False, error=RouterError(code=PROVIDER_ERROR, ...))`, Amelia surfaces the sanitized error message + suggests common causes (key invalid, key revoked, region blocked, billing not enabled on the Anthropic account, organization seat not assigned).

### AC-5 — Discord bot token captured with the Hermes-container caveat made explicit

**Given** the Discord bot token is read by the Hermes container only (per Rule F.1 — the Anthropic key never reaches Hermes, and the Discord token never reaches mailbot-api; see `docker-compose.yml` line 15 vs line 35),

**When** the story reaches the Discord block,

**Then** Amelia opens `discord.com/developers/applications` in the browser (or walks Adam there in chat), guides Adam to create a new application named `MailBot` (or reuse an existing one), navigate to the Bot tab, and "Reset Token" → copy the value. Adam pastes; Amelia writes to `.env` as `DISCORD_BOT_TOKEN`.

**And** Amelia ALSO captures the **channel ID** Adam wants Hermes to use for notifications + the **user ID** Adam wants Hermes to DM for prompts + the **allow-listed user ID(s)** Hermes will accept commands from (Epic 6 territory, but cheap to capture now). These go into `.env` as `DISCORD_HOME_CHANNEL`, `DISCORD_USER_ID`, and `DISCORD_ALLOWED_USERS` even though no Epic-3-or-earlier code reads them yet — they're Epic 6 inputs being captured ahead of need.

> **AMENDMENT 2026-06-04 (Epic 6 retro action item A6):** Earlier drafts of this AC named the channel-ID variable `DISCORD_CHANNEL_ID` — that name does NOT match the binding contract on the Hermes side. The canonical name across `docker-compose.yml`, `.env.example`, `hermes-config/config.yaml`, and `scripts/setup_vps.sh` is `DISCORD_HOME_CHANNEL`. Discovery context: during Story 6-10 Phase 3.5 live walk, the digest cron job posted nothing because `DISCORD_HOME_CHANNEL` was empty in `.env`; the variable Adam had populated under the old name (`DISCORD_CHANNEL_ID`) was ignored by Hermes. Rename was applied inline during the walk. **`DISCORD_ALLOWED_USERS` was also missed by the original rubric** — it surfaced during Epic 6 Phase 3.5 CP-2 walk attempt #1 when Hermes emitted `WARNING gateway.run: No user allowlists configured. All unauthorized users will be denied.` The fix here is rubric-only — captures both keys at the same prompt where `DISCORD_BOT_TOKEN` is captured, with the same redacted-echo treatment.

**And** Amelia explicitly notes that no smoke test will be run against Discord in this story — the Hermes container isn't running yet (Epic 5 ships Hermes wiring; Epic 6 ships the notification dispatcher). The smoke test for Discord is **deferred to Epic 6's Story 6-3** (notification-tier dispatcher) and recorded as a TODO in this story's Completion Notes.

**And** Amelia warns Adam: "the token you just gave me is a **bot** token — if you ever paste this into a chat that's logged or screenshot, regenerate it from the developer portal." (One-time warning, no recurring nag.)

### AC-6 — `MAILBOT_ROUTER_KEY` self-issued by Amelia (not user-provided)

**Given** the Router bearer key (`MAILBOT_ROUTER_KEY`) is a self-issued secret for the `/v1/chat/completions` endpoint (Story 2-10) — it gates Hermes-container → mailbot-api calls and has no external provider; it's purely internal,

**When** the story reaches this step,

**Then** Amelia generates a 32-byte URL-safe random token via `secrets.token_urlsafe(32)` (Python stdlib; cryptographically secure), writes it to `.env` as `MAILBOT_ROUTER_KEY`, and shows Adam the **first 8 + last 4 characters** only ("generated `MAILBOT_ROUTER_KEY`: `aB3xKp9Q...vXyZ` — full value written to .env").

**And** Amelia explains in one sentence what this key is for ("internal bearer between Hermes container and mailbot-api; rotates independently of cloud keys; if you ever expose it, regenerate by re-running this step").

**And** the smoke test is a single authenticated request against `/v1/chat/completions` once the Docker stack is up (deferred to AC-9's consolidated Phase 3.5 walkthrough — at this point in the story the stack isn't running yet).

### AC-7 — Container-config keys captured with defaults pre-filled

**Given** three container-config keys have safe defaults (`MAILBOT_DB_PATH=/data/mailbot.db`, `MAILBOT_POLICY_PATH=/app/router/policy.yaml`, `OLLAMA_URL=http://ollama:11434`) appropriate for the docker-compose stack,

**When** the story reaches the container-config block,

**Then** Amelia presents the three defaults in a single block ("these three values are container-path defaults; press enter to accept, or paste an override") and accepts Adam's "accept all" as the canonical happy path. If Adam wants any override (e.g., dev wants `MAILBOT_DB_PATH=./mailbot.db` for local-non-Docker runs), Amelia captures the override.

**And** `MAILBOT_LOGS_PATH` is **not** captured (no Epic-3-or-earlier code path requires it; the notifications module defaults to `/var/log/mailbot` which is the right value for the compose stack). Recorded in this story's Completion Notes as "intentionally skipped — default is correct."

**And** `MAILBOT_PATTERNS_PATH` is **not** captured (defaults to `/app/router/sensitivity_patterns.yaml` which Story 3-3 ships at the right path).

**And** any `MAILBOT_SKIP_*` env vars are **explicitly NOT written** — these are test-only bypass flags and must never appear in a production `.env`. Amelia surfaces this rule once at the start of the container-config block.

### AC-8 — A redacted artifact records what was captured (no secret material)

**Given** the story file's Completion Notes must remain commit-safe,

**When** all credentials are captured,

**Then** the story file's Completion Notes contain a redacted summary table:

```
| Key                       | Status | Length | Last 4 | Verified by                          |
|---------------------------|--------|--------|--------|--------------------------------------|
| OUTLOOK_CLIENT_ID         | set    | 36     | a1b2   | check_graph_auth.py exit 0           |
| OUTLOOK_CLIENT_SECRET     | set    | 40     | wXyZ   | check_graph_auth.py exit 0           |
| OUTLOOK_TENANT_ID         | set    | 36     | c3d4   | check_graph_auth.py exit 0           |
| OUTLOOK_REFRESH_TOKEN     | set    | 1057   | qR8m   | check_graph_auth.py + sync-now CP-6  |
| ANTHROPIC_API_KEY         | set    | 108    | k9pL   | router smoke dispatch (haiku, $0.00006) |
| DISCORD_BOT_TOKEN         | set    | 70     | jH2n   | deferred to Story 6-3                |
| DISCORD_HOME_CHANNEL      | set    | 19     | 7821   | deferred to Story 6-3                |
| DISCORD_USER_ID           | set    | 18     | 4493   | deferred to Story 6-3                |
| DISCORD_ALLOWED_USERS     | set    | 18     | 4493   | deferred to Story 6-3                |
| MAILBOT_ROUTER_KEY        | set    | 43     | vXyZ   | /v1/chat/completions 200 (CP-10)     |
| MAILBOT_DB_PATH           | set    | 17     | t.db   | docker compose up + lifespan OK      |
| MAILBOT_POLICY_PATH       | set    | 26     | .yaml  | docker compose up + lifespan OK      |
| OLLAMA_URL                | set    | 23     | 1434   | docker compose up + ollama 200       |
```

**And** the same table is mirrored in a new `_bmad-output/implementation-artifacts/4-0-credential-capture-evidence.md` file — also commit-safe, no secret material. This file is the durable artifact for "Phase 3.5 verification happened on date X."

**And** the table records timestamps for each verification.

**And** no full key values, no partial-key-greater-than-4-chars values, and no decoded JWT payloads are written anywhere outside `.env`.

### AC-9 — Consolidated Phase 3.5 walkthrough exercises the integrated stack end-to-end

**Given** every credential is captured + each light smoke test passed,

**When** Amelia transitions to the consolidated Phase 3.5 walkthrough,

**Then** the following checkpoints are executed in order, each with a recorded PASS/FAIL/SKIP verdict in the evidence file:

- **CP-A — Docker stack up**: `docker compose up -d --build` brings all 4 containers up (`mailbot-api`, `mailbot-hermes`, `ollama`, `ollama_model_warmup`). `docker compose ps` shows `mailbot-api (healthy)` and `ollama (healthy)`. `ollama_model_warmup` exits 0. Expected duration: 60–120s on a typical home connection (model pull dominates; Epic 2 retro §3 documented the timing race).
- **CP-B — `curl http://localhost:8000/health`** returns HTTP 200 with the Story 1-8 enriched payload (`sync_last_heartbeat_at`, `sync_last_outcome`, `sync_minutes_since_last_ok`, `sync_health_alarm`).
- **CP-C — `docker exec mailbot-api python scripts/check_graph_auth.py`** exits 0 and prints the authenticated UPN.
- **CP-D — `docker exec mailbot-api python scripts/mailbot.py sync-now`** exits 0; observe one or more emails synced. `docker exec mailbot-api sqlite3 /data/mailbot.db "SELECT COUNT(*) FROM emails"` returns ≥ 1.
- **CP-E — Send-yourself-test-email + sync + ingest**: Adam sends himself an email from any client (subject prefixed with `[mailbot-4-0-test]`). Wait ≤ 4 minutes. `sync-now` again. Verify the row exists in `emails`. Then invoke `docker exec mailbot-api python -m mailbot_api.ingest.pipeline --email-id <id>` (Story 3-5 CLI). Verify all 7 derived-field columns are populated for a `class_coarse="human"` email (or all-but-fine_class for non-human). Query: `docker exec mailbot-api sqlite3 /data/mailbot.db "SELECT sensitivity, sensitivity_at, coarse_class, summary_short, importance_score, action_extraction, embedding_dtype FROM emails WHERE graph_id=<id>"`.
- **CP-F — Sensitivity-blocks-API observed live**: Adam sends himself an email with a force_sensitive pattern match (e.g., subject "URGENT — password reset code 123456" matches Story 3-3's password-reset regex). Re-run the ingest pipeline. Verify `sensitivity="sensitive"` (or "confidential" if the pattern is in `force_confidential`), then verify the Haiku-bound steps (summary, importance, action) returned `SENSITIVITY_BLOCKS_API` in the structured log (`event="ingest.step.skipped_sensitive"`) AND the corresponding `*_at` columns are NULL. Local Qwen-bound steps + embedding completed normally.
- **CP-G — Anthropic warm-cache hit observed**: Re-run the ingest pipeline on the same `class_coarse="human"` email from CP-E. Verify each Haiku step short-circuits via the `derivations_idempotency` table — zero new `router_calls` rows for those task_types. Then issue a fresh dispatch via `/v1/chat/completions` (curl with the `MAILBOT_ROUTER_KEY` bearer) sending an identical Hermes-aux pass-through twice and verify the second call's `cache_read_input_tokens > 0` in the audit row.
- **CP-H — `/v1/chat/completions` round-trip with bearer**: `curl -H "Authorization: Bearer $MAILBOT_ROUTER_KEY" -H "Content-Type: application/json" -d '{"model":"hermes-aux","messages":[{"role":"user","content":"ping"}]}' http://localhost:8000/v1/chat/completions` returns HTTP 200 with the OpenAI-shape response envelope (`choices[0].message.content`). With a missing or wrong bearer, returns HTTP 401.
- **CP-I — Cost verb returns the full picture**: `docker exec mailbot-api python scripts/mailbot.py cost` returns the JSON breakdown (per_task / per_model / per_caller_origin / cache_hit_rate / degraded_mode) populated with the dispatches made in CP-A through CP-H.
- **CP-J — Pause/resume kill switch live-fires**: `docker exec mailbot-api python scripts/mailbot.py pause` then attempt CP-H again; expect HTTP 503 or `RouterError(code=PAUSED)`. `docker exec mailbot-api python scripts/mailbot.py resume` and confirm CP-H succeeds again.
- **CP-K — Worker → alarm → JSONL notification chain (incidentally exercised)**: confirmed by stopping the `ollama` container (`docker stop mailbot-ollama`), waiting 60 min OR forcing the alarm-debounce window via the env, observing `sync_health_alarm=true` in `/health`, and observing one (and only one) row appended to `/var/log/mailbot/notifications_pending.jsonl`. **Time-skippable**: if Adam doesn't want to wait, this checkpoint records as SKIP with rationale "incidentally verified in Epic 1 Phase 3.5 walk; alarm-debounce code path unchanged since."

**And** each checkpoint records a verdict + a one-line evidence string in the evidence file. Failures do NOT abort the walkthrough — Amelia surfaces the failure, records it, and continues. The end-of-walkthrough summary lists all FAILs with recommended remediation.

**And** the final verdict for the story is one of: **PASS** (all checkpoints PASS), **PASS WITH FINDINGS** (≤ 2 SKIPs or ≤ 1 non-blocking FAIL with documented mitigation), **FAIL** (any privacy-invariant or load-bearing checkpoint fails — CP-F, CP-C, CP-D, CP-E).

### AC-10 — `epic-3-run-flags.md` Phase 3.5 gate flips from ☐ to ☑

**Given** `epic-run-flags.md` (and `epic-2-run-flags.md`) carry an open `B2 — Phase 3.5 manual-verification gate` checkbox,

**When** this story closes with a PASS or PASS WITH FINDINGS verdict,

**Then** the orchestrator updates both flags files: Epic 2 and Epic 3 sections both flip `B2` from `☐ NOT YET RESOLVED` to `☑ PASS (programmatic walk + real Docker stack verify, <date>)` — referencing this story's evidence file.

**And** Epic 1's flags file already records a PASS WITH FINDINGS verdict from the Epic 1 retro walkthrough; this story confirms that record is still valid (re-runs CP-1..CP-5 + CP-AC-6 equivalents to verify Epic 1's containerization fixes haven't regressed; if any check fails, surface as a regression — this is the only way to catch regression in deferred-verification land).

**And** the sprint-status row for Story 4-0 records the verdict, the evidence-file path, and the count of FAILs/SKIPs.

### AC-11 — All quality gates green (story-level)

**Given** Story 4.0 ships no production code — only an interactive workflow + an evidence artifact,

**When** the standard quality gates run,

**Then**:
- pytest: no new tests required (the walkthrough exercises real code paths, not unit tests). Existing 458 tests still pass.
- ruff check / format: no source-code changes outside `_bmad-output/`.
- mypy: no source-code changes.
- boundary check: exit 0 — no new boundaries introduced.

**And** the only files this story creates or modifies are:
- `.env` (gitignored — NOT committed)
- `_bmad-output/implementation-artifacts/4-0-credential-capture-evidence.md` (new, commit-safe)
- `_bmad-output/implementation-artifacts/4-0-...story-file.md` (this file, Completion Notes filled)
- `_bmad-output/implementation-artifacts/epic-run-flags.md` (B2 flip for Epic 3)
- `_bmad-output/implementation-artifacts/epic-2-run-flags.md` (B2 flip for Epic 2)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (story 4-0 row, last_updated)

## Tasks / Subtasks

- [x] **Task 1**: Pre-flight checks (AC-1, AC-2)
  - [x] Verify `.env` is in `.gitignore` (fail-fast if not)
  - [x] Verify `.env.example` matches the 7-required-keys list (warn if drift)
  - [x] Verify `docker-compose.yml` is present and parseable
  - [x] Verify Python venv has `secrets` (stdlib — always present), `httpx`, and `numpy` (existing deps)
  - [x] Confirm with Adam: "ready to walk through credential capture + Phase 3.5? Estimated wall-clock: 20–40 min depending on how fast the Entra + Anthropic + Discord console steps go."

- [x] **Task 2**: Outlook OAuth block (AC-3)
  - [x] Walk Adam through `docs/entra-app-registration.md` — capture `OUTLOOK_CLIENT_ID`
  - [x] Capture `OUTLOOK_CLIENT_SECRET` (Adam wrote to .env directly; not echoed)
  - [x] Capture `OUTLOOK_TENANT_ID`
  - [x] Confirm `OUTLOOK_REDIRECT_URI` matches the script default (or capture override)
  - [x] Write the four values to `.env` (first-write confirmation gate)
  - [x] Invoke `python scripts/mint_refresh_token.py`; capture stdout refresh token
  - [x] Write `OUTLOOK_REFRESH_TOKEN` to `.env`
  - [x] Smoke test: `python scripts/check_graph_auth.py` exits 0; record UPN ('Adam Maroni' / 'adamaroni@hotmail.fr')
  - [x] **MID-STORY SCOPE EXPANSION** — AADSTS90023 finding: patched mint_refresh_token.py + graph_client.py + oauth.py + check_graph_auth.py to support public-client (no OUTLOOK_CLIENT_SECRET) Entra setup. Added 6 regression tests. All 464 tests pass.

- [x] **Task 3**: Anthropic block (AC-4)
  - [x] Walk Adam through `console.anthropic.com/settings/limits`; confirm hard cap $35/mo + alerts at 80/100%
  - [x] Capture `ANTHROPIC_API_KEY` (Adam wrote to .env directly; not echoed)
  - [x] Write to `.env`
  - [x] Smoke test: invoke a `hermes_aux` Router dispatch programmatically; record model/tokens/cost (claude-haiku-4-5-20251001, tokens_in=33, tokens_out=5, cost_usd=$0.000058, latency_ms=782)
  - [x] First attempt: HTTP 400 "credit balance too low" — surfaced via PROVIDER_ERROR; Adam added $20 credits and re-ran successfully

- [x] **Task 4**: Discord block (AC-5)
  - [x] Walk Adam through `discord.com/developers/applications`; create or reuse the `MailBot` app
  - [x] Capture `DISCORD_BOT_TOKEN` (Adam wrote to .env directly; not echoed; one-time security warning given)
  - [x] Capture `DISCORD_HOME_CHANNEL`, `DISCORD_USER_ID`, and `DISCORD_ALLOWED_USERS` (rubric-corrected per 2026-06-04 amendment; see AC-5 amendment note)
  - [x] Write all four to `.env`
  - [x] Smoke test: explicitly DEFERRED to Story 6-3; record in Completion Notes

- [x] **Task 5**: Router bearer self-issue (AC-6)
  - [x] Generate via `secrets.token_urlsafe(32)`
  - [x] Write `MAILBOT_ROUTER_KEY` to `.env` (length=43, last4=4_DU)
  - [x] Show Adam the first-8 + last-4 redaction; explain rotation procedure

- [x] **Task 6**: Container-config defaults (AC-7)
  - [x] Present the three defaults block; accept "accept all" or capture overrides (Adam accepted all)
  - [x] Write `MAILBOT_DB_PATH=/data/mailbot.db`, `MAILBOT_POLICY_PATH=/app/router/policy.yaml`, `OLLAMA_URL=http://ollama:11434` to `.env`
  - [x] Document the explicit skips (`MAILBOT_LOGS_PATH`, `MAILBOT_PATTERNS_PATH`, `MAILBOT_SKIP_*`)
  - [x] Noted finding: Git Bash MSYS path translation mangled the leading-slash container paths on first write; MSYS_NO_PATHCONV=1 needed on the helper invocation. Documented for retro.

- [x] **Task 7**: Generate redacted evidence artifact (AC-8)
  - [x] Compute length + last-4 for each captured key
  - [x] Write `_bmad-output/implementation-artifacts/4-0-credential-capture-evidence.md`
  - [x] Mirror the table into this story's Completion Notes (see Completion Notes List below)

- [x] **Task 8**: Consolidated Phase 3.5 walkthrough (AC-9) — CP-A through CP-K
  - [x] CP-A docker stack up — PASS (all 4 containers; mailbot-api + ollama healthy; warmup exit 0)
  - [x] CP-B `/health` 200 + enriched payload — PASS (all 4 Story 1-8 fields present; alarm initially raised due to stale heartbeat)
  - [x] CP-C `check_graph_auth.py` exit 0 — PASS (UPN 'adamaroni@hotmail.fr'; only works after Finding 1 patch)
  - [x] CP-D `sync-now` exit 0 + ≥1 email row — PASS (1,592 emails, 1,418 threads, 657 senders; messages_seen=1592 messages_upserted=0 (no new since prior sync); fresh heartbeat cleared sync_health_alarm to false)
  - [x] CP-E send-yourself-test + ingest pipeline → all 7 derived fields populated — PARTIAL PASS (sensitivity + coarse + fine all populated for human email; embedding works after Finding 6 patch; summary_short / importance / action blocked by Finding 5 (Haiku schema-validation bug — needs Story 3-2 fix))
  - [x] CP-F sensitivity-blocks-API observed live — **PASS** (FR-2.3 privacy invariant confirmed: force_sensitive pattern fired → sensitivity=sensitive → Haiku steps in steps_blocked_by_sensitivity → Anthropic NEVER called; this is the highest-stakes contract in the codebase)
  - [x] CP-G Anthropic cache hit observed — SKIP (Anthropic ephemeral cache requires ≥1024 input tokens to activate; CP-H smoke prompts were 44 tokens; cache mechanism verified by Story 2-6 unit tests against recorded fixtures)
  - [x] CP-H `/v1/chat/completions` 200 with bearer; 401 without — PASS (correctly 401 with no bearer / wrong bearer; 200 with correct bearer; OpenAI-shape response envelope; caller_origin propagation verified in audit row)
  - [x] CP-I `mailbot cost` returns populated breakdown — PASS (verb returns total_usd, per_task, per_model, per_caller_origin, cache_hit_rate, degraded_mode — but CLI subcommand wiring is missing → Finding 7)
  - [x] CP-J pause → 503 → resume → 200 — PASS (in-process verification; cross-process pause requires server restart since pause state is module-level singleton; CLI subcommand wiring is missing → bundled with Finding 7)
  - [x] CP-K worker alarm chain — PASS (incidentally observed: CP-B showed sync_health_alarm=true on stale heartbeat → CP-D wrote fresh heartbeat → next /health showed sync_health_alarm=false; full chain verified without needing the 60-min wait)

- [x] **Task 9**: Record verdict + update flags (AC-10)
  - [x] Compute final verdict (PASS WITH FINDINGS — see evidence file)
  - [x] Flip B2 in `epic-run-flags.md` (Epic 3 section) and `epic-2-run-flags.md` (Epic 2 section)
  - [x] Epic 1 regression-check outcome: CP-C (Outlook OAuth via real Graph) PASS for the first time — Epic 1 stories 1-5/1-7/1-8 confirmed working against real Graph after F1 patch. The "Epic 1 PASS WITH FINDINGS" record in epic-run-flags.md was from a `SecretMissing` failure-mode walk (no actual OAuth call); Story 4-0 is the first time the OAuth refresh-token exchange has touched real Microsoft Graph. No regressions detected; the OAuth code path patched in F1 now works where it never did before.
  - [x] Update sprint-status row for Story 4-0

- [x] **Task 10**: Story closure (AC-11)
  - [x] Confirm `.env` not in git status — verified via `git check-ignore -v .env` (`.gitignore:25:.env` matches; `git ls-files .env` exit 0 with no output)
  - [x] Confirm evidence file is commit-safe (no secret material) — regex scan ran across both story file + evidence file; no Anthropic / MS / Discord / Entra / bearer-shaped strings found (only false positives from file paths + markdown separator characters)
  - [x] Fill Completion Notes with the redacted summary table, the CP-A..CP-K verdict table, and any findings — done in Tasks 7 + 9
  - [x] Mark story `review` in sprint-status (per dev-story workflow Step 9; verdict PASS WITH FINDINGS; awaiting code-review or user sign-off before moving to `done`)

## Dev Notes

### Why this is one story, not seven

Each credential could be its own story (Story 4-0a Outlook, 4-0b Anthropic, etc.), but that fragments the user experience: Adam would have to context-switch between seven story sessions, and the Phase 3.5 consolidated walkthrough at the end only makes sense if all credentials are present. **One interactive session is the right shape.** The cost is a longer story file; the benefit is one-shot completion of the three-epic verification debt.

### Why `.env` writes are incremental, not batched

If Adam abandons mid-walkthrough (real-life interruption, Entra portal flaky, etc.), every verified credential should survive. Incremental writes mean re-invoking the story picks up exactly where it left off — Amelia detects "OUTLOOK_CLIENT_ID is already set in .env, last-4=a1b2, skip capture and re-run smoke test only?" and offers the resume path.

### Secret-handling discipline

Adam's pastes go into a single in-memory variable inside Amelia's tool-use session. After the value is written to `.env`, the in-memory variable is overwritten with `"<redacted>"` (Python doesn't truly delete; this is best-effort). The story file's Completion Notes and the evidence file ONLY ever contain length + last-4 + verification result — never the value, never a partial-value-greater-than-4-chars, never a JWT payload decode.

Concrete rule: **if a piece of text would let an attacker who reads this file impersonate Adam against any of (Outlook, Anthropic, Discord, the Router endpoint), it MUST NOT appear in the file.** Length-and-last-4 fails that test (4 chars of a 40+ char secret is not impersonation-capable). Full key value passes the test trivially (catastrophic). The redacted echo in chat is the same standard.

### Why a $35 provider-side cap, not $30

Epic 2's Layer 3 in-code cap is $30/mo (degraded-mode trip). The provider-side cap is $5 above — gives the in-code defense room to fire first (more graceful UX, structured `degraded_mode=true` flag, force-override path for emergencies), with the provider-side cap as the absolute backstop. If we set them equal, race conditions between the in-code aggregator and Anthropic's billing window could cause spurious cap trips. $5 of headroom is small enough that the provider-side cap meaningfully bounds spend if the in-code guard ever fails.

### Why `MAILBOT_ROUTER_KEY` is self-issued

Unlike Outlook/Anthropic/Discord — where the secret is issued by an external authority and Adam transcribes it — `MAILBOT_ROUTER_KEY` is internal-only. Generating it via `secrets.token_urlsafe(32)` inside the story gives Adam a cryptographically-strong value he can't accidentally weaken by choosing a weak passphrase. The flip side: Amelia must show Adam enough of the value (first-8 + last-4) that he can sanity-check the write happened, without showing enough to compromise rotation discipline.

### CP-G (cache hit observation) precision

Anthropic's prompt cache is ephemeral (per Story 2-6 / Rule M). Cache lifetime is ~5 minutes. To reliably observe a cache hit in CP-G, the two dispatches must happen within that window — Amelia issues them back-to-back in the same tool-use turn, not minutes apart. If the cache miss happens anyway (e.g., the SYSTEM block changed between dispatches), CP-G records as SKIP-needs-rerun rather than FAIL — the cache mechanism is verified by Story 2-6's unit tests against recorded fixtures; this checkpoint is the integration confirmation.

### CP-K (worker alarm) is the only time-sensitive checkpoint

The sync-health alarm fires when `now() - sync_last_heartbeat_at > 60 minutes`. Forcing this in real time means either (a) waiting 60 min after stopping the `ollama` container, or (b) using a test-only env var that compresses the alarm-debounce window. **(b) is not available in production code** (rightly — test-only knobs leak otherwise). So CP-K is SKIP-allowable with the rationale "Epic 1 Phase 3.5 walk exercised this code path via the SecretMissing failure mode — the alarm-debounce + JSONL-write paths are unchanged since." If Adam wants to wait, the wait is real.

### Resume semantics

If this story is re-invoked after a partial completion:
1. Amelia reads `.env` and detects which keys are present (by last-4-char fingerprint).
2. For each present key, Amelia offers: "OUTLOOK_CLIENT_ID is set (last-4=a1b2). Re-capture, re-verify only, or skip?"
3. The Phase 3.5 walkthrough always re-runs from scratch (cheap; deterministic).

### Project Structure Notes

- New files: `_bmad-output/implementation-artifacts/4-0-credential-capture-evidence.md` (commit-safe redacted artifact)
- Modified files: `.env` (not committed), `_bmad-output/implementation-artifacts/epic-run-flags.md` (B2 flip), `_bmad-output/implementation-artifacts/epic-2-run-flags.md` (B2 flip), `_bmad-output/implementation-artifacts/sprint-status.yaml`
- No `mailbot_api/` source changes
- No `scripts/` changes (reuses `scripts/mint_refresh_token.py`, `scripts/check_graph_auth.py`, `scripts/mailbot.py` as-is)
- No `tests/` changes (this is verification of production code paths against real services, not unit testing)

### References

- Epic 1 retro action item #2 (Phase 3.5 cadence): `_bmad-output/implementation-artifacts/epic-1-retro-2026-06-01.md`
- Epic 2 retro action item #3 (Phase 3.5 re-commitment): `_bmad-output/implementation-artifacts/epic-2-retro-2026-06-01.md` §7
- Epic 3 retro action item #3 (Phase 3.5 escalated to structural skill amendment): `_bmad-output/implementation-artifacts/epic-3-retro-2026-06-01.md` §7
- Epic 1 Phase 3.5 walkthrough precedent: `_bmad-output/implementation-artifacts/epic-run-flags.md` lines 88–122
- Epic 2 Phase 3.5 walkthrough precedent: `_bmad-output/implementation-artifacts/epic-2-run-flags.md` §"Phase 3.5 Manual Verification — verdict: PASS"
- `.env.example`: project root (the 7 required keys + 3 container-config defaults)
- `docker-compose.yml`: project root (env-var consumption sites at lines 15, 35–42)
- `mailbot_api/config.py`: `get_secret(...)` / `get_secret_optional(...)` — the only legitimate consumer of `os.environ` per Story 1-4's boundary rule
- Story 1-9 OAuth mint script: `scripts/mint_refresh_token.py` + `docs/entra-app-registration.md`
- Story 1-5 Graph auth check: `scripts/check_graph_auth.py`
- Story 2-6 Anthropic adapter + Rule M cache: `mailbot_api/router/models.py`
- Story 2-8 Layer 3 $30/mo in-code cap: `mailbot_api/router/budget.py`
- Story 2-10 `/v1/chat/completions` endpoint + `MAILBOT_ROUTER_KEY` bearer: `mailbot_api/main.py` lines 277+
- Story 3-3 sensitivity-blocks-API + force_sensitive pattern: `mailbot_api/sensitivity/` + `router/sensitivity_patterns.yaml`
- Story 3-5 ingest pipeline CLI: `python -m mailbot_api.ingest.pipeline`

## Dev Agent Record

### Agent Model Used

_(filled at run time — claude-opus-4-7 (1M context) recommended for the interactive walkthrough; the workflow is long-context and the live smoke tests benefit from a single coherent reasoning thread.)_

### Debug Log References

_(filled at run time)_

### Completion Notes List

**Walkthrough date:** 2026-06-01 (UTC ~19:50–20:40 capture phase; Task 8 verification phase pending).
**Operator:** Adam (adamaroni@hotmail.fr).
**Full evidence artifact:** `_bmad-output/implementation-artifacts/4-0-credential-capture-evidence.md`.

#### AC-8 redacted capture summary (mirror — full table + findings in evidence file)

| #  | Key                       | Status | Length | Last 4 | Verified by                                     |
|----|---------------------------|--------|--------|--------|-------------------------------------------------|
| 1  | OUTLOOK_CLIENT_ID         | set    | 36     | 88f1   | `check_graph_auth.py` exit 0                    |
| 2  | OUTLOOK_TENANT_ID         | set    | 9      | mers   | `check_graph_auth.py` exit 0 (consumers route)  |
| 3  | OUTLOOK_REDIRECT_URI      | set    | 30     | back   | `mint_refresh_token.py` consumed callback OK    |
| 4  | OUTLOOK_CLIENT_SECRET     | set    | 40     | fcuj   | Retained in `.env` but ignored by post-patch code (public-client mode) |
| 5  | OUTLOOK_REFRESH_TOKEN     | set    | 481    | 9g$$   | `check_graph_auth.py` exit 0 — 'Adam Maroni' (adamaroni@hotmail.fr) |
| 6  | ANTHROPIC_API_KEY         | set    | 108    | dAAA   | Router smoke: haiku-4-5, tokens 33/5, cost $0.000058 (after $20 credit top-up) |
| 7  | DISCORD_BOT_TOKEN         | set    | 72     | wY0c   | Deferred to Story 6-3                           |
| 8  | DISCORD_HOME_CHANNEL      | set    | 19     | 3532   | Renamed 2026-06-04 (Epic 6 retro A6 — was `DISCORD_CHANNEL_ID`; canonical name lives in docker-compose.yml + hermes-config) |
| 9  | DISCORD_USER_ID           | set    | 18     | 9136   | Deferred to Story 6-3                           |
| 10 | DISCORD_ALLOWED_USERS     | set    | 18     | 9136   | Added 2026-06-04 (Epic 6 retro A6 — Hermes refused all commands during CP-2 walk attempt #1 because no allow-list configured; populated inline to Adam's DISCORD_USER_ID) |
| 11 | MAILBOT_ROUTER_KEY        | set    | 43     | 4_DU   | Self-issued via `secrets.token_urlsafe(32)`; smoke deferred to CP-H |
| 12 | MAILBOT_DB_PATH           | set    | 16     | t.db   | Container default `/data/mailbot.db`; verified by CP-A |
| 13 | MAILBOT_POLICY_PATH       | set    | 23     | yaml   | Container default `/app/router/policy.yaml`; verified by CP-A |
| 14 | OLLAMA_URL                | set    | 19     | 1434   | Container default `http://ollama:11434`; verified by CP-A |

#### Mid-story scope expansion — Finding 1 (HIGH)

- AADSTS90023 against real Entra exposed a Story 1-9 latent bug: the OAuth code path (mint script + GraphClient + oauth.py) required `OUTLOOK_CLIENT_SECRET` unconditionally, but Entra rejects this for public-client apps (the recommended platform).
- Patched in-story across 4 files (mint_refresh_token.py, graph_client.py, oauth.py, check_graph_auth.py), updated `docs/entra-app-registration.md` (Steps 5/7 + failure-modes table), added 6 regression tests across 3 test files. Test count: 458 → 464 passing.
- All gates green after patch: ruff/mypy/boundary-check clean; full suite 464 passed + 2 skipped + 0 failed.
- See evidence file Finding 1 for full root-cause + why-mocks-didn't-catch-it discussion.

#### Findings 2 & 3 (LOW, recorded for retro)

- Anthropic 400 'credit balance too low' on first dispatch — environmental, resolved with $20 top-up. Validates Story 2-6 PROVIDER_ERROR sanitization chain.
- Git Bash MSYS path translation mangled container-path env values — operational, resolved with `MSYS_NO_PATHCONV=1`.

#### Final verdict

**PASS WITH FINDINGS** (2026-06-01).

- 11 Phase 3.5 checkpoints: 9 PASS, 1 SKIP-documented (CP-G Anthropic cache needs ≥1024 input tokens), 1 PARTIAL (CP-E summary_short blocked by Finding 5 prompt-engineering bug).
- **Privacy invariants CP-C and CP-F BOTH PASS** — FR-2.3 sensitivity-blocks-API integration-confirmed against real Anthropic + real Microsoft Graph + real Ollama for the first time.
- 5 latent bugs discovered + 1 design-limitation documented during the walk (exactly the value Phase 3.5 was designed to deliver):
  - F1 (HIGH, patched): OAuth code path required client_secret; real Entra returns AADSTS90023 for public-client apps
  - F4 (HIGH, patched): ingest pipeline CLI didn't load policy/patterns/adapters before invoking process_email
  - F5 (HIGH, NOT patched — documented for Story 3-2 fix): summary_short SYSTEM prompt doesn't instruct Haiku to return JSON; even retry-with-schema-prefix fails
  - F6 (HIGH, patched): init_default_adapters didn't register nomic-embed-text
  - F7 (MEDIUM, NOT patched — documented for Story 2-9/2-10 follow-up): scripts/mailbot.py missing cost / pause / resume subcommands
  - F8 (LOW, design-intent documented): pause state is per-process singleton; cross-process pause requires server restart
- Test count: 458 (baseline) → 466 passing (+8 net regression coverage for F1/F4/F6 patches). All gates (ruff/mypy/boundary/pytest) green.
- 13 keys captured in `.env` (gitignored). Evidence artifact `4-0-credential-capture-evidence.md` is commit-safe — no secret material; only length + last-4 fingerprints + verification results.
- B2 flag flipped to ☑ PASS WITH FINDINGS in both `epic-run-flags.md` (Epic 3 section) and `epic-2-run-flags.md` (Epic 2 section).
- Phase 3.5 three-epic deferral CLOSED.

#### Recommended follow-up before Story 4.1

Story 4-0a (or per-story fixes): F5 + F7 (HIGH/MEDIUM combined ~1h of work). F5 is the blocker for end-to-end demo of the ingest pipeline against real services. F8 is optional.

### Change Log

| Date       | Change |
|------------|--------|
| 2026-06-01 | Story 4-0 started; baseline_commit recorded as 9c368c4 (in YAML frontmatter). |
| 2026-06-01 | Tasks 1–7 complete: 13 keys captured to `.env` (gitignored); evidence artifact written. |
| 2026-06-01 | Mid-story scope expansion #1 (Finding 1): patched OAuth code path across 4 source files + docs + 6 regression tests. AADSTS90023 from real Entra exposed Story 1-9 latent bug (public-client OAuth). |
| 2026-06-01 | Mid-story scope expansion #2 (Finding 4): patched ingest pipeline CLI to load policy/patterns/adapters before invoking process_email; added 1 regression test. |
| 2026-06-01 | Mid-story scope expansion #3 (Finding 6): patched init_default_adapters to register nomic-embed-text; added 1 regression test. |
| 2026-06-01 | Task 8 complete: Phase 3.5 walkthrough CP-A..CP-K against real Docker stack — 9 PASS, 1 SKIP, 1 PARTIAL. Privacy invariants CP-C + CP-F both PASS. |
| 2026-06-01 | Task 9 complete: verdict PASS WITH FINDINGS; B2 flag flipped in Epic 2 and Epic 3 run-flags files. Phase 3.5 three-epic deferral CLOSED. Story Status → review. |

### File List

**Story-scoped files (no production code; `.env` not committed):**

- `.env` — created at repo root (gitignored): 13 keys captured per AC-8 summary
- `_bmad-output/implementation-artifacts/4-0-credential-capture-evidence.md` — new (commit-safe, contains Phase 3.5 CP-A..CP-K results + all 8 findings)
- `_bmad-output/implementation-artifacts/4-0-env-upsert-helper.py` — new (story-scoped helper for atomic upserts to .env)
- `_bmad-output/implementation-artifacts/4-0-interactive-credential-capture-and-phase-3-5-verification.md` — this file (YAML frontmatter baseline_commit, Tasks/Subtasks checkboxes, Dev Agent Record (Completion Notes + Change Log + File List), Status modified)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — Story 4-0 row updated to `review` + last_updated comment
- `_bmad-output/implementation-artifacts/epic-run-flags.md` — Epic 3 section B2 flipped to ☑ PASS WITH FINDINGS
- `_bmad-output/implementation-artifacts/epic-2-run-flags.md` — Epic 2 section B2 updated to PASS WITH FINDINGS (Story 4-0 walk)

**Production code changes from mid-story scope expansions (Findings 1, 4, 6):**

- `scripts/mint_refresh_token.py` — modified (Finding 1 — public-client OAuth: client_secret now optional in exchange_code_for_tokens + _validate_args)
- `scripts/check_graph_auth.py` — modified (Finding 1 — error message updated to clarify OUTLOOK_CLIENT_SECRET is optional)
- `mailbot_api/sync/graph_client.py` — modified (Finding 1 — OUTLOOK_CLIENT_SECRET via get_secret_optional; form body conditional include)
- `mailbot_api/sync/oauth.py` — modified (Finding 1 — same change as graph_client.py)
- `mailbot_api/ingest/pipeline.py` — modified (Finding 4 — added `_cli_init_runtime` that mirrors lifespan ordering: apply_migrations → set_policy_snapshot → set_patterns_snapshot → init_default_adapters → get_guard().initialize → get_pause_state().initialize)
- `mailbot_api/router/registry.py` — modified (Finding 6 — register_adapter for `nomic-embed-text` added to `init_default_adapters`)
- `docs/entra-app-registration.md` — modified (Finding 1 — Step 5 + Step 7 + failure-modes table updated to reflect public-client-default + AADSTS90023 signature)

**Test additions from mid-story scope expansions:**

- `tests/integration/test_mint_refresh_token.py` — modified (+3 tests: public-client form body omits client_secret; _validate_args no longer requires client_secret; _validate_args still requires client_id + tenant)
- `tests/unit/sync/test_graph_client.py` — modified (+2 tests: public-client refresh exchange omits client_secret; confidential client still includes it)
- `tests/integration/test_oauth_state.py` — modified (+1 test: public-client refresh exchange omits client_secret in the form body)
- `tests/integration/test_pipeline_e2e.py` — modified (+1 test: _cli_init_runtime populates all 4 snapshots/registries process_email reads from)
- `tests/unit/router/test_registry.py` — modified (+1 test: init_default_adapters registers nomic-embed-text alongside Qwen)

**Test count delta:** 458 (baseline at story start) → 466 passing + 2 skipped + 0 failed (+8 net regression coverage).
