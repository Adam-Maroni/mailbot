# Hermes Agent — Reconciliation Notes for Story 6-0

**Date:** 2026-06-02
**Author:** Amelia (autonomous-epic-run dev pass)
**Source upstream URL:** `https://hermes-agent.nousresearch.com/docs/`
**Probed image digest source:** `nousresearch/hermes-agent:latest` (pull on 2026-06-02)
**Purpose:** Reconcile Story 5-4's invented `hermes-config/config.yaml` schema against the actual Hermes runtime contract. Close F3 / F4 / F5 carry-forward from Epic 5 Phase 3.5 Section B.

> **Phase 6-0a deviation note:** the canonical `docs-archiver` skill could not run because `FIRECRAWL_API_KEY` is unset on this dev host. As a fallback, the critical Hermes docs pages were fetched via `WebFetch` (Configuration, Messaging, Discord, MCP, Installation, Quickstart) — sufficient evidence for the schema reconciliation but does NOT produce the full `docs/external/hermes-agent/{SITE-MAP.md,PAGE-GRADING.md,pages/}` mirror format the skill normally builds. If a later story needs the full mirror (e.g., for offline reference), Adam should set `FIRECRAWL_API_KEY` in `.env` and re-run `docs-archiver` then.

---

## §1. Docs-says — the real Hermes config schema

### 1.1 File location & env-var contract

- **Config path:** `~/.hermes/config.yaml` for native installs. Inside `nousresearch/hermes-agent:latest` Docker, the Dockerfile pins `ENV HERMES_HOME=/opt/data`, so the in-container path is **`/opt/data/config.yaml`**. Confirmed live by `hermes config path` → `/opt/data/config.yaml`.
- **Secrets path:** `~/.hermes/.env` (native) / `/opt/data/.env` (Docker). Confirmed live by `hermes config env-path` → `/opt/data/.env`.
- **Env-var substitution in YAML:** Hermes supports `${VAR_NAME}` syntax. Undefined vars at runtime remain literal placeholders. `$VAR` (no braces) is NOT expanded.
- **Precedence:** CLI flags > `~/.hermes/config.yaml` > `~/.hermes/.env` > built-in defaults. Secrets belong in `.env`; everything else in `config.yaml`.

### 1.2 Top-level config keys that matter for MailBot

The full Hermes schema has ~30 top-level keys; MailBot needs a subset.

| Real top-level key | Type | Purpose for MailBot |
| --- | --- | --- |
| `model` | mapping | **Main provider config** — `model.default`, `model.provider`, `model.base_url`, `model.api_key`, `model.context_length`, `model.request_timeout_seconds`, plus per-provider override sub-mappings. |
| `auxiliary` | mapping | **Helper-model config per task family** — sub-keys: `vision`, `web_extract`, `compression`, `approval`, `triage_specifier`, `skills_hub`, `mcp`, `title_generation`, `profile_describer`, `kanban_decomposer`. Each takes `provider`, `model`, `base_url`, `api_key`, `timeout`. Default `provider: "auto"` routes to main model. |
| `mcp_servers` | mapping | **MCP client config** — each top-level key under `mcp_servers` is a server name; the entry takes either (`command` + `args` + `env`) for stdio OR (`url` + `headers`) for HTTP. Also `enabled`, `timeout`, `connect_timeout`, `tools.{include,exclude,prompts,resources}`, `sampling.{enabled,model,max_tokens_cap,timeout,max_rpm}`, `auth: oauth`, `oauth.{client_id,client_secret}`. |
| `discord` | mapping | **Discord gateway config** — `require_mention`, `thread_require_mention`, `free_response_channels`, `auto_thread`, `reactions`, `ignored_channels`, `no_thread_channels`, `history_backfill`, `history_backfill_limit`, `channel_prompts`, `allow_mentions.{everyone,roles,users,replied_user}`. **Intents are NOT in config** — they're auto-configured by Hermes; they must be enabled in the Discord Developer Portal. |
| `streaming` | mapping | Edit-in-place transport for gateway responses; defaults are fine. |
| `prompt_caching` | implicit | Auto-enabled on Anthropic / OpenRouter / Nous Portal; cannot be disabled; TTL `1h`. **No config key required.** |
| `display`, `compression`, `agent`, `memory`, `web`, `security`, `approvals`, `timezone`, etc. | mappings | Defaults are fine for MailBot's first deploy. |
| `group_sessions_per_user` | bool | Per-user session isolation in shared chats; default `true`. Keep default. |

