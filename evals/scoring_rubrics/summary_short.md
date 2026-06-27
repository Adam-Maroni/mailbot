# Rubric: `summary_short`

## Success criteria

Subjective task — scored by an LLM scorer (Story 9.7) calibrated against
20 Adam-authored anchors in `evals/anchors/summary_anchors.jsonl`.
Per-axis scores in 1-5; the auto-eval is considered passing when its
output is within ±0.5 MAE of Adam's anchor scores across the calibration
set (per Story 9.7 acceptance).

## Edge case handling

- **Empty summary**: scored 1 across all axes (the model failed to
  produce output).
- **Summary that hallucinates content not in `raw_body`**: heavy penalty
  on `faithfulness` (score 1-2). The faithfulness axis is the dominant
  penalty surface for hallucinations.
- **Summary that omits the email's primary action item**: penalty on
  `actionability` (1-2 depending on severity).

## Scoring scale

1-5 per axis, on three axes:
- **`faithfulness`** — does the summary accurately reflect what
  `raw_body` says? (1 = hallucinates / contradicts; 5 = faithful).
- **`concision`** — is the summary appropriately compressed? (1 = too
  verbose or too terse; 5 = right-sized for the email).
- **`actionability`** — does the summary surface what Adam needs to do
  next? (1 = misses primary action; 5 = surfaces the right action).

`adam_overall_score` is the holistic 1-5 verdict (not necessarily the
mean of the axes — Adam may weight faithfulness more heavily).

## Anchor reference

`evals/anchors/summary_anchors.jsonl` (20 items, AC-3 contract). The
scorer's prompt INLINE-INCLUDES the 20 anchors as calibration examples;
Story 9.11 audits cross-evaluator agreement on these same 20 anchors via
Krippendorff α.
