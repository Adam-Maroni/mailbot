---
baseline_commit: a4fee9676da1fe7138aeab0f81596a6a55a7020b
---

# Story 6.6.7: MCP transport-security `allowed_hosts` fix — F7 closure

Status: done

## Story

As Adam,
I want Hermes's MCP client to successfully discover and register all 22 MailBot MCP tools at startup against the Docker-internal `mailbot-api:8000` hostname (no more `Client error '421 Misdirected Request'` in the Hermes logs),
So that Epic 6 Phase 3.5 CP-2 (`/spend month` round-trip) can walk end-to-end through Hermes to Discord, and the carry-forward Hermes-cron-skill bundles (Story 6-3 pull loop + Story 6-5 08:00 digest cron) have a live MCP transport to consume.

## Root cause (from Epic 6 Phase 3.5 CP-2 live discovery)

Story 6-6.6 closed F6 (the `/mcp` 307→404 redirect chain) with a two-part fix: server-side `streamable_http_path="/"` + client-side trailing-slash URL. Story 6-6.6's regression tests use FastAPI's `TestClient`, which sends `Host: testserver` by default.

When CP-2 walked live (2026-06-03, the first F6-unblocked Phase 3.5 walk), Hermes still failed to register MCP tools:

- **Hermes log:** `WARNING tools.mcp_tool: MCP server 'mailbot-api' failed initial connection after 3 attempts, giving up: unhandled errors in a TaskGroup (1 sub-exception)` → `Failed to connect to MCP server 'mailbot-api': Client error '421 Misdirected Request' for url 'http://mailbot-api:8000/mcp/'`
- **mailbot-api log:** `transport_security: Invalid Host header: mailbot-api:8000` (repeated 4× — once per Hermes retry)

FastMCP 1.27.2 ships `mcp.server.transport_security.TransportSecurityMiddleware`, a DNS-rebinding-protection layer that validates the `Host:` header against an `allowed_hosts` allow-list. The relevant default is:

```python
class TransportSecuritySettings(BaseModel):
    enable_dns_rebinding_protection: bool = Field(default=True, ...)
    allowed_hosts: list[str] = Field(default=[], ...)
```

When `enable_dns_rebinding_protection=True` and `allowed_hosts=[]`, every incoming Host header fails the allow-list check → middleware returns `Response("Invalid Host header", status_code=421)`. The MCP transport never sees the request.

Hermes reaches mailbot-api as `mailbot-api:8000` (Docker service hostname on the `mailbot-net` network). This hostname is not on the FastMCP default allow-list → 421 → Hermes gives up after 3 retries → zero MCP tools register.

Story 6-6.6's TestClient-based regression tests didn't surface this because:
1. TestClient defaults `Host: testserver`, not `mailbot-api:8000`.
2. With `allowed_hosts=[]` (empty), the middleware rejects everything — but Story 6-6.6's tests asserted on `status != 404` and `status != 307`, not on the F6-fixed positive case actually reaching the handler. The 421 from the security layer happens BEFORE routing, so structurally the F6 fix is still right; F7 is a wholly distinct layer (security middleware vs. mount-path routing).

## Fix

`build_mcp_server` constructs FastMCP with an explicit `transport_security=TransportSecuritySettings(...)` that allow-lists every hostname the server is reached at:

```python
from mcp.server.transport_security import TransportSecuritySettings
...
server = FastMCP(
    name="mailbot-api",
    streamable_http_path="/",        # F6 closure (Story 6-6.6)
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "mailbot-api:8000",      # Docker service hostname (Hermes reaches us here)
            "localhost:8000",        # operator-driven curl/debug
            "127.0.0.1:8000",        # same
            "testserver",            # FastAPI TestClient default
        ],
    ),
    ...
)
```

**Why keep DNS-rebinding protection enabled rather than disable it:**

