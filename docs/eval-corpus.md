# Eval corpus contract (`evals/email_corpus_v1.jsonl` + anchors + canary fixture)

This document is the authoritative reference for the Story 9-5 eval-corpus
contract. The corpus is the ground-truth set every Story 9-6 benchmark
runner dispatches against; the subjective-task anchors calibrate Story
9-7's scorer; the 5-item canary fixture is what Story 9-8's E2E
integration test loads in CI.

---

## 1. Why the corpus is privacy-sensitive

The corpus is **production-sampled** (from Adam's live inbox via the local
SQLite `emails` table) rather than hand-authored from scratch. Adam-decision
2026-06-26 (Epic 9 tranche retro § 3.3 + § 6 A4) accepted this tradeoff:

- **Pro:** authoring labor drops from ~3-5h (original Story 7.1 hand-author
  spec) to ~1-2h (sample + label-aid-review + paste). Real inboxes have
  representative examples we can't easily fabricate.
- **Con:** `evals/email_corpus_v1.jsonl` becomes a privacy-sensitive
  artifact. It joins `router/policy.user-overrides.yaml` and
  `router/sensitivity_patterns.yaml` as the privacy-sensitive-operator-
  state family: gitignored, VPS-only, bind-mounted read-only into the
  running container.
- **Coverage tradeoff:** the original "≥ 8 items per category" floor is
  **removed**. The sample is whatever Adam's inbox produced; Story 9.9's
  sample-size gate (`n ≥ 15 per cohort`) handles unbalanced categories
  naturally.

The hand-authored 5-item canary fixture (`evals/fixtures/canary_5.jsonl`)
is the CI-safe carve-out: PII-free by construction (not by anonymization),
gitted, and Story 9.8's E2E test loads it directly.

The AC-6.5 "labeling-session privacy invariant" (the agent-never-sees-
`raw_body` discipline during the AC-15 co-pilot session) is a sibling
contract — see § 11.

---

## 2. File layout

```
evals/
  __init__.py                                  # gitted, empty marker
  corpus_schema.py                             # gitted, Pydantic models + helpers
  anonymizer.py                                # gitted, regex PII pass
  email_corpus_v1.jsonl                        # gitignored, Adam-authored, bind-mounted RO
  email_corpus_v1.jsonl.example                # gitted, discoverable template
  fixtures/
    canary_5.jsonl                             # gitted, hand-authored CI fixture
  scoring_rubrics/                             # gitted, 8 markdown rubrics
    coarse_class.md
    fine_class.md
    sensitivity_class.md
    summary_short.md
    importance_scoring.md
    action_extraction.md
    reference_resolution.md
    draft_reply.md
  anchors/
    VERSION                                    # gitted, contains "v1" (no trailing newline)
    draft_reply_anchors.jsonl                  # gitignored, Adam-authored, bind-mounted RO
    draft_reply_anchors.jsonl.example          # gitted template
    summary_anchors.jsonl                      # gitignored
    summary_anchors.jsonl.example              # gitted template
  _labeling/                                   # gitignored, AC-15 worksheet scratch
```

### JSONL-with-comments convention

The `.example` files lead with `//`-prefixed comment lines so operators
see context at first directory listing. The `load_corpus` and anchor-
loading code skip `//`-prefixed lines so the comments don't break parsing.
DO NOT strip the comments accidentally; they're the discoverability surface.

The convention applies to all `.jsonl` files loaded through
`evals.corpus_schema.load_corpus`, including the production corpus
(which does not use it in practice, but the parser is uniform).

---

## 3. Schema reference

The Pydantic schema is the source of truth — see [`evals/corpus_schema.py`](../evals/corpus_schema.py).

A realistic `CorpusItem` line (formatted for readability; the file stores
each item as one JSON line, no internal indentation):

```json
{
  "id": "corpus-v1-042",
  "category": "human_professional",
  "raw_subject": "Re: Q3 budget review — quick question",
  "raw_body": "Hi <email-001@example.com>, can you confirm by <phone-001> if ...",
  "labels": {
    "sensitivity": "normal",
    "class_coarse": "human_professional",
    "class_fine": "work_collaboration",
    "summary_short_anchor": "Colleague asking for Q3 budget confirmation by Friday.",
    "importance_score": 4,
    "actions": [
      {
        "action_type": "reply",
        "summary": "Confirm Q3 spend numbers by Friday",
        "deadline": "2026-07-04",
        "recipient": null
      }
    ],
    "reference_resolution_slice": false,
    "reference_resolution_turns": null,
    "expected_resolved_email_ids": null,
    "adversarial": false
  },
  "source_note": "sampled from emails.id=4711, graph_id=AAA-..., received_at=2026-06-15T..., seed=v1-pass-1"
}
```

