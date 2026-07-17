# Pre-Review Self-Audit — 10-7-3

**Generated:** 2026-07-16 by claude-opus-4-8[1m]
**Story file:** `_bmad-output/implementation-artifacts/10-7-3-allowlist-trim-toward-mailbot-api-only.md`
**Status at audit time:** review (post dev-story, pre code-review)

## 1. AC-vs-code drift scan

- **AC-1 (messaging dropped): MATCH** — `- messaging` removed from `platform_toolsets.discord` in `hermes-config/config.yaml`; asserted by `test_hermes_config_discord_allowlist_excludes_messaging_send_peer`.
- **AC-2 (email verbs stay): MATCH** — allow-list still `[mailbot-api, cronjob, memory, clarify]`; `mailbot-api` (26 verbs) present; `test_hermes_config_discord_allowlist_keeps_mailbot_verbs` passes with `messaging` removed from `_REQUIRED_DISCORD_TOOLSETS`.
- **AC-3 (MCP-server invariant): MATCH** — `messaging` is a Hermes built-in toolset, NOT an MCP server; the only MCP server `mailbot-api` stays named; `test_hermes_config_every_mcp_server_is_on_the_discord_allowlist` passes.
- **AC-4 (noise stays excluded): MATCH** — `_NOISE_TOOLSETS_FORBIDDEN_ON_DISCORD` unchanged and absent; existing noise-exclusion test green.
- **AC-5 (boundary recorded honestly): MATCH** — config has TRIMMED + BOUNDARY notes naming `pull_pending_notifications` + `F-10-7-3-R1`; residual filed in `story-run-flags.md`; `test_hermes_config_10_7_3_boundary_documented` asserts both marker strings present.
- **AC-6 (offline drift gates; live deferred): MATCH** — all `test_hermes_config.py` tests parse YAML directly (no Docker/Discord/Anthropic). Clause 3 (live Discord turn) explicitly NOT claimed.

No DRIFT; no AC text needed correcting.

## 2. File-List-vs-git diff check

`git status --porcelain` / `git diff --cached --name-only` cross-referenced against `### File List`:

- `hermes-config/config.yaml` — STAGED + IN FILE LIST ✅ (M)
- `tests/integration/test_hermes_config.py` — STAGED + IN FILE LIST ✅ (M)
- `_bmad-output/implementation-artifacts/story-run-flags.md` — STAGED + IN FILE LIST ✅ (M)
- `_bmad-output/implementation-artifacts/10-7-3-allowlist-trim-toward-mailbot-api-only.md` — STAGED + IN FILE LIST ✅ (A, the story file itself)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — STAGED, tracking artifact (status flip), expected side-effect, not a File-List entry per convention ✅

Not staged (correctly excluded): `.claude/settings.json` (pre-existing background), `10-7-0-spike-finding.md` (pre-existing background), `.autonomous-run-active.json` (run-state memo). No UNTRACKED story-adjacent files missed. **No silent scope-creep.**

## 3. Adversarial self-review

- [MEDIUM] `hermes-config/config.yaml` — Dropping `messaging` removes Rule R cross-platform PUSH from the Discord surface. On a future MULTI-platform deploy this would silently disable cross-platform notification send on chat turns. Mitigated: TRIMMED comment + test docstring both explicitly say a multi-platform deploy must re-add `messaging` deliberately. Residual risk accepted (single-user Adam-only deploy today).
- [MEDIUM] `hermes-config/config.yaml` — This story does NOT remove the spike's DOMINANT attractor (`pull_pending_notifications`), so on its own it does NOT get qwen to a reliable email-only menu on the flat surface. Risk: someone reads "allow-list trim toward mailbot-api-only" and assumes selection is fixed. Mitigated: BOUNDARY note + F-10-7-3-R1 + Completion Notes all state this is a PARTIAL lever; clause 3 explicitly not claimed.
- [LOW] `tests/integration/test_hermes_config.py` — `test_hermes_config_10_7_3_boundary_documented` is a text-grep gate; if the config comment is later reworded without the literal strings `pull_pending_notifications` / `F-10-7-3-R1` it red-gates even if the boundary is still documented under different wording. Accepted: the two strings are stable identifiers (a verb name + a residual id), low churn risk; the gate's whole purpose is to force those two anchors to persist.
- [LOW] The `messaging` toolset's exact membership (does it contain ONLY `send_message`, or other verbs too?) is inferred from epics.md §4350 + the 10.6.5 comment ("Rule R cross-platform notification send"), not from a live Hermes `tools list`. If `messaging` also carried a benign useful verb, dropping it loses that too. Accepted: offline story; the live `hermes tools list --platform discord` VERIFY runbook line (unchanged) is the operational check before deploy, and no email-reading turn needs a `messaging` verb.
- [LOW] No live-Discord proof in this story (by design, AC-6). The selection improvement is argued from the 10-7-0 spike, not re-measured here. Accepted: clause 3 is the epic live-walk's job; this is a config drift-gate story.

