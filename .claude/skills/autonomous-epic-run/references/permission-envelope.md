# Permission Envelope — Pre-Flight & Logging Details

This file expands Steps 0.0 and 0.0b of the autonomous-epic-run skill. Load this when running the pre-flight envelope check or when the run produces permission prompts.

**Why a separate file:** the envelope details (allowed glob shapes, compound-exec gotchas, dev-env-skill prerequisites, log-before-answer rule) are dense reference material that rarely changes between stories. The orchestrator skill body stays focused on flow; the envelope mechanics live here.

## Why the envelope matters

The user chose "autonomous" — if the skill causes permission prompts mid-run, it has failed. Every command, tool call, and workflow step must be planned around the permissions already granted in `<settings-file>` (typically `.claude/settings.json`). The #1 failure mode in early production runs of this skill was dozens of compound `cd X && Y` commands triggering prompts and defeating the purpose of the skill.

## Rules of the envelope

1. **Never run compound `cd … && …` commands.** Permission matching does not unwrap compounds — even if both halves are individually allowed, the compound prompts. Use tool-native flags instead. Examples by stack:
   - **pnpm monorepo:** `pnpm --filter <name> <script>` or `pnpm --dir <path> <script>` (both bypass `cd`)
   - **npm/yarn workspaces:** `npm --workspace=<name> run <script>` / `yarn workspace <name> <script>`
   - **Jest in subdir:** `npx jest --rootDir=<path>` — not `cd <path> && npx jest`
   - **Pytest in subdir:** `pytest <path>` directly (pytest accepts a path arg) — not `cd <path> && pytest`. For a specific test: `pytest <path>::TestClass::test_name`. Discovery rooted elsewhere: `pytest --rootdir=<path>`.
   - **Ruff / mypy in subdir:** `ruff check <path>` / `mypy <path>` directly — not `cd <path> && ruff check .`
   - **Docker compose with a specific compose file:** `docker compose -f <path>/docker-compose.yml <cmd>` — not `cd <path> && docker compose <cmd>`. Exec into a container: `docker compose exec <service> <cmd>` (no `cd` needed; service name resolves from compose file).
   - **Git in sub-repo:** `git -C <path> <cmd>` — though from project root, plain `git status` / `git diff` / `git log` / `git add *` / `git stash *` cover almost everything

2. **Prefer tool calls over shell.** `Read` / `Write` / `Edit` / `Grep` / `Glob` bypass Bash permission rules entirely. Reach for `cat` / `head` / `tail` / `find` / raw `grep` only when nothing else fits — and even then, ask whether the dedicated tool would do it.

3. **Plain `ls` may or may not be allowed depending on the project's settings.** Many projects allow only `Bash(ls -la *)` and not bare `ls`. Use `Glob` for directory listings; if you must use `ls`, pass `-la`.

4. **If the agent realizes a required command is not in the envelope:** do NOT just run it and take the prompt. Either (a) find an equivalent allowed shape, (b) decompose into tool calls, or (c) surface the gap ONCE at the very start of the run ("these commands will prompt: X, Y, Z — extend settings.json before I continue?") and let the user decide. Twenty prompts mid-run is unacceptable; one up-front is fine.

5. **Pre-flight the envelope before Phase 1.** Step 0.0 reads `<settings-file>`, projects the commands this skill will run, and confirms coverage. If something's missing, it surfaces ONCE, up-front — never mid-run.

Every subagent spawned by this skill inherits this contract. Pass it through in their prompts: _"Stay inside the `<settings-file>` permission envelope — do not run commands that will prompt. Prefer tool-native filter flags over `cd X && <cmd>`."_

## Step 0.0 — Pre-flight checklist

Before Phase 1, read `<settings-file>` and build a short mental list of what command shapes the skill will need:

