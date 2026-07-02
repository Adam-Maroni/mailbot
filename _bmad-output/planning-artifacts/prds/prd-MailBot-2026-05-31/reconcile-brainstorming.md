---
title: Input Reconciliation — Brainstorming Session vs. PRD + Addendum
input: _bmad-output/brainstorming/brainstorming-session-2026-05-31-1430.md
produced:
  - _bmad-output/planning-artifacts/prds/prd-MailBot-2026-05-31/prd.md
  - _bmad-output/planning-artifacts/prds/prd-MailBot-2026-05-31/addendum.md
date: 2026-05-31
reconciler: Claude (Opus 4.7, input-reconciliation pass)
---

# Reconciliation Report

## Captured (made it through)

- **Rule Ω as meta-principle** — present in PRD §2 and elevated to "product principle"; addendum A2 maps it.
- **All 21 architectural rules (Ω, A–X)** — cross-referenced in addendum A2 table, each tied to a PRD FR/NFR.
- **3-tier model stack (Qwen 3B / Haiku 4.5 / Opus 4.7)** with model IDs — FR-3.1 + addendum A3.
- **Router as single source of truth** — FR-3.2, FR-3.9, NFR-OPS-6 (fallback).
- **Verb API + MCP integration + hydration discipline** — FR-3.2, §6, addendum A5.
- **Cron-pull sync, queued intents, derived-field caching** — FR-1.1, FR-2.x, FR-5.5.
- **Four-tier authorization model + scoped grants + cooling-off + 20/day cap** — FR-5.1–5.6.
- **4-layer budget (per-call, daily, monthly, refusal threshold)** — FR-6.1–6.5.
- **Sensitivity routing (normal/sensitive/confidential)** — NFR-PRIV-1–3, FR-2.5.
- **Notification tiering + quiet hours + dedup + mute + self-reflection** — FR-7.4–7.5.
- **Eval system (corpus + runner + scorer + report + sampling + drift + shadow rollouts)** — FR-8.1–8.7.
- **Hermes-native primitives + 3-container stack + Discord adapter + MCP** — §6, FR-4.1, NFR-OPS-1, addendum A1/A4.
- **Operational settings (rate limits, anti-loop, cache-warmer, weekly cadences)** — FR-3.5, FR-3.6, FR-3.8, addendum A3.
- **Rejected alternatives** — addendum A6 (webhooks, raw SQL, key-in-Hermes, cascading, GPU, OpenRouter, Honcho-from-day-1, Hermes-plugin/HTTP-via-skill).
- **Calibration cadence + DEMOTION HYPOTHESIS framing** — FR-6.6, §7.3, addendum A3 calibration section.

---

## Gaps (most-impactful-first)

### CRITICAL

#### G1 — Rule F.1's load-bearing rationale ("Router becomes a major architectural component because the key lives here") is not surfaced
- **Where in source:** Phase 1 "Consequence of F.1(a)" block (lines 99–127). The key insight is that holding ANTHROPIC_API_KEY in `mailbot-api` forces the Router to be the natural home for cost accounting, prompt caching, response caching, cascading, budget guards, routing policy, sanitized errors, and the audit log — all *because* the key is there. The Router's architectural centrality is a *consequence* of the secrets decision, not an independent design choice.
- **PRD/addendum location:** NFR-SEC-2 names the isolation but skips the architectural payoff. §6 ("Architecture Anchors") lists "Router as single source of truth" as parallel to secrets, not derived from it. Addendum A6 mentions the rejection but loses the cascading consequences.
- **Severity:** **critical** — losing this rationale means a downstream architect could legitimately question why the Router can't be split or relocated, since the connection to F.1 is invisible.

#### G2 — Local LLM stack reasoning ("Ollama over llama.cpp ~10% perf cost", "single-model commitment", "no 7B fallback because RAM budget") trimmed
- **Where in source:** Phase 1 "Local LLM stack (committed)" section (lines 219–224). Specifically: Ollama chosen for "simplicity over the ~10% perf cost vs raw llama.cpp; revisit if perf hurts"; "No 7B fallback. Single-model local layer. Anything 3B can't handle reliably → escalate to API"; "Privacy posture: VPS-local is sufficient. The local Qwen process is allowed to see all email categories."
- **PRD/addendum location:** FR-3.1 mentions "via Ollama" without justification. NFR-HW-3 says "No 7B fallback at v1" but loses the *why* (RAM budget + revisit-if-perf-hurts). The privacy posture ("VPS-local is sufficient; Qwen sees all categories") is gone entirely — and it's load-bearing because Rule Q's sensitivity routing depends on it being safe to send confidential emails to local Qwen.
- **Severity:** **critical** — Rule Q is built on this premise; without it surfaced, a future reviewer might add data-class restrictions on local inference and break the whole privacy model.

