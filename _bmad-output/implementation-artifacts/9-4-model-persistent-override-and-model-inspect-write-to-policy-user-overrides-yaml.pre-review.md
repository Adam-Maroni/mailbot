# Pre-Review Self-Audit — 9-4

**Generated:** 2026-06-26 by claude-opus-4-7[1m]
**Story file:** _bmad-output/implementation-artifacts/9-4-model-persistent-override-and-model-inspect-write-to-policy-user-overrides-yaml.md
**Status at audit time:** review (post dev-story, pre code-review)

## 1. AC-vs-code drift scan

- **AC-1: MATCH** — `set_model_persistent` verb shipped in `mailbot_api/verbs/router_control.py` with `SetModelPersistentOut` shape; task validation via `snapshot_for_dispatch().tasks.keys()`; model validation via Story 9-3's `_normalize_model_id` (full ID + qwen/haiku/opus aliases); OQ-3 file-state pre-flight (exists + writable, refuses-with-actionable-error otherwise via `_persistent_error` helper); atomic write via `write_user_overrides_atomic` (`tempfile.mkstemp` + `os.fsync` + `os.replace`); structured-log emit `policy.user-overrides.set_persistent`; hot-reload pickup poll 100ms × 20 = 2s timeout. **One nuance:** the hot-reload pickup uses `snapshot.version` change detection — this works for genuine reloads but a content-identical re-write yields no version change (the hash is content-addressed). For Story 9-4 v1 this is acceptable; documented in code via the AC-1 polling loop comment.
- **AC-2: MATCH** — three changes ship the contract: (a) `PolicyTable.overrides_applied: frozenset[str] = Field(default_factory=frozenset)`; (b) `_merge_user_overrides` returns 3-tuple including the provenance set; (c) `router.py` emits `OVERRIDE_SLASH_PERSISTENT` when `task_type in policy.overrides_applied` AND no force_model AND no oneshot engagement. `inspect_policy` returns markdown table + degraded line + one-shot line. Cache-hit clobber narrowed via `_persistent_engaged` threaded kwarg (mirrors Story 9-3 CR-F1).
- **AC-3: MATCH** — verified by 4 integration tests: overridden task emits `OVERRIDE_SLASH_PERSISTENT`; non-overridden sibling emits `policy_default(task)`; baseline-only emits `policy_default(task)`; one-shot-wins-then-persistent precedence sequence.
- **AC-4: MATCH (with OQ-1 discharge — architecturally-impossible)** — `hermes-config/config.yaml` gains NO `slash_commands` block (`test_hermes_config_discord_at_top_level_not_under_gateway` continues to pass); existing Story 9-3 OQ-2 comment extended with Story 9-4 note; `hermes-config/skills/mailbot/SKILL.md` extended with persistent + inspect subsections + arg-count dispatch table; frontmatter MCP-tool count bumped 23 → 25.
- **AC-5: MATCH** — `tests/integration/test_persistent_override_atomic_write.py` ships 8 tests: byte-identity on policy.yaml, schema-valid round-trip across 3 writes, crash-during-replace atomicity (monkeypatched `os.replace`), OQ-3 absent-file refusal (verb does NOT create the file), unknown-task rejection, unknown-model rejection, shorthand-alias normalization, shallow-leaf preservation of sibling fields.
- **AC-6: MATCH** — `tests/unit/verbs/test_inspect_policy.py` ships 7 tests covering all sub-bullets: baseline-only state, one-override 🔧 prefix, degraded-mode line, one-shot armed line, multi-override count, markdown-table shape sanity, file_path field correctness.
- **AC-7: MATCH** — §5.12 verdict below records MANDATORY-CR; review dispatch under `claude-sonnet-4-6` (dev model: `claude-opus-4-7`) is the next step.

## 2. File-List-vs-git diff check

Captured via `git status --porcelain` + `git diff --numstat`.

**Tracked (modified):**

