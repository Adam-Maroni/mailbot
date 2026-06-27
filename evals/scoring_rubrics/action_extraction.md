# Rubric: `action_extraction`

## Success criteria

Field-level match on `labels.actions` (a list of `ExpectedAction` per
AC-1). The model is correct on an item if it emits actions that match
Adam's label-set on these axes:

- **Count**: # of actions matches Adam's (±0 — exact)
- **`action_type` set**: model's action types match Adam's (set-equality,
  case-insensitive)
- **`summary` for each action**: per-action match scored by a subjective
  scorer (Story 9.7) — not exact-string match (the summary is a paraphrase).

Per-item score is the mean of these three sub-scores (each 0-1).

## Edge case handling

- **Null label**: items where Adam left `actions` as null (no actions
  required, e.g., a newsletter) — the model is correct if it emits an
  empty list, incorrect if it hallucinates actions.
- **Empty list label**: same as null label (treated identically).
- **`deadline` / `recipient` fields**: ignored in scoring unless Adam
  populated them in the label (in which case they're scored as
  field-level match).

## Scoring scale

Per-item score 0.0-1.0 (mean of count + action_type-set + per-action-
summary sub-scores). Reported as mean across items.

## Anchor reference

N/A — objective for the count and action_type axes; the per-action
summary axis is subjective but reuses the `summary_short` scorer with a
narrower prompt (no separate anchor file).
