# Story 10-3 Walk Evidence — Qwen batch-lane usage + quality audit

## Session header

| Field | Value |
|---|---|
| Date / TZ | 2026-07-06, Europe/Paris (all DB timestamps UTC Z) |
| Commit at audit | `4a615458e21170d322f4807d48e24ddd1a5ec753` (= story baseline_commit) |
| Run mode | `/autonomous-story-run 10-3` — no run-mode binding (read-only audit, $0); executor split: Claude (fable-5) composes+runs queries and spot-scores in-session; Adam signs verdicts at the Phase 3.5 gate |
| DB | live `mailbot_db` volume via `docker compose exec -T mailbot-api`, opened **read-only**: `sqlite3.connect('file:/data/mailbot.db?mode=ro', uri=True)` — every query in this audit used this idiom; zero writes by construction |
| policy version | `policy-v1-2026-07-04` (router/policy.yaml:17) |
| DB baselines | router_calls=13,600 (max id 13600, max ts `2026-07-06T06:54:59Z`); emails=1,943 (16 with `removed_reason` set, excluded from quality sample) |
| Stack | mailbot-api Up 17h (healthy), mailbot-hermes Up 2d, mailbot-ollama Up 3d (healthy) |
| Anthropic spend | **$0** — zero Router dispatches, zero API calls; audit is SELECT-only |
| Adam signature | _see per-AC verdict lines + footer_ |

---

## Section 1 — AC-1: usage distribution (router_calls GROUP BY model_chosen/task_type)

**Verdict: PASS (delegated walk)** — *Adam-directed "Can you run the manual verification yourself?" 2026-07-06, per 6-13/9.5.5 Phase 3.5 delegation precedent; checkpoints re-verified with fresh commands, see story-run-flags.md § Story 10-3 Manual Verification*

### 1.1 Core GROUP BY (verbatim query + full result)

```sql
SELECT model_chosen, task_type, COUNT(*), SUM(tokens_in), SUM(tokens_out),
       ROUND(SUM(cost_usd_estimated),4), MIN(ts), MAX(ts)
FROM router_calls GROUP BY model_chosen, task_type ORDER BY model_chosen, COUNT(*) DESC;
```

| model_chosen | task_type | n | tok_in | tok_out | est_$ | first | last |
|---|---|---:|---:|---:|---:|---|---|
| claude-haiku-4-5-20251001 | summary_short | 1788 | 1,270,025 | 113,396 | 1.837 | 06-01 | 07-04T21:05 |
| claude-haiku-4-5-20251001 | draft_reply | 373 | 109,695 | 21,138 | 0.2154 | 07-03 | 07-03 |
| claude-haiku-4-5-20251001 | action_extraction | 193 | 203,048 | 13,853 | 0.2723 | 07-03 | 07-04 |
| claude-haiku-4-5-20251001 | importance_scoring | 193 | 193,248 | 27,280 | 0.3296 | 07-03 | 07-04 |
| claude-haiku-4-5-20251001 | chat_completions_tool_call | 98 | 436,335 | 9,360 | 0.2893 | 06-04 | 07-03 |
| claude-haiku-4-5-20251001 | anchor_calibrated_eval | 80 | 2,406,610 | 8,610 | 2.4497 | 07-04 | 07-04 |
| claude-haiku-4-5-20251001 | hermes_aux | 30 | 113,105 | 871 | 0.1175 | 06-01 | 07-03 |
| claude-opus-4-7 | draft_reply | 375 | 139,125 | 26,843 | 4.1001 | 06-04 | 07-03 |
| claude-opus-4-7 | anchor_calibrated_eval | 197 | 4,111,042 | 12,251 | **62.5845** | 07-03 | 07-04 |
| claude-opus-4-7 | chat_completions_tool_call | 7 | 0 | 0 | 0 | 07-03 | 07-03 |
| claude-opus-4-7-20251220 | anchor_calibrated_eval | 226 | 0 | 0 | 0 | 07-03 | 07-03 |
| claude-sonnet-4-5 | anchor_calibrated_eval | 60 | 0 | 0 | 0 | 07-03 | 07-04 |
| hermes-aux / hermes_aux | hermes_aux | 2+6 | 0 | 0 | 0 | 06-01 | 06-03 |
| nomic-embed-text | embedding | 321 | 0 | 0 | 0 | 06-01 | 07-06 |
| qwen2.5:3b-instruct-q4_K_M | sensitivity_class | 6557 | 1,417,572 | 150,669 | 0 | 06-01 | 07-06T06:53 |
| qwen2.5:3b-instruct-q4_K_M | coarse_class | 1936 | 1,388,794 | 78,443 | 0 | 06-01 | 07-06T06:54 |
| qwen2.5:3b-instruct-q4_K_M | fine_class | 1106 | 860,230 | 52,010 | 0 | 06-01 | 07-06T06:53 |
| qwen2.5:3b-instruct-q4_K_M | chat_completions_tool_call | 18 | 0 | 0 | 0 | 07-03 | 07-06 |
| qwen2.5:3b-instruct-q4_K_M | action_extraction | 11 | 11,274 | 1,175 | 0 | 07-05 | 07-06 |
| qwen2.5:3b-instruct-q4_K_M | importance_scoring | 11 | 11,043 | 914 | 0 | 07-05 | 07-06 |
| qwen2.5:3b-instruct-q4_K_M | summary_short | 11 | 4,207 | 309 | 0 | 07-05 | 07-06 |
| qwen2.5:3b-instruct-q4_K_M | hermes_aux | 1 | 158 | 5 | 0 | 07-04 | 07-04 |