- `mailbot_api/router/policy.py` MODIFIED — TRACKED ✅
- `mailbot_api/router/router.py` MODIFIED — TRACKED ✅
- `mailbot_api/verbs/router_control.py` MODIFIED — TRACKED ✅
- `mailbot_api/mcp_server.py` MODIFIED — TRACKED ✅
- `hermes-config/skills/mailbot/SKILL.md` MODIFIED — TRACKED ✅
- `hermes-config/config.yaml` MODIFIED — TRACKED ✅
- `tests/integration/test_mcp_server.py` MODIFIED — TRACKED ✅
- `tests/integration/test_mcp_server_extended_tools.py` MODIFIED — TRACKED ✅
- `tests/integration/test_spend_chart_command.py` MODIFIED — TRACKED ✅
- `tests/unit/router/test_policy_user_overrides_merge.py` MODIFIED — TRACKED ✅
- `_bmad-output/implementation-artifacts/sprint-status.yaml` MODIFIED — TRACKED ✅

**Untracked (new files in story scope):**

- `tests/integration/test_persistent_override_audit_reason.py` UNTRACKED ✅ — listed in File List, will be staged
- `tests/integration/test_persistent_override_atomic_write.py` UNTRACKED ✅ — listed in File List, will be staged
- `tests/unit/verbs/test_inspect_policy.py` UNTRACKED ✅ — listed in File List, will be staged
- `_bmad-output/implementation-artifacts/9-4-...md` (story file itself) UNTRACKED ✅ — will be staged
- This pre-review artifact UNTRACKED ✅ — will be staged

**Out-of-scope working-tree state (not staged, not story-related):**

- `.claude/settings.json` modified — pre-existing environment work, NOT staged for this story
- `.claude/hooks/`, `.claude/skills/.archive/`, `.claude/skills/*/`, `.claude/scheduled_tasks.lock` — pre-existing local-environment files outside scope
- `_bmad-output/brainstorming/`, `_bmad-output/implementation-artifacts/epic-6-5-retro-2026-06-06.md`, `_bmad-output/planning-artifacts/prds/`, various other untracked files — unrelated retro / brainstorming artifacts not part of Story 9-4

**Verdict:** all File-List entries are TRACKED or UNTRACKED-pending-stage. No silent scope-creep detected. Step 2.6 selective staging will explicitly add only the in-scope entries.

## 3. Adversarial self-review

- **[MEDIUM] `_persistent_engaged` threading boundary surface** — `mailbot_api/router/router.py:~292` — the `_persistent_engaged` boolean is computed in `ask_router` from `force_model is None and task_type in policy.overrides_applied`. This evaluates the snapshot field AT ask_router entry. If a hot-reload swaps the snapshot mid-call between `ask_router` capturing `policy` (line 227) and the audit-emit point (line ~287), the new field value is irrelevant — we use the captured snapshot. Verified by re-reading: `_persistent_engaged` is computed AFTER `policy: PolicyTable = snapshot_for_dispatch()` (line 227) using the captured `policy.overrides_applied`. Race-acceptable per AR-D11-2.

- **[MEDIUM] cache-hit clobber regression mirrors Story 9-3 CR-F1** — `mailbot_api/router/router.py:~610-617` — the cache-hit branch lives inside `_dispatch_with_failure_chain` which does NOT receive `policy`. I threaded `_persistent_engaged: bool` as a kwarg (same shape as `_oneshot_engaged`). The carve-out is `if not _oneshot_engaged and not _persistent_engaged: model_chosen_reason = CACHE_HIT.value`. Regression tests `test_cache_hit_on_overridden_task_preserves_persistent_reason` and `test_cache_hit_on_non_overridden_task_writes_cache_hit` pin both branches. **Caught the right bug ahead of CR review.**