`AnchorItem` for the subjective-task anchors lives in the same module —
20 per task, with task-specific axes (see § 8).

### Cross-field invariants enforced by Pydantic

- `reference_resolution_slice=True` requires both
  `reference_resolution_turns` AND `expected_resolved_email_ids` to be
  non-None and non-empty.
- `reference_resolution_slice=False` requires both to be None.
- `importance_score`, if present, is 1-5.
- Every `AnchorItem` axis-score AND `adam_overall_score` is 1-5.
- `AnchorItem.adam_score_axes` keys match the task: `draft_reply` →
  `{faithfulness, tone_match, actionability}`; `summary_short` →
  `{faithfulness, concision, actionability}`.

---

## 4. Authoring workflow

The Adam-facing surface is `scripts/build_corpus.py` — a 5-subcommand
CLI. The workflow Adam runs (host-side) during the AC-15 live labeling
co-pilot session is:

### Round 1 — Corpus (~100 items + 5-10 adversarial)

```bash
# 1. Sample 120 rows from production
python scripts/build_corpus.py sample --from-db --count 120 \
    --seed v1-pass-1 \
    --out evals/_labeling/corpus-draft-pass1.jsonl

# 2. Convert draft → spreadsheet-editable CSV worksheet
python scripts/build_corpus.py to-csv --mode corpus \
    --draft evals/_labeling/corpus-draft-pass1.jsonl \
    --out evals/_labeling/corpus-worksheet.csv

# 3. *** Adam edits evals/_labeling/corpus-worksheet.csv in his spreadsheet editor ***
#     - pastes raw_body into the raw_body column
#     - ticks _reviewed_<label>=TRUE for accepted prefills (edits + ticks TRUE to override)
#     - fills category, actions (pipe-separated JSON), source_note
#     - marks 5-10 rows adversarial=TRUE with the rationale in source_note

# 4. Ingest the worksheet
python scripts/build_corpus.py from-csv --mode corpus \
    --csv evals/_labeling/corpus-worksheet.csv

# 5. Iterate on the rejected.csv if needed; re-run from-csv until accepted == target
# 6. Validate the result
python scripts/build_corpus.py validate --strict
```

### Round 2 — Reference-resolution slice (20 items)

```bash
# Generate an Adam-readable index (no raw_body per AC-9 privacy invariant)
python scripts/build_corpus.py list-corpus \
    --columns id,raw_subject,from_display_name,received_at \
    --out evals/_labeling/corpus-index.csv

# *** Adam marks 20 ids in evals/_labeling/corpus-index.csv ***

python scripts/build_corpus.py to-csv --mode reference-slice \
    --corpus evals/email_corpus_v1.jsonl \
    --candidate-ids corpus-v1-001,corpus-v1-007,... \
    --out evals/_labeling/reference-slice-worksheet.csv

# *** Adam fabricates the 3-turn transcripts + expected_resolved_email_ids ***

python scripts/build_corpus.py from-csv --mode reference-slice \
    --csv evals/_labeling/reference-slice-worksheet.csv \
    --corpus evals/email_corpus_v1.jsonl
```

### Round 3 — Anchors (20 per task)

Same pattern: `to-csv --mode anchor --task draft_reply ...`, Adam scores
each of 20 candidates per axis + overall, `from-csv --mode anchor ...`.
Repeat for `--task summary_short`.

### `validate --strict` pre-commit pattern

Before any Story 9-6 benchmark run, run `validate --strict`. It loads
the corpus, runs the AC-6 anonymization regexes against `raw_subject`
and `raw_body`, checks the reference-slice count is exactly 20, the
adversarial count is in [5, 10], and the anchor files each contain
exactly 20 items.

