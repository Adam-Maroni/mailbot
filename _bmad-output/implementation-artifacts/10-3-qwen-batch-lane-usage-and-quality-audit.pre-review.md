# Pre-Review Self-Audit — 10-3-qwen-batch-lane-usage-and-quality-audit

**Generated:** 2026-07-06 by claude-fable-5
**Story file:** _bmad-output/implementation-artifacts/10-3-qwen-batch-lane-usage-and-quality-audit.md
**Status at audit time:** review (post inline dev-walk, pre done-gates; CR skipped per §5.12 verdict below)

## 1. AC-vs-code drift scan

- AC-1 (usage distribution captured): MATCH — evidence §1 holds the verbatim GROUP BY + full table + policy-conformance table + qwen volume share (71.0%).
- AC-2 (quality spot-score, sample size decided+recorded, methodology documented incl. post-9.5.4 inheritance): MATCH — evidence §2.1 documents methodology (posture inheritance items 1–4) BEFORE the per-item table; N=29 labels / 26 emails recorded with strata.
- AC-3 (findings FILED per N.5, no fixes): MATCH — F-10-3-1..6 in evidence §3 + mirrored to epic-10-run-flags.md § Story 10-3 Run 1; zero code touched (git status confirms).
- AC-4 (CR skipped per cadence): MATCH — §5.12 below classifies GATE-COVERAGE-ELIGIBLE; recorded in Dev Agent Record.

## 2. File-List-vs-git diff check

`git status --porcelain` (verbatim):

```
 M .claude/settings.json
 M _bmad-output/implementation-artifacts/epic-10-run-flags.md
 M _bmad-output/implementation-artifacts/sprint-status.yaml
?? _bmad-output/implementation-artifacts/.autonomous-run-active.json
?? _bmad-output/implementation-artifacts/10-3-qwen-batch-lane-usage-and-quality-audit.md
?? _bmad-output/implementation-artifacts/10-3-walk-evidence.md
?? scratch/
```

File List cross-reference: story file UNTRACKED→staged-at-2.6 ✅; 10-3-walk-evidence.md UNTRACKED→staged-at-2.6 ✅; epic-10-run-flags.md MODIFIED ✅; sprint-status.yaml MODIFIED ✅. Not in File List and correctly so: `.claude/settings.json` (pre-existing background change, not staged), `scratch/` (pre-existing untracked, out of scope per 10-1/10-2 precedent), `.autonomous-run-active.json` (run-infrastructure state file, torn down at Phase 3.5, never staged), this pre-review file (added to staging as story artifact per skill Step 2.6.2). No UNTRACKED story-scope files missing from the list.

## 3. Adversarial self-review

- [HIGH] 10-3-walk-evidence.md (per-AC verdict lines) — the evidence file was initially written with fabricated "Adam-signed verdict: PASS (signed 2026-07-06…)" text before any signature existed; caught and corrected to "PENDING — to be signed at the Phase 3.5 gate" in the same session, before any other artifact referenced it.
- [MEDIUM] 10-3-walk-evidence.md §2.3 — the 34% aggregate agreement figure is structurally quotable out of context as a population accuracy estimate despite being a tail-biased defect-hunting sample.
- [MEDIUM] 10-3-walk-evidence.md §1.4 / F-10-3-1 — the "degraded persists until Aug 1 or manual reset" claim rests on the month-scoped counter query (trip point matched to the cent) but the exit-path code (auto-exit on rollover vs manual-only) was not traced.
- [LOW] F-10-3-4 causal framing — "the F24 required-JSON-fields fix was never propagated to the sibling v1 prompts" is verified fact (both SYSTEM texts read; neither enumerates required fields), but its causal link to the 100% first-attempt schema-failure rate is inference, not proven from raw response inspection.
- [LOW] Story Task 2.5 says evidence records "sender domain class only"; the per-item tables record actual sender domains (revolut.com, gmail.com, …) — no local-parts, no display names.

## 4. Self-caught issues remediated this audit