#### G3 — Capability gap rationale: "the 3B↔Opus gap is large; no graceful cheap escalation"
- **Where in source:** Phase 1 "API LLM stack (committed)" block (lines 226–231). The original design was *binary* Qwen-or-Opus precisely because the gap was acknowledged as ungraceful — Haiku was a *deferred* decision that became v1 only later in the session. The "every task kept on 3B is pure savings" framing is the original cost-discipline driver.
- **PRD/addendum location:** FR-3.1 just states "three-tier from day 1." Addendum A6 mentions middle-tier was originally rejected ("this is a 2026-05-31 update") but the underlying rationale (binary-was-deliberate, savings-per-task-on-3B-is-large) is absent. The Rule-Ω motivation reads as principle without the gap-economics that originally drove it.
- **Severity:** **critical** — the cost discipline narrative loses force without the "binary on purpose; Haiku added grudgingly" backstory.

### HIGH

#### G4 — `policy.yaml` as "the agent's cost-discipline artifact" + "every change deliberate and evidence-backed"
- **Where in source:** Phase 4 closing (lines 759–760) and Rule Ω consequences (lines 432–438). The file itself is positioned as a *moral artifact* — a public ledger of cost commitments — not just a config.
- **PRD/addendum location:** §7.3 mentions the framing in passing ("policy file is the agent's cost-discipline artifact") but loses the operational weight: every Opus assignment must cite a benchmark; comments are mandatory; demotion ratchets automatically when benchmarks allow; promotion ratchets only when benchmarks demand; features whose only justification is "would be nice" but require unjustified API spend are *rejected*.
- **Severity:** **high** — this is the "soul" of the design and risks being read as routine governance.

#### G5 — Phase 3 pre-mortem narrative ("$340 instead of $30" + six named failure modes) is stripped
- **Where in source:** Phase 3 (lines 417–474). Six specific failure scenarios were walked back to produce Rules J–O: (1) "agent dumps 47 full emails into one Opus call" (Rule J), (2) "backlog death loops + idempotency bugs + cascade-escalation storms" (Rule K), (3) "GitHub notifications appeared in August, 3B was never trained for them" (Rule L), (4) "you thought you had 85% cache hits; you have 10%" (Rule M), (5) "$50 overnight from 8000 small calls in a loop" (Rule N), (6) "v3 of draft prompt is subtly worse than v2; you don't notice for 5 weeks" (Rule O).
- **PRD/addendum location:** Rules J–O are mapped in addendum A2 but the *failure modes* they prevent are gone. A reader who's never seen the brainstorm can't tell *why* hydration is rate-limited, *why* the cache-warmer cadence matters, or *why* shadow rollouts exist.
- **Severity:** **high** — these are the load-bearing scenarios for the safety mechanisms; without them, the mechanisms read as paranoia, not as named-threat responses.

#### G6 — The session's "soul" framing: Rule Ω as articulated by Adam ("gives the whole system its soul")
- **Where in source:** Phase 3 intro (line 419): "Above them all, one meta-principle (Rule Ω) was articulated by Adam that gives the whole system its soul."
- **PRD/addendum location:** §2 names Rule Ω as the product principle but flattens it to engineering language. The session positions Ω as *Adam's invention*, the moment the design crystallized — a piece of personal authorship that the PRD doesn't honor.
- **Severity:** **high** — qualitative; this is the kind of thing FR structures silently drop. Matters for product identity and for downstream agents (SOUL.md, AGENTS.md) that need to embody the voice.

#### G7 — Specific 3B↔Opus tier-jump examples and reasoning behind escalation flags
- **Where in source:** Phase 1 atomic operations (lines 148–202) — every operation carries an inline "(local LLM, API on uncertainty)" or "(API — quality matters)" or "(local for short, API for long/important)" reasoning. E.g., operation #16: "Summarize a thread on demand (local for short, API for long/important)" — this *contextual* reasoning is the per-task DEMOTION HYPOTHESIS in raw form.
- **PRD/addendum location:** Addendum A3 has the policy table but the column "Demotion hypothesis" is one-line summaries. The original per-operation reasoning (e.g., "API on uncertainty", "quality matters", "synthesis-heavy, infrequent") is lost.
- **Severity:** **high** — these phrases are what tells the agent *when* to escalate at runtime. Without them, the prompt-engineering side of policy.yaml is undercited.

