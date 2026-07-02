---
title: Reconciliation — policy-v0.yaml vs. prd.md + addendum.md
source: _bmad-output/brainstorming/policy-v0.yaml
produced:
  - _bmad-output/planning-artifacts/prds/prd-MailBot-2026-05-31/prd.md
  - _bmad-output/planning-artifacts/prds/prd-MailBot-2026-05-31/addendum.md
created: 2026-05-31
verdict: acceptable
---

# Reconciliation — policy-v0.yaml against PRD + Addendum

## Method

Walked policy-v0.yaml linearly. For each task entry and each operational note, located the corresponding reflection in either prd.md or addendum.md (§A3 is the obvious home for the policy table). Gaps are anything in the source that did not survive into either produced artifact.

The PRD itself does not attempt to reproduce the policy table — that work is delegated to addendum §A3, which is correct division of labor. So per-task gap accounting is judged against §A3.

---

## 1. Per-Task Coverage Table

Legend: ✓ = present, ~ = partial, ✗ = missing.

### TIER PREMIUM (Opus)

| Task                 | In addendum? | Hypothesis preserved?              | Rationale preserved?                          | Gap notes                                                                                  |
| -------------------- | ------------ | ---------------------------------- | --------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `draft_reply`        | ✓ (A3 Opus)  | ✓ "Very weak — edit-distance parity" | ~ "single most quality-critical" not echoed   | `sensitivity: allowed` + per-session-confirm-on-sensitive nuance lives in NFR-PRIV-2, not in the table. `max_tokens_out=800` not in table. `cache SYSTEM aggressively` covered by FR-3.6. |
| `tone_style_mirror`  | ✓            | ✓ "Medium — Haiku may match with style examples" | ~ "may collapse INTO draft_reply" note lost   | The "may collapse into draft_reply" architectural note is dropped — minor.                |
| `user_model_refresh` | ✓            | ✓ "Weak — synthesis quality matters" | ~ "≤1×/month unless force=true" partly preserved (≤1×/month only) | `force=true` override path not surfaced. `max_tokens_out=2000` not in table.              |

### TIER CHEAP (Haiku)

| Task                    | In addendum? | Hypothesis preserved?                                | Rationale preserved?                                          | Gap notes                                                                                  |
| ----------------------- | ------------ | ---------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `action_extraction`     | ✓            | ✓ "Medium — bench 3B; demote if ≥ 90% on dates + asks" | ✓ rationale (3B hallucinates dates) partially implied         | escalate=true → opus reason "missing a deadline is costly" not stated.                    |
| `importance_scoring`    | ✓            | ✓ "Weak — likely stays on Haiku"                    | ~ "requires user-model context" not stated                    | The user-model-context coupling rationale is lost.                                         |
| `intent_parsing_chat`   | ✓            | ✓ **STRONG** preserved with threshold                | ~ "UX bar < 2s … 3B 2-5s borderline" not in table             | Latency rationale dropped from the row; partially reflected in NFR-PERF-3.                |
| `reference_resolution`  | ✓            | ✓ "Medium"                                          | ✗ "pronoun resolution, short-term context + memory recall" lost | Verbal example list ("That one", "the lawyer") not preserved in addendum.                |
| `subscription_audit`    | ✓            | ✓ "Medium — viable on 3B if pre-classified"         | ~ "reads dozens of emails via hydration" not stated           | Rule-J hydration coupling lost from this task's row.                                       |
| `bulk_action_proposals` | ✓            | ✓ **STRONG** "3B may handle if summaries are clean" | ~ "Explanation quality matters for trust" lost                | Trust-coupled rationale lost.                                                              |
| `summarize_long_thread` | ✓            | ✓ "Weak — 3B context too small"                     | ~ ≤3 emails / ≤2K-token routing rule lost                     | The size-based routing split with `summarize_short_thread` not made explicit in addendum. |

### TIER FREE (Qwen 3B)

The addendum lists Qwen tasks by name only (no per-task table); rationales and hypotheses are largely flattened.

