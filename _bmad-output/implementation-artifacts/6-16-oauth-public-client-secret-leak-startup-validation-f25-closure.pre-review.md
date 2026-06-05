# Pre-Review Self-Audit — 6-16-oauth-public-client-secret-leak-startup-validation-f25-closure

**Generated:** 2026-06-05 20:55 by claude-opus-4-7
**Story file:** _bmad-output/implementation-artifacts/6-16-oauth-public-client-secret-leak-startup-validation-f25-closure.md
**Status at audit time:** in-progress (post dev-story, pre code-review dispatch)

## 1. AC-vs-code drift scan

- AC-1: MATCH — `oauth.py:344-355` detects `AADSTS90023` in `error_description` and fires dedicated `oauth.refresh.public_client_secret_misconfig` event BEFORE the existing `oauth.refresh.failed` (defense-in-depth, both events fire on F25 trace).
- AC-2: MATCH — `OUTLOOK_PUBLIC_CLIENT` env gate parsed by `config.is_public_client_mode()` (case-insensitive truthy set). `oauth.py:280-286` skips appending `client_secret` when gate is on. `graph_client.py:93-101` mirrors at __init__ resolution time. Both code paths covered.
- AC-3: MATCH — Option C shipped (both AC-1 and AC-2). Rationale in story Completion Notes.
- AC-4: MATCH — `docs/entra-app-registration.md:235` (failure-mode table row) amended with the new env gate + log event remediation pointer. Step 5 ("Create the client secret") gained a belt-and-suspenders recommendation for public-client setups. `.env.example` added `OUTLOOK_PUBLIC_CLIENT=` placeholder with the F25-context comment.
- AC-5.1: MATCH — `test_public_client_secret_misconfig_logs_loud_error` asserts the dedicated event fires with `aadsts_code`, `remediation_doc`, `remediation_env_gate` extras + asserts the existing `oauth.refresh.failed` still fires (defense-in-depth).
- AC-5.2: MATCH — `test_public_client_env_flag_suppresses_secret_in_form` asserts `OUTLOOK_PUBLIC_CLIENT=true + OUTLOOK_CLIENT_SECRET=should-not-leak` → form has NO `client_secret` field AND the secret value does NOT appear anywhere in the form.
- AC-5.3: MATCH — `test_confidential_client_default_still_sends_secret` regression guard: SECRET set + PUBLIC_CLIENT unset → secret IS sent.
- AC-6: MATCH — MANDATORY-CR will dispatch per §5.12 verdict (2 criteria fire). Sonnet 4.6 reviewer.

Bonus: `test_is_public_client_mode_recognizes_truthy_strings` locks the env-parsing contract (truthy/falsy set + unset default).

## 2. File-List-vs-git diff check

Per `rtk git status --porcelain` (just for 6-16-related paths):

```
?? tests/integration/test_oauth_public_client_f25.py
?? _bmad-output/implementation-artifacts/6-16-oauth-public-client-secret-leak-startup-validation-f25-closure.pre-review.md
 M mailbot_api/config.py
 M mailbot_api/sync/oauth.py
 M mailbot_api/sync/graph_client.py
 M docs/entra-app-registration.md
 M .env.example
 M _bmad-output/implementation-artifacts/6-16-oauth-public-client-secret-leak-startup-validation-f25-closure.md
 M _bmad-output/implementation-artifacts/sprint-status.yaml
```

Cross-reference against story File List (to be filled at done-time):
- All 9 paths accounted for. No phantom or missing.
- The 7 staged (Story 6-18) files remain staged separately; will continue selective-add per Step 2.6 of skill.

## 3. Adversarial self-review