- **Test runners** — your project's primary test command(s). Examples: `pnpm test`, `npm test`, `cargo test`, `pytest`, `python -m pytest`, `go test`. Also any monorepo-scoped variants (`pnpm --filter @scope/pkg test`, `npm --workspace=pkg test`, etc.)
- **Lint/build** — `pnpm lint`, `pnpm build`, or your equivalents. Python stacks: `ruff check`, `ruff format`, `mypy`, `pyright`.
- **Git** — `git status*`, `git add *`, `git diff *`, `git log *`, `git stash *`, `git ls-files *` (the last is used by Step 2.4.6's File-List-vs-git gate — easy to forget). Also `git init` and `git config*` if the project is not yet a git repo.
- **File listing** — `Glob` tool (preferred) or `Bash(ls -la *)`
- **File content** — `Read` / `Grep` / `Edit` / `Write` tools — always allowed (not gated by settings)
- **Workspace filters** — if your project uses a workspace/monorepo tool with filter flags (`pnpm --filter`, `npm --workspace`, `yarn workspace`, `nx run`, etc.), confirm they're allowed. Python projects using `pip + venv` have no workspace tool — this is N/A.

### Python-stack pre-flight checklist

If the target project is Python-based (FastAPI / Django / Flask / pure-CLI), the envelope needs these shapes that aren't on the generic list above:

- **Python interpreter:** `python *`, `python -m *`, `python3 *` — needed for `python -m pytest`, `python -m venv`, `python -m pip`, and any module-form invocations the dev workflow uses
- **Package management:** `pip install *`, `pip install -r *`, `python -m pip *`, `python -m venv *` — needed for Story 1-1-style bootstrap and any dep-change story
- **Test discovery quirks:** `pytest <path>` (path arg is positional, no `--rootdir` needed for most cases); `pytest -k <expr>`; `pytest <path>::<class>::<test>` for specific tests. `Bash(pytest *)` covers all of these.
- **Async test runner:** `pytest-asyncio` runs under `pytest *` — no separate envelope entry needed
- **Type checker:** `mypy *` or `pyright *` — pick one based on the project's choice
- **Linter/formatter (ruff):** `ruff check *`, `ruff format *`, `ruff format --check *`
- **REPL / one-shot eval:** `python -c "*"` — use sparingly (one-shot scripts to verify imports, run migrations manually, etc.); inline `python -c` quoting often escapes broad rules, so consider writing a `.py` file under a temp dir and `python <path>` instead

### Docker / container-stack pre-flight checklist

If the target project ships a Docker Compose stack (typical for backend services with multiple processes — e.g., MailBot's 3-container stack of `mailbot-hermes` + `mailbot-api` + `ollama`):

- **Compose lifecycle:** `docker compose up *`, `docker compose down *`, `docker compose ps`, `docker compose logs *`, `docker compose restart *`
- **Container introspection:** `docker ps *`, `docker logs *`, `docker inspect *`
- **Container exec (for DB diagnostics, manual probes):** `docker exec * *`, `docker compose exec * *`
- **Health probing:** `curl localhost:*`, `curl 127.0.0.1:*`, `curl -s -o /dev/null *`
- **Image/build operations:** `docker build *`, `docker compose build *` — only needed if the story rebuilds an image, otherwise skip
- **Optional:** `docker volume *`, `docker network *` if the dev-env skill or any story touches them

### Compound-exec gotcha (common across monorepos)

Many projects have a rule like `Bash(pnpm --filter *)` but it does **not** automatically match `pnpm --filter X exec Y` where `Y` is itself a command chain. The pattern is recurring across monorepo tools — if the skill will invoke any of:

- `<pkg-mgr> --filter <pkg> exec <orm-cli> *` (migrations, schema generation, etc.)
- `<pkg-mgr> --filter <pkg> exec <test-runner> *` — package-scoped test runs
- `<pkg-mgr> --filter <pkg> exec <transpiler> *` — package-scoped script runs (tsx, ts-node, etc.)

…confirm the envelope contains explicit per-subcommand entries rather than a broad `<pkg-mgr> --filter * exec *` rule. The broad rule is often considered unsafe (it permits arbitrary shell execution via `exec bash -c …`), and projects tighten it to a 3-4-way split (`exec <orm-cli> *`, `exec <test-runner> *`, `exec <transpiler> *`, etc.).

Story-level hint: any story with a new ORM model, schema change, or migration will trigger your migration CLI — this compound-exec path.

### Dev-env-skill prerequisites

If the target project defines `<dev-env-skill>` (e.g., `/debug-vista-manager`, `/debug-dev-env`), Phase 3.0 will run it unconditionally. That skill typically uses commands like `docker ps`, `curl http://localhost:<port>`, or platform-specific shell launchers (PowerShell on Windows, bash on macOS/Linux). Pre-flight should verify those commands are allowed. Common additions:

- `Bash(docker ps *)` — container inspection
- `Bash(docker exec <container-name> *)` — DB diagnostics (psql, pg_isready, etc.)
- `Bash(curl -s -o /dev/null*)` or `Bash(curl *localhost*)` — health probes
- Platform-specific shell launchers if the dev-env skill uses one (e.g., `powershell.exe -ExecutionPolicy Bypass*` on Windows)

If missing, surface with the envelope gap at Step 0.0.

### Closing the pre-flight

If the skill will need a command shape not covered, surface the full list ONCE with a single permission request. Proceed only after the user either extends `<settings-file>` or confirms the substitutions. **Do not start the main loop until the envelope is confirmed clean.**

## Step 0.0b — Permission request log (optional)

If the project has a `PreToolUse` hook that logs commands missing the allow-list to a file (e.g., `<permission-log>`), the run benefits from a written feedback loop — every command that misses the allow-list lands in the log before the user sees the prompt. The agent doesn't have to log manually — but the agent does have to **observe the log feedback loop** at end-of-epic.

If no such hook is installed on the target project, this is N/A and Phase 3.3's final report simply says "no permission log configured."

**Log format (typical for an append-only hook):**

```
- `<exact command string>` — <YYYY-MM-DD HH:MM:SS> — <description> — outcome: pending
```

The hook would write `outcome: pending` because it runs before the prompt resolves. If you want outcome tracking (granted / denied / deferred), the agent can append a status edit after the prompt resolves — but it's optional and rarely worth the friction.

**Why the log exists:** it creates a feedback loop. After a run, review the log, extract recurring shapes, and extend `<settings-file>` so the next run is cleaner. Without the log, each run rediscovers the same gaps from memory and the envelope never tightens.

**Final-report reminder:** Phase 3's final report (Step 3.3) MUST cite the log if it was written to during the run — e.g. "7 permission prompts occurred, logged to `<permission-log>` — top 3 recurring shapes: <X>, <Y>, <Z>. Review to extend `<settings-file>` for future runs." If the log was NOT written to (clean run, zero prompts), state that explicitly: "Zero permission prompts during the run — envelope was sufficient." If no log is configured: "No permission log configured — count of mid-run prompts unknown."

## Setting up the hook (optional, recommended)

If your project doesn't yet have a permission-prompt hook, the skill can still run — the only loss is automated log capture. To add one, create a `.claude/hooks/log-permission-prompt.mjs` (or equivalent for your platform) that intercepts `PreToolUse` events, checks the command string against `<settings-file>`'s `permissions.allow` list, and appends a row to `<permission-log>` whenever the command would prompt. Register it in `<settings-file>` under the `hooks` section.

The exact hook implementation is project-specific (depends on path conventions, glob-matching semantics, log file location). See your project's hook documentation for the registration format.

## Why this file exists

Moving the envelope details out of SKILL.md:

- Keeps the orchestrator skill focused on phase-level flow
- Makes the envelope reference easy to find when the agent is debugging a prompt loop
- Provides a stable target-project porting surface (replace placeholder paths once here, not throughout SKILL.md)

Load this file when Step 0.0 fires, when a prompt happens mid-run, or when extending the allow-list after a run.