| Task                        | In addendum? | Hypothesis preserved? | Rationale preserved? | Gap notes                                                                              |
| --------------------------- | ------------ | --------------------- | -------------------- | -------------------------------------------------------------------------------------- |
| `coarse_class`              | ✓ name only  | n/a (default tier)    | ~ "cached forever" implicit via Rule A | The 6-category taxonomy (transactional / newsletter / human / notification / spam_like / unknown) not enumerated. |
| `fine_class`                | ✓ (escalate→haiku noted) | ✓ **PROMOTION HYPOTHESIS** ("cold outreach vs real prospects") preserved? | ✗ — the specific promotion hypothesis text is **not preserved** in addendum | **GAP**: 4-subcategory taxonomy (personal / professional / cold outreach / automated-but-human-looking) and promotion hypothesis rationale lost. |
| `sensitivity_class`         | ✓ (called out as local_only) | n/a   | ✓ via FR-2.5 + NFR-PRIV-1 | "default to sensitive on uncertain" preserved in NFR-PRIV-1. "Anthropic API never sees an email that hasn't been sensitivity-classified" preserved via FR-2.3 ordering. |
| `auto_file_decision`        | ✓ name only  | n/a                  | ~ Tier 1/2 reference lost  | The "Tier 1/2 action (Rule P)" coupling not surfaced.                                |
| `unsubscribe_candidate`     | ✓ name only  | n/a                  | ~ "Tier 2 action — batch approval" reference lost | Tier-2 batch-approval coupling lost from the row.                                      |
| `notification_decision`     | ✓ name only  | n/a                  | ~ "Rules + 3B tiebreaker" lost | The "mostly rules-based" framing is absent.                                            |
| `thread_continuity`         | ✓ name only  | n/a                  | ~ "memory lookup + small LLM tiebreaker" lost | Memory-lookup coupling lost.                                                           |
| `summary_short`             | ✓ name only  | n/a                  | ✓ Rule A caching covered | "Foundation of Rule J hydration model" framing covered via FR-3.5 / verbs in §A5.    |
| `summarize_short_thread`    | ✓ (escalate→haiku noted) | n/a   | ~ "≤3 emails, ≤2K tokens" threshold lost | The numerical split with `summarize_long_thread` is not preserved.                    |
| `sender_reputation_summary` | ✓ name only  | n/a                  | ✓ FR-2.7 preserves "first-sender" one-liner, cached forever | Good coverage.                                                                         |
| `daily_digest`              | ✓ name only  | n/a                  | ✓ FR-7.7 preserves "templating, not synthesis" | Good coverage.                                                                         |
| `anomaly_detection`         | ✓ name only  | n/a                  | ~ "unknown-country login / currency mismatch" examples lost | Specific examples lost.                                                                |
| `promised_reply_check`      | ✓ name only  | n/a                  | ~ rationale lost      | "Adam said he'd reply, he hasn't" framing lost from this row.                         |
| `multi_turn_refinement`     | ✓ (escalate→haiku, opus on force_model noted) | n/a | ~ "Make that draft shorter / warmer / more formal" lost | UX example lost; behavior preserved.                                                   |

### NON-LLM

| Task        | In addendum?       | Rationale preserved?                                              | Gap notes                                                                  |
| ----------- | ------------------ | ----------------------------------------------------------------- | -------------------------------------------------------------------------- |
| `embedding` | ✓ (A3 Embedding)   | ✓ "~100 MB resident, near-free CPU"; vectors-in-SQL via Rule A    | `sensitivity: local_only` for embeddings not explicitly stated in addendum (implicit via Q for bge-small). |

---

## 2. Operational Settings Coverage

