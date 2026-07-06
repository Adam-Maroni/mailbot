---
baseline_commit: 4a615458e21170d322f4807d48e24ddd1a5ec753
---

# Story 10.3: Qwen batch-lane usage + quality audit

Status: done (audit executed 2026-07-06 autonomous; Phase 3.5 delegated walk PASS WITH FINDINGS — Adam-directed "run the manual verification yourself", 1 walk-caught finding WALK-10-3-F1 corrected in-walk; see story-run-flags.md § Story 10-3 Manual Verification)

<!--
Walk/audit story, Epic 10 README-as-charter UAT. NOT an implementation story: it produces
audit evidence (usage distribution + spot-scored quality sample) and defect FILINGS, not code.

NO RUN-MODE BINDING (deliberate, unlike 10-1/10-5): every step is read-only against the live
DB ($0 spend, zero mailbox mutation, zero Router dispatch). Autonomous execution is compatible;
Adam signs the per-AC verdicts at the end-of-run manual-verification gate (Phase 3.5), matching
the walk-evidence signature convention.

SEQUENCING CONSTRAINT (HARD, satisfied): fires only after Epic 9.5 close — epic-9-5 done-flipped
2026-07-05 (retro epic-9-5-retro-2026-07-05.md); the scoring methodology inherits the
post-9.5.4 calibration posture (see Dev Notes § Scoring methodology).

Scope fence (N.5 policy): this story FILES findings with evidence attached; it fixes NOTHING.
Any in-audit code fix escalates CR per §5.12.
-->

## Story

As Adam,
I want a ground-truth answer to "what is qwen actually doing in production" — a `router_calls` GROUP BY `model_chosen`/`task_type` query against the live DB — plus spot-scoring of a sample of qwen outputs on `sensitivity_class` / `coarse_class` / `fine_class`,
So that the free tier's actual usage and quality are audited evidence rather than assumptions, and any misclassification patterns become filed defects with data behind them.

## Acceptance Criteria

**AC-1 — Usage distribution captured**
**Given** the live local DB
**When** the usage query fires
**Then** the `router_calls` GROUP BY `model_chosen`/`task_type` distribution is captured in walk evidence — which tasks qwen actually serves, at what volume, vs what `policy.yaml` says it should serve

**AC-2 — Quality spot-score with documented methodology**
**Given** the usage distribution
**When** the quality audit fires
**Then** a sample of qwen outputs on `sensitivity_class` / `coarse_class` / `fine_class` is spot-scored (sample size decided at walk time and recorded), with the scoring methodology documented in the evidence — including its inheritance from the post-9.5.4 calibration posture

**AC-3 — Findings FILED, not fixed**
**Given** the audit surfaces misclassification patterns
**When** findings emerge
**Then** they are FILED per the N.5 policy (defect filings with the evidence attached) — this story does NOT absorb fixes

**AC-4 — CR cadence**
**Given** this is a walk/audit story
**When** CR cadence is evaluated per the 6 criteria
**Then** zero criteria fire → CR skipped per cadence binding

### AC interpretation pins (code-reality; read before executing)

- **AC-1's "vs what policy.yaml says":** at `policy-v1-2026-07-04`, qwen (`qwen2.5:3b-instruct-q4_K_M`) is the policy model for exactly 8 task types: `coarse_class`, `sensitivity_class`, `fine_class`, `sender_reputation_summary`, `thread_continuity`, `intent_parsing_chat` (escalate:true), `reference_resolution` (escalate:true), `daily_digest_intro`. The comparison is two-directional: (a) qwen rows on tasks policy does NOT give it, and (b) non-qwen rows on qwen-policy tasks — both legitimate only via the closed `model_chosen_reason` set (`policy` / `override` / `degraded` / `response_cache_hit` / `force_override` / `escalated_from_<X>`). Any drift outside those reasons is a finding.
- **AC-2's "sample of qwen outputs":** the stored derived fields on `emails` ARE the qwen outputs — `sensitivity` / `class_coarse` / `class_fine` with `*_model` / `*_conf` / `*_prompt_v` / `*_at` companions. Spot-scoring = re-judging the stored label against the email content. Only rows whose `*_model` companion names qwen are in the qwen sample (the companion is the provenance pin; escalate:false on all three tasks predicts 100% qwen, verify don't assume).
- **AC-2's "sample size decided at walk time":** decide from observed volume; recommended ≥20 scored labels stratified across the 3 task types, oversampling `sensitive`/`confidential` sensitivity rows and low-`*_conf` rows (the interesting tails). Record the actual N + selection rule in evidence.
- **Verdict vocabulary:** PASS / PARTIAL-PASS / FAIL per AC section, Adam-signed at the Phase 3.5 gate, per the 9.5.x/10-1 walk-evidence convention.