### 1.3 Fallback providers — NOT a top-level config key

Story 5-4 shipped `fallback_providers:` at the top level. **Real Hermes does NOT use a `fallback_providers:` config block.** Fallback chains are managed via the **`hermes fallback`** CLI subcommand (`hermes fallback add`, `hermes fallback list`, `hermes fallback remove`, `hermes fallback clear`). The fallback chain is stored in the same config file but under a different shape (likely under a `fallback` or `providers` namespace — exact key not surfaced by the docs page consulted, but `hermes fallback list` reads from config so the persistence target IS `config.yaml`). The operator runs `hermes fallback add anthropic claude-opus-4.6` (or similar) interactively; the CLI writes the entry.

**Implication for MailBot:** the NFR-OPS-6 emergency-only fallback to `api.anthropic.com` should be set up via `hermes fallback add anthropic claude-opus-4-7` from inside the Hermes container's first-run setup, NOT hand-written as a YAML block. The `hermes-config/config.yaml` we ship should NOT carry the invented `fallback_providers:` block — that block will be either ignored or trigger a schema warning when Hermes loads the config.

### 1.4 Slash commands — runtime-registered, NOT config-file-driven

Story 5-4 shipped a `gateway.discord.slash_commands:` list with 8 commands (cost / pause / resume / cancel / mute / label / budget / confirm). **Real Hermes does NOT register slash commands from config YAML.** The Discord docs page is explicit:

> "Hermes automatically registers installed skills as native Discord Application Commands."

Slash commands come from:
1. **Installed skills** — Hermes scans `~/.hermes/skills/` (the bind-mounted `/opt/data/skills/` in our Docker case) for skill directories with the right shape, and auto-registers each as a slash command.
2. **Built-in commands** — Hermes ships its own slash commands (`/hermes`, etc.).

The Discord-portal-side `MESSAGE_CONTENT` and Server Members intents must still be enabled by hand (Adam already did this at the Discord Developer Portal).

Registration sync policy is controlled via env var `DISCORD_COMMAND_SYNC_POLICY` (`safe` | `bulk` | `off`).

**Implication for MailBot:** MailBot's 8 slash commands need to be expressed as Hermes **skills**, not as config-YAML entries. The existing `hermes-config/skills/mailbot/SKILL.md` from Story 5-5 is the right surface — but its structural contract (skill manifest format, MCP-verb dispatch convention) needs to match what `hermes skills install` expects. The Story 5-6 dispatcher contract becomes: each slash command corresponds to a skill bundled in `hermes-config/skills/mailbot/` that calls the MCP verb on `mailbot-api`. This is a larger contract revision than this story alone can deliver — Story 6-3's notification dispatcher work + a follow-up story to refactor `hermes-config/skills/mailbot/` will need to close this loop. **This story (6-0) closes the schema-shape gap; the skill-as-slash-command refactor is a downstream Epic 6 / Epic 7 story.**

### 1.5 Discord environment variables (`.env` side, not `config.yaml`)

Per the Discord docs page, these belong in `.env`:

- `DISCORD_BOT_TOKEN` — required, bot auth credential
- `DISCORD_ALLOWED_USERS` — required for our deploy; comma-separated Discord user IDs that may DM the bot. MailBot has one user (Adam); set to Adam's Discord ID.
- `DISCORD_ALLOWED_ROLES` — optional, OR'd with allowed-users
- `DISCORD_HOME_CHANNEL` — channel ID for proactive messages (digest, urgent notifications). MailBot needs this set to Adam's DM channel ID (or a dedicated MailBot channel ID).
- `DISCORD_REQUIRE_MENTION`, `DISCORD_FREE_RESPONSE_CHANNELS`, `DISCORD_AUTO_THREAD`, `DISCORD_REACTIONS` — optional behavior tuning; most have sensible defaults.
- `DISCORD_COMMAND_SYNC_POLICY` — `safe` (default) is fine.

