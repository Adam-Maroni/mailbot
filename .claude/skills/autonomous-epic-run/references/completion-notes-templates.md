# Completion Notes & Sprint-Status Truncation Templates

This file expands Step 2.4.8 of the autonomous-epic-run skill — the Verbose-Row Truncation Gate. Load this when flipping a story to `done` and capturing its narrative.

**Why this exists:** without an explicit truncation contract, sprint-status rows accrete a paragraph at every state transition. Audit trail integrity is preserved, but the file becomes unreadable. Sprint-status's job is to be the *index* of sprint health, not the *content*. Story files already are the canonical content home (`## Completion Notes` section). This gate enforces the split.

**Hard contract:** when flipping a row to `done`, the skill MUST:

1. **Capture the verbose narrative** from the in-progress row content (everything after `# YYYY-MM-DD:` markers — the paragraph(s) describing dev pass, review findings, remediation, gate results).
2. **Append to story file `## Completion Notes`** — write or extend the `## Completion Notes` section in `<bmad-output>/implementation-artifacts/{story-id}-*.md` with the captured narrative. Preserve any existing Completion Notes content; append new content with a `### {YYYY-MM-DD} — {phase}` header (e.g., `### 2026-05-15 — Done flip`).
3. **Replace the row content** with a 1-2 sentence summary + pointer. The summary captures the headline outcome only (verdict, key metrics, key followup pointers if any).

**Apply going forward only.** Existing rows on the target project retain historical bloat as audit trail — do NOT retroactively rewrite. The first row using the new pattern is the next `done`-flip after this gate ships.

## Sprint-status row template (truncated)

```yaml
{story-id}: done # {YYYY-MM-DD}: {headline-sentence}. See [story-file]({path}#completion-notes) for full dev/review/UAT history.
```

### Headline-sentence shape

```
{action verb} {key outcome}; {key metric or scope} delivered; {0|1|2} followup(s) filed{; if reopened, "REOPENED" + reason in 5 words max}
```

### Examples

- `Toast acknowledgment pattern shipped; 8 ACs delivered, 11 prod/test files modified, 2 followups filed. See [story file]({story-id}-scrape-acknowledgment-affordance.md#completion-notes).`
- `Provider consolidation shipped; 12 ACs delivered, single-provider architecture, 1 followup filed. See [story file]({story-id}-llm-provider-consolidation.md#completion-notes).`

## Story file `## Completion Notes` template

```markdown
## Completion Notes

### {YYYY-MM-DD} — Dev pass complete (Status: review)

{verbose narrative captured from sprint-status row about dev work, test counts, ACs delivered, pre-review summary}

### {YYYY-MM-DD} — Code-review pass (review model: {model-id})

{verbose narrative about code-review findings, severity distribution, remediation, re-run gate results}

### {YYYY-MM-DD} — Done flip (Status: done)

{verbose narrative about final gate results, regression test totals, lint/build/i18n/lockfile state, dev-env verification verdict if applicable}

### {YYYY-MM-DD} — Post-done amendment (if any)

{any narrative about subsequent reopening, follow-up findings, UAT verdicts, etc. — preserves audit trail without bloating sprint-status row}
```

## Refuse-to-proceed enforcement

1. Before writing the `done`-flipped row, check that `<bmad-output>/implementation-artifacts/{story-id}-*.md` exists (the story file).
2. Read the story file. Verify it has a `## Completion Notes` section (create one if missing — append after `## Dev Agent Record`).
3. Write the captured narrative to the story file's Completion Notes section per the template.
4. Replace the sprint-status row with the truncated headline + pointer.
5. If the story file is missing or unwritable, HALT with:

```
🛑 Verbose-Row Truncation gate (Step 2.4.8) — story {story-id} cannot proceed to done-flip.

Reason: {missing story file at expected path | story file unwritable | Completion Notes section append failed}

Required: story file at <bmad-output>/implementation-artifacts/{story-id}-*.md with appendable ## Completion Notes section.

Do not flip sprint-status to done until the verbose narrative is captured in the story file.
```

## Why hard refuse, not loud-fail

Soft-commitment versions of "remember to be concise in sprint-status" decay over time. The forcing function is the only mechanism shape that survives contact with autonomous execution. The cost of the refuse is one extra Read+Write per `done`-flip; the benefit is sprint-status stays readable forever.

## Interaction with other gates

- **Step 2.4.4** (Dev Agent Record completeness) — this gate fires AFTER it; the Completion Notes section that this gate writes to is part of the Dev Agent Record completeness contract.
- **Step 2.5** (per-story dev-env verification) — fires AFTER this gate. Truncation happens before dev-env verification runs; the verification verdict is appended to Completion Notes by the dev-env skill itself if it produces a notable outcome.
- **Step 2.6** (staging) — this gate's writes to the story file count as story-scope changes and SHOULD be in the staging allow-list per Step 2.6.