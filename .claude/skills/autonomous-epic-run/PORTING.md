# Porting `autonomous-epic-run` to MailBot

This skill is a BMAD epic orchestrator — it drives `bmad:bmm:workflows:create-story`, `bmad:bmm:workflows:dev-story`, and `bmad:bmm:workflows:code-review` in a loop until every story in the target epic is `done`. It also wires in defensive gates (pre-review self-audit, File-List-vs-git, middleware-real-bootstrap, verbose-row truncation) and end-of-epic manual verification.

This document is the MailBot-specific port checklist — what's ready, what's not, and what to do before the first run.

---

## First-run readiness — read before invoking

Before `/autonomous-epic-run` will work cleanly on this project, three things must be true. As of the port date, **none of them are** — this is a pre-code project: BMAD planning artifacts exist, but the source tree, the git repo, and the Claude permission envelope have not been bootstrapped yet.

### 1. Git must be initialized

The skill runs `git status --porcelain`, `git ls-files --error-unmatch`, and `git add <path>` at several gates (Step 2.3.5 §2, Step 2.4.6, Step 2.6). Today, `git status` returns `fatal: not a git repository` because no `.git/` exists at the repo root.

**Fix:** the very first acceptance criterion of Story 1-1 (`1-1-repo-scaffold-dependency-pinning`) is `git init`. Either run Story 1-1 manually before invoking this skill, OR accept that the first autonomous run's first story will be Story 1-1 itself — in which case dev-story handles `git init` and every subsequent gate works. Both are valid; the second is more aligned with the "autonomous" framing.

### 2. `.claude/settings.json` must exist with the right permission envelope

The skill assumes a permission envelope is in place before it starts. Today, `.claude/settings.json` does not exist — every Bash command will prompt.

**Fix:** before the first run, create `.claude/settings.json` covering at minimum:

- Git operations: `git status*`, `git add *`, `git log *`, `git diff *`, `git stash *`, `git ls-files *`, `git init`, `git config*`
- Python test/lint/type: `python -m pytest *`, `pytest *`, `ruff *`, `mypy *`, `pyright *`
- Docker: `docker compose *`, `docker ps`, `docker logs *`, `docker exec *`
- Python tooling: `pip install *`, `python -m venv *`, `python -m pip *`, `python *`
- Health-check probing: `curl localhost:*`, `curl 127.0.0.1:*`

Read [references/permission-envelope.md](references/permission-envelope.md) for the full envelope discussion, then walk Scenario 3 in [dry-run-scenarios.md](dry-run-scenarios.md) to enumerate the specific shapes the first epic will hit.

### 3. The BMAD framework is already installed and working

Verified at port time: `_bmad/` and `_bmad-output/` both exist, `_bmad-output/implementation-artifacts/sprint-status.yaml` is populated with 7 epics × 58 stories (all `backlog`), `_bmad-output/planning-artifacts/epics.md` is the canonical story source. Nothing to do here — this requirement is met.

---

## Hard requirements (the skill will not work without these)

### 1. BMAD core + bmm module installed — ✓ met

`_bmad/bmm/` exists and exposes the four workflows the skill drives: `create-story`, `dev-story`, `code-review`, and `retrospective` (the last is referenced but never invoked).

### 2. A sprint-status YAML file — ✓ met (at the default path)

`_bmad-output/implementation-artifacts/sprint-status.yaml` exists. No search-and-replace needed — the skill's default path is correct for this project.

### 3. A planning artifact for epic/story scoping — ✓ met (at the default path)

`_bmad-output/planning-artifacts/epics.md` exists with 7 fully-decomposed epics. No path override needed.

### 4. Per-story files under a known directory — ✓ met (structurally; files not yet created)

The skill writes `_bmad-output/implementation-artifacts/{story-id}.md` files. The directory exists; the individual story files don't yet (every story is `backlog`). `create-story` (Step 2.2) will write them on demand. No path override needed.

### 5. Claude Code settings with a permission envelope — ✗ not yet met

See "First-run readiness §2" above. This is the single biggest port-time gap. Create `.claude/settings.json` before the first run.

### 6. The `Agent` tool must accept the `model` parameter — ✓ met

The Claude Code environment in use supports `model` override on `Agent` invocations, so the dev-vs-review different-model invariant (Phase 1) holds.

---