DNS rebinding is a browser-side attack vector where an attacker tricks a browser into resolving `attacker.com` to `127.0.0.1` after the initial page load, then has JavaScript on the page POST to the localhost service. Our MCP server is reached only via the Docker-internal MCP transport (never a browser), so the protection is belt-and-suspenders. Disabling it (`enable_dns_rebinding_protection=False`) would be a strict subset of behavior; preserving FastMCP's default-safe posture is the lower-blast-radius option.

**Why allow-list `localhost:8000` + `127.0.0.1:8000`** despite the above:

Operator debugging via `curl http://localhost:8000/mcp/` shouldn't 421 just because the operator's terminal sets Host correctly. Same for the existing Story 6-1 `mailbot status` CLI's health-checks.

**Why allow-list `testserver`:**

FastAPI TestClient defaults to `Host: testserver`. Without this entry, every existing MCP-related integration test that uses TestClient (Story 5-2's MCP server tests, Story 6-6.6's mount-routing tests, Story 6-8's render_spend_chart tests) would suddenly 421 — preserving the old test baseline is non-negotiable.

## Acceptance Criteria

**Given** `mailbot_api/mcp_server.py:build_mcp_server` constructs FastMCP
**When** the construction is amended to include `transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=[...])` with the 4 required hostnames
**Then** a `POST /mcp/` request with `Host: mailbot-api:8000` reaches the FastMCP handler (no 421)
**And** a `POST /mcp/` request with `Host: evil-rebind-attacker.com` is still rejected with 421 (protection preserved)

**Given** the fix is applied
**When** existing Story 5-2 / 5-6 / 6-6.6 / 6-8 MCP integration tests run
**Then** every test passes unchanged (TestClient's default `Host: testserver` is in the allow-list)
**And** the 4 quality gates (ruff, mypy --strict, boundary checker, pytest) stay green

**Given** a new regression test guards against F7 re-introduction
**When** the test suite runs
**Then** `test_mcp_transport_security_allows_docker_hostname` confirms POST /mcp/ with `Host: mailbot-api:8000` does NOT return 421
**And** `test_mcp_transport_security_settings_include_docker_host` is a STRUCTURAL assertion (the FastMCP server's `settings.transport_security` is not None AND `"mailbot-api:8000" in settings.allowed_hosts`)

**Given** the F7 carry-forward is closed
**When** `_bmad-output/implementation-artifacts/epic-6-run-flags.md` is updated
**Then** F7 gets a **RESOLVED** preamble + dated walk note documenting the fix
**And** Epic 6 Phase 3.5 CP-2 walk can proceed

## Tasks / Subtasks

- [x] **Task 1: Patch `mailbot_api/mcp_server.py:build_mcp_server`** (AC: 1)
  - [x] Import `TransportSecuritySettings` from `mcp.server.transport_security`
  - [x] Add `transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=["mailbot-api:8000", "localhost:8000", "127.0.0.1:8000", "testserver"])` kwarg to the `FastMCP(...)` constructor
  - [x] Document the why in a multi-line comment immediately above the constructor: F7 closure + why we keep protection enabled + why the 4 hostnames

- [x] **Task 2: Write F7 regression tests in `tests/integration/test_mcp_mount_routing.py`** (AC: 2, 3)
  - [x] Add `test_mcp_transport_security_allows_docker_hostname` — boots mailbot_api.main:app via TestClient and POSTs `/mcp/` with `Host: mailbot-api:8000` header. Asserts status != 421 (the F7 failure mode). Documents the failure-mode in the assertion message.
  - [x] Add `test_mcp_transport_security_settings_include_docker_host` — STRUCTURAL: constructs the FastMCP server, asserts `server.settings.transport_security is not None`, asserts `"mailbot-api:8000" in settings.allowed_hosts`. Catches the refactor-drops-kwarg regression.
  - [x] Document the bug in a multi-paragraph module-level comment block (mirrors the F6 documentation style — same sibling-test contract)

- [x] **Task 3: Run 4 quality gates** (AC: 2)
  - [x] `ruff check` clean on touched files
  - [x] `mypy --strict mailbot_api/mcp_server.py` clean
  - [x] `python scripts/check_boundaries.py` exit 0
  - [x] `pytest -q` full suite: 976 + 2 skipped → 978 + 2 skipped (+2 net: the two F7 regression tests)

- [x] **Task 4: Live verification (F7 closed)** (AC: 1)
  - [x] `docker compose build mailbot-api` → new image with F7 fix baked in
  - [x] `docker compose up -d --no-deps mailbot-api` → recreate with new image
  - [x] `docker compose up -d --no-deps mailbot-hermes` (after `.env` `DISCORD_ALLOWED_USERS` populated to clear the parallel "No user allowlists configured" warning — separate finding, not part of F7 itself but blocking the same CP-2 walk)
  - [x] Verify Hermes MCP handshake succeeds: mailbot-api log shows `POST /mcp/ HTTP/1.1" 200 OK` (initialize), `GET /mcp/ HTTP/1.1" 200 OK` (SSE attach), `POST /mcp/ HTTP/1.1" 202 Accepted` (notifications/initialized), `POST /mcp/ HTTP/1.1" 200 OK` (tools/list). NO 421 responses.
  - [x] Adversarial verification: `docker exec mailbot-hermes curl -H "Host: evil-rebind-attacker.com" http://mailbot-api:8000/mcp/` STILL returns 421 — protection layer preserved.
  - [x] Positive verification: `docker exec mailbot-hermes curl -H "Host: mailbot-api:8000" -H "Content-Type: application/json" --data '<init-payload>' http://mailbot-api:8000/mcp/` returns 406 (the MCP protocol's "must accept text/event-stream" — proves request reached MCP handler past the security layer).

- [x] **Task 5: Update epic-6-run-flags.md** (AC: 5)
  - [x] Add new section `### F7 — MCP transport-security default-empty-allowlist mismatch — RESOLVED 2026-06-03 (Story 6-6.7)`
  - [x] Document the live walk verification: bad-Host 421, good-Host 406, Hermes MCP handshake 200/200/202/200
  - [x] Add per-story summary table row for 6-6.7
  - [x] Update Final loop disposition: 11 stories shipped in Epic 6 (was 10); add 6-6.7 to the list

- [x] **Task 6: Update sprint-status.yaml**
  - [x] Add `6-6.7-mcp-transport-security-allowed-hosts-f7-closure: done` entry under Epic 6
  - [x] Update last_updated to 2026-06-03

- [x] **Task 7: Update docs/setup-vps-runbook.md §3.5** (load-bearing operator note)
  - [x] Add a paragraph under §3.5 noting that the `mailbot-api:8000` allow-list entry is also load-bearing — a future operator who renames the Docker service in docker-compose.yml MUST update `allowed_hosts` in `mailbot_api/mcp_server.py` to match, or Hermes MCP discovery will start failing with 421 again.

## Dev Notes

### Why this is its own story (vs. amending 6-6.6)

Per Epic 4 retro action #6: explicit story for each discrete fix. F6 and F7 are wholly distinct middleware layers:

- F6 = mount-path routing chain (Story 6-6.6)
- F7 = transport-security middleware allow-list (this story)

Even though they appear at the "same MCP boundary" from a 30k-ft view, the code lives in different parts of FastMCP's source. Story 6-6.6's regression tests are correct AS-IS — F6 is not re-broken by F7's discovery; they're cousins, not parent-child. Folding the fix into 6-6.6 retroactively would muddy the audit trail.

### Schema-reality reframe pattern (Epic 6 retro action #1 candidate)

F7 surfaced because FastMCP 1.27.2 added DNS-rebinding protection between when Story 5-2's MCP server was first wired (and tested with TestClient's `testserver` default) and when CP-2 first tried to drive it live through the Docker network. This is the same shape as F6 (Story 6-0 walk surfaced an issue Story 5-2's local tests missed): live-stack discipline at every story boundary, not just at Phase 3.5 walks.

### Walk-record evidence convention

Live verification (in walk record under epic-6-run-flags.md § Story 6-6.7):
- mailbot-api log timestamps showing successful `200/200/202/200` MCP handshake from Hermes
- curl adversarial-test command + 421 response (protection preserved)
- curl positive-test command + 406 response (handler reached past security layer)
- All run from inside the Docker network using `docker exec mailbot-hermes curl ...` so Host header semantics match Hermes's actual behavior

### Project Structure Notes

- **MODIFIED**: `mailbot_api/mcp_server.py` — add TransportSecuritySettings import + kwarg
- **MODIFIED**: `tests/integration/test_mcp_mount_routing.py` — add 2 regression tests (F7-prefix doc block + 2 test functions)
- **MODIFIED**: `_bmad-output/implementation-artifacts/epic-6-run-flags.md` — F7 RESOLVED preamble + per-story row + final loop disposition update
- **MODIFIED**: `_bmad-output/implementation-artifacts/sprint-status.yaml` — add 6-6.7 done
- **MODIFIED**: `docs/setup-vps-runbook.md` §3.5 — add load-bearing operator note for allowed_hosts ↔ docker-compose service name coupling
- **NEW**: `_bmad-output/implementation-artifacts/6-6-7-mcp-transport-security-allowed-hosts-f7-closure.md` (this file)
- **NO Hermes-side files** — Hermes is the unmodified MCP client; F7 fix is purely server-side

### Testing standards summary

The 4 quality gates (ruff, mypy --strict, boundary checker, pytest) MUST be green AFTER the patch. Net pytest delta: +2 (two F7 regression tests in test_mcp_mount_routing.py). No pre-existing tests changed.

The structural test (`test_mcp_transport_security_settings_include_docker_host`) catches the refactor-drops-kwarg regression. The behavioral test (`test_mcp_transport_security_allows_docker_hostname`) catches the live failure mode. Both together prevent any single-point regression from re-opening F7.

### References

- [_bmad-output/implementation-artifacts/6-6-6-mcp-redirect-fix-f6-closure.md](./6-6-6-mcp-redirect-fix-f6-closure.md) — sibling F6 closure (same MCP boundary, different middleware layer)
- [_bmad-output/implementation-artifacts/epic-6-run-flags.md](./epic-6-run-flags.md) § "F6 — MCP mount-path / trailing-slash mismatch" — the F6 finding this F7 fix is cousin-of
- [mailbot_api/mcp_server.py](../../mailbot_api/mcp_server.py) — fixed file
- [tests/integration/test_mcp_mount_routing.py](../../tests/integration/test_mcp_mount_routing.py) — regression tests live here (sibling to F6 tests)
- [docs/setup-vps-runbook.md](../../docs/setup-vps-runbook.md) §3.5 — operator-facing load-bearing note

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Debug Log References

- **Live discovery (2026-06-03 ~20:09 UTC):** Epic 6 Phase 3.5 CP-2 walk attempt #1 — Hermes log `Client error '421 Misdirected Request' for url 'http://mailbot-api:8000/mcp/'`; mailbot-api log `transport_security: Invalid Host header: mailbot-api:8000` (4×).
- **FastMCP source inspection inside the live container:** `docker exec mailbot-api python -c "import mcp.server.transport_security; import inspect; print(inspect.getsource(mcp.server.transport_security))"` revealed the `TransportSecuritySettings` model with `allowed_hosts: list[str] = Field(default=[])` defaulting to empty list, and `enable_dns_rebinding_protection: bool = Field(default=True)` defaulting to enabled — which together cause the 421 on every Host header.
- **FastMCP constructor signature inspection:** `docker exec mailbot-api python -c "from mcp.server.fastmcp import FastMCP; import inspect; print(inspect.signature(FastMCP.__init__))"` confirmed `transport_security` is a top-level FastMCP kwarg accepting an `Optional[TransportSecuritySettings]`. No need to monkey-patch the middleware after construction.
- **Live closure verification (2026-06-03 ~20:29 UTC):** Hermes container restart → mailbot-api log `INFO: 172.19.0.3:48596 - "POST /mcp/ HTTP/1.1" 200 OK` + `GET /mcp/ 200 OK` + `POST /mcp/ 202 Accepted` + `POST /mcp/ 200 OK` (initialize → SSE-attach → notifications/initialized → tools/list). Zero 421s post-fix.

### Completion Notes List

- F7 was discovered DURING Epic 6 Phase 3.5 CP-2 walk attempt #1, not during planned story work. The autonomous-epic-run skill's contract ("walks discover findings; findings get filed as stories; the fix-then-walk loop absorbs them") played out exactly as designed.
- Found a parallel-but-distinct second finding during the same walk: Hermes container was running with empty `DISCORD_ALLOWED_USERS` (env var set in docker-compose.yml via `${DISCORD_ALLOWED_USERS:-}` but missing in `.env`). Hermes emitted `WARNING gateway.run: No user allowlists configured. All unauthorized users will be denied.` — meaning even after F7 closed, the CP-2 walk would have failed because the bot would refuse Adam's DMs. Fixed by appending `DISCORD_ALLOWED_USERS=<DISCORD_USER_ID-value>` to `.env`. **This is NOT part of F7 itself** — Story 4-0's credential capture missed it; flag as Story 4-0 amendment candidate for the Epic 6 retro (Adam-decided whether to amend retroactively or leave as documented gap).
- The two `# pragma: no cover` annotations on FastMCP's `_validate_host` confirm the upstream maintainers consider the validation path effectively branch-untestable from outside (which is part of why this surfaced at our live walk instead of in our test suite). Our two regression tests cover it from our test surface.
- Sequence note: F7 fix was applied → 4 gates green → mailbot-api rebuilt → Hermes restarted → live handshake verified ALL within ~30 minutes of F7's discovery during the CP-2 walk. Consistent with the autonomous-epic-run skill's "fix-then-walk loop absorbs inline findings" pattern (vs. carrying forward to a separate session).

### File List

- `mailbot_api/mcp_server.py` — added `TransportSecuritySettings` import + kwarg on FastMCP constructor + multi-line comment documenting the F7 closure rationale
- `tests/integration/test_mcp_mount_routing.py` — added F7-prefix doc block + 2 regression tests (`test_mcp_transport_security_allows_docker_hostname` + `test_mcp_transport_security_settings_include_docker_host`)
- `.env` — appended `DISCORD_ALLOWED_USERS=690538949310939136` (parallel finding, not F7-strict; documents the credential gap)
- `_bmad-output/implementation-artifacts/6-6-7-mcp-transport-security-allowed-hosts-f7-closure.md` — this story file
- `_bmad-output/implementation-artifacts/epic-6-run-flags.md` — append F7 RESOLVED section + per-story row + final loop disposition update
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — add 6-6.7 done
- `docs/setup-vps-runbook.md` §3.5 — operator-facing note on allowed_hosts ↔ docker-compose service hostname coupling

### Change Log

- 2026-06-03 — Story 6.6.7 shipped: F7 closed via `transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=[mailbot-api:8000, localhost:8000, 127.0.0.1:8000, testserver])` on FastMCP constructor in `build_mcp_server`. 2 regression tests added (1 structural, 1 e2e via TestClient). 4 gates green. Live verification: 4× `200 OK / 200 OK / 202 Accepted / 200 OK` MCP handshake from Hermes; zero 421s. Parallel `.env` `DISCORD_ALLOWED_USERS` gap fixed inline (separate finding; flagged as Story 4-0 amendment candidate for Epic 6 retro).