#### G8 — Phase 1 atomic operations inventory (34 ops) — not all 34 enumerated in PRD/addendum
- **Where in source:** Phase 1 "Atomic Operations Inventory" (lines 148–202): operations 1–34 across inbound, chat, background/cron, sync, schema, and agent↔data contract.
- **PRD/addendum location:** PRD describes capabilities through FR groupings (F1–F8) but no longer lists the *34 atomic operations*. Some — like (24) Sync scope delta, (26) Conflict resolution, (27) Attachment policy, (30) Soft-vs-hard schema, (31) History vs latest — appear as Open Questions, but operations like (7) Thread continuity check, (19) Promised-reply tracking, (20) Anomaly detection (unknown-country login, currency mismatch), (22) User-model refresh are *partially* surfaced (addendum A3 task table covers some, not others).
- **Severity:** **high** — the inventory was meant to be exhaustive; missing operations risk being silently dropped from epics.

### MEDIUM

#### G9 — Specific anomaly examples: "unknown-country login, currency mismatch"
- **Where in source:** Phase 1 operation #20 (line 177): "Anomaly detection: unknown-country login, currency mismatch (rules + local LLM)".
- **PRD/addendum location:** FR-6.5 mentions "hourly anomaly detection" for *call volume*; nothing for *email-content* anomaly detection. Addendum A3 lists `anomaly_detection` as a Qwen-3B background task but doesn't name what it detects.
- **Severity:** **medium** — concrete examples make this requirement testable; their absence makes it vaporware.

#### G10 — VPS specs and CPU-only inference reality numbers
- **Where in source:** Phase 1 "VPS reality" (lines 205–209): "KVM 2 / 2 vCPU / 8 GB RAM / 100 GB NVMe / 8 TB bandwidth, no GPU. Upgrade declined. RAM budget for LLM: ~4.5–5.5 GB after OS, SQL, Python services, and Hermes. CPU-only inference reality: 3B at ~10 t/s is usable; 7B at ~2–5 t/s is too slow for interactive chat."
- **PRD/addendum location:** NFR-HW-1 has the hardware spec; NFR-HW-2 has the RAM budget. The throughput numbers (10 t/s for 3B, 2–5 t/s for 7B) — which are the *evidence* that 7B is unusable — are gone.
- **Severity:** **medium** — without the t/s numbers, the "no 7B" decision lacks substantiation; future re-litigation likely.

#### G11 — Rule G ("Local for Batch, API for Interactive") rationale: "matches the VPS hardware honestly; forcing 7B for chat would make the tool unusable"
- **Where in source:** Phase 1 Rule G (lines 211–216).
- **PRD/addendum location:** Mapped in addendum A2 (FR-3.5, NFR-PERF-3) but the *justification* clause is gone. Without it, the lane-split looks like an arbitrary architectural choice.
- **Severity:** **medium**

#### G12 — Embedding model details and reasoning
- **Where in source:** Phase 1 (line 222): "bge-small-en-v1.5 or nomic-embed-text via Ollama (~100–150 MB resident). Embed every email at ingest; enables semantic search over the SQL mailbox."
- **PRD/addendum location:** FR-3.1 mentions "bge-small/nomic-embed" briefly. The *purpose* ("enables semantic search over the SQL mailbox") and *resource footprint* ("~100–150 MB resident") are absent.
- **Severity:** **medium** — semantic-search affordance is a near-invisible capability without this.

#### G13 — Anchor-examples-for-subjective-scoring mechanism (~20 examples scored 1–5 across axes by Adam)
- **Where in source:** Phase 1 benchmark scorer (lines 244–248): "Subjective (summary / draft) → hybrid approach: ~20 anchor examples scored manually by Adam (1–5 axes), then strong-model auto-eval calibrated against those anchors for the remaining items."
- **PRD/addendum location:** FR-8.3 mentions "20 hand-anchored examples + strong-model auto-eval calibrated against anchors" — but the "1–5 axes" granularity and the *Adam-must-score-these-personally* operational note are lost.
- **Severity:** **medium** — affects time-estimate honesty for M4.