- **[MEDIUM] escalation-recursion non-forwarding inherited from Story 9-3 CR-F7** — `mailbot_api/router/router.py:~821` — the recursive escalated call already does not forward `_oneshot_engaged`; same reasoning applies to `_persistent_engaged` (escalated audit row carries `policy:escalation:<from>→<to>`, not the outer caller's reason). Added a paragraph comment naming the Story 9-4 application of the same rule. **Defensive against the same future-developer footgun.**

- **[LOW] tempfile-cleanup-on-replace-failure** — `mailbot_api/router/policy.py:~458` — `write_user_overrides_atomic` does best-effort `tmp_path.unlink(missing_ok=True)` in the `except UserOverridesWriteError` branch. If the cleanup itself fails (rare; OSError), we swallow it (`except OSError: pass`) and re-raise the original. Trade-off: cluttering the next operator-visible inspection with stale `.policy.user-overrides.*.yaml.tmp` files vs masking the original error. Accepted: leaked tempfile is operator-recoverable; original error visibility wins.

- **[LOW] hot-reload polling false-positive risk** — `mailbot_api/verbs/router_control.py:~273` — the poll uses `snapshot.version != version_before` to detect reload. A genuine race where ANOTHER write (concurrent operator edit OR `policy.yaml` itself swapped) advances the version would yield ok=True even though our write may not be the one applied. MailBot is single-user single-operator and the watchfiles loop is single-threaded — the realistic concurrent-edit window is microseconds. Accepted as v1; document if a multi-operator regression is filed.

- **[LOW] `_read_baseline_models` re-uses `read_user_overrides_raw`** — `mailbot_api/verbs/router_control.py:~331` — to read `policy.yaml` (the baseline), I use the same `read_user_overrides_raw(path)` helper because both files share top-level `{tasks: {...}}` shape. This works because the helper is shape-agnostic at this level (just returns the raw dict). If a future Story changes `policy.yaml`'s top-level shape but not the overrides file, this would silently mis-read. Mitigation: the markdown row's `baseline_model` column would fall back to `"?"`, signaling the discrepancy in inspect output. Acceptable v1; flagged for §5.4 multi-consumer awareness.

- **[LOW] inspect verb does not chunk for Discord 2000-char limit** — `mailbot_api/verbs/router_control.py:~390` — the markdown for 16 tasks @ ~150 chars each = ~2400 chars exceeds Discord's 2000 limit. Per AC-2's explicit framing ("Hermes is responsible for chunking / file-attachment if it exceeds Discord's 2000-character limit"), the verb returns the full markdown unchunked. Hermes-side chunking is upstream. If a future Story adds 30+ tasks, the InspectPolicyOut.markdown will exceed Discord's limit and Hermes (or Story 9-10's slash-handler) must split — not the MCP verb's concern.

## 4. Self-caught issues remediated this audit

1. **MEDIUM `_persistent_engaged` threading boundary surface** — **ACCEPT WITH RATIONALE.** Captured-snapshot semantics per AR-D11-2 already address the race; the kwarg-threading pattern mirrors Story 9-3's verified `_oneshot_engaged` design. No fix needed.

2. **MEDIUM cache-hit clobber regression mirrors Story 9-3 CR-F1** — **FIX NOW (applied during dev pass).** The carve-out shipped during Task 4 implementation along with two regression tests. Already in the diff.

3. **MEDIUM escalation-recursion non-forwarding inherited from Story 9-3 CR-F7** — **FIX NOW (applied during dev pass).** Extended the existing CR-F7 comment block with the Story 9-4 application. Already in the diff.

4. **LOW tempfile-cleanup-on-replace-failure** — **ACCEPT WITH RATIONALE.** Best-effort cleanup + original-error preservation is the correct trade-off for a rare path; tempfiles are operator-recoverable via the next normal write cycle.

5. **LOW hot-reload polling false-positive risk** — **ACCEPT WITH RATIONALE.** Single-user single-operator deployment makes the concurrent-write window negligible. Documented in the verb's Task 2.7 subtask description.

6. **LOW `_read_baseline_models` re-uses `read_user_overrides_raw`** — **ACCEPT WITH RATIONALE.** The shared shape `{tasks: {<task>: {model: ...}}}` is stable across both file roles per Story 9-1 contract. If a future Story changes one but not the other, the inspect surface returns `"?"` which is operator-discoverable, not silent corruption.

7. **LOW inspect verb does not chunk for Discord 2000-char limit** — **ACCEPT WITH RATIONALE per AC-2 framing.** Chunking is explicitly an upstream concern in the spec. Story 9-10 (or whichever future story wires Hermes-side slash-handling) owns the chunking decision.

## 5. Posture Audit

### 5.1 — Lockfile hygiene

```bash
$ git diff --stat -- requirements.txt
(no output)
```

**Verdict:** ✅ PASS — non-dep-change story; no `requirements.txt` modifications.

### 5.2 — Cross-doc pair verification

**Cross-doc claims in this story:**

