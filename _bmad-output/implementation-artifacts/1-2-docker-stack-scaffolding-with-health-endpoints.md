# Story 1.2: Docker stack scaffolding with health endpoints

Status: done

## Story

As Adam,
I want `docker compose up` to bring up the three-container stack (`mailbot-hermes`, `mailbot-api`, `ollama`) with named volumes and a working `/health` endpoint on `mailbot-api`,
so that I can verify the deployment topology end-to-end before any business logic is written.

## Acceptance Criteria

**AC-1.** `docker-compose.yml` declares 3 services (`mailbot-hermes`, `mailbot-api`, `ollama`) on a `mailbot-net` network with 4 named volumes (`mailbot_db`, `mailbot_ollama`, `mailbot_hermes_data`, `mailbot_logs`); `docker/Dockerfile.mailbot-api` builds the `mailbot-api` image with multi-stage layout; `docker/entrypoint.sh` backgrounds the worker placeholder + foregrounds uvicorn; `docker-compose.override.yml` bind-mounts source for dev hot-reload and exposes ports 8000 + 11434.

**AC-2.** `mailbot-api` exposes `GET /health` returning HTTP 200 with `{"ok": true}` and `GET /v1/health` with the same shape.

**AC-3.** `curl http://localhost:8000/health` returns HTTP 200 `{"ok": true}` within 5s of stack startup; `curl http://localhost:11434/api/tags` returns HTTP 200.

**AC-4.** Named volumes survive `docker compose down && docker compose up`.

## Tasks / Subtasks