**Qwen volume share: 9,651 of 13,600 router calls = 71.0%.** The epic charter's claim "the free tier does most of the ingest volume" is CONFIRMED. Within the ingest classification trio alone (sensitivity/coarse/fine), qwen is 9,599 calls = 100% of that surface.

### 1.2 Conformance vs policy-v1-2026-07-04 (per AC pin 1, using `model_chosen_reason`)

| Observation | Reason evidence | Verdict |
|---|---|---|
| qwen on its 8 policy tasks (sensitivity/coarse/fine dominate) | `policy` / `policy:<task>:default` | CONFORMANT |
| haiku on summary_short / importance_scoring / action_extraction / hermes_aux | `policy` (+ benchmark `override:api:force_model` subsets) | CONFORMANT |
| haiku on draft_reply (373) + anchor_calibrated_eval (80) | `override:api:force_model` — 9.5.3 Haiku-vs-Opus benchmark + 9.5.4 secondary evaluator | EXPLAINED-BY-REASON |
| **qwen on summary_short / importance_scoring / action_extraction / hermes_aux (11+11+11+1)** | `degraded:claude-haiku-4-5-20251001→qwen2.5:3b-instruct-q4_K_M` | EXPLAINED-BY-REASON — but the degraded state itself is finding **F-10-3-1** |
| **qwen on chat_completions_tool_call (18)** | 12 `degraded:…` + 6 `slash_command:one_shot:adam` | EXPLAINED-BY-REASON — but **all 18 failed** → finding **F-10-3-2** |
| opus-4-7-20251220 (226) + sonnet-4-5 (60), all 0-token `failed` | `override:api:force_model` — 9.5.3/9.5.4 unregistered-model dispatches | EXPLAINED-HISTORICAL — already filed+fixed in Epic 9.5 (UnknownModelPricingError gates, A2) |
| `sensitivity_gate:refused` rows (2 each on summary/importance/actions, 6 tool_call) | NFR-PRIV walk artifacts (9.5.2 AC-3) | CONFORMANT |

No unexplained (model, task) pair exists — the `model_chosen_reason` closed set accounts for every row. **Zero silent routing drift.**

### 1.3 Outcome quality on the qwen lane (verbatim query in §1.1 style; full table)

```sql
SELECT task_type, outcome, COUNT(*) FROM router_calls
WHERE model_chosen LIKE 'qwen%' GROUP BY 1,2;
```