In default (non-strict) mode, AC-6 regex matches are warnings (the
regexes have known false positives — sentence-internal digit runs that
look like phone numbers but aren't); `--strict` upgrades them to errors.

---

## 5. Anonymization contract

`evals/anonymizer.py` exposes `anonymize(raw_text, *, seed=None)`. The 7
regex patterns (applied in this order) replace PII shapes with stable
`<token-NNN>` placeholders:

1. **URLs with token query strings** (`https://x.com/get?api_key=...`)
2. **Email addresses** (`adam@example.com`)
3. **SSN-shape** (`NNN-NN-NNNN`)
4. **Credit-card-shape** (16-digit run with optional dash/space separators)
5. **Phone-shape** (`+CC NNN-NNN-NNNN` / `(NNN) NNN-NNNN` / `NNN-NNN-NNNN` / `NNN.NNN.NNNN`)
6. **Postal address-shape** (`<number> <street-name> <street-type>, <city>`)

### What the regexes don't catch (accepted false-positive risk)

- Sentence-internal digit runs that LOOK like phone numbers (`we shipped
  5551234567 units`) pass through unchanged. The regex requires
  separators or parens for phone numbers — Adam's review pass catches
  these in the worksheet stage.
- Names (`Adam Maroni`) — regex-detecting names without a heuristic
  is unreliable. Adam-review pass catches these too.
- Single-word company names that happen to be PII (rare but possible).

The regex pass is **fail-safe-by-design**: it errs on the side of
under-redaction so the worksheet shows Adam the original text where
possible, and Adam removes whatever the regex missed during the review
pass. The CI surface (canary fixture + `.example`) is PII-free by
construction, not by regex — see `test_no_pii_in_committed_corpus`.

---

## 6. Reference-resolution slice rules (AC-4)

Exactly 20 items in the corpus carry `labels.reference_resolution_slice
= True`. For each:

- `reference_resolution_turns` is a list of 3 dicts shaped
  `{"role": "user" | "agent", "content": str}`. Turn 0 is `user`, turn
  1 is `agent`, turn 2 is `user`. The last user turn is the one that
  triggers the reference resolution (e.g., "the one from Bob about the
  audit").
- `expected_resolved_email_ids` is the non-empty list of corpus ids the
  agent SHOULD resolve the reference to.

The 20 items are Adam-picked for resolution-difficulty coverage, not
category coverage; they may belong to any of the 8 categories.

---

## 7. Adversarial slice rules (AC-5)

Between 5 and 10 items carry `labels.adversarial = True`. These are
deliberately ambiguous, multi-signal-borderline, or edge-case
sensitivity classifications — exactly the failure mode the F27 incident
report (`f27_qwen_sensitivity_drift` in `epic-3-run-flags.md`) was
filed for. The `source_note` for each adversarial item documents WHY
the item is adversarial (which signals collide, what the ambiguity is,
what Adam decided on the ground-truth label and why).

Adversarial items MAY overlap with the reference-resolution slice.

Story 9.9's report renderer surfaces accuracy SEPARATELY for adversarial
vs. non-adversarial subsets so regressions on the adversarial slice are
visible against the baseline.

---

## 8. Anchor sets (AC-3)

Each subjective task (`draft_reply` and `summary_short`) has its own
anchor file in `evals/anchors/`. Each file contains **exactly 20 items**
(HARD contract — Story 9.7 secondary-evaluator path + Story 9.11 anchor
stability audit both assume n=20).

### Axes per task

- `draft_reply` → `faithfulness`, `tone_match`, `actionability` (each 1-5)
- `summary_short` → `faithfulness`, `concision`, `actionability` (each 1-5)

Plus `adam_overall_score` (1-5), `score_rationale` (free text), and
`corpus_item_id` (link to a `CorpusItem.id` if the anchor is derived
from a corpus row; `None` if Adam-authored synthetic). The 20 anchors
SHOULD span the 1-5 range with at least 2 at each level (calibration
needs variance); the script warns but does not refuse an unbalanced
set — Adam decides.

---

## 9. Re-anchoring procedure

When subjective rubrics change (e.g., the `summary_short` rubric grows
a new axis), the anchor scores become invalid against the new rubric.
The procedure to re-anchor:

1. Decide what changed in the rubric. Document in `evals/scoring_rubrics/<task>.md`.
2. Clear the affected anchor file: `evals/anchors/<task>_anchors.jsonl`.
3. Re-run Round 3 of the AC-15 workflow (`to-csv --mode anchor ...` →
   Adam scores 20 fresh anchors → `from-csv --mode anchor ...`).
4. Bump `evals/anchors/VERSION`: `v1` → `v2`. Single line, no quotes,
   no trailing newline.
5. Commit the VERSION bump with a message explaining the re-anchoring
   rationale: "anchors v1 → v2: summary_short rubric grew an actionability
   axis; re-anchoring needed because v1 anchors are uncalibrated
   against the new axis."

Story 9.6's `benchmark_runs.cohort_key` includes `anchors_version` —
re-anchoring creates a new cohort, so old runs aren't comparable to new
ones. This is the right behavior; comparing across rubric versions
would compare apples to oranges.

---

## 10. Cross-references

- **[Story 9.1](../_bmad-output/implementation-artifacts/9-1-contract-pin-policy-user-overrides-yaml-schema-and-shallow-leaf-merge-semantics.md)** — established the gitignore + bind-mount + `.example` sibling pattern this story replicates.
- **[Story 9.4](../_bmad-output/implementation-artifacts/9-4-model-persistent-override-and-model-inspect-write-to-policy-user-overrides-yaml.md)** — `write_user_overrides_atomic` is the atomic-write precedent for `write_corpus`.
- **Story 9.6 (benchmark runner)** — primary consumer of `load_corpus()` and `read_anchors_version()`. `--corpus` flag defaults to `evals/email_corpus_v1.jsonl`; `--corpus evals/fixtures/canary_5.jsonl` for CI.
- **Story 9.7 (scorer)** — primary consumer of `evals/scoring_rubrics/*.md` (subjective scorer prompts inline-include the rubric markdown) + `evals/anchors/*.jsonl` (calibration source).
- **Story 9.8 (E2E canary)** — primary consumer of `evals/fixtures/canary_5.jsonl`. The 5-item × 5-category coverage is DESIGNED for Story 9.8's `5 × 3 × 2 = 30 dispatches` shape.
- **Story 9.9 (report)** — sample-size gate `n ≥ 15 per cohort` handles the unbalanced-corpus tradeoff.
- **Story 9.11 (anchor stability audit)** — primary consumer of the 20 anchors per task. Audit dispatches a second evaluator; Krippendorff α gets computed; Adam reads the verdict.

---

## 11. Co-pilot session privacy contract (AC-6.5)

The AC-15 live labeling co-pilot session has the dev agent guiding Adam
through a CSV-driven workflow live in the conversation. Because
`raw_body` content is privacy-sensitive, the **agent's role boundary**
needs explicit definition. This contract is **normative** — future
co-pilot sessions (a Story 9-5 v2 corpus refresh, or any similar
Adam-in-the-loop labeling story) MUST follow it.

### What the agent MUST NOT do

- **Read `raw_body` content from the conversation.** Adam pastes
  `raw_body` into the CSV file in his spreadsheet editor — NEVER into
  the chat. If Adam accidentally pastes an email body into chat, the
  agent MUST refuse to process it, explicitly note the privacy
  violation, and redirect Adam to paste into the CSV.
- **Read `evals/email_corpus_v1.jsonl` directly.** The agent reads only
  the corpus-shape metadata via `list-corpus` output (`id`,
  `raw_subject`, `from_display_name`, `received_at`) — never `raw_body`.
- **Open or read `evals/_labeling/*.csv` worksheets directly.** Adam
  edits these; the agent only invokes `scripts/build_corpus.py from-csv
  ...` which reads the file via the script's anonymizer + validator
  pipeline. The agent reads back ONLY the script's structured output —
  `accepted N/M, rejected K/M`, per-rejected-row hint messages — and
  the hint messages are pointer-only (column-name + error-class +
  pointer to `rejected.csv`), never the cell's value.
- **Propose label values.** No `class_coarse` / `class_fine` /
  `sensitivity` / `summary_short_anchor` / `importance_score` /
  `actions` / `category` proposals. The agent guides PROCESS only
  ("next: 18 reference-slice items to go"; "the `_reviewed_*` columns
  block ingest if FALSE — make sure to tick them"). It does NOT guide
  LABEL CONTENT.
- **Read captured `model_output` strings** from any real-spend dispatch
  capture (the AC-15 step 15 mode-(a) path). Those land in
  `evals/_labeling/anchor-outputs-<task>-<timestamp>.jsonl` which is
  gitignored AND off-limits to the agent. The script's `to-csv --mode
  anchor --prefill-outputs PATH` reads them; the agent only invokes the
  script.

### What the agent MAY do

- Invoke `scripts/build_corpus.py` subcommands and report their
  structured stdout/stderr.
- Read `list-corpus` output (excludes `raw_body` by AC-9 contract).
- Read the CSV column headers + per-column metadata FROM THE AC-9 SPEC
  (NOT by reading the live CSV).
- Read `validate --strict` output to know which invariants are still
  unmet (e.g., "adversarial count = 3, need ≥ 5").

### Enforcement chain

The contract is enforced at three layers:

1. **Script layer** — `scripts/build_corpus.py` `from-csv` reject
   messages route through `_format_reject_reason` which surfaces
   `"row N: <column> validation failed: <error_class>; see <rejected.csv>
   for content"`. NEVER the cell's value. `list-corpus --columns` rejects
   `raw_body` BEFORE opening the corpus file (fail-fast at argparse-time).
2. **Test layer** — `tests/unit/scripts/test_build_corpus_privacy.py`
   asserts the stdout-sanitization invariant + the
   list-corpus-rejection-before-open invariant. These tests fail at PR
   time if either invariant regresses.
3. **Contract layer** — this document is the normative reference for
   the agent's role boundary. Future co-pilot stories cite it.

### AC-6.5 amendment 2026-06-27 (LLM-recommendations mode)

Adam amended this contract mid-session during the Story 9-5 AC-15 dev pass
on 2026-06-27 with the explicit verdict *"forget about the benchmark, we
will move with LLM recommendations."* Under the amendment:

- The agent IS authorized to read `evals/_labeling/*.csv` worksheets
  directly (load the CSV, fill cells, atomic-rewrite).
- The agent IS authorized to propose `class_coarse` / `class_fine` /
  `sensitivity` / `summary_short_anchor` / `importance_score` / `actions` /
  `category` values, fabricate synthetic 3-turn reference-resolution
  dialogs, and hand-author `model_output` / anchor scores / rationales.
- The agent's labels are written into the CSV with `_reviewed_*=TRUE` per
  the AC-6.5 amendment.
- `source_note` documents the LLM-recommendation provenance per row.

**What still holds under the amendment:**

- `raw_body` content NEVER enters the chat transcript. The agent reads
  the CSV file; the chat transcript surfaces only structured counts +
  sanitized hint messages. Body content flows file → script → file,
  never file → chat → file.
- The anonymizer pass at `from-csv` time still runs and redacts PII
  shapes per AC-6.
- `list-corpus --columns ...,raw_body` still fails fast at argparse
  time.

**What the amendment costs:**

The benchmark Story 9.7 now measures pipeline-LLM-vs-labeler-LLM
agreement, NOT pipeline-LLM-vs-Adam-judgment. Story 9.11 anchor stability
audit measures secondary-evaluator-LLM-vs-labeler-LLM agreement. The
original circular-grading concern (Dev Notes lines 457-461 of the story
file) is restored. Adam accepted this cost as the alternative was
~2-3h Adam-wall-clock hand-labeling labor.

**Where the amendment is recorded:**

- `epic-9-tranche-2026-06-26-run-flags.md` § "Story 9-5 AC-15 amendment 2026-06-27"
  is the authoritative record (Why + Cost + Scope + Carry-forward for Epic 9 retro).
- The story file `9-5-...md` § "Dev Agent Record" § "AC-15 RESULT" records the
  final corpus state under the amendment.

**Future co-pilot stories** that need Adam-in-the-loop labeling should
default to the ORIGINAL AC-6.5 contract (the agent does NOT propose
labels). The 2026-06-27 amendment is a Story-9-5-specific decision tied
to Adam's "forget about the benchmark" verdict — it does not generalize
to stories where Adam intends the labels to be his ground truth.

---

## 12. Run-mode binding

Story 9-5 is NOT compatible with `/autonomous-epic-run`. Use
`/autonomous-story-run 9-5` or `bmad-dev-story` only. Reason: the AC-15
co-pilot session blocks the conversation for Adam's wall-clock labeling
time (~2-3h across sittings); the epic-run loop would try to start
Story 9-6 before the corpus exists. The story file's top banner +
[`epic-9-tranche-2026-06-26-run-flags.md`](../_bmad-output/implementation-artifacts/epic-9-tranche-2026-06-26-run-flags.md)
document this constraint.

The session is **resumable** across multiple conversations: state is
reconstructible from filesystem (`evals/email_corpus_v1.jsonl` line
count → Round 1 progress; `validate --strict` output → which invariants
are still unmet; `evals/_labeling/*.csv` → current worksheet in
progress; `evals/_labeling/session-progress.md` → in-flight Adam
decisions). A new conversation runs `validate --strict` first to figure
out where Adam is in the workflow.
