# PRD Quality Review — MailBot (2026-05-31)

## Overall verdict

This is a strong, decision-ready PRD that earns its rigor: Rule Ω is a real thesis, the six "trusts" in §1.3 are testable, and the seven feature areas project cleanly off the 21 ratified rules. The risks are concentrated in done-ness clarity (a handful of FRs lean on adjectives the way the rubric explicitly flags) and a few unresolved `[ASSUMPTION]` and OQ items that should be closed at Finalize but not before status-final.

## Decision-readiness — strong

Decisions are stated as decisions, not deferred to "considerations." §1.5 names ten explicit deferrals; §8 lists six "locked" constraints with the trade given up named (e.g., "Cron-pull only — Trades freshness in minutes for no public endpoint + simplicity"). Counter-metrics in §1.4 are real — "Cost overrun rate (target: 0)" and "Unauthorized-action incidents (target: 0, by construction not by behavior)" — and the "by construction" phrasing in particular signals an honest commitment, not a wish. The Open Questions in §9 are genuinely open (OQ-2 sync-conflict resolution, OQ-4 history vs latest-only) rather than rhetorical. Addendum A1b's causal chain ("the Router is not a layer we chose to build … it falls out of holding the API key in one place") is the kind of trade-off explanation that lets a future maintainer push back productively.

### Findings
- **low** Two `[ASSUMPTION]` tags remain unresolved that the PRD itself flags for Finalize (FR-4.8 slash-command DM parity; FR-6.3 `/budget reset` command name; FR-7.6 default-on for trust-signal). *Fix:* close these in Finalize step 4 per OQ-7 before status moves to `final`.

## Substance over theater — strong

Almost no furniture. Rule Ω in §2 is doing real load-bearing work — every FR-6.x guard, the policy.yaml default-cheapest stance, and the sensitivity-override handshake (FR-5.7) all derive from it. The Vision (§1.1) is genuinely product-specific: "It is not an inbox assistant — it is a defender of attention" would not survive being pasted into a different PRD. There are no personas (correctly, for a single-user system — see Shape fit). NFRs name thresholds rather than adjectives in most places: NFR-PERF-1 "p95 ≤ 5s", NFR-HW-2 "4.5–5.5 GB RAM budget", FR-6.4 ">$0.20 per-call refusal". The "Defender, not assistant" persona in NFR-PERSONA-1 is anchored to four observable behaviors, not a vibe.

### Findings
- **low** §6 "Architecture Anchors (read-only here)" risks being section-furniture since the addendum carries the real content. *Fix:* this is acceptable as a pointer section, but consider a one-line "this section exists so downstream architecture docs have a stable anchor list to ground against" preamble to make the role explicit.

## Strategic coherence — strong

The PRD has a single thesis — "make Rule Ω safe to honor" (§2.2) — and every feature area visibly serves it. The seven-trust decomposition in §1.3 reads as the operationalization of the north-star and is reused as the MVP gate in §7.1 ("All seven trusts hold for a 24-hour test run") and the launch gate in §7.2. Success metrics validate the thesis: "Monthly API spend tracking ≤ $30" measures cost discipline directly, not activity. Counter-metrics in §1.4 are paired with the positive metrics — that pairing is uncommon and well-executed. Feature prioritization is thesis-driven, not what-was-easy: F8 (Eval & Calibration) is called out as "a first-class deliverable, not a nice-to-have" precisely because Rule Ω's "default-cheapest" stance requires measured evidence rather than vibes.

### Findings
*(none — dimension is strong)*

## Done-ness clarity — adequate

This is the weakest dimension and the one most likely to bite downstream. Many FRs are excellent — FR-1.4 "Running sync twice with no inbox changes produces zero writes and zero LLM calls", FR-3.8 "Prompt-hash repeated > 10× in 5 min refuses with `loop_detected`", FR-7.1 "returns within 10 seconds" — these are testable. But several lean on the exact adjectives the rubric flags.

### Findings
- **high** FR-4.2 "responds via Router-routed verb calls in under 5 seconds for typical queries" — "typical queries" is undefined; NFR-PERF-1 says p95 ≤ 5s but the FR doesn't reference it. *Fix:* replace "for typical queries" with "(see NFR-PERF-1)" or inline the p95 bound.
- **high** FR-4.3 Reference resolution — "Pronouns and ellipsis … resolve against recent context + memory" has no testable consequence. What's the success rate? On what corpus? *Fix:* add an acceptance bound, e.g. "≥ 90% correct resolution on the 20-item reference-resolution slice of `email_corpus_v1.jsonl`" or explicitly defer to F8 calibration.
- **medium** FR-4.4 Draft reply flow — describes the loop but doesn't say what makes a draft "good enough to ship." *Fix:* either add an edit-distance/approval-rate proxy (acceptable since the demotion hypothesis already references "edit-distance parity") or explicitly state "subjective quality gated by FR-8.7 shadow-mode comparisons."
- **medium** FR-7.5 Anti-fatigue — "if Adam's response rate drops below 30% for a week, MailBot sends ONE self-reflection message … then goes further quiet until engaged" — "further quiet" and "engaged" are undefined. *Fix:* specify the quiet posture (e.g., "urgent-only until any slash command is issued").
- **medium** FR-2.3 Pipeline ordering — "Sensitivity is first so downstream tasks know whether API is allowed" — implicit acceptance is "no downstream task fires before sensitivity is written," but it's not stated. *Fix:* add explicit invariant: "no Router call for any other task on email_id is permitted until `sensitivity_at IS NOT NULL`."
- **low** FR-8.3 Scorer subjective method — "20 hand-anchored examples + strong-model auto-eval calibrated against anchors" — the calibration method is unspecified (inter-rater agreement threshold? correlation target?). *Fix:* state the calibration acceptance criterion or defer explicitly to M4 design.

