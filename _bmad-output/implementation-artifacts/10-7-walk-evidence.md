# Story 10-7 Walk Evidence — README evidence-backing close-out

**Session:** 2026-07-06, `/autonomous-story-run 10-7` (docs-closure story, no run-mode binding, $0 spend, zero live-stack interaction — pure Read/Grep/Edit/Write sweep over the repo).
**Orchestrator/dev model:** claude-fable-5. **Baseline commit:** `56cb43d` (working tree also carried pre-existing `.claude/settings.json` modification + untracked `scratch/` — neither touched).
**Signature line:** Phase 3.5 verification DELEGATED to orchestrator by Adam ("Check manual verification yourself", 10-3/10-4/10-5 precedent). Delegated pass executed 2026-07-06 with fresh commands (see story-run-flags.md § Story 10-7 Manual Verification): CP-1 tag sweep re-verified (45 grep lines, 3 back-fills verbatim-present, 5 illustrative markers); CP-2 limitations re-verified (13 bullets, 4 new headings + finding IDs present, nothing removed); CP-3 verdict-table counts re-derived programmatically (S1 29 rows 18P/11F, S1b 4 EXCLUDED, S2 18 rows 13P/5F — exact match to the three evidence tally lines re-read fresh) + 5 README line refs spot-verified (:147/:184/:213/:295/:310 all land as cited, :380 unshifted); CP-4 staged diff = 8 files, zero source paths. **Delegated verdict: PASS — all 4 AC verdicts (AC-1/2/3/4 PASS) signed via Adam's delegation directive.**

---

## 1. AC-1 — Verified-tag sweep + back-fill (Task 0 + Task 1)

### 1.1 Anchor inventory method

Walked anchors enumerated from the six walk-evidence files' case/verdict tables (10-4 §"Per-case verdict table", 10-5 §4, 10-6 §5, 10-1/10-2 AC-verdict tables + doc-drift sections) — not from intuition — then each anchor's README site checked for (real captured output + `<!-- verified 10-x, run_id ... -->` tag).

### 1.2 Sweep result

| Metric | Count |
| --- | --- |
| Walked README anchors checked (Sections 1+2 of the verdict table) | 29 example rows + 18 error rows |
| Already evidence-real + tagged (10-1..10-6 same-story passes) | 41 tag sites pre-existing (43 grep-matching lines incl. 2 prose mentions at :19/:200) |
| **Back-filled by this sweep** | **3 tags** (below) |
| Walked examples still illustrative after sweep | **0** |
| Unwalked examples (honestly marked, never retro-tagged) | 4 (undo, delete, `cost` row, status sample board) |
| Verified tags in README at close | **44 tag sites** (45 grep-matching lines: `grep -c "verified 10-"` = 45, one being the :19 prose mention; :200 carries prose + tag on one line) |

### 1.3 Back-fills applied (all cite already-captured evidence; zero freshly-invented output)

1. **README:56 (thread-summary honest-broken note)** — carried the 10-4 C3/C3b FAIL content but no tag; back-filled `<!-- verified 10-4, run_id 10-4-c3+10-4-c3b/2026-07-06 (FAIL, documented honestly) -->`.
2. **README:194 (sensitive-escalation honest-broken note)** — carried the 10-5 W3 FAIL content but no tag; back-filled `<!-- verified 10-5, run_id 10-5-w3/2026-07-06 (FAIL, documented honestly) -->`.
3. **README:200 (slash-table header)** — the S1/S4 native-slash FAIL evidence (the systemic F-10-5-1 result) had no tag of its own; back-filled `<!-- verified 10-5, run_id 10-5-s1+10-5-s4/2026-07-06 -->`.

### 1.4 Honesty markers added to unwalked examples (never tagged as verified)

Per the AC-1 pin (unwalked examples are NOT retro-tagged), the two remaining illustrative example blocks were explicitly marked *illustrative* with reasons, mirroring the `cost`-row convention 10-5 established:

- **README:159 Tier-1 undo** — marked *illustrative chat transcript*; underlying revert machinery cited to the 10-2 walk.
- **README:166 Tier-3 delete** — marked *illustrative — deliberately never walked in Epic 10* (destructive, no revert path) + F-10-5-1/7 caveats on its `/confirm` choreography.

### 1.5 Discrepancies found during transcription

None that changed a verdict. Zero tagged-but-uncited-in-evidence sites; zero README tags contradicting their evidence file. (The 10-4 CP-3 count "7 tags" and 10-6 "10 PASS tags + 6 FAIL corrections" reconciled exactly against the pre-sweep grep inventory of 42.)

**AC-1 proposed verdict: PASS** — no walked example remains illustrative; 3 gaps back-filled from existing captured evidence; unwalked examples honestly marked, never fabricated.

---

## 2. AC-2 — Limitations section honesty pass (Task 2)

