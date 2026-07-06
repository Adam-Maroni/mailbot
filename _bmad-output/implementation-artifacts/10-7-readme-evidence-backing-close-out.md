---
baseline_commit: 56cb43d30b9c3c455089467fa183187c2dbc578d
---

# Story 10.7: README evidence-backing close-out — verified tags + limitations + per-row verdict table

Status: done

<!--
Docs-closure story, Epic 10 README-as-charter UAT. NOT an implementation story: it discharges
epic-10 done-flip clauses 2, 3, and 4 by (a) sweeping the README for any walked example still
illustrative, (b) updating the limitations section honestly against walk findings, and
(c) publishing the complete per-row verdict table as epic evidence. Zero production code.
Ships under §5.12 self-audit cadence per AC-4 (zero mandatory CR criteria fire; the verdict
table's completeness review IS part of the epic done-flip gate itself, not a CR).

Scope fence (N.5 policy): this story fixes NOTHING. Findings from 10-1..10-6 stay FILED.
The only README edits allowed are evidence-backing edits: back-filling a missing verified
tag/real output for an already-walked example, and honest limitations-section updates. Any
behavior-claim change beyond that must be traceable to a named walk-evidence citation.

Note on "17 error rows" in the AC/charter text: F-10-6-1 (INFO) reconciled this honestly —
the README table has 16 data rows; R15 carries 3 codes walked as R15a/b/c → 18 verdict rows.
The verdict table uses the honest 16-rows/18-verdicts framing and cites F-10-6-1.
-->

## Story

As Adam,
I want every walked example's illustrative output in the README replaced with real captured output tagged `<!-- verified 10-x, run_id ... -->`, the limitations section updated honestly, and the complete per-row verdict table published as epic evidence,
So that Epic 10 closes at "every user-facing claim has a named, evidence-backed verdict" rather than "we walked around a bit."

## Acceptance Criteria

**AC-1 — Verified-tag sweep + back-fill**
**Given** Stories 10.1–10.6 have each updated their README examples same-story same-commit per doc-drift rule (a)
**When** the close-out sweep fires
**Then** the sweep verifies NO walked example remains illustrative — every one carries real captured output + its `<!-- verified 10-x, run_id ... -->` tag — and back-fills any gap the per-story passes missed

**AC-2 — Honest limitations section**
**Given** the walks surfaced what the product does NOT do well
**When** the limitations section is updated
**Then** it honestly reflects walk findings (including any FAIL/EXCLUDED rows and FILED defects), not marketing posture

**AC-3 — Complete per-row verdict table published as epic evidence**
**Given** done-flip clause 2
**When** the verdict table is published as epic evidence
**Then** every README example AND all error-table rows (16 rows / 18 verdict rows per F-10-6-1 reconciliation) have a named PASS / FAIL / EXCLUDED-with-reason verdict, with citations into the 10-x walk-evidence files (and induced-vs-simulated honesty tags carried through from 10.6)

**AC-4 — CR cadence**
**Given** this is a docs-closure story
**When** CR cadence is evaluated per the 6 criteria
**Then** zero mandatory criteria fire → ship under §5.12 self-audit cadence (the verdict table is reviewed for completeness against the README as part of the done-flip gate itself)

### AC interpretation pins (code-reality; read before executing)

- **"Walked example" scope (AC-1):** every README example/claim that a 10-1..10-6 walk actually exercised. The sweep enumerates README anchors from the six walk-evidence files' case tables — not from intuition — then checks each anchor's README site for (real output + verified tag). Examples the walks did NOT exercise are NOT retro-tagged; if any load-bearing example remains illustrative AND unwalked, it is named honestly in the verdict table as EXCLUDED-with-reason (never silently tagged).
- **Back-fill contract (AC-1):** a back-fill replaces illustrative output with output actually captured in a 10-x walk-evidence file, citing its run_id — never freshly-invented prose. If evidence lacks a usable capture, the row goes EXCLUDED-with-reason instead of fabricating.
- **Sanitization rule carried from WALK-10-4-F1/10-5:** any back-filled README output masks real client emails/names per the established convention (real address masked, note in the tag).
- **Limitations section (AC-2) source set:** FAIL verdict rows from 10-4 (5) / 10-5 (6) / 10-6 (5); FILED findings 10-1 F1–F6+B1, F-10-3-1..6, F-10-4-1..6, F-10-5-1..12, F-10-6-1..7; already-documented caveats stay unless walk evidence contradicts them. Honesty means: the section names what's broken/missing today with finding IDs, not hedged marketing.
- **Verdict table (AC-3) is a NEW epic-evidence artifact:** `_bmad-output/implementation-artifacts/epic-10-verdict-table.md`. Two sections: (1) README examples — one row per walked anchor (10-1 move, 10-2 revert, 10-4's 11 cases, 10-5's 16 cases, 10-3's audit scope note), (2) error table — 18 verdict rows R1..R16 incl. R15a/b/c with induced-vs-simulated tags carried verbatim from 10-6. Columns: anchor/case, README line ref, verdict (PASS/FAIL/EXCLUDED-with-reason), evidence citation (file § + run_id), honesty tag where applicable.
- **Verdicts are TRANSCRIBED, not re-adjudicated:** this story carries per-case verdicts from the signed 10-1..10-6 evidence; it does not re-run walks or flip verdicts. A discrepancy found during transcription (e.g., README tag contradicts evidence) is a doc-drift correction (AC-1) or a new INFO finding — never a silent verdict edit.
- **Done-flip gate NOT flipped here:** this story discharges clauses 2/3/4 and flips itself done; the epic-10 row flip + retrospective remain outside scope (retro owns the Epic 10.5 spawn decision).
- **Gates expectation:** docs+evidence only → ruff/mypy/boundaries/pytest byte-identical to baseline (1708+2+3 at 10-6 close).

## Tasks / Subtasks

- [x] **Task 0 — Anchor inventory (BLOCKING)** (AC: 1, 3) — inventory built from 10-1/10-2 AC tables + 10-4 §verdict-table + 10-5 §4 + 10-6 §5; README grep found 42 pre-existing tags; 3 back-fill candidates + 0 tag-vs-evidence discrepancies identified
  - [x] 0.1 Walked-anchor inventory: 29 example rows + 18 error rows (evidence §1.1)
  - [x] 0.2 Tag diff: 3 walked-but-untagged sites (README:56 thread note, :194 sensitive note, :200 slash header); zero tagged-but-uncited sites
- [x] **Task 1 — Verified-tag sweep + back-fill** (AC: 1) — 3 tags back-filled citing already-captured evidence (no invented output); undo + delete examples marked *illustrative* with reasons (cost-row convention); 0 walked examples remain illustrative; 44 tag sites at close (evidence §1)
  - [x] 1.1 Back-fills applied (evidence §1.3); zero discrepancies to reconcile
  - [x] 1.2 Sweep result recorded (evidence §1.2)
- [x] **Task 2 — Limitations section honesty pass** (AC: 2) — gap found: 10-3/10-4/10-6 findings had zero limitations presence; 4 bullets added (read-family gaps F-10-4-*; estimator inflation + degraded reality F-10-3-1/2; qwen quality edges F-10-3-4/5/6; operator tooling gaps F-10-6-2/3/7+4/5); nothing removed (evidence §2)
- [x] **Task 3 — Publish `epic-10-verdict-table.md`** (AC: 3) — published: 29 walked example rows (18P/11F) + 4 EXCLUDED-with-reason + 18 error rows (13P/5F, honesty tags verbatim from 10-6); roll-up 31/16/4 across 51 rows (evidence §3)
  - [x] 3.1 Both sections composed, every row cites walk-evidence file § + run_id
  - [x] 3.2 Completeness self-check both directions: discrepancy list EMPTY; verdicts transcribed, none re-adjudicated
- [x] **Task 4 — CR-cadence determination + §5.12 self-audit** (AC: 4) — zero of 6 criteria fire (README + `_bmad-output/` only); CR skipped per cadence; §5.12 self-audit = pre-review artifact + verdict-table completeness check (evidence §4)
- [x] **Task 5 — Evidence, run-flags, gates, sprint flip, stage (never commit)** (AC: 1, 2, 3, 4)
  - [x] 5.1 `10-7-walk-evidence.md` composed (per-AC proposed verdicts: 4× PASS)
  - [x] 5.2 Run-flags appended (epic-10-run-flags.md § Story 10-7 Run 1; story-run-flags.md report)
  - [x] 5.3 Gates: ruff clean on tracked tree (6 pre-existing T201 in untracked `scratch/`, same residual class as 10-1..10-6); mypy --strict clean (129 files); boundaries exit 0; pytest **1708 passed + 2 skipped + 3 deselected in 217.66s** — byte-identical to baseline
  - [x] 5.4 sprint-status flipped `review`; explicit-path staging; `done` on Adam-signed verdicts; nothing committed

## Dev Notes

### Technical requirements

Pure docs + evidence story. No source tree changes. Tooling: Read/Grep/Edit/Write + `.venv/Scripts/python.exe -m pytest/ruff/mypy` for the byte-identical gate run. No Docker, no live stack, no spend ($0).

### Files this story may touch — and ONLY these

`README.md` (AC-1 back-fills + AC-2 limitations), `_bmad-output/implementation-artifacts/epic-10-verdict-table.md` (new), `10-7-walk-evidence.md` (new), `epic-10-run-flags.md` (append), `story-run-flags.md` (append), `sprint-status.yaml` (flips), this story file, `10-7-*.pre-review.md`. ZERO changes under `mailbot_api/`, `scripts/`, `router/`, `hermes-config/`, `docker/`, `tests/`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md § "Story 10.7" + § "Epic 10 Detail" (done-flip clauses 2/3/4, doc-drift rules, N.5 fence)]
- [Source: README.md — examples throughout; :287-310 error table; limitations section (~:362-387)]
- [Source: 10-1/10-2/10-3/10-4/10-5/10-6 walk-evidence files — verdict tables, run_ids, honesty tags, findings]
- [Source: _bmad-output/implementation-artifacts/epic-10-run-flags.md — consolidated findings registry]
- [Source: 10-6 story file — F-10-6-1 16-vs-17 reconciliation; sanitization convention from 10-4/10-5 (WALK-10-4-F1)]

## Dev Agent Record

### Agent Model Used

claude-fable-5 (Claude Fable 5) — inline create-story + inline dev walk (repo-only docs sweep), `/autonomous-story-run 10-7` session 2026-07-06. No live-stack interaction; Adam signs verdicts at Phase 3.5.

### Debug Log References

- `10-7-walk-evidence.md` (sweep result, back-fill list, limitations diff, verdict-table completeness check, per-AC proposed verdicts)
- `epic-10-verdict-table.md` (the AC-3 artifact)
- `epic-10-run-flags.md` § "Story 10-7 Run 1"

### Completion Notes List

- **AC-1 (verified-tag sweep + back-fill): PASS proposed** — 29 walked example anchors + 18 error rows checked against the six walk-evidence files; 41 tag sites pre-existing, 3 back-filled (README:56 thread-FAIL note, :194 sensitive-FAIL note, :200 slash-header S1/S4 evidence — all citing already-captured run_ids, zero invented output); 0 walked examples remain illustrative; the 4 unwalked anchors (undo, delete, `cost`, status board) are explicitly *illustrative*-marked, never retro-tagged. 44 tag sites at close (45 grep lines incl. the :19 prose mention).
- **AC-2 (limitations honesty): PASS proposed** — 4 gap bullets added covering the 10-3/10-4/10-6 findings that had no limitations presence (read-family gaps; estimator inflation + degraded-mode reality; qwen classification quality edges; operator recovery-tooling gaps), each naming its finding IDs; nothing still-true removed.
- **AC-3 (verdict table as epic evidence): PASS proposed** — `epic-10-verdict-table.md` published: Section 1 = 29 walked README-example rows (18 PASS / 11 FAIL), Section 1b = 4 EXCLUDED-with-reason, Section 2 = 18 error-table rows (13 PASS / 5 FAIL / 0 EXCLUDED) with induced-vs-simulated tags carried verbatim from 10-6 (12 INDUCED / 5 SIMULATED / 1 n/a); every row cites its walk-evidence file § + run_id; roll-up 31 PASS / 16 FAIL / 4 EXCLUDED across 51 rows; verdicts transcribed, none re-adjudicated; completeness check both directions clean.
- **AC-4 (CR cadence): PASS proposed** — zero production code touched (README + `_bmad-output/` artifacts only); zero of 6 CR criteria fire → CR skipped per cadence, ships under §5.12 self-audit.
- **Done-flip clauses discharged:** clause 2 (verdict table), clause 3 (no walked example illustrative), clause 4 (limitations honest). Clause 1 completes when this story flips done; clause 5 held epic-wide (38 findings FILED, zero absorbed beyond 10-2's pre-declared scope). Epic-10 done-flip + retro remain out of scope.
- **Spend: $0** — repo-only sweep, zero Router/API/container interaction.
- Gates at close: ruff clean on tracked tree (6 pre-existing T201 in untracked `scratch/`), mypy --strict clean (129 files), boundaries exit 0, pytest **1708 passed + 2 skipped + 3 deselected in 217.66s** — byte-identical to baseline (docs-only confirmed by the suite itself).

### File List

None — documentation/closure story, no source files modified. Artifacts:

- `README.md` (3 back-filled verified tags; 2 illustrative markers on undo/delete examples; 4 new limitations bullets)
- `_bmad-output/implementation-artifacts/epic-10-verdict-table.md` (new — the AC-3 epic-evidence artifact)
- `_bmad-output/implementation-artifacts/10-7-walk-evidence.md` (new)
- `_bmad-output/implementation-artifacts/10-7-readme-evidence-backing-close-out.md` (this file)
- `_bmad-output/implementation-artifacts/10-7-readme-evidence-backing-close-out.pre-review.md` (new)
- `_bmad-output/implementation-artifacts/epic-10-run-flags.md` (§ Story 10-7 Run 1 appended)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status flips)
- `_bmad-output/implementation-artifacts/story-run-flags.md` (run report)

### Change Log

- 2026-07-06 — Epic 10 close-out sweep: README fully evidence-backed (45 verified tags, 0 walked-but-illustrative sites, 3 back-fills, 2 honest illustrative markers), limitations section updated with 4 honesty bullets (10-3/10-4/10-6 findings), complete per-row verdict table published as `epic-10-verdict-table.md` (31 PASS / 16 FAIL / 4 EXCLUDED across 51 rows, honesty tags carried through). Done-flip clauses 2/3/4 discharged. $0, zero code.