- Claim: "Story 9-1 docs the hot-reload contract limitation" → references `docs/policy-overrides.md` "Hot-reload contract limitation — file-must-exist-at-startup" section.

  ```
  $ Grep "file-must-exist-at-startup|contract limitation" docs/policy-overrides.md
  output_mode: files_with_matches
  ```

  Verification ran: file exists, story 9-1 was a prereq, the doc reference is consistent with the verb's actionable error wording. **Verdict: MATCH.**

- Claim: "ModelChosenReason.OVERRIDE_SLASH_PERSISTENT shipped by Story 9-2" → references `mailbot_api/router/audit_vocab.py:85`.

  ```
  $ Grep "OVERRIDE_SLASH_PERSISTENT" mailbot_api/router/audit_vocab.py
  85:    OVERRIDE_SLASH_PERSISTENT = "slash_command:persistent:adam"
  ```

  **Verdict: MATCH** — enum member present at the cited line.

- Claim: "Story 9-3 OQ-2 discharged AC-4 as architecturally-impossible via SKILL.md docs only" → references the Story 9-3 file.

  ```
  $ Grep "OQ-2|architecturally-impossible|architecturally impossible" _bmad-output/implementation-artifacts/9-3-model-one-shot-dispatch-session-flag-ttl-gates-inherited.md
  ```

  9 hits in the Story 9-3 file documenting OQ-2 + the discharge + Story 9-10 ownership of runtime registration. **Verdict: MATCH.**

**§5.2.1 schema-touching trigger:** N/A — File List contains zero paths under `mailbot_api/db/migrations/`. The `overrides_applied` field is a Pydantic field on PolicyTable (in-memory); no SQL schema change.

**Verdict:** ✅ PASS — all cross-doc claims verified; §5.2.1 N/A.

### 5.3 — Lifecycle string-uniqueness