### 1.6 Provider routing for MailBot's main-inference path

Story 5-4's intent: route Hermes's main inference through `mailbot-api`'s `/v1/chat/completions` so all calls go through the Router. Real schema mapping:

```yaml
model:
  default: "hermes_aux"          # policy.yaml task type
  provider: "custom"             # custom OpenAI-compatible endpoint
  base_url: "http://mailbot-api:8000/v1"
  api_key: "${MAILBOT_ROUTER_KEY}"
```

(Story 5-4 used `provider: "openai-compatible"` which doesn't exist in the real provider list. Use `provider: "custom"` per the docs.)

For the `auxiliary` blocks (compression, title_generation) Story 5-4 invented, the real schema is:

```yaml
auxiliary:
  compression:
    provider: "custom"
    base_url: "http://mailbot-api:8000/v1"
    model: "hermes_aux"
    api_key: "${MAILBOT_ROUTER_KEY}"
    # NOTE: there is no documented `headers:` key for auxiliary entries.
    # The caller_origin propagation Story 5-4 designed via headers cannot be
    # expressed in config; instead it has to flow via the request layer.
    # mailbot-api's /v1/chat/completions endpoint MUST infer caller_origin
    # from the model field ("hermes_aux") combined with the requesting
    # context (e.g., the task at hand if it's exposed). This is a Story 5-4
    # follow-up — auxiliary headers do NOT pass through.
  title_generation:
    provider: "custom"
    base_url: "http://mailbot-api:8000/v1"
    model: "hermes_aux"
    api_key: "${MAILBOT_ROUTER_KEY}"
```

**Implication:** Story 5-4's `X-Mailbot-Caller-Origin: hermes-aux-compression` header trick does NOT survive. Two options:

1. **Accept the lossiness** — every Hermes-side auxiliary call lands in `router_calls` with `caller_origin = "hermes_aux"` (no sub-distinction between compression / title / main). Cost forensics lose granularity but stay correct in aggregate.
2. **Use distinct model names** — declare `hermes_aux_compression` and `hermes_aux_title` as separate policy.yaml task types pointing to the same underlying model; the model field in each auxiliary block becomes the distinguishing key, and the Router's `task_type` parameter (already part of the OpenAI request's model field) lets `mailbot-api` populate `caller_origin` correctly.

Option 2 is cleaner BUT requires policy.yaml edits that would touch the Router boundary in ways the dev pass for 6-0 shouldn't.

**Decision shipped in Story 6-0d (Option 1):** `hermes-config/config.yaml` keeps `model: "hermes_aux"` in BOTH `auxiliary.compression` and `auxiliary.title_generation` blocks. Caller_origin granularity loss is accepted: every Hermes-side auxiliary call lands in `router_calls` with `caller_origin = "hermes_aux"` (no sub-distinction). Aggregate cost discipline holds.

**Option 2 deferred to follow-up:** when Story 6-3 or 6-5 needs the per-task forensic breakdown, `policy.yaml` gains `hermes_aux_compression` + `hermes_aux_title` task entries (clones of `hermes_aux` with distinct caller_origin defaults) AND this `config.yaml` switches to those names — single coordinated change. Filed as §6 item 2.

### 1.7 MCP server entry — `mcp_servers`, not `mcp_clients`

Story 5-4 used `mcp_clients:` (a top-level list) with each entry naming `{name, url, transport: streamable_http}`. **Real Hermes:** `mcp_servers:` (a top-level mapping where each key is the server name), with values like:

```yaml
mcp_servers:
  mailbot-api:
    url: "http://mailbot-api:8000/mcp"
    headers:
      Authorization: "Bearer ${MAILBOT_ROUTER_KEY}"
    enabled: true
    timeout: 30
    # tools.include / tools.exclude omitted = all tools registered
```

**Transport name:** the docs name two transports — `stdio` (via `command`/`args`) and HTTP (via `url`/`headers`). The Story 5-4 invented label `transport: streamable_http` is not present in the schema; the HTTP transport is implicit when `url:` is present.

**Tool naming convention discovered:** Hermes prefixes registered MCP tools with `mcp_<server_name>_<tool_name>`. So `mailbot-api`'s `find_emails` tool gets registered to the LLM as `mcp_mailbot-api_find_emails`. The Hermes-side dispatcher (and any test harness verifying the tool count) needs to be aware of this prefix.

**Implication for Story 5-2's claim "11/16 MCP tools registered":** all 16 still register; they just appear as `mcp_mailbot-api_find_emails` etc. to the Hermes agent. The count is unchanged; the names are prefixed. Phase 6-0e CP5 verification must check the prefixed names.

---

## §2. Image-says — what `nousresearch/hermes-agent:latest` actually runs

### 2.1 Entrypoint contract

```
ENTRYPOINT: /init /opt/hermes/docker/main-wrapper.sh
CMD: (empty)
WORKDIR: /opt/hermes
ENV HERMES_HOME=/opt/data
ENV PATH=/opt/hermes/bin:/opt/hermes/.venv/bin:/opt/data/.local/bin:$PATH
```

The `/init` binary is s6-overlay v3's init. It runs through three stages:

- **Stage 1** — `/etc/cont-init.d/*` (one-shot init scripts; root). The image ships:
  - `01-hermes-setup` (→ `/opt/hermes/docker/stage2-hook.sh`) — UID/GID remap (`PUID`/`PGID` aliases), volume chown, config seeding, skills sync, Docker-socket group membership for DooD.
  - `015-supervise-perms` (stamps perms before stage 2).
  - `02-reconcile-profiles` (legacy profile migration).
- **Stage 2** — supervised long-running services. **The image has NO `/etc/services.d/`.** This is the key correction to Epic 5 F4. There is NO supervised hermes service the way s6-overlay typically operates; instead, the image uses **s6-overlay's "main program" model** where `/init` runs `main-wrapper.sh` as the CMD process and the container's lifecycle follows CMD's lifecycle.
- **Stage 3** — `main-wrapper.sh` runs with full stdin/stdout/stderr, executes the routing logic below, and `exec`s `hermes ...`.

### 2.2 `main-wrapper.sh` routing logic (transcribed from `cat`)

```sh
# /opt/hermes/docker/main-wrapper.sh — shebang /command/with-contenv sh
# Routing rules:
#   no args                       → exec `hermes` (default — the interactive TUI)
#   first arg is an executable    → exec it directly (sleep, bash, sh, ...)
#   first arg is anything else    → exec `hermes <args>` (subcommand passthrough)
# Drops privilege via s6-setuidgid hermes when running as root.
export HOME=/opt/data
cd /opt/data
. /opt/hermes/.venv/bin/activate
[ $# -eq 0 ] && drop hermes
command -v "$1" >/dev/null && drop "$@"
drop hermes "$@"
```

**Critical implication:** the Docker-level `command:` in `docker-compose.yml` is NOT swallowed — it's routed through this wrapper. Setting `command: ["gateway", "run"]` causes `main-wrapper.sh` to execute `hermes gateway run` because the first arg `gateway` is not on PATH but is a hermes subcommand. **F4 is closeable.**

### 2.3 The right daemon entry point — discovered via `hermes gateway --help`

```
hermes gateway run    # Run gateway in foreground (recommended for WSL, Docker, Termux)
hermes gateway start  # Start the installed systemd/launchd background service (NOT for Docker)
hermes gateway stop / restart / status / install / uninstall / list / setup / migrate-legacy
```

