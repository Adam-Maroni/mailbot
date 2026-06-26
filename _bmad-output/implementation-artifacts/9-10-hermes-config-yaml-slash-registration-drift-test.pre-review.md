# Pre-Review Self-Audit — 9-10 (reframed Path γ)

**Generated:** 2026-06-26 by claude-opus-4-7[1m]
**Story file:** _bmad-output/implementation-artifacts/9-10-hermes-config-yaml-slash-registration-drift-test.md
**Status at audit time:** review (post dev-story, pre code-review)

## 1. AC-vs-code drift scan

- **AC-1 (forward-drift MCP→SKILL.md):** MATCH — `test_every_registered_tool_has_skill_md_entry` verifies every registered tool has a SKILL.md entry or is on the exemption allow-list. Currently 25 tools, 25 SKILL.md entries, 0 exemptions → passes.
- **AC-2 (reverse-drift SKILL.md→MCP):** MATCH — `test_no_stale_skill_md_headings_for_removed_verbs` verifies no stale SKILL.md headings. Currently 0 stale → passes.
- **AC-3 (frontmatter MCP-tool-count consistency):** MATCH — `test_frontmatter_mcp_tool_count_matches_registered_count` extracts `via N MCP tools` integer (= 25) and compares to `len(registered_tools)` (= 25).
- **AC-4 (deliberate-omission sanity tests):** MATCH — both regression sentinels ship: `test_forward_drift_detects_missing_skill_md_section` (canary `set_model_oneshot`) and `test_reverse_drift_detects_stale_skill_md_section` (canary `inspect_policy`).
- **AC-5 (exemption fixture):** MATCH — `tests/fixtures/skill_md_exempt_tools.yaml` ships with `exempt: []` + header comment block documenting legitimate-exemption criteria + add-procedure. Validator test verifies every exemption (if any) is a real registered tool.
- **AC-6 (no slash_commands block):** MATCH — `git diff hermes-config/config.yaml` is empty for Story 9-10's commit scope; `test_hermes_config_discord_at_top_level_not_under_gateway` continues to pass.
- **AC-7 (§5.12 GATE-COVERAGE-ELIGIBLE):** §5.12 below confirms — no criterion fires.