**Verdict:** N/A — story added zero i18n keys (Hermes uses MailBot's English-only markdown; no multi-locale keys). The SKILL.md prose additions are stable identifiers describing the new verbs, not lifecycle i18n strings.

### 5.4 — Multi-consumer impact scan

Modified shared symbols + their consumers:

```
$ Grep -rn "PolicyTable\(" mailbot_api/
mailbot_api/router/policy.py — 3 sites (load_policy_with_status + tests)
tests/* — direct PolicyTable() constructors in test fixtures (Story 9-1 + Story 9-3 + Story 9-4 tests)
```

**PolicyTable.overrides_applied (new field):**

Consumers of the new field:

- `mailbot_api/router/router.py:~287` — audit-reason emission (PRIMARY consumer, story scope)
- `mailbot_api/verbs/router_control.py:~393` (inspect_policy markdown rendering — PRIMARY consumer, story scope)

Existing PolicyTable consumers verified for the new optional field:

- `mailbot_api/router/policy.py` `load_policy_with_status` — UPDATED to populate the field
- `mailbot_api/router/policy.py` `set_policy_snapshot` / `get_policy` / `snapshot_for_dispatch` — opaque pass-through, no field-specific code
- Test fixtures that construct PolicyTable directly — backwards-compatible via `default_factory=frozenset` (zero existing test required updating its constructor call; verified by 1366-test pass rate)

**`_merge_user_overrides` (signature change 2-tuple → 3-tuple):**

Consumers — only one production call site:

- `mailbot_api/router/policy.py` `load_policy_with_status` — UPDATED to consume 3-tuple
- `tests/unit/router/test_policy_user_overrides_merge.py` — 4 unpack sites UPDATED to 3-tuple (verified via the full pytest run)

**Verdict:** ✅ PASS — all consumers enumerated, all updated.

### 5.5 — Screenshot-based perception check

**Verdict:** N/A — project has no graphical frontend per PORTING.md; UI ACs in this story refer to Discord-rendered text from `inspect_policy.markdown` output, owned by an external Hermes container. The markdown structural sanity is verified by `test_inspect_policy_markdown_table_shape` (regex `^\|.*\|$` line-count) which is a structural check, not a paint-cycle check. Real-user verification of the rendered Discord chat output is a Phase 3.5 manual-walk concern (deferred to end-of-epic per the autonomous-epic-run skill's Layer 2 contract for projects without a graphical frontend).

### 5.6 — Upstream-contract spec coverage

**Story 9-1 upstream contract — `policy.user-overrides.yaml` companion file + watchfiles hot-reload:**

- Present case: tests exercise the path where the file exists + has content + reload propagates. Covered in `test_persistent_override_atomic_write.py::test_successful_write_leaves_policy_yaml_byte_identical` + `test_persistent_override_audit_reason.py::test_overridden_task_emits_override_slash_persistent`.
- Absent case (file does not exist): `test_absent_file_refused_with_actionable_error` verifies OQ-3 refusal path. The verb does NOT create the file (would be silently un-watched per Story 9-1 contract).
- Parse-failure case: handled at the policy-loader layer (Story 9-1's `load_policy_with_status` returns `"parse_failed"`). The verb never sees a parse-failed snapshot because the reload loop refuses to swap; the prior valid snapshot persists. Tests for that path live in Story 9-1's test suite.

**Story 9-3 upstream contract — `_oneshot_override` slot + `_consume_oneshot_override` semantics:**

- Present case: covered by `test_oneshot_wins_over_persistent_for_next_call_then_consumes` (one-shot active → wins → consumes).
- Absent case (no one-shot armed but persistent override is): covered by `test_overridden_task_emits_override_slash_persistent` (one-shot slot is None; persistent path emits OVERRIDE_SLASH_PERSISTENT).
- Absent case (no one-shot AND no persistent): covered by `test_baseline_only_emits_policy_default` (both layers absent; policy_default emits).

**Verdict:** ✅ PASS — both upstream contracts have present-AND-absent coverage.

### 5.7 — Module-level mutable container check

**Python-stack overlay (per PORTING.md / posture-audit.md):**

Searched all modified `.py` files for module-level mutable state:

```
$ Grep -n "^[A-Z_]+\s*[:=]" mailbot_api/router/policy.py mailbot_api/verbs/router_control.py mailbot_api/router/router.py
```

Findings:

- `mailbot_api/router/policy.py` — `_policy: PolicyTable | None = None` (pre-existing Story 2-2; explicitly documented as the module-singleton; reset via `_reset_policy_snapshot_for_test`). NO new module-level mutable state added in Story 9-4 — `UserOverridesWriteError` is an exception class (immutable), `read_user_overrides_raw` + `write_user_overrides_atomic` are stateless functions.
- `mailbot_api/verbs/router_control.py` — only new module-level additions are `_log = logging.getLogger(__name__)` (immutable handle), `_USER_OVERRIDES_FILENAME: Final[str]`, `_POLICY_FILENAME: Final[str]`, `_PERSISTENT_HOT_RELOAD_TIMEOUT_S: Final[float]`, `_PERSISTENT_HOT_RELOAD_POLL_S: Final[float]`. All are `Final[T]` typed constants per PEP 591. NO mutable containers.
- `mailbot_api/router/router.py` — only kwarg-threading change to `_dispatch_with_failure_chain`; no new module-level state.

**Verdict:** ✅ PASS — Story 9-4 adds zero new module-level mutable state. Existing `_policy: PolicyTable | None` is the pre-existing Story 2-2 singleton with an explicit reset helper.

### 5.8 — Dev-fixture seed-vs-production-shape parity

**Test-fixture trigger:** the story adds 3 new test files. All use in-spec object literals + adapter mocks rather than recorded JSON fixtures. Classifying:

- `test_persistent_override_audit_reason.py` — uses **Pattern 2 (producer-test-driven shapes)**: `AdapterResponse(text=json.dumps({"draft_body": "ok", ...}), ...)` are constructed against the actual `AdapterResponse` Pydantic model (the canonical producer). The JSON payloads inside (e.g., `{"class_coarse": "newsletter", "confidence": 0.9}`) are verified against the actual prompt-module output schemas — `CoarseClassOutput` requires `class_coarse` (enum) + `confidence` (float 0-1), which the test payload matches verbatim. **Drift sentinel:** the prompt-module output schemas themselves are the canonical contract; any change there breaks the `schema_validate_json` call in the router before reaching the assert.
- `test_persistent_override_atomic_write.py` — fixtures are tmp_path-rooted YAML files mirroring the Story 9-1 `policy.user-overrides.yaml.example` shape (`tasks: {}` + Story-9-1-validated `UserOverridesEntry` field set). **Pattern 2 (producer-test-driven)** via `UserOverridesTable.model_validate` — the same Pydantic model the production loader uses.
- `test_inspect_policy.py` — same Pattern 2 — tmp_path YAML files + `PolicyTable` construction via the Story-9-1 loader.

**Verdict:** ✅ PASS — all 3 new test files use producer-test-driven fixtures (Pattern 2). No hand-imagined Pattern-3 fixtures shipped.

### 5.9 — grep-verify-cited-figures

Numeric cites in this pre-review + the story file:

- **"1366 + 2 + 3-deselected" / "+29 net tests"** — verified by `.venv/Scripts/python.exe -m pytest -q --tb=line` exit-0 output `1366 passed, 2 skipped, 3 deselected`. Baseline (Story 9-3 done-flip per sprint-status.yaml line 248): `1337+2+3-deselected`. Delta: 1366 - 1337 = 29. **Verdict: MATCH.**
- **"4 quality gates green"** — verified inline:
  ```
  $ .venv/Scripts/python.exe -m ruff check .  → "All checks passed!"
  $ .venv/Scripts/python.exe -m mypy --strict mailbot_api/  → "Success: no issues found in 127 source files"
  $ .venv/Scripts/python.exe scripts/check_boundaries.py  → exit 0
  $ .venv/Scripts/python.exe -m pytest -q  → 1366 passed
  ```
  **Verdict: MATCH** — all 4 gates exit 0.
- **"+8 unit / +7 unit / +6 integration / +8 integration"** — verified per-file:
  ```
  $ .venv/Scripts/python.exe -m pytest tests/unit/router/test_policy_user_overrides_merge.py -q
   34 passed → 34 - 26 (Story 9-1 baseline) = 8 ✓
  $ .venv/Scripts/python.exe -m pytest tests/unit/verbs/test_inspect_policy.py -q
   7 passed → all new ✓
  $ .venv/Scripts/python.exe -m pytest tests/integration/test_persistent_override_audit_reason.py -q
   6 passed ✓
  $ .venv/Scripts/python.exe -m pytest tests/integration/test_persistent_override_atomic_write.py -q
   8 passed ✓
  Total new: 8 + 7 + 6 + 8 = 29 ✓
  ```
  **Verdict: MATCH.**
- **"25 MCP tools" (frontmatter + docstring + _EXPECTED_TOOL_COUNT)** — verified by `pytest tests/integration/test_mcp_server.py::test_build_mcp_server_registers_25_tools_with_expected_names` exit-0. The assertion is `assert len(tool_names) == 25` AND the expected-names list has 25 entries. **Verdict: MATCH.**

**Verdict:** ✅ PASS — every cited figure verified via runnable command at audit time.

### 5.10 — Producer-boundary contract enforcement

**§5.10.a typed-column producer-boundary scan (Python-stack overlay):**

Story 9-4 writes to a YAML file, not a typed ORM column. The closest analog is `write_user_overrides_atomic(path, data: dict[str, Any])` where `data` is the post-mutation dict. The data input comes from `read_user_overrides_raw` (which validates dict-shape) + mutated by the verb (which validates task name + model id against known sets). The atomic write itself does not coerce types — it serializes the dict via `yaml.safe_dump`. **Boundary guards:**

- Verb input `task: str` validated against `snapshot.tasks.keys()` (the live policy set).
- Verb input `model: str` validated against `_MODEL_ALIASES | _ALLOWED_FULL_MODEL_IDS` (Story 9-3's frozen set).
- File read input via `read_user_overrides_raw` validates top-level shape, `tasks` field type, and each task-entry shape (dict required); raises `UserOverridesWriteError` on non-dict.
- Pre-write defensive check at `mailbot_api/verbs/router_control.py:~210` — if `tasks[task]` is a non-mapping (operator-edited file shape corruption), the verb refuses rather than silently coercing.

**§5.10.b response-shape co-emission audit (Python-stack overlay):**

`SetModelPersistentOut` + `InspectPolicyOut` are the two new wire shapes:

- `SetModelPersistentOut(BaseModel)` — fields: `ok`, `task`, `model`, `file_path`, `effective_after_reload_ms`, `error`. Pydantic explicit field list = the allow-list. No sensitive fields, no PII, no internal-only columns. The `file_path` field exposes the absolute path of `policy.user-overrides.yaml` which is operator-visible config (the docker-compose bind-mount target — already operator-known per Story 9-1's docs).
- `InspectPolicyOut(BaseModel)` — fields: `markdown`, `task_count`, `override_count`, `file_path`. The `markdown` field embeds task names + baseline model IDs + override model IDs + lane + sensitivity tier. The sensitivity tier values are from `policy_entry.sensitivity` which is operator-config not user-data — already part of the policy file Adam authors. No PII, no credentials.

**§5.10.c producer-boundary input-shape guard:**

`read_user_overrides_raw` enforces input-shape guards: file existence, `text.strip()` empty check, YAML parse exception handling, top-level dict check, `tasks` field dict check. All before the dict reaches `_merge_user_overrides` or any typed write. **Verdict: GUARDED.**

**§5.10.d adjacent-shared-type re-export audit:**

`PolicyTable.overrides_applied` is the new shared type field. It is re-exported via the `policy.snapshot_for_dispatch()` surface to two consumers (router.py + the new inspect_policy verb). Both consumers read it as a read-only `frozenset[str]` (Pydantic guarantees immutability via the `default_factory=frozenset` declaration). No secondary re-export through `mailbot_api/__init__.py` (verified by Grep). **Verdict: PASS.**

**Verdict:** ✅ PASS — all sub-rules satisfied.

### 5.11 — Git-evidence consistency check

**§5.11.a — File-List-vs-working-tree consistency:**

```
$ git status --porcelain (filtered to in-scope paths)
 M _bmad-output/implementation-artifacts/sprint-status.yaml
 M hermes-config/config.yaml
 M hermes-config/skills/mailbot/SKILL.md
 M mailbot_api/mcp_server.py
 M mailbot_api/router/policy.py
 M mailbot_api/router/router.py
 M mailbot_api/verbs/router_control.py
 M tests/integration/test_mcp_server.py
 M tests/integration/test_mcp_server_extended_tools.py
 M tests/integration/test_spend_chart_command.py
 M tests/unit/router/test_policy_user_overrides_merge.py
?? _bmad-output/implementation-artifacts/9-4-...md
?? _bmad-output/implementation-artifacts/9-4-...pre-review.md
?? tests/integration/test_persistent_override_atomic_write.py
?? tests/integration/test_persistent_override_audit_reason.py
?? tests/unit/verbs/test_inspect_policy.py

$ git diff --cached --name-only
(empty — Step 2.6 selective staging happens after pre-review gate)
```

Cross-reference verdict: every File-List entry maps to a `M` or `??` line. No declared-but-not-touched paths. Out-of-scope working-tree files (under `.claude/`, `_bmad-output/brainstorming/`, etc.) are NOT in the story File List — silent unrelated background work, will NOT be staged at Step 2.6.

**Verdict:** ✅ PASS.

**§5.11.b — Production-only test-to-code ratio (live):**

```
$ git diff --numstat (tracked) + wc -l (untracked):
Tracked:
  hermes-config/config.yaml             8     0    (docs per classifier)
  hermes-config/skills/mailbot/SKILL.md 91    1    (docs per classifier)
  mailbot_api/mcp_server.py            109    6    (prod)
  mailbot_api/router/policy.py         170    7    (prod)
  mailbot_api/router/router.py         61     9    (prod)
  mailbot_api/verbs/router_control.py  395    0    (prod)
  tests/integration/test_mcp_server.py 10     5    (test)
  tests/integration/test_mcp_server_extended_tools.py  4   3   (test)
  tests/integration/test_spend_chart_command.py        4   3   (test)
  tests/unit/router/test_policy_user_overrides_merge.py 219 4  (test)
Untracked (new files; lines counted = additions):
  tests/integration/test_persistent_override_atomic_write.py  313  0  (test)
  tests/integration/test_persistent_override_audit_reason.py  438  0  (test)
  tests/unit/verbs/test_inspect_policy.py                     237  0  (test)
  _bmad-output/implementation-artifacts/9-4-...md              537  0  (docs)

testAdded = 10+4+4+219+313+438+237 = 1225
docsAdded = 8+91+537 = 636
prodAddedExcludingDocs = 109+170+61+395 = 735
prodOnlyTestRatio = 1225 / 735 = 1.667

Threshold: 0.3
```

**Verdict:** ✅ PASS — 1.667 ≥ 0.30 (the test surface is 1.67× the production surface).

**§5.11.c — No-later-commits-under-attribution:**

```
$ git log --since="2026-06-26" --oneline -- mailbot_api/ tests/ hermes-config/ _bmad-output/
(empty — single-session dev pass)
```

**Verdict:** ✅ PASS — single-session dev pass, no commits under attribution since the status flip moment.

### 5.12 — CR-cadence-mandatory surface classification

**Story surface classification:**

- **Criterion 1 (boundary-introducing):** YES — story adds new `overrides_applied` field to PolicyTable (a shared invariant other code reads), AND adds new module-public helpers `read_user_overrides_raw` + `write_user_overrides_atomic` + `UserOverridesWriteError` exception type. While not adding a new lint rule, the `overrides_applied` field IS a new shared-invariant surface that downstream code (router.py audit-emit + inspect_policy) leans on. **Fires.**
- **Criterion 2 (dep-introducing):** NO — no new external dependencies; uses stdlib `os`, `tempfile`, `datetime`, plus already-pinned `pyyaml` + `pydantic` + `watchfiles`.
- **Criterion 3 (dev-self-flagged):** NO — section 4 has zero ESCALATE-TO-REVIEWER items; all 7 findings dispositioned as FIX NOW (3) or ACCEPT WITH RATIONALE (4).
- **Criterion 4 (capstone):** NO — story 9-4 is mid-tranche of Epic 9; subsequent tranche stories (9-10 reframed, plus benchmark tranche 9-5..9-11) are parked but in the same epic.
- **Criterion 5 (privacy-invariant):** NO — persistent overrides change WHICH model dispatches, not WHETHER sensitivity gates fire. The sensitivity gate runs above the audit-emit point (line ~280 vs ~287); persistent override emission happens only on the success path. AC-3's gate-inheritance tests (via the one-shot path which already shipped this) verify the layering. No FR-2.5 / NFR-PRIV-* surface modified.
- **Criterion 6 (load-bearing-orchestrator):** YES — `mailbot_api/verbs/router_control.py` is the slash-command verb surface that Hermes (and Story 9-10's eventual runtime registration) will call as its primary integration surface. Both `set_model_persistent` and `inspect_policy` are PRIMARY integration surfaces for any future Epic 7 / Epic 9 work involving routing observability or drift correction. Additionally, the `_persistent_engaged` kwarg threaded through `_dispatch_with_failure_chain` is a router-hot-path surface that every `ask_router` call exercises. **Fires.**

**Cadence verdict: MANDATORY-CR** (criterion 1 + criterion 6 fire).

The code-review subagent dispatch under `claude-sonnet-4-6` is REQUIRED before Step 2.4.8 can flip the story to `done`. No escape hatch.

---

## Posture Audit summary table

| Check                                                       | Status                                  |
| ----------------------------------------------------------- | --------------------------------------- |
| 5.1 Lockfile hygiene                                        | ✅ PASS                                 |
| 5.2 Cross-doc pair verification                             | ✅ PASS                                 |
| 5.3 Lifecycle string-uniqueness                             | N/A — story added zero i18n keys        |
| 5.4 Multi-consumer impact scan                              | ✅ PASS                                 |
| 5.5 Screenshot-based perception check                       | N/A — no graphical frontend             |
| 5.6 Upstream-contract spec coverage                         | ✅ PASS                                 |
| 5.7 Module-level mutable container                          | ✅ PASS                                 |
| 5.8 Dev-fixture seed-vs-production-shape parity             | ✅ PASS                                 |
| 5.9 grep-verify-cited-figures                               | ✅ PASS                                 |
| 5.10 Producer-boundary contract enforcement                 | ✅ PASS                                 |
| 5.11 Git-evidence consistency check                         | ✅ PASS                                 |
| 5.12 CR-cadence-mandatory surface classification            | **MANDATORY-CR**                        |