**The Epic 5 dev pass tried `hermes gateway start`. That was the wrong command** — `start` is for systemd/launchd-installed services, which the Docker image does not have. **The right command is `hermes gateway run`** — explicitly documented as "recommended for Docker".

`hermes gateway run --help` further documents:

> "Inside the s6-overlay Docker image, normally `gateway run` is automatically redirected to the supervised s6 service (so the gateway gets auto-restart on crash, plus a supervised dashboard if `HERMES_DASHBOARD` is set). Pass `--no-supervise` to opt out..."

So `hermes gateway run` inside the Docker image automatically engages s6 supervision (long-running with auto-restart on crash). **F3 is closeable — the image DOES support daemon-mode operation, just through the right CLI subcommand.** Epic 5's framing ("the image is interactive-only") was wrong; the image is multi-mode and we used the wrong mode.

### 2.4 Env-var contract — verified inside the image

```
HOME=/root           (set by docker; main-wrapper.sh overrides to /opt/data before exec)
HERMES_HOME=/opt/data
HERMES_WEB_DIST=/opt/hermes/hermes_cli/web_dist
PYTHONUNBUFFERED=1
PATH=/opt/hermes/bin:/opt/hermes/.venv/bin:/opt/data/.local/bin:$PATH
```

Plus the OpenAI-compatible env vars and platform-specific vars the running `hermes` process reads (from `.env` at `/opt/data/.env`, AND from container env passed by `docker-compose.yml environment:` block — both are honored).

### 2.5 Bind-mount expectations confirmed

The cont-init `stage2-hook.sh` script:

- Creates `/opt/data` if missing (`mkdir -p "$HERMES_HOME"`)
- Honors `HERMES_UID` / `HERMES_GID` (or `PUID` / `PGID` aliases) for UID/GID remap of the `hermes` user (default 10000)
- Chowns `/opt/data` to `hermes` user after remap

**Bind-mount-from-host implications:** Adam's host repo `./hermes-config/` is bind-mounted at `/opt/data` (read-write per Epic 5 F1 fix). The stage2-hook may chown the contents back to UID 10000 (or whatever the host UID maps to under `PUID`). For local dev (running compose as the Adam user), this means file ownership inside `hermes-config/` may flip to UID 10000 between container restarts — manageable via PUID/PGID env vars in docker-compose to align with Adam's host UID.

---

## §3. Divergence — invented schema vs real schema

| Invented (Story 5-4) | Real (Hermes 2026-06-02 docs + image) | Disposition for 6-0d |
| --- | --- | --- |
| Top-level `provider:` block with `base_url`, `model`, `api_key` | Top-level `model:` block with same fields plus `provider: "custom"` | **RENAME `provider:` → `model:` + add `provider: "custom"` line** |
| `auxiliary.compression` with `headers.X-Mailbot-Caller-Origin` | `auxiliary.compression` with same shape minus `headers:` | **DROP headers; document caller_origin lossiness; decision: use distinct `hermes_aux_compression` model name in a future policy.yaml task entry (out of scope for 6-0)** |
| `auxiliary.title_generation` with `headers.X-Mailbot-Caller-Origin` | Same shape minus `headers:` | Same as compression |
| Top-level `fallback_providers:` list | NOT in `config.yaml`; managed via `hermes fallback add` CLI; stored elsewhere | **DROP from `config.yaml`; document the operator-run fallback CLI setup in Adam's first-run runbook for the production deploy** |
| `gateway.discord.bot_token` | `DISCORD_BOT_TOKEN` env var | **DROP from `config.yaml`; require in `.env`** |
| `gateway.discord.intents: [...]` | NOT in config; auto-configured by Hermes | **DROP from `config.yaml`; document the Developer Portal step in the runbook** |
| `gateway.discord.slash_commands: [...]` (8 commands) | NOT config-driven; auto-registered from installed skills | **DROP from `config.yaml`; the 8 slash commands need to be expressed as a `hermes-config/skills/mailbot/` skill bundle in a follow-up story (out of scope for 6-0)** |
| Discord behavioral keys (`require_mention`, `auto_thread`, `free_response_channels`) | Real `discord:` block at top level (NOT under `gateway:`) with these as direct keys plus more | **MOVE `discord:` to top-level; expand to include `reactions`, `allow_mentions`, etc. with sensible MailBot defaults** |
| `mcp_clients:` list with `{name, url, transport}` | `mcp_servers:` mapping keyed by name with `{url, headers, enabled, timeout}` | **RENAME `mcp_clients` → `mcp_servers` + change to mapping form** |
| `transport: streamable_http` on MCP entry | NOT in schema; HTTP transport implicit when `url:` present | **DROP `transport:` line** |

