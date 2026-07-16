# Pre-Review Self-Audit — 10-7-2

**Generated:** 2026-07-16 by claude-opus-4-8
**Story file:** `_bmad-output/implementation-artifacts/10-7-2-tool-format-and-selection-system-prompt.md`
**Status at audit time:** review (post dev-story, pre code-review)

## 1. AC-vs-code drift scan

- **AC-1** (qwen-only instruction injected at the tool-call seam): MATCH — `_QWEN_TOOLCALL_SYSTEM_INSTRUCTION` (router.py:152) + `_compose_qwen_toolcall_system_text` (router.py:164) gated on `_TOOL_CAPABLE_LOCAL_MODEL_RE` (qwen-only); wired at router.py:2523. `claude-*` path returns unchanged. Test-locked both directions.
- **AC-2** (composes with, never replaces, client system messages): MATCH — the helper appends after the `"\n\n".join(system_parts)` result; `test_qwen_instruction_composes_with_client_system_messages` + `test_qwen_instruction_present_with_zero_client_system_messages` assert both branches.
- **AC-3** (no-op for non-tool / `ask_router` path): MATCH — helper is called ONLY at the `dispatch_tool_call` seam (grep: single call-site at router.py:2523); `ask_router` and `OllamaAdapter.call` untouched.
- **AC-4** (measured real-N fidelity + selection): MATCH — live measurement (`10-7-2-measurement-evidence.md`): selection 20/20 (no regression), adversarial Graph-id fidelity 20/20 exact @ temp 0.
- **AC-5** (unit tests prove the seam): MATCH — `tests/integration/test_dispatch_tool_call_qwen_system_prompt.py`, 4/4 pass.
- **AC-6** (honest disposition): MATCH — Completion Notes record ship-ON-by-default with the AC-4 data + $0/local + safety-untouched + clause-3-not-discharged framing.

No DRIFT; no AC-text edits required.

## 2. File-List-vs-git diff check

`git status --porcelain`:
```
 M .claude/settings.json                                                  (NOT story — env/pre-existing)
 M _bmad-output/implementation-artifacts/10-7-0-spike-finding.md          (NOT story — pre-existing WIP)
 M _bmad-output/implementation-artifacts/sprint-status.yaml               (story — status rows)
 M mailbot_api/router/router.py                                           (story — STAGED)
?? _bmad-output/implementation-artifacts/.autonomous-run-active.json      (run-state memo)
?? _bmad-output/implementation-artifacts/10-7-2-measurement-evidence.md   (story)
?? _bmad-output/implementation-artifacts/10-7-2-tool-format-and-selection-system-prompt.md (story)
?? tests/integration/test_dispatch_tool_call_qwen_system_prompt.py        (story — STAGED)
```
File List paths:
- `mailbot_api/router/router.py` — MODIFIED, STAGED ✅
- `tests/integration/test_dispatch_tool_call_qwen_system_prompt.py` — UNTRACKED→STAGED ✅
- `10-7-2-tool-format-and-selection-system-prompt.md` — UNTRACKED (to stage at Step 2.6) ✅
- `10-7-2-measurement-evidence.md` — UNTRACKED (to stage at Step 2.6) ✅
- `scratch/qwen_toolcall_10_7_2_measure.py` — gitignored, NOT staged (correct; scratch) ✅

Pre-existing modifications (`.claude/settings.json`, `10-7-0-spike-finding.md`) are unrelated background work — NOT staged, will not be swept at Step 2.6. No UNTRACKED story-scope file left behind.

## 3. Adversarial self-review