#### G14 — Single eval-corpus build is a 3–6h (not 3–5h) one-time Adam effort
- **Where in source:** Phase 1 line 241: "~100 real (anonymized) emails covering the 5 most common task types … one-time ~3–6 h." Also line 195: "covering the 5 most common task types."
- **PRD/addendum location:** FR-8.1 says "8 task families … 3–5 hours" — both numbers are different from source ("5 most common task types" / "3–6 h"). The "anonymized" property is dropped.
- **Severity:** **medium** — task-family count expanded from 5 to 8 silently; anonymization requirement dropped.

#### G15 — Decision 3 (failure handling): per-task `escalate` flag philosophy and "error-as-data" framing
- **Where in source:** Phase 1 Decision 3 (lines 296–328). The framing "error-as-data" — agent treats failures as structured data, not exceptions — is a load-bearing design philosophy that simplifies agent prompts.
- **PRD/addendum location:** FR-3.4 lists the chain and stable error codes but the "structured error-as-data" philosophy is implicit. Two stable error codes from source — `loop_detected` and `sensitivity_blocks_api` — appear *only* in PRD (not in source); source lists 7 codes, PRD lists 9. Source list: `schema_validation_failed`, `timeout`, `budget_exceeded`, `per_call_threshold_exceeded`, `provider_error`, `monthly_budget_exceeded`, `degraded_mode_blocked`. (PRD additions are reasonable but warrant flagging.)
- **Severity:** **medium**

#### G16 — Prompt-management layout convention (`prompts/<task>/vN.py` with `VERSION`, `SYSTEM`, `USER_TEMPLATE`, `OUTPUT_SCHEMA`)
- **Where in source:** Phase 1 Decision 5 (lines 338–365). The convention that every `vN.py` exports `VERSION` (string), `SYSTEM` (cacheable block), `USER_TEMPLATE`, `OUTPUT_SCHEMA` (Pydantic class) is the contract that makes prompt caching and benchmark iteration work.
- **PRD/addendum location:** Nowhere. PRD treats prompts abstractly. This is engineering-detail-by-design but the *cacheable-SYSTEM-block* property is what makes FR-3.6 actually save money.
- **Severity:** **medium** — load-bearing for FR-3.6's "primary cost lever" claim.

#### G17 — "Pre-filtering before LLM (SQL/regex narrows candidates)" operation #34
- **Where in source:** Phase 1 op #34 (line 200): "Pre-filtering before LLM (SQL/regex narrows candidates, LLM only sees survivors)".
- **PRD/addendum location:** Implicit in verb-API design (FR-3.2) but never stated as a *first-class cost mechanism*. The "SQL/regex first, LLM only on survivors" pattern is a major cost lever.
- **Severity:** **medium**

### LOW

#### G18 — Hermes affordances inventory ("60+ tools, 20+ messaging platforms")
- **Where in source:** Context Guidance (line 30).
- **PRD/addendum location:** Not surfaced. Not load-bearing since Discord is the only platform v1.
- **Severity:** **low**

#### G19 — `bge-small-en-v1.5` *vs* `nomic-embed-text` choice deferred
- **Where in source:** "bge-small-en-v1.5 OR nomic-embed-text" (line 222).
- **PRD/addendum location:** Addendum A3 lists "bge-small / nomic-embed-text" without marking the choice as still-deferred.
- **Severity:** **low**

#### G20 — Outbound `pending_send` second-authorization-check detail
- **Where in source:** Rule P (lines 506–511): "drain worker performs a **second authorization check** — refuses if no fresh grant."
- **PRD/addendum location:** FR-5.5 says "performs a **second** authorization check at drain time — refuses if no fresh grant" — actually captured. **Not a gap.** (Self-correction.)
- **Severity:** N/A — captured.

#### G21 — `enabled_toolsets` per-cron-job toolset narrowing
- **Where in source:** Hermes primitives table (line 676).
- **PRD/addendum location:** Addendum A4 captures it. **Not a gap.**
- **Severity:** N/A — captured.

#### G22 — Hermes auxiliary tasks (compression, title generation) ALSO routed through our `/v1` so Rule Ω applies
- **Where in source:** Rule X (line 628): "Hermes's auxiliary tasks (compression, title generation, etc.) ALSO point at the same endpoint — so Rule Ω extends to Hermes's internal work, not just our verbs."
- **PRD/addendum location:** Addendum A4 mentions `auxiliary.compression → our Router → Qwen` but the *generalization* ("Rule Ω extends to Hermes's internal work") is absent.
- **Severity:** **low–medium** — affects total cost picture if Hermes-internal calls are non-trivial.

