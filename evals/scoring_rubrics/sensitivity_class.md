# Rubric: `sensitivity_class`

## Success criteria

Exact match on `labels.sensitivity` (3-value `Literal`: `normal`,
`sensitive`, `confidential`).

This is the load-bearing rubric for catching F27-class regressions
(multi-signal-borderline sensitivity classification failures). The 5-10
adversarial items per AC-5 are deliberately constructed to exercise
this rubric — their `source_note` documents why each is adversarial.

## Edge case handling

- **Adversarial items** (`labels.adversarial == True`): scored
  identically to non-adversarial items, BUT the report renderer in
  Story 9.9 surfaces accuracy SEPARATELY for adversarial vs.
  non-adversarial subsets so regressions on the adversarial slice are
  visible against the baseline.
- **Mixed-signal borderline**: Adam's labeled value is the ground
  truth — the model is wrong if it predicts a different value, even if
  the signals are genuinely ambiguous.

## Scoring scale

Binary: 0 / 1. Reported as overall accuracy + adversarial-subset
accuracy (per Story 9.9).

## Anchor reference

N/A — objective task.
