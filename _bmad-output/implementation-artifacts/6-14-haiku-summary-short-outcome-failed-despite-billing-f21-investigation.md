# Story 6.14: Haiku `summary_short` `outcome=failed` despite billing — F21 investigation

Status: backlog

> Filed 2026-06-04 during Story 6-6.5 third-pass walk. NO inline fix applied — the root cause is unclear and the fix shape is non-obvious. This story is an investigation-then-fix story (same shape as Story 6-11 was for F17). NON-BLOCKING for Story 6-6.5 Section B re-walks (summary_short is an ingest-pipeline task, not a draft-reply task).

## Story

As MailBot,
I want every Haiku `summary_short` ingest call to either succeed (`outcome=ok`) or fail BEFORE billing (no token consumption recorded against a failed call),
So that I am not paying ~$0.001 per failed call for outputs we cannot validate — and so the ingest pipeline can actually produce summaries instead of perpetually failing.

## Acceptance Criteria

**AC-1 (root cause identified)**: Through the same investigation pattern Story 6-11 used (reproduce, isolate, add instrumentation if needed, identify), the root cause of `summary_short outcome=failed with cost>0` is documented in this story file's Dev Notes with: (a) which validation step rejects the output (schema, content, length, etc.); (b) what shape the Anthropic response actually has vs what the validator expects; (c) whether this is prompt-side drift (Story 5-3 prompts updated since policy was loaded?), schema-side drift (output Pydantic model tightened?), model-side drift (Haiku 4.5 changed default output format?), or some combination.

**AC-2 (fix applied)**: Either (a) the prompt/schema/parser fix lands inline with this story OR (b) the story closes with a documented decision-deferral citing why the fix is out of scope (e.g., "the schema is correct but Haiku 4.5 prose tail-content makes it unfit for this task — recommend swap to Qwen via policy.yaml change in Story X").

**AC-3 (regression test)**: A test asserts the success path against a recorded real Anthropic response (Story 6-11 pattern via `httpx.MockTransport`).

**AC-4 (backlog drain)**: Once the fix is applied, the ingest pipeline catches up on the summary_short backlog (the unclassified-then-classified-but-no-summary rows). Verify via `/admin/status` ingest section.

**AC-5**: MANDATORY-CR if the fix touches prompt files or schema files (cross-story load-bearing).

## Tasks / Subtasks

- [ ] **Task 1**: Reproduce locally: pick one of the failed `summary_short` rows (e.g., `router_calls.id=389`, model=`claude-haiku-4-5-20251001`, outcome=failed) — query the email_id, fetch the email body, replay the prompt call against live Anthropic, capture the raw response.
- [ ] **Task 2**: Run the response through the validator that produces the failed outcome — log the validation error.
- [ ] **Task 3**: Identify which dimension drifted (prompt / schema / model / parser).
- [ ] **Task 4**: Apply the fix OR document the deferral (AC-2).
- [ ] **Task 5**: Add the regression test (AC-3).
- [ ] **Task 6**: Confirm backlog drains (AC-4).
- [ ] **Task 7**: Gates + CR if needed.

## Dev Notes

### Why this story exists

Story 6-6.5 third-pass walk surfaced F21 as a side-observation. Story 6-11's completion notes had already hinted at it ("new downstream finding: summary_short schema_validation_failed (was masked by sensitivity short-circuit; out of scope for this story; file as follow-up)") — Story 6-6.5's walk confirmed the symptom is still live and the cost is real.

### F21 details

Every `claude-haiku-4-5-20251001 summary_short` ingest call today (router_calls ids 389/392/396/400/403/407/410/413/421/425, ...) shows `outcome=failed` with non-zero `cost_usd_estimated` (~$0.001/call). The Anthropic call succeeds — Anthropic charges us — but the response fails downstream validation.

Cost impact: ~$0.001 per failed call × ~10+ calls/min in steady-state ingest = ~$0.6/hr if left running. Not catastrophic but not zero either.

Working hypothesis: schema_validation_failed at the prompt-output Pydantic boundary (`SummaryShortOutput` or similar in `mailbot_api/prompts/summary_short/v1.py`). Haiku may be emitting prose with a JSON-fenced block that the strict-extract path no longer accepts, OR the schema may have tightened in a recent story, OR Haiku 4.5 itself may have shifted its default output format.

### Reference rows

| router_calls.id | ts | tokens_in | tokens_out | cost |
| --- | --- | --- | --- | --- |
| 389 | 2026-06-04T16:04:52.614456Z | 716 | 48 | $0.0010 |
| 392 | 2026-06-04T16:05:17.173419Z | 670 | 132 | $0.0013 |
| 396 | 2026-06-04T16:05:47.843963Z | 582 | 63 | $0.0009 |
| 400 | 2026-06-04T16:06:23.251518Z | 1062 | 56 | $0.0013 |
| 403 | 2026-06-04T16:06:59.845527Z | 1062 | 58 | $0.0014 |

### References

- `_bmad-output/implementation-artifacts/epic-6-run-flags.md § Story 6-6.5 walk record § Third pass § F21`
- `_bmad-output/implementation-artifacts/6-11-ingest-pipeline-provider-error-investigation.md` — completion notes flagged this as downstream finding
- `mailbot_api/prompts/summary_short/v1.py` — likely surface for the fix