#### G23 — Session-summary item: "26 distinct tasks (collapsed from Phase 1's 34)"
- **Where in source:** Line 739: collapsed task count + which were split/merged ("summary_short and summarize_short_thread are separate now; intent_parsing split into chat-interactive vs. background").
- **PRD/addendum location:** Addendum A3 says "14 Qwen tasks + 8 Haiku + 3 Opus + 1 embedding = 26" but doesn't explain the consolidation history. Minor.
- **Severity:** **low**

---

## Qualitative-voice notes that risk being silently dropped

These are the FR-resistant ideas that give MailBot its identity. Several are partially preserved but at lower wattage than the source.

1. **"Defender, not assistant"** — captured (NFR-PERSONA-1) but the source's framing of "defender of attention" (PRD §1.1 has this — good) is one of the few places the qualitative voice survives intact.

2. **"Conservative bias on destructive actions"** — captured in NFR-PERSONA-1 + SOUL.md reference, but the source's *cascading prohibitions* phrasing (Rule Ω: "Two cascading prohibitions, in strict order") is lost. The strictness — first never-distant, second never-high-grade — reads as a moral hierarchy in source, as a bullet list in PRD.

3. **"Rule Ω gives the whole system its soul"** — captured weakly in §2 and §7.3. The session frames it as Adam's *invention* mid-session; the PRD frames it as adopted principle. The authorship lineage is lost. (See G6.)

4. **"Cost as moral hygiene" (implicit voice)** — Phase 4 closing: "Every change to it must be deliberate and evidence-backed." This voice — that policy.yaml is a *ledger of cost commitments*, not config — survives only as the phrase "agent's cost-discipline artifact." (See G4.)

5. **"Single user — period. Not 'single-user first.'"** — captured (PRD §1.2) and *strengthened* well. Good preservation.

6. **"Hermes isn't being reimplemented; MailBot only builds the mailbox-specific intelligence layer"** — captured (§6 + addendum A4) including the "What we do NOT reimplement" list. Good.

7. **"Trade freshness in minutes for no public endpoint"** — captured (FR-1.1, §8) but the *defender-role rationale* ("freshness in minutes is acceptable for a defender role") is muted to just "for a defender role" in addendum A6.

8. **"Pre-mortem $340 instead of $30" scenario** — completely lost (see G5). The scenario is what makes Rules J–O feel necessary rather than overcautious.

9. **"Privacy posture: VPS-local is sufficient. Local Qwen sees all categories"** — completely lost (see G2). This is *the* premise of Rule Q.

10. **"Two cascading prohibitions"** — the rigid ordering ("strict order") of Rule Ω is captured semantically but loses the structural weight of being labeled "cascading prohibitions."

11. **"The 3B↔Opus gap is large; every task kept on 3B is pure savings"** — economic framing of cost discipline, lost. (See G3.)

12. **"Demotion ratchets when benchmarks allow; promotion ratchets only when benchmarks demand"** — Rule Ω consequence. Captured weakly in FR-6.6. The *ratchet metaphor* (one-way mechanism, easier to demote than promote) is what makes Rule Ω self-improving over time.

---

## Numerical/operational parameters — source vs. PRD audit