---

## §4. Re-litigation trigger check

The story's re-litigation trigger fires if "Hermes docs explicitly state Docker image is interactive-only by design; native install required for daemon use." **No such statement was found.** On the contrary, `hermes gateway run --help` explicitly recommends `gateway run` for Docker, and the docs page lists Docker as a supported terminal backend AND mentions running Hermes itself in Docker via the official image is a supported (if not heavily-documented) path. **Re-litigation NOT triggered. Fix-forward proceeds.**

---

## §5. Action plan for phase 6-0d (config + compose rewrite)

1. **`hermes-config/config.yaml`** — full rewrite against the real schema, preserving every documented intent.
2. **`docker-compose.yml`** — remove the carry-forward comment block, add `command: ["gateway", "run"]` (which is the Docker-recommended foreground form that auto-engages s6 supervision), add `HERMES_HOME=/opt/data` env var explicitly (defensive; the image sets it but documenting in compose is clearer), add `DISCORD_ALLOWED_USERS` and `DISCORD_HOME_CHANNEL` env passthroughs.
3. **`scripts/check_hermes_config.py`** — full rewrite against the new schema; checks `model.base_url`, `auxiliary.{compression,title_generation}`, `mcp_servers.mailbot-api.url`, `discord` block presence; drops checks for the invented `provider:` top-level / `gateway.discord.slash_commands` / `fallback_providers:`.
4. **`epic-5-run-flags.md`** — amend F3 / F4 / F5 sections with `RESOLVED 2026-06-02 — see Story 6-0 walk record (this file + epic-6-run-flags.md)` status updates; do NOT rewrite the original findings.
5. **`.env.example`** — add the new Discord-side env vars (DISCORD_ALLOWED_USERS, DISCORD_HOME_CHANNEL) with stub comments. Adam fills them at first deploy.

---

## §6. Carry-forward items (NOT closed by Story 6-0, filed for follow-up)

1. **`hermes-config/skills/mailbot/` skill-bundle refactor** — Story 5-6's 8 slash commands need to be expressed as a Hermes skill bundle, not a config-YAML registry. Owner: Story 6-3 work (or a dedicated follow-up) — the dispatcher contract change is non-trivial.
2. **`caller_origin` granularity loss in auxiliary calls** — see §1.6 above. Plan: future `policy.yaml` task entries `hermes_aux_compression` + `hermes_aux_title` distinguished by the model name in the `auxiliary.<task>.model` field. Owner: Story 6-3 or 6-5 wiring.
3. **NFR-OPS-6 emergency fallback CLI provisioning** — operator-runs `hermes fallback add anthropic claude-opus-4-7` from inside the Hermes container during first deploy; document in Story 6-7's `setup_vps.sh` runbook. Owner: Story 6-7.
4. **Docs-archiver full mirror** — needs `FIRECRAWL_API_KEY`. Plan: when Adam has the key, re-run `docs-archiver` for the canonical `SITE-MAP.md` + `PAGE-GRADING.md` + `pages/` artifact. Until then, this `RECONCILIATION-NOTES.md` IS the reference. Owner: low-priority follow-up.

---

## §7. Phase 6-0e walk record (offline + DB-real surrogates)

Filled in during Step 9 of the dev pass — see `_bmad-output/implementation-artifacts/epic-6-run-flags.md` for the formal walk record.