Cross-checked the Limitations section against the full findings + FAIL-row source set (10-1 F1-F6+B1, F-10-3-1..6, F-10-4-1..6, F-10-5-1..12, F-10-6-1..7 + the 11 example-FAIL and 5 error-FAIL rows). Pre-existing bullets (local-only, folder moves, revert, slash prefix, send flow, Tier-2 choreography, sensitive escalation, agent self-edit) already covered 10-1/10-2/10-5 honestly. **Gaps found: the walks' 10-3, 10-4 and 10-6 findings had no limitations presence.** Four bullets added:

1. **Read-family gaps** (F-10-4-1/3/4/5/6): unread-as-recent proxy, thread summaries broken via chat, enrichment layer never runs (0/727 senders, 0/1753 threads), no name search, digest intro never generated + scheduled-slot degraded-mode fragility.
2. **Budget estimator inflation + degraded-mode reality** (F-10-3-1/2): estimator ~$70 vs ~$27-28 Console truth; the inflated counter tripped the $30 cap and stuck degraded mode 07-03→07-06; degraded mode = "no tool answers from chat" (qwen 18/18 tool-call failures); Console is spend truth.
3. **Free-tier classification quality edges** (F-10-3-4/5/6): coarse/fine 0-for-3,042 first-attempt schema validation (doubled qwen calls); `human` over-trigger ~28% from automation senders; dead `automated` escape valve; sensitivity keyword-anchoring + one OTP under-classification.
4. **Operator recovery tooling gaps** (F-10-6-2/3/7 + 4/5): `mailbot rederive` crashes every invocation; `mailbot replay` inert for move-induced `target_deleted`; `mailbot logs` Windows encoding; two dead error codes dropped from the table.

Nothing removed — every pre-existing limitation bullet is still true per the walk record.

**AC-2 proposed verdict: PASS** — the section now names every user-visible broken/missing surface the walks established, each with its finding ID; no marketing posture.

---

## 3. AC-3 — Per-row verdict table published (Task 3)

Published as **`_bmad-output/implementation-artifacts/epic-10-verdict-table.md`** (epic evidence, staged with this story):

- **Section 1:** 29 walked README-example rows (10-1 move, 10-2 revert, 10-4's 11 cases, 10-5's 16 cases) — 18 PASS / 11 FAIL, every row citing its walk-evidence file § + run_id.
- **Section 1b:** 4 EXCLUDED-with-reason rows (undo chat form, Tier-3 delete, `cost` row, status sample board).
- **Section 2:** 18 error-table verdict rows (16 README rows; R15a/b/c) — 13 PASS / 5 FAIL / 0 EXCLUDED, induced-vs-simulated tags carried verbatim from 10-6 §5 (12 INDUCED / 5 SIMULATED / 1 n/a-unreachable).
- **Roll-up:** 31 PASS / 16 FAIL / 4 EXCLUDED across 51 rows; every FAIL FILED per N.5 (38 findings epic-wide), every FAIL anchor honest in the README.
- **10-3 scope note:** contributes no example rows by design (read-only DB audit, no README anchors); its findings feed the limitations bullets.
- **Charter-count honesty:** 16 rows / 18 verdicts framing per F-10-6-1 (charter said 17); reconciliation cited.

**Completeness self-check (Task 3.2, both directions):**

- README → table: all 45 verified-tag sites + 4 illustrative-marked sites map to a table row (or to the same walk case — multi-tag anchors like W1a/W1b share row 29). ✓
- Evidence → table: 10-4 verdict table 11/11 transcribed; 10-5 verdict table 16/16; 10-6 verdict table 18/18; 10-1/10-2 walk verdicts 2/2. Discrepancy list: empty. ✓
- Verdicts transcribed, none re-adjudicated. ✓

**AC-3 proposed verdict: PASS.**

---

## 4. AC-4 — CR cadence (Task 4)

Zero production code touched: this story's diff is `README.md` + `_bmad-output/implementation-artifacts/*` only (verdict table, this file, story/tracking files). Zero of the 6 CR criteria fire → **CR skipped per cadence binding; ships under §5.12 self-audit** (the verdict table's completeness review in §3 above IS the done-flip-gate review the AC names). Self-audit artifact: `10-7-readme-evidence-backing-close-out.pre-review.md`.

**AC-4 proposed verdict: PASS.**

---

## Footer

- **Spend:** $0 — zero Router calls, zero API calls, zero container interaction; repo-only sweep.
- **Gates at close:** recorded in the story Dev Agent Record (docs-only story; pytest expected byte-identical 1708+2+3).
- **Done-flip clause status after this story:** clause 2 (verdict table) DISCHARGED — `epic-10-verdict-table.md`; clause 3 (verified tags) DISCHARGED — 0 walked-but-illustrative sites remain; clause 4 (limitations honesty) DISCHARGED — 4 gap bullets added; clause 1 (10-1..10-7 done) completes when this story flips done on Adam-signed verdicts; clause 5 (defects FILED not absorbed) held by every story (38 findings, zero absorbed beyond 10-2's pre-declared scope). Epic-10 done-flip itself is OUT of this story's scope (retro owns it).
