# Pre-Review Self-Audit — 10-7-5

**Generated:** 2026-07-15 by claude-opus-4-8 (dev)
**Story file:** _bmad-output/implementation-artifacts/10-7-5-find-emails-tool-description-rewrite.md
**Status at audit time:** review (post dev-story, pre code-review)

## 1. AC-vs-code drift scan

- **AC-1** (find_emails desc natural-language, no jargon): **MATCH** — `_TOOL_DESCRIPTIONS["find_emails"]` (`mcp_server.py:~977`) leads "Find, list, show, or search the user's emails — the primary tool for reading the inbox, including unread mail." "unread"/"inbox" present; "email projections"/"Rule J" removed.
- **AC-2** (100-cap preserved plainly): **MATCH** — desc reads "up to 100 at a time" + "call hydrate_email for a full body."
- **AC-3** (sibling sweep): **MATCH** — `count_emails`/`get_thread`/`hydrate_email`/`get_sender_summary` rewritten; constraints preserved (5-opens/turn + confidential-refused on hydrate_email; count-only on count_emails). `pull_pending_notifications` untouched (10.7.3 scope).
- **AC-4** (contract test updated, not deleted): **MATCH** — `test_list_tools_returns_constraint_phrases` updated: removed find_emails "Rule J" assert, added "unread"+natural-verb+`"projection" not in` asserts, kept "100"; sibling "Rule J" literals → purpose-word asserts; 26-count assert intact.
- **AC-5** (description-only, no wiring/schema change): **MATCH** — only `_TOOL_DESCRIPTIONS` values + one test edited; wrappers/schemas/fail-fast unchanged; suite unchanged at 1941 passed.
- **AC-6** (direct-drive scope honesty): **MATCH** — Completion Notes record §4.4 direct-drive measure (0/20→20/20) and that clause 3 (live Discord turn) + real-N arg-fidelity re-check remain owed. No over-claim.

No DRIFT — no AC text edits needed.

## 2. File-List-vs-git diff check

`git status --porcelain`:
```
 M .claude/settings.json                                              (pre-existing background — NOT story scope)
 M _bmad-output/implementation-artifacts/10-7-0-spike-finding.md      (pre-existing background — NOT story scope)
 M _bmad-output/implementation-artifacts/sprint-status.yaml           (story-adjacent — status flips)
 M mailbot_api/mcp_server.py                                          (IN FILE LIST)
 M tests/integration/test_mcp_server.py                               (IN FILE LIST)
?? _bmad-output/implementation-artifacts/.autonomous-run-active.json  (run-state marker — not staged)
?? _bmad-output/implementation-artifacts/10-7-5-...-rewrite.md        (IN FILE LIST — this story file)
```
File List entries:
- `mailbot_api/mcp_server.py` — **MODIFIED-NOT-STAGED** (will stage at Step 2.6) ✅
- `tests/integration/test_mcp_server.py` — **MODIFIED-NOT-STAGED** ✅
- `10-7-5-...-rewrite.md` — **UNTRACKED** (this story file) ✅ (staged at 2.6)

Pre-existing `.claude/settings.json`, `10-7-0-spike-finding.md` mods are background WIP present at baseline (`47b5f75` git status at run start showed them) — NOT staged, NOT story scope. No UNTRACKED story-scope file left un-added.

## 3. Adversarial self-review

- [LOW] `mcp_server.py` find_emails desc — the phrase "up to 100 at a time" is looser than the old "Capped at 100 results"; a pedant could read it as "paginate 100 at a time indefinitely." The verb still hard-caps at 100 (LIMIT_EXCEEDED at limit>100) so no behavior gap, but the wording is slightly less precise. ACCEPT (see §4).
- [LOW] Sibling `count_emails` desc dropped the explicit "(cheap signal)" hint that told the agent count is cheaper than listing. The natural-language "without listing them" partially preserves the intent, but the cost-signal nuance is softened. ACCEPT — cost hint is secondary to selection correctness, which was the story's whole point.
- [MEDIUM] The spike's proven-effective string was `find_emails`-only (leaf_desc cell, 20/20). My sibling rewrites (`count_emails` etc.) are NOT independently spike-measured — they follow the same natural-language principle but could, in theory, make a sibling *more* attractive than `find_emails` on a real turn (e.g. an over-eager `count_emails` desc pulling a "show me" turn). Mitigation: I kept `find_emails` explicitly framed as "the primary tool for reading the inbox" and `count_emails` scoped to "how many rather than to see" — a deliberate hierarchy. ESCALATE TO REVIEWER (see §4) — reviewer should sanity-check the sibling descriptions don't create a new distractor.
- [LOW] `pull_pending_notifications` (the measured dominant distractor) is left untouched by design (10.7.3 scope). On the flat-26 surface this story alone does NOT fix selection (§1 still 0/N) — only the leaf/scoped-menu regime. This is correctly scoped but means the story's *own* impact is not live-provable until 10.7.3 lands. ACCEPT — story AC-6 already records this honestly.

