# Runbook: Discord slash-command registration for the `/model` family

**Story:** 9.5.1 (Path γ discharge — reframed 2026-07-03)
**Script:** [scripts/register_discord_commands.py](../../scripts/register_discord_commands.py)
**When to run:** once per Discord application, plus once per `router/policy.yaml` schema change that adds or removes a task.

This runbook covers the out-of-band registration flow for the `/model` slash-command family (`/model set`, `/model persist`, `/model inspect`) with the Discord Developer Portal. The registration is **one-shot and server-persistent** — once Discord has the commands, they appear in every user's slash autocomplete, and stock upstream `nousresearch/hermes-agent` routes their interactions to mailbot-api's MCP verbs unchanged. **No Hermes source is modified.**

---

## Section 1 — OAuth2 scope requirement

Discord slash-command registration requires the bot token to carry the **`applications.commands`** OAuth2 scope (in addition to `bot`, which Hermes already uses for its Gateway connection).

**How to verify the current token has the scope:**

1. Open the Discord Developer Portal → your application → **OAuth2** → **URL Generator**.
2. Under **Scopes**, check both `bot` and `applications.commands`.
3. Compare the resulting invite URL's scope list against the URL used when the current bot was originally invited to your test guild.

**If the current Hermes bot token lacks `applications.commands`:**

1. Portal → your application → **OAuth2** → **URL Generator** → check both scopes.
2. Copy the generated URL and open it in a browser.
3. Re-invite the bot to your test guild. Discord Portal will merge the new scope with the existing installation.
4. The bot token itself does not change; only its permitted scope set expands.
5. No `.env` update is needed — same token, expanded permissions.

There is no downside to re-inviting: Discord treats it as a scope-widening operation, not a re-installation.

---

## Section 2 — Environment variable setup

The script reads two environment variables at `--apply` / `--delete-all` time:

| Variable                 | Source                                                       | Secret? |
| ------------------------ | ------------------------------------------------------------ | ------- |
| `DISCORD_BOT_TOKEN`      | Discord Portal → your application → **Bot** → **Token**      | **YES** |
| `DISCORD_APPLICATION_ID` | Discord Portal → your application → **General Information**  | No      |

**Setting them locally for a one-shot run (PowerShell):**

```powershell
$env:DISCORD_BOT_TOKEN = "<paste token here>"
$env:DISCORD_APPLICATION_ID = "<paste application ID here>"
.venv\Scripts\python.exe -m scripts.register_discord_commands --apply
```

**Security discipline — the bot token is a secret:**

- Do NOT paste the token into any chat window (agent conversation, Discord, Slack, etc.). Copy it directly from the Portal to your terminal or `.env` file. See the memory entry `feedback_oauth_token_handling.md` for the full rule.
- The token grants full bot permissions on any guild it is invited to. Rotate it via the Portal ("Reset Token") if you suspect exposure.
- If you keep the token in `.env`, ensure `.env` is listed in `.gitignore`.

**`.env.example` entries:**

- `DISCORD_BOT_TOKEN=` — see [.env.example](../../.env.example) line 7 (already present, added in an earlier story)
- `DISCORD_APPLICATION_ID=` — added by this story (Task 6)

---

## Section 3 — Run procedure

### 3.1 Dry-run (inspect the payload)

Always dry-run first. This confirms the JSON payload matches what you expect before hitting Discord.

```powershell
.venv\Scripts\python.exe -m scripts.register_discord_commands --dry-run
```

Output is the exact JSON body the script will POST to Discord. Inspect the subcommand list — you should see `set`, `persist`, `inspect` — and confirm the `persist` task-choices list matches your `router/policy.yaml` task set.

### 3.2 Apply (register with Discord)

```powershell
.venv\Scripts\python.exe -m scripts.register_discord_commands --apply
```

Expected output on success:

```text
Registered /model → command_id=<19-digit snowflake>
Summary: registration complete. Discord commands appear in-client autocomplete within ~1 minute globally. Verify by typing / in Discord.
```

Exit codes:

| Code | Meaning                                                             |
| ---- | ------------------------------------------------------------------- |
| 0    | All commands registered successfully                                |
| 1    | Discord returned a 4xx or 5xx — see stderr for the Discord error    |
| 2    | Missing `DISCORD_BOT_TOKEN` or `DISCORD_APPLICATION_ID` env var     |

### 3.3 Verify in Discord

1. Open the Discord client.
2. In any channel of a guild where the bot is invited, type `/`.
3. The autocomplete list should now include `/model` with three subcommand entries: `set`, `persist`, `inspect`.
4. Global commands can take up to 1 hour to propagate in the worst case; guild-specific commands are near-instant. This script uses the global endpoint (`/applications/{app_id}/commands`, not `/applications/{app_id}/guilds/{guild_id}/commands`).

If the commands do not appear after a few minutes:

- Check the exit code — a silent 4xx would have exited 1.
- Re-run `--dry-run` and inspect the payload for schema issues.
- Use `--delete-all` (Section 4) to clear stale registrations and retry.

---

## Section 4 — Idempotency + iteration via `--delete-all`

**Re-`--apply` is safe.** Discord Portal deduplicates by `(application_id, command_name)` — re-POSTing the same payload updates the existing command in place rather than creating a duplicate.

**Payload regeneration flow:** if `router/policy.yaml` gained or lost a task and you want the stale `/model persist` choices removed from Discord:

```powershell
# Enumerate + delete every registered application command
.venv\Scripts\python.exe -m scripts.register_discord_commands --delete-all

# Then re-register with the current payload
.venv\Scripts\python.exe -m scripts.register_discord_commands --apply
```

`--delete-all` is scoped to global application commands only. Guild-specific commands (if any) are not touched.

---

## Section 5 — What this runbook does NOT change

**Hermes source is unmodified.** This is a MailBot-side out-of-band operation:

- Registration happens via HTTPS from your workstation (or CI) to Discord's servers.
- Discord persists the command definitions server-side.
- When a user invokes `/model set model:qwen` in Discord, Discord dispatches the interaction to the endpoint Hermes already exposes (Hermes's existing Gateway + interaction handler).
- Hermes routes the interaction to mailbot-api's `set_model_oneshot` MCP verb via its existing MCP dispatch — no source change required in Hermes.

**Why this matters:** MailBot deployments (KVM images with pre-integrated stock `nousresearch/hermes-agent`) do not need a custom Hermes fork. Bumping the Hermes image version does not lose the slash-command registration — the registration lives on Discord's side, independent of Hermes releases.

**What Hermes DOES do:** receives Discord interaction webhooks, routes them to MCP verbs. That machinery was shipped in earlier Epic 9 stories (Stories 9-3 / 9-4 delivered the MCP verbs; Hermes's built-in interaction router handles the dispatch). This runbook adds the missing step that tells Discord the commands exist.

---

## Section 6 — References

- Discord Developer Portal — Application Commands: <https://discord.com/developers/docs/interactions/application-commands>
- Discord API error codes: <https://discord.com/developers/docs/topics/opcodes-and-status-codes#json>
- Epic 9.5 planning: [_bmad-output/planning-artifacts/epics.md § "Story 9.5.1"](../../_bmad-output/planning-artifacts/epics.md)
- Original halt + reframe decision: [_bmad-output/implementation-artifacts/epic-9-5-run-flags.md](../../_bmad-output/implementation-artifacts/epic-9-5-run-flags.md)
- Downstream: [_bmad-output/planning-artifacts/epics.md § "Story 9.5.2"](../../_bmad-output/planning-artifacts/epics.md) — the live walks that verify this registration end-to-end.
