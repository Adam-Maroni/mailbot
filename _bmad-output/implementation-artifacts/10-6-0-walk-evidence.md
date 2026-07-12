# Story 10.6.0 — Phase 3.5 Walk Evidence

**Date:** 2026-07-12
**Mode:** DELEGATED (Adam: "Run the manual verification yourself")
**Stack:** local Docker (mailbot-api + mailbot-hermes + mailbot-ollama), all healthy; mailbot-api + hermes restarted to load the fix (fresh start 10:44).
**Spend:** $0 (no router calls; direct Graph dispatch against the real mailbox).

## Fix-is-live confirmation

The fix runs in the container (bind-mounted source via `docker-compose.override.yml`; no image rebuild needed — unlike the 10.5.4 `scripts/` gap):

- `outlook_adapter.py` in-container: `on_auth_failure` param at :182, stored :192, 401 branch :380, hook await :387.
- `worker.py` in-container: hook wired at :315 `on_auth_failure=lambda: _refresh_access_token_cache(db_path, token_cache)`.
- Worker process (`python -m mailbot_api.worker`, PID 8) + API/uvicorn (PID 9) both up on the new code.

## AC-6 — induced-401 recovery against REAL Microsoft Graph (INDUCED, honesty-tagged)

**Method:** ran the fix's exact code path inside the container against real Graph. Constructed the REAL `OutlookGraphWriteAdapter` with (a) a deliberately **stale/garbage access token** seeded into the token cell, and (b) the REAL refresh hook (re-reads `oauth_state`, identical to what `worker.py` wires). Dispatched a real `mark_read` on a live inbox email (`AAkALgAA…MhL2oQAA`, "Votre code de sécurité"). Restored the email's original `isRead` state afterward.

**Honesty tag:** the 401 is INDUCED (garbage token seeded), NOT a natural stale-cache race. The refresh hook firing, the retry, and both real Graph status codes (401 then 200) are all REAL — against the real mailbox, real token endpoint, real `oauth_state`.

**Captured output:**

```
[setup] real access token acquired (len=1440)
[pre-state] isRead = False
[dispatch] mark_read with STALE token (induces real Graph 401)…
  [graph] PATCH → 401
  [hook] on_auth_failure fired (call #1) — token cell refreshed
  [graph] PATCH → 200
[result] ok=True error=None retry_count=0
[restore] isRead set back to False → status 200

=== VERDICT ===
  dispatch statuses seen: [401, 200]
  refresh hook calls:     1
  final result.ok:        True
  restore status:         200
  PASS
```

**Interpretation:** BEFORE the fix, the first real Graph 401 would have marked the action terminal `provider_4xx_401` (the AI-1 walk's id=40 failure — a proposed action that says "done" then silently fails). AFTER the fix, the 401 triggers exactly one on-demand token refresh and the retry succeeds against real Graph (200), so the action genuinely completes. This is Epic 10.6 done-flip clause 2 rendered at L3 for the drain path: the action truly applies to Microsoft Graph, not a persona "done" over a failed drain.

## Verdict per AC

| AC | Verdict | Evidence |
| --- | --- | --- |
| AC-1 (401 → refresh + retry once → applied) | **PASS (L3, real Graph)** | 401→refresh→200, `result.ok=True` |
| AC-2 (bounded: one refresh max) | **PASS** | `refresh hook calls: 1` (exactly once); unit + integration tests cover 401-then-401 terminal |
| AC-3 (hook refreshes from oauth_state, sync provider re-reads) | **PASS (L3)** | hook re-read `oauth_state`; retry carried the fresh token → 200 |
| AC-4 (non-401 4xx unchanged) | **PASS (code-L3)** | covered by `test_403_with_hook_does_not_refresh_or_retry` + unchanged 4xx branch; not re-exercised live (would require inducing a 403/404, out of walk scope) |
| AC-5 (MANDATORY-CR + gates) | **PASS** | sonnet-5 CR 5/5 Patches applied; 1889+3+3 suite; ruff/mypy/boundaries green |
| AC-6 (live drain → real Graph, mailbox changes) | **PASS (L3, drain path)** | real Graph 200 via the fix; mailbox restored as found |

## Scope-honesty note

The walk proves the fix at the **drain→adapter→real-Graph** boundary (the actual defect locus) via a direct real-adapter dispatch with an induced 401. It does NOT drive a full Discord-chat → propose → cool-off → drain round-trip, because that needs Adam interacting in Discord live. The recovery behavior being verified is entirely in the drain/adapter path (model-independent), so the direct dispatch is a faithful L3 exercise of the fix. A future full-chat round-trip (10.6.1 AC-6 / 10.6.2 send-follow-through) will additionally exercise the propose/persona front-end, now unblocked because the drain actually completes.

## Restoration / no-collateral

Post-walk vs pre-walk baseline: pause OFF (unchanged), degraded OFF (unchanged), `consecutive_refresh_failures=0` (unchanged — the induced client-side 401 did NOT count as an oauth failure), `rotation_count 344→345` (a normal fresh-token rotation from `get_access_token`, healthy), max `pending_actions` id=40 (no synthetic queue rows created), 2008 live emails (unchanged), all 3 containers healthy. Walk email's `isRead` restored to its original `False`. Container `/tmp/walk_*.py` is ephemeral (vanishes on restart); host `scratch/` script removed.
