---
baseline_commit: b1784a5
---

# Story 6.18: Sensitivity-class prompt missing `confidence` field — F24 closure + backlog drain

Status: backlog

> **Filed 2026-06-05** during Story 6-6.5 fourth-pass walk. Same defect class as F21 (which Story 6-14 fixed for Haiku `summary_short`) — the prompt instructs the model to "Reply with valid JSON matching the schema; no preamble" but the schema field names are NOT in the prompt, so the model has no signal that `confidence` is required. Backlog at sample time: 712+ rows (growing). **BLOCKS Story 6-6.5 Section B re-walk** (no fresh `sensitivity` classifications => no fixtures for CP-A/B/C). See `epic-6-run-flags.md § F24` for the full finding.

## Story

As the MailBot ingest pipeline,
I want every `sensitivity_class` Router call to receive a schema-valid response from qwen2.5:3b on the first attempt,
So that the 712-email unclassified backlog drains, Story 6-6.5 Section B's CP-A/B/C walks become unblocked, and the privacy-defending sensitivity gate (Story 3-3 + Story 4-7) keeps firing against incoming mail.

## Acceptance Criteria

**AC-1 — Prompt explicitly lists the schema fields.**
Given the current `mailbot_api/prompts/sensitivity_class/v1.py` SYSTEM block instructs the model to reply with valid JSON but does NOT enumerate the required fields,
When this story closes,
Then the SYSTEM block MUST explicitly list `sensitivity`, `confidence` (float between 0.0 and 1.0), and `reason` (max 200 chars) as required output keys,
And the prompt version MUST bump (`v1` -> `v2`) per Rule M byte-stable-prompt discipline,
And the resolver in `mailbot_api/prompts/__init__.py` MUST route `sensitivity_class` to the new v2 file.

**AC-2 — Live roundtrip proves the fix.**
Given the prompt update is deployed,
When a direct `OllamaAdapter.call` is exercised against the live qwen2.5:3b-instruct-q4_K_M model with the new prompt + a representative fixture (the F24 root-cause probe shape — French Microsoft account-security email),
Then the raw response MUST parse cleanly against `SensitivityClassOutput` (`sensitivity` + `confidence` + `reason` all present, types correct).

**AC-3 — Regression test locks in the failure mode.**
Given the root cause is closed,
When the fix lands,
Then it MUST be accompanied by an integration test in `tests/integration/` that:
- (a) uses a mocked `OllamaAdapter` response WITHOUT `confidence` to assert `SCHEMA_VALIDATION_FAILED` (current broken behavior — defends against prompt regression);
- (b) uses a mocked `OllamaAdapter` response WITH all three fields to assert `outcome=ok`;
- (c) bonus: a full-roundtrip test against the real Ollama adapter (gated `pytest.mark.live`) that proves the live model honors the new schema-explicit prompt.

**AC-4 — Backlog drains.**
Given the fix is deployed,
When the next 6 ingest ticks (~30 min at the 5-min cadence) run,
Then `/admin/status` MUST report `ingest.unprocessed_count` strictly decreasing,
And `ingest.backpressure_active` MUST eventually flip to `false`.

**AC-5 — Story 6-6.5 Section B unblocked.**
Given AC-1..AC-4 pass,
When this story closes,
Then `epic-6-run-flags.md § F24` MUST flip from OPEN to RESOLVED with a one-line root-cause summary,
And `epic-6-run-flags.md § Story 6-6.5 walk record § Fourth pass` MUST be updated to flip the "Section B CP-A/B/C/D NOT WALKED" disposition to QUEUED for Adam's re-walk,
And `sprint-status.yaml` row for `6-6-5-epic-5-capstone-carry-forward-walk` MUST be amended noting the F24 unblock.

**AC-6 — MANDATORY-CR per §5.12.**
Two criteria fire: (a) prompt-version bump (Rule M discipline + downstream `prompt_version` field in `router_calls`); (b) cross-story load-bearing (Stories 3-2 prompt seam + 3-3 classifier safeguard + ingest pipeline + Story 4-7 sensitivity-token gate). Minimum one CR pass before done-flip.

## Tasks / Subtasks (high-level, awaits context-engineering)

