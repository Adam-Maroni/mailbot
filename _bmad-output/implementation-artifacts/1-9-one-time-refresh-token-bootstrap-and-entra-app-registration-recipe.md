---
baseline_commit: d300a9650bf3540d9d8037bb7c48135fb05f024e
---

# Story 1.9: One-time refresh-token bootstrap + Entra app-registration recipe

Status: done

## Story

As Adam,
I want a one-time interactive bootstrap script that runs the OAuth 2.0 Authorization Code flow on a local dev machine with a browser and prints a refresh token for hand-copy to the VPS `.env`, plus a step-by-step recipe for registering the MailBot app in the Microsoft Entra admin center,
so that there is a documented, reproducible path from "fresh Outlook account" to "VPS `.env` contains a working `OUTLOOK_REFRESH_TOKEN`" — closing the bootstrap gap Stories 1-5/1-6 silently assumed away.

## Context (why this story exists)

The Azure-docs review after the Epic 1 retrospective surfaced four gaps:

1. Refresh tokens for delegated access are issued **only at the end of an Authorization Code flow** with a browser-based user-consent step ([auth-v2-user.md §Step 1](../../docs/external/learn-microsoft-azure/pages/graph/auth-v2-user.md)). No `client_credentials` grant produces one.
2. Story 1-5's `OUTLOOK_REFRESH_TOKEN` env var has **no story owning its initial population** — it is read by `seed_oauth_state_from_env` in [mailbot_api/sync/oauth.py:99](../../mailbot_api/sync/oauth.py#L99) but no story ever produced it.
3. The current [docs/auth-recovery.md](../../docs/auth-recovery.md) ends Step 1 with "The dev-box auth script lives in your local workspace (not committed)" — i.e., the script that does not yet exist.
4. Microsoft Entra app registration is a 6-step UI flow that Adam must do exactly once and document for any future re-creation (lost client, expired secret, new account).

This story closes both gaps: the operator recipe (Entra setup) and the automation (the bootstrap script). It is a **prerequisite for Phase 3.5 real-tenant verification** (CP-6: OAuth round-trip; CP-7: live sync ingest) and for any future production deploy.

## Acceptance Criteria

**AC-1.** `docs/entra-app-registration.md` exists and walks the reader through Entra app registration end-to-end:

- Sign in to <https://entra.microsoft.com/> with the same Microsoft account that owns the target Outlook mailbox.
- Navigate to **Identity → Applications → App registrations → New registration**.
- Set: Name = `MailBot`; Supported account types = **Personal Microsoft accounts only** (because the target mailbox is Adam's personal Outlook.com) — note that work/school accounts choose a different option and the recipe spells out both.
- Set redirect URI: Platform = **Public client/native (mobile & desktop)**, URI = `http://localhost:8765/callback`. (The bootstrap script binds 8765 locally; the VPS never receives a redirect.)
- Record: Application (client) ID, Directory (tenant) ID. For personal Microsoft accounts, the tenant value Adam will paste into `.env` is the literal string `consumers` (not the directory GUID — the GUID is for the Entra admin center only). For work/school: paste the directory GUID. For mixed-mode apps: `common`.
- Under **Certificates & secrets → New client secret**: create a secret named `MailBot bootstrap secret`, valid 24 months; copy the secret **value** immediately (Entra hides it after the page reloads).
- Under **API permissions → Add a permission → Microsoft Graph → Delegated permissions**: grant `Mail.Read`, `Mail.ReadWrite`, `Mail.Send`, `User.Read`, and `offline_access` (the last is what makes refresh tokens come back). Click **Grant admin consent** if the button is offered.
- Recipe ends with a checklist of values the operator should have in hand before running the bootstrap script: Client ID, Tenant value (`consumers` for personal, GUID for work/school, `common` for mixed-mode), Client Secret value, Redirect URI (`http://localhost:8765/callback`).
- Includes a **"First-time mint walkthrough"** section documenting the expected operator experience when running `scripts/mint_refresh_token.py`: the script prints the authorize URL, the default browser opens, the user signs in + consents, the browser redirects to `localhost:8765/callback`, the terminal prints the refresh token in the marker block.

**AC-2.** `scripts/mint_refresh_token.py` is a self-contained one-shot CLI that runs the Authorization Code flow locally:

- argparse CLI reads four required values, preferring `--flag` arguments and falling back to env vars: `OUTLOOK_CLIENT_ID`, `OUTLOOK_TENANT_ID` (the v2 tenant routing value: `consumers` / GUID / `common`), `OUTLOOK_CLIENT_SECRET`, `OUTLOOK_REDIRECT_URI` (defaults to `http://localhost:8765/callback`).
- Builds the `/authorize` URL per [auth-v2-user.md §Step 1](../../docs/external/learn-microsoft-azure/pages/graph/auth-v2-user.md) by `urllib.parse.urlencode`-ing these params:
  - `client_id={OUTLOOK_CLIENT_ID}`
  - `response_type=code`
  - `redirect_uri={OUTLOOK_REDIRECT_URI}`
  - `response_mode=query`
  - `scope=offline_access User.Read Mail.Read Mail.ReadWrite Mail.Send`
  - `state=<32-char hex from secrets.token_hex(16)>`
  - URL base: `https://login.microsoftonline.com/{OUTLOOK_TENANT_ID}/oauth2/v2.0/authorize`
- Spawns a `http.server.HTTPServer` bound to `127.0.0.1:8765`. Implements a single-request handler subclass (`BaseHTTPRequestHandler`) that records `path`, parses query params, returns a minimal HTML "you may close this tab" body to the browser, then signals the main thread to shut down the server.
- Opens the authorize URL in the default browser via `webbrowser.open(url)`. If `webbrowser.open` returns `False` (headless dev machine, WSL without browser), prints `Open this URL manually in any browser:\n{url}` to stderr and continues waiting.
- The local HTTP handler captures `?code=...&state=...` query params on the callback. Verifies `state` matches the freshly-minted value; if not, prints `FATAL: state mismatch — possible CSRF; aborting` to stderr and exits with status `3`.
- Exchanges the code for tokens via `POST {login.microsoftonline.com/{tenant}/oauth2/v2.0/token}` with `application/x-www-form-urlencoded` body containing: `grant_type=authorization_code`, `client_id`, `client_secret`, `code` (the captured one), `redirect_uri`, `scope=offline_access User.Read Mail.Read Mail.ReadWrite Mail.Send` (per [auth-v2-user.md §Step 2](../../docs/external/learn-microsoft-azure/pages/graph/auth-v2-user.md)). Uses `httpx.Client` synchronously with `timeout=30s`.
- On 2xx: prints to stdout the refresh token wrapped in a marker block (exact format below), plus the access token's `expires_in` and the granted `scope` string from the response, for the operator's sanity check before paste:

  ```text
  ===== REFRESH TOKEN (paste into VPS .env as OUTLOOK_REFRESH_TOKEN) =====
  <token here>
  ===== END =====
  expires_in: <int seconds>
  granted_scope: <scope string from token response>
  ```

  Exit status `0`.
- On any non-2xx from the token endpoint: parses the JSON error body (`{"error": "...", "error_description": "..."}`), pipes the body dict through `mailbot_api.observability.logging._sanitize` (re-exported as `sanitize` for callers — see Task 6) to redact any token-shaped strings, then prints `FATAL: token exchange failed status={status_code} body={sanitized_body!r}` to stderr. Exit status `2`.
- On transport errors (`httpx.RequestError`): prints `FATAL: transport error: {type(exc).__name__}` to stderr. Exit status `4`.
- On `KeyboardInterrupt` (Ctrl+C while waiting for callback): prints `aborted by operator` to stderr, cleanly closes the HTTP server, exits status `130`.
- The script is fully self-contained: only stdlib (`argparse`, `secrets`, `urllib.parse`, `http.server`, `webbrowser`, `sys`) + `httpx` (already in `requirements.txt` per Story 1-1) + `mailbot_api.observability.logging.sanitize`. **No `msal` import** (see Dev Notes for rationale).

**AC-3.** [docs/auth-recovery.md](../../docs/auth-recovery.md) is updated to replace the current Step 1 ("The dev-box auth script lives in your local workspace") with a pointer to Story 1-9's deliverables. The new Step 1 reads:

> ### Step 1 — Mint a new refresh token on your dev box
>
> On your local dev machine (the same one with a browser):
>
> ```bash
> python scripts/mint_refresh_token.py
> ```
>
> The script reads `OUTLOOK_CLIENT_ID`, `OUTLOOK_TENANT_ID`, `OUTLOOK_CLIENT_SECRET` from env (or your local `.env`), opens the consent flow in your browser, captures the callback on `localhost:8765`, exchanges the code for tokens, and prints the refresh token between two `===== ... =====` marker lines.
>
> For first-time setup (not just recovery), follow the prerequisites in `docs/entra-app-registration.md` first — you need a registered app and its client ID/secret before this script can run.
>
> Copy the printed refresh token (the value between the marker lines). Continue to Step 2.

All other steps (2-5) and the "Why not auto-fall-back-to-env?" + "Monitoring" sections are preserved as-is.

**AC-4.** `scripts/mint_refresh_token.py` imports the JSON sanitizer from `mailbot_api.observability.logging`. To make this a public surface (the symbol is currently named `_sanitize` with a leading underscore, marking it module-private), the dev refactors `mailbot_api/observability/logging.py` to also export it under the public name `sanitize` — a one-line addition `sanitize = _sanitize` after the function definition, or rename `_sanitize` → `sanitize` and add a `_sanitize = sanitize` backwards-compat alias if any existing call sites depend on the private name. Run `rg "_sanitize" mailbot_api tests` to verify call-site impact before choosing approach. The script then imports as `from mailbot_api.observability.logging import sanitize`. This ensures error-body printing redacts to the same standard as runtime logs.

**AC-5.** `.env.example` is updated. Replace:

```dotenv
OUTLOOK_REFRESH_TOKEN=
```

with:

```dotenv
# Obtained via scripts/mint_refresh_token.py — see docs/entra-app-registration.md
OUTLOOK_REFRESH_TOKEN=
```

The comment goes on the line directly above `OUTLOOK_REFRESH_TOKEN=`. All other existing comments and entries in `.env.example` are preserved.

**AC-6.** Integration tests at `tests/integration/test_mint_refresh_token.py` cover the **token-exchange path** of `mint_refresh_token.py` via `httpx.MockTransport`. The browser-spawn + local-HTTP-server-callback path is **not** integration-tested (it requires a real browser); manual verification is the "First-time mint walkthrough" section of `docs/entra-app-registration.md` (AC-1). The script must expose its token-exchange logic as an injectable function (e.g., `def exchange_code_for_tokens(*, code: str, client_id: str, tenant: str, client_secret: str, redirect_uri: str, transport: httpx.BaseTransport | None = None) -> dict[str, Any]:`) so tests can pass a `MockTransport` directly without invoking the browser path. Required test cases:

- `test_successful_exchange_returns_refresh_token`: `MockTransport` returns 200 with `{"access_token": "at-x", "refresh_token": "rt-x", "expires_in": 3600, "scope": "offline_access User.Read Mail.Read Mail.ReadWrite Mail.Send", "token_type": "Bearer"}`; assert the function returns the dict and that `refresh_token == "rt-x"`.
- `test_invalid_grant_raises_with_sanitized_body`: `MockTransport` returns 400 with `{"error": "invalid_grant", "error_description": "AADSTS70008: The provided authorization code or refresh token has expired"}`; assert function raises (custom `TokenExchangeError` or `RuntimeError` with the status code + sanitized body in the message); assert that a `Bearer rt-leaked` substring in the body would be redacted via the sanitizer (use an input crafted to include such a leak).
- `test_transport_error_propagates`: `MockTransport` handler raises `httpx.ConnectError("simulated")`; assert function raises (httpx.RequestError or wrapped equivalent) with no token-shaped string in the message.
- The CLI's state-mismatch branch (AC-2 exit 3) is tested by directly calling the state-comparison helper, **not** by spinning up an HTTP server in tests. Factor the comparison out as `def _verify_state(received: str, expected: str) -> None` so tests can call it directly and assert it raises on mismatch.

Pattern: follow [tests/integration/test_oauth_state.py](../../tests/integration/test_oauth_state.py) for `httpx.MockTransport` factory + monkeypatch-based env setup. No real network calls. No mock of the script's own internal logic — only the HTTP transport boundary is mocked.

**AC-7.** All gates pass: `ruff check .`, `mypy --strict mailbot_api/ scripts/`, `python scripts/check_boundaries.py`, `pytest -q`. The boundary checker passes without modification because `scripts/mint_refresh_token.py` lives in `scripts/` (already covered by `pyproject.toml` `[tool.ruff.lint.per-file-ignores]` for `T201`/`T203`, and the AST boundary scanner in `scripts/check_boundaries.py` only scans `mailbot_api/` per [scripts/check_boundaries.py:173-174](../../scripts/check_boundaries.py#L173-L174)). The script targets `login.microsoftonline.com`, NOT `graph.microsoft.com`, so Rule B (only `mailbot_api/sync/graph_client.py` may touch Graph) is preserved.

## Tasks / Subtasks

- [x] **Task 1** — Author `docs/entra-app-registration.md` end-to-end recipe with "First-time mint walkthrough" section (AC: #1)
- [x] **Task 2** — Refactor `mailbot_api/observability/logging.py` to publicly export the sanitizer (`sanitize` symbol); verify zero impact on existing call sites via `rg "_sanitize"` (AC: #4)
- [x] **Task 3** — Write `scripts/mint_refresh_token.py` with argparse CLI, `/authorize` URL builder, `http.server` callback handler, `webbrowser.open`, state verification, token exchange via httpx, sanitized error reporting, and exit code contract per AC-2 (AC: #2, #4)
- [x] **Task 4** — Update `docs/auth-recovery.md` Step 1 to point at the new script + Entra recipe (AC: #3)
- [x] **Task 5** — Update `.env.example` comment on `OUTLOOK_REFRESH_TOKEN` (AC: #5)
- [x] **Task 6** — Integration tests at `tests/integration/test_mint_refresh_token.py` covering the three token-exchange branches + the `_verify_state` helper (AC: #6)
- [x] **Task 7** — Phase 3.5 prep: document in the recipe (AC-1 "First-time mint walkthrough") that the operator should immediately run `python scripts/check_graph_auth.py` against a `.env` populated from the script output, to confirm the minted token actually authenticates against the real tenant (operator step, not automated). This closes the loop with Story 1-5's smoke script.
- [x] **Task 8** — All gates green: `ruff check .`, `mypy --strict mailbot_api/ scripts/`, `python scripts/check_boundaries.py`, `pytest -q` (AC: #7)

### Review Findings

_2026-06-01 — code-review (3 layers: Blind Hunter, Edge Case Hunter, Acceptance Auditor)_

- [x] [Review][Patch] **AC-3 verbatim deviation — reverted `M.C5...` hint** [docs/auth-recovery.md:57] — resolved from decision-needed: reverted to AC-3 verbatim by dropping the "typically starting with `M.C5...`" suffix from the closing sentence of Step 1.
- [x] [Review][Patch] **`do_GET` accepts any path → favicon/prefetch GETs short-circuit the callback** [scripts/mint_refresh_token.py:198-219] — empty-query GETs (favicon, prefetch, root visit) set `result.code=""`, fire `shutdown_event`, and close the server before the real callback arrives; Entra then redirects to a closed port. Gate `shutdown_event.set()` on `parsed.path == "/callback"` AND on presence of `code` or `error` in `params`; respond 404 otherwise without setting the event.
- [x] [Review][Patch] **`OUTLOOK_TENANT_ID` substituted into URL without validation** [scripts/mint_refresh_token.py:126,150] — `_AUTHORIZE_URL_TEMPLATE.format(tenant=tenant)` and `_TOKEN_URL_TEMPLATE.format(tenant=tenant)` interpolate raw operator input. A malformed value (full URL, path-traversal, `?`-injection) bypasses tenant routing. Validate `tenant` against `^(consumers|common|organizations|[0-9a-fA-F-]{36})$` before substitution; raise FATAL on mismatch.
- [x] [Review][Patch] **Callback-server bind host not constrained to loopback** [scripts/mint_refresh_token.py:331-335] — only literal `"localhost"` / `""` are rewritten to `127.0.0.1`. `0.0.0.0` (or any LAN IP) in `OUTLOOK_REDIRECT_URI` binds publicly during the ~10s window; first-to-arrive wins the single-use code. Whitelist binding to `127.0.0.1` / `::1` / `localhost` only; raise FATAL for any other host. Also normalize the `redirect_uri` sent to Entra to match the bound interface to avoid IPv6-resolver edge cases.
- [x] [Review][Patch] **`webbrowser.open` returns True on headless WSL → silent 10-min hang** [scripts/mint_refresh_token.py:350-358] — `GenericBrowser` paths return True even when no browser actually opened. Always print the authorize URL to stderr regardless of `opened`, OR detect WSL/headless (`os.environ.get("WSL_DISTRO_NAME")` / no `$DISPLAY`) and force the manual-URL fallback.
- [x] [Review][Patch] **`TimeoutError` from `_wait_for_callback` reported with misleading "could not bind" message** [scripts/mint_refresh_token.py:258-260,365-371] — `TimeoutError` subclasses `OSError` since 3.10 so the generic bind-error handler catches it; operator sees "could not bind callback server" when the real cause is "no callback received within 600s". Catch `TimeoutError` explicitly first with a distinct FATAL message; exit 4 still acceptable.
- [x] [Review][Patch] **`exchange_code_for_tokens` doesn't validate 2xx body is a `dict`** [scripts/mint_refresh_token.py:174-175] — annotation `dict[str, Any]` is a runtime no-op. A misbehaving proxy returning `200 OK` with `"hello"` or `[...]` JSON crashes `main()` with `AttributeError` on `body.get("refresh_token")` instead of a controlled FATAL. Add `if not isinstance(body, dict): raise TokenExchangeError(response.status_code, sanitize({"error": "unexpected_body_type", "body": body}))`.
- [x] [Review][Patch] **`test_transport_error_propagates_as_httpx_request_error` is tautological** [tests/integration/test_mint_refresh_token.py:255-269] — handler raises `httpx.ConnectError("simulated DNS failure")`; the secret `"super-secret-value"` was never injected into the exception in the first place. Either drop the secret-leak assertion (it tests nothing) or rewrite to invoke `main()` and capture stderr, verifying no client_secret appears in the operator-visible FATAL line.
- [x] [Review][Patch] **`docs/entra-app-registration.md` links AR-D9-1/AR-D9-2 to `architecture.md`, but those anchors live in `epics.md`** [docs/entra-app-registration.md:10] — grep shows `AR-D9-1`/`AR-D9-2` only in `_bmad-output/planning-artifacts/epics.md` lines 197-198; the architecture.md section "Sync ↔ Actions (D4 + D5 + D9)" at line 390 does not define them. Either link to `epics.md` or add the anchors to `architecture.md`.
- [x] [Review][Patch] **`test_unparseable_error_body_falls_back_to_text` lacks type-check on `sanitized_body`** [tests/integration/test_mint_refresh_token.py:252] — `"<html>" in exc_info.value.sanitized_body` would also pass if the impl ever wrapped the text in a dict (dict `in` matches keys). Add `assert isinstance(exc_info.value.sanitized_body, str)` before the substring check to lock in the str-fallback behavior.
- [x] [Review][Patch] **State-mismatch FATAL line interpolates `(exc)` — leak-fragile** [scripts/mint_refresh_token.py:397] — currently safe because `StateMismatchError` carries only a static message. But the test suite does not assert this; a future edit to embed state values would silently regress. Drop `({exc})` from the printed line; the static prefix is sufficient.
- [x] [Review][Patch] **KeyboardInterrupt branch around `exchange_code_for_tokens` is dead code** [scripts/mint_refresh_token.py:421-423] — KI during a sync `httpx.post(...)` inside a context manager raises `httpx.RequestError` (cleanup wraps), not `KeyboardInterrupt`. The spec's exit-130 path is "Ctrl+C while waiting for callback" — the live handler at line 362 already covers that. Remove the duplicate branch to avoid misleading future readers.
- [x] [Review][Patch] **Recipe "Common failure modes" table missing WSL/headless symptom** [docs/entra-app-registration.md:215-223] — pairs with the `webbrowser.open` issue above. Add a row: "Script appears to hang indefinitely / no browser opened" → "WSL or headless dev box" → "Open the authorize URL printed to stderr manually in any browser".
- [x] [Review][Defer] **Consent-flow `?error=...` callback maps to exit 2** [scripts/mint_refresh_token.py:373-385] — deferred, pre-existing: the spec's exit-code table doesn't enumerate this path; exit 2 is a defensible bucket. Could be tightened to a dedicated exit code in a future polish pass.

Counts: 1 decision-needed (resolved → patched), 12 patches (all applied), 1 deferred, 14 dismissed as noise. All 4 gates re-verified after patches: ruff clean, mypy --strict clean (25 source files), boundary checker exit 0, 93 tests pass.

## Developer Context

### Files this story creates

| Path | Why |
| --- | --- |
| `scripts/mint_refresh_token.py` | The one-shot CLI itself (Task 3) |
| `docs/entra-app-registration.md` | Operator recipe (Task 1) |
| `tests/integration/test_mint_refresh_token.py` | Token-exchange MockTransport tests (Task 6) |

### Files this story modifies (READ THESE BEFORE EDITING)

| Path | Current state | What this story changes | What must be preserved |
| --- | --- | --- | --- |
| [mailbot_api/observability/logging.py](../../mailbot_api/observability/logging.py) | Defines `_sanitize` (line 31, module-private) used by `JsonFormatter.format` (line 95) | Add public `sanitize` alias so `scripts/` can import it (Task 2) | The recursive sanitizer behavior (Bearer/sk-/URL-query/secret-paths). The `JsonFormatter.format` call site must continue to work unchanged. `configure_logging` is idempotent — keep it. |
| [docs/auth-recovery.md](../../docs/auth-recovery.md) | Step 1 ends at "The dev-box auth script lives in your local workspace (not committed)" — i.e., refers to a script that does not exist | Replace Step 1 body with a pointer to `scripts/mint_refresh_token.py` + `docs/entra-app-registration.md` (Task 4) | Symptoms, Cause, Steps 2–5, "Why not auto-fall-back-to-env?", Monitoring sections. The `oauth_state` deletion + `docker compose restart mailbot-api` flow (Steps 3–4) is the recovery-time re-seed mechanism; do not alter its semantics. |
| [.env.example](../../.env.example) | `OUTLOOK_REFRESH_TOKEN=` on line 11, no inline comment | Add a `# Obtained via scripts/mint_refresh_token.py — see docs/entra-app-registration.md` line directly above (Task 5) | Every other line. The grouping (Discord / Anthropic / Outlook / SQLite / Ollama / Router) and existing comments. |

### Architecture compliance (no negotiation)

- **AR-D9-1 (architecture.md §"Sync ↔ Actions (D4 + D5 + D9)" line 417):** "Bootstrap refresh token is minted via a one-time interactive browser flow on a dev machine — see Story 1-9's `scripts/mint_refresh_token.py` and `docs/entra-app-registration.md`. The VPS itself is never a redirect URI target. The minted token is hand-copied into the VPS `.env`." **This story implements the architecture's explicit pin.** The redirect URI `http://localhost:8765/callback` is dev-box-only by design.
- **AR-D9-2 (architecture.md line 419):** "`.env` becomes a bootstrap seed — used once to populate the row, then `oauth_state` is runtime source of truth." The script's output is paste material for `.env`. The runtime then uses it once via `seed_oauth_state_from_env` ([mailbot_api/sync/oauth.py:89](../../mailbot_api/sync/oauth.py#L89)) and never again. Do not invent any "auto-paste to oauth_state" shortcut — the hand-copy step is the deliberate human-in-the-loop.
- **Rule B preserved (architecture.md line 1054):** `scripts/mint_refresh_token.py` targets `login.microsoftonline.com` (identity endpoint), NOT `graph.microsoft.com`. The boundary checker enforces Rule B only for the latter and only inside `mailbot_api/`. No carve-out is needed.
- **Rule F preserved:** the script reads env vars via `argparse` defaults + `os.environ.get(...)` fallback. The checker bans `os.environ` outside `mailbot_api/config.py`, but only scans `mailbot_api/` (see [scripts/check_boundaries.py:173](../../scripts/check_boundaries.py#L173)) — scripts/ is outside the scan scope. **Acceptable.** The script can use `os.environ.get` directly because it runs once on a dev box, not in the production container.
- **Naming conventions** (architecture.md §"Naming Patterns"): module/file/function snake_case, table names plural snake_case (n/a here — no DB writes), timestamps as `TEXT` UTC ISO-8601 with `Z` suffix (n/a here — no DB writes).
- **Logging conventions** (architecture.md §"AR-PAT-3"): if the script logs at all, it goes via `logging.getLogger(__name__)` + `configure_logging()` for the JSON-on-stdout shape. **But** the marker-block stdout output (AC-2) is **human-readable**, not JSON — it goes through plain `print(...)` to stdout. This is a deliberate departure justified by the script being a one-shot human-facing tool, not a long-running container process. Sanitized errors still use `print(..., file=sys.stderr)` (no `logger.error`) because the operator is reading them directly.

### Library / framework versions (pinned in requirements.txt from Story 1-1)

- Python 3.12+ (`pyproject.toml:5`)
- `httpx` (no pinned version yet — uses whatever Story 1-1 pulled in; verify with `pip show httpx`). Synchronous `httpx.Client(timeout=httpx.Timeout(30.0))` matches the pattern in [mailbot_api/sync/oauth.py:143](../../mailbot_api/sync/oauth.py#L143).
- stdlib `argparse`, `secrets`, `urllib.parse`, `http.server`, `webbrowser`, `sys`, `json` — all available, no install needed.
- **Do NOT add** `msal` to `requirements.txt`. See Dev Notes "Why we don't use MSAL here".

### Reuse: token-exchange pattern is already mostly in the codebase

The token-exchange call in this script is the `grant_type=authorization_code` sibling of the existing `grant_type=refresh_token` call at [mailbot_api/sync/oauth.py:111-222](../../mailbot_api/sync/oauth.py#L111-L222). Steal the structural pattern (form-encoded POST, response.json() parsing, 4xx-with-sanitized-error-code) but rewrite for the auth-code grant type. **Do not import from `oauth.py`** — that module is async + depends on `db.connection`. The script is sync + has no DB. Duplicating ~30 lines of POST-and-parse is the right call.

The `_TOKEN_URL_TEMPLATE` constant `"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"` is in [mailbot_api/sync/graph_client.py:25](../../mailbot_api/sync/graph_client.py#L25). The script may either re-define it locally (cleaner — no cross-module import for a one-shot script) or import it. **Re-define locally** to keep the script standalone and importable for tests without pulling in the async stack.

### Exit-code contract (mandatory)

| Exit | Meaning |
| --- | --- |
| `0` | Success: refresh token printed in marker block |
| `1` | (reserved — do not use, to keep semantic distance from a bare `sys.exit(1)`) |
| `2` | Token endpoint returned 4xx/5xx — sanitized body printed to stderr |
| `3` | State mismatch on callback — possible CSRF |
| `4` | Transport error (network, DNS, timeout) before/during token exchange |
| `130` | KeyboardInterrupt — operator aborted |

### Testing patterns (reuse from prior stories)

- Async test pattern: `pytest-asyncio` with `asyncio_mode = "auto"` ([pyproject.toml:62](../../pyproject.toml#L62)). **But** this story's script is synchronous, so use **synchronous** test functions — no `async def` needed. The token-exchange function under test is itself sync.
- `httpx.MockTransport` factory pattern: see [tests/integration/test_oauth_state.py:41-61](../../tests/integration/test_oauth_state.py#L41-L61) — a `_token_transport(...)` closure builds a `MockTransport(handler)` and returns it for injection. Mirror this pattern.
- Env-var monkeypatching: `monkeypatch.setenv(k, v)` per-test (also in `test_oauth_state.py`).
- Test directory: `tests/integration/` (consistent with Story 1-6 / 1-7 / 1-8). No new test framework or fixtures needed.

### Previous-story intelligence (Epic 1 learnings to apply)

- **Story 1-3 lesson — transaction-semantics misfires concentrate in transaction-boundary code.** This story has no DB writes, so the analogous risk is **HTTP-state-machine misfires**: confirm the script handles all branches (success, 4xx with parseable body, 4xx with unparseable body, 5xx, transport error, KeyboardInterrupt). Test cases enumerated in AC-6 cover the first four; the last is operator-driven and untestable in CI.
- **Story 1-4 lesson — boundary checker catches real violations** (caught embedded SQL in story 1-6's oauth.py). Run the boundary checker before declaring the story done; expect zero violations because the script lives outside `mailbot_api/`.
- **Story 1-6 lesson — error-body sanitization matters.** The refresh-token rotation handler already parses the error body and logs `error_code` (see [mailbot_api/sync/oauth.py:160-172](../../mailbot_api/sync/oauth.py#L160-L172)). This story's script needs the same discipline — never let a raw error body leak to stderr; always sanitize first. AC-4 is the load-bearing requirement.
- **Story 1-8 lesson — Phase 3.5 deferral is acceptable for real-tenant calls.** This story's only "real network" verification is `python scripts/check_graph_auth.py` post-mint, which is explicitly a Phase 3.5 / operator step (AC-7 / Task 7), not a CI test. The integration tests use `MockTransport` only.
- **Recent-commits intelligence:** the last 5 commits ([d300a96](../../) docs-planning, [921f10f](../../) epic-1 feat) reflect the freshly-completed Epic 1 surface. Story 1-9 (this) and 1-10 (next) are the post-retro additions; no concurrent work conflicts with this story's files.
- **Migration numbering:** N/A — this story adds no migrations. The 001/002/004 contiguous-but-skipping-003 pattern from Stories 1-3/1-6/1-8 (per architecture's "apply-order keys, not version-controlled identifiers") is preserved.

### Code-style guardrails

- `from __future__ import annotations` at the top of every new `.py` file (consistent with Stories 1-3 through 1-8).
- No `print()` in `mailbot_api/` — but `scripts/` allows it via `T201`/`T203` per-file-ignore ([pyproject.toml:38](../../pyproject.toml#L38)). The marker-block output is `print(...)` to stdout; errors are `print(..., file=sys.stderr)`. No `# noqa: T201` needed inside `scripts/`.
- `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")` if any timestamp is emitted (DTZ rule per Story 1-4). The script likely doesn't need timestamps, but if logging is added, use this format.
- mypy --strict: every function fully typed. `def main() -> int:`, `def exchange_code_for_tokens(*, code: str, ...) -> dict[str, Any]:`, etc. No `Any` returns from helper functions — only the raw decoded JSON dict from the token endpoint typed as `dict[str, Any]`.

### Why this is its own story (not folded into 1-5 or 1-6)

Story 1-5 ships the *runtime* path that consumes an already-extant refresh token. Story 1-6 ships *persistence* of rotated tokens. Neither owns the bootstrap. This is also the only story in Epic 1 with an explicit operator-facing UI surface (the browser flow + Entra UI) — it has a fundamentally different test posture (manual walkthrough + mock-only automated tests). Splitting it out also lets Story 1-10 (sync correctness patches) proceed in parallel without depending on this story's manual-verification artefacts.

### Why `tenant=consumers` for personal Outlook

[auth-v2-user.md parameters table](../../docs/external/learn-microsoft-azure/pages/graph/auth-v2-user.md) documents the allowed `{tenant}` values: `common` (both), `organizations` (work/school only), `consumers` (Microsoft accounts only), or a tenant identifier (GUID for a specific work/school directory). Adam's target mailbox is a personal `@outlook.com` / `@hotmail.fr` account → `consumers`. If MailBot is later pointed at a work/school account, the tenant flips to a GUID. The recipe documents all three cases so future-Adam doesn't have to re-derive it.

### Why a public-client redirect URI on `http://localhost:8765/callback`

Public-client native/desktop redirect URIs are the documented pattern for headless-but-bootstrapped flows. The localhost loopback is special-cased in [OAuth 2.0 RFC 8252](https://datatracker.ietf.org/doc/html/rfc8252) — Microsoft Entra accepts it without TLS. Port 8765 is high enough to avoid `/etc/services` conflicts and low enough to be a plain `bind()` (no privileged-port concern). Binding to `127.0.0.1` specifically (not `0.0.0.0`) ensures no LAN exposure during the seconds the server is alive.

### Why the script bypasses the boundary checker for HTTP-to-Graph

`scripts/check_boundaries.py` enforces Rule B (only `mailbot_api/sync/graph_client.py` may call `graph.microsoft.com`). But `scripts/mint_refresh_token.py` targets `login.microsoftonline.com` (token endpoint), NOT `graph.microsoft.com` — Rule B doesn't apply. Per Story 1-4, the checker scans only `mailbot_api/` ([scripts/check_boundaries.py:173-174](../../scripts/check_boundaries.py#L173-L174)), so no carve-out is needed. The boundary checker will pass cleanly.

### Why we don't use MSAL here

MSAL would be the canonical choice for token acquisition (per [auth-v2-user.md §"Use the Microsoft Authentication Library (MSAL)"](../../docs/external/learn-microsoft-azure/pages/graph/auth-v2-user.md)). We deliberately avoid it for this one-shot script because:

1. The script runs on the dev machine, not in production — failure mode is "Adam reruns it", not "the VPS sync stalls".
2. Adding `msal` to `requirements.txt` for one-time use pollutes the runtime image. The architecture decision (post-Epic-1 docs review) was to retain hand-rolled `httpx` for the runtime client; carrying that through to the bootstrap script keeps the dependency surface minimal.
3. The protocol is simple enough to express in ~80–120 lines of `httpx` + `http.server`. The complexity MSAL provides (token caching, silent refresh, broker integration) is irrelevant for a one-shot mint.

### Threat model (operator-facing)

- **CSRF on callback:** mitigated by the `state` parameter check. The handler MUST verify `state` equals the freshly-minted value before exchanging the code. Test case in AC-6 covers this.
- **Refresh-token leakage to stdout:** the script prints the refresh token to stdout by design — this is the operator hand-copy channel. The operator is responsible for not running this script in a tmux session that scrolls into a shared screen, etc. Document this caveat in `docs/entra-app-registration.md` ("Best practice: run from a local terminal, not over SSH; clear scrollback after copy").
- **Refresh-token leakage to stderr:** the script writes error bodies to stderr, sanitized via `mailbot_api.observability.logging.sanitize`. AC-4 + AC-6 enforce this. Never let a raw error body reach stderr.
- **Replay attack on `code`:** the code is exchanged exactly once inside the script's process; even if intercepted, it would already be redeemed. Acceptable.
- **TLS:** the loopback redirect URI is HTTP (no TLS), which is explicitly allowed by Entra for `localhost` per RFC 8252. The token-exchange POST is HTTPS via `httpx` defaults.

### References

- [docs/external/learn-microsoft-azure/pages/graph/auth-v2-user.md](../../docs/external/learn-microsoft-azure/pages/graph/auth-v2-user.md) — Authorization Code flow protocol details (§Step 1 authorize URL, §Step 2 token exchange, parameters table)
- [docs/external/learn-microsoft-azure/pages/graph/auth/auth-concepts.md](../../docs/external/learn-microsoft-azure/pages/graph/auth/auth-concepts.md) — delegated vs app-only access
- [docs/auth-recovery.md](../../docs/auth-recovery.md) — existing recovery flow (to be updated by this story)
- [mailbot_api/sync/oauth.py](../../mailbot_api/sync/oauth.py) — runtime refresh-token rotation (sibling pattern to reuse)
- [mailbot_api/sync/graph_client.py:25](../../mailbot_api/sync/graph_client.py#L25) — `_TOKEN_URL_TEMPLATE` constant
- [mailbot_api/observability/logging.py:31](../../mailbot_api/observability/logging.py#L31) — `_sanitize` (to be aliased as `sanitize`)
- [scripts/check_graph_auth.py](../../scripts/check_graph_auth.py) — Story 1-5 smoke script invoked in Phase 3.5 verification (Task 7)
- [scripts/check_boundaries.py:173-174](../../scripts/check_boundaries.py#L173-L174) — confirms `scripts/` is outside boundary-scan scope
- [pyproject.toml:38-40](../../pyproject.toml#L38-L40) — `scripts/**/*.py` ruff per-file-ignores
- [tests/integration/test_oauth_state.py](../../tests/integration/test_oauth_state.py) — `httpx.MockTransport` factory pattern to mirror
- architecture.md §"Sync ↔ Actions (D4 + D5 + D9)" lines 415-421 — D9 bootstrap pin
- architecture.md §"Architectural Boundaries" line 1054 — Rule B

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context)

### Debug Log References

- All 4 gates green on first full-suite run after autofix: ruff `All checks passed`, mypy `25 source files no issues`, boundary checker exit 0, pytest `93 passed`. The 9 new tests are all in `tests/integration/test_mint_refresh_token.py`.
- One ruff autofix needed: I'd split `import httpx` and `from mailbot_api.observability.logging import sanitize` into two import groups with a blank line between — ruff `I` (isort) wants them in the same third-party group. Auto-fixed.
- mypy --strict was clean on the first try; the script's full type surface (incl. the `http.server.BaseHTTPRequestHandler` subclass with `# noqa: N802` for the API-mandated `do_GET` casing) typed cleanly.
- No code-review subagent invoked — consistent with the gate-coverage-only cadence formalized in the Epic 1 retrospective action item #1. Story 1-9 introduces no new boundary surface (the script is outside `mailbot_api/`) and no new external dependency surface (uses existing `httpx` + stdlib), so it falls inside the gate-coverage default.

### Completion Notes List

- **Task 2 — sanitizer publication:** renamed `_sanitize` → `sanitize` in `mailbot_api/observability/logging.py` and updated the 3 internal call sites (function body recursion x2 + `JsonFormatter.format` consumer). No external imports of the underscore name existed (verified via `rg "_sanitize" mailbot_api tests` — zero hits outside the module). Cleaner than the dual-name alias approach hypothesised in AC-4. The 27 prior sanitizer-related tests in `tests/unit/observability/test_logging_sanitizer.py` + `tests/unit/sync/test_graph_client.py` continued to pass without modification because they always imported `JsonFormatter` / `configure_logging`, not the lower-level helper.
- **Task 3 — `scripts/mint_refresh_token.py`:** ~310 lines. Three layers:
  1. **Pure helpers** (`build_authorize_url`, `_verify_state`, `exchange_code_for_tokens`) — synchronous, no IO except the one HTTP POST in `exchange_code_for_tokens` (and that's injectable via `transport=`). Unit-testable without browser or network.
  2. **Local callback server** (`_CallbackResult`, `_make_handler_class`, `_wait_for_callback`) — `http.server.HTTPServer` bound to `127.0.0.1:8765` with a 10-min watchdog timer and 1-second poll cadence so a `shutdown_event.set()` from the handler exits cleanly. Silences default access-log noise via `log_message` override.
  3. **CLI entrypoint** (`_parse_args`, `_validate_args`, `main`) — argparse with `OUTLOOK_*` env-var defaults, exit-code contract enforcement (0/2/3/4/130), `webbrowser.open` with manual-URL fallback for headless dev boxes.
  - State verification uses `secrets.compare_digest` for constant-time comparison — defense in depth on top of the 32-hex-char state token.
  - The error-body fallback handles both JSON and non-JSON 4xx/5xx bodies (e.g., an HTML 500 from a load balancer); both paths go through `sanitize()` before reaching `TokenExchangeError.sanitized_body`.
  - **No `msal` dependency added** — kept the runtime image surface minimal per the post-Epic-1 architecture decision.
- **Task 6 — integration tests:** 9 tests in `tests/integration/test_mint_refresh_token.py`. Loaded the script via `importlib.util.spec_from_file_location` (the script is in `scripts/`, not a package) and cached in `sys.modules`. Coverage:
  - `build_authorize_url` produces all 6 required query params; scope contains all 5 delegated permissions.
  - `_verify_state` returns silently on match, raises `StateMismatchError` on mismatch.
  - `exchange_code_for_tokens` happy path returns the full token response dict.
  - **Form-encoded POST body shape test** — confirms `grant_type=authorization_code`, all 6 form fields, `application/x-www-form-urlencoded` Content-Type, and the exact `login.microsoftonline.com/{tenant}/oauth2/v2.0/token` URL.
  - `invalid_grant` 400 → `TokenExchangeError` with status code + dict body preserved.
  - **Sanitization regression test** — error body containing `Bearer ABCdef.ghi-jkl_mno12345` gets the Bearer string redacted to `[REDACTED_BEARER]` before reaching `sanitized_body`. This is the load-bearing privacy test.
  - Unparseable error body (HTML 500) falls through to `response.text` capture, still sanitized.
  - `httpx.ConnectError` propagates unchanged as `httpx.RequestError`; the secret value never appears in the exception message.
- **Task 1 — `docs/entra-app-registration.md`:** 9-step recipe (sign in → register → redirect URI → record IDs → secret → permissions → pre-flight checklist → first-time mint walkthrough → `check_graph_auth.py` verification). Documents all three tenant routing values (`consumers` / GUID / `common`) and a "Common failure modes" table covering the four most likely operator errors. The Phase 3.5 verification step (Step 9 in the doc) satisfies Task 7 — no separate file needed.
- **Task 4 — `docs/auth-recovery.md` Step 1:** replaced the previous "lives in your local workspace (not committed)" paragraph with a concrete pointer to `scripts/mint_refresh_token.py` and `docs/entra-app-registration.md`. Steps 2-5, "Why not auto-fall-back-to-env?", and Monitoring sections preserved verbatim.
- **Task 5 — `.env.example`:** added `# Obtained via scripts/mint_refresh_token.py — see docs/entra-app-registration.md` comment directly above `OUTLOOK_REFRESH_TOKEN=`. No other entries touched.
- **Boundary preservation:** verified that `scripts/check_boundaries.py` only scans `mailbot_api/` (line 173-174), so the script's `os.environ.get` calls in `_parse_args` defaults are outside scope — Rule F preserved. The script targets `login.microsoftonline.com`, never `graph.microsoft.com`, so Rule B preserved. No carve-outs needed.
- **Phase 3.5 real-tenant verification deferred:** consistent with Epic 1 stories 1-5/1-6/1-7/1-8, the actual browser-based mint + `check_graph_auth.py` round-trip against the real tenant is an operator step (documented in `docs/entra-app-registration.md` Steps 8-9), not an automated test. CP-6 / CP-7 from the Epic 1 retrospective are now unblocked from a code perspective — Adam can execute them when ready to deploy.

### File List

**New:**

- `scripts/mint_refresh_token.py` — the bootstrap CLI (Task 3)
- `docs/entra-app-registration.md` — operator recipe (Task 1, includes Task 7's Phase 3.5 step)
- `tests/integration/test_mint_refresh_token.py` — 9 integration tests (Task 6)

**Modified:**

- `mailbot_api/observability/logging.py` — `_sanitize` renamed to `sanitize` + docstring expanded (Task 2)
- `docs/auth-recovery.md` — Step 1 rewritten (Task 4)
- `.env.example` — `OUTLOOK_REFRESH_TOKEN` comment added (Task 5)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — 1-9 status transitions (workflow-managed)

### Change Log

- 2026-06-01 — Story 1-9 implemented: refresh-token bootstrap CLI + Entra recipe + auth-recovery + .env.example updates. 9 new integration tests; sanitizer published as a public symbol. All gates green (93 tests pass, ruff clean, mypy --strict clean, boundary checker clean).
