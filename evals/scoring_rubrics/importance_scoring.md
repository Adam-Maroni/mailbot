# Rubric: `importance_scoring`

## Success criteria

`labels.importance_score` is an integer 1-5 (1 = least important / spam-
adjacent; 5 = highest priority / Adam must address now). The model's
output is scored as **within ±1 of Adam's label** = correct;
**within ±2** = partial credit (0.5); otherwise incorrect (0).

This is a regression rubric, not a classification rubric — small
calibration drift is acceptable; large drift (≥ 2 score levels off) is a
regression signal.

## Edge case handling

- **Null label**: items where Adam left `importance_score` as null
  (e.g., spam-shaped items where the question is moot) are skipped.
- **Model emits non-integer**: treated as the rounded value if it's a
  float in [1.0, 5.0]; outside that range, scored 0.

## Scoring scale

- **1.0** — exact match (|model - adam| == 0)
- **1.0** — off-by-one (|model - adam| == 1)
- **0.5** — off-by-two (|model - adam| == 2)
- **0.0** — off-by-three-or-more

Reported as mean score `(sum of per-item scores) / (# scored items)`.

## Anchor reference

N/A — objective task scored against Adam's integer label. The 1-5 range
itself is the implicit anchor (no separate file).