| task | ok | retry_recovered | failed |
|---|---:|---:|---:|
| sensitivity_class | 1029 | 912 | **4616** |
| coarse_class | **0** | 1922 | 14 |
| fine_class | **0** | 1105 | 1 |
| action_extraction (degraded) | 0 | 6 | 5 |
| importance_scoring (degraded) | 0 | 11 | 0 |
| summary_short (degraded) | 11 | 0 | 0 |
| chat_completions_tool_call | 0 | 0 | **18** |
| hermes_aux (degraded) | 1 | 0 | 0 |

Segmentation of the sensitivity_class failures by prompt_version (verbatim):

| prompt_v | outcome | n | window |
|---|---|---:|---|
| v1 | failed | 2945 | 2026-06-04 → 06-05 (F24 era — known, filed, fixed by v2) |
| v1 | retry_recovered | 912 | 06-01 → 06-05 |
| v2 | failed | 1048 | 06-06 only (F27 era — known, filed, fixed by v3) |
| v2 | ok | 355 | 06-05 → 06-06 |
| v3 | failed | 623 | **06-06T11:19 → 15:04 only** (backfill day; zero failures since) |
| v3 | ok | 674 | 06-06 → **07-06 (current, 100% ok since 06-07)** |

**Current-era read:** sensitivity_class has been 100% `ok` for a month (last-7-days daily table verified: every day 07-02→07-06 all-ok). The 70% historical failure rate is F24/F27 archaeology, corroborating the existing filings — NOT a live defect. By contrast **coarse_class and fine_class have never returned `ok` once in 3,042 lifetime calls** — 100% of successes go through the schema-fail-retry leg (`retry_recovered` per router.py:895 = first attempt failed schema validation, stricter retry passed). That is a live systematic defect → **F-10-3-4**.

### 1.4 Degraded-mode timeline (the headline operational finding)

```sql
SELECT * FROM degraded_mode_state;          -- (1, active=1, entered_at='2026-07-03T14:41:24.978890Z', exited_at=NULL)
SELECT ROUND(SUM(cost_usd_estimated),2) FROM router_calls
WHERE ts >= '2026-07-01' AND ts <= '2026-07-03T14:41:25';   -- 35.37
SELECT substr(ts,1,7), ROUND(SUM(cost_usd_estimated),2) FROM router_calls GROUP BY 1;
--  2026-06: 1.96   2026-07: 70.24
```

- **Degraded mode is ACTIVE right now and has been since 2026-07-03T14:41:24Z (~2.6 days at audit time), `exited_at=NULL`.**
- Trigger: the budget guard's **$30 monthly hard cap** (`MONTHLY_HARD_CAP_USD = 30.0`, budget.py:37 — MailBot-internal; distinct from the $35 Anthropic **Console** cap the 9.5.x docs cite) was crossed by the guard's in-memory estimator counter mid-9.5.3-benchmark. DB-cumulative July `cost_usd_estimated` at the entry moment was $35.37 — the $5.37 excess over the cap reflects counter-vs-ledger accounting (`add_spend` feeds the counter on successful calls; the router_calls ledger also carries failed-call costs; not fully traced, see amendment A1). Entry is budget-guard-by-design (budget.py: "monthly budget breached — entering degraded mode"), NOT an Anthropic health event: force_model benchmark calls kept succeeding against Anthropic for another day (last ok 07-04T21:21). Live confirmation at verification time: `mailbot status` → `month: $70.2359 / $30.00 cap (234.1%)`, `degraded mode: yes`.
- The counter that tripped is the **local estimator**, whose July numbers are known-inflated: opus `anchor_calibrated_eval` alone carries **$62.58 estimated**, while the Adam-read Anthropic Console total for ALL of July was ~$26 (9.5.4 close, D1 reconciliation). The 3× opus placeholder pricing was fixed only 2026-07-05 (epic-9.5 retro A2, commit 5222589) — historical July rows retain inflated estimates, so July-estimated ($70.24) will stay above the cap until month rollover regardless of real spend.
- Consequence since 2026-07-05 (first post-entry ingest): every Anthropic-policy ingest task (summary_short, importance_scoring, action_extraction) is qwen-served (`degraded:…` reason rows), and qwen tool-call turns fail (§1.3). Filed as **F-10-3-1 / F-10-3-2 / F-10-3-3**.