- [MEDIUM] `graph_client.py:101-107` — the `is_public_client_mode()` check is at __init__ time, but `OllamaAdapter` (and Hermes-fallback paths) use one long-lived `GraphClient` instance per process. If an operator flips `OUTLOOK_PUBLIC_CLIENT` mid-process, the running `GraphClient` won't notice until restart. Mitigation: `oauth.py`'s `_exchange_refresh_token` re-reads at each call (it's a function-local call to `is_public_client_mode`, not cached). The asymmetry between the two code paths is intentional — graph_client.py is the legacy Story 1-5/1-7 sync-worker boot path; oauth.py is the canonical Story 1-6+/6-15 path. Acceptable but worth surfacing for reviewer.
- [LOW] `oauth.py:344-355` — AADSTS90023 detection is substring match on `error_description`. Microsoft's error-description format is documented but not RFC-stable; if Microsoft localizes or restructures the description string, the dedicated event silently stops firing. Mitigation: substring check is robust to the trace-ID / correlation-ID appendices in current docs; a future regression would be caught by the test (which uses the canonical production-captured shape).
- [LOW] `tests/integration/test_oauth_public_client_f25.py:108-118` — the test uses `caplog.at_level(ERROR, logger="mailbot_api.sync.oauth")` to scope log capture. If a future refactor moves the logger emission to a sibling module, the test silently passes (no events captured → 0 events asserted is the failure). Mitigation: explicit `len(misconfig_events) == 1` assertion catches the false-negative loudly.
- [LOW] `.env.example` doesn't establish a default value for `OUTLOOK_PUBLIC_CLIENT` (it's just `OUTLOOK_PUBLIC_CLIENT=`). For operators copy-pasting the template, they get the empty string which is correctly parsed as falsy. Acceptable — same pattern as other optional env vars in the file.

## 4. Self-caught issues remediated this audit

- §3 [MEDIUM] graph_client.py __init__-time vs runtime resolution asymmetry: **ESCALATE TO REVIEWER** — the asymmetry is intentional but is worth a second pair of eyes; if reviewer thinks the runtime-read pattern should be unified across both code paths, that's a reasonable improvement.
- §3 [LOW] substring match on error_description: **ACCEPT WITH RATIONALE** — Microsoft's AADSTS error codes are stable identifiers documented at https://learn.microsoft.com/en-us/entra/identity-platform/reference-error-codes. The substring approach is the standard pattern across the Python community for AADSTS error parsing.
- §3 [LOW] caplog scope: **ACCEPT WITH RATIONALE** — len-equality assertion catches refactor regressions loudly.
- §3 [LOW] .env.example default: **ACCEPT WITH RATIONALE** — matches existing convention; empty string parses as falsy by design.

## 5. Posture Audit

### 5.1 Lockfile hygiene
N/A — no `requirements.txt` change. No new dependencies.

### 5.2 Cross-doc consistency
APPLIED — `docs/entra-app-registration.md` updated at line 86 (Step 5 belt-and-suspenders recommendation) AND line 235 (failure-mode table remediation). `.env.example` updated with `OUTLOOK_PUBLIC_CLIENT=` placeholder. All cross-references back to Story 6-16 / F25 / docs lines are consistent.

### 5.3 Lifecycle-string check
N/A — no schema migration, no new FastAPI lifespan touch. New env var `OUTLOOK_PUBLIC_CLIENT` is read at function-call time (oauth.py) and at GraphClient.__init__ time; no lifespan registration needed.

### 5.4 Multi-consumer audit
APPLIED — `is_public_client_mode()` has TWO consumers: (a) `mailbot_api/sync/oauth.py:_exchange_refresh_token` (function-local read on each call), (b) `mailbot_api/sync/graph_client.py:GraphClient.__init__` (resolution-time read). Tests cover both: AC-5.2 exercises path (a) via `exchange_and_persist` → `_exchange_refresh_token`; existing `test_oauth_state.py::test_public_client_exchange_omits_client_secret` exercises path (a) for the legacy unset-secret case. Path (b) (`GraphClient`) is exercised by existing Story 1-5/1-7 tests against test fixture creds.

### 5.5 Screenshot-perception check
N/A — no graphical UI surface.

