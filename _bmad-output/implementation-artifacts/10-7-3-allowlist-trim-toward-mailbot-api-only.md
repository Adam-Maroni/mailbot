---
baseline_commit: 97534025f34128629e64542c5752b7b87c4560b5
---

# Story 10.7.3: Allow-list trim toward mailbot-api-only — scope the Discord chat surface to email-reading verbs

Status: done

## Story

**As** the MailBot operator (Adam) relying on the $0 local qwen lane to carry real tool-driven turns,
**I want** the Discord per-turn tool surface trimmed toward the MailBot email verbs — removing the mis-pickable `send_message` peer (from the `messaging` toolset) that qwen selects over `find_emails` —
**so that** a "find my unread emails" turn presents qwen a smaller, sharper menu dominated by email-reading verbs, improving its odds of firing the right tool (the load-bearing clause-3 fidelity goal) without a paid model or a second round-trip.

## Context & boundary honesty (read before implementing)

This story is the **`hermes-config` allow-list lever** identified by the 10.7.0 characterization spike (`10-7-0-spike-finding.md` §4.4 FINAL fire-list item 2) and epics.md § Epic 10.7 Detail. It extends 10.6.5's `platform_toolsets.discord` allow-list in `hermes-config/config.yaml`.

**What this lever CAN do (the achievable scope):**
- The Discord chat tool list is curated at **toolset granularity** by `platform_toolsets.discord` — Hermes enables only the listed toolsets on a per-turn Discord surface (`hermes_cli/tools_config.py` `_get_platform_tools`). Dropping the `messaging` toolset removes its `send_message` verb — the **exact mis-pick named in the epic headline** and in F-10-6-5-W1 defect #1 (qwen picks `send_message` from `messaging` over `find_emails`).

**What this lever CANNOT do (the honest boundary — must be stated, not papered over):**
- The spike's DOMINANT real-surface mis-pick is **`pull_pending_notifications`** (100% of wrong picks on the flat 26-verb surface, §1). That verb is registered **inside the `mailbot-api` MCP server**, not a separate toolset. `platform_toolsets.discord` keeps or drops WHOLE toolsets — dropping `mailbot-api` would drop all 26 email verbs *including `find_emails`*, defeating the purpose. **So this story CANNOT remove the `pull_pending_notifications` attractor via the allow-list.** Per-verb curation of the mailbot-api MCP surface is a *different seam* (`mcp_server.py` verb registration / a per-platform verb filter) and is **out of scope here** — it is filed as a residual (see Task 5), not silently absorbed.
- Therefore this story is a **partial selection lever**: it removes the `messaging`/`send_message` peer, shrinking the surface, but does NOT by itself get qwen to a small email-reading menu on the real Hermes path. The spike's §4.4 already measured that the flat-26 surface fails 0/N even *with* the 10.7.5 description rewrite; getting to a genuinely small menu (a real tree, or a mailbot_api verb-level scope) is the "remaining real engineering" the spike names — larger than this one config lever.

**Cost-of-removal weigh (why dropping `messaging` is not free):** the `messaging` toolset was kept in 10.6.5 for **Rule R cross-platform notification send** — the defender persona sending the user a chat message across platforms. On an **Adam-only, DM-first, single-platform Discord deploy**, cross-platform send is not exercised by the email-reading turns this epic targets; Hermes already delivers to Discord via its native gateway, and the urgent/digest notification path is the **pull-based** `pull_pending_notifications` + cron skill (Story 6-3 / 6-10), NOT the `messaging` toolset's push. So on the current deploy the `messaging` toolset is a mis-pick attractor with no load-bearing use on email turns. This trade-off must be recorded explicitly (drift test + Dev Notes) so a future multi-platform deploy re-evaluates it rather than inheriting a silent cut.

## Acceptance Criteria

**AC-1 — `messaging` dropped from the Discord allow-list.** `platform_toolsets.discord` in `hermes-config/config.yaml` no longer contains `messaging`. The `send_message` mis-pick peer (F-10-6-5-W1 defect #1) is thereby off the per-turn Discord surface.

**AC-2 — `mailbot-api` (the 26 email verbs) stays on the surface.** The allow-list still contains `mailbot-api` so `find_emails` and its email-reading siblings remain dominant. No email verb is lost.

**AC-3 — Every registered MCP server stays named in the allow-list.** The CR-10-6-5-1 invariant holds: any `mcp_servers` entry must also appear in `platform_toolsets.discord` (else its tools auto-inject unaccounted-for). Trimming `messaging` (a built-in toolset, not an MCP server) must not violate this.

**AC-4 — Noise toolsets stay excluded.** The `_NOISE_TOOLSETS_FORBIDDEN_ON_DISCORD` set (tts/image_gen/vision/…/skills) remains absent — the trim narrows the surface, it must not re-admit noise.

**AC-5 — The `pull_pending_notifications` boundary is recorded honestly.** The config comment block and a drift test document that this attractor is an intra-`mailbot-api` verb the allow-list CANNOT remove, and that per-verb mailbot-api surface scoping is a filed residual, NOT delivered here. No claim that this story gets qwen to a small email-only menu on the flat surface.

**AC-6 — Offline drift gates only; live proof deferred.** All new/changed tests are offline YAML-shape drift gates (no Docker/Discord/Anthropic dependency), consistent with the existing `test_hermes_config.py` pattern. The live-Discord "find my unread emails" qwen→`find_emails` turn (done-flip clause 3) is a Phase 3.5 / epic-live-walk item and is explicitly NOT claimed discharged by this story.

## Tasks / Subtasks

- [x] **Task 1 (AC-1, AC-2, AC-3): Trim `messaging` from the keep-set in the drift-test contract** *(RED first)* — removed `"messaging"` from `_REQUIRED_DISCORD_TOOLSETS`; added `_TRIMMED_TOOLSETS_10_7_3` frozenset + `test_hermes_config_discord_allowlist_excludes_messaging_send_peer` (F-10-6-5-W1 defect #1 + single-platform rationale). RED confirmed (2 fail, keep-set still passes).

- [x] **Task 2 (AC-1): Drop `messaging` from `platform_toolsets.discord` in config.yaml** *(GREEN)* — removed `- messaging`; exclusion test now passes, keep-set + noise + every-mcp-server tests still pass.

- [x] **Task 3 (AC-4, AC-5): Update the config comment block honestly** *(REFACTOR)* — KEEP-SET list updated (messaging removed); added `# TRIMMED (Story 10.7.3)` + `# BOUNDARY — what this lever CANNOT do` notes; VERIFY runbook line unchanged (still valid).

- [x] **Task 4 (AC-5, AC-6): Add the boundary-honesty drift gate** — `test_hermes_config_10_7_3_boundary_documented` asserts config text names `pull_pending_notifications` + `F-10-7-3-R1`. All tests offline (parse YAML directly, no Docker/network).

- [x] **Task 5 (AC-5): File the intra-mailbot-api verb-scoping residual** — F-10-7-3-R1 appended to `story-run-flags.md` (toolset-granularity boundary; needs verb-filter or tree design; WARNING, owed before clause-3).

- [x] **Task 6 (all ACs): Run the 4 gates** — see gate results in Completion Notes.

## Dev Notes

### Technical requirements
- **Stack:** Python 3.12, YAML config, pytest. No new dependencies.
- **The only product artifact touched is `hermes-config/config.yaml`** (a container config consumed by Hermes at startup) — this is NOT `mailbot_api` source. Plus its offline drift tests in `tests/integration/test_hermes_config.py`.
- **No `mailbot_api/` source change.** The chat tool list comes from Hermes's `request.tools` curated by `platform_toolsets.discord`, not a server-curated MCP set (epics.md §4357). Per spike grounding, this is a hermes-config lever, not a mailbot_api one.

### Architecture compliance
- **Extends 10.6.5's allow-list** (`hermes-config/config.yaml` `platform_toolsets.discord`, lines ~173-179). 10.6.5 kept `mailbot-api, messaging, cronjob, memory, clarify` and dropped the built-in noise swarm + `skills`. This story removes `messaging` from that keep-set.
- **CR-10-6-5-1 invariant preserved (AC-3):** `test_hermes_config_every_mcp_server_is_on_the_discord_allowlist` requires every `mcp_servers` entry to be named in the allow-list. `messaging` is a Hermes built-in toolset, NOT an MCP server (the only MCP server is `mailbot-api`), so dropping it does not violate the invariant. Verify this test still passes.
- **Boundary honesty (memory `feedback_measure_real_tool_surface_at_every_level`, `project_epic_6_scope_cleave`):** file the intra-mailbot-api residual rather than editing config to look like it solved the flat-26 problem. The spike is explicit (§1, §4.4): the flat-26 surface still fails 0/N; this trim removes one attractor (`send_message`) but does not deliver a small menu.

### Files to touch
- `hermes-config/config.yaml` — remove `- messaging` from `platform_toolsets.discord`; update the comment block (KEEP-SET rationale + TRIMMED note + BOUNDARY note).
- `tests/integration/test_hermes_config.py` — remove `messaging` from `_REQUIRED_DISCORD_TOOLSETS`; add exclusion test + boundary-documented test.
- `_bmad-output/implementation-artifacts/story-run-flags.md` — append F-10-7-3-R1 residual.

### Testing requirements
- **Offline drift gates only** (AC-6). The existing `test_hermes_config.py` parses YAML directly — no Docker, no Discord, no Anthropic. Match that pattern.
- **Live proof is deferred** to the epic live walk (done-flip clause 3): a real Discord "find my unread emails" turn producing `router_calls` with `model_chosen=qwen2.5:*` and `tool_calls_count≥1` invoking `find_emails`. This story does NOT and cannot discharge clause 3 (a config trim is one ingredient; the spike shows the flat-26 problem is larger).
- **MANDATORY-CR** with reviewer model ≠ dev model (config = model-facing surface contract; the allow-list directly shapes what qwen can pick). Per memory `feedback_reviewer_model_substitution`.

### References
- `_bmad-output/planning-artifacts/epics.md` § Epic 10.7 Detail (lines 4343-4391) — story spec, boundary grounding (§4357), done-flip gate (clause 3 load-bearing).
- `_bmad-output/implementation-artifacts/10-7-0-spike-finding.md` §1 (flat-26 0/N), §4 (surface-trim re-opened), §4.2 (top-split tree viable), §4.4 (FINAL fire-list: 10.7.3 FIRE — "getting qwen to a small menu is the remaining real engineering").
- `hermes-config/config.yaml` lines 119-179 — the 10.6.5 allow-list + rationale this story extends.
- `tests/integration/test_hermes_config.py` lines 129-266 — the 10.6.5 drift-gate pattern.
- `mailbot_api/mcp_server.py` `_EXPECTED_TOOL_COUNT = 26` (:1133), `pull_pending_notifications` description (:1091) — proof the attractor is an intra-mailbot-api verb, not a separable toolset.
- sprint-status.yaml 10-7-3 row — FIRM/FIRE disposition; hermes-config lever, not mailbot_api; drift-tested; MANDATORY-CR reviewer≠dev.

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (dev, autonomous-story-run)

### Debug Log References

- Confirmed via code recon (`mcp_server.py:1091,1133`) that `pull_pending_notifications` is an intra-`mailbot-api` MCP verb (one of the 26), NOT a separable toolset — so the toolset-level `platform_toolsets.discord` allow-list structurally CANNOT drop it. This is the load-bearing scope-honesty finding: the epic headline "remove the mis-pickable send_message" IS achievable (drop `messaging`), but the spike's DOMINANT attractor (`pull_pending_notifications`, 100% of flat-26 wrong picks) is NOT. Filed as F-10-7-3-R1 rather than papered over.
- Weighed the cost of dropping `messaging`: it was kept in 10.6.5 for Rule R cross-platform PUSH. On the Adam-only, DM-first, single-platform Discord deploy that push is unused on email turns (native-gateway delivery + pull-based `pull_pending_notifications`/cron for urgent/digest), so `messaging` is a pure mis-pick attractor here. Trade-off recorded in config + test + Dev Notes so a future multi-platform deploy re-evaluates deliberately.
- Noted `router.py:158` already ships a 10.7.2 system-prompt nudge ("prefer email-reading tools such as find_emails over generic messaging") — this config trim removes the `messaging`/`send_message` peer from the surface entirely, complementary to that prompt.
- RED→GREEN: 2 new drift tests failed pre-change (messaging present, boundary note absent), pass post-change. No `mailbot_api/` product source touched — config + tests + docs only.

### Completion Notes List

- **AC-1 (messaging dropped):** `- messaging` removed from `platform_toolsets.discord` in `hermes-config/config.yaml`. `send_message` mis-pick peer (F-10-6-5-W1 defect #1) is off the per-turn Discord surface. Verified by `test_hermes_config_discord_allowlist_excludes_messaging_send_peer`.
- **AC-2 (email verbs stay):** allow-list still holds `mailbot-api` (+cronjob/memory/clarify). `find_emails` and its 25 siblings remain. Verified by `test_hermes_config_discord_allowlist_keeps_mailbot_verbs` (with `messaging` removed from `_REQUIRED_DISCORD_TOOLSETS`).
- **AC-3 (MCP-server invariant):** `mailbot-api` (only MCP server) still named in the allow-list; `messaging` is a Hermes built-in toolset, not an MCP server, so `test_hermes_config_every_mcp_server_is_on_the_discord_allowlist` still passes.
- **AC-4 (noise stays excluded):** `_NOISE_TOOLSETS_FORBIDDEN_ON_DISCORD` set unchanged and still absent; verified by the existing noise-exclusion test.
- **AC-5 (boundary recorded honestly):** config comment block gained a `# TRIMMED (Story 10.7.3)` note + a `# BOUNDARY — what this lever CANNOT do` note naming `pull_pending_notifications` + `F-10-7-3-R1`; residual filed in `story-run-flags.md`. Verified by `test_hermes_config_10_7_3_boundary_documented`. No over-claim that this gets qwen to a small email-only menu.
- **AC-6 (offline drift gates; live deferred):** all `test_hermes_config.py` tests parse YAML directly — no Docker/Discord/Anthropic. Done-flip clause 3 (live Discord qwen→find_emails turn) explicitly NOT claimed by this story.
- **ACCEPTED RISK (inference-only `messaging` membership) — CR-10-7-3 Decision, option (b):** the claim that dropping `messaging` costs nothing on email turns rests on the *inference* that `messaging` exposes only `send_message` (sourced from epics.md §4350 + the inherited 10.6.5 comment — neither an enumeration of the toolset's full verb list). Unlike 10.6.5 (which ran the change through the real Hermes resolver `_get_platform_tools(cfg,"discord")` and discovered the non-obvious `kanban`-preserved behavior), this story has NO live-resolver re-run for the `messaging` removal — only offline YAML-shape drift gates. **This inference-only risk is explicitly accepted here in the story's own record (not just the pre-review):** if `messaging` in fact bundles a benign verb beyond `send_message`, this trim silently removes it and the triple-write cost-of-removal argument (config + test + flags) would be wrong in all three places (they share the one unverified premise). The mitigating live-resolver sanity check (`hermes tools list --platform discord`) is promoted to the epic live-walk (recorded in story-run-flags.md), materially cheaper than and sharing the same walk as clause 3. Accepted because: (i) no email-reading turn needs a `messaging` verb, and (ii) a future multi-platform deploy must re-evaluate `messaging` deliberately per the config/test docstrings regardless.
- **Gates (post-CR):** ruff clean · mypy `--strict mailbot_api` clean (134 files) · boundary exit 0 · pytest **1972 passed / 3 skipped / 3 deselected** (+2 net vs 1970 baseline — the 2 new drift tests; CR-10-7-3-P re-scoped one of them, still green).

### File List

- `hermes-config/config.yaml` (modified) — dropped `- messaging` from `platform_toolsets.discord`; updated KEEP-SET rationale + added TRIMMED + BOUNDARY comment notes.
- `tests/integration/test_hermes_config.py` (modified) — removed `messaging` from `_REQUIRED_DISCORD_TOOLSETS`; added `_TRIMMED_TOOLSETS_10_7_3` + `test_hermes_config_discord_allowlist_excludes_messaging_send_peer` + `test_hermes_config_10_7_3_boundary_documented`.
- `_bmad-output/implementation-artifacts/story-run-flags.md` (modified) — filed residual F-10-7-3-R1.
- `_bmad-output/implementation-artifacts/10-7-3-allowlist-trim-toward-mailbot-api-only.md` (new) — this story file.

### Live-resolver verification (CR-10-7-3 Decision option (a) — DISCHARGED early, 2026-07-16)

Ran the CR-promoted live check during the Phase 3.5 walk (Adam + orchestrator; `mailbot-hermes` restarted to load the trimmed config):

```
$ docker exec mailbot-hermes hermes tools list --platform discord
Built-in toolsets (discord):
  ✓ enabled  memory / clarify / cronjob
  ✗ disabled  messaging  📨 Cross-Platform Messaging   ← the send_message peer, now OFF
  ✗ disabled  (all noise: web/browser/terminal/file/code_execution/vision/…/skills/tts/todo/delegation/computer_use)
MCP servers:
  mailbot-api  all tools enabled
```

**Discharges the CR Decision accepted-risk:** the resolver shows `messaging` is a single toggle-as-one-unit toolset (`📨 Cross-Platform Messaging`), so dropping it is a clean toolset-level off-switch — no benign sibling verb was collaterally dropped by inference error (the inference-only premise is now confirmed correct on the real surface, not just epics.md §4350). AC-1..AC-4 all confirmed LIVE, not only by the offline YAML drift gates. **Also confirms F-10-7-3-R1's boundary:** `mailbot-api` resolves as `all tools enabled` (one server, no per-verb toggle in this view) — `pull_pending_notifications` cannot be individually disabled here, exactly the intra-mailbot-api boundary the story documented. Clause 3 (a real qwen→`find_emails` Discord turn) remains owed at the epic live-walk — this check verified the *surface*, not the *selection*.

### Change Log

- 2026-07-16 — Trimmed `messaging` (the `send_message` mis-pick peer, F-10-6-5-W1 #1) from the Discord tool-surface allow-list; documented the intra-`mailbot-api` `pull_pending_notifications` boundary (F-10-7-3-R1). Config + drift-tests only, no product source. $0.

### Review Findings

- [x] [Review][Decision] **RESOLVED via option (b) — inference-only risk now accepted in the story's own Dev Notes + Completion Notes (below), not just the pre-review.** Option (a) live-resolver check (`hermes tools list --platform discord` / the 10.6.5 container `_get_platform_tools` call) is NOT runnable in this non-interactive autonomous session (needs the live mailbot-hermes container) and is promoted to a Phase 3.5 / epic-live-walk verification item, recorded in `story-run-flags.md` alongside F-10-7-3-R1. The offline drift gates stand as the CI contract; the resolver-level sanity check is owed at the same walk that discharges clause 3 (it is materially cheaper than the live-turn proof and shares the walk). Original finding text preserved below. `messaging` toolset's real membership was never verified — dropping it may over-trim a benign verb, and no live resolver check confirms the change's effect (unlike 10.6.5's precedent) — decide whether to verify before/after merge or accept the risk as-is. The dev's own pre-review self-audit (§4) already escalated this exact question to the reviewer ("is dropping the whole `messaging` toolset the right lever, given the surface is toolset-level only") and it survives adversarial + edge-case scrutiny as unresolved. Concretely: (1) the claim that `messaging` exposes *only* `send_message` (config comment, test docstring `_TRIMMED_TOOLSETS_10_7_3`, and `story-run-flags.md` all assert "Rule R cross-platform notification send" / `send_message`) is sourced from `epics.md:4350` ("qwen picks `send_message`, from the `messaging` toolset") and a prose comment inherited from 10.6.5 — neither is an enumeration of the toolset's full tool list, and no Hermes docs archive or in-repo schema reference lists `messaging`'s member verbs. (2) Story 10.6.5, which is the precedent this story extends, explicitly ran the change through the REAL Hermes resolver (`_get_platform_tools(cfg, "discord")` inside the container) and discovered a non-obvious behavior (`kanban` silently preserved as a "non-configurable" entry regardless of the allow-list) — 10.7.3's Dev Notes/Completion Notes/pre-review self-audit contain no equivalent live-resolver re-run for the `messaging` removal, only the offline YAML-shape drift tests. AC-6 correctly scopes the live-Discord-*turn* proof (clause 3) out of this story, but a resolver-level sanity check is a materially cheaper, different verification that was precedented and is silently absent here. If `messaging` in fact bundles other verbs beyond `send_message` (e.g., a benign cross-platform utility), this trim silently removes them with no test surface that would catch it, and the "no load-bearing use on email turns" cost-of-removal argument in the config/test/flags-file triple-write would be wrong in all three places simultaneously since it's copied from the same unverified premise. Recommend either (a) running `hermes tools list --platform discord` (or the container resolver call 10.6.5 used) against the new config once and recording the actual resolved verb set in Dev Notes, or (b) explicitly accepting the inference-only risk in the story (it is currently accepted only in the pre-review self-audit, not in the story's own Dev Notes/Completion Notes).

- [x] [Review][Patch] **FIXED** — `test_hermes_config_10_7_3_boundary_documented` now scopes the substring match to the `# BOUNDARY` comment block (text between the `# BOUNDARY` marker and the `platform_toolsets:` key it annotates), asserting both `pull_pending_notifications` and `F-10-7-3-R1` appear *within that block*, not anywhere in the file. Deleting the BOUNDARY prose now red-gates even if the strings survive elsewhere. (CR-10-7-3-P.) Original finding: `test_hermes_config_10_7_3_boundary_documented` is an unscoped substring match, not a scoped check of the BOUNDARY comment block [tests/integration/test_hermes_config.py:144-163]. The test asserts `"pull_pending_notifications" in raw_text` and `"F-10-7-3-R1" in raw_text` against the *entire* config file's raw text, not against the specific BOUNDARY note it's meant to guard. It would pass just as well if both strings appeared anywhere else in the file (e.g., in an unrelated future comment, or if the BOUNDARY paragraph were deleted entirely but the strings happened to survive elsewhere, such as in a different note or a stray reference). This weakens the gate's stated purpose ("red-gates a future edit that quietly claims full surface-scoping without the filed intra-mailbot-api residual") — a determined or careless future edit could satisfy the assertion without preserving the actual boundary-honesty prose. Suggested fix: extract the specific comment block (e.g., text between `# BOUNDARY` and the next top-level comment section, or between `# TRIMMED (Story 10.7.3)` and `platform_toolsets:`) and assert both strings appear within that scoped substring, not just anywhere in the file.

- [x] [Review][Defer] `_REQUIRED_DISCORD_TOOLSETS` and `_TRIMMED_TOOLSETS_10_7_3` disjointness is not itself enforced by a test [tests/integration/test_hermes_config.py:168-183] — deferred, pre-existing pattern (the existing `_NOISE_TOOLSETS_FORBIDDEN_ON_DISCORD` set has the same characteristic relative to `_REQUIRED_DISCORD_TOOLSETS`, i.e., no test asserts the two constant sets stay disjoint as a general invariant). Not a regression introduced by this story; a future story could add a shared `assert not (_REQUIRED_DISCORD_TOOLSETS & _TRIMMED_TOOLSETS_10_7_3)` sanity test if this class of self-contradiction becomes a recurring risk.