## Scope honesty — strong

§1.5 "Out of scope" enumerates 10 deliberate deferrals; §8 lists 6 locked constraints with rationale; §9 surfaces 7 open questions cross-referenced to the brainstorming session. `[ASSUMPTION]` tags appear inline at FR-1.6, FR-4.8, FR-6.3, FR-7.6 — the count is low and each is genuinely an inferred-not-confirmed item. OQ-7 explicitly commits to clean-up at Finalize step 4. The PRD does not silently de-scope: when "no 7B fallback at v1" is decided, it appears in §1.5, §8, NFR-HW-3, AND addendum A6 — visible from every angle a reader might approach it.

### Findings
- **low** No formal Assumptions Index section at the document tail. The four inline `[ASSUMPTION]` tags are scannable but not collected. *Fix:* add an Appendix A "Assumptions Index" listing the four tags with location and Finalize disposition. Per OQ-7 this is already on the Finalize path.

## Downstream usability — adequate

This PRD is chain-top — it feeds architecture, epics, stories, and the existing `policy-v0.yaml` and `phase-4-build-order.md`. FR IDs are contiguous within each area (FR-1.1 through FR-1.7, FR-2.1 through FR-2.7, etc.) and the namespace convention `FR-<area>.<n>` is stated at §4 with a "never renumber, only deprecate" rule. Cross-references mostly resolve (Rule Ω → §2, FR-6.6; the A2 rule-inventory table maps every rule to its PRD location). Most sections survive extraction — F5 (Authorized Actions) and F6 (Cost Governance) read as cleanly portable specs.

The main gap is the absence of a Glossary. Domain nouns like "verb," "lane," "tier" (auth vs LLM cost tier — same word, two meanings), "grant," "RouterResult," "session," "force_model," and "degraded mode" appear repeatedly and are mostly used consistently, but a downstream story author will have to derive their definitions from context.

### Findings
- **medium** No Glossary section. "Tier" in particular is overloaded: §4.5 uses Tier 0–3 for authorization; §4.3 uses tier for LLM cost (Free/Cheap/Premium); FR-5.6 says "the agent cannot promote an action's tier" — readable in context but a glossary entry would prevent future drift. *Fix:* add a Glossary appendix covering at minimum: tier (auth) vs tier (cost), verb, lane, grant, RouterResult, force_model, degraded mode, session (per FR-5.7), sensitivity classes.
- **low** `[ASSUMPTION]` at FR-4.8 is the only one without an inline Finalize-disposition cue beyond the trailing sentence "To resolve at Finalize." *Fix:* OQ-7 covers this generically; no action needed beyond Finalize step 4 itself.
- **low** F8 (FR-8.1..7) vs A3 calibration cadence — both describe the eval loop. They are consistent but a single canonical source would prevent drift. *Fix:* either trim A3's "Calibration cadence" or have F8 say "operational cadence in addendum A3."

## Shape fit — strong

The PRD correctly shapes itself as a capability spec for a single-operator tool. The decision to skip User Journeys is right for the shape: with one user, one notification surface, and one authorization grantor, UJs would be theater. The decision is documented (per the briefing context) and the PRD instead leans on §7's MVP scenarios ("A Discord message at 10pm — 'show me unread from today'") which carry the journey-shaped content where it actually adds value. Capability-first organization (§3 Capability Map, then §4 FRs by area) matches the agent-tool genre. SMs in §1.3 are operational (cost trust, send trust, sync trust) rather than user-facing engagement metrics — correct for the shape. Stakes calibration is appropriate: the PRD is rigorous where rigor pays (cost discipline, sensitivity routing, authorization) and light where it would be overhead (no GTM, no pricing model, no stakeholder map).

### Findings
*(none — dimension is strong; UJ omission is correct for the shape)*

## Mechanical notes

- **Glossary drift:** no glossary present (see Downstream usability finding). Most terms used consistently, but "tier" is overloaded across auth and cost contexts.
- **ID continuity:** FR IDs contiguous within each area: F1 (1.1–1.7), F2 (2.1–2.7), F3 (3.1–3.10), F4 (4.1–4.8), F5 (5.1–5.7), F6 (6.1–6.7), F7 (7.1–7.7), F8 (8.1–8.7). NFR IDs grouped by category (PRIV, SEC, OPS, PERF, HW, PERSONA) — readable. OQ IDs OQ-1 through OQ-7, contiguous.
- **Cross-references:** spot-checked — Rule Ω → §2 ✓; FR-7.5 self-correction reference cited from §1.4 ✓; FR-2.4 backpressure → Rule K ✓; Addendum A2 rule inventory → PRD locations resolved on inspection. No broken refs detected.
- **Assumptions Index roundtrip:** no Index section. Four inline `[ASSUMPTION]` tags found (FR-1.6, FR-4.8, FR-6.3, FR-7.6). OQ-7 commits to ratification at Finalize step 4.
- **UJ protagonist naming:** N/A — UJs deliberately omitted; protagonists named in §7 MVP scenarios as "Adam" implicitly.
- **Required sections present:** Vision, Strategic Foundation, Capability Map, FRs, NFRs, Architecture Anchors, Success Criteria, Constraints, Open Questions, Decision Provenance — all present. Glossary absent (flagged).