| Setting                                | In source             | In addendum                                  | In PRD                                | Status   |
| -------------------------------------- | --------------------- | -------------------------------------------- | ------------------------------------- | -------- |
| `monthly_cap_usd: 30`                  | yes                   | ✓ A3 "Budget"                                | ✓ §1.3, FR-6.3, §8                    | ✓ full   |
| `daily_warn_threshold_usd: 2`          | yes                   | ✓ A3 "Budget"                                | ✓ FR-6.2                              | ✓ full   |
| `per_call_refusal_usd: 0.20`           | yes                   | ✓ A3 "Budget"                                | ✓ FR-6.4                              | ✓ full   |
| Degraded-mode chain opus→haiku→qwen    | yes                   | ✓ A3 "Budget"                                | ✓ FR-6.3                              | ✓ full   |
| chat rate limit 60/hr                  | yes                   | ✓ A3                                         | ✓ FR-3.5                              | ✓ full   |
| ingest rate limit 300/hr               | yes                   | ✓ A3                                         | ✓ FR-3.5                              | ✓ full   |
| ingest backpressure queue > 500        | yes                   | ✓ A3 (implicit)                              | ✓ FR-2.4, NFR-PERF-4                  | ✓ full   |
| escalations 20/hr + circuit-breaker    | yes                   | ✓ A3 "circuit-breaker"                       | ✓ FR-3.5 (number only; breaker mention thin) | ~ partial — circuit-breaker behavior named in addendum, but "pause escalations" effect not made operational in PRD |
| Anti-loop: prompt-hash 10 calls / 5min | yes                   | ✓ A3                                         | ✓ FR-3.8                              | ✓ full   |
| Sensitivity routing 3 tiers            | yes                   | ✓ A3                                         | ✓ NFR-PRIV-2                          | ✓ full   |
| Cache warmer every 4 min, TTL 5 min    | yes                   | ✓ A3                                         | ✓ FR-3.6, NFR-PERF-2                  | ✓ full   |
| Continuous eval weekly sampling (5)    | yes                   | ✓ A3                                         | ✓ FR-8.5                              | ✓ full   |
| Weekly drift report (coarse_class)     | yes                   | ✓ A3                                         | ✓ FR-8.6                              | ✓ full   |
| **Calibration cadence 6 steps**        | yes                   | ✓ A3 — 6 steps preserved verbatim-in-spirit  | ~ §7.3 mentions "calibration loop runs continuously" but not the 6-step procedure | ~ partial — the explicit 6-step recipe lives only in addendum; PRD does not point at it |
| **"This file is the agent's cost-discipline artifact" framing** | yes | ✗ not in addendum verbatim | ✓ §7.3 echoes it: "policy file is the **agent's cost-discipline artifact** — every change is a deliberate, evidence-backed act" | ✓ PRD preserves the framing |

---

## 3. Schema-Level Coverage

The source schema is `{model, prompt, escalate, max_tokens_out, lane, sensitivity, notes}` per task.

| Field            | Preserved in addendum?                                                                 |
| ---------------- | -------------------------------------------------------------------------------------- |
| `model`          | ✓ (tier-grouped)                                                                       |
| `prompt`         | ✓ (v1 shown in Opus / Haiku tables; assumed v1 for Qwen rows)                          |
| `escalate`       | ✓ (Haiku table column; called out for Qwen escalating tasks)                           |
| `max_tokens_out` | ✗ **per-task token caps not preserved in addendum.** Only the general "Default 4000; task-overridable" appears in PRD FR-6.1. **Each row's cap (e.g., 800 / 300 / 50 / 30 / 2000) is lost.** |
| `lane`           | ✓ (interactive / batch column in Opus + Haiku tables; bucketed for Qwen)               |
| `sensitivity`    | ~ partial — only `local_only` cases called out; `allowed` is implicit for the rest    |
| `notes`          | ~ partial — flattened into a single "Demotion hypothesis" column for Opus/Haiku; mostly lost for Qwen rows |

---

## 4. Hypotheses Audit

| Type                  | Source rows                                                                                       | Preserved? |
| --------------------- | ------------------------------------------------------------------------------------------------- | ---------- |
| DEMOTION HYPOTHESIS (Opus, 3 tasks)   | draft_reply (very weak), tone_style_mirror (medium), user_model_refresh (weak)                    | ✓ all 3    |
| DEMOTION HYPOTHESIS (Haiku, 7 tasks)  | action_extraction (medium), importance_scoring (weak), intent_parsing_chat (STRONG), reference_resolution (medium), subscription_audit (medium), bulk_action_proposals (STRONG), summarize_long_thread (weak) | ✓ all 7   |
| PROMOTION HYPOTHESIS (Qwen→Haiku)     | `fine_class` — "may need Haiku if 3B can't tell cold outreach from real prospects"                | ✗ **LOST** in addendum (only the `escalate→haiku` flag survives, rationale dropped) |

**Promotion-hypothesis count:** 1 in source, 0 in addendum. The PRD does mention PROMOTION HYPOTHESIS as a concept (NFR-PERF-3) and FR-6.6 references "DEMOTION HYPOTHESIS" inline, but no Qwen-row-specific promotion content is preserved.

---

## 5. Gaps by Severity

### Critical
None. Every numerical budget guard, rate limit, sensitivity rule, and tier assignment is present somewhere in the produced artifacts.

### High