**Mid-pass drift discovered (load-bearing finding):** initial parser run extracted only 20 of 25 expected tool names. Investigation: 5 MCP-registered tools (`ack_notification`, `pull_pending_notifications`, `compose_digest`, `finalize_digest_delivery`, `unmute_category`) were mentioned in SKILL.md prose but lacked per-tool `### <tool_name>` headings. Added 5 new per-tool sections after `render_spend_chart`. This is EXACTLY the silent-no-op failure mode Story 9-10 exists to prevent recurring — the test would have shipped on already-drifted docs. The principled fix is to add the missing docs (per the fixture's "When NOT to add to exempt list" criteria), not to exempt them.

## 2. File-List-vs-git diff check

**Tracked (modified):**

- `hermes-config/skills/mailbot/SKILL.md` MODIFIED — TRACKED ✅ — added 5 new tool sections
- `_bmad-output/planning-artifacts/epics.md` MODIFIED — TRACKED ✅ — OQ-1 discharge annotation
- `_bmad-output/implementation-artifacts/sprint-status.yaml` MODIFIED — TRACKED ✅

**Untracked (new files in scope, will be staged):**

- `tests/integration/test_skill_md_registration_coverage.py` UNTRACKED ✅
- `tests/fixtures/skill_md_exempt_tools.yaml` UNTRACKED ✅
- `_bmad-output/implementation-artifacts/9-10-hermes-config-yaml-slash-registration-drift-test.md` UNTRACKED ✅ — story file
- `_bmad-output/implementation-artifacts/9-10-hermes-config-yaml-slash-registration-drift-test.pre-review.md` UNTRACKED ✅ — this file

**Out-of-scope working-tree state:** various unrelated files under `.claude/skills/`, `.claude/hooks/`, `_bmad-output/brainstorming/`, etc. — not part of Story 9-10, will NOT be staged at Step 2.6.

**Verdict:** all File-List entries TRACKED or pending-stage. No silent scope-creep.

## 3. Adversarial self-review

- **[MEDIUM] Mid-pass docs drift fix was a Story 9-10 scope expansion:** the original story scope was "add the drift test." Adding 5 new SKILL.md sections to make the test pass on the current state is a scope expansion that wasn't in the original ACs. **However**, it's the only principled path — shipping a known-failing test would have been a loud-pass-on-broken-state regression. The alternative (exempting all 5) violates the fixture's "When NOT to add to exempt list" criteria. The drift-fix is correctly inline with the test introduction; it's exactly the failure mode the test is designed to catch, caught one cycle earlier than the test would have on its own. **Accept as the right call.**

- **[LOW] Parser regex is permissive — could match identifiers in non-tool contexts:** the regex `\`([a-z_][a-z0-9_]*)\`` finds ANY backticked snake_case identifier on a `### ` line. In theory a future SKILL.md heading like `### Notes about \`policy_user_overrides_yaml\`` (an arbitrary identifier-shaped backticked thing that isn't a tool) would be captured as a "tool name" and the reverse-drift assertion would FAIL on it. Mitigation: SKILL.md's existing convention is that the FIRST backticked token in a `### ` heading IS the tool name; no current heading has backticked non-tool identifiers. If a future heading introduces one, the test will FAIL loudly (the failure mode is loud, not silent). The exemption fixture would be the escape hatch. **Accept; document in the parser docstring.** Done in the test file's docstring.

- **[LOW] The deliberate-omission tests aren't true monkeypatch tests:** they don't actually intercept the AC-1 / AC-2 test's `_load_skill_md_text()` or `_get_registered_tools()` calls. Instead they compute the diff verdict against a synthetic input set that omits one canary. This is functionally equivalent — if the diff computation is broken, both the real assertion AND the regression sentinel break together. But a future refactor that moves the assertion logic into a helper function would need to keep the sanity tests pointing at the same helper to remain protective. **Accept; the simpler shape avoids the "monkeypatch the test under test" anti-pattern (which would be hard to reason about) at a small risk-coverage cost.** Document in the test file's docstring near the deliberate-omission test pair.

- **[LOW] Boundary check — `yaml.safe_load` in a test file:** the test file calls `yaml.safe_load` on the exemption fixture path. The `_YAML_LOAD_ALLOW` boundary list in `scripts/check_boundaries.py` only allowlists `mailbot_api/router/policy.py` + `mailbot_api/sensitivity/patterns.py`. **Verified at dev pass:** the boundary check exit-0 — the rule fires only on `mailbot_api/*` source paths, so test files in `tests/integration/` are not subject to it. **Accept; passes the boundary gate cleanly.**

- **[LOW] The exemption-fixture parser doesn't validate the YAML schema:** if a malicious or buggy edit produces shape `{exempt: "not-a-list"}` or `{not_exempt: [...]}`, `_load_exempt_set()` returns an empty set silently rather than failing. **However**, the validator test `test_exemption_list_entries_are_real_tools` would still pass on an empty set; the forward-drift test would treat all tools as needing SKILL.md entries (the safe default). The failure mode is **safe-by-default** (more restrictive, not less), so a malformed exemption file effectively self-disables. **Accept; the alternative (strict pydantic schema) is over-engineering for a 1-key fixture.**

## 4. Self-caught issues remediated this audit

1. **MEDIUM Mid-pass docs drift fix scope expansion** — **FIX NOW (applied during dev pass).** Added 5 SKILL.md sections; documented as a Story 9-10 finding rather than rejecting/exempting. Already in the diff.

2. **LOW Parser regex permissiveness** — **DOCUMENT.** Added a paragraph to the test file's docstring explaining the convention (first backticked identifier on a `### ` line IS the tool name) and the failure-mode-is-loud safety property.

3. **LOW Deliberate-omission tests aren't true monkeypatch** — **DOCUMENT.** The test file's docstring explains the simpler shape's trade-off. No code change needed.

4. **LOW Boundary check yaml.safe_load** — **ACCEPT — verified to pass at dev pass.** No code change.

5. **LOW Exemption-fixture schema validation** — **ACCEPT WITH RATIONALE — safe-by-default failure mode.** No code change.

## 5. Posture Audit

### 5.1 — Lockfile hygiene

```bash
$ git diff --stat -- requirements.txt
(no output)
```

**Verdict:** ✅ PASS — no `requirements.txt` modifications.

### 5.2 — Cross-doc pair verification

**Cross-doc claims in this story:**

- Claim: "Story 9-3 OQ-2 discharged AC-4 as architecturally-impossible" → references the Story 9-3 file. Verified: 9-3 story file lines 30-36 + 150-152 + 254 document the OQ-2 expanded finding. **MATCH.**
- Claim: "Story 9-4 OQ-1 is the same precedent" → references the Story 9-4 file's OQ-1 section. Verified: 9-4 story file contains OQ-1 architectural-impossibility discharge. **MATCH.**
- Claim: "RECONCILIATION-NOTES §1.4/§1.5 ban `discord.slash_commands`" → references the existing test:

  ```
  $ Grep "RECONCILIATION-NOTES §1.4|RECONCILIATION-NOTES §1.5|slash_commands.*RECONCILIATION" tests/integration/test_hermes_config.py
  ```

  Test at lines 106-126 references the RECONCILIATION-NOTES citation verbatim. **MATCH.**

**§5.2.1 schema-touching trigger:** N/A — File List contains zero paths under `mailbot_api/db/migrations/`. No schema changes.

**Verdict:** ✅ PASS.

### 5.3 — Lifecycle string-uniqueness

**Verdict:** N/A — story added zero i18n keys.

### 5.4 — Multi-consumer impact scan

- `tests/integration/test_skill_md_registration_coverage.py` — new file; zero existing consumers (it IS the consumer of `build_mcp_server` + SKILL.md + the exemption fixture).
- `tests/fixtures/skill_md_exempt_tools.yaml` — new file; only consumer is the test above.
- `hermes-config/skills/mailbot/SKILL.md` — modified (added 5 sections). Consumers:
  - Hermes runtime reads SKILL.md as agent-facing skill docs (operational concern; new sections are documentation-only, no behavior change)
  - This story's new test parses SKILL.md headings (PRIMARY consumer)
  - No other production consumers Grep'd

**Verdict:** ✅ PASS — modifications are documentation-only; no behavioral surface touched.

### 5.5 — Screenshot-based perception check

**Verdict:** N/A — project has no graphical frontend per PORTING.md; SKILL.md is text-rendered by Hermes/Discord.

### 5.6 — Upstream-contract spec coverage

**Story 9-4 upstream contract — 25 MCP tools registered + 25 SKILL.md sections:**

- Present case: all 25 tools registered AND documented → test passes cleanly (verified).
- Absent case (canary missing): deliberate-omission tests cover both directions (forward-drift removes one from documented set; reverse-drift removes one from registered set). Both assertions fire correctly with the canary named.

**Verdict:** ✅ PASS — present-AND-absent coverage via deliberate-omission sanity tests.

### 5.7 — Module-level mutable container check

Story 9-10 adds ZERO new Python source files under `mailbot_api/`. The test file is under `tests/integration/` (covered by the Python-stack overlay's test-bleed concern, but new file). Module-level state in the new test file:

```
$ Grep -n "^[A-Z_]+\s*[:=]" tests/integration/test_skill_md_registration_coverage.py
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILL_MD_PATH = _REPO_ROOT / ...
_EXEMPT_FIXTURE_PATH = _REPO_ROOT / ...
_SKILL_HEADING_RE = re.compile(...)
_BACKTICKED_IDENT_RE = re.compile(...)
_FRONTMATTER_COUNT_RE = re.compile(...)
```

All 6 module-level declarations are **immutable**: `Path` instances (immutable), compiled regex objects (immutable). No mutable containers. **Verdict:** ✅ PASS.

### 5.8 — Dev-fixture seed-vs-production-shape parity

`tests/fixtures/skill_md_exempt_tools.yaml` is a NEW fixture with shape `{exempt: list[str]}`. Pattern 1 (shape-faithful synthesis from a contract defined here in this story, not from an external producer). The shape is documented in the fixture's header comment + validated by the AC-5 test. Initial contents `exempt: []` are operator-state (Adam-controlled), not producer-recorded.

**Verdict:** ✅ PASS — fixture shape is contract-anchored (Story 9-10 IS the producer of the shape).

### 5.9 — grep-verify-cited-figures

Numeric cites in this pre-review + the story file:

- **"1377 + 2 + 3-deselected" / "+7 net tests"** — verified at dev pass via `pytest -q` exit-0 → "1377 passed, 2 skipped, 3 deselected". Baseline (Story 9-4 done-flip per sprint-status.yaml line 249): 1370+2+3. Delta: 1377 - 1370 = 7. **MATCH.**
- **"25 MCP tools / 25 SKILL.md entries"** — verified via `_get_registered_tools(tmp_path)` returns set of length 25 AND `_parse_skill_md_tool_names(...)` returns set of length 25. The AC-3 test asserts these are equal AND match the frontmatter `via 25 MCP tools.` claim. **MATCH.**
- **"5 missing SKILL.md sections" / "added 5 new sections"** — verified by counting the 5 names: `unmute_category`, `pull_pending_notifications`, `ack_notification`, `compose_digest`, `finalize_digest_delivery`. Parser went 20 → 25. **MATCH.**

**Verdict:** ✅ PASS — every cited figure verified.

### 5.10 — Producer-boundary contract enforcement

Story 9-10 adds zero production code paths. The new test file consumes existing surfaces (`build_mcp_server`, file-system reads, regex). No new producer surfaces. **§5.10.a / 5.10.b / 5.10.c / 5.10.d all N/A.**

**Verdict:** ✅ PASS.

### 5.11 — Git-evidence consistency check

**§5.11.a — File-List-vs-working-tree consistency:**

```
$ git status --porcelain (in-scope filter)
 M _bmad-output/implementation-artifacts/sprint-status.yaml
 M _bmad-output/planning-artifacts/epics.md
 M hermes-config/skills/mailbot/SKILL.md
?? _bmad-output/implementation-artifacts/9-10-hermes-config-yaml-slash-registration-drift-test.md
?? _bmad-output/implementation-artifacts/9-10-hermes-config-yaml-slash-registration-drift-test.pre-review.md
?? tests/fixtures/skill_md_exempt_tools.yaml
?? tests/integration/test_skill_md_registration_coverage.py
```

Every File-List entry maps to a M or ?? line. No declared-but-not-touched paths. Out-of-scope files (`.claude/...`, etc.) are not in the File List → will not be staged at Step 2.6.

**Verdict:** ✅ PASS.

**§5.11.b — Production-only test-to-code ratio:**

Story 9-10 modifies zero production source files (`mailbot_api/*` unchanged; `hermes-config/skills/mailbot/SKILL.md` is docs per the classifier; `_bmad-output/*` is docs). The ratio computation has `prodAddedExcludingDocs = 0`, making the ratio `null`.

**Verdict:** N/A — story is meta-tooling + docs only; production code unchanged.

**§5.11.c — No-later-commits-under-attribution:**

```
$ git log --since="2026-06-26" --oneline -- ...
(empty — single-session dev pass)
```

**Verdict:** ✅ PASS.

### 5.12 — CR-cadence-mandatory surface classification

**Story surface classification:**

- **Criterion 1 (boundary-introducing):** NO — new test + new fixture; no new writer monopoly / lint boundary / shared invariant. The drift test consumes the existing MCP-registry surface + SKILL.md surface; it does not introduce a new invariant for downstream code.
- **Criterion 2 (dep-introducing):** NO — uses only existing stdlib `re` + `pathlib` + `pytest` + already-pinned `pyyaml`.
- **Criterion 3 (dev-self-flagged):** NO — section 4 has zero ESCALATE-TO-REVIEWER items; 5 findings all dispositioned FIX NOW (1) / DOCUMENT (2) / ACCEPT WITH RATIONALE (2).
- **Criterion 4 (capstone):** NO — Story 9-4 was the load-bearing capstone of the `/model` surface tranche; Story 9-10 is a follow-up coverage hardening. The benchmark tranche (9-5..9-9, 9-11) remains parked.
- **Criterion 5 (privacy-invariant):** NO — drift test is meta-tooling, no FR-2.5 / NFR-PRIV-* surface touched. The new SKILL.md sections describe `ack_notification` / `pull_pending_notifications` / `compose_digest` / `finalize_digest_delivery` / `unmute_category` — none of these expose privacy-relevant state.
- **Criterion 6 (load-bearing-orchestrator):** NO — the test never runs in production; it's CI-only. The drift detection IS the load-bearing function, but the audit surface is meta-tooling, not a production integration point.

**Cadence verdict: GATE-COVERAGE-ELIGIBLE** — no criterion fires.

Per the autonomous-epic-run cadence binding (Step 2.4): CR-subagent dispatch is **OPTIONAL** for this story. The orchestrator MAY skip given context-budget context; the four gates (ruff / mypy / boundary / pytest, all green at 1377+2+3) ARE the evidence for `done`. Orchestrator decision will be recorded in the Completion Notes at Step 2.4.8.

---

## Posture Audit summary table

| Check                                                       | Status                                       |
| ----------------------------------------------------------- | -------------------------------------------- |
| 5.1 Lockfile hygiene                                        | ✅ PASS                                      |
| 5.2 Cross-doc pair verification                             | ✅ PASS                                      |
| 5.3 Lifecycle string-uniqueness                             | N/A — story added zero i18n keys             |
| 5.4 Multi-consumer impact scan                              | ✅ PASS                                      |
| 5.5 Screenshot-based perception check                       | N/A — no graphical frontend                  |
| 5.6 Upstream-contract spec coverage                         | ✅ PASS                                      |
| 5.7 Module-level mutable container                          | ✅ PASS                                      |
| 5.8 Dev-fixture seed-vs-production-shape parity             | ✅ PASS                                      |
| 5.9 grep-verify-cited-figures                               | ✅ PASS                                      |
| 5.10 Producer-boundary contract enforcement                 | N/A — zero production code paths            |
| 5.11 Git-evidence consistency check                         | ✅ PASS (§5.11.b N/A — no prod code)         |
| 5.12 CR-cadence-mandatory surface classification            | **GATE-COVERAGE-ELIGIBLE**                   |