- [ ] Task 1 — Create `mailbot_api/prompts/sensitivity_class/v2.py` with schema-explicit SYSTEM block; preserve cautious-bias instruction; preserve Rule M byte-stable discipline.
- [ ] Task 2 — Update `mailbot_api/prompts/__init__.py` resolver to route `sensitivity_class` to v2 (and check `router/policy.yaml prompt_version: "v2"` is consistent).
- [ ] Task 3 — Live roundtrip probe via direct OllamaAdapter call (AC-2). Capture the actual qwen response in the story Completion Notes.
- [ ] Task 4 — Regression tests (AC-3): WITHOUT-confidence => SCHEMA_VALIDATION_FAILED + WITH-confidence => ok + optional live roundtrip.
- [ ] Task 5 — Backlog drain monitoring (AC-4). Verify `unprocessed_count` actually decreases over 6 ticks. If it stalls, root-cause (Ollama capacity? Other failure mode?).
- [ ] Task 6 — Cross-doc updates (AC-5): flip F24 status in epic-6-run-flags + update walk record + amend sprint-status row.
- [ ] Task 7 — MANDATORY-CR pass (AC-6).

## Dev Notes (light — full context-engineering at pickup time)

### Root-cause evidence

Captured 2026-06-05 fourth-pass walk via:

```python
adapter = OllamaAdapter(model_id="qwen2.5:3b-instruct-q4_K_M", base_url="http://ollama:11434")
result = await adapter.call(system=SYSTEM_v1, user="Subject: ... From: ... Body preview: ...", max_tokens_out=128)
# result.text == '{\n  "sensitivity": "normal",\n  "reason": "L\'email concerne des applications Microsoft..."\n}'
```

Schema in [mailbot_api/prompts/sensitivity_class/v1.py:46-52](../../mailbot_api/prompts/sensitivity_class/v1.py#L46-L52):

```python
class SensitivityClassOutput(BaseModel):
    sensitivity: Literal["normal", "sensitive", "confidential"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(max_length=200)
```

qwen drops `confidence` entirely. Pydantic rejects. Retry produces same output (deterministic at temperature=0). Policy `escalate: false` (FR-2.5 / Rule Q local-only). Ingest blocked permanently per email.

### F21 / Story 6-14 reference

Story 6-14 closed F21 (same defect class for Haiku `summary_short`) by updating that prompt to explicitly list required JSON keys. Use that story's solution shape as the reference; the qwen prompt update is structurally identical work.

### Cautious-bias preservation (NFR-PRIV-1)

The v1 SYSTEM block contains the cautious-bias instruction ("when uncertain between normal and sensitive, choose sensitive"; "when uncertain between sensitive and confidential, choose confidential"). This MUST be preserved verbatim in v2 — Story 3-3's classifier wrapper also downgrades `confidence < 0.5` to `sensitive` regardless of model label, but the prompt-side bias instruction is the first line of defense.

### References

- [mailbot_api/prompts/sensitivity_class/v1.py](../../mailbot_api/prompts/sensitivity_class/v1.py) — current prompt to be replaced
- [mailbot_api/sensitivity/classifier.py](../../mailbot_api/sensitivity/classifier.py) — FR-2.5 safeguard (qwen-only enforcement)
- [router/policy.yaml](../../router/policy.yaml) — `sensitivity_class` task entry (`escalate: false`, `prompt_version: "v1"`)
- [mailbot_api/router/router.py:670-752](../../mailbot_api/router/router.py#L670-L752) — SCHEMA_VALIDATION_FAILED failure path
- [_bmad-output/implementation-artifacts/6-14-haiku-summary-short-outcome-failed-despite-billing-f21-investigation.md](./6-14-haiku-summary-short-outcome-failed-despite-billing-f21-investigation.md) — F21 closure reference
- `epic-6-run-flags.md § F24` — full finding text

## Dev Agent Record

### Agent Model Used

(awaiting pickup)

### Debug Log References

(awaiting pickup)

### Completion Notes List

(awaiting pickup)

### File List

(awaiting pickup)

### Change Log

- 2026-06-05 — Story 6.18 filed as STUB during Story 6-6.5 fourth-pass walk. Root-cause-identified, fix-shape-clear, awaits context-engineering + dev pickup.