## Tasks / Subtasks

- [x] **Task 0 — Pre-audit stack + baseline capture (BLOCKING)** (AC: 1)
  - [x] 0.1 `docker ps` → `mailbot-api` healthy (the live DB lives in the `mailbot_db` named volume at `/data/mailbot.db`; the audit reads it through the container — image has NO sqlite3 CLI, use `docker compose exec -T mailbot-api python -c "import sqlite3, json; ..."`)
  - [x] 0.2 Record into evidence header: `git rev-parse HEAD`, audit date/TZ, `policy.yaml` version line (`policy-v1-2026-07-04` expected), DB row baselines — `SELECT COUNT(*) FROM router_calls;`, `SELECT COUNT(*) FROM emails;`, `SELECT MAX(id), MAX(ts) FROM router_calls;`
  - [x] 0.3 Read-only discipline pin: every audit query opens the DB with `sqlite3.connect("file:/data/mailbot.db?mode=ro", uri=True)` — zero-mutation guarantee by construction; record the connection idiom verbatim in evidence

- [x] **Task 1 — Usage distribution query (AC-1)**
  - [x] 1.1 Fire the core GROUP BY: `SELECT model_chosen, task_type, COUNT(*), SUM(tokens_in), SUM(tokens_out), ROUND(SUM(cost_usd_estimated),4), MIN(ts), MAX(ts) FROM router_calls GROUP BY model_chosen, task_type ORDER BY model_chosen, COUNT(*) DESC;` → full table into evidence
  - [x] 1.2 Supplement with the drift lenses: `model_chosen_reason` distribution per (model, task) — `SELECT task_type, model_chosen, model_chosen_reason, COUNT(*) FROM router_calls GROUP BY 1,2,3;` — and `outcome` distribution per qwen task — `SELECT task_type, outcome, COUNT(*) FROM router_calls WHERE model_chosen LIKE 'qwen%' GROUP BY 1,2;`
  - [x] 1.3 Compare against the policy expectation table (AC pin 1): mark each (model, task) pair CONFORMANT / EXPLAINED-BY-REASON / DRIFT; qwen share of total call volume computed and recorded ("the free tier does most of the ingest volume" is the epic's claim — test it)
  - [x] 1.4 Any DRIFT rows → candidate findings for Task 3 (FILED, not fixed)

- [x] **Task 2 — Quality spot-score (AC-2)**
  - [x] 2.1 Decide + record the sample: stratified draw across `sensitivity_class` / `coarse_class` / `fine_class` per AC pin 2-3 (recommended ≥20 total; oversample sensitive/confidential + low-conf tails; fine_class only exists where `class_coarse='human'`). Record the exact SELECTs used for the draw
  - [x] 2.2 Verify provenance on every sampled row: `*_model` companion names qwen (`qwen2.5:3b-instruct-q4_K_M`); non-qwen rows are excluded from the qwen quality verdict (but their existence is Task 1 drift data)
  - [x] 2.3 Score each sampled label against the email content (from/subject/body_preview read in-session, read-only): AGREE / DISAGREE / BORDERLINE + one-line rationale per item, against the closed taxonomies (sensitivity: normal/sensitive/confidential; coarse: transactional/newsletter/human/notification/spam_like/unknown; fine: personal/professional/family/cold_outreach/automated/unknown)
  - [x] 2.4 Document the scoring methodology in evidence BEFORE the per-item table, including the post-9.5.4 calibration posture inheritance (Dev Notes § Scoring methodology — single-evaluator posture, evaluator identity, $0/no-benchmark-pipeline rationale, known limits)
  - [x] 2.5 Privacy discipline: evidence records truncated subjects (≤60 chars) + sender domain class only; NO full bodies quoted; for `sensitive`/`confidential` rows, record the label judgment + rationale WITHOUT quoting content (Rule Q spirit — confidential bodies never leave the local surface, and walk evidence is a gitted artifact)
  - [x] 2.6 Aggregate: per-task agreement rate + misclassification pattern candidates (systematic, not one-off — e.g., "newsletters with personal salutations skew human", "borderline professional/personal defaults to X")

- [x] **Task 3 — Findings FILED per N.5 (AC-3)**
  - [x] 3.1 Each misclassification pattern (Task 2.6) + each usage drift (Task 1.4) + anything else surfaced → `## Walk-discovered findings (F-track)` table in evidence: severity | finding | disposition=FILED (with evidence pointer)
  - [x] 3.2 Mirror the findings into `epic-10-run-flags.md` § "Story 10-3" (append; file exists since 10-1)
  - [x] 3.3 Zero fixes shipped — if ANY code/config/prompt change is proposed, it is written into the filing text as a recommendation, never applied here

- [x] **Task 4 — Compose `10-3-walk-evidence.md`**
  - [x] 4.1 Structure per the 10-1/9.5.x conventions: `## Session header` table (date+TZ, commit, policy version, DB baselines, executor split, Adam signature line) → `## Section 1 — AC-1` / `## Section 2 — AC-2` / `## Section 3 — AC-3` each opening `**Adam-signed verdict: PENDING**` (flipped at Phase 3.5) → evidence blocks (SQL + result tables verbatim, fenced) → findings table → `## Footer` (end `git status`, gate counts, corrections-appended-never-rewritten rule honored)
  - [x] 4.2 Honesty rules: all queries verbatim; sample selection rule recorded before scoring; no simulated data; scoring-limits caveats stated, not buried

- [x] **Task 5 — CR determination, run-flags, sprint flip, stage (AC-4; never commit autonomously)**
  - [x] 5.1 CR cadence determination per AC-4: zero criteria fire if no code was touched → record "CR skipped per cadence binding" in Dev Agent Record; if ANY code shipped, escalate per §5.12 instead
  - [x] 5.2 Append the Story 10-3 run record to `epic-10-run-flags.md` (audit scope, sample size, agreement rates, findings count)
  - [x] 5.3 Run the 4 gates for the evidence footer (ruff / mypy / boundaries / pytest — expect unchanged: docs-only story)
  - [x] 5.4 Flip `sprint-status.yaml` `10-3-qwen-batch-lane-usage-and-quality-audit` → `review` at audit close, → `done` on Adam's signed verdicts; stage all changes (`rtk git add` explicit paths); Adam decides the commit

## Dev Notes

### Why no RUN-MODE BINDING (decision record)

10-1/10-5 carry Adam-hands-on bindings because they mutate the real mailbox and/or spend real Anthropic budget. 10-3 does neither: it is read-only SQL against the live DB (`mode=ro` URI pin, Task 0.3) plus in-session judgment. $0 spend — the epic budget allocates real spend only to 10-5 (~$2-4). Adam's hands-on role is verdict-signing, which the autonomous-run Phase 3.5 gate provides. If at any point the audit would require a Router dispatch, a mailbox touch, or any Anthropic call, HALT — that exceeds this story's read-only charter.

### Live-DB access pattern (from 10-1/10-2 walk records)

- DB: named volume `mailbot_db` → `/data/mailbot.db` inside `mailbot-api` (`MAILBOT_DB_PATH=/data/mailbot.db`). NOT bind-mounted to the host; the repo-root `mailbot.db` is a dev artifact, NOT the live DB — do not audit it.
- The image has NO sqlite3 CLI. Pattern: `docker compose exec -T mailbot-api python -c "import sqlite3, json; con=sqlite3.connect('file:/data/mailbot.db?mode=ro', uri=True); ..."` printing JSON/rows to stdout.
- Ops note (10-2, durable memory `ops_msys_path_mangling_docker_exec.md`): Git-Bash MSYS mangles bare `/data`-style path ARGS through docker exec; paths embedded inside a `python -c` string are safe. If a path arg is ever needed, `MSYS_NO_PATHCONV=1`.
- Keep result sets bounded (GROUP BYs + LIMITed samples); never dump full bodies to stdout for `confidential` rows (Task 2.5).

### Schema pins (verified against migrations at story-authoring time)

- **`router_calls`** (006 + 022): `id, ts, task_type, prompt_version, model_chosen, model_chosen_reason, tokens_in, tokens_out, cached_tokens_in, cost_usd_estimated, latency_ms, outcome, caller_verb, caller_origin, email_id, sensitivity_grant_id, sensitivity_grant_minted_at` (+ 022's tool-call columns). Column-name gotcha (9.5.2 sibling finding): it is `task_type`/`model_chosen`, NOT `task`/`model_used`. `outcome` ∈ ok / retry_recovered / escalated / failed. `model_chosen_reason` closed set enforced app-side: `policy` / `override` / `degraded` / `response_cache_hit` / `force_override` / `escalated_from_<X>`. Sole writer: `observability/audit.py record_router_call()` (Rule C).
- **`emails` derived fields** (001_init + 011): `sensitivity` (normal/sensitive/confidential), `class_coarse`, `class_fine`, each with `*_prompt_v`, `*_conf`, `*_model`, `*_at` companions. `class_fine` populated only when `class_coarse='human'` (Story 3-5 conditional). Indexes exist on sensitivity/class_coarse/class_fine/sensitivity_at.
- **Taxonomies** (prompt modules, closed sets): sensitivity → `normal|sensitive|confidential` (prompts/sensitivity_class/v3.py current); coarse → `transactional|newsletter|human|notification|spam_like|unknown` (prompts/coarse_class/v1.py); fine → `personal|professional|family|cold_outreach|automated|unknown` (prompts/fine_class/v1.py).

### Policy expectation table (policy-v1-2026-07-04, verified)

qwen2.5:3b-instruct-q4_K_M is policy model for: `coarse_class` (v1), `sensitivity_class` (v3 — v1/v2 rows in history are legitimate older prompt_versions, not drift), `fine_class` (v1), `sender_reputation_summary`, `thread_continuity`, `intent_parsing_chat` (escalate:true → `escalated_from_qwen…` haiku rows legitimate), `reference_resolution` (escalate:true, same), `daily_digest_intro`. Haiku-policy tasks: `summary_short`, `importance_scoring`, `action_extraction`, `hermes_aux`. Opus-policy: `draft_reply`, `tone_style_mirror`, `multi_turn_refinement`, `anchor_calibrated_eval`. `embedding` never hits `ask_router`/router_calls (dispatch_embedding helper).

### Audit-interpretation history (context for expected artifacts in the data — evidence, not surprises)

- Story 6-18 F24: sensitivity_class v1 SYSTEM blocked 712+ ingest rows on SCHEMA_VALIDATION_FAILED (fixed by v2, 2026-06-05). Expect `failed` outcomes / v1-era gaps in old rows.
- Story 6-21 F27: v2 over-anchored confidence 0.95-normal on borderline emails; v3 (2026-06-06) added borderline anchors. Confidence distributions differ by prompt_version era — segment by `*_prompt_v` when reading `*_conf`.
- Story 9.5.3 F-FENCE-STRIP (fixed 2026-07-03): 3-day silent **Anthropic** ingest failure — affected haiku-task rows, not qwen rows, but shows up in outcome history.
- 10-1 F5/F6: the 10-1/10-2 walk subject email had local soft-delete churn — a handful of rows may carry `removed_reason` artifacts; exclude removed rows from the quality sample (`removed_reason IS NULL`).

### Scoring methodology (AC-2's calibration-posture inheritance — write this into evidence §2)

The post-9.5.4 posture (epic-9-5-retro-2026-07-05.md, Adam-signed Path B): the benchmark evaluator pipeline is **single-evaluator-trusted (opus-only) for v1**; cross-evaluator Krippendorff α=0.3490 FAILED-CALIBRATION is the honest v1 baseline; α≥0.6 is a v2 gate. Inheritance for this audit:

1. This audit does NOT invoke the benchmark evaluator pipeline (`anchor_calibrated_eval`) — that would cost real Anthropic spend (epic allocates $0 to 10-3) and would inherit the failed-calibration caveat anyway.
2. Evaluator = the in-session dev model (claude-fable-5), scoring classification agreement by direct reading — a SINGLE-EVALUATOR judgment, consistent with (not stronger than) the v1 posture. No inter-rater calibration exists for it; that limit is stated in evidence, mirroring the retro's honesty pattern.
3. Mitigations recorded per-item: closed-taxonomy tasks (not open-ended quality rubrics — categorical agreement is materially more objective than the 1-5 subjective axes that failed α); BORDERLINE verdicts get their own bucket rather than forced AGREE/DISAGREE; every DISAGREE carries a quotable rationale so Adam can overrule item-by-item at Phase 3.5.
4. Framing: spot-score verdicts are DEFECT-FILING EVIDENCE (N.5 filings for 10.5-era triage), not a calibrated quality metric; no policy/routing decision may cite them as a benchmark substitute (that is Epic 9 machinery's job).

### Testing requirements

No new tests — walk/audit story. Suite baseline at story-authoring time: **1708 passed + 2 skipped + 3 deselected**; must remain green at close (trivially — only evidence/tracking files change). Run the 4 gates for the evidence footer per convention. Any code change voids this section and escalates CR per §5.12.

### Project Structure Notes

Files this story may touch — and ONLY these:
- `_bmad-output/implementation-artifacts/10-3-walk-evidence.md` (new)
- `_bmad-output/implementation-artifacts/epic-10-run-flags.md` (append)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status flips)
- this story file (checkboxes, Dev Agent Record)

ZERO changes under `mailbot_api/`, `scripts/`, `router/`, `hermes-config/`, `docker/`, `tests/`, `README.md`. If the audit contradicts a README claim, that is a FILED finding routed to 10-7's evidence-backing close-out, not a same-story edit (10-3's ACs carry no doc-drift clause).

### References

- [Source: _bmad-output/planning-artifacts/epics.md § "Epic 10 Detail" + § "Story 10.3"] — story ACs (verbatim), N.5 scope fence, HARD sequencing constraint
- [Source: router/policy.yaml (policy-v1-2026-07-04)] — policy expectation table
- [Source: mailbot_api/db/migrations/006_router_calls.sql, 022_router_calls_tool_calls.sql, 001_init.sql:53-71, 011_derived_fields.sql] — schema pins
- [Source: mailbot_api/prompts/sensitivity_class/v3.py, coarse_class/v1.py, fine_class/v1.py] — closed taxonomies
- [Source: _bmad-output/implementation-artifacts/10-1-live-folder-move-walk-sacrificial-outlook-folder.md + 10-1-walk-evidence.md + epic-10-run-flags.md] — walk-evidence conventions, live-stack facts, docker-exec DB pattern
- [Source: _bmad-output/implementation-artifacts/epic-9-5-retro-2026-07-05.md] — post-9.5.4 calibration posture (single-evaluator-trusted, α≥0.6 v2 gate)
- [Source: memory feedback_anthropic_spend_source_of_truth.md ($0 discipline), project_epic_6_scope_cleave.md (N.5), feedback_l1_l2_l3_done_layers.md] — durable rules binding this audit

## Dev Agent Record

### Agent Model Used

claude-fable-5 (Claude Fable 5) — inline create-story + audit execution + spot-scoring, single `/autonomous-story-run 10-3` session 2026-07-06. Adam signs per-AC verdicts at the Phase 3.5 manual-verification gate.

### Debug Log References

- `10-3-walk-evidence.md` (all queries verbatim, full result tables, per-item score table, findings)
- `epic-10-run-flags.md` § "Story 10-3 Run 1" (run record, CR determination, Epic 10.5 triage inputs)

### Completion Notes List

- **AC-1:** usage distribution captured from the live DB (13,600 router_calls, read-only `mode=ro` throughout). Qwen = 9,651 calls = **71.0% of all volume**, 100% of the ingest classification trio — the charter's "free tier does most of the volume" claim is CONFIRMED. Conformance vs policy-v1-2026-07-04: **zero silent routing drift**; every off-policy pair explained by the closed `model_chosen_reason` set.
- **AC-2:** 29 labels spot-scored (26 distinct emails), stratified tail-biased draw with methodology + post-9.5.4 calibration-posture inheritance documented BEFORE scoring (single-evaluator claude-fable-5, categorical agreement vs the prompts' own rubrics, benchmark evaluator pipeline deliberately NOT used — $0 + failed-calibration caveat). 10 AGREE / 5 BORDERLINE / 14 DISAGREE (explicitly NOT a population accuracy estimate — defect-hunting sample). Patterns P1–P6 extracted with volume backing.
- **AC-3:** findings **F-10-3-1..6 FILED per N.5, zero fixed, zero code touched**. Headline: degraded mode stuck active since 2026-07-03T14:41Z on a pre-A2 inflated estimator counter (budget-guard $30 monthly cap, budget.py:37; DB-cumulative $35.37 at entry; $70.24 estimated-July vs ~$26 Console-real — honest counter would sit UNDER the cap; cap figure corrected $35→$30 at delegated verification, see evidence amendment A1) — all Anthropic ingest tasks qwen-served since 07-05, and qwen tool-call turns fail 18/18. Plus: coarse/fine 0-of-3,042 first-attempt-ok retry tax; human-over-trigger → dead `automated` valve cascade.
- **AC-4:** CR cadence — zero of the 6 criteria fire (docs/evidence/tracking artifacts only); **CR skipped per cadence binding**.
- Gates at close: ruff clean on tracked tree (2 pre-existing T201 in untracked `scratch/`, same residual as 10-1/10-2), mypy --strict clean (129 files), boundaries exit 0, pytest **1708 passed + 2 skipped + 3 deselected** — byte-identical to baseline (docs-only confirmed).

### File List

None — documentation/audit story, no source files modified. Artifacts:

- `_bmad-output/implementation-artifacts/10-3-qwen-batch-lane-usage-and-quality-audit.md` (this file)
- `_bmad-output/implementation-artifacts/10-3-walk-evidence.md` (new)
- `_bmad-output/implementation-artifacts/epic-10-run-flags.md` (§ Story 10-3 Run 1 appended)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status flips)

### Change Log

- 2026-07-06 — Qwen batch-lane usage + quality audit executed read-only against the live DB; 6 findings filed per N.5; zero code changes.
