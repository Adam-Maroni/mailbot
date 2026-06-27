# Rubric: `draft_reply`

## Success criteria

Subjective task — scored by an LLM scorer (Story 9.7) calibrated against
20 Adam-authored anchors in `evals/anchors/draft_reply_anchors.jsonl`.
Per-axis scores in 1-5; the auto-eval is considered passing when its
output is within ±0.5 MAE of Adam's anchor scores across the calibration
set (per Story 9.7 acceptance).

## Edge case handling

- **Empty reply**: scored 1 across all axes.
- **Reply that contradicts the email's content** (hallucinates a
  commitment Adam didn't make): heavy penalty on `faithfulness` (1-2).
- **Reply that's tonally wrong** (e.g., chatty in response to a formal
  legal request): penalty on `tone_match` (1-2).
- **Reply that doesn't advance the conversation** (no next action, no
  ask, no acknowledgement): penalty on `actionability` (1-2).

## Scoring scale

1-5 per axis, on three axes:
- **`faithfulness`** — does the reply accurately reflect what was said
  in the inbound email and what Adam's position should be? (1 =
  contradicts / hallucinates; 5 = faithful).
- **`tone_match`** — does the reply match Adam's voice + the formality
  expected by the inbound? (1 = jarring mismatch; 5 = correct tone).
- **`actionability`** — does the reply move the conversation forward
  with a clear next step? (1 = no action; 5 = clear next step).

`adam_overall_score` is the holistic 1-5 verdict (not necessarily the
mean — Adam may weight tone or faithfulness more heavily).

## Anchor reference

`evals/anchors/draft_reply_anchors.jsonl` (20 items, AC-3 contract).
The scorer's prompt INLINE-INCLUDES the 20 anchors as calibration
examples; Story 9.11 audits cross-evaluator agreement on these same 20
anchors via Krippendorff α.