1. **Per-task `max_tokens_out` caps lost.** The source pins 17 distinct per-task output ceilings (e.g., draft_reply=800, importance_scoring=50, sensitivity_class=30, daily_digest=800, user_model_refresh=2000). FR-6.1 says "Default 4000; task-overridable" — but the per-task overrides themselves are not enumerated. **Operational consequence:** policy.yaml itself remains canonical; downstream readers cannot reconstruct the budget envelope from the addendum alone.
2. **`fine_class` PROMOTION HYPOTHESIS lost.** The only promotion hypothesis in the source ("cold outreach vs. real prospects") was dropped. Calibration §A3 step 5 still names the general procedure ("if escalation rate > 30%, PROMOTION HYPOTHESIS won"), but the specific failure-mode-to-watch for fine_class is gone.

### Medium

3. **Per-task `notes` rationales heavily compressed.** The addendum's Haiku/Opus tables keep a single "Demotion hypothesis" column. The richer "why this tier" rationales — coupling to user-model context (importance_scoring), latency budget (intent_parsing_chat), hydration-reads (subscription_audit), trust-via-explanation-quality (bulk_action_proposals) — are largely flattened.
4. **No Qwen per-task table at all.** All 14 Qwen tasks are listed as a comma-separated name dump in §A3. Rationales like "Rules + 3B tiebreaker" (notification_decision), "memory lookup + tiebreaker" (thread_continuity), "≤3 emails, ≤2K tokens" boundary (summarize_short_thread), Tier-1/Tier-2 action coupling (auto_file_decision, unsubscribe_candidate) are dropped.
5. **Taxonomy enumerations lost.** `coarse_class` 6 categories (transactional / newsletter / human / notification / spam_like / unknown) and `fine_class` 4 sub-categories (personal / professional / cold outreach / automated-but-human-looking) are not enumerated in the produced artifacts.
6. **Calibration 6-step recipe lives only in addendum.** The PRD §7.3 paraphrases continuous-improvement but does not point to or summarize the explicit 6-step calibration cadence. A reader of the PRD alone misses the operational ritual.

### Low

7. **`tone_style_mirror` may collapse into draft_reply** architectural note dropped (minor design hint).
8. **`user_model_refresh force=true` override** is mentioned in source but not surfaced; only "≤1×/month" survives.
9. **`summarize_long_thread` escalate→opus reason** ("user requests deep summary") dropped.
10. **`action_extraction` escalate→opus reason** ("missing a deadline is costly") dropped.
11. **Specific anomaly_detection examples** ("unknown-country login alerts, currency mismatch on invoices") dropped.
12. **Reference-resolution UX examples** ("That one", "the lawyer", "Marc's last email") and `multi_turn_refinement` UX examples ("shorter / warmer / more formal") dropped from per-task rows — though equivalent examples do appear in §4.4 FR-4.3 of the PRD for reference_resolution.
13. **`embedding sensitivity: local_only`** not explicitly carried into addendum (implied by being a local model).
14. **Sensitivity-class "default to `sensitive` when uncertain"** is preserved (NFR-PRIV-1) — noted as a non-gap for completeness.

---

## 6. "Cost-Discipline Artifact" Framing

The source closes with: *"This file IS the artifact that captures the agent's cost discipline. Every change to it should be a deliberate, evidence-backed act."*

- **PRD §7.3 preserves this nearly verbatim:** "The policy file is the **agent's cost-discipline artifact** — every change is a deliberate, evidence-backed act."
- **FR-6.6 reinforces it:** "Each escalation … carries an inline `notes` justification *and* a 'DEMOTION HYPOTHESIS' to be tested by F8 benchmarks. Every Opus assignment must cite a benchmark run."

Verdict on framing: **fully preserved**, and propagated as a first-class product principle (Rule Ω in §2 + §7.3 continuous-improvement clause).

---

## 7. Verdict

**acceptable** — with two High-severity items worth resolving before policy-v0 is considered "captured" by the PRD set:
- (a) Add per-task `max_tokens_out` ceilings to the addendum table (or explicit pointer to policy.yaml as canonical source for caps).
- (b) Preserve the `fine_class` PROMOTION HYPOTHESIS verbatim — it is the only promotion hypothesis in the source and a deliberate calibration signal.

All numerical operational settings, sensitivity rules, tier assignments, demotion hypotheses, and the cost-discipline framing are intact. Medium gaps are mostly compression of per-task rationale that policy.yaml itself remains the canonical home for — acceptable as long as policy.yaml is treated as a live artifact (which §7.3 explicitly says it is).