## 4. Self-caught issues remediated this audit

- [LOW] "up to 100 at a time" imprecision → **ACCEPT WITH RATIONALE** — verb hard-cap is authoritative; description precision is secondary and the plainer wording is the point.
- [LOW] `count_emails` "(cheap signal)" nuance softened → **ACCEPT WITH RATIONALE** — selection correctness > cost-hint nuance for this story.
- [MEDIUM] sibling descriptions not independently spike-measured → **ESCALATE TO REVIEWER** — ask the reviewer to confirm the rewritten sibling descriptions preserve the find_emails-primary hierarchy and don't introduce a new mis-pick attractor. (This is criterion 3 → contributes to MANDATORY-CR.)
- [LOW] flat-26 not fixed by this story alone → **ACCEPT WITH RATIONALE** — correctly fenced to 10.7.3; AC-6 records it.

§3 is not shallow (4 issues, one MEDIUM escalated).

## 5. Posture Audit

### 5.1 Lockfile hygiene
```
$ git diff --stat -- requirements.txt
(no output)
```
N/A — no dependency change. requirements.txt untouched.

### 5.2 Cross-doc pair verification
N/A (cross-doc branch) — the story makes no claim that another canonical doc must reflect. The rewrite is a self-contained model-facing string; the spike finding (10-7-0) it implements is historical evidence, not a live cross-doc contract to keep in sync.
§5.2.1 (schema-touching): N/A — File List contains no migrations paths.

### 5.3 Lifecycle string-uniqueness
N/A — story added no i18n keys (MailBot has no graphical frontend / i18n surface).

### 5.4 Multi-consumer impact scan
`_TOOL_DESCRIPTIONS` is a module-level dict consumed only within `mcp_server.py` (applied at `:1282-1284` via `server.add_tool`).
```
$ Grep "_TOOL_DESCRIPTIONS" mailbot_api tests   → mailbot_api/mcp_server.py only (definition + application + fail-fast assert)
```
The runtime consumer is the model itself (the description string on the function list). Verdict: single production consumer (the MCP registration loop); no other module imports these strings. ✅ PASS.

### 5.5 Screenshot-based perception check
N/A — no user-visible UI surface; backend MCP description string. No "visible"/"appears" AC.

### 5.6 Upstream-contract spec coverage
N/A — story consumes no upstream-stripped/projection field. Purely a description string; no role-gated or workspace-scoped read path touched.

### 5.7 Module-level mutable container check
Modified `.py` file: `mailbot_api/mcp_server.py`. `_TOOL_DESCRIPTIONS: dict[str, str]` is a module-level dict — but it is a read-only constant table populated once at import and only *read* at `add_tool` time (never mutated at runtime).
```
$ Grep "_TOOL_DESCRIPTIONS\[" mailbot_api/mcp_server.py   → only `_TOOL_DESCRIPTIONS[tool_name]` READ at :1283; no write/mutation
```
This story added no new mutable container and did not change the dict's read-only lifecycle (pre-existing pattern, unchanged by this story). ✅ PASS — no new module-level mutable state; edited values of an existing read-only table.

### 5.8 Dev-fixture seed-vs-production-shape parity
N/A — story introduced/modified zero test fixtures. The only test change is assertion edits in an existing integration test that boots the real `build_mcp_server` + connected client (no fixture payload).

