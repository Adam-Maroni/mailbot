# Posture Audit — Section 5 of the Pre-Review Self-Audit

This file expands `## 5. Posture Audit` of the pre-review artifact emitted by Step 2.3.5 of the autonomous-epic-run skill. Load this when generating the pre-review for a story.

**Why a separate file:** the 11 posture checks are dense, runnable-command-driven reference material that rarely changes between stories. The orchestrator skill body stays focused on flow; the audit content lives here.

**Hard contract recap:** each of the 11 checks below MUST produce a runnable command (or N/A justification) AND its actual output pasted inline in the pre-review artifact. Textual claims like "verified clean" without command output are rejected by the gate.

---

## 5.1 — Lockfile hygiene

**Catches:** mass-reformat of the lockfile masquerading as a small dep change.

**Run:**

```bash
# Replace pnpm-lock.yaml with your project's lockfile name
git diff --stat -- <lockfile>
```

Common lockfile names: `pnpm-lock.yaml`, `package-lock.json`, `yarn.lock`, `Cargo.lock`, `poetry.lock`, `Gemfile.lock`.

**Python-stack note (pip + venv, no lockfile generator):** projects using bare `pip + venv` with a hand-pinned `requirements.txt` (e.g., MailBot per AR-BOOT-1) have no auto-generated lockfile. Use `git diff --stat -- requirements.txt` and apply the same threshold (≤ 50 lines for non-dep-change). For projects using `pip-compile` / `pip-tools`, the generated `requirements.lock` (or `requirements.txt` if compiled in place) IS the lockfile and follows the standard threshold. Projects using `poetry` → `poetry.lock`; `uv` → `uv.lock`.

**Threshold:** lockfile diff ≤ **50 lines** for a non-dep-change story. For a dep-change story, the diff should be roughly proportional to the dep count (a single dep removal that produces >500 lines warrants inspection — possibly a transitive cascade, possibly a reformat).

**Required output:**