| Parameter | Source value | PRD value | Status |
|---|---|---|---|
| Sync cadence | 4 min | 4 min (FR-1.1, NFR-PERF-2) | OK |
| Cache TTL alignment | 5 min cache, 4 min warmer | 5 min TTL, 4 min warmer (FR-3.6) | OK |
| Monthly hard cap | $30 | $30 (FR-6.3) | OK |
| Daily soft warning | target ~$1.50/day, warn at $2 | warn at $2 (FR-6.2) | **target ~$1.50/day DROPPED** |
| Per-call refusal | $0.20 | $0.20 (FR-6.4) | OK |
| Default max_tokens_out | 4000 | 4000 (FR-6.1) | OK |
| Chat rate limit | 60/hr | 60/hr (addendum A3) | OK |
| Ingest rate limit | 300/hr | 300/hr (addendum A3) | OK |
| Escalations rate limit | 20/hr | 20/hr (addendum A3) | OK |
| Backpressure ceiling | >500 emails | >500 (FR-2.4, addendum A3) | OK |
| Pipeline batch size | 100 emails | 100 (NFR-PERF-4) | OK |
| Anti-loop window | 10 calls / 5 min | 10 / 5 min (FR-3.8, addendum A3) | OK |
| Hydration rate limit | 5 per agent turn | 5 per turn (addendum A5) | OK |
| Cooling-off | 60s default, configurable to 0 | 60s, configurable (FR-5.3) | OK ("configurable to 0" specific dropped) |
| Daily send cap | 20 outbound/day | 20/day (FR-5.4) | OK |
| Quiet hours | 22:00–08:00 | 22:00–08:00 (FR-7.5) | OK |
| Notification dedup | 5+/hour collapses | 5+/hour (FR-7.5) | OK |
| Response rate fatigue threshold | <30% for a week | <30%/week (FR-7.5, §1.3) | OK |
| Auto-decline window for Tier 3 | "N minutes" (unspecified) | "after N minutes" (FR-7.4) | OK (both unspecified) |
| Local timeout | 30s | 30s (FR-3.4) | OK |
| API timeout | 60s | 60s (FR-3.4) | OK |
| Eval corpus size | ~100 emails | ~100 (FR-8.1) | OK |
| Task families covered | "5 most common" | "8 task families" (FR-8.1) | **CHANGED 5 → 8** |
| Corpus build time | ~3–6 h | "~3–5 hours" (FR-8.1) | **CHANGED 3–6 → 3–5** |
| Anchor examples for subjective scoring | ~20, 1–5 axes | "20 hand-anchored" (FR-8.3) | "1–5 axes" dropped |
| Weekly sampling | 5–10 clicks | "5 random calls" (FR-8.5) | OK-ish (5 vs 5–10) |
| Drift report cadence | weekly | weekly (FR-8.6) | OK |
| Qwen 3B resident size | ~2 GB | not stated | **DROPPED** |
| Embedding model resident | ~100–150 MB | not stated | **DROPPED** |
| Local LLM RAM budget | 4.5–5.5 GB | 4.5–5.5 GB (NFR-HW-2) | OK |
| 3B throughput | ~10 t/s | not stated | **DROPPED** |
| 7B throughput | ~2–5 t/s | not stated | **DROPPED** |
| First-time sync duration | 10–30 min | 10–30 min (FR-1.2) | OK |
| OAuth refresh window concern | 90-day refresh | "90-day refresh-window" (FR-1.6) | OK |
| Backup retention | not specified in source | 14 daily + 8 weekly (NFR-OPS-5) | PRD-ADDED |
| Chat response p95 | not in source explicitly | ≤5s (NFR-PERF-1) | PRD-ADDED |
| Opus draft p95 | not in source explicitly | ≤15s (NFR-PERF-1) | PRD-ADDED |

### Numerical-parameter summary

**Dropped from PRD:**
- Qwen 3B resident size (~2 GB)
- Embedding model resident size (~100–150 MB)
- 3B and 7B CPU throughput numbers (~10 t/s, ~2–5 t/s)
- Daily spend *target* of $1.50/day (only the $2 warning threshold remains)
- "1–5 axes" granularity on subjective scoring anchors
- "Configurable to 0" for cooling-off cleanly

**Changed from source:**
- Eval task families: 5 → 8 (silently expanded)
- Eval corpus build estimate: 3–6h → 3–5h

**Added by PRD (not in source — not gaps, but worth noting):**
- Chat response p95 ≤5s, Opus draft p95 ≤15s (NFR-PERF-1)
- Backup retention: 14 daily + 8 weekly
- Two extra stable error codes: `loop_detected`, `sensitivity_blocks_api`

---

## Overall assessment

**Verdict: acceptable, with significant qualitative-voice and rationale gaps.**

Structurally, the PRD and addendum capture the *what* of every major decision. All 21 rules are mapped, all 4 budget layers preserved, all major numerical parameters intact. The addendum's A6 "rejected alternatives" section is a strong save for decision provenance.

The gaps are concentrated in *rationale, voice, and pre-mortem narrative*:
- The "why" behind Rule F.1 → Router-centrality (G1)
- The privacy premise underwriting Rule Q (G2)
- The economic framing of Rule Ω (G3, G4)
- The six pre-mortem failure modes that justify Rules J–O (G5)
- The session-authored "soul" framing of Rule Ω (G6)
- Several quantified facts about local-LLM performance that justify single-3B commitment (G10, G12, and the throughput-numbers row in the table above)

These are exactly the kinds of qualitative ideas an FR-structure silently drops. Two of them (G2, G3) are load-bearing for downstream decisions and should be reintroduced before architecture phase. The pre-mortem narrative (G5) deserves preservation somewhere — ideally an addendum section A8 "Pre-mortem failure modes" listing the six named scenarios with their rule pairings.

If those three (G2, G3, G5) are addressed, this would move from *acceptable* to *complete*.