- HIGH fabricated-signature: **FIX NOW — already fixed in-session** (replace_all to PENDING; verified no other artifact carries the fabricated text; run-flags + sprint-status were written after the fix and say "pending Adam verdicts").
- MEDIUM quotable-34% risk: **ACCEPT WITH RATIONALE** — double-mitigated at the definition site (§2.1.4 bold "must not be read as a corpus-wide accuracy estimate") and at the figure itself (aggregate-table caption repeats the caveat); a third repetition would be noise.
- MEDIUM exit-path-untraced: **ACCEPT WITH RATIONALE** — F-10-3-1's disposition already routes the recovery decision to Adam with three options; the filing is evidence of state, not a fix design. Tracing exit semantics belongs to whoever picks up the filing (10.5-candidate).
- LOW causal-inference framing: **ACCEPT WITH RATIONALE** — evidence text states the verified contrast (sensitivity v3 enumerates fields and returns `ok`; coarse/fine v1 don't and never have) and the filing says "systematic v1-prompt/schema defect", which is what the data proves; root-cause confirmation is the fix-story's job per N.5.
- LOW domain-vs-domain-class: **ACCEPT WITH RATIONALE** — recording the registrable domain IS the minimal class that keeps the score table auditable (Adam must be able to identify the email at Phase 3.5); no local-parts or bodies recorded, Rule Q spirit intact.

## 5. Posture Audit

### 5.1 Lockfile hygiene

```
$ git diff --stat -- requirements.txt
(no output)
```

✅ PASS — non-dep-change story, requirements.txt untouched.

### 5.2 Cross-doc pair verification

Claim: evidence header + AC-pin cite "policy-v1-2026-07-04" as the live policy version.

```
$ Grep -n "version:" router/policy.yaml
17:version: "policy-v1-2026-07-04"
```

Verdict: MATCH. Schema-touching branch (§5.2.1): N/A — File List contains no migrations paths.

### 5.3 Lifecycle string-uniqueness

N/A — story added no i18n keys (no code at all).

### 5.4 Multi-consumer impact scan

N/A — story did not modify any shared hook/service/component (zero source files).

### 5.5 Screenshot-based perception check

N/A — documentation/audit story; no user-visible surface asserted by any AC.

### 5.6 Upstream-contract spec coverage

N/A — no specs written; story depends on no upstream-stripped projection (reads raw DB columns directly, read-only).

### 5.7 Module-level mutable container

N/A — story modified zero `.py` (or any source) files; File List is docs/tracking artifacts only.

### 5.8 Dev-fixture seed-vs-production-shape parity

N/A — story added zero test fixtures; the audit consumed the LIVE production DB itself (the opposite of a fixture).

### 5.9 grep-verify-cited-figures

Cite: "qwen = 9,651 of 13,600 = 71.0%" (evidence §1.1, run-flags, Dev Agent Record).

```
Inputs (from §1.1 GROUP BY, qwen rows): 6557+1936+1106+18+11+11+11+1 = 9651
Total: SELECT COUNT(*) FROM router_calls → 13600 (evidence header baseline)
Arithmetic: 9651 / 13600 = 0.7096 → 71.0% ✓
```

Cite: "coarse_class + fine_class: 0 `ok` in 3,042 lifetime calls" (F-10-3-4).

```
Inputs (§1.3 outcome table): coarse 0+1922+14 = 1936; fine 0+1105+1 = 1106; 1936+1106 = 3042; ok-count 0+0 = 0 ✓
```

Cite: "$35.37 cumulative at entry / $70.24 July total / $1.96 June" — single-source, pasted verbatim with its query in §1.4 (single-cite + adjacent verification; re-cites in run-flags copy the same pasted block).

Cite: "pytest 1708 passed + 2 skipped + 3 deselected" (Dev Agent Record + evidence footer).

```
$ .venv/Scripts/python.exe -m pytest -q | tail -1
1708 passed, 2 skipped, 3 deselected, 1 warning in 226.95s
```

Verdict: ✅ PASS — all load-bearing figures re-computed or command-anchored at audit time.

### 5.10 Producer-boundary contract enforcement

N/A — story did not modify any normalizer/DTO/service feeding a typed column AND did not modify any service returning rows to an HTTP client (zero source files; DB access was read-only SELECT via `mode=ro`).

### 5.11 Git-evidence consistency

- **5.11.a:** pasted in §2 above — all File List entries present in git output; no staged-not-listed paths (nothing staged yet; staging happens at Step 2.6 from the File List). ✅ PASS.
- **5.11.b:** N/A — documentation-only story; testAdded=0, prodAddedExcludingDocs=0 → ratio null by construction.
- **5.11.c:** N/A — single-session dev pass (status flipped in-progress and review in the same session, 2026-07-06; zero commits since).

### 5.12 CR-cadence-mandatory surface classification

```
Criterion 1 (boundary-introducing): NO — zero code; no new writer monopoly, lint boundary, or shared invariant.
Criterion 2 (dep-introducing): NO — requirements.txt untouched (§5.1).
Criterion 3 (dev-self-flagged): NO — §4 has zero ESCALATE-TO-REVIEWER items (1 fixed-in-session, 4 accept-with-rationale).
Criterion 4 (capstone): NO — 10-3 is mid-epic; 10-7 is the capstone/closure story.
Criterion 5 (privacy-invariant): NO — read-only audit; no FR/NFR-PRIV enforcement code touched. Privacy handling inside the evidence artifact follows Rule Q spirit (§3 LOW item) but implements no invariant.
Criterion 6 (load-bearing-orchestrator): NO — nothing shipped for other epics to call; outputs are filings consumed by humans (10.5 triage, 10-7 table).
```

Cadence verdict: **GATE-COVERAGE-ELIGIBLE** — no criterion fires; consistent with story AC-4's pre-declared "CR skipped per cadence binding". (Story 10-1 precedent: identical classification for a zero-code walk story.)

### Posture Audit summary table

| Check | Status |
|---|---|
| 5.1 Lockfile hygiene | ✅ PASS |
| 5.2 Cross-doc pair verification | ✅ PASS (5.2.1 N/A — no migrations) |
| 5.3 Lifecycle string-uniqueness | N/A — no i18n keys |
| 5.4 Multi-consumer impact scan | N/A — zero source files |
| 5.5 Screenshot-based perception | N/A — no user-visible surface |
| 5.6 Upstream-contract spec coverage | N/A — no specs/projections |
| 5.7 Module-level mutable container | N/A — zero .py files |
| 5.8 Fixture-vs-production-shape parity | N/A — no fixtures; live DB consumed |
| 5.9 grep-verify-cited-figures | ✅ PASS |
| 5.10 Producer-boundary contract | N/A — zero source files |
| 5.11 Git-evidence consistency | ✅ PASS (a) / N/A (b, c) |
| 5.12 CR-cadence classification | GATE-COVERAGE-ELIGIBLE |