## Soft requirements — adapted for MailBot

### Dev-environment verification skill — not configured

No `/debug-mailbot` or equivalent skill exists yet. Step 2.5 (per-story dev-env verification) and Step 3.0 (end-of-epic dev-env verification) will both be N/A for now and the skill notes that in `<flags-file>`.

**Candidate for later:** once the Docker stack from Story 1-2 is up, a `/debug-mailbot-stack` skill could be wired in that runs `docker compose up -d`, waits for health, and curls `localhost:8000/health` + the worker's `/v1/health`. If/when that skill ships, replace `<dev-env-skill>` occurrences in `SKILL.md` Steps 2.5, 3.0, and `references/permission-envelope.md` with its actual name.

### UX advisory persona subagent — N/A for this project

**MailBot has no graphical UI surface.** Discord is the user interface, and the Discord client is owned entirely by the `nousresearch/hermes-agent` Docker container — not anything this project ships. There are no `.tsx` / `.vue` / `.svelte` files in the planned architecture (verified against `architecture.md` §"Complete Project Directory Structure" — the layout is `mailbot_api/` Python only).

**Implication:** Step 3.1 (UX advisory) should be treated as N/A unconditionally. The Phase 0.4 UI-noun regex and Step 2.4.5 UI-scope gate are also mostly inapplicable — they'll match UI nouns in some ACs (e.g., "Discord digest layout", "draft reply card"), but there are no UI source files for the gate to validate against. **Expect noise** from those gates until SKILL.md is patched to neutralize them for this project (see "Follow-up SKILL.md edits" below).

### Permission-prompt logging hook — not configured

No `PreToolUse` hook is installed. Phase 3.3's final report will print "no permission log configured" instead of citing one. The run still works; envelope drift just has to be detected by watching for prompts manually.

---

## Path placeholders — MailBot's actual values

The skill files contain placeholder strings. Below is the project-specific mapping. **Note:** the skill files still contain the angle-bracket placeholders verbatim — they are documentation, not load-bearing. The agent reads this table to know what each placeholder means in this project; it does not need to find them replaced in the source.

| Placeholder            | MailBot's value                                              | Status                                                                                                  |
| ---------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| `<bmad-output>`        | `_bmad-output`                                               | ✓ matches default                                                                                       |
| `<sprint-status>`      | `_bmad-output/implementation-artifacts/sprint-status.yaml`   | ✓ exists, matches default                                                                               |
| `<epics-file>`         | `_bmad-output/planning-artifacts/epics.md`                   | ✓ exists, matches default                                                                               |
| `<story-file>`         | `_bmad-output/implementation-artifacts/{story-id}.md`        | Directory exists; files not yet created (all stories `backlog`)                                         |
| `<flags-file>`         | `_bmad-output/implementation-artifacts/epic-run-flags.md`    | Will be created by the skill on first run                                                               |
| `<permission-log>`     | _(none — no hook installed)_                                 | N/A for first runs                                                                                      |
| `<settings-file>`      | `.claude/settings.json`                                      | ✗ does not exist — see First-run readiness §2                                                           |
| `<dev-env-skill>`      | _(none yet)_                                                 | N/A — Step 2.5 + 3.0 skipped, noted in flags                                                            |
| `<frontend-src>`       | _(none — Discord is the UI, owned by Hermes container)_      | N/A — see "UX advisory" above                                                                           |
| `<backend-src>`        | `mailbot_api/` (Python 3.12)                                 | Planned per architecture.md §"Complete Project Directory Structure"; does not exist until Story 1-1 ships |
| `<orm-migrations-dir>` | `mailbot_api/db/migrations/` (raw `.sql` files; **no ORM**)  | Planned per architecture.md; created in Story 1-3. See note below                                       |
| `<lockfile>`           | `requirements.txt` (pinned pip + venv)                       | Created in Story 1-1                                                                                    |

**Note on `<orm-migrations-dir>`:** MailBot uses stdlib `sqlite3` with raw SQL migration files — Alembic and SQLAlchemy are explicitly deferred per architecture decision AR-D14-1. The posture-audit §5.2.1 check at [references/posture-audit.md](references/posture-audit.md) describes itself in terms of "ORM models" and "Prisma/TypeORM/SQLAlchemy"; for MailBot, interpret that check as "raw SQL migration file `NNN_*.sql` under `mailbot_api/db/migrations/` referenced by Dev Notes is actually present on disk." Same intent, different surface.

---

## Follow-up SKILL.md edits — shipped

The follow-up pass shipped on the same port date. All five items below were applied directly to the skill files, and the corresponding gates now have project-aware behavior keyed off this PORTING.md's path-placeholder table (specifically `<frontend-src>` being marked N/A).

1. **Step 2.4.5 — UI-Scope Pre-Flight Check.** Now short-circuits with `N/A — project has no graphical frontend` when `<frontend-src>` is N/A in PORTING.md. The silent-UI-scope-cut detection only fires for projects with a real frontend stack.

2. **Step 2.4.7 — Middleware-Real-Bootstrap Gate.** Stack adapters now enumerate FastAPI / NestJS / Express / Django / Flask patterns. For MailBot specifically, added a "MailBot-specific reframing" sub-section that retargets the gate around the Router contract: any new state-changing verb, `ask_router` call site, or SQLite write must have a Router-real, DB-real, or HTTP-real integration test (NOT mocking `ask_router`, `queries.py`, or the adapters above the boundary).

3. **Phase 0.4 — UI-gate check.** Now suppresses the UI-noun flag entirely when `<frontend-src>` is N/A, with the message `UI-gate N/A — project has no graphical frontend per PORTING.md; UI nouns in ACs refer to Discord-rendered text, owned by an external container`. Mockup verification is skipped because it cannot succeed.

4. **Step 3.1 — UX advisory.** Short-circuited at the top of the step when `<frontend-src>` is N/A. The skill writes the N/A line to `<flags-file>` and continues to Step 3.2. The advisory still spawns for projects with a graphical frontend.

5. **Permission envelope** (both the SKILL.md inline section and [references/permission-envelope.md](references/permission-envelope.md)). Test-runner examples now enumerate `pytest` / `python -m pytest` / `ruff` / `mypy` alongside the JS/TS / Rust / Go originals. A dedicated **"Python-stack pre-flight checklist"** and **"Docker / container-stack pre-flight checklist"** subsection were added to permission-envelope.md covering the shapes MailBot's first run will need (pytest, ruff, mypy, docker compose, docker exec, curl localhost).

Additionally, [references/posture-audit.md](references/posture-audit.md) gained Python-stack overlay notes at the three checks where the JS/TS framing degraded most:

- **§5.1 (Lockfile hygiene):** documents `requirements.txt` (pip + venv) and the `pip-compile` / `poetry` / `uv` lockfile names.
- **§5.7 (Module-mutable container):** adds a Python overlay listing the equivalent anti-patterns (module-level `dict`/`list`/`set`, `lru_cache` on unhashable args, global counters) and acceptable patterns (`Final[...]`, `MappingProxyType`, `frozenset`, frozen dataclasses). Flags `mailbot_api/router/router.py`, `budget.py`, `cache_warmer.py`, and `config.py` as the highest-risk module-singleton surface.
- **§5.10 (Producer-boundary contract):** maps `BigInt(...)` / `new Decimal(...)` to `int(value)` / `Decimal(value)` Python equivalents and Pydantic `@field_validator(mode="before")` as the defense-in-depth layer; maps Prisma `SAFE_USER_SELECT` to explicit `SELECT col1, col2, ...` lists in raw SQL (no `SELECT *`) for MailBot's stdlib-`sqlite3` stack.
- **§5.11.b (Test-to-code ratio):** adds a Python pytest test-file regex covering `tests/` directories, `test_*.py`, `*_test.py`, and `conftest.py`. Also includes `*.sql` under `mailbot_api/db/migrations/` in the docs bucket so pure-schema stories don't trip the gate.

**What was deliberately not touched in this pass:**

- [dry-run-scenarios.md](dry-run-scenarios.md) still uses `<frontend-src>` and `.tsx` paths as illustrative placeholders. The scenarios are skill-logic illustrations (not project-specific recipes), and rewriting them for Python adds bulk without changing what a reader learns from walking through them.
- The full body of [references/posture-audit.md](references/posture-audit.md) (§5.3 i18n lifecycle, §5.5 SSR screenshot perception, §5.8 ORM fixture parity, etc.) still reads as JS/TS-anchored. Each check that primarily targets a JS/TS-specific failure mode now has a Python overlay at the top OR is implicitly N/A for MailBot (no i18n keys, no graphical UI, no ORM). A full rewrite would be a larger project and would risk diluting the canonical illustrations.
- Pre-existing markdownlint warnings (missing fenced-code language tags, `<X>` placeholder angle brackets parsed as inline HTML, missing trailing newlines) are unchanged — they don't affect skill behavior and chasing them is out of scope for the port.