- `(no output)` for non-dep-change stories — paste literally.
- For dep-change stories — paste the `git diff --stat` line and a one-sentence justification ("removed package X + 8 transitive deps; -37 lines is the surgical delta").
- If output exceeds threshold without justification: HALT — fix the lockfile (revert and re-run the package manager's install command cleanly) before proceeding.

---

## 5.2 — Cross-doc pair verification

**Catches:** doc claims that contradict the canonical source they reference.

**When this check applies:**

1. **Cross-doc claim trigger:** the story makes any claim that cross-references another canonical doc (architecture.md ↔ data-protection.md, .env.example ↔ feature-flags.md, story file ↔ change log, etc.).
2. **Schema-touching trigger:** the story's File List includes ANY path matching the project's migrations directory (e.g., `<orm-migrations-dir>/*`) — regardless of whether the story makes other cross-doc claims. This trigger is mandatory and exercises §5.2.1 below.

**Run (cross-doc claims):** for every doc claim in the story that cross-references another doc, paste a `git grep` (or `Grep` tool) result of the canonical source into this section. Format:

```
Claim: "<doc-A> says runId is now visible to all roles" (story file:LINE)
Canonical source: docs/<doc-A>.md:LINE
Verification:
  $ git grep -n "runId" docs/<doc-A>.md
  <paste result>
Verdict: MATCH | DRIFT — <description>
```

**Required output (cross-doc branch — independent of §5.2.1):** at least one pair-verification block for every cross-doc claim. If the story makes no cross-doc claims, write `N/A (cross-doc branch) — no cross-doc claims in this story` and explicitly justify (e.g., "single-file refactor, no doc surface touched"). The schema-touching branch is evaluated separately at §5.2.1 — a story may legitimately have `N/A (cross-doc branch)` AND `FLAGGED (§5.2.1)` simultaneously, or any other combination.

**Anti-pattern:** "verified that doc X reflects the change" without pasted grep output — REJECTED.

### 5.2.1 — Schema-touching schema-doc verification

**Catches:** schema migrations that ship without any corresponding entry in the project's schema doc (e.g., `docs/DATABASE.md`, `docs/schema.md`), leaving new contributors orienting on a stale schema doc.

**Trigger:** File List contains ANY path matching the project's ORM migrations directory. The trigger is binary — if the path is present, this check is mandatory; if absent, this check is N/A.

**Run:**

```bash
# Replace <NewModelName> / <new_table_name> / <NewEnumName> with the actual additions from the migration SQL.
# Use Grep tool with output_mode: "count" or "content" — pasted output required.
Grep "<NewModelName>|<new_table_name>|<NewEnumName>" docs/<schema-doc>.md
```

**Required output:** the Grep tool's actual response pasted inline. If matches ≥ 1, verdict is `MATCH — schema doc mentions the new schema element`. If matches = 0, verdict is `⚠️ FLAGGED — story MUST add a schema-doc section/paragraph BEFORE flipping to review`.

**Required schema-doc entry shape** (typical per-table convention):

- **Model purpose** — one-sentence description of what the table represents in the domain
- **Key columns** — the load-bearing columns with their types (FK references, enums, unique constraints)
- **Indexes** — any non-trivial composite indexes or unique constraints
- **Data classification** — PII / non-PII / mixed; encrypted columns called out; retention posture
- **Lifecycle** — append-only vs mutable; supersession semantics if any; cascade-delete behavior

**Anti-pattern:** textual claim like "schema doc updated for the new schema element" without the pasted Grep output — REJECTED. The grep output is the load-bearing artifact.

**N/A justification (when trigger does NOT fire):** "File List contains no migrations paths" — explicitly state.

---

## 5.3 — Lifecycle string-uniqueness check

**Catches:** new/modified i18n keys whose string content collides with sibling lifecycle stages, breaking multi-stage progressions before any user sees them.

**When this check applies:** the story added or modified i18n keys that participate in a multi-stage lifecycle. Examples: `toast.loading()` → `toast.success()` (2-stage); modal `opening` → `confirming` → `success` (3-stage); banner `pending` → `in-progress` → `complete` (3-stage); any keys related by lifecycle prefix (e.g., `actionLoading`, `actionSuccess`, `actionError`).

**Run:** for each new/modified key, list ALL sibling lifecycle keys side-by-side with their strings. Visual comparison — the dev model literally reads them and confirms each is _visually distinguishable_ from siblings (different opening words, different lengths, different punctuation patterns).

**Required output:**

```
Lifecycle: importJob (process import flow)
Stage 1 (loading):     importJobLoading: "Starting import…"
Stage 2 (success):     importJobSuccess: "Import complete — N rows added."
Stage 3 (cooldown):    importJobCooldown: "Import recently run — retry available in 1 hour."
Stage 4 (forbidden):   importJobForbidden: "Insufficient permission to run imports."
Verdict: ALL DISTINCT (different opening words, different lengths)
```

**Anti-pattern:** comparing only the new key against the _immediate_ sibling. Compare against ALL keys that share the lifecycle prefix.

**N/A justification:** "story added no i18n keys" or "story added i18n keys that don't participate in any lifecycle (e.g., one-off labels)" — explicitly state which.

---

## 5.4 — Multi-consumer impact scan

**Catches:** changes to shared hooks/services/components that affect consumers the dev model didn't audit.

**When this check applies:** the story modified a file under a shared-code location — e.g., a shared hooks directory, a shared services directory, any component re-exported from a shared `index.ts`, or any module that is consumed by multiple call sites in the codebase.

**Run:** for the modified file/symbol, paste a `git grep` (or `Grep` tool) result enumerating production consumers:

```bash
# Production code consumers
git grep -n "from.*<modified-module-path-or-name>" <project-src-root>/
```

**Required output:**

```
Modified file: <path-to-modified-shared-module>
Production consumers found:
  <path-to-primary-consumer>     — kebab item (PRIMARY consumer, story scope)
  <path-to-secondary-consumer-A> — button (SECONDARY — needs explicit opt-out)
  <path-to-secondary-consumer-B> — failure-banner retry (SECONDARY — needs explicit opt-out)
Verdict: 3 production consumers; story scope is PRIMARY; SECONDARY consumers verified opt-out path.
```

**Anti-pattern:** modifying a shared hook and reasoning only about the primary consumer. EVERY consumer must be enumerated and the dev model must explicitly verify the change is correct (or has an opt-out) for each.

**N/A justification:** "story did not modify any shared hook/service/component" — explicitly state.

---

## 5.5 — Screenshot-based perception check (when an AC asserts "X is human-visible")

**Catches:** validation surfaces using DOM-level instruments (MutationObserver, test-id queries, CSS-class assertions) as proof of perceptibility, when the actual question is whether the user's eyes see the painted state. DOM-level instruments fire BEFORE paint and miss paint-cycle gaps.

**Anti-pattern (do NOT use):** MutationObserver, `data-testid` queries with `queryByTestId`, CSS-class presence assertions, or any DOM-level instrument as proof of perceptibility. These prove _correctness_ (the right mutation fired) but NOT _perceptibility_ (the user had a chance to see it).

**Required pattern:** browser screenshot via your automated browser tool (Playwright MCP `browser_take_screenshot`, Cypress, etc.) with ≥16ms delay AFTER the trigger event (one paint cycle) AND visual confirmation — either real-user eye verification OR a literal pixel-diff against a baseline image. The screenshot evidence is pasted as a file path reference; the visual confirmation is a one-line verdict.

**When this check applies:** the story includes any AC, UAT surface, or verification step that uses the verb "visible" / "visible to user" / "human-perceptible" / "user sees" / "appears" / "displays". If the story is documentation-only or backend-only with no user-visible behavior, mark N/A.

**Required output:**

```
Visibility claim: AC-2 "loading toast appears for ≥1 paint cycle on fast 409 response"
Screenshot evidence: <bmad-output>/implementation-artifacts/<story-id>-dvm-loading-toast.png
Trigger → screenshot delay: 33ms (screenshot fired 33ms after click event)
Visual verdict: PAINTED — loading toast visible in screenshot before warning toast replacement
Real-user verification: PASS (verified <YYYY-MM-DD>)
```

**N/A justification:** "story is documentation-only" / "story is backend-only with no user-visible surface" / "story modifies internal API contract not user-facing UI" — explicitly state.

---

## 5.6 — Upstream-contract spec coverage check

**Catches:** specs that test "fallback if upstream is missing" branches without also testing "real desired behavior when upstream is missing but a _related_ signal IS present" — produces unit-test-green code that fails real-world integration.

**When this check applies:** the story implements behavior that depends on an **upstream projection contract** — e.g., role-stripped fields, encrypted-at-rest boundaries, workspace-scoped queries, optional response fields stripped by a guard, behavior that varies based on a server-side gate.

**Run:** for the modified file, identify every consumed upstream field and:

1. List each upstream contract dependency in the story file's Dev Notes (e.g. "depends on Story X-2 — `rawPayload` stripped for non-admin role")
2. For each dependency, verify the spec encodes BOTH the present-AND-absent cases
3. For each absent case, verify the spec encodes the FULL desired-output contract — not just the "fallback to default" branch. If a related upstream signal IS present in the absent case (e.g. `summary` present even when `rawPayload` absent), the spec MUST test the desired derived behavior

**Required output:**

```
Upstream-contract dependency 1: `event.rawPayload` (stripped for non-admin role)
- Present case: spec test "ADMIN with full rawPayload" asserts canonical message + disclosure ✓
- Absent case (related signal present): `event.summary` IS visible to non-admin AND contains "${errorType} — ..." prefix
  - Spec test name: "non-admin derives canonical from summary when rawPayload absent"
  - Assertion: rendered canonical matches event.summary's errorType prefix → CANONICAL[errorType]
  - Status: ✓ PASS / ⚠️ FLAGGED — <gap>
```

**Anti-pattern:** spec tests `"rawPayload undefined → UNKNOWN"` and stops there. The desired contract was "non-admin sees the SAME canonical message as admin, derived from `summary` instead of `rawPayload.errorType`." The spec encoded the WRONG fallback contract.

**N/A justification:** "story does NOT depend on any upstream-stripped field" — explicitly state which projection contract was checked + confirmed not in scope. If the story is purely additive (new field, new component, no projection consumption), N/A applies.

---

## 5.7 — Module-level mutable container check (FE+BE scope)

**Catches:** module-level mutable containers (`let counter = 0;`, `const cache = new Map();`, `const set = new Set([...]);` without `Object.freeze`, etc.) in any `.ts/.tsx`/`.js/.jsx` source file — both frontend and backend. Two distinct failure modes:

- **Frontend concern (SSR-rendered frameworks like Next.js / Remix / SvelteKit):** SSR hydration mismatch. Module-singleton state diverges between server render (counter starts at 0, increments per server-render call) and client hydration (counter starts at 0 again, but with stale-on-server values already painted).
- **Backend concern:** Test-runner shared-module-scope test bleed. Module-level Set/Map declared once, mutated in test A, leaks state into test B. Even when usage looks read-only, lack of `Object.freeze` allows future code (or a misguided test) to mutate.

**Python-stack overlay (FastAPI / pure-Python backends, no graphical frontend):** the SSR-hydration concern is N/A. The backend test-bleed concern applies and is sharper than in JS/TS because Python has no `Object.freeze` equivalent for arbitrary objects. For Python projects, apply this check as:

- **In scope:** every modified `.py` file in the story's File List
- **Anti-patterns to flag:** module-level `dict`, `list`, `set` declarations that get mutated by any code path (`MY_CACHE: dict[str, X] = {}` followed by `MY_CACHE[k] = v` anywhere); module-level counters (`_call_count = 0` mutated via `global _call_count` inside a function); module-level Pydantic model instances used as mutable defaults; `lru_cache` on functions taking unhashable args (silently fails to cache and accumulates over time)
- **Acceptable patterns:** module-level constants typed as `Final[...]` (PEP 591) and never mutated; `MappingProxyType(dict)` for read-only mappings; `frozenset([...])` for read-only sets; `tuple([...])` instead of list for read-only sequences; dataclass instances marked `frozen=True`
- **MailBot-specific anti-pattern to watch for:** module-level state in `mailbot_api/router/router.py`, `mailbot_api/router/budget.py`, `mailbot_api/router/cache_warmer.py`, or `mailbot_api/config.py` — these run inside a long-lived process where module-singleton state persists across all requests. Any mutable container here is a per-process global, which is fine if intentional (e.g., a budget tracker singleton) but must be explicitly documented with a one-line comment naming the lifecycle (`# module-singleton: per-process budget state; reset on container restart`).
- **N/A if:** the story modified zero `.py` files (documentation-only / config-only / skill-only).

**When this check applies:** the story added or modified ANY source file in the story's File List — frontend OR backend.

**Run:**

```bash
# Search modified files for module-scope mutable patterns
git diff --cached -- '**/*.ts' '**/*.tsx' '**/*.js' '**/*.jsx' | grep -E '^\+\s*(let|var)\s+[a-zA-Z_$][a-zA-Z0-9_$]*\s*[:=]|^\+\s*const\s+[a-zA-Z_$][a-zA-Z0-9_$]*\s*=\s*new\s+(Map|Set|WeakMap|WeakSet)' | head -20
```

OR via the Grep tool: search the modified files for these patterns at module scope (not inside a function body):

- `let foo = 0;` (mutable counter)
- `let foo: SomeType | null = null;` (mutable cache)
- `const cache = new Map();` (mutable shared collection)
- `const set = new Set([...]);` (any Set/Map without `Object.freeze`)
- `const obj = { ... };` (mutable shared object)
- `const subscribers = new Set();` (legitimate frontend ONLY if accompanied by a documented subscribe/getSnapshot pattern + `useSyncExternalStore` consumers)

**Required output:** for each match, document either:

- `(no output)` if grep is clean — module-level mutable container pattern not present in either layer
- For each match: classification + remediation, citing the layer and the appropriate remediation pattern below

**Frontend example (SSR hydration concern):**

```
File: <frontend-src>/lib/foo/error-rendering.ts
Match: `let disclosureIdCounter = 0;` (line ~62)
Layer: FE (frontend)
Classification: ❌ Anti-pattern — mutable counter at module scope, consumed at component render time → SSR hydration mismatch risk
Remediation: replaced with `idPrefix?` parameter (caller passes the framework's stable-ID hook, e.g., `React.useId()`); state moved out of module entirely
Verdict: FIXED — no module-level mutable state remains
```

**Backend example (test-bleed concern):**

```
File: <backend-src>/services/foo.service.ts
Match: `const QUOTA_GATED_SOURCES = new Set(['providerA', 'providerB']);` (pre-fix shape)
Layer: BE (backend)
Classification: ❌ Anti-pattern — mutable Set at module scope; even if usage is read-only, test-runner shared-module-scope test-bleed risk is non-zero
Remediation: wrap in `Object.freeze(...)` and type as `ReadonlySet<string>` —
  const QUOTA_GATED_SOURCES: ReadonlySet<string> = Object.freeze(
    new Set<string>(['providerA', 'providerB']),
  );
Verdict: FIXED — frozen at module-load; type signature locks read-only access at compile time
```

**Legitimate exceptions:**

- **Frontend:** module-level mutable state is OK ONLY when ALL of these hold:
  1. The file exports a documented subscribe-and-snapshot API (`subscribeToFoo()` + `getFooSnapshot()`)
  2. Consumers use `useSyncExternalStore(subscribe, getSnapshot, () => null)` (or the framework's equivalent SSR-safe store hook)
  3. The state is genuinely shared across multiple consumers and the alternative would be prop-drilling through 3+ component layers

- **Backend:** genuine immutable constants where the freeze cost isn't worth it (rare; default to freezing). Requires an explicit `// eslint-disable-line` or inline justification comment naming the constant + why freezing was skipped. Without that comment, the BE-side default is `Object.freeze` + `ReadonlySet<T>` / `ReadonlyMap<K,V>` / `Readonly<T>` typing.

**Anti-patterns:**

- FE: `let counter = 0; function nextId() { return ++counter; }` consumed at render time without `useSyncExternalStore`. Will produce hydration mismatch + SSR/CSR ID divergence.
- BE: `const SOURCES = new Set([...])` at module scope without `Object.freeze`. Even if read-only at the call site, future code or a stray test can mutate; type system won't prevent it.

**N/A justification:** "story modified zero source files in either FE or BE" — explicitly state which layer was checked + confirmed not in scope. Documentation-only stories + skill-only stories are N/A. Single-layer stories (FE-only or BE-only) state the touched layer + confirm the other layer was untouched.

---

## 5.8 — Dev-fixture seed-vs-production-shape parity check

Dev-fixture seeds for any surface consuming ORM-query output (or any pipeline-recorded / recorder-produced JSON payload) MUST be designed against the **actual producer shape** — a recorded fixture from a real run, OR a snapshot driven by a pinned producer test — NOT against the consumer's expectations.

**Catches:** consumer-side test fixtures hand-crafted against what the test author _imagined_ the producer emits — instead of what the producer actually emits. The fixture passes the consumer's tests because it matches the consumer's mental model; it then fails on the first real-domain interaction because production data uses the actual producer shape.

**When this check applies:**

1. **Test-fixture trigger:** the story's File List introduces or modifies a test fixture (JSON, in-spec object literal, test helper) consumed by code that reads ORM output OR a pipeline-recorded JSON payload.
2. **Pipeline-output surface trigger:** the story's File List modifies a service or projection that consumes pipeline-recorded payloads and the modification implies a new test fixture is needed to exercise the changed read path.

When either trigger fires, every fixture-introduced-or-modified MUST be classified per the "Required output" branch below. If neither trigger fires, see the **N/A justification** branch.

**Run:**

For each fixture file or in-spec fixture object introduced or modified by the story, document its provenance — one of three acceptable patterns, in order of preference:

1. **Recorded snapshot** — the fixture is a literal snapshot of a real producer run (e.g., a JSON export from a known dev/staging row, or a fixture file recorded once from a real vendor API / ORM response). Header comment / `_meta` block MUST name the source (run id + domain/account + extraction date + drift-spec re-record trigger).
2. **Producer-test-driven snapshot** — the fixture is byte-equal to the output of a **pinned producer test** (e.g., a `RecorderClass.build()` call driven through a representative lifecycle inside the same spec). The spec MUST assert byte-equality (`expect(fixturePayload).toEqual(recorderOutput)`) so any future producer drift fails this assertion immediately. Header comment / `_meta` block MUST name the producer, the build commit, and the regenerate command.
3. **Shape-faithful synthesis (last resort)** — the fixture is hand-crafted but every field name, type, and nesting depth maps 1:1 to the canonical producer interface. Acceptable ONLY when patterns 1 and 2 are **demonstrably infeasible**. Acceptable infeasibility reasons (non-exhaustive but concrete — pre-review §4 MUST cite ONE of these or escalate):
   - **External API not yet deployed in dev env** — credentials/integration would be outside the story's scope.
   - **Producer class not yet merged** — pattern 2 is blocked on a parallel/dependent story.
   - **Fixture predates the producer abstraction** — refactoring the legacy fixture is out of scope.
   - **Producer is a third-party library output the project does not own** — recording would require a real round-trip the spec is not set up for.

   Header comment MUST cite the canonical interface by file:line AND name which infeasibility reason applies. The shape MUST also be guarded by a separate byte-equality drift spec that catches producer-side changes. If no drift spec exists OR the cited infeasibility reason is not in this list (or comparably concrete), the fixture MUST escalate to ESCALATE TO REVIEWER in §4. "Pattern 3 is convenient" is NOT a valid infeasibility reason.

**Required output:** for each fixture introduced or modified, paste a one-block summary:

```
File: <path/to/fixture or in-spec object location>
Pattern: 1 (recorded snapshot) | 2 (producer-test-driven snapshot) | 3 (shape-faithful synthesis — last resort)
Producer: <RecorderClass.build() | real vendor API response | CanonicalShape interface | ...>
Header comment / _meta provenance: <quoted excerpt or "<inline at line N>">
Drift sentinel: <byte-equal spec path | "N/A — recorded snapshot" | "ESCALATE — no drift spec available">
Verdict: PASS | FLAGGED — <reason>
```

**Anti-pattern (REJECTED):**

```
File: <backend-src>/services/__tests__/some-projection.spec.ts (in-spec object literal)
Pattern: hand-crafted against consumer expectations
Producer: <unspecified — author imagined what the recorder produces>
Header: <none — the fixture is a bare object literal>
Drift sentinel: NONE
Verdict: ❌ FLAGGED — fixture anchors on consumer-side expectations, not producer shape; future producer change WILL silently green-path the consumer tests while breaking real-domain interactions. Refuse to proceed; switch to pattern 1, 2, or 3.
```

**Legitimate exceptions:**

- **Content vs shape:** fixture content (specific values — URLs, names, hashes) MAY be illustrative as long as the **shape** is faithful (every field name and type matches the producer). A recorder-driven fixture with fictional content strings still satisfies §5.8 because the recorder is the literal producer of the shape.
- **Cross-spec sharing:** a single recorded fixture MAY be referenced by multiple specs (the JSON file is the shared canonical artifact); each consumer spec MUST cite the fixture path + the byte-equality drift sentinel that protects it.

**Sibling rule cross-reference:** §5.8 catches the **producer-shape side** of fixture-vs-real-data drift. The **runtime-verification side** is caught by `SKILL.md` Phase 3.5 → "Three-layer verification model" (real-user verification on real-domain data, NOT batchable when fixture seeds were authored by the same agent that ran the test). Together, §5.8 (fixture parity at pre-review time) + Phase 3.5 real-user verification (real-data verification at end-of-epic) close the failure mode end-to-end.

**N/A justification:** ANY of the following:

- "Story added zero new test fixtures consumed by code reading ORM output or pipeline payloads" — explicitly state.
- "Story modified an existing fixture and the §5.4 multi-consumer scan confirmed the producer shape is unchanged" — cite §5.4 verdict.
- "Story is documentation-only or skill-only (no source code, no test fixtures)" — explicitly state.

---

## 5.9 — grep-verify-cited-figures

Numeric figures cited in pre-review artifacts, story files, or code-review dispositions (cost subtotals, test counts, file counts, line-number references, character deltas, entry counts, percentage figures) MUST be verified via a runnable command + pasted output BEFORE the cite ships — NOT cited from prior prose memory or earlier-story self-references.

**Catches:** self-citation cited without verification. The dev agent reads a figure in their own prior prose (an earlier pre-review, an earlier story's Completion Notes, an earlier sprint-status row), treats it as authoritative without re-grep / re-run, and the figure propagates through subsequent pre-reviews — accumulating drift each cite.

**When this check applies:** the pre-review, story file, or code-review disposition cites ANY numeric figure that COULD have drifted since the cite-source was originally produced. Examples of in-scope citation types (non-exhaustive):

- **Cost arithmetic** — paid-API spend subtotals; combined-cap headroom remaining
- **Test counts** — "X/Y tests PASS", "Δ +N tests since baseline", suite-level counts
- **Reference-data counts** — JSON entry counts, Map sizes, Set sizes
- **File counts** — "N files in scope", "M files staged", File List counts
- **Line-number references** — `<file>:294-303` (where the line numbers could have drifted in subsequent edits)
- **Character deltas** — "JSON grew by ~150 bytes", "bundle delta +20 KB gzipped"
- **Percentage figures** — "applied-rate 89%", "coverage 81%"

Out of scope: figures that are inherently stable for the lifetime of the story (epic number, story number, RFC numbers, fixed external constants).

**Run:** for each numeric cite in the pre-review/story/disposition, paste the runnable command + actual output into the artifact alongside the cite. For computed figures (cost sums, percentage rates), paste the inputs + the arithmetic. Verification commands MAY be inline in §5 OR cross-referenced from the cite site to a previously-pasted §5 block.

**Required output (per cite):**

```text
Cite: "X/Y tests PASS in <surface>" — at <pre-review §1 AC-N> + <story File List>
Verification command:
  $ <test runner command targeted at the relevant suite>
  [paste actual tail output]
Verdict: MATCH (figure matches command output) | DRIFT — <delta>
```

For computed figures (cost sums, arithmetic):

```text
Cite: "Combined epic spend $0.0567 / $0.50 cap (11.34% used; $0.4433 headroom)"
Inputs: story-1 $0.04 + story-2 $0.00003 + story-3 $0.0076 + ... [paste cost-log entries]
Arithmetic: 0.04 + 0.00003 + 0.0076 + ... = 0.0567 ✓
Verdict: MATCH (sum + percentage + headroom all recomputed at audit time)
```

For line-number references:

```text
Cite: "validator call site at <file>:294-303" + "second site at <file>:559"
Verification command:
  $ Grep -n "<symbol-name>" <file>
  297:    if (createDto.foo && !isValid(createDto.foo)) {
  556:    if (updateDto.foo && !isValid(updateDto.foo)) {
Verdict: DRIFT — 294-303 → 297 (line shift since cite); 559 → 556. Update cite to current line numbers OR add commit-hash anchor.
```

**Disambiguation rule when verification output is ambiguous:** if a runnable command output requires interpretation (e.g., a Grep that returns sub-sections sharing a parent number, or a `wc -l` count that includes blank-lines the cite didn't), the verdict block MUST include an explicit counting rationale — not just "MATCH". Example: `Verdict: MATCH — 10 raw Grep matches; §5.2.1 is a sub-of-§5.2 so the canonical top-level count is 9.` Silent miscount acceptance is a §5.9 anti-pattern in itself.

**Anti-pattern (REJECTED):**

```text
Cite: "Combined epic spend $0.0567 / $0.50 cap"
Source: <prior-story> pre-review §5.5 (no verification, re-cited from <even-earlier-story> pre-review without re-summing the cost-log)
Verdict: ❌ FLAGGED — figure cited from prior prose without re-verification.
```

**Precedence rule when a cite appears in a code-review finding or honest-rescope note:** the verification MUST run BEFORE the dispositioning edit ships. A code-review finding that says "the dev agent cited X but actual value is Y" requires the dev pass to (a) re-run the verification command, (b) paste the actual output, (c) update both the cite AND the dispositioning narrative to match. Skipping verification at the dispositioning step is a re-instance of the same failure mode inside the fix for that failure mode. **Termination — the pasted command output is the LEAF unit:** it is not subject to a further §5.9 verification cycle. The rule does not recurse on its own output; the leaf-unit framing prevents spurious re-verification loops.

**PASS-vs-N/A boundary:** the "Single-cite + single-use" exception below applies ONLY when the cite NEVER leaves its adjacent-verification block. The moment ANY numeric figure is re-cited elsewhere in the artifact (in §1 AC-vs-code, §3 self-review, §4 disposition table, Completion Notes, Change Log, or the sprint-status row), the check verdict is **PASS** (not N/A) and the verification output MUST be available for every re-cite site. The exception path is narrow: a one-off self-contained verification block with no narrative re-references. If in doubt, default to PASS (with paste-output anchoring) rather than N/A.

**Legitimate exceptions:**

- **Single-cite + single-use** — a figure cited once in a single pre-review §5 block with the verification command + output immediately adjacent AND no re-cite anywhere else in the artifact. The §5.9 check is N/A by construction because there's no re-citation surface.
- **Frozen historical figures** — figures that were verified at a known point in time AND the story explicitly cites the verification source by URL + timestamp (e.g., "verified at commit `<sha>` on <YYYY-MM-DD>"). The verification must be re-runnable from the cited commit + the cite must include the timestamp + commit.
- **Order-of-magnitude approximations** explicitly marked as such (e.g., "~150 entries", "~$0.02 worst-case"). The `~` prefix or "approx" marker signals non-load-bearing precision; not subject to §5.9.

**N/A justification:** ANY of the following:

- "Story cited zero numeric figures" — explicitly state (rare; most stories cite at least a test count or file count).
- "All cites are single-use with adjacent verification" — list the cite locations + confirm no re-citation surface.
- "Story is documentation-only with no test/cost/count figures" — explicitly state.

**Sibling rule cross-reference:** §5.9 is the verification-discipline complement to §5.2 (cross-doc pair verification). §5.2 catches doc claims contradicting their canonical source; §5.9 catches numeric figures cited from prose memory without command-output anchoring. Together: §5.2 (qualitative claims) + §5.9 (quantitative claims) close the broader "self-citation without verification" failure mode.

**Tiebreaker for mixed qualitative+quantitative claims:** when a cross-doc claim contains a numeric figure (e.g., "schema doc shows the new table has 3 columns"), BOTH §5.2 (structural canonical-source match) AND §5.9 (numeric verification) must pass independently. The two checks are AND-composed for mixed claims, not OR-composed.

---

## 5.10 — Producer-boundary contract enforcement

Sibling rule to §5.4. Where §5.4 enumerates consumers of a modified producer, §5.10 inverts the lens: when the story touches a **producer** that feeds **typed-column writes** OR emits **response shapes consumed by HTTP clients**, the producer MUST enforce the safety contract at its own boundary — not at the consumer boundary.

**Python-stack overlay (FastAPI + Pydantic + raw SQL):** the JS/TS examples below use `BigInt(...)`, `new Decimal(...)`, `parseInt(...)`, and `SAFE_USER_SELECT` (Prisma allow-list). For Python projects, the equivalents are:

- **§5.10.a typed-column producers (Python equivalents):**
  - `int(value)` on third-party JSON without `isinstance(value, (int, float)) and math.isfinite(value)` — equivalent to unguarded `BigInt(...)`. Will raise `ValueError` on bad input that leaks via HTTP 500.
  - `Decimal(value)` from `decimal` module without try/except + type guard — equivalent to unguarded `new Decimal(...)`.
  - `datetime.fromisoformat(value)` on third-party strings without `isinstance(value, str)` guard — raises `TypeError` on non-string input.
  - **Defense-in-depth via Pydantic:** use `@field_validator(mode="before")` on the boundary model to coerce + validate, OR use `Annotated[int, Field(strict=True)]` to make Pydantic refuse coercion. The validator IS the boundary guard.
  - **MailBot-specific:** raw SQL writes in `mailbot_api/db/queries.py` should accept already-validated Pydantic instances, never raw `dict`s from `request.json()`. The Pydantic boundary is the producer guard.
- **§5.10.b response-shape allow-lists (Python equivalents):**
  - The Prisma `select: { ... }` allow-list translates to: a **response Pydantic model** (`UserResponse(BaseModel)`) that explicitly lists wire-allowed fields, returned from the route handler instead of returning the ORM row dict directly.
  - **MailBot-specific:** with stdlib `sqlite3` and raw SQL (no ORM), the equivalent is: `SELECT id, email, name FROM users WHERE id = ?` — never `SELECT *`. The `SELECT` column list IS the allow-list, and it's enforced at the query, not at the response model. The verb returns a Pydantic model whose fields match the SELECT columns 1:1, which makes accidental column widening a type error caught at construction time.
  - **Sensitive-field surface for MailBot specifically:** `oauth_state.refresh_token`, `oauth_state.access_token`, `router_calls.sensitivity_grant_id` if `mint_sensitivity_token` lifecycle leaks, anything under the privacy posture in NFR-PRIV-0..4. Per Rule F.1, the Anthropic API key is never in a row at all — but any query that joins onto user-supplied credentials needs the allow-list discipline.

The JS/TS examples below remain the canonical illustration of the check's intent; substitute Python equivalents when applying it to a Python project.

Two distinct sub-rules:

- **§5.10.a — Typed-column shape constraints** — producers writing to typed columns (`BigInt`, `Decimal`, enum-like, narrowed unions) MUST validate input shape AT THE PRODUCER. Unguarded coercion (`BigInt(value)`, `new Decimal(value)`, `parseInt(value, 10)` without `Number.isFinite`) on third-party / IO inputs is rejected. Defense-in-depth at the DTO/serializer layer is required when the value crosses an HTTP boundary on the way in.
- **§5.10.b — Response-shape co-emission audit** — when §5.4 audits multi-consumer impact for shared type T, the audit MUST enumerate **other shared types co-emitted with T in the same response path**. If any co-emitted type carries sensitive fields (auth — `passwordHash`/`refreshTokenHash`/session secrets; PII — un-hashed email, raw token; internal-only — `deletedAt`, soft-delete columns, internal cursors), those types MUST also be audited for explicit wire-shape allow-lists (`<Model>Select` projection, DTO whitelist, etc.).

**Catches:** producer-side gaps that adversarial code-review cannot see by reading the producer in isolation. Example failure modes: (a) third-party JSON containing a fractional numeric value reaches an unguarded `BigInt(value)` coercion → raw runtime exception leaks via 5xx response; (b) a `findUnique` / `findFirst` call returns the full ORM row including sensitive fields because the service used `select: undefined` instead of an explicit allow-list.

**When this check applies:** the story modifies a file that normalizes / extracts / ingests third-party data, OR any code path that produces a value destined for a typed ORM column, OR any service returning an ORM row to an HTTP consumer. Also fires when §5.4 audits a shared type that is co-emitted in any response shape.

**Run §5.10.a — Typed-column producer-boundary scan:**

For every producer modified in the story, grep for unguarded coercion against the typed column it feeds:

```bash
# Pattern: unguarded BigInt() / Decimal() / parseInt() on third-party numeric input
git grep -n -E 'BigInt\(|new Decimal\(|parseInt\(' <integration-or-normalizer-paths>/
git grep -n -E 'BigInt\(|new Decimal\(' <modified-service-paths>/
```

Then for each hit, classify:

- **GUARDED** — wrapped in `Number.isFinite(value)` + `Math.round(value)` (numeric) OR explicit narrowed-type guard (enum, string-pattern) BEFORE the coercion call. ✅ PASS.
- **DTO-guarded** — value enters via a validator DTO with a `@Transform` (or equivalent) that performs the rounding/guarding. ✅ PASS, but document the DTO + the guard site.
- **UNGUARDED** — raw `BigInt(value)` / `new Decimal(value)` / `parseInt(value, 10)` on an input that could be NaN, fractional, or a non-string. ❌ FLAGGED — fix at the producer (Math.round + Number.isFinite for numerics; explicit narrow guard for enums/strings) AND add DTO-layer defense-in-depth if the value crosses HTTP.

**Fix exemplar:**

```typescript
// producer normalizer (post-fix)
static extractNumericField(input: VendorResponse): bigint | null {
  const raw = input.latestRecord?.numericValue;
  if (raw == null) return null;
  const numeric = typeof raw === 'number' ? raw : Number(raw);
  if (!Number.isFinite(numeric)) return null;
  return BigInt(Math.round(numeric));
}

// DTO defense-in-depth
const toRoundedBigInt = ({ value }: TransformFnParams): bigint | undefined => {
  if (value == null || value === '') return undefined;
  const numeric = typeof value === 'number' ? value : Number(value);
  if (!Number.isFinite(numeric)) return undefined;
  return BigInt(Math.round(numeric));
};

@Transform(toRoundedBigInt)
numericField?: bigint;
```

**Required output (§5.10.a):**

```text
Producer modified: <path-to-normalizer>:extractNumericField
Typed columns fed: ORM `<table>.numericField` (BigInt), `<table>.capital` (BigInt)
Coercion sites:
  <path>:370  return BigInt(Math.round(numeric));  ← GUARDED (Number.isFinite + Math.round)
DTO defense-in-depth:
  <dto-path>:42   @Transform(toRoundedBigInt) numericField?: bigint;  ← present
Verdict: ✅ PASS — producer guards inputs; DTO defense-in-depth present for HTTP-boundary writes.
```

**Run §5.10.b — Response-shape co-emission audit:**

For every shared type T touched by §5.4 in this story, enumerate the response shapes where T is co-emitted with other shared types:

```bash
# Pattern: find ORM include / select trees that co-emit the audited type
git grep -n -E 'include:|select:' <service-feeding-T-paths>/ | grep -v test
```

Then for each co-emitted type, classify:

- **ALLOW-LISTED** — the service projects through a named `<Model>Select` constant (e.g., `SAFE_USER_SELECT`) that explicitly enumerates wire-allowed fields. ✅ PASS.
- **NON-SENSITIVE** — the co-emitted type has no sensitive fields (no credentials, no PII, no internal-only columns). ✅ PASS — document the audit.
- **UNFILTERED** — the service returns the co-emitted type with `select: undefined` or `include: { ... }` without a projection layer, AND the type contains sensitive fields. ❌ FLAGGED — introduce a `<Model>Select` allow-list constant and project through it; cross-link the constant to the frontend consumer type for synchronization.

**Fix exemplar:**

```typescript
// service (post-fix)
const SAFE_USER_SELECT = {
  id: true,
  workspaceId: true,
  email: true,
  emailHash: true,
  name: true,
  jobTitle: true,
  avatarUrl: true,
  locale: true,
  timezone: true,
  role: true,
  createdAt: true,
  updatedAt: true,
} as const;
// passwordHash, refreshTokenHash, deletedAt explicitly OMITTED — adding a new sensitive
// column doesn't accidentally widen the response.
```

**Required output (§5.10.b):**

```text
§5.4 audited type: <PrimarySurface> (this story's primary surface)
Co-emission audit — types appearing in response shapes alongside <PrimarySurface>:
  - User (via /users/me + dashboard layout)         — wire-shape allow-list: SAFE_USER_SELECT ✅
  - Summary (via /entities/:id/summary)             — non-sensitive (no auth/PII)             ✅
  - VendorError (via /entities/:id/errors)          — non-sensitive after vendor redaction    ✅
Verdict: ✅ PASS — all co-emitted shared types have wire-shape allow-lists or are non-sensitive.
```

**Anti-patterns (REJECTED):**

```text
Producer: <normalizer-path>:extractNumericField (pre-fix)
Coercion site: return BigInt(input.latestRecord.numericValue);  ← UNGUARDED
Verdict: ❌ FLAGGED — vendor may return fractional value; unguarded BigInt() throws TypeError;
                     TypeError.message ("The number X cannot be converted to a BigInt...")
                     leaks via HTTP exception filter to 500 response detail (pre-fix).
```

```text
§5.4 audited type: <PrimarySurface>
Co-emission audit: not performed — only <PrimarySurface>'s direct consumers were enumerated.
Verdict: ❌ FLAGGED — User is co-emitted in dashboard responses; passwordHash + refreshTokenHash
                     leak via /users/me without SAFE_USER_SELECT projection. Information
                     disclosure ship.
```

### 5.10.c — Producer-boundary input-shape guard

**Catches:** producer ingestion paths that don't validate third-party input shape (vendor API JSON) before reaching typed ORM columns. Defense-at-boundary vs defense-via-consumer.

**When this check applies:** the story modifies a `.normalizer.*`, `.extractor.*`, or any service ingesting third-party JSON destined for typed ORM columns.

**Run:**

```bash
git grep -n -E '(VendorA|VendorB|extractFrom|normalize)' <integrations-dir>/
```

For each producer-boundary site: verify input-shape guards (`typeof === 'object'` checks, schema-validation, null guards) BEFORE values flow into typed-column writes.

**Verdict:** ✅ PASS (input-shape guarded) | ⚠️ FLAGGED (unguarded third-party JSON reaches typed column) | N/A (story modified zero ingestion paths).

### 5.10.d — Adjacent-shared-type re-export audit

**Catches:** shared types re-exported through a shared `index.ts` (or cross-package re-export sites) whose re-export site was not audited for sensitive-field leak via the new export path. §5.4 audits direct consumers; §5.10.d audits 2nd-degree consumers via re-export.

**When this check applies:** the story modifies any file under a shared types directory OR a shared `index.ts` re-export site, AND the modified type is consumed by HTTP responses.

**Run:**

```bash
git grep -n -E 'export.*from.*\./<modified-type>' <shared-types-dir>/
git grep -n -E 'import.*<modified-type>' <backend-src>/ <frontend-src>/
```

For each re-export site + each 2nd-degree consumer: verify the type's wire-shape allow-list (or non-sensitive classification) is intact through the re-export path.

**Verdict:** ✅ PASS (re-export audit clean) | ⚠️ FLAGGED (re-export 2nd-degree consumer leaks sensitive field via new export path) | N/A (story modified zero shared types or zero re-export sites).

**Defense-in-depth precedent (information-disclosure layer):** when a producer-boundary guard is missed, the raw runtime exception text should never reach the client. Add or verify a structural backup: an HTTP exception filter that, for `status >= 500`, suppresses raw `exception.message` and emits a generic `'An unexpected error occurred'`; 4xx pass-through unchanged. Document any new 5xx-emitting code path against this contract.

**Legitimate exceptions:**

- **§5.10.a** — value originates from an ORM `findFirst`/`findUnique` result on a typed column (the ORM already enforces the column type at the DB boundary). N/A for that producer.
- **§5.10.b** — the modified service returns a primitive type (string, number, boolean) — no shared ORM type is co-emitted. N/A for that response shape.

**N/A justification:** ANY of the following:

- "Story did not modify any normalizer/DTO/service feeding a typed ORM column AND did not modify a service returning an ORM row to an HTTP client" — explicitly state both halves.
- "All §5.4-audited types are returned as primitives only (no co-emission with other shared ORM types)" — list the response shapes verified.
- "Story is documentation-only / fixture-only / test-infrastructure-only and produces no runtime values consumed by typed columns or HTTP responses" — explicitly state.

---

## 5.11 — Git-evidence consistency check

Sibling rule to §5.9. Where §5.9 verifies cited figures via runnable commands at write-time, §5.11 verifies the dev pass's working-tree state against the story's declared scope at pre-review-gate time. Three sub-checks. Each takes < 2 minutes to run.

**Catches:** the meaningful fraction of code-review findings that retros surface as "this could have been caught earlier." Where retrospective-time tooling catches them at epic-close, §5.11 catches them at pre-review-gate time, before the code-review subagent ever spawns.

**When this check applies:** every story at pre-review-gate time, with three N/A exceptions enumerated at the end of this section. The check fires AFTER dev-pass finishes, BEFORE the code-review subagent spawns.

### 5.11.a — File-List-vs-working-tree consistency

```bash
git status --porcelain
git diff --cached --name-only
```

For each entry in the story's `### File List`, verify it appears in either output above (status `M`, `A`, `D`, or `??` for untracked-pending-add; or in `--cached --name-only` for staged paths). For each path in the git output NOT in the File List, classify:

- **STAGED + IN FILE LIST** ✅ — expected; no action.
- **STAGED + NOT IN FILE LIST** ❌ FLAGGED — silent scope-creep. Resolution: (i) add to File List if story-adjacent, OR (ii) unstage with `git restore --staged <path>` if unrelated background work.
- **UNTRACKED + NOT IN FILE LIST** — informational; only FLAGGED if the file is under the story's logical scope (story-adjacent test fixture, snapshot, generated artifact). Genuinely unrelated background work passes silently.
- **IN FILE LIST + NOT IN GIT OUTPUT** ❌ FLAGGED — declared but not touched. Resolution: (i) remove from File List if the AC was descoped, OR (ii) implement the missing touch.

**Required output:**

```text
git status --porcelain output: [paste]
git diff --cached --name-only output: [paste]
File List declared paths: [list from story file ### File List]
Cross-reference verdict:
  <backend-src>/services/foo.service.ts   STAGED + IN FILE LIST   ✅
  <backend-src>/services/__tests__/foo.spec.ts   STAGED + IN FILE LIST   ✅
  <backend-src>/services/bar.service.ts   STAGED + NOT IN FILE LIST   ❌ FLAGGED — silent scope-creep
Verdict: ⚠️ FLAGGED — 1 silent-scope-creep instance. Resolution: add to File List (line 47).
```

### 5.11.b — Production-only test-to-code ratio (live, not retro-time)

```bash
git diff --cached --numstat
```

Apply a test-vs-docs classifier:

- `testAdded` = sum of `added` for paths matching `/(\/__tests__\/|\.(spec|test|e2e)\.(t|j)sx?$)/i` (adjust the regex for your project's test naming conventions). **Python-stack regex:** `/^tests\/|\/tests\/|\/test_[^\/]+\.py$|\/[^\/]+_test\.py$|\/conftest\.py$/` — matches pytest's discovery rules (top-level `tests/` directory, nested `tests/` dirs, `test_*.py` modules, `*_test.py` modules, and `conftest.py` fixture files). **MailBot-specific:** per the architecture's source-tree decision, tests live in `tests/unit/` and `tests/integration/` mirroring `mailbot_api/` — co-located tests are forbidden. The regex above covers both conventions.
- `docsAdded` = sum of `added` for paths matching `\.(md|mdx)$` anywhere OR `\.(ya?ml|json)$` under your project's docs / planning directories. **MailBot-specific:** also include `\.sql$` under `mailbot_api/db/migrations/` — migration files are schema-as-code, not production logic, but they're also not tests; treat them as docs for ratio purposes (otherwise a pure schema-migration story would trip the gate with 0% test ratio).
- `prodAddedExcludingDocs` = (total non-test added) − `docsAdded`
- `prodOnlyTestRatio = testAdded / prodAddedExcludingDocs` (null if denominator 0)

If `prodOnlyTestRatio < 0.3` AND `prodAddedExcludingDocs > 0`, FLAG in §2 of pre-review. Resolution paths:

- (i) **Add tests now** — preferred when the missing coverage is structural (untested branch, new public API surface, new error path).
- (ii) **Explicit `[deferred:reason]` note** — acceptable when the coverage gap is tooling-shaped (e.g., refactor with no behavior change; new file that's tested transitively via a higher-level integration test) AND the rationale is auditable.

**Required output:**

```text
git diff --cached --numstat (test-classifier applied):
  testAdded: 47
  docsAdded: 12
  prodAddedExcludingDocs: 138
  prodOnlyTestRatio: 47 / 138 = 0.341
Threshold: 0.3
Verdict: ✅ PASS — 0.341 ≥ 0.30
```

Or under FLAG conditions:

```text
git diff --cached --numstat (test-classifier applied):
  testAdded: 8
  docsAdded: 4
  prodAddedExcludingDocs: 142
  prodOnlyTestRatio: 8 / 142 = 0.056
Threshold: 0.3
Verdict: ⚠️ FLAGGED — 0.056 < 0.30. Resolution: (i) [list of test files to add] OR (ii) [deferred:reason].
```

### 5.11.c — No-later-commits-under-attribution

```bash
git log --since="<story.status-flipped-in-progress timestamp>" --oneline -- <File-List-paths>
```

The story's `Status` flipped from `ready-for-dev` → `in-progress` at a moment captured in the sprint-status.yaml inline comment. After that moment, any commit touching the story's File List that is NOT the dev-pass's own work-in-progress is a "honest-rescope before status flip" violation in real-time. The check catches the violation at pre-review-gate time vs. waiting for the retro digest to surface it at epic-close.

For typical autonomous-epic-run flows where the dev pass + commit happens in the same session, this check is N/A (the story never left the dev's working tree). It fires when (a) the dev pass spans multiple sessions, (b) the story file flipped to `in-progress` days before the commit, or (c) parallel work on a sibling story modified files that overlap this story's File List.

**Required output:**

```text
Story status-flip timestamp (from sprint-status.yaml inline comment): <YYYY-MM-DD>
git log --since="<YYYY-MM-DD>" --oneline -- [File-List paths]:
  [paste output — empty for same-session dev passes]
Verdict: ✅ PASS — no commits under attribution since flip
```

Or under FLAG conditions:

```text
Story status-flip timestamp: <YYYY-MM-DD>
git log --since="<YYYY-MM-DD>" --oneline -- <backend-src>/services/foo.service.ts:
  88f11a0 chore(misc): unrelated tooling commit touching foo.service.ts (<later-date>)
Verdict: ⚠️ FLAGGED — commit `88f11a0` landed under attribution after status-flip. Resolution: either (i) honest-rescope this story's File List to acknowledge the prior commit's overlap, OR (ii) document why the prior commit is covered by an existing AC.
```

**N/A justification:** ANY of the following:

- **Documentation-only story** with no source-code File List entries — §5.11.b is trivially N/A (no prod code), and §5.11.a still applies but is usually clean.
- **Single-session dev pass** with no `git log` history under the story's File List paths between status-flip and the pre-review run — §5.11.c trivially N/A.
- **Story is a tooling/skill story** modifying only infrastructure files — §5.11.b N/A (the classifier counts these as docs), §5.11.a still applies.

**Sibling rule cross-reference:** §5.11 is the working-tree-evidence complement to §5.9 (cited-figures verification). §5.9 anchors numeric claims to command output at write-time; §5.11 anchors the story's declared scope to git's actual state at pre-review-gate time. Together: §5.9 (quantitative cite anchoring) + §5.11 (scope-claim anchoring) close the "dev pass says X but git shows Y" failure mode.

---

## 5.12 — CR-cadence-mandatory surface classification

**Catches:** the orchestrator (or a future dev pass) deciding under context pressure that the code-review subagent dispatch is skippable for a high-impact story, when the story actually touches a surface that other epics will lean on or that enforces a privacy / authorization invariant. Retroactive CR debt is the dominant Epic 4 retro finding (action item #2) — this check makes the cadence decision binary and recorded BEFORE the orchestrator can reach Step 2.4's dispatch.

**Why this exists:** Epic 3 retro action #1 documented six CR-mandatory criteria as guidance. Epic 4 ran the exact predicted failure mode anyway — Stories 4-4 (drainer) and 4-7 (sensitivity-token handshake) shipped without CR under context pressure, even though both criteria matched. Adam's Epic 4 retro decision (2026-06-02, action item #1): **option A — codify in skill as a hard gate, not aspirational text.** §5.12 is that gate.

**The six criteria — a story is `MANDATORY-CR` if ANY apply:**

1. **Boundary-introducing.** Adds a new writer-monopoly, new lint boundary, new allowlist in `scripts/check_boundaries.py`, or a new shared invariant that other modules will be checked against (e.g., a new enum + bare-string-literal lint check).
2. **Dep-introducing.** Adds a new external dependency (new package, new adapter, new MCP server, new third-party API integration). The dep's behaviour now propagates through the codebase.
3. **Dev-self-flagged.** The dev pass itself flagged a concern in `## 4. Self-caught issues remediated this audit` that escalated to the reviewer rather than being fixed inline, OR the dev pass left a deferred item with `blocks: <future-story>`.
4. **Capstone.** The story is the last in its epic OR is explicitly a cross-story-collision story (multiple other stories' deliverables collide here at integration time — e.g., a draft-reply flow that touches 8+ prior stories).
5. **Privacy-invariant.** The story implements or modifies enforcement of any FR-2.3 / FR-2.5 / FR-5.7 surface, any NFR-PRIV-* requirement, or any AR-D12-* architecture rule. Project-specific invariant rules listed in the project's `architecture.md` count.
6. **Load-bearing-orchestrator.** The story ships a module that other epics will call as their primary integration surface — e.g., a continuous worker loop, a per-email pipeline orchestrator, a Router precondition layer, a dispatch table, an MCP server. "Other epics will call this" is the criterion, not "this is complex."

If NONE apply, the story is `GATE-COVERAGE-ELIGIBLE` — meaning the dev model + the four green gates (test / lint / type / boundary) are sufficient evidence for `done`, and the CR subagent can be skipped if context pressure or budget warrants. Gate-coverage-eligible is the default for mechanical CRUD on already-CR-cleared boundaries, prompt-module shims, schema-only migrations whose semantics another story already proved, and pure-doc stories.

**Run:** classify the story against each criterion using grep / story-spec reading. For each criterion that triggers, paste the evidence inline.

**Required output:**

```
Story surface classification:

Criterion 1 (boundary-introducing): YES — story ships `mailbot_api/actions/types.py` + extends `scripts/check_boundaries.py` with a new Tier-1/2/3 bare-string-literal lint check. Evidence:
  $ git diff --stat scripts/check_boundaries.py
  scripts/check_boundaries.py | 47 +++++++++++
Criterion 2 (dep-introducing): NO — no new deps in requirements.txt diff.
Criterion 3 (dev-self-flagged): NO — section 4 has no ESCALATE-TO-REVIEWER items.
Criterion 4 (capstone): NO — story 4-1 is the first in Epic 4 type-foundation phase.
Criterion 5 (privacy-invariant): NO — types module is authorization-shape only, no FR-2.5 surface.
Criterion 6 (load-bearing-orchestrator): YES — `ActionType` + `ACTION_PROPERTIES` + `tier_for` are the primary integration surface for every action-system story in Epic 4 (4-2 through 4-8) AND for Epic 5's MCP server tool registrations.

Cadence verdict: MANDATORY-CR (criterion 1 + criterion 6 both fire).
```

OR

```
Story surface classification:

Criterion 1 (boundary-introducing): NO — no new writer monopoly, lint boundary, or shared invariant.
Criterion 2 (dep-introducing): NO — no new external deps.
Criterion 3 (dev-self-flagged): NO — section 4 has no ESCALATE-TO-REVIEWER items.
Criterion 4 (capstone): NO — story 4-3 is mid-epic and only one other Epic-4 story (4-4) consumes it.
Criterion 5 (privacy-invariant): NO — grants are authorization-shape, no FR-2.5 / NFR-PRIV-* surface.
Criterion 6 (load-bearing-orchestrator): NO — mint_grant / is_grant_valid / revoke_grant are pure CRUD on a single table; the drainer (4-4) is the orchestrator, this story is its data layer.

Cadence verdict: GATE-COVERAGE-ELIGIBLE — no criterion fires; mechanical CRUD on Story 4-2's schema with strict validation.
```

**Anti-pattern:** verdict `GATE-COVERAGE-ELIGIBLE` with criterion 6 marked NO based on "the dev pass already covered it" or "the tests are comprehensive." Comprehensive tests are necessary for `done`; they are NOT what the criterion asks. The criterion asks "will OTHER epics call this as their primary integration surface?" — answer based on the epics-file / story-spec dependency graph, not on test count.

**Anti-pattern:** verdict `MANDATORY-CR` is downgraded to `GATE-COVERAGE-ELIGIBLE` after the fact because "the CR subagent timed out" or "context budget is tight." The verdict is BINDING at the time it is written into the pre-review artifact. Step 2.4 of the skill refuses to skip CR on a `MANDATORY-CR` story regardless of operational pressure; if context is genuinely insufficient, the orchestrator must halt and surface the gap to the user rather than silently downgrade.

**N/A justification:** none — this check ALWAYS runs and ALWAYS produces a verdict. Documentation-only stories are `GATE-COVERAGE-ELIGIBLE` (no code surface to review), but the verdict still gets pasted.

**Sibling rule cross-reference:** §5.12 is the gate-coverage-cadence anchor. The cadence verdict it produces is consumed by Step 2.4 of the orchestrator skill (the cadence-binding step). §5.12 produces the classification; Step 2.4 honors it. The "operational context-pressure skip" failure mode that Epics 3 and 4 demonstrated is closed by the two halves of this contract working together: §5.12 records what the cadence MUST be; Step 2.4 refuses to deviate.

---

## Posture Audit summary table

Closes section 5 of the pre-review artifact:

| Check                                                       | Status                                  |
| ----------------------------------------------------------- | --------------------------------------- |
| 5.1 Lockfile hygiene                                        | ✅ PASS \| ⚠️ FLAGGED \| N/A — <reason> |
| 5.2 Cross-doc pair verification                             | ✅ PASS \| ⚠️ FLAGGED \| N/A — <reason> |
| 5.3 Lifecycle string-uniqueness                             | ✅ PASS \| ⚠️ FLAGGED \| N/A — <reason> |
| 5.4 Multi-consumer impact scan                              | ✅ PASS \| ⚠️ FLAGGED \| N/A — <reason> |
| 5.5 Screenshot-based perception check                       | ✅ PASS \| ⚠️ FLAGGED \| N/A — <reason> |
| 5.6 Upstream-contract spec coverage                         | ✅ PASS \| ⚠️ FLAGGED \| N/A — <reason> |
| 5.7 Module-level mutable container                          | ✅ PASS \| ⚠️ FLAGGED \| N/A — <reason> |
| 5.8 Dev-fixture seed-vs-production-shape parity             | ✅ PASS \| ⚠️ FLAGGED \| N/A — <reason> |
| 5.9 grep-verify-cited-figures                               | ✅ PASS \| ⚠️ FLAGGED \| N/A — <reason> |
| 5.10 Producer-boundary contract enforcement                 | ✅ PASS \| ⚠️ FLAGGED \| N/A — <reason> |
| 5.11 Git-evidence consistency check                         | ✅ PASS \| ⚠️ FLAGGED \| N/A — <reason> |
| 5.12 CR-cadence-mandatory surface classification            | MANDATORY-CR \| GATE-COVERAGE-ELIGIBLE  |

If any check is FLAGGED, escalate to section 4 of the pre-review artifact (FIX NOW / ESCALATE TO REVIEWER / ACCEPT WITH RATIONALE).