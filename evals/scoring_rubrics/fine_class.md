# Rubric: `fine_class`

## Success criteria

Exact match on `labels.class_fine`. This task is conditional: only
items with `labels.class_coarse == "human_personal"` OR
`labels.class_coarse == "human_professional"` carry a non-null
`class_fine` label. Items with other `class_coarse` values are SKIPPED
from this rubric's evaluation (the model's output for them is not
scored under this rubric).

## Edge case handling

- **Null label**: items where Adam left `class_fine` as null (because the
  `class_coarse` did not require it) are skipped, NOT marked incorrect.
- **Model emits a fine label on a non-human coarse item**: not penalized
  here (this rubric only scores items Adam labeled with a non-null fine
  class); the `coarse_class` rubric is the relevant penalty surface.

## Scoring scale

Binary: 0 / 1 over the subset of items with non-null `labels.class_fine`.

## Anchor reference

N/A — objective task.
