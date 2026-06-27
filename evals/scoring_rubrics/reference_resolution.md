# Rubric: `reference_resolution`

## Success criteria

For items with `labels.reference_resolution_slice == True` (exactly 20
per AC-4): the model receives the 3-turn transcript
(`labels.reference_resolution_turns`) AND a candidate set of email ids,
and must emit the resolved email id(s) the final user turn refers to.

The model's output is scored as:
- **1.0** — emitted ids match `labels.expected_resolved_email_ids`
  (set-equality)
- **partial credit** — Jaccard similarity over the symmetric difference
  if the model partially resolved (e.g., found 1 of 2 expected ids)
- **0.0** — emitted ids do not overlap with expected

This is FR-4.3 validation — the load-bearing capability the agent
provides for multi-turn email lookups.

## Edge case handling

- **Items where `reference_resolution_slice == False`**: skipped (not
  scored under this rubric).
- **Model emits no ids**: scored 0.0.
- **Model emits malformed ids** (not in corpus id namespace): scored 0.0.

## Scoring scale

Per-item score 0.0-1.0 (Jaccard over expected vs. emitted id sets).
Reported as mean across the 20 reference-slice items.

## Anchor reference

N/A — objective task. The `expected_resolved_email_ids` Adam-labeled set
IS the ground truth; no separate anchor file.
