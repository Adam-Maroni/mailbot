# Epic 10.6 Retrospective — Capability Reachability (PARTIAL, 2/4 stories)

**Date:** 2026-07-13
**Facilitator:** Amelia (Developer)
**Project Lead:** Adam
**Participants:** Amelia (Developer), Alice (Product Owner), Charlie (Senior Dev), Dana (QA)
**Format:** Partial party-mode retrospective (Adam-chosen: "Partial retro now, 2/4")

> ⚠️ **PARTIAL RETRO.** Epic 10.6 is **NOT complete** and is **NOT done-flipped** by this session. 2 of (now) 5 stories are done (10-6-0, 10-6-1). Remaining `backlog`: 10-6-2 (draft reachability, clause 4), 10-6-3 (scratch/ ruff), and **10-6-4 (cheap-lane latency — spawned in this session from the F-10-6-1-W1 diagnosis; inside clause 3 per D1)**. This document reviews the two done stories and sets the finish path. A final full retro / done-flip fires when all five stories land.
>
> **Post-retro work done this session (2026-07-13):** ran the F-10-6-1-W1 diagnosis live (see `F-10-6-1-W1-diagnosis-2026-07-13.md`) — root cause is COLD PROMPT INGEST (~19s for 1658 tokens on CPU) from model eviction (no `keep_alive`), NOT `num_ctx` (measured red herring). Live-confirmed `keep_alive:-1` collapses a repeat/chained turn to ~3-4s. Spawned **Story 10-6-4** (full-scope A+B fix: adapter `keep_alive`+timeout env-config, Hermes-side trim/prefix/retry-tame). Epic roster 4→5; `epic-10-6` flipped `in-progress` (2/5 done).

---

## 1. Scope of this retro

- **Reviewed (done):** 10-6-0 (Graph-auth-at-drain infra fix), 10-6-1 (local-tool-caller chat-path reachability = AI-1 Phase 2).
- **NOT reviewed (backlog):** 10-6-2 (AI-2 draft-pipeline reachability, F-10-5-11 — **load-bearing clause 4**), 10-6-3 (AI-4 scratch/ ruff, 4th-carry risk).
- **Epic theme:** *"wired + capable + tested ≠ reached on the real user path."*

---

## 2. Delivery metrics (2 stories)

- **Stories done:** 2 / 4 (both dev + MANDATORY-CR + Adam-driven L3 live walk)
- **Test suite:** 1885 → **1905** (+20 net; 10-6-0 → 1889 [+4], 10-6-1 → 1905 [+16]); 4 gates green at every close
- **MANDATORY-CR:** ran on both; **reviewer claude-sonnet-5 ≠ dev claude-opus-4-8** both times (substitution rule from Epic 10.5 retro / durable memory — held again)
- **Real Anthropic spend:** ~$0 (10-6-0 is Graph-only; 10-6-1 routes to LOCAL qwen — the entire point of the story)
- **Live validation (L3):** both walked by Adam — 10-6-0 induced-401 recovery against real Microsoft Graph (mailbox actually changed and restored); 10-6-1 real Discord turn routed to and served by qwen (DB `router_calls` ground truth)

---

## 3. Done-flip gate — clause-by-clause (4 clauses; epic CANNOT flip)

| # | Clause | Status | Evidence / note |
|---|--------|--------|-----------------|
| 1 | Stories 10.6.0–10.6.3 = done | ❌ | 2/4 done; 10-6-2 + 10-6-3 still `backlog` |
| 2 | Graph-auth drain works (10.6.0) | ✅ | 10-6-0 live: induced 401 → on-demand refresh → Graph 200, `mark_read` applied, mailbox restored (real Graph, real adapter, real oauth_state hook) |
| 3 | Cheap lane REACHED (10.6.1) **(load-bearing)** | ⚠️ **RE-OPENED by decision D1** | Routing proven L3 (qwen `router_calls` rows on a real Discord turn) — BUT **Adam-decided REACHED ≠ usable**: F-10-6-1-W1 (qwen-CPU >30s timeout on full-context turns) now blocks this clause until the latency fix lands |
| 4 | Draft pipeline REACHED (10.6.2) | ⬜ | Not started (backlog) |

**Clause 3 was the load-bearing clause the epic was built around (the cost thesis as a gate).** This retro tightened it: a `router_calls` row proving qwen got the turn is not sufficient if the turn 502s at the 30s adapter timeout. See §7 D1.

---

## 4. What went well

