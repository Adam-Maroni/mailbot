# MailBot

Personal email triage agent. Sits between Microsoft Outlook and Discord on a single VPS, fetches the inbox via Microsoft Graph, classifies and prioritizes each email through a cost-disciplined LLM Router (local Qwen 3B + Claude Haiku 4.5 + Claude Opus 4.7), and answers conversational queries from Adam over Discord — "show me unread from today", "draft a reply to that", "/pause" — within a per-message authorization model that never sends or deletes without consent.

This repo is the implementation. The full design lives in `_bmad-output/planning-artifacts/architecture.md` and `_bmad-output/planning-artifacts/prds/`.

## Local setup

Requires Python 3.12 and Docker Desktop (for stories beyond 1-1).

```bash
git clone <this repo>
cd mailbot

# Create a Python 3.12 venv. On Windows with the py launcher:
py -3.12 -m venv .venv
# Or with explicit python:
# python -m venv .venv   (only if `python` is 3.12.x)

# Activate the venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Windows cmd:
.venv\Scripts\activate.bat
# POSIX:
source .venv/bin/activate

pip install -r requirements.txt
pytest -q                          # should report 0 collected tests on the bare scaffold
ruff check .                       # should report 0 issues
mypy --strict mailbot_api/         # should report 0 issues
```

## Architecture overview

- **3-container Docker stack** on the `mailbot-net` network: `mailbot-hermes` (Hermes runtime, Discord adapter, cron, memory), `mailbot-api` (Router + verbs + MCP server + sync worker; holds the Anthropic API key), `ollama` (Qwen 3B + embedding model).
- **Five hard code boundaries** (enforced by ruff lint rules added in story 1-4): Router / sync / db / config / audit isolation.
- **Pinned runtime versions**: FastAPI 0.136.1, Anthropic 0.105.2, Ollama 0.6.2, MCP 1.27.2, Pydantic v2.
- **stdlib `sqlite3`** with WAL + raw SQL migrations under `mailbot_api/db/migrations/` (no ORM by design — AR-D14-1).

See `_bmad-output/planning-artifacts/architecture.md` for the full design and `_bmad-output/planning-artifacts/epics.md` for the implementation plan.

## Project layout

```
mailbot_api/                Python package — the F1..F8 implementation
  db/                         SQL boundary (raw SQL only inside queries.py)
  router/                     LLM adapter boundary (only place anthropic/ollama imports live)
  sync/                       Microsoft Graph boundary
  verbs/                      Agent-facing data window (MCP tools)
  ingest/ actions/ ...        See architecture §2 for full breakdown

router/                     Top-level runtime config (policy.yaml lives here — added in story 2-2)
docker/                     Dockerfile + entrypoint (story 1-2)
hermes-config/              Hermes runtime config (epic 5)
evals/ benchmark/           Eval corpus + benchmark runner (epic 7)
scripts/                    Operator CLIs + VPS deploy scripts (epics 1, 6)
tests/                      Pytest tests (unit / integration / fixtures)
docs/                       Project docs (auth-recovery.md, etc.)
```

## Make targets

- `make test` — run pytest
- `make lint` — run ruff + mypy
- `make local` — start the local dev stack (story 1-2+)
- `make build` / `make deploy` / `make logs` / `make status` / `make backup` — VPS operations (epic 6)

## Status

This is the **scaffold** (story 1-1). No business logic yet. Subsequent epics layer in the Docker stack (1-2), SQLite + migrations (1-3), code boundaries + logging (1-4), Microsoft Graph client + OAuth (1-5..1-6), delta sync (1-7), and the two-process container entrypoint (1-8).