### 5.9 grep-verify-cited-figures
Cited figures in the story/pre-review:
```
Cite: "1941 passed / 3 skipped / 3 deselected"
Verification: $ .venv/Scripts/python.exe -m pytest -q  → "1941 passed, 3 skipped, 3 deselected, 1 warning in 260.14s"
Verdict: MATCH
```
```
Cite: "0/20 → 20/20 leaf selection" — sourced from 10-7-0-spike-finding.md §4.4 (leaf_desc cell), a frozen historical figure from the completed spike story.
Verdict: MATCH (frozen historical figure, cited to its source artifact §4.4; not re-derived here — the spike is done and its measurement is the authority).
```
```
Cite: "26 tools" / "_EXPECTED_TOOL_COUNT == 26"
Verification: $ Grep "_EXPECTED_TOOL_COUNT = 26" mailbot_api/mcp_server.py  → ":1117: _EXPECTED_TOOL_COUNT = 26"; test asserts len(by_name)==26, suite green.
Verdict: MATCH
```
✅ PASS.

### 5.10 Producer-boundary contract enforcement
N/A — story modifies no normalizer/DTO/service feeding a typed ORM column, and no service returning an ORM row to an HTTP client. Description strings only; no coercion, no response-shape widening. Both halves confirmed not in scope.

### 5.11 Git-evidence consistency check
**5.11.a** File-List-vs-working-tree: see §2 — the two source paths + story file are present in git output; declared-but-untouched = none; staged-not-in-list = none (nothing staged yet; staging at 2.6 will use explicit paths). ✅ PASS.
**5.11.b** Test-to-code ratio: this is a description-string + test-assertion change. `prodAddedExcludingDocs` = the `_TOOL_DESCRIPTIONS` value edits (a handful of string lines) and `testAdded` = the assertion edits — the change is dominated by test + description prose, not new production logic branches. No new untested branch/API surface (zero new code paths; the verbs, schemas, wiring are untouched). Ratio-gate is not meaningfully applicable to a pure-description change; treat as ✅ PASS — no untested production behavior added.
**5.11.c** No-later-commits-under-attribution: single-session dev pass; story flipped to in-progress and to review in this same session. N/A.

### 5.12 CR-cadence-mandatory surface classification
```
Criterion 1 (boundary-introducing): NO — no new writer monopoly / lint boundary / shared invariant; edits values of an existing description table.
Criterion 2 (dep-introducing): NO — no requirements.txt change.
Criterion 3 (dev-self-flagged): YES — §4 escalates the "sibling descriptions not independently spike-measured; confirm no new mis-pick attractor" concern TO REVIEWER.
Criterion 4 (capstone): NO — not the last story in Epic 10.7 (10.7.3/10.7.1 remain).
Criterion 5 (privacy-invariant): NO — no FR-2.3/2.5, NFR-PRIV-*, AR-D12-* surface; a description string does not touch the sensitivity/authorization pipeline.
Criterion 6 (load-bearing-orchestrator): YES — the MCP tool-description surface is the PRIMARY model-facing integration surface for the local qwen tool-calling lane; this description IS the contract the whole cost-thesis fidelity gate (Epic 10.7 clause 3 / Epic 10.6 clause 3b) turns on. A wrong description here mis-routes every qwen inbox turn. The epic charter explicitly marks description = model-facing contract → MANDATORY-CR reviewer ≠ dev.

Cadence verdict: MANDATORY-CR (criterion 3 + criterion 6 fire).
```

## Posture Audit summary table

| Check | Status |
| --- | --- |
| 5.1 Lockfile hygiene | N/A — no dep change |
| 5.2 Cross-doc pair verification | N/A — no cross-doc claim; no migrations |
| 5.3 Lifecycle string-uniqueness | N/A — no i18n / no frontend |
| 5.4 Multi-consumer impact scan | ✅ PASS — single consumer (MCP registration loop) |
| 5.5 Screenshot-based perception check | N/A — backend string, no UI |
| 5.6 Upstream-contract spec coverage | N/A — no upstream-stripped field consumed |
| 5.7 Module-level mutable container | ✅ PASS — read-only table, no new mutable state |
| 5.8 Dev-fixture seed-vs-production-shape parity | N/A — no fixtures introduced/modified |
| 5.9 grep-verify-cited-figures | ✅ PASS — test count + 26-count + spike figure verified |
| 5.10 Producer-boundary contract enforcement | N/A — no typed-column producer / HTTP row emit |
| 5.11 Git-evidence consistency check | ✅ PASS — File List matches git; single-session |
| 5.12 CR-cadence-mandatory surface classification | MANDATORY-CR (criterion 3 + 6) |