- [ ] **Task 1** — `mailbot_api/main.py` minimal FastAPI app with `/health` + `/v1/health` (AC: #2)
- [ ] **Task 2** — `mailbot_api/worker.py` placeholder (event-loop heartbeat; AC: full body in story 1-8)
- [ ] **Task 3** — `docker/Dockerfile.mailbot-api` multi-stage (builder installs deps, runtime is slim) (AC: #1)
- [ ] **Task 4** — `docker/entrypoint.sh` background worker + foreground uvicorn (AC: #1)
- [ ] **Task 5** — `docker-compose.yml` 3 services + `mailbot-net` + 4 named volumes (AC: #1)
- [ ] **Task 6** — `docker-compose.override.yml` source bind-mounts + dev ports (AC: #1)
- [ ] **Task 7** — Unit test for `/health` + `/v1/health` using FastAPI's TestClient (AC: #2)
- [ ] **Task 8** — Verify `pytest -q` + `ruff check .` + `mypy --strict mailbot_api/` all green

## Dev Notes

- AC-3 and AC-4 require Docker Desktop running locally. If Docker is NOT available on the dev host, document this in Completion Notes as a deferral to Phase 3.5 manual verification — do NOT block the story. The `mailbot_api/main.py` + tests are the primary AC-2 deliverables and are testable without Docker via `httpx.AsyncClient(app=app)` / `TestClient(app)`.
- `mailbot_api/main.py` is also a **Middleware-Real-Bootstrap** trigger surface — it ships an HTTP endpoint per Step 2.4.7. Per the MailBot reframing in that gate, the verification path is "HTTP-real integration test for mailbot_api/main.py endpoints — TestClient(app) exercising /health, /v1/health with the real app." That test lands in Task 7.
- The Dockerfile is multi-stage to keep the runtime image lean. Architecture §2 line 807 specifies `Dockerfile.mailbot-api  # multi-stage; ENTRYPOINT runs worker + uvicorn`.
- `mailbot-hermes` is the upstream image `nousresearch/hermes-agent:latest` — no Dockerfile here; just a `docker-compose.yml` reference. Per PORTING.md "Discord is the UI, owned entirely by the `nousresearch/hermes-agent` Docker container" — we don't customize the Hermes container in this story.
- `ollama` is `ollama/ollama:latest` — model pulling is deferred to a later story (story 2-3 handles Qwen 3B installation). Story 1-2 just needs the container to start and `curl localhost:11434/api/tags` to return HTTP 200 (empty `{models: []}` array is acceptable).

### References

- [Source: architecture.md§"Complete Project Directory Structure"] — `docker/Dockerfile.mailbot-api`, `docker/entrypoint.sh`, `docker-compose.yml`, `docker-compose.override.yml`
- [Source: architecture.md§"Two processes inside the mailbot-api container (D7)"] — uvicorn + worker topology
- [Source: architecture.md§"3-container Docker Compose stack on mailbot-net"] — service list + volume list
- [Source: epics.md§"Story 1.2"] — canonical ACs

### Code Review Findings (Sonnet 4.6)

- [x] **[HIGH] CR-1 — entrypoint.sh does NOT fail the container when the worker dies.** The `trap` only forwards SIGTERM/INT from tini to the worker; there is no monitoring loop. If `python -m mailbot_api.worker` exits on its own, uvicorn continues running and the container stays alive — directly violating the Story 1-8 AC ("kill worker → container exits"). A `wait $WORKER_PID; exit $?` (or equivalent poll loop) after the exec-less uvicorn launch, or switching to a process supervisor, is required. As written, `exec uvicorn …` replaces the shell, so the trap never fires and `$WORKER_PID` is orphaned the moment exec runs.

- [x] **[HIGH] CR-2 — docker-compose.override.yml `command` override bypasses entrypoint.sh entirely.** Setting `command: ["uvicorn", …]` replaces the Dockerfile `CMD` but tini still calls the new command directly, skipping `entrypoint.sh`. The worker process is therefore never started in dev mode. Any dev-mode test of worker behavior is silently absent. The override should instead mount source and set `RELOAD=1` env var that entrypoint.sh reads, or use `--reload` inside entrypoint.sh when the env var is present.

- [x] **[HIGH] CR-3 — No non-root USER in Dockerfile runtime stage.** The container runs as root (uid 0). This is a container security baseline violation. A non-root user (`RUN adduser --system --no-create-home mailbot && USER mailbot`) must be added to the runtime stage before `EXPOSE`. Also ensure volume mount paths are writable by that user.

- [x] **[MEDIUM] CR-4 — `python:3.12-slim` is unpinned in both builder and runtime stages.** `3.12-slim` resolves to the current patch release and will silently drift between builds. Both stages should pin to a specific patch digest (e.g., `python:3.12.10-slim-bookworm@sha256:…`) or at minimum `python:3.12.10-slim` to get reproducible builds. Same concern applies to both `FROM` lines.

- [ ] **[MEDIUM] CR-5 `[partial: ollama pinned to 0.6.2; hermes-agent:latest deferred per architecture AR-DEPLOY-1 explicit `latest` pin — flagged for retro]`** Original CR-5 — `ollama/ollama:latest` and `nousresearch/hermes-agent:latest` are floating `latest` tags.** `latest` can break silently on `docker compose pull`. Both should be pinned to a concrete version tag (e.g., `ollama/ollama:0.4.7`, `nousresearch/hermes-agent:1.0.0`) or a digest. Story notes explicitly accept an empty `/api/tags` response, so a fixed version is safe.

- [x] **[MEDIUM] CR-6 — `depends_on: ollama` has no `condition: service_healthy` and ollama has no healthcheck.** `mailbot-api` will start immediately after ollama's container is created, potentially before ollama is ready to serve `/api/tags`. At minimum add a healthcheck to the ollama service (`test: ["CMD", "curl", "-f", "http://localhost:11434/api/tags"]`) and update the depends_on to `condition: service_healthy`. Currently AC-3's `curl localhost:11434/api/tags` may race.

- [x] **[MEDIUM] CR-7 — `mailbot-hermes` has no healthcheck; `mailbot-api` has no `condition: service_healthy` on its dependency.** `mailbot-hermes` depends on `mailbot-api` starting, but only with default start-order semantics. If `mailbot-api` is still initialising when Hermes tries to reach `http://mailbot-api:8000/v1`, it will fail at startup. Add `condition: service_healthy` to the hermes `depends_on` block so it waits for `mailbot-api`'s defined healthcheck to pass.

- [x] **[LOW] CR-8 — `@pytest.mark.asyncio` decorators are redundant and misleading under `asyncio_mode = "auto"`.** `pyproject.toml` sets `asyncio_mode = "auto"`, which marks all async tests automatically. The explicit decorators are harmless but imply the mode is `strict`, confusing future contributors. Remove the decorators for clarity, or add a comment explaining they are kept for explicitness.

- [x] **[LOW] CR-9 — `entrypoint.sh` `exec uvicorn …` makes the preceding `trap` a no-op.** After `exec`, the shell process is replaced by uvicorn; the bash `trap` is no longer in scope. Tini's SIGTERM goes directly to uvicorn (PID now held by tini), so the trap line (`trap "kill -TERM $WORKER_PID …"`) never executes. The comment "tini watches the process tree" is correct but the trap code is dead. It should either be removed (and the comment clarified) or the script should be restructured so uvicorn runs in the background and the shell stays alive to catch signals.

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Debug Log References

### Completion Notes List

- Implemented all 4 ACs structurally; AC-3 + AC-4 require Docker Desktop to verify against a live `docker compose up`, deferred to Phase 3.5 manual verification (Docker not running on this host).
- 7 new files: `mailbot_api/main.py` (FastAPI with /health + /v1/health), `mailbot_api/worker.py` (placeholder asyncio loop, real body in 1-8), `docker/Dockerfile.mailbot-api` (multi-stage, non-root `mailbot` user, tini PID 1), `docker/entrypoint.sh` (background worker + background uvicorn + `wait -n` propagation per Story 1-8 AC), `docker-compose.yml` (3 services, mailbot-net, 4 named volumes, healthchecks on mailbot-api + ollama), `docker-compose.override.yml` (dev source bind-mounts + UVICORN_RELOAD env-var-driven reload), `tests/integration/test_health_endpoints.py` (3 tests via ASGITransport(app=app) — Middleware-Real-Bootstrap MailBot reframing).
- Code review (Sonnet 4.6) raised 9 issues; **8 applied** (CR-1 entrypoint.sh restructured to `wait -n` for fail-fast on worker death; CR-2 override.yml uses UVICORN_RELOAD env var instead of `command:` to preserve entrypoint.sh execution; CR-3 added non-root `mailbot` user; CR-4 pinned `python:3.12.10-slim-bookworm`; CR-6 added ollama healthcheck + `condition: service_healthy`; CR-7 added hermes `condition: service_healthy` for mailbot-api dependency; CR-8 removed redundant @pytest.mark.asyncio decorators; CR-9 entrypoint no-`exec` restructure resolved same root cause as CR-1).
- **1 partial:** CR-5 — ollama pinned to `ollama/ollama:0.6.2` matching the Python SDK pin per AR-BOOT-2; `nousresearch/hermes-agent:latest` retained per architecture AR-DEPLOY-1 explicit "latest" pin (architecture-amendment required to change; flagged in epic-run-flags.md).
- Gates green post-fix: `pytest -q` → 3 passed in 0.38s; `ruff check .` → All checks passed; `mypy --strict mailbot_api/` → Success: no issues in 13 source files.

### File List

- `mailbot_api/main.py`
- `mailbot_api/worker.py`
- `docker/Dockerfile.mailbot-api`
- `docker/entrypoint.sh`
- `docker-compose.yml`
- `docker-compose.override.yml`
- `tests/integration/test_health_endpoints.py`
- `_bmad-output/implementation-artifacts/1-2-docker-stack-scaffolding-with-health-endpoints.md` (this story file)
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
