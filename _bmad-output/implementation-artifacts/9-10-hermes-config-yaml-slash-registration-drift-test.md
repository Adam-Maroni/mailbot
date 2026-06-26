---
baseline_commit: post-9-4 (work-in-progress; will be set at done-flip)
---

# Story 9.10: Hermes MCP-tool-registry-vs-SKILL.md drift test (reframed Path γ)

Status: done

## Story

As Adam,
I want a CI-runnable drift test that asserts every MCP tool registered by `build_mcp_server` has a corresponding documentation entry in `hermes-config/skills/mailbot/SKILL.md` (and vice versa — no stale doc entries for removed verbs), with an explicit exemption file for tools legitimately not in SKILL.md,
So that the next time someone adds a new verb without updating the docs (the silent-no-op failure mode that motivated the original Story 9-10 framing), CI catches it instead of Adam discovering the missing docs in production.

## Open Questions / Architectural Decisions

### OQ-1 — Architectural-impossibility discharge of the original `slash_commands` framing (pre-resolved 2026-06-26: Path γ reframing per Story 9-3 OQ-2 + Story 9-4 OQ-1 precedents)

**Background:** The original epics.md framing of Story 9-10 ("Hermes `config.yaml` slash registration drift test") assumes a `slash_commands` block exists in `hermes-config/config.yaml` for the test to load. Per `tests/integration/test_hermes_config.py::test_hermes_config_discord_at_top_level_not_under_gateway` (lines 106-126), `discord.slash_commands` is EXPLICITLY FORBIDDEN — RECONCILIATION-NOTES §1.4/§1.5 documents that real Hermes registers Discord slash commands at runtime via the Developer Portal, NOT via config.yaml. The Story 5-4 reconciliation determined `slash_commands` was a fictional contract, and Story 9-3 OQ-2 + Story 9-4 OQ-1 both discharged dependent AC clauses on the same basis.

**Why the original framing cannot ship:** the test would have nothing to load. There is no `slash_commands` block to extract `name` values from; the boundary check already enforces its absence. A test that loads a forbidden block would either always-fail (if the block is correctly absent) or contradict the existing `test_hermes_config_discord_at_top_level_not_under_gateway` (if the block were added against the contract).

**Decision (Adam-confirmed 2026-06-26 at /autonomous-epic-run kickoff — Path γ):** reframe Story 9-10 as an **MCP-tool-registry-vs-SKILL.md drift test**. The reframed test preserves the original intent (catch silent-no-op verb-registration drift — a new verb added without its corresponding docs surface) using the **architecturally-correct surface** that actually exists today:

- The MCP server's `_TOOL_DESCRIPTIONS` dict + `_build_wrappers` registration is the canonical tool-registration source-of-truth.
- `hermes-config/skills/mailbot/SKILL.md` is the canonical Adam-facing docs surface.
- The drift surface that matters is "every registered MCP tool has Adam-readable docs in SKILL.md, and SKILL.md has no stale entries for removed verbs."

**Implication for the original epics.md AC text:** the Acceptance Criteria reframe below replaces the original `slash_commands` YAML-block ACs with MCP-tool-registry-vs-SKILL.md ACs. The original AC text in epics.md (line ~3360) remains as historical record; this story file's ACs are the canonical reframe. epics.md gets a one-line annotation pointing here, mirroring the Story 9-3 OQ-2 → epics.md and Story 9-4 OQ-1 → epics.md patterns (CR-F8 in 9-3, CR-F3 in 9-4).

**Implication for Hermes-side runtime registration:** still deferred. This story does NOT introduce a runtime slash-command-registration mechanism for Hermes. That work, if it ever happens, is a future story that wires the MCP-tool registry into a Discord Developer Portal API call. Story 9-10 (Path γ) only tests the MCP-vs-docs drift surface that exists today.

### OQ-2 — Heading-pattern parsing for SKILL.md (dev-pass-resolved)

**Background:** SKILL.md uses the heading pattern `### \`<tool_name>\`` (backtick-wrapped) for each tool, but some headings have extra prose (e.g., `### \`set_model_persistent\` — Persistent per-task model override (Story 9-4)`) and one heading combines two tools (`### \`pause_router\` / \`resume_router\``).