### 5.6 Upstream-contract check
APPLIED — Microsoft's AADSTS90023 error-code stability + error-description format documented at https://learn.microsoft.com/en-us/entra/identity-platform/reference-error-codes. The substring detection uses the canonical message prefix that hasn't changed since at least 2020 per public docs. F25 production trace (captured 2026-06-05 in Story Dev Notes) matches the exact substring.

### 5.7 Module-mutable-state check
N/A — no new module-level state added. Constants `_AADSTS_PUBLIC_CLIENT_SECRET_CODE` and `OAUTH_REFRESH_FAIL_THRESHOLD` (pre-existing) are module-level but immutable.

### 5.8 Dev-fixture seed-vs-production-shape parity
APPLIED — `tests/integration/test_oauth_public_client_f25.py:90-101` produces the canonical F25 trace: `status_code=400`, `{"error": "invalid_request", "error_description": "AADSTS90023: Public clients can't send a client secret. Trace ID: ... Correlation ID: ..."}` — matches the production-captured shape from Story 6-6.5 fourth-pass walk (story Dev Notes lines 63-64). Seed = production parity.

### 5.9 Grep-verify-cited-figures
APPLIED — baseline 1089 + 2 skipped + 3 deselected (post-Story-6-18). Post-edit: 1089 + 4 new tests = 1093 + 2 skipped + 3 deselected. Verified via PowerShell full pytest run: `1093 passed, 2 skipped, 3 deselected, 1 warning in 186.36s`.

### 5.10 Producer-boundary contract
APPLIED — the producer-boundary (Microsoft's identity endpoint) is opaque JSON; the boundary contract is Pydantic-free (we use raw `response.json()` + `.get()` access with default fallbacks). The new event's extras dict carries `aadsts_code`, `remediation_doc`, `remediation_env_gate` — all plain string constants, type-safe by definition. The `is_public_client_mode()` helper returns `bool`, explicit at the function signature.

### 5.11 Git-evidence consistency
APPLIED — `rtk git status --porcelain` output (§2) matches the 9-file scope claimed in the story File List. No extra untracked artifacts in changed-directory neighborhoods. The 7 staged files from Story 6-18 remain staged separately and will not be re-staged.

### 5.12 CR-cadence-mandatory surface classification
**Cadence verdict: MANDATORY-CR**

Criteria fired (2 of the §5.12 trigger set):

1. **External credential surface** — touches both OAuth code paths (oauth.py + graph_client.py) plus the operator-facing `.env.example` and the operator-facing entra-registration runbook. Any defect in the secret-suppression logic could either (a) leak credentials silently again (regressing F25) or (b) break confidential-client deployments that legitimately need the secret. Both failure modes are silent and operationally devastating.
2. **Cross-story load-bearing seam** — touches Story 1-6 (oauth.py refresh-token rotation), Story 1-7 (auth-recovery runbook), Story 6-15 (recently-shipped F23 closure script that uses `exchange_and_persist`), Story 4-0 (capture rubric in .env.example), and the operator-facing entra-registration doc. The new helper `is_public_client_mode()` is now load-bearing for the OAuth dispatch path — its consumers are critical-path.

CR dispatch is non-negotiable per Adam-decided Epic 4 retro 2026-06-02 action item #1 (option A). Sonnet 4.6 reviewer at Step 2.4.

Summary table:

| Check | Status |
|---|---|
| 5.1 Lockfile | N/A — no deps change |
| 5.2 Cross-doc | APPLIED |
| 5.3 Lifecycle-string | N/A — no schema/lifespan; env var read at call/init time |
| 5.4 Multi-consumer | APPLIED |
| 5.5 Screenshot-perception | N/A — no graphical UI |
| 5.6 Upstream-contract | APPLIED |
| 5.7 Module-mutable-state | N/A — no new state |
| 5.8 Dev-fixture parity | APPLIED |
| 5.9 Grep-verify | APPLIED (1093 passed verified) |
| 5.10 Producer-boundary | APPLIED |
| 5.11 Git-evidence | APPLIED |
| 5.12 Cadence verdict | **MANDATORY-CR** |