---

## Section 2 — AC-2: quality spot-score of qwen outputs

**Verdict: PASS (delegated walk)** — *Adam-directed "Can you run the manual verification yourself?" 2026-07-06, per 6-13/9.5.5 Phase 3.5 delegation precedent; checkpoints re-verified with fresh commands, see story-run-flags.md § Story 10-3 Manual Verification*

### 2.1 Scoring methodology (documented BEFORE scoring, incl. post-9.5.4 calibration-posture inheritance)

1. **Posture inheritance.** Per epic-9-5-retro-2026-07-05.md (Adam-signed Path B): the benchmark evaluator pipeline is **single-evaluator-trusted (opus-only) for v1**; cross-evaluator Krippendorff α=0.3490 = honest FAILED-CALIBRATION v1 baseline; α≥0.6 is a v2 gate. This audit does NOT invoke that pipeline (`anchor_calibrated_eval`): it would spend real Anthropic budget (epic allocates $0 to 10-3 — and degraded mode is active, §1.4) and would inherit the failed-calibration caveat anyway.
2. **Evaluator.** claude-fable-5 (the in-session dev model), scoring **categorical agreement** by directly reading each sampled email (from/subject/body_preview) against the exact rubric qwen was given (the SYSTEM text of sensitivity_class/v3.py, coarse_class/v1.py, fine_class/v1.py). Single-evaluator judgment — consistent with, not stronger than, the v1 posture. No inter-rater calibration exists for this evaluator; Adam can overrule item-by-item at Phase 3.5 (every DISAGREE carries a one-line rationale for exactly that purpose).
3. **Why categorical agreement is more defensible than the failed 1–5 rubric axes:** closed 3/6/6-label taxonomies with written label definitions, judged AGREE / DISAGREE / BORDERLINE (BORDERLINE = defensible under the prompt's cautious-bias instructions or genuinely ambiguous — never force-bucketed).
4. **Sample design (size decided at walk time = 29 scored labels, 26 distinct emails).** Stratified DEFECT-HUNTING draw, deliberately oversampling the interesting tails (sensitive/confidential labels, low-confidence rows, `unknown` labels, current-era v3) — **NOT a uniform population sample; the aggregate agreement rate below must not be read as a corpus-wide accuracy estimate.** Population accuracy is bounded-better: the un-oversampled bulk is high-confidence transactional/newsletter/notification traffic, which the sample shows qwen handles well. All rows `removed_reason IS NULL` and `*_model = qwen2.5:3b-instruct-q4_K_M` (provenance verified per-row). Draw = deterministic ORDER BY (conf ASC / id DESC) per stratum — selection SQL recorded in the session transcript; strata: sensitivity 12 (3 confidential-v3, 3 sensitive-v3-lowconf, 2 normal-v3-lowconf, 2 normal-v3-recent, 2 sensitive-v1-tail), coarse 10 (2 human-recent, 1 human-lowconf, 1 newsletter, 2 notification-lowconf, 1 transactional, 1 spam_like, 2 unknown-lowconf), fine 7 (2 cold_outreach, 2 personal, 1 professional, 1 family, 1 unknown).
5. **Privacy discipline.** Truncated subjects (≤60 chars) + sender domain only; no body quoted; for rows the system labeled sensitive/confidential the rationale names the signal type without reproducing content (Rule Q spirit — this evidence file is a gitted artifact).
6. **Framing.** Spot-score verdicts are DEFECT-FILING EVIDENCE (N.5), not a calibrated quality metric; no routing/policy decision may cite them as a benchmark substitute.

### 2.2 Per-item score table

**sensitivity_class** (12 items; v3 unless noted):

| id | sender domain | subject (≤60) | qwen label (conf) | score | rationale |
|---|---|---|---|---|---|
| 3301 | revolut.com | "Votre code d'accès a été modifié ✅" | confidential (0.75) | BORDERLINE | Security notice, but body explicitly contains NO code/token; fails the "must remain on device" test. Defensible only via cautious bias sensitive→confidential |
| 3366 | indy.fr | "🚨 J-30 pour déclarer votre solde d'IS" | confidential (0.75) | DISAGREE | Broadcast tax-deadline reminder from a SaaS; no personal financial data in body. `sensitive` at most; `confidential` (legal/NDA/tokens/identity tier) is a two-notch miss |
| 3424 | bitstack-app.com | "Votre carte bancaire est invalide 💳" | confidential (0.75) | DISAGREE | Payment-instrument status notice = `sensitive` (finances); no credential/token/identity material → not `confidential` |
| 1223 | gmail.com (assoc. list) | "[reparateurs] REFER: Animation des Ateliers…" | sensitive (0.7) | DISAGREE | Community mailing-list broadcast about repair workshops; zero health/financial/family/private signal → `normal` |
| 1271 | freecodecamp.org | "Welcome to freeCodeCamp.org" | sensitive (0.7) | DISAGREE | Body carries a live OTP code — the v3 rubric names "two-factor codes" as `confidential` verbatim. UNDER-classification (inverse direction from the cluster above) |
| 1277 | scalian.com | 'RE: Changement de "tuteur entreprise"…' | sensitive (0.7) | BORDERLINE | Ordinary work-admin thread (tutor change); `normal` is the better read, but interpersonal/HR-adjacent framing makes `sensitive` defensible under cautious bias |
| 1278 | gmail.com | 'Re: Changement de "tuteur entreprise"…' | normal (0.75) | AGREE | Same thread as 1277 — correct label here; note the thread-level inconsistency (same conversation, two labels) |
| 1397 | gmail.com | "Re: cpl" | normal (0.75) | AGREE | Peer technical thread, no sensitive signal |
| 3561 | linkedin.com | "Ce qu'il vous faut : c'est une bonne crise." | normal (0.95) | AGREE | Newsletter |
| 3560 | duolingo.com | "Bienvenue sur Duolingo Famille !" | normal (0.95) | AGREE | Marketing invite |
| 766 | worldofbooks.com | "Re: Where is my item?" | sensitive (0.2, v1) | BORDERLINE | Ground truth `normal` (routine support reply). Conf 0.2 < 0.5 ⇒ the NFR-PRIV-1 classifier backstop governs this label — working-as-designed privacy floor, not a raw qwen judgment |
| 896 | nuwber.zendesk.com | "Request #148938: How would you rate…" | sensitive (0.2, v1) | BORDERLINE | Same backstop mechanism as 766; ground truth `normal` (CSAT survey) |

**coarse_class** (10 items, v1):

| id | sender domain | subject (≤60) | qwen label (conf) | score | rationale |
|---|---|---|---|---|---|
| 3560 | duolingo.com | "Bienvenue sur Duolingo Famille !" | human (0.95) | DISAGREE | Automated service invite ("Stephanie t'invite" = product-templated); rubric human = "a real person addressing the recipient" → `notification`/`newsletter` |
| 3559 | linkedin.com (jobs-noreply) | "Adam, déposez votre candidature maintenant…" | human (0.95) | DISAGREE | Automated job alert from a noreply sender → `notification`. At 0.95 confidence — the exact over-confident pattern F27 closed for sensitivity |
| 524 | gmail.com | "Fwd: Cap sur Brasilia : musiques traditionnelles…" | human (0.75) | AGREE | Real person forwarding an event with a personal note |
| 3561 | linkedin.com (newsletters-noreply) | "Ce qu'il vous faut : c'est une bonne crise." | newsletter (0.95) | AGREE | |
| 1431 | gmail.com | "Re: eval labview" | notification (0.6) | DISAGREE | Real-person peer thread (labview eval answers) → `human`. Inverse miss; the prompt's "prefer notification when in doubt" bias eating a genuine human email |
| 825 | cally.com | "Event changed: Départ nini" | notification (0.65) | AGREE | Automated event-change alert |
| 3557 | headout.com | "Tickets for 1-Day Ticket to Disneyland®…" | transactional (0.95) | AGREE | Booking confirmation |
| 3502 | revolut.com | "Gagnez 80 € pour chaque ami qui s'inscrit…" | spam_like (0.95) | BORDERLINE | Referral marketing from the user's own bank — `newsletter` (marketing broadcast) fits better; "unsolicited bulk" is arguable |
| 253 | beehiiv.com | "CO2 : un actif à 15% par an ?" | unknown (0.35) | DISAGREE | Clear newsletter (beehiiv platform sender, digest content) — `unknown` on a clear case |
| 357 | yahoo.fr | "Fwd: : RELANCE: 9618 - 11 B RUE ROMAIN ROLLAND…" | unknown (0.35) | DISAGREE | Family member forwarding a quote/insurance chain with personal signature → `human` |

**fine_class** (7 items, v1; fires only on coarse=human):

| id | sender domain | subject (≤60) | qwen label (conf) | score | rationale |
|---|---|---|---|---|---|
| 3559 | linkedin.com | "Adam, déposez votre candidature maintenant…" | cold_outreach (0.85) | DISAGREE | Upstream coarse was wrong (automated alert); the rubric's `automated` escape valve exists verbatim for this case and was not used |
| 3545 | linkedin.com | (same alert, earlier instance) | cold_outreach (0.85) | DISAGREE | Same |
| 3560 | duolingo.com | "Bienvenue sur Duolingo Famille !" | personal (0.95) | DISAGREE | Product-templated invite → `automated`; "personal" at 0.95 pollutes the highest-trust relationship bucket |
| 3538 | malt.com | "Adam, donnez un coup de pouce à votre activité" | personal (0.95) | DISAGREE | Platform onboarding broadcast → `automated` |
| 1398 | gmail.com | "Re: cpl" | professional (0.75) | AGREE | Peer/colleague technical exchange |
| 1962 | hotmail.fr (self) | "Merry Christmas and happy new year." | family (0.95) | AGREE | Warm personal mail to host family; `family`/`personal` boundary is soft, label defensible |
| 762 | worldofbooks.com | "Customer Satisfaction" | unknown (0.0) | DISAGREE | Automated CSAT survey → `automated`; conf 0.0 is honest but the label choice ducks the escape valve again |

### 2.3 Aggregate + misclassification patterns

| task | AGREE | BORDERLINE | DISAGREE | clean-agreement (tail-biased sample!) |
|---|---:|---:|---:|---|
| sensitivity_class | 4 | 4 | 4 | 4/12 |
| coarse_class | 4 | 1 | 5 | 4/10 |
| fine_class | 2 | 0 | 5 | 2/7 |
| **total** | **10** | **5** | **14** | **10/29 (34%)** — defect-hunting stratification; not a population accuracy estimate (per §2.1.4) |

**Patterns (systematic, each backed by ≥2 sample items + volume queries):**

- **P1 — coarse `human` over-triggers on personalized automation.** Duolingo/LinkedIn/malt-style templated mail with first-name salutations lands `human` at 0.95. Volume backing: `human` = 1,105 of 1,908 classified live rows (**57.9%** — implausibly high for a real mailbox), and **≥307 of those 1,105 (27.8%) come from automation-pattern senders** (`no-reply%`/`noreply%`/`support@`/`team@`/`hello@`/`newsletters-%`/`info@`/`community%`/`contact@`, incl. 21 linkedin.com + 15 revolut.com rows). Every false `human` also burns a wasted fine_class qwen call (2 calls with the retry defect F-10-3-4).
- **P2 — fine `automated` escape valve has NEVER fired: 0 of 1,105 lifetime fine_class rows.** The v1 prompt ships `automated` explicitly for upstream-was-wrong cases; P1 shows those cases are common (sample: 4/7 fine items were upstream leaks). Instead the leaks land in `cold_outreach` (423 rows — LinkedIn job alerts shaped exactly like this) and `personal` (404 rows) at high confidence, poisoning both buckets for downstream prioritization.
- **P3 — sensitivity over-classification cluster on fintech/security-keyword broadcasts.** Revolut/Indy/Bitstack notices land `confidential` at exactly 0.75 = the v3 borderline-example anchor range; the label AND the confidence look example-anchored (the same anchoring mechanism F27 documented, now in the opposite direction). Volume: v3-era `confidential` = 7 rows, 3 sampled, 2 clear misses + 1 borderline; v3 `sensitive` = 103 rows, sampled tail suggests broadcast leakage into it.
- **P4 — inverse miss: a live OTP body scored `sensitive`, not `confidential`** (item 1271) — the one category the rubric names verbatim ("two-factor codes"). One item, but it is the privacy-tier direction that matters most; `sensitive` and `confidential` differ in digest/body handling downstream.
- **P5 — real-person threads leak into `notification`/`unknown`** (items 1431, 357): the prompt's prefer-notification bias plus forward-header noise costs genuine human mail. Impact: human mail excluded from fine_class refinement + relationship-aware handling.
- **P6 — thread-level label inconsistency** (items 1277 vs 1278): same conversation, `sensitive` vs `normal` on adjacent messages. Per-email classification has no thread memory (design fact, worth knowing when reading per-thread projections).

---

## Section 3 — AC-3: findings FILED per N.5

**Verdict: PASS (delegated walk)** — *Adam-directed "Can you run the manual verification yourself?" 2026-07-06, per 6-13/9.5.5 Phase 3.5 delegation precedent; checkpoints re-verified with fresh commands, see story-run-flags.md § Story 10-3 Manual Verification*

Zero fixes shipped in this story (zero code touched anywhere). All findings below are FILED with evidence pointers; mirrored to `epic-10-run-flags.md` § "Story 10-3".

| ID | Sev | Finding | Evidence | Disposition |
|---|---|---|---|---|
| F-10-3-1 | HIGH (operational) | **Degraded mode active since 2026-07-03T14:41:24Z on an inflated estimator counter** — the budget guard's $30 monthly hard cap (budget.py:37) tripped mid-benchmark (DB-cumulative $35.37 at entry; see §1.4 counter-vs-ledger note), driven by pre-A2 3× opus placeholder pricing ($62.58 estimated on opus eval calls vs ~$26 Console-real for all July). **Under corrected pricing the honest July counter would be ~$26 < $30 — degraded mode would NOT be active.** Historical rows keep inflated estimates post-A2, so estimated-July ($70.24, 234% of cap per live `mailbot status`) stays over cap → degraded until Aug 1 or manual reset. All Anthropic ingest tasks qwen-served since 07-05. Recovery decision (budget reset / accept until rollover / re-derive July estimates at corrected pricing) is Adam's | §1.4 | FILED |
| F-10-3-2 | HIGH (user-facing) | **qwen cannot serve `chat_completions_tool_call`: 18/18 failed** (12 degraded-mode + 6 slash-command one-shot). While degraded mode is active, Hermes tool-calling chat turns dispatched to qwen fail outright — the Discord surface degrades from "cheaper answers" to "no tool answers", which is not the cost-shedding contract's intent | §1.3 | FILED |
| F-10-3-3 | MEDIUM (quality) | **Degraded-qwen `action_extraction` fails ~45%** (5 failed / 6 retry_recovered of 11); the 5 failed emails (ids 13539/13544/13549/13585/13594, 07-05→07-06) have no action extraction. Degraded-qwen importance_scoring is 11/11 retry_recovered (double-call) | §1.3 + row list in transcript | FILED |
| F-10-3-4 | MEDIUM (efficiency/reliability) | **coarse_class + fine_class NEVER pass first-attempt schema validation: 0 `ok` in 3,042 lifetime calls** (1,922+1,105 retry_recovered, 15 failed). Every ingested email pays 2× qwen calls for coarse (and 2 more for fine when human) — latency + local compute doubled by a systematic v1-prompt/schema defect. Contrast: sensitivity_class v3 returns `ok` (its v3 SYSTEM enumerates required JSON fields; coarse/fine v1 SYSTEMs do not — the F24 fix was never propagated to the sibling prompts) | §1.3 | FILED |
| F-10-3-5 | MEDIUM (quality) | **Misclassification patterns P1+P2** — `human` over-trigger on personalized automation (≥27.8% of human rows from automation senders; 57.9% human share) cascading into a dead `automated` escape valve (0/1,105) and poisoned `cold_outreach`/`personal` buckets | §2.3 P1/P2 | FILED |
| F-10-3-6 | LOW (quality/privacy) | **Sensitivity edge behavior**: keyword-anchored `confidential` over-classification on fintech broadcasts (P3) + one live-OTP body under-classified `sensitive` (P4) + human-mail leakage to notification/unknown (P5) + thread-inconsistent labels (P6) | §2.3 P3–P6 | FILED |

Historical corroboration (no new filing): sensitivity_class v1/v2 failure archaeology matches F24/F27 exactly (§1.3); 226 unknown-model + 60 sonnet-4-5 failed eval rows match the already-closed 9.5.x filings.

---

## Section 4 — AC-4: CR cadence

**Verdict: PASS (delegated walk)** — *Adam-directed "Can you run the manual verification yourself?" 2026-07-06, per 6-13/9.5.5 Phase 3.5 delegation precedent; checkpoints re-verified with fresh commands, see story-run-flags.md § Story 10-3 Manual Verification*

Zero code touched (git status confirms: only `_bmad-output/` artifacts + this evidence file). Zero of the 6 CR criteria fire → **CR skipped per cadence binding**, recorded in the story Dev Agent Record.

---

## Footer

- Read-only invariant held: every DB access used `mode=ro` URI; no INSERT/UPDATE/DELETE issued anywhere in the audit.
- End-of-audit `git status` (tracked): modified `.claude/settings.json` (pre-existing), `sprint-status.yaml`, story file; new: this file, run-flags append. No source files.
- Gates at audit close: ruff clean on tracked tree (2 pre-existing T201 in untracked `scratch/walk_bootstrap.py`, out of scope — same residual recorded by 10-1/10-2); mypy --strict clean (129 files); `check_boundaries.py` exit 0; pytest **1708 passed + 2 skipped + 3 deselected** — byte-identical to the 10-2-close baseline (docs-only story confirmed by the suite itself).
- Corrections-appended-never-rewritten rule honored: signed blocks above are final; any post-signature correction lands as an amendment banner below this line.

---

## Amendments

### A1 — 2026-07-06 (delegated verification walk, pre-signature): monthly-cap figure corrected $35 → $30

The original §1.4 / F-10-3-1 text claimed the degraded-mode trigger was "the $35 monthly cap". The delegated Phase 3.5 walk caught this via live `mailbot status` output (`month: $70.2359 / $30.00 cap (234.1%)`): the audit conflated the **$35 Anthropic Console cap** (the figure the 9.5.x docs cite) with MailBot's own budget-guard cap, which is **$30** (`MONTHLY_HARD_CAP_USD = 30.0`, `mailbot_api/router/budget.py:37`). §1.4, the F-10-3-1 row, the story Completion Notes, and the run-flags entry were corrected in place (blocks were still PENDING — unsigned — at correction time; this banner records the change anyway for archaeology). The $35.37 DB-cumulative-at-entry figure itself was re-verified and stands; the $5.37 excess over the $30 cap is counter-vs-ledger accounting (`add_spend` feeds the in-memory counter on successful calls only; the router_calls ledger also carries failed-call costs — not fully traced, noted in F-10-3-1). Net effect on the finding: **strengthened** — honest July spend (~$26 Console-real) is UNDER the $30 cap, so with corrected pricing degraded mode would not be active at all.