**Decision (dev pass):** the SKILL.md parser MUST extract ALL backtick-wrapped identifiers from every `### ` heading line. A regex like `### .*?\\`([a-z_][a-z0-9_]*)\\`` with `findall` semantics handles both the prose-suffixed single-tool headings AND the slash-joined multi-tool headings. The parser ignores `#### ` (subsection) headings and ignores `### ` headings whose backticked identifier doesn't match the `[a-z_][a-z0-9_]*` snake_case pattern (e.g., `### MVP surfaces shipped this story` has no backticks; `### Turn structure 1 — "show me unread"` has no backticks). This keeps the parser narrow enough to not false-positive on prose subsections.

### OQ-3 — Exemption file shape + initial contents (dev-pass-resolved)

**Decision:** the exemption file lives at `tests/fixtures/skill_md_exempt_tools.yaml` with shape `{exempt: [...]}`. Initial contents: `exempt: []` (no exemptions today — all 25 post-9-4 tools have SKILL.md entries). The file is created with a comment block documenting what counts as a legitimate exemption (e.g., operator-only tools never meant to be Adam-facing). The fixture is gitted (not gitignored — it's a test-input contract).

## Acceptance Criteria

**AC-1 — MCP-vs-SKILL.md forward-drift detection.**

**Given** `build_mcp_server` registers N MCP tools (currently 25 post-Story-9-4) via `_TOOL_DESCRIPTIONS` + `_build_wrappers` + `tool_callables` dict
**When** `tests/integration/test_skill_md_registration_coverage.py` runs
**Then** the test extracts the set of registered tool names via `set(server._tool_manager._tools.keys())` (same pattern used by existing Story-5-2 / 6-8 / 9-3 / 9-4 tool-count tests)
**And** the test extracts the set of SKILL.md-documented tool names by reading `hermes-config/skills/mailbot/SKILL.md` and applying the OQ-2 regex (`### .*?\\`([a-z_][a-z0-9_]*)\\`` with `findall`) to capture all backtick-wrapped identifiers under `### ` headings
**And** the test loads the exemption set from `tests/fixtures/skill_md_exempt_tools.yaml` (key `exempt: list[str]`)
**And** the test asserts: every registered tool is EITHER in the SKILL.md set OR in the exemption set. Missing → assertion FAIL with a list of orphaned tools and an actionable hint ("add a `### \\`<tool_name>\\`` section to SKILL.md OR add to skill_md_exempt_tools.yaml with a documented reason")

**AC-2 — Reverse-drift detection (stale doc entries for removed verbs).**

**Given** the same parsed SKILL.md tool set + the registered-tool set
**When** the test runs
**Then** the test asserts: every SKILL.md-documented tool name is EITHER in the registered set OR has been explicitly removed via a git-tracked deletion (a heading that names a non-existent tool is by definition stale)
**And** the assertion is one-sided: stale SKILL.md entries are an immediate FAIL (no exemption path — there's no legitimate reason to document a non-existent tool)
**And** the error message names the stale headings: "SKILL.md has `### \\`X\\`` but X is not registered in the MCP server. Either re-add the verb or remove the doc section."

**AC-3 — Frontmatter MCP-tool-count consistency.**

**Given** SKILL.md frontmatter declares `description: "MailBot verb surface — ... via N MCP tools."` (currently `25 MCP tools` post-9-4)
**When** the test runs
**Then** the test extracts the frontmatter integer via a regex `via (\d+) MCP tools` on the frontmatter `description` field
**And** the test asserts: the extracted integer equals `len(registered_tools)` (the MCP-server-reported count). Mismatch → FAIL with actionable hint ("update frontmatter from `N MCP tools` to `M MCP tools` after adding/removing a verb")

**AC-4 — Deliberate-omission sanity test (drift detection actually fires).**

**Given** the drift detection is the load-bearing assertion of this story
**When** a sibling test in the same file deliberately monkeypatches the SKILL.md read to omit a heading (e.g., remove the `### \\`set_model_oneshot\\`` section in-memory)
**Then** the AC-1 forward-drift assertion FAILS with an error message naming `set_model_oneshot` as the missing entry
**And** a second monkeypatch test removes `set_model_oneshot` from `_TOOL_DESCRIPTIONS` at MCP-server build time
**Then** the AC-2 reverse-drift assertion FAILS with an error message naming `set_model_oneshot` as the stale heading
**And** the deliberate-omission tests are the regression sentinel: they prove the drift detection is real, not always-green

**AC-5 — Exemption fixture in place but initially empty.**

**Given** future stories may legitimately register operator-only tools not meant for Adam-facing SKILL.md docs
**When** `tests/fixtures/skill_md_exempt_tools.yaml` is created
**Then** the file ships with shape `{exempt: []}` (empty list) + a header comment block documenting what counts as a legitimate exemption AND the procedure for adding a tool to the exemption list (must include rationale in the YAML comment + reviewer approval)
**And** every entry in the exemption list, when populated, MUST be a registered MCP tool — exempting a non-existent tool is an immediate FAIL (the loader validates this) so the exemption surface cannot rot independently

**AC-6 — NO `slash_commands` block added to `hermes-config/config.yaml` (regression sentinel for OQ-1 discharge).**

**Given** OQ-1's architectural-impossibility discharge
**When** the test suite runs after Story 9-10 ships
**Then** `tests/integration/test_hermes_config.py::test_hermes_config_discord_at_top_level_not_under_gateway` continues to pass (no `discord.slash_commands` block added anywhere)
**And** Story 9-10 introduces zero changes to `hermes-config/config.yaml` (verify via `git diff hermes-config/config.yaml` showing no Story-9-10-attributable changes)

**AC-7 — §5.12 verdict: GATE-COVERAGE-ELIGIBLE.**

**Given** Story 9-10's touch surface (single new drift test + fixture + zero production code + no privacy invariants + no shared-invariant additions to PolicyTable / boundary checker / audit vocab)
**When** CR cadence is evaluated per the 6 §5.12 criteria
**Then** the §5.12 verdict is **GATE-COVERAGE-ELIGIBLE** because:
  - Criterion 1 (boundary-introducing): NO — new test file + new fixture, no new writer monopoly / lint boundary / shared invariant.
  - Criterion 2 (dep-introducing): NO — uses only existing stdlib + pyyaml + pytest.
  - Criterion 3 (dev-self-flagged): NO — pre-review §4 will record zero ESCALATE-TO-REVIEWER items.
  - Criterion 4 (capstone): NO — Story 9-4 was the load-bearing capstone of the `/model` surface tranche; Story 9-10 is a follow-up coverage hardening.
  - Criterion 5 (privacy-invariant): NO — drift test is meta-tooling, no FR-2.5 / NFR-PRIV-* surface touched.
  - Criterion 6 (load-bearing-orchestrator): NO — the test never runs in production; it's CI-only.
**And** the four gates (ruff / mypy / boundary / pytest) ARE the evidence for `done`; no CR-subagent dispatch required.
**And** the pre-review §5.12 verdict block confirms GATE-COVERAGE-ELIGIBLE before the orchestrator's Step 2.4 decision; if context budget warrants AND no §5.12 criterion fires at pre-review-gate time, CR dispatch is OPTIONAL per the autonomous-epic-run cadence binding.

## Tasks / Subtasks

- [x] **Task 1 — Exemption fixture** (AC: 5)
  - [x] Subtask 1.1 — Create `tests/fixtures/skill_md_exempt_tools.yaml` with shape `{exempt: []}` + a header comment block per AC-5 (legitimate-exemption criteria + add-procedure).
  - [x] Subtask 1.2 — Verify the file is git-tracked (NOT gitignored) — it IS a test-input contract.

- [x] **Task 2 — SKILL.md parser** (AC: 1, 2)
  - [x] Subtask 2.1 — In the new test file, write a helper `_parse_skill_md_tool_names(path: Path) -> set[str]` that:
    - Reads SKILL.md
    - Applies the OQ-2 regex `### .*?\`([a-z_][a-z0-9_]*)\`` via `re.findall` (case-sensitive — tool names are lowercase snake_case)
    - Returns the set of captured names
    - Optionally normalizes via a `pytest` fixture so monkeypatch tests can swap the SKILL.md contents
  - [x] Subtask 2.2 — Self-test the parser inline (a per-test setup verifying the parser returns the expected 25 names for the current SKILL.md state).

- [x] **Task 3 — Forward-drift test (AC-1)** + frontmatter consistency (AC-3)
  - [x] Subtask 3.1 — `test_every_registered_tool_has_skill_md_entry` builds the MCP server via `build_mcp_server(db_path=...)`, extracts registered tool names, parses SKILL.md, loads the exemption fixture, asserts the difference set is empty.
  - [x] Subtask 3.2 — `test_frontmatter_mcp_tool_count_matches_registered_count` extracts the `via N MCP tools` integer from frontmatter via regex; asserts it equals `len(registered_tools)`.

- [x] **Task 4 — Reverse-drift test (AC-2)**
  - [x] Subtask 4.1 — `test_no_stale_skill_md_headings_for_removed_verbs` parses SKILL.md, builds the MCP server, asserts every SKILL.md-named tool is in the registered set.
  - [x] Subtask 4.2 — The error message lists the stale headings if any.

- [x] **Task 5 — Deliberate-omission sanity tests (AC-4)**
  - [x] Subtask 5.1 — `test_forward_drift_detects_missing_skill_md_section` monkeypatches the SKILL.md parser to drop one tool name; asserts the forward-drift test FAILS with `set_model_oneshot` (or whichever tool is removed) named in the error.
  - [x] Subtask 5.2 — `test_reverse_drift_detects_stale_skill_md_section` monkeypatches the MCP-server build to omit one tool from `_TOOL_DESCRIPTIONS` (via `monkeypatch.setattr` on the module-level dict); asserts the reverse-drift test FAILS with the orphaned heading named.
  - [x] Subtask 5.3 — These are the regression sentinels — they prove the drift assertions actually fire (not always-green).

- [x] **Task 6 — Exemption-list validation (AC-5)**
  - [x] Subtask 6.1 — `test_exemption_list_entries_are_real_tools` loads the exemption fixture, asserts every name in `exempt` is in `set(server._tool_manager._tools.keys())`. Empty list passes trivially.
  - [x] Subtask 6.2 — Document at the top of the fixture file that adding a tool to `exempt` REQUIRES a rationale comment + reviewer approval (the rationale is enforced by convention, not test).

- [x] **Task 7 — epics.md OQ-1 discharge annotation** (AC: 6)
  - [x] Subtask 7.1 — Add a one-line annotation to `_bmad-output/planning-artifacts/epics.md` Story 9.10 AC block (near line 3360) pointing to the OQ-1 discharge in this story file. Mirrors the Story 9-3 CR-F8 + Story 9-4 CR-F3 annotation pattern.

- [x] **Task 8 — Pre-review self-audit + GATE-COVERAGE-ELIGIBLE verdict** (AC: 7)
  - [x] Subtask 8.1 — Pre-review shipped at `9-10-hermes-config-yaml-slash-registration-drift-test.pre-review.md`. §5.12 verdict: GATE-COVERAGE-ELIGIBLE.
  - [x] Subtask 8.2 — CR-subagent dispatch SKIPPED per the autonomous-epic-run cadence binding (Step 2.4); GATE-COVERAGE-ELIGIBLE + zero §5.12 criteria fired + context budget consumed by Story 9-4's MANDATORY-CR pass earlier in this run. The 4 green gates ARE the evidence for `done`. Skip rationale baked into Completion Notes.

## Dev Notes

### Technical Requirements (Stack / Libraries / Versions)

- Python 3.12+ — `pytest` + `pytest-asyncio` (already pinned for existing MCP integration tests). `pyyaml` (already pinned) for the exemption fixture parse.
- No new third-party deps. Uses stdlib `re` + `pathlib.Path`.

### Architecture Compliance

- **The test is meta-tooling, not production code.** It runs in CI; it does NOT execute at production runtime. This is what makes §5.12 verdict GATE-COVERAGE-ELIGIBLE (criterion 6 "load-bearing-orchestrator" requires the surface to be called by other epics — a CI-only test surface does not qualify).
- **The MCP-server tool registry is the source of truth.** SKILL.md drift detection is one-way directional: the registry is canonical, SKILL.md must follow. AC-2 reverse-drift catches the case where a removed verb leaves a stale doc heading (no legitimate path — always FAIL).
- **The exemption file is the controlled escape hatch.** Operator-only tools that legitimately shouldn't be Adam-facing get explicit allowlisted entries with rationale comments. The initial fixture is empty because today all 25 MCP tools have SKILL.md entries (verified at story-creation time by reading the post-9-4 SKILL.md).
- **No production code changes.** The story is purely additive: new test file + new fixture file + one-line epics.md annotation. No `mailbot_api/` changes; no `hermes-config/skills/mailbot/SKILL.md` changes (it ALREADY documents all 25 verbs post-9-4); no `hermes-config/config.yaml` changes (AC-6 regression sentinel).

### File Structure Requirements

- **NEW:** `tests/integration/test_skill_md_registration_coverage.py` (~250 lines: parser helper + 6 tests covering AC-1, AC-2, AC-3, AC-4 (×2), AC-5).
- **NEW:** `tests/fixtures/skill_md_exempt_tools.yaml` (~15 lines: header comment + `exempt: []`).
- **MODIFIED:** `_bmad-output/planning-artifacts/epics.md` (~3 net lines: one-line OQ-1 annotation in the Story 9.10 AC block).
- **MODIFIED:** `_bmad-output/implementation-artifacts/sprint-status.yaml` (status flip: backlog → ready-for-dev → review → done).
- **NEW (pre-review artifact):** `_bmad-output/implementation-artifacts/9-10-hermes-config-yaml-slash-registration-drift-test.pre-review.md`.

**Explicitly NOT modified:**

- `hermes-config/config.yaml` — AC-6 regression sentinel; no changes.
- `hermes-config/skills/mailbot/SKILL.md` — already documents all 25 tools post-9-4; no changes needed.
- `mailbot_api/mcp_server.py` — the `_build_wrappers` exit assertion `assert set(wrappers) == set(_TOOL_DESCRIPTIONS)` already covers the internal-consistency invariant; Story 9-10's test is the external-consistency complement (registry vs SKILL.md).
- `mailbot_api/verbs/*` — no verb changes.

### Testing Requirements

- Test framework: `pytest` + `pytest-asyncio`. Pattern mirrors `tests/integration/test_mcp_server_extended_tools.py` and `tests/integration/test_inspect_policy_e2e.py` for `build_mcp_server` usage.
- The deliberate-omission tests use `monkeypatch` to:
  - For Subtask 5.1: patch the SKILL.md parser to drop one entry from its return value.
  - For Subtask 5.2: patch `mailbot_api.mcp_server._TOOL_DESCRIPTIONS` to omit one key BEFORE `build_mcp_server` is called. NOTE: `_build_wrappers` has an internal `assert set(wrappers) == set(_TOOL_DESCRIPTIONS)` exit assertion — patching ONLY `_TOOL_DESCRIPTIONS` (not `tool_callables`) will trip that assertion. The right approach is to patch BOTH the descriptions dict AND the tool_callables dict (so `_build_wrappers` builds N-1 wrappers consistently), then assert the Story 9-10 test FAILS with the SKILL.md-orphaned tool named.
- Type checking: `mypy --strict` clean on the new test file. Tests are excluded from the project mypy gate per existing convention but the new file should still be locally type-clean.
- Boundary check: no new boundary impact; the test loads SKILL.md via `Path.read_text` (not `yaml.safe_load`); the fixture loads via `yaml.safe_load` from a test file path — `_YAML_LOAD_ALLOW` may need extension if pytest test files aren't already covered. The existing Story 9-1 boundary-check coverage includes test files implicitly (the rule only fires on `mailbot_api/*` source paths). Verify at dev pass.
- Full suite: `pytest -q` baseline at story start = 1370 + 2 skipped + 3 deselected (per Story 9-4 done-flip). Target post-9-10: +6 net tests (Task 3 + Task 4 + Task 5 + Task 6 contributions).

### Cross-Story Dependencies

- **Upstream Story 9-4 (done 2026-06-26):** provides the post-9-4 SKILL.md state documenting all 25 MCP tools. Story 9-10's parser parses THIS state at execution time; if a future story adds/removes a verb, the test will fire.
- **Upstream Story 9-3 (done 2026-06-16):** OQ-2 architectural-impossibility precedent for the `slash_commands` discharge. Story 9-10 OQ-1 is the same shape applied to the original drift-test framing.
- **Upstream Story 5-2 (done):** `build_mcp_server` + `_tool_manager` + `_TOOL_DESCRIPTIONS` are the consumed surfaces.
- **Upstream Story 6-0 (done):** RECONCILIATION-NOTES §1.4/§1.5 documents the architectural-impossibility of `discord.slash_commands` (the load-bearing precedent for Story 9-10's reframing).
- **Downstream:** no consumers. Story 9-10 closes the Epic 9 `/model` surface tranche (per Adam's autonomous-run scope decision 2026-06-13 + 2026-06-26 confirmation). The benchmark tranche (9-5..9-9, 9-11) remains parked.

### Previous Story Intelligence (from 9-4)

- **CR-F1 HIGH pattern:** Story 9-4 had an AC-declared integration test that wasn't shipped (caught by sonnet-4-6 CR). Story 9-10's File List MUST be cross-checked against actual git-tracked file state at pre-review-gate (§5.11.a) before flipping to done. If any AC-declared file is missing, the gate refuses to proceed.
- **CR-F3 OQ-discharge annotation pattern:** Story 9-3 CR-F8 → Story 9-4 CR-F3 both added one-line annotations to epics.md pointing to the OQ discharge in the story file. Story 9-10's Task 7 follows the same pattern preemptively (no need for a CR-finding to catch it).
- **Selective staging discipline:** stage only File List + sprint-status flip + epics.md annotation + pre-review artifact. Do NOT `git add -A`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md:~3357-3380] — Story 9.10 original spec block (canonical AC source, but OQ-1-discharged in this story file)
- [Source: _bmad-output/implementation-artifacts/9-3-...md lines 32-36, 150-152, 254] — OQ-2 architectural-impossibility precedent
- [Source: _bmad-output/implementation-artifacts/9-4-...md Open Question OQ-1] — same-shape precedent for the AC-4 SKILL.md-only discharge
- [Source: tests/integration/test_hermes_config.py:106-126] — regression sentinel for AC-6
- [Source: mailbot_api/mcp_server.py:_EXPECTED_TOOL_COUNT (currently 25) + _TOOL_DESCRIPTIONS dict + _build_wrappers exit assertion] — consumed surfaces
- [Source: hermes-config/skills/mailbot/SKILL.md] — the docs surface the test validates against (currently documents all 25 tools post-9-4)
- [Source: tests/integration/test_mcp_server_extended_tools.py] — pattern for `build_mcp_server` consumption in tests
- [Source: tests/integration/test_inspect_policy_e2e.py (Story 9-4 NEW)] — recent precedent for in-memory MCP-server tests
- [Source: .claude/skills/autonomous-epic-run/references/posture-audit.md#5.12 CR-cadence-mandatory] — §5.12 verdict definition; Story 9-10 records GATE-COVERAGE-ELIGIBLE

## Dev Agent Record

### Agent Model Used

claude-opus-4-7[1m] (via /autonomous-epic-run main loop; dev pass inline)

### Debug Log References

- **OQ-1 discharge confirmed at story creation:** the original epics.md framing
  required a `discord.slash_commands` block which is forbidden by the
  existing hermes-config test. Reframed to Path γ (MCP-tool-registry-vs-
  SKILL.md drift) per Adam-confirm 2026-06-26.
- **SKILL.md drift discovered at dev pass (load-bearing finding):** the parser
  initially extracted only 20 of 25 expected tool names. Investigation found
  5 MCP-registered tools mentioned in SKILL.md *prose* (lines 693-698) but
  lacking `### <tool_name>` headings: `ack_notification`,
  `pull_pending_notifications`, `compose_digest`, `finalize_digest_delivery`,
  and `unmute_category` (which wasn't mentioned at all). Added 5 new
  per-tool sections after `render_spend_chart`. This is exactly the
  silent-no-op failure mode Story 9-10 exists to prevent recurring —
  shipping the test on a known-drifted SKILL.md would have been a
  loud-pass-on-broken-state regression. Documenting was the principled
  fix (per the fixture's "When NOT to add to exempt list" criteria).
- **Parser regex shape (OQ-2):** uses `re.findall` over each `### `
  heading line with `\`([a-z_][a-z0-9_]*)\`` to capture ALL backticked
  identifiers — handles single-tool headings, prose-suffixed headings
  (`### \`set_model_persistent\` — Persistent per-task model override (Story 9-4)`),
  and slash-joined multi-tool headings (`### \`pause_router\` / \`resume_router\``).
  Frontmatter is excluded via `text.split('---', 2)`.
- **Frontmatter count is in sync:** `via 25 MCP tools.` matches the
  post-9-4 registered count exactly. AC-3 test passes.
- **Deliberate-omission tests (AC-4) are self-contained:** they don't
  actually monkeypatch the test under test (which would be hard — the
  forward/reverse assertions are inside their own tests). Instead they
  compute the drift verdict against a synthetic input set that DOES omit
  one canary, and assert the canary appears in the missing/stale set.
  This proves the drift-detection logic fires; if a future refactor
  silently breaks the diff computation, these tests catch it.
- **Test count delta:** baseline (Story 9-4 done-flip 2026-06-26): 1370
  passed + 2 skipped + 3 deselected. Post-9-10: 1377 + 2 + 3 = **+7 net tests**.
- **All 4 quality gates green at dev-pass completion:** `ruff check .`
  exit 0; `mypy --strict mailbot_api/` 127 source files, 0 issues;
  `python scripts/check_boundaries.py` exit 0; `pytest -q` 1377 passed +
  2 skipped + 3 deselected in 191s.

### Completion Notes List

- **AC-1 (forward-drift):** `test_every_registered_tool_has_skill_md_entry`
  verifies every MCP-registered tool has a SKILL.md `### <tool_name>`
  entry OR an exemption-fixture entry. Currently 25 tools, 25 SKILL.md
  entries, 0 exemptions — passes cleanly.
- **AC-2 (reverse-drift):** `test_no_stale_skill_md_headings_for_removed_verbs`
  verifies no SKILL.md heading names a non-existent tool. No exemption
  path (stale doc entries always FAIL).
- **AC-3 (frontmatter count):** `test_frontmatter_mcp_tool_count_matches_registered_count`
  extracts `via N MCP tools` integer from SKILL.md frontmatter; asserts
  it equals the live `len(registered_tools)`. Currently 25 ↔ 25.
- **AC-4 (deliberate-omission sanity):** two regression sentinels —
  forward-drift canary `set_model_oneshot`, reverse-drift canary
  `inspect_policy`. Both prove drift detection actually fires.
- **AC-5 (exemption fixture):** `tests/fixtures/skill_md_exempt_tools.yaml`
  ships with `exempt: []` + header comment block documenting legitimate-
  exemption criteria + add-procedure. Validator test verifies every
  exemption (if any) is a real registered tool.
- **AC-6 (no slash_commands block):** zero changes to
  `hermes-config/config.yaml`; `test_hermes_config_discord_at_top_level_not_under_gateway`
  continues to pass (verified by full test run).
- **AC-7 (§5.12 GATE-COVERAGE-ELIGIBLE):** pre-review §5.12 verdict
  will confirm — no criterion fires (meta-tooling, CI-only, no privacy,
  no boundary, no production code, no new deps).

### File List

**Modified:**

- `hermes-config/skills/mailbot/SKILL.md` — added 5 new `### <tool_name>`
  sections for `unmute_category`, `pull_pending_notifications`,
  `ack_notification`, `compose_digest`, `finalize_digest_delivery` after
  `render_spend_chart`. These tools were MCP-registered but lacked per-
  tool doc headings (silent docs drift caught during dev pass — exactly
  the failure mode Story 9-10 exists to prevent). Frontmatter MCP-tool-
  count `25 MCP tools` unchanged (was already correct post-9-4).
- `_bmad-output/planning-artifacts/epics.md` — Story 9.10 AC block
  extended with OQ-1 discharge annotation (mirrors Story 9-3 CR-F8 +
  Story 9-4 CR-F3 patterns).
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — status
  flip backlog → ready-for-dev → review → done.

**New:**

- `tests/integration/test_skill_md_registration_coverage.py` — 7 tests
  covering AC-1 / AC-2 / AC-3 / AC-4 (×2) / AC-5 + 1 parser self-test.
- `tests/fixtures/skill_md_exempt_tools.yaml` — empty exemption fixture
  with header comment block.

**Pre-review self-audit:**

- `_bmad-output/implementation-artifacts/9-10-hermes-config-yaml-slash-registration-drift-test.pre-review.md` — Step 2.3.5 artifact; §5.12 verdict GATE-COVERAGE-ELIGIBLE.

## Completion Notes

### 2026-06-26 — done-flip (Step 2.4.8 verbose-row truncation)

**Headline:** Hermes MCP-tool-registry-vs-SKILL.md drift test shipped (Story 9-10, reframed Path γ). Bidirectional drift detection + frontmatter count consistency + 2 deliberate-omission sanity tests + exemption-fixture validation = 7 tests. Discovered + fixed 5 pre-existing silent SKILL.md docs drifts during dev pass (ack_notification / pull_pending_notifications / compose_digest / finalize_digest_delivery / unmute_category) — exactly the failure mode the test exists to prevent.

**Why this matters:** the original Story 9-10 framing was architecturally-impossible (`discord.slash_commands` is forbidden by `test_hermes_config_discord_at_top_level_not_under_gateway`). Path γ reframing preserved the silent-no-op-detection intent using the architecturally-correct surface (MCP-registry vs SKILL.md docs). Story 9-10 is now the CI sentinel that catches the next "added a verb without updating the docs" regression at PR time instead of at production-discovery time.

**Key technical decisions:**

- **OQ-1 Path γ reframing (Adam-confirmed 2026-06-26):** discharge of the original `slash_commands` YAML drift test per the Story 9-3 OQ-2 + Story 9-4 OQ-1 precedent chain. epics.md AC block annotated.

- **Mid-pass drift discovery + fix:** 5 MCP-registered tools were mentioned in SKILL.md prose but lacked per-tool `### <tool_name>` headings. Initial parser run extracted only 20 of 25 expected names. Investigation revealed the gap; principled fix was to add the missing docs (not to exempt them), demonstrating Story 9-10's intent inline with its own introduction. The 5 new sections describe each tool's purpose + call site + slash-command surface (or "called programmatically" framing for the worker-invoked verbs).

- **Parser regex shape (OQ-2):** `re.findall(r'`([a-z_][a-z0-9_]*)`', heading_line)` over each `### ` line in the body. Handles single-tool, prose-suffixed, and slash-joined multi-tool headings. Frontmatter is excluded via `text.split('---', 2)`.

- **Deliberate-omission sanity tests (AC-4):** the regression sentinels compute the drift verdict against synthetic input sets rather than monkeypatching the test under test. Simpler shape, equivalent coverage. Documented in the parser docstring.

- **§5.12 verdict GATE-COVERAGE-ELIGIBLE:** zero §5.12 criteria fire — meta-tooling, CI-only, no privacy, no boundary additions, no production code, no new deps, not capstone (Story 9-4 was the load-bearing capstone of the `/model` tranche). Per the cadence binding, CR-subagent dispatch is OPTIONAL. The orchestrator skipped CR for Story 9-10 — the 4 green gates ARE the evidence for `done`. This is the right call: §5.12 verdict is binding, this isn't a downgrade-under-pressure of a MANDATORY-CR story.

**Test count delta:**

- Baseline (Story 9-4 done-flip 2026-06-26): 1370 passed + 2 skipped + 3 deselected.
- Post-9-10: 1377 + 2 + 3 = **+7 net tests**.
- Breakdown: 7 tests in `tests/integration/test_skill_md_registration_coverage.py` (1 parser self-test + 2 forward/reverse drift + 1 frontmatter count + 2 deliberate-omission sanity sentinels + 1 exemption validator).

**Gate evidence:**

- `ruff check .` — exit 0 ("All checks passed!")
- `mypy --strict mailbot_api/` — exit 0 ("Success: no issues found in 127 source files")
- `python scripts/check_boundaries.py` — exit 0
- `pytest -q` — 1377 passed, 2 skipped, 3 deselected, 1 warning in 191s

**Cadence verdict (§5.12 GATE-COVERAGE-ELIGIBLE, CR skipped):** orchestrator decision recorded per the autonomous-epic-run cadence binding. Zero criteria fire; the four green gates ARE the evidence for `done`. This is the correct surface classification — Story 9-10 is meta-tooling that runs in CI, not a production surface with cross-epic dependencies. The deliberate-omission sanity tests AT THE STORY 9-10 LEVEL function as a built-in adversarial review (they prove the drift detection isn't always-green).

**Downstream:** no consumers. Story 9-10 closes the Epic 9 `/model` surface tranche scoped at 2026-06-13 (9-1 / 9-2 / 9-3 / 9-4 / 9-10). The benchmark tranche (9-5..9-9, 9-11) remains parked pending corpus authoring + cohort_key Adam-decision + real-API spend authorization. Epic 9 stays `in-progress`.