## 4. Self-caught issues remediated this audit

- MEDIUM (multi-platform Rule R loss): **ACCEPT WITH RATIONALE** — documented in config comment + test docstring + Dev Notes; single-user deploy makes it non-load-bearing today; future deploy re-evaluates deliberately.
- MEDIUM (partial-lever over-claim risk): **FIX NOW (done)** — BOUNDARY note + F-10-7-3-R1 residual + explicit "does NOT discharge clause 3" language shipped across config, flags file, and story. This was the load-bearing honesty fix and it is in the code.
- LOW (text-grep gate brittleness): **ACCEPT WITH RATIONALE** — the two anchor strings are stable identifiers; brittleness is the intended forcing function.
- LOW (messaging membership inferred): **ESCALATE TO REVIEWER** — flag for the reviewer to sanity-check whether dropping the whole `messaging` toolset (vs. a narrower lever) is the right granularity, given the surface is toolset-level only.
- LOW (no live proof): **ACCEPT WITH RATIONALE** — AC-6 scopes live proof out; deferred to epic walk.

## 5. Posture Audit

### 5.1 Lockfile hygiene
`git diff --cached --stat -- requirements.txt` → (no output). No dependency change. **N/A — no dep change.**

### 5.2 Cross-doc pair verification
The story cross-references the 10-7-0 spike + epics.md for the surface-lever grounding, and the config comment cross-references `pull_pending_notifications`. Verified the attractor claim against the canonical source:
```
$ Grep "pull_pending_notifications" mailbot_api/mcp_server.py  → matches at :123,:815,:951,:1091 (registered verb, intra-mailbot-api)
$ Grep "_EXPECTED_TOOL_COUNT = 26" mailbot_api/mcp_server.py   → :1133 (26 verbs in the one mailbot-api MCP server)
```
Verdict: MATCH — `pull_pending_notifications` is confirmed an intra-`mailbot-api` verb (not a separable toolset), which is exactly what the BOUNDARY note claims. **§5.2.1 (schema-doc):** N/A — File List contains no migrations paths. **PASS.**

### 5.3 Lifecycle string-uniqueness
N/A — story added no i18n keys (no graphical frontend; config + tests + docs only).

### 5.4 Multi-consumer impact scan
`hermes-config/config.yaml` `platform_toolsets.discord` is consumed by Hermes at container startup (not by `mailbot_api` code) and by `tests/integration/test_hermes_config.py` (updated in this story). No `mailbot_api/` module imports the config. Verified no other test/code reads the `messaging` entry:
```
$ Grep "messaging" over *.py/*.yaml/*.json  → only config.yaml (comments) + test_hermes_config.py (this story) + router.py:158 (a 10-7-2 prompt STRING mentioning "messaging", not the toolset)
```
Verdict: PASS — single functional consumer (the test), updated in-story; `router.py:158` is an unrelated prompt-text mention, not a config consumer.

### 5.5 Screenshot-based perception check
N/A — no user-visible UI surface; no AC uses "visible"/"appears"/"displays". Live-Discord proof is explicitly deferred (AC-6).

### 5.6 Upstream-contract spec coverage
N/A — story consumes no upstream-stripped/role-gated projection field. It is a config allow-list edit + its offline drift gates; no runtime data contract.

