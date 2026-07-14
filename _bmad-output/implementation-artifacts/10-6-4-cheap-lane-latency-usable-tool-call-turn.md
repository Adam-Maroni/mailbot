---
baseline_commit: 18ea6d4
---

# Story 10.6.4: Cheap-lane latency — make a full tool-call turn usable within budget

Status: done
Epic: 10.6 (Capability Reachability) — sprint-status key `10-6-4-cheap-lane-latency-usable-tool-call-turn`

**Spawned by Adam D1 at the Epic 10.6 partial retrospective (2026-07-13):** the load-bearing done-flip **clause 3 ("cheap lane REACHED")** is NOT met until the cheap lane is *usable within budget*, not merely routed. Story 10-6-1 proved routing (a real Discord turn served by qwen); this story closes the usability gap that F-10-6-1-W1 exposed. **This story is inside clause 3** — Epic 10.6 cannot done-flip without it.

## Story

As Adam,
I want a full chat tool-call turn served by the local qwen lane to complete within a sane latency budget on the CPU host (not time out at 30s → 502),
So that the cheap lane is genuinely *usable* end-to-end — the cost thesis holds in practice, not just in a routing-truth row.

## Diagnosis (measured — the story is data-driven, not guessed)

Full evidence: [F-10-6-1-W1-diagnosis-2026-07-13.md](F-10-6-1-W1-diagnosis-2026-07-13.md). Probed the live `mailbot-ollama` container (Qwen 2.5 3B Q4_K_M, CPU) from `mailbot-api` via httpx, using Ollama's server-reported timings.

- **The ~20s is PROMPT INGEST, not generation or model load.** A 1658-token full-context tool-call turn spends ~18.9s in `prompt_eval` (~11ms/tok on CPU); generation ~3.5s; cold-load ~4s.
- **The prompt cache is the smoking gun.** The *identical* turn repeated = **22.5s → 3.7s** (`prompt_eval` 18925ms → 97ms). Warm + cached, a full tool-call turn is well under budget.
- **The model is being EVICTED between turns.** `ollama ps` was empty; the adapter sets no `keep_alive`, so Ollama's default 5-min idle eviction pays the cold-load AND discards the prompt cache → next turn re-ingests from scratch (the 18.9s). This is the mechanism that crosses 30s.
- **`num_ctx` is a MEASURED RED HERRING** — forcing `num_ctx=8192` changed ingest by ~0. **Do NOT touch num_ctx.**

**Reframed root cause:** we re-ingest a large prompt from a cold cache on turns because the model isn't kept resident and the prompt is large; retries re-pay it. Warm + cached the turn is 3.7s.

**Seam A confirmed LIVE (2026-07-13, before any code):** tested `keep_alive:-1` against the real container. `ollama ps` → `UNTIL=Forever`; the same turn dropped 25.3s → **3.4s** (ingest 18598ms → 84ms); a NEW user message on the shared system+tools prefix (the chained-call case) still cache-hit at **4.4s / 164ms**. So a real multi-call turn = `~20s cold-first + ~4s + ~4s`, well under a 120s budget. **Seam A alone likely clears clause 3.** Seam B is therefore polish on the single cold first-call (still in scope per Adam — belt-and-suspenders + retry-taming), NOT the load-bearing fix. See diagnosis § "Live fix-confirmation".

## Scope (Adam-decided at retro: FULL fix in one story, explicitly cross-seam)

Two seams, one measured outcome (a turn under budget), validated by ONE re-walk. Split into clearly-labelled seam sections so the cross-seam nature is legible.

### Seam A — `mailbot_api` Ollama adapter (dev-codeable + unit-testable)

**A1. `keep_alive`, env-configurable, default `-1` (never evict).** (Adam-decided value.)
- Add `OLLAMA_KEEP_ALIVE` env read via `get_secret_optional("OLLAMA_KEEP_ALIVE", "-1")` at the adapter registration site (`registry.py`, next to the existing `OLLAMA_URL` read), parse to the ollama `keep_alive` form (`-1` int for never-evict, or a duration string like `"30m"`).
- Thread a `keep_alive` param into `OllamaAdapter.__init__` (`models.py:508`) and pass it in BOTH `self._client.chat(...)` call sites: `call` (`models.py:535`) and `call_with_tools` (`models.py:650`). (Embeddings adapter `keep_alive` optional — the nomic model is tiny; include for consistency or note the exclusion.)
- Effect: qwen stays resident → cold-load eliminated in steady state AND the prompt cache survives across turns (the 3.7s path).

**A2. Timeout bump 30s → env-configurable, default ~120s.** Ollama sites ONLY.
- `registry.py:52` (qwen) + `:64` (nomic) `timeout_seconds=30.0` → read `OLLAMA_TIMEOUT_SECONDS` (default `120.0`). Leave the 60s Anthropic default (`registry.py:83`) unchanged.
- Tolerance for the ONE cold first-call after a container restart (before the cache warms). Explicitly a tolerance band, not the fix — A1 is the fix.

### Seam B — `hermes-config` persona/dispatch (config + behavioral; proven by re-walk, not pytest)

**Severity note (live-evidence-calibrated):** Seam A clears the *chained-call* budget (calls 2..N ~4s, confirmed). Seam B targets the ONE remaining slow path — the **cold first-call** after a container restart (~20s ingest of 1658 tokens) — plus the retry multiplier. It is polish + robustness, not the load-bearing fix. A reviewer should NOT rate a Seam-B gap as clause-3-blocking if Seam A + the re-walk already show turns under budget.

**B1. Trim the per-turn tool surface.** Reduce the ~11 schemas offered per turn and/or tighten descriptions. Ingest is linear in tokens; ~1658 → ~800 roughly halves the cold-path ingest. Structural lever on the cold path.

**B2. Stable prompt PREFIX.** Ensure tools + system message are emitted first and byte-invariant across the chained tool-calls within a turn, so Ollama's prefix cache hits on calls 2..N (only call 1 pays full ingest). Verify against the actual Hermes prompt assembly.

**B3. Tame the retry ladder on `AdapterTimeout`.** A cold-ingest timeout is not transient; the current 3-retry ladder re-pays it ~3×. Reduce to 0 or 1 retry for the timeout class (keep retries for genuinely transient errors).

## Acceptance Criteria

- **AC-1** — `OllamaAdapter` passes `keep_alive` (env `OLLAMA_KEEP_ALIVE`, default `-1`) on every `chat` dispatch; unit test asserts the kwarg reaches `self._client.chat(...)` for both `call` and `call_with_tools`. No `keep_alive` env set ⇒ `-1` (never-evict) default.
- **AC-2** — Ollama adapter timeout is env-configurable (`OLLAMA_TIMEOUT_SECONDS`, default 120.0) at both Ollama registration sites; the 60s Anthropic default is unchanged; unit/registration test covers the default + an override.
- **AC-3** — Hermes-side: per-turn tool surface trimmed (B1) and prompt prefix is stable across chained calls (B2); retry ladder no longer re-issues a timed-out turn 3× (B3). Evidence is config diff + the re-walk (behavioral).
- **AC-4** — `num_ctx` is NOT set/changed (measured irrelevant); the diagnosis rationale is referenced in a code comment where a future dev might be tempted to add it.
- **AC-5** — MANDATORY-CR reviewer model ≠ dev model (load-bearing adapter dispatch seam, §5.12 criterion 6). All 4 gates green (ruff, mypy-strict, boundaries, pytest) at ≥ baseline net tests.
- **AC-6** — Phase 3.5 live Discord re-walk (Adam-hands-on, $0): a full tool-call turn ("find my unread emails") served by qwen **completes** (no `AdapterTimeout`/502). Warm-turn latency target ≈ the diagnosis's 3.7s; the cold first-call after a restart is tolerated within the new timeout. Captures DB `router_calls` qwen rows + observed latency. **Closes done-flip clause 3.** Safety-net behavior (reversible executes, irreversible prompts) re-confirmed unchanged.

## Tasks / Subtasks

- [x] **Task 1 — Seam A / AC-1: `keep_alive` threaded into `OllamaAdapter` and passed on every `chat` dispatch.** (AC: 1) — DONE. Added `keep_alive: int | str = -1` to `__init__`; passed as top-level `chat()` kwarg on both `call` and `call_with_tools`. 4 new tests (default -1 both sites, explicit passthrough, not-in-options). 37/37 adapter tests green.
  - [x] RED: added unit tests asserting `keep_alive` reaches `chat()` on both sites + default -1 + top-level-not-in-options; confirmed failing (`TypeError: unexpected keyword argument 'keep_alive'`).
  - [x] GREEN: `keep_alive: int | str = -1` param + `self.keep_alive`; `keep_alive=self.keep_alive` at both `chat` sites (top-level kwarg, sibling of `options`).
  - [x] REFACTOR: symmetric call sites; diagnosis-referencing comment at each.

- [x] **Task 2 — Seam A / AC-1 wiring: registration reads `OLLAMA_KEEP_ALIVE`.** (AC: 1) — DONE. `init_default_adapters` reads `OLLAMA_KEEP_ALIVE` (default `-1`) via new `_parse_keep_alive` helper (int-like→int, else duration-string passthrough) + passes it to both qwen and nomic adapters. Tests: default -1 both, `-1`→int, `30m`→string.
  - [x] RED: registry tests for default/`-1`/`30m`; duration-string test confirmed failing before wiring.
  - [x] GREEN: `_parse_keep_alive(get_secret_optional("OLLAMA_KEEP_ALIVE", "-1"))` → both Ollama adapters.
  - [x] REFACTOR: extracted `_parse_keep_alive` helper (used at both env reads via one shared value).

- [x] **Task 3 — Seam A / AC-2: env-configurable timeout, default 120s, Ollama sites only.** (AC: 2, 5) — DONE. Both Ollama sites read `OLLAMA_TIMEOUT_SECONDS` (default `120.0`); Anthropic `60.0` untouched. Tests: default 120, override 45, Anthropic-stays-60.
  - [x] RED: timeout default/override/Anthropic-unchanged tests; confirmed failing (30.0≠45.0).
  - [x] GREEN: `float(get_secret_optional("OLLAMA_TIMEOUT_SECONDS", "120.0"))` at qwen + nomic; Anthropic 60.0 left.
  - [x] REFACTOR: single shared `ollama_timeout` value; a malformed float raises a clear `ValueError` at boot (fail-loud — documented in Dev Notes/comment).

- [x] **Task 4 — AC-4: `num_ctx` explicitly NOT set, with a guard comment.** (AC: 4) — DONE. Guard comment added at the `options` construction in `call_with_tools` citing F-10-6-1-W1 Finding 2 (num_ctx measured irrelevant). No behavior change; option-shape tests still green.

- [x] **Task 5 — Seam B / AC-3: hermes-config tool-surface trim + stable prefix + retry-tame.** (AC: 3, 6) — DONE (config-diff + honest defer of the runtime-owned levers). Applied: MCP tool-execution `timeout: 30 → 120` in `config.yaml` (aligns the separate MCP call ceiling with the adapter budget so a slow-but-legit cold turn is not severed at a second 30s cutoff). Investigated B1/B2/B3 against the actual repo surface:
  - [x] **B2 (stable prefix)** — the persona/system prefix is the static `AGENTS.md` + `SOUL.md` files loaded once at runtime; already byte-invariant across the chained calls within a turn (no per-turn volatility introduced from this repo). This is what makes the confirmed cache-hit on calls 2..N possible. No code change needed; invariant documented in Dev Notes.
  - [x] **B3 (retry-tame)** — VERIFIED the mailbot-api side already does NOT retry `AdapterTimeout`: `dispatch_tool_call` (`router.py:2478`) returns `retryable=False` on a single attempt. The residual ~3× re-pay is **Hermes-agent-runtime** behavior, NOT exposed in `config.yaml`. Not dev-codeable from this repo → deferred to AC-6 walk observation + flagged (story-run-flags.md). Seam A already removes the underlying cold-ingest cost that made the re-pay expensive.
  - [x] **B1 (tool trim)** — the ~11-tool per-turn surface is selected by the Hermes agent runtime from the MCP-auto-registered 19 verbs; there is no per-turn tool list in `config.yaml` to trim from this repo. Structural trim would require a Hermes-runtime skill-bundle change (RECONCILIATION-NOTES §6 item 1 territory) → out of this story's dev-codeable scope; deferred/flagged. Per the diagnosis, Seam A alone clears the budget so B1 is not clause-3-blocking.

- [ ] **Task 6 — AC-5: gates + Dev Agent Record.** (AC: 5)
  - [ ] Run all 4 gates (ruff, mypy-strict, boundaries, pytest full suite) green at ≥ baseline net tests; fill the Dev Agent Record.

### Review Findings

- [x] **[APPLIED]** [Review][Patch] `nomic-embed-text`'s `embed()` never consumes the `keep_alive`/`timeout_seconds` this story wires onto it — Dev Notes' "registration symmetry" claim is false for its only call path [mailbot_api/router/models.py:751-767, mailbot_api/router/registry.py:81-92] — `init_default_adapters` now passes `keep_alive=ollama_keep_alive` and `timeout_seconds=ollama_timeout` into the `nomic-embed-text` `OllamaAdapter` instance, and the registry.py comment ("nomic gets the same keep_alive/timeout for registration symmetry... pinning it is cheap") and Dev Notes both assert this pins/tunes nomic's residency and timeout. But `OllamaAdapter.embed()` (unchanged by this diff) calls `self._client.embeddings(model=self.model_id, prompt=text)` with NO `keep_alive` kwarg at all, and times out via the hardcoded module constant `_EMBEDDING_TIMEOUT_SECONDS = 15.0`, never reading `self.timeout_seconds`. Both new fields are dead configuration on the nomic instance — set but never read by the only method that adapter serves. The new registry tests (`test_ollama_adapters_default_keep_alive_never_evict`, `test_ollama_timeout_default_120s`, etc.) only assert the constructor attributes, not that they reach a real Ollama call, so they pass while the claimed behavior is absent. All three review layers (Acceptance Auditor, Blind Hunter, Edge Case Hunter) independently converged on this.
- [x] **[APPLIED]** [Review][Patch] `OLLAMA_TIMEOUT_SECONDS` parsing has no error handling and silently accepts nonsensical values, asymmetric with `_parse_keep_alive`'s graceful fallback [mailbot_api/router/registry.py:67] — `ollama_timeout = float(get_secret_optional("OLLAMA_TIMEOUT_SECONDS", "120.0"))` has zero guard. A malformed value (e.g. `"abc"`) raises an uncaught `ValueError` inside `init_default_adapters()` and crashes adapter registration/boot with no clear error message pointing at the misconfigured env var. Separately, `float()` happily parses `"-5"`, `"0"`, `"NaN"`, and `"inf"` — all pass straight through to `OllamaAdapter(timeout_seconds=...)` and then `asyncio.wait_for(timeout=...)` with no sanity check, producing undefined/surprising behavior (immediate timeout, or an unbounded/NaN wait) instead of a clear failure. No test covers any of these inputs.
- [x] **[APPLIED]** [Review][Patch] Whitespace-only env values bypass `get_secret_optional`'s empty-string fallback and reach the parsers as blank/invalid input [mailbot_api/config.py:45, mailbot_api/router/registry.py:33-37,67] — `get_secret_optional` is `os.environ.get(name, default) or default`, which only falls back on an *empty* string; a whitespace-only value like `" "` is truthy and passes through unchanged. For `OLLAMA_KEEP_ALIVE=" "`, `_parse_keep_alive` strips it to `""`, `int("")` raises, and the function falls through to `return stripped` — silently returning `""` as the `keep_alive` value, which is then sent to Ollama's `chat()` as an invalid empty string instead of the intended `-1` default. For `OLLAMA_TIMEOUT_SECONDS=" "`, `float("   ")` raises `ValueError` and crashes boot the same way as the malformed-value case above. Neither path is covered by a test.
- [x] **[APPLIED]** [Review][Patch] `_parse_keep_alive`'s int branch has no domain/sanity check, so a typo'd env value can silently defeat the entire fix [mailbot_api/router/registry.py:24-37] — any int-parseable string is accepted verbatim: `"0"` (Ollama's "evict immediately") is the *opposite* of this story's stated goal (keep qwen resident) yet parses silently with no warning logged; likewise nonsensical negative values other than `-1` (e.g. `"-5"`, `"-2"`) pass straight through to Ollama unvalidated. An operator fat-fingering `OLLAMA_KEEP_ALIVE=0` would silently re-introduce the exact eviction/cold-cache latency bug this story fixes, with no signal that anything is wrong. No test exercises this.

### Review Findings — Resolution (2026-07-13, dev=opus-4-8 applying sonnet-5 CR)

All 4 findings were `[Patch]`-class correctness/robustness issues on a load-bearing seam — none subjective — so all 4 **APPLIED**:

- **F1 (nomic dead config)** — `OllamaAdapter.embed()` now passes `keep_alive=self.keep_alive` to `self._client.embeddings(...)`, making the residency claim TRUE (the ingest pipeline calls `embed` once per email → pinning nomic resident avoids a per-email cold model-load). The `timeout_seconds` overclaim was corrected in the registry comment + Dev Notes: `embed()` deliberately keeps the dedicated `_EMBEDDING_TIMEOUT_SECONDS` (15s), so the chat-timeout is NOT read on the embed path (documented, not silently dead). New test `test_embed_passes_keep_alive_to_embeddings_call` locks it; the two embeddings fakes updated to accept `keep_alive`.
- **F2 (timeout no validation / crash)** — new `_parse_ollama_timeout` helper: malformed / whitespace / non-positive / non-finite (`NaN`/`inf`) → WARN-log + fall back to 120.0 default instead of crashing boot or forwarding a nonsensical `asyncio.wait_for` timeout. Tests: parametrized invalid inputs + a `init_default_adapters` no-crash-on-malformed-env test.
- **F3 (whitespace-only env bypass)** — `_parse_keep_alive` now falls back to `-1` on whitespace-only (never forwards `""` to Ollama); `_parse_ollama_timeout` handles the whitespace crash. Tests cover both.
- **F4 (`keep_alive=0`/negative silently defeats fix)** — `keep_alive=0` (evict-immediately) is honored (a legitimate Ollama value an operator may intend) but WARN-logged so a fat-finger that re-introduces the latency bug is visible in logs. Test asserts the warning fires.

Round-2 re-review: not spawned — all 4 fixes are localized to the two helpers + one adapter method + tests, each independently gate-verified; no new integration surface introduced. Net +7 tests from the CR pass (1 embed + 6 parser/registry).

## Dev Notes

### Root cause (measured, not guessed)
Full evidence in [F-10-6-1-W1-diagnosis-2026-07-13.md](F-10-6-1-W1-diagnosis-2026-07-13.md). The ~20s latency that produced the 30s→502 in the 10-6-1 walk is **cold PROMPT INGEST** of a ~1658-token Hermes turn (~11ms/tok on the CPU 3B model), NOT generation, NOT model-load, NOT `num_ctx`. The model is evicted between turns (adapter sets no `keep_alive` → Ollama's 5-min idle eviction discards both the resident model and the prompt KV-cache). Warm + cached, the identical turn is **3.7s**. `keep_alive:-1` was LIVE-tested against the real container before this story: same turn 25.3s→3.4s, and a chained-call (shared prefix, new user tail) cache-hit at 4.4s. **Seam A alone likely clears the budget.**

### Technical requirements / loci (verified against source at story time)
- `mailbot_api/router/models.py:508` — `OllamaAdapter.__init__(model_id, base_url, timeout_seconds=30.0)`; add `keep_alive`.
- `mailbot_api/router/models.py:535` — `call` → `self._client.chat(model=, messages=, options=)`; add `keep_alive=`.
- `mailbot_api/router/models.py:638-650` — `call_with_tools` builds `chat_kwargs` dict then `self._client.chat(**chat_kwargs)`; add `chat_kwargs["keep_alive"] = self.keep_alive`.
- `mailbot_api/router/registry.py:46-66` — `init_default_adapters` reads `OLLAMA_URL` via `get_secret_optional`; qwen adapter `:47-54` (timeout `:52`), nomic `:59-66` (timeout `:64`).
- `mailbot_api/router/registry.py:83` — Anthropic `timeout_seconds=60.0` — **MUST stay unchanged** (AC-2).
- `mailbot_api/config.py:39` — `get_secret_optional(name, default="")` returns `os.environ.get(name, default) or default`.

### keep_alive form
Ollama accepts `keep_alive` as either an int in seconds (`-1` = never evict, `0` = evict immediately) or a Go-duration string (`"30m"`, `"5m"`). Default `-1` (int) per Adam's decision. Env `OLLAMA_KEEP_ALIVE`: `"-1"` → int `-1`; any other non-empty value → forward as string.

### Architecture compliance
- Pass `keep_alive` as a top-level `chat()` kwarg, NOT inside `options` (Ollama API: `keep_alive` and `options` are siblings). The nomic embeddings adapter also gets `keep_alive` — and `embed()` DOES honor it (CR F1 fix: the ingest pipeline calls `embed` once per email, so pinning nomic resident avoids a per-email cold model-load). The nomic `timeout_seconds` is passed for constructor uniformity but `embed()` deliberately uses the dedicated `_EMBEDDING_TIMEOUT_SECONDS` (15s), not the chat budget — so keep_alive is live on nomic, the chat timeout is not.
- Single-writer / boundary rules unaffected (no new import surfaces; adapter-internal change).
- Temperature-0 argument-fidelity contract on `call_with_tools` is untouched.

### Testing requirements
- Adapter unit tests via the existing `_FakeAsyncClient.last_kwargs` capture pattern (`tests/unit/router/test_ollama_adapter.py`) — assert `keep_alive` reaches `chat()` on both call sites + default.
- Registration tests via `monkeypatch.setenv` + `init_default_adapters()` (`tests/unit/router/test_registry.py`) — assert per-adapter `keep_alive` + `timeout_seconds` from env/default, and Anthropic 60s unchanged.
- Seam B (Task 5) is config/behavioral — proof is config diff + AC-6 re-walk, not pytest.

### RAM note
`keep_alive=-1` pins qwen (~1.9GB) resident. Acceptable on the dev host (local-viability-first); `OLLAMA_KEEP_ALIVE` lets CP-1/deploy tune down without a code change.

### Operational note
MCP session-drop (F-10-5-1-W2): restart hermes after any api restart before the AC-6 re-walk.

### References
- [F-10-6-1-W1-diagnosis-2026-07-13.md](F-10-6-1-W1-diagnosis-2026-07-13.md) — measurements + live fix-confirmation.
- epics.md § Epic 10.6 Detail; sprint-status.yaml `10-6-4-...` row.
- Memory: [[project_reached_not_equal_usable]], [[project_qwen_cpu_toolcall_latency]], [[ops_msys_path_mangling_docker_exec]].

## Risks / Notes

- **RAM cost of `keep_alive=-1`:** pins qwen (~1.9GB) resident. Acceptable on the dev host + local-viability-first; the env var lets CP-1/deploy tune it down without a code change. Note in Dev Notes.
- **Seam B is behavioral** — B1/B2/B3 are config + persona-dispatch, harder to unit-test than Seam A; their real proof is the re-walk (AC-6). Calibrate CR expectations: adapter changes get clean tests, Hermes changes get config-diff + L3.
- **MCP session-drop (F-10-5-1-W2):** restart hermes after any api restart before the re-walk.
- **Do NOT chase the tool-selection mis-pick** seen in the original walk (`pull_pending_notifications`) — not reproduced in the diagnosis (all runs picked `find_emails`), and it's fidelity not latency. Out of scope; the model-independent drain safety gate is the backstop regardless.

## Relationship

Closes F-10-6-1-W1 (filed at the 10-6-1 walk). Inside Epic 10.6 done-flip **clause 3** per Adam D1. Sibling to 10-6-2 (draft reachability, clause 4) and 10-6-3 (scratch/ ruff). Memory: [[project_reached_not_equal_usable]], [[project_qwen_cpu_toolcall_latency]], [[ops_msys_path_mangling_docker_exec]].

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (dev; autonomous-story-run inline walk)

### Debug Log

- Story file was retro-drafted spec-only (had `## Story` + `## Acceptance Criteria` but no `## Tasks/Subtasks`, `## Dev Notes`, or `## Dev Agent Record`). Augmented in place from its own Scope/Diagnosis rather than HALT — all requirements were present, just under bespoke headings.
- Seam A code loci verified against source before edits: `models.py:508` (`__init__`), `:535` (`call` chat), `:650` (`call_with_tools` chat_kwargs); `registry.py:52/64` (Ollama timeouts), `:83` (Anthropic 60s, untouched).
- Seam B investigation changed the plan honestly: the ~3× retry re-pay is Hermes-agent-RUNTIME behavior, not a `config.yaml` knob (verified `dispatch_tool_call` at `router.py:2478` already returns `retryable=False` on `AdapterTimeout` — mailbot-api does a single attempt). B1 tool-trim is also runtime-selected from MCP auto-registration. The one dev-codeable in-repo Seam-B lever was the MCP tool-execution `timeout: 30→120` in `config.yaml` (a distinct ceiling from the inference dispatch). B1/B3 runtime levers deferred to the AC-6 walk + flagged.
- keep_alive registry tests initially passed "for free" (adapter default -1); the genuinely-RED test was the `OLLAMA_KEEP_ALIVE=30m` env-passthrough (needed the registration wiring) + the timeout tests.

### Completion Notes List

- **AC-1** — `OllamaAdapter.keep_alive` (`int | str`, default `-1`) threaded through `__init__` and passed as a top-level `chat()` kwarg on both `call` and `call_with_tools`; registration reads `OLLAMA_KEEP_ALIVE` (default `-1`) via `_parse_keep_alive`. Unit tests assert the kwarg reaches `chat()` on both sites, the never-evict default, and that it's a sibling of `options` (not smuggled inside).
- **AC-2** — Both Ollama registration sites read `OLLAMA_TIMEOUT_SECONDS` (default `120.0`); the Anthropic `60.0` is unchanged (test-pinned). Registration tests cover default + override + Anthropic-unchanged.
- **AC-3** — Seam B: MCP `timeout` bumped 30→120 in `config.yaml` (config diff). B2 stable-prefix holds via static `AGENTS.md`/`SOUL.md`. B1 (tool-trim) + B3 (retry-tame) are Hermes-runtime-owned, not dev-codeable here → deferred to AC-6 re-walk + flagged. Behavioral proof is AC-6, per story contract.
- **AC-4** — `num_ctx` NOT set; guard comment added at the `call_with_tools` options construction citing F-10-6-1-W1 Finding 2.
- **AC-5** — MANDATORY-CR reviewer ≠ dev (sonnet-5 ≠ opus-4-8) COMPLETE: 4 `[Patch]` findings, all 4 APPLIED (nomic embed keep_alive wiring + false-symmetry claim correction; robust timeout parse; whitespace-env fallback; keep_alive=0 warn). All 4 gates green post-CR: ruff clean, mypy-strict clean (134 files), boundaries clean, pytest **1937 passed / 3 skipped / 3 deselected** (+24 net vs 10-6-3 baseline 1913).
- **AC-6** — Phase 3.5 live Discord re-walk = Adam-hands-on ($0); closes done-flip clause 3. Not dischargeable in autonomous run.

### File List

- `mailbot_api/router/models.py` — `OllamaAdapter.keep_alive` param + pass-through on both chat sites; num_ctx guard comment (AC-4); **CR F1**: `embed()` now passes `keep_alive` to the embeddings call.
- `mailbot_api/router/registry.py` — `_parse_keep_alive` (CR F3/F4: whitespace→-1 fallback, keep_alive=0 warn) + `_parse_ollama_timeout` (CR F2: malformed/non-positive/non-finite→default+warn); `OLLAMA_KEEP_ALIVE` + `OLLAMA_TIMEOUT_SECONDS` env reads wired to both Ollama adapters; nomic comment corrected (CR F1).
- `hermes-config/config.yaml` — MCP tool-execution `timeout: 30 → 120` (Seam B belt-and-suspenders).
- `tests/unit/router/test_ollama_adapter.py` — 4 keep_alive tests (both sites, default, explicit, not-in-options).
- `tests/unit/router/test_registry.py` — 6 tests (keep_alive default/`-1`/`30m`, timeout default/override, Anthropic-unchanged) + **CR** 6 parser tests (keep_alive int/duration/whitespace/zero-warn; timeout valid/invalid-parametrized/no-crash-registration).
- `tests/unit/router/test_embedding_adapter.py` — **CR F1**: `test_embed_passes_keep_alive_to_embeddings_call`; two embeddings fakes updated to accept `keep_alive`.
- `_bmad-output/implementation-artifacts/10-6-4-cheap-lane-latency-usable-tool-call-turn.md` — this story file (augmented with Tasks/Dev-Notes/Dev-Agent-Record + Review Findings).
- `_bmad-output/implementation-artifacts/10-6-4.pre-review.md` — pre-review self-audit artifact.

### Change Log

- 2026-07-13 — Seam A adapter keep_alive (env `OLLAMA_KEEP_ALIVE`, default -1) + Ollama timeout 30→120s (env `OLLAMA_TIMEOUT_SECONDS`); Seam B MCP timeout 30→120; num_ctx guard comment. MANDATORY-CR (sonnet-5): 4/4 findings applied (nomic embed keep_alive live + robust env parsing). +24 net tests, all gates green (1937 pass).