1. **The epic proved its own thesis against itself, three layers deep in one story.** 10-6-1 hit "wired ≠ reached" at the adapter (Phase 1: `OllamaAdapter.call_with_tools` raised `tools_unsupported`, a stale Story-6-9 write-off), the router capability gate (`_model_supports_tool_calls` hard-coded `^claude-*`), AND the policy layer (`dispatch_tool_call` sourced its default model from the `hermes_aux`=haiku entry — no `chat_completions_tool_call` task existed). Each layer looked done+tested; none reached qwen until the layer above was fixed. The flagship story diagnosed the exact bug-class the epic exists to kill.
2. **Latent bugs were REACHED, not theorized.** Flipping the default to qwen exercised the Ollama multi-turn `tool_calls[].function.arguments` string→dict path for the first time; a pydantic `ValidationError` surfaced immediately via an *existing* regression test (`test_sensitivity_refusal_envelope_boundary`) — a genuine find caught by the safety net, not a walk crash.
3. **Boundary-honesty held (10.5 discipline).** 10-6-0 scope-fenced hard off `oauth.py`/`graph_client.py` (Adam's fence) and FILED the true-token-endpoint-refresh residual rather than pretending the DB-re-read was a full fix. 10-6-1 confirmed the persona needed no Hermes-side change and located the gap 100% server-side instead of editing config to look busy.
4. **Adversarial CR did real work, reviewer ≠ dev both times.** 10-6-0: sonnet-5 caught a final-iteration silent-wrong-error bug (forced a `for`→`while`+manual-counter restructure) and caught the 401-refresh stealing an AR-D5-1 backoff slot. 10-6-1: the Blind Hunter's 3 "asserted, not shown" safety claims were independently re-verified by code read by the other two hunters; 5 patches applied (100% of actionable).
5. **A privacy-model change was surfaced, not silently shipped.** 10-6-1 flags that confidential tool-calls now serve on local qwen (no longer `SENSITIVITY_BLOCKS_API`-refused on the default path) — tested both directions; CR found it *closer* to NFR-PRIV-2's letter than pre-diff. Parked for Adam's Phase 3.5 sign-off, not assumed.

---

## 5. What didn't (challenges / growth areas)

1. **The reachability tail bites after the reachability fix — F-10-6-1-W1 (MEDIUM, perf/infra).** 10-6-1 closed the routing gap and immediately exposed a latency gap: qwen-on-CPU ~3s on minimal payloads (dev tests + direct-endpoint proof) but ~20s full-context and **>30s → AdapterTimeout** on real multi-call Discord turns (`registry.py:52,64` / `models.py:512` hard-code `timeout_seconds=30.0`). The cheap lane is *reached* but not yet *usable end-to-end within budget on this CPU host*. The fix reached a new regime the minimal-payload tests never covered.
2. **10-6-0's headline fix carries a documented residual by design.** The on-demand refresh hook is a *DB re-read of `oauth_state`*, not a token-endpoint exchange — under the exact stale-cache race where the periodic `oauth_token_refresh` task also hasn't rotated the row, it's a bounded no-op (retry re-401s, now audited, no regression). Common case fixed; deep case needs a follow-up touching the scope-fenced files. CR rated it ACCEPT-WITH-RATIONALE (correctly, not "fixed").
3. **Retro-ing a half-done epic; the unaddressed half repeats a prior-retro miss.** 10-6-2 (draft reachability) is the sibling instance of the same "wired≠reached" class AND was already flagged unaddressed in the Epic 10.5 retro — where it made clause 4 close weak. It is now leaving Epic 10.6's clause 4 open too. 10-6-3 (scratch/ ruff) faces its potential **4th consecutive carry** (A6 → Epic 9.5 → Epic 10 → Epic 10.6).

---

## 6. Previous-retro (Epic 10.5) follow-through

| Epic 10.5 action item | Status in Epic 10.6 |
|---|---|
| **AI-1** local tool-caller verify-or-restore | ✅ **Delivered** as 10-6-1 (Phase 2 done + live-walked). P0 re-test PASSED, cost thesis survived, "minor wiring fix" altitude held. |
| **AI-2** draft-pipeline reachability (F-10-5-11) | ❌ **Not addressed** — still backlog as 10-6-2 (repeat miss from 10.5). |
| **AI-3** reviewer-substitution memory | ✅ Discharged (durable memory); held 100% again across both 10.6 stories. |
| **AI-4** scratch/ ruff (3rd carry) | ❌ **Not addressed** — still backlog as 10-6-3; 4th-carry risk. |
| **10-6-0** Graph-auth (the AI-1 walk's separate infra blocker) | ✅ **Delivered** — 401-refresh-retry, L3 live-walked against real Graph. |

---

## 7. Adam decisions this retro

| ID | Decision | Consequence |
|----|----------|-------------|
| **D1** | **Clause 3 ("cheap lane REACHED") is NOT fully met until the cheap lane is *usable*, not just *routed*.** F-10-6-1-W1 (qwen-CPU >30s timeout) is a **blocker on clause 3**, not a CP-1/perf footnote. | The load-bearing done-flip clause is **re-opened**. 10-6-1 stays `done` as a story (routing + safety proven, CR-clean); the *epic* done-flip now additionally requires the timeout/usability fix. W1 must become **scheduled work** (new story 10-6-4, or folded into a 10-6-1 re-walk after a timeout bump — create-story-time call). |
| **D2** | **Finish the epic before Epic 7:** run 10-6-2 then 10-6-3, close all 4 clauses, done-flip Epic 10.6. | Preserves the "Epic 10.6 before Epic 7" sequencing from the 10.5 retro. No partial-epic hand-off to Epic 7. |

---

## 8. Critical path to Epic 10.6 done-flip

1. **10-6-2** (AI-2 — draft-pipeline reachability, F-10-5-11) — closes **clause 4**; persona/dispatch seam; MANDATORY-CR reviewer≠dev; small Opus draft-walk spend. Story file drafted (`ai-2-draft-pipeline-reachability-from-chat.md`).
2. **F-10-6-1-W1** (qwen-CPU tool-call timeout) — **now inside the gate (clause 3) per D1.** Promote from filed finding to scheduled work (10-6-4 or 10-6-1 re-walk). Immediate-unblock option: bump `registry.py:52,64` 30s→90–120s; durable options: trim Hermes per-turn tool surface / GPU host [CP-1] / less per-turn chaining.
3. **10-6-3** (AI-4 — scratch/ ruff) — low-effort chore; 6 T201 sites; repo-wide `ruff check .` green. Do it before it carries a 4th time.

**Residual (filed, non-blocking):** 10-6-0 true-token-endpoint refresh follow-up (DB-re-read no-op in the deep stale-cache race, bounded + audited).

---

## 9. Next epic preview — Epic 7: Production Calibration

Unchanged from the Epic 10.5 retro preview: Epic 7 discharges the production half of Rule H (eval-driven routing). Surviving stories 7.5 (Sunday production sampling) / 7.6 (weekly KL-divergence drift) / 7.7 (shadow-mode prompt rollouts + FR-4.3 ≥90% reference-resolution). Hard-dependent on Epic 9 (satisfied); 7-0 prep done. **Per D2, Epic 7 does not start until Epic 10.6 done-flips** — calibrating routing quality while the cheap lane isn't usable (W1) and the draft pipeline is unreachable (10-6-2) would calibrate a product nobody can use. CP-1 (VPS deploy) stays the final ship gate outside all epics; local viability remains top priority.

---

## 10. Readiness assessment — is Epic 10.6 done? **NO.**

| Dimension | Status |
|-----------|--------|
| Stories | ❌ 2/4 done (10-6-2, 10-6-3 backlog) |
| Tests / quality | ✅ 1905+3skip+3desel, 4 gates green; MANDATORY-CR reviewer≠dev on both done stories |
| Live validation (L3) | ✅ both done stories walked by Adam (real Graph, real Discord→qwen) |
| Load-bearing clause 3 | ⚠️ routing proven, **usability re-opened by D1** (W1 timeout) |
| Deployment | N/A — local stack only; CP-1 outside all epics |
| Stakeholder (Adam) acceptance | ⚠️ 10-6-1 confidential-on-local privacy disposition still pending Adam Phase-3.5 sign-off |
| Unresolved carry-forward | 10-6-2 (clause 4), 10-6-3 (4th-carry chore), F-10-6-1-W1 (now in clause 3), 10-6-0 refresh residual |

**Verdict:** Epic 10.6 is **partially complete**. The two hardest/highest-priority stories (Graph-auth drain + cost-thesis cheap-lane routing) are done and L3-verified; the founding cost thesis went from 18/18 tool-call failures (top of Epic 10.5) to a real Discord turn served by qwen. But the epic **cannot done-flip**: clause 1 (2 stories backlog), clause 3 re-opened by D1 (W1 usability), clause 4 not started. Finish path = 10-6-2 + W1 + 10-6-3, then a full retro / done-flip before Epic 7.

---

## 11. Key takeaways

1. **"Reached" is not the last word — "usable" is.** The epic's founding lesson was "wired ≠ reached"; this retro added the next level: **reached ≠ usable within budget.** A `router_calls` proof that qwen got the turn isn't enough if the turn times out. (Adam D1.)
2. **The cost thesis is now demonstrably alive on the real path** — 18/18 tool-call failures → a live Discord turn routed to and served by the local lane at $0 — but its *end-to-end usability* on the target host is the remaining open question (F-10-6-1-W1).
3. **Boundary-honesty + reviewer≠dev CR are durable** — both held across both stories under autonomous pressure; each caught real defects (401-refresh restructure; Ollama multi-turn arg bug; safety re-verification).
4. **A twice-deferred story becomes a pattern.** AI-2 (draft reachability) has now been left unaddressed across two consecutive retros. D2 schedules it as immediate next work to stop the pattern.