- [LOW] router.py:152 — the instruction contains an em-dash (`—`, non-ASCII). ruff passed and the file already uses em-dashes throughout its comments, so no lint/encoding risk; noted for completeness (the console `�` in the measurement run was cp1252 rendering, not a source defect).
- [MED] router.py:164 — the gate uses `_TOOL_CAPABLE_LOCAL_MODEL_RE.match`, NOT `_model_supports_tool_calls`. If a future dev "simplifies" to the capability predicate, the instruction would wrongly inject on the `claude-*` path. Mitigated by `test_claude_tool_dispatch_does_not_inject_instruction` (locks absence on the API path) + an explicit docstring warning.
- [LOW] router.py:2523 — injection sits AFTER degraded-mode demotion (:1964-1967), so a budget-degraded demotion landing on qwen correctly receives the instruction. Verified by reading the control flow; no test drives the degraded→qwen path with a system-text capture (the existing `test_dispatch_tool_call_degraded_no_qwen_tools` covers the incapable case). Acceptable: the injection is a pure function of the resolved `model`, and the qwen-positive path is directly tested.
- [LOW] Instruction length — kept short (spike warns 3B degrades on long prompts). The measurement confirms it neither helps nor hurts selection on a good description; length is not load-bearing here.
- [MED] AC-4 measurement is direct-ollama drive, NOT the real Hermes chat path — so it proves neutral+fidelity-safe but does NOT prove the instruction HELPS on the real path (that's clause 3, owed at the epic live walk). This is disclosed in the evidence note + Completion Notes, not hidden.

## 4. Self-caught issues remediated this audit

- LOW em-dash (§3): **ACCEPT WITH RATIONALE** — consistent with the file's existing style; ruff/mypy green.
- MED wrong-gate-if-refactored (§3): **FIX NOW (already in place)** — docstring warning + dedicated test lock both shipped in this pass.
- LOW degraded→qwen no system-capture test (§3): **ACCEPT WITH RATIONALE** — injection is a pure function of resolved `model`; qwen-positive path directly tested; degraded-incapable path already covered.
- LOW instruction length (§3): **ACCEPT WITH RATIONALE** — measured neutral.
- MED direct-drive ≠ Hermes-path (§3): **ACCEPT WITH RATIONALE** — honestly disclosed; discharging it is clause 3's job (epic live walk), out of this story's scope by design.

## 5. Posture Audit

### 5.1 Lockfile hygiene
`git diff --stat -- requirements.txt` → (no output). Non-dep-change story. ✅ PASS.

### 5.2 Cross-doc pair verification
Cross-doc branch: N/A — the story makes no doc-vs-doc canonical claims (it cites source-code line ranges + the spike finding, verified in §5.9, not doc-to-doc contradictions). §5.2.1 schema-touching branch: N/A — File List contains no `mailbot_api/db/migrations/` paths. ✅ N/A.

### 5.3 Lifecycle string-uniqueness
N/A — story added no i18n keys (no graphical frontend; the instruction is a single English constant, not a lifecycle key set). ✅ N/A.

### 5.4 Multi-consumer impact scan
The new symbols are consumed at exactly one site.
```
$ Grep "_QWEN_TOOLCALL_SYSTEM_INSTRUCTION|_compose_qwen_toolcall_system_text" mailbot_api/
  router.py:152  (definition)
  router.py:164  (definition)
  router.py:185  (internal use in helper)
  router.py:186  (internal use in helper)
  router.py:2523 (sole call-site — dispatch_tool_call)
```
Both symbols are module-private (`_`-prefixed) and used only within `router.py`. Verdict: 1 production consumer (the dispatch seam); no shared re-export. ✅ PASS.

### 5.5 Screenshot-based perception check
N/A — backend-only; no user-visible painted surface. The story's "visible/appears" surface is a model-facing system prompt, not a UI. ✅ N/A.

### 5.6 Upstream-contract spec coverage
N/A — the story consumes no upstream-stripped/role-gated projection field. It reads the already-assembled `system_text` (built one line above) and the resolved `model`; both are local, present-always values. The present-vs-absent client-system-messages axis (which IS a contract variation) is tested both ways (AC-2 tests). ✅ PASS (both cases of the one relevant variation encoded).

### 5.7 Module-level mutable container check
`_QWEN_TOOLCALL_SYSTEM_INSTRUCTION` is a module-level `str` (immutable) built from a parenthesized literal concatenation — no `dict`/`list`/`set`/counter, never mutated. `_compose_qwen_toolcall_system_text` is a pure function (no module state). No `mailbot_api/router/router.py` per-process mutable global introduced. ✅ PASS.

### 5.8 Dev-fixture seed-vs-production-shape parity
N/A — the story introduces no ORM-output / pipeline-payload fixture. Test tools use hand-authored `ChatCompletionToolDef` shapes (the real Pydantic producer type, constructed directly), and the measurement uses the LIVE MCP surface (real producer), not a synthesized fixture. ✅ N/A.

### 5.9 grep-verify-cited-figures
- Cite "pytest 1961 passed (+4 vs 1957)":
  ```
  $ .venv/Scripts/python.exe -m pytest -q   → 1961 passed, 3 skipped, 3 deselected
  ```
  10-7-1 baseline 1957 (sprint-status row); 1961 − 1957 = 4 new tests = the 4 in this story's test file. Verdict: MATCH.
- Cite "selection 20/20, fidelity 20/20": from the live measurement run output pasted in `10-7-2-measurement-evidence.md` (SPIKE_N=5 → 4 paraphrases × 5 repeats = 20). Verdict: MATCH (command output is the leaf artifact).
- Cite "testAdded 252 / prod 64 → ratio 3.9": `git diff --cached --numstat` → `64 router.py`, `252 test file`. 252/64 = 3.94. Verdict: MATCH.
- Line refs (router.py:152/164/2523): grep in §5.4 confirms current line numbers. Verdict: MATCH.
✅ PASS.

### 5.10 Producer-boundary contract enforcement
N/A both sub-rules — the story writes no typed ORM column (§5.10.a: no `int()`/`Decimal()`/`fromisoformat()` on third-party input; the helper only concatenates strings) and returns no ORM row to an HTTP client (§5.10.b: the value produced is a system-prompt string handed to the adapter, not a response shape). No normalizer/extractor/ingestion path touched (§5.10.c/d). ✅ N/A.

### 5.11 Git-evidence consistency check
- **5.11.a** File-List-vs-tree: `git status --porcelain` (pasted §2). Staged story paths (router.py, test file) IN File List ✅; story docs UNTRACKED pending Step 2.6 ✅; pre-existing `.claude/settings.json` + `10-7-0-spike-finding.md` NOT in File List and NOT staged (unrelated background) ✅. No silent scope-creep.
- **5.11.b** Test ratio: `git diff --cached --numstat` → testAdded 252, docsAdded 0 (staged code+test only), prodAddedExcludingDocs 64. Ratio 252/64 = 3.94 ≥ 0.30. ✅ PASS.
- **5.11.c** No-later-commits-under-attribution: single-session dev pass (status flipped ready-for-dev→in-progress→review within this run, baseline 6cf920b). `git log` under File List paths shows no commits since flip. ✅ N/A (same-session).
✅ PASS.

### 5.12 CR-cadence-mandatory surface classification
- Criterion 1 (boundary-introducing): NO — no new writer-monopoly / lint boundary / allowlist in check_boundaries.py.
- Criterion 2 (dep-introducing): NO — requirements.txt unchanged (§5.1).
- Criterion 3 (dev-self-flagged): NO — §4 has no ESCALATE-TO-REVIEWER items (all ACCEPT/FIX-NOW).
- Criterion 4 (capstone): NO — mid-epic; other Epic 10.7 stories (10.7.3) are independent surfaces.
- Criterion 5 (privacy-invariant): NO — no FR-2.3/2.5/NFR-PRIV surface; the safety pipeline (propose→grant→drain) is untouched and model-independent.
- Criterion 6 (load-bearing-orchestrator): **YES** — `dispatch_tool_call` is the Router's tool-call dispatch seam, the primary integration surface for every Hermes chat tool-call turn. Modifying its system-prompt assembly is a load-bearing dispatch-seam change (the story row itself pins "MANDATORY-CR reviewer≠dev, dispatch seam").

Cadence verdict: **MANDATORY-CR** (criterion 6 fires; also the epic-level discipline pins reviewer≠dev on every product-code story).

## Posture Audit summary table

| Check | Status |
| --- | --- |
| 5.1 Lockfile hygiene | ✅ PASS |
| 5.2 Cross-doc pair verification | N/A — no cross-doc claims; no migration paths |
| 5.3 Lifecycle string-uniqueness | N/A — no i18n keys |
| 5.4 Multi-consumer impact scan | ✅ PASS — 1 call-site, module-private |
| 5.5 Screenshot-based perception check | N/A — backend-only |
| 5.6 Upstream-contract spec coverage | ✅ PASS — client-system present/absent both tested |
| 5.7 Module-level mutable container | ✅ PASS — immutable str + pure fn |
| 5.8 Dev-fixture seed-vs-production-shape parity | N/A — no ORM/pipeline fixture |
| 5.9 grep-verify-cited-figures | ✅ PASS |
| 5.10 Producer-boundary contract enforcement | N/A — no typed-column write / HTTP row emission |
| 5.11 Git-evidence consistency check | ✅ PASS |
| 5.12 CR-cadence-mandatory surface classification | MANDATORY-CR |