---

## Recommended first run

1. **Bootstrap the project bare minimum** — either manually run `git init` + create `.claude/settings.json` with the envelope from "First-run readiness §2," OR accept that Story 1-1 will do the `git init` itself and just create `.claude/settings.json` upfront (the envelope is still needed before any Bash command runs).
2. **Read [references/permission-envelope.md](references/permission-envelope.md)** and walk Scenario 3 in [dry-run-scenarios.md](dry-run-scenarios.md). Verify the envelope covers Python / Docker / git operations.
3. **Pick epic-1 as the first target.** It's the most foundational (8 stories: scaffold, Docker, SQLite, logging, Graph client, OAuth, sync worker, container entrypoint) and the most mechanical — exactly the profile the skill is best at. Don't pick epic-5 (Conversational Control) or epic-7 (Eval & Calibration) first; both have ambiguous ACs the autonomous loop will struggle with.
4. **Invoke the skill** (`/autonomous-epic-run` or "run epic 1 autonomously").
5. **Watch Phase 0.4** — the Blocker Scan report should print before the main loop starts. Expect noise from the UI-gate check on later epics; for epic-1 it should be clean (epic-1 is pure backend scaffolding).
6. **Watch for permission prompts.** Any mid-loop prompt means the envelope is short — record the prompted shape and extend `.claude/settings.json` before the next run.
7. **At Phase 3.5,** the manual-verification prompt will ask for browser verification. For MailBot, "browser verification" translates to: bring the Docker stack up, `curl localhost:8000/health`, and (for epic-1) confirm the OAuth flow completes against a real Microsoft Graph tenant. Post `PASS` / `PASS WITH FINDINGS` / `FAIL` based on that.
8. **Run the retrospective manually** in a separate session — the skill doesn't run it, and `#yolo` must not propagate to the retro.

---

## What this skill explicitly does NOT do

- **No retrospective.** That stays manual + interactive. The skill stops before it.
- **No commits.** Only `git add`. Review `git status` and commit when you want.
- **No epic planning.** If there's no epic to run, it exits. Use BMAD's planning workflows separately.
- **No model auto-fallback.** If the different-model requirement can't be met, it halts.
- **No mid-loop user-facing text.** Per the Loop Continuity Contract in SKILL.md Phase 2, the skill only addresses the user at Phase 0.4 (blockers), Phase 3.5 (manual verification), and Phase 3.3 (final report). All other output is tool calls or HALT messages.

---

## MailBot-specific feedback to track for future iterations

The "Follow-up SKILL.md edits" list above is the durable record of what doesn't fit. Beyond those, the items below are MailBot-specific quirks worth keeping in mind during runs — none are blockers, just things to expect:

- **Cost-discipline ACs:** many stories assert "every Router call records to `router_calls`" or "cost estimated upfront before > $5 spend." The Middleware-Real-Bootstrap Gate (Step 2.4.7) is the closest defensive gate, but it doesn't natively understand the Router contract. Watch for stories where the gate passes structurally but the Router-routing invariant is violated.
- **Sensitivity routing as a hard invariant:** FR-2.3 enforces that no Router call for any other task can happen on an `email_id` until `sensitivity_at IS NOT NULL`. This is a Router-internal hard rule, but it's the kind of thing that "tests pass on mocks" can silently break. Worth a project-specific gate later.
- **The agent never holds the Anthropic key (Rule F.1):** any story that touches `mailbot_api/router/models.py` or adapter wiring should be inspected for accidental key leakage into agent context. Not something the existing gates check.
- **No frontend means Layer 2 verification is shaped differently.** Phase 3.5's "open the app in a browser" doesn't apply — for MailBot, real-user verification means "send yourself a test email, watch the sync pick it up, ask in Discord, verify the response." The UAT story authoring should reflect this; the gate's prompt template should probably be reworded for Discord-as-UI projects in a future SKILL.md pass.
