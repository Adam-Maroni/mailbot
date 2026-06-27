# Rubric: `coarse_class`

## Success criteria

Exact match on `labels.class_coarse` (8-value `Literal`: `transactional`,
`newsletter`, `human_personal`, `human_professional`, `cold_outreach`,
`spam_like`, `notification`, `edge_case`). The benchmark runner emits a
binary `correct` / `incorrect` per item.

## Edge case handling

- **Multi-signal items** (e.g., a marketing newsletter that's also a
  transactional receipt): Adam's labeled `class_coarse` is the dominant
  signal, NOT the secondary one. The model is judged against Adam's call.
- **Edge-case items** (Adam's `edge_case` label): the model is correct
  ONLY if it predicts `edge_case`. Any other label is wrong even if
  arguably defensible — the `edge_case` bin exists for the items where
  the human grader couldn't pick one of the other 7 with confidence.

## Scoring scale

Binary: 0 (incorrect) or 1 (correct). Reported as accuracy `(# correct)
/ (# total)`.

## Anchor reference

N/A — objective task. No subjective anchor file; scoring is mechanical
string-equality against `labels.class_coarse`.