### 5.7 Module-level mutable container
N/A — story modified zero `.py` source files under `mailbot_api/`. The only `.py` touched is `tests/integration/test_hermes_config.py`, whose additions are module-level `frozenset` constants (`_TRIMMED_TOOLSETS_10_7_3`) — immutable by construction, and `_REQUIRED_DISCORD_TOOLSETS` remains a `frozenset`. No mutable module container introduced.

### 5.8 Dev-fixture seed-vs-production-shape parity
N/A — story added no test fixture consumed by code reading ORM output or pipeline payloads. The new tests read the real `hermes-config/config.yaml` on disk (the actual production artifact), not a synthesized fixture — the strongest possible parity (it IS the producer).

### 5.9 grep-verify-cited-figures
Cited figures: "26 verbs" (`_EXPECTED_TOOL_COUNT = 26`, verified at §5.2 Grep :1133 = MATCH); "pytest 1972 passed / 3 skipped / 3 deselected":
```
$ .venv/Scripts/python.exe -m pytest -q  → 1972 passed, 3 skipped, 3 deselected in 263.45s
```
Verdict: MATCH — test count re-run at audit time, not cited from prior prose. "+2 net vs 1970" = 1972 − 1970 (1970 is the 10-7-2 baseline in `story-run-flags.md`, the two new tests this story added) → MATCH. **PASS.**

### 5.10 Producer-boundary contract enforcement
N/A — story modified no normalizer/DTO/service feeding a typed ORM column, and no service returning an ORM row to an HTTP client. Config allow-list + tests only; produces no runtime values consumed by typed columns or HTTP responses.

### 5.11 Git-evidence consistency check
- **5.11.a (File-List-vs-working-tree):** cross-referenced in §2 above — all File-List paths STAGED + IN FILE LIST; no silent scope-creep; no declared-but-untouched. ✅
- **5.11.b (test-to-code ratio):** `git diff --cached --numstat`: testAdded=61 (`tests/integration/test_hermes_config.py`); docsAdded=118+12+29+? = markdown story (118) + flags (12) + config.yaml treated as infra/docs (29) + sprint-status (1); `prodAddedExcludingDocs` = 0 (no `mailbot_api/` source). Ratio denominator 0 → ratio null. Verdict: ✅ PASS by construction — zero production source added; this is a config+tests+docs story, tests exceed the (zero) production surface.
- **5.11.c (no-later-commits):** status flipped to in-progress 2026-07-16 (same session). `git log --since="2026-07-16" --oneline -- [File-List paths]` → (empty). ✅ PASS — same-session dev pass, no commits under attribution.
Verdict: **PASS.**

### 5.12 CR-cadence-mandatory surface classification

Story surface classification:

- **Criterion 1 (boundary-introducing): YES** — the `platform_toolsets.discord` allow-list IS a shared invariant that the Discord tool surface is checked against (5 drift-gate tests enforce keep-set / noise-exclusion / mcp-server-listing / messaging-exclusion / boundary-documented). This story changes that invariant's contents + adds two new gates. Evidence: `git diff --cached --stat tests/integration/test_hermes_config.py` → 61 insertions.
- **Criterion 2 (dep-introducing): NO** — no new dependency.
- **Criterion 3 (dev-self-flagged): YES** — §4 has one ESCALATE-TO-REVIEWER item (messaging-toolset granularity: is dropping the whole toolset the right lever?).
- **Criterion 4 (capstone): NO** — mid-epic story; not the last in Epic 10.7.
- **Criterion 5 (privacy-invariant): NO** — the allow-list is a tool-surface fidelity lever; it does not enforce a sensitivity/authorization invariant. (The propose→grant→drain safety pipeline is model-independent and untouched — spike §5.)
- **Criterion 6 (load-bearing-orchestrator): YES (soft)** — the Discord tool surface this allow-list curates is the primary integration surface for every qwen chat turn; it is a model-FACING contract (directly shapes what tools qwen can select). Epic 10.7's whole thesis leans on this surface.

Cadence verdict: **MANDATORY-CR** (criteria 1 + 3 + 6 fire). Reviewer model MUST differ from dev (opus-4-8) → sonnet-5.
