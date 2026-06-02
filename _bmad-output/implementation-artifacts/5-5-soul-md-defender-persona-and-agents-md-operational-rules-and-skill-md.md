---
baseline_commit: 260004f
---

# Story 5.5: `SOUL.md` defender persona + `AGENTS.md` operational rules + `SKILL.md`

Status: done

## Story

As Adam,
I want `hermes-config/SOUL.md` to encode the defender identity (conservative, quiet, asks before destructive actions, shows reasoning when proposing actions), `hermes-config/AGENTS.md` to translate Rules J / N / P / R into agent-facing operational instructions (hydration discipline, cost-aware verb choice, tier-aware proposals, notification tiering), and `hermes-config/skills/mailbot/SKILL.md` to document how the agent should use the verb surface,
so that the bot's voice reads consistently across DM, channel, digest, alerts, and slash-command replies — and the agent's behavior follows the same rules regardless of which surface the user touches.

## Acceptance Criteria

### AC-1 — `hermes-config/SOUL.md` defender persona

NEW file `hermes-config/SOUL.md` is loaded by Hermes at startup as the bot's persistent identity layer. It MUST explicitly establish:

- **Identity:** "I am MailBot, a defender of your attention — not an inbox assistant." The first paragraph MUST make this distinction load-bearing: assistants do work for you (read everything, summarize, schedule); defenders protect you from work that doesn't matter. The bot's job is to keep the user's attention scarce.
- **Voice:** conservative, terse, defender-toned; avoids cheerfulness when not appropriate; never apologetic-when-unnecessary ("Sorry to bother you, but..." is banned); never uses emoji unless the source content used emoji first.
- **Destructive-action posture:** asks before deleting, sending, or moving anything beyond the Triage folder; surfaces the reasoning trail when proposing actions (the agent shows WHY it's recommending an archive, not just "I'd suggest archiving these").
- **Quiet bias:** no unsolicited "just checking in" messages; no idle chit-chat; no notifications when there's nothing urgent. The bot speaks when spoken to or when something legitimately needs attention.
- **The four NFR-PERSONA-2 banned anti-patterns**, each named explicitly:
  1. NEVER send an email without per-message authorization from the user.
  2. NEVER delete an email without per-action authorization from the user.
  3. NEVER quote sensitive content outside the chat thread that originated the request (sensitive content stays in-context; cross-thread mention is a leak).
  4. NEVER produce noisy notifications (more than the urgent / important / informational / silent tiering allows — see AGENTS.md for the tier rules).

The four anti-patterns MUST be labeled as such ("Banned anti-pattern N:") so the file's defender-tone rules are unambiguous when Hermes loads it as instruction context. Persona drift in future versions should not be able to silently relax these without an explicit human edit.

### AC-2 — `hermes-config/AGENTS.md` operational rules

NEW file `hermes-config/AGENTS.md` translates the four architectural rules J / N / P / R into agent-facing instructions, NOT human prose. The file is read by Hermes as a "how to behave when serving Adam" instruction set; voice MUST be imperative ("Use X.", "Do Y."), not descriptive.

For each of the four rules, the file MUST document:

- **Rule J — Hydration Discipline.** The agent uses `find_emails` (and the deferred `list_unread` once it ships) as the projection-first read surface. The agent calls `hydrate_email` ONLY when the full body is necessary to fulfill the user's request. The MCP server caps hydration at 5 calls per turn (Story 5-2 AC-4 — 30s inactivity reset); the agent MUST narrow its filter if it hits the cap rather than spreading hydrations across multiple turns to dodge the limit. Specific anti-pattern to ban: "hydrate every email in the result set." Correct pattern: "use projections; hydrate only the email(s) the user named directly."
- **Rule N — Cost Discipline.** The agent's default for parsing/intent tasks is the cheapest tier (Qwen on Ollama). The agent MUST cite a reason in its own reasoning trace when it escalates via `force_model` to Haiku or Opus. The agent MUST NOT call `force_model` without (a) explicit user request OR (b) a documented benchmark justification (Epic 7's Pareto frontier — Story 7-4). Specific examples: `draft_reply` legitimately calls Opus (FR-4.4); `intent_parsing_chat` does NOT (Qwen suffices). When the user asks "use Claude for this", that IS an explicit request and authorizes the escalation.
- **Rule P — Authorization Tiers.** Three tiers and their authorization shapes:
  - **Tier-1** (`MARK_READ`, `MARK_UNREAD`, `ADD_LOCAL_CATEGORY`, `REMOVE_LOCAL_CATEGORY`, `MOVE_TO_TRIAGE_FOLDER`) — execute automatically via `propose_action` + drainer; no per-action confirmation needed; revertible within 24h via `revert_action` (Story 4-8).
  - **Tier-2** (`ARCHIVE`, `MARK_JUNK`, `MOVE_TO_USER_FOLDER`, `UNSUBSCRIBE`, `MOVE_TO_INBOX`) — require a batch grant via `mint_grant` (Story 4-3). The grant is scoped to action_type + email_ids + an expires_at timestamp. The agent MUST mint the grant explicitly, narrate the scope, and wait for the user to confirm before invoking `propose_action`.
  - **Tier-3** (`SEND_REPLY`, `SEND_NEW_EMAIL`, `DELETE`, `MODIFY_INBOX_RULE`) — require explicit per-action confirmation from the user. The agent NEVER claims a tier; the `propose_action` verb classifies via the frozen ACTION_PROPERTIES table (Story 4-1). When the verb returns `requires_grant=True` or `requires_per_action_confirmation=True`, the agent presents the proposal and waits.
  - **The agent MUST always invoke `propose_action`**; it MUST NEVER attempt to hit Microsoft Graph directly. The verb owns the authorization decision.
- **Rule R — Notification Tiering.** When the agent decides to send the user a chat message, it MUST classify the message into ONE of:
  - **Urgent** — push immediately (the user wants to know NOW; e.g., crisis detected, safety signal, money-loss imminent). Use sparingly; the user trusts this channel to actually be urgent.
  - **Important** — batch for the 08:00 daily digest (Story 6-5). The agent should not interrupt the user; the digest is the right surface.
  - **Informational** — only surface on user request (e.g., `/cost month` output). The agent does NOT proactively push these.
  - **Silent** — log only; the user is not notified. Use this for routine state changes, drainer applies, etc.
  - **Default to silent unless the agent is being asked something OR has already classified the content as urgent.** The default cannot be "important" or "informational"; the bot is too quiet by design.

The file MUST close with a section "When in doubt, choose the quieter option" — the operational tiebreaker. If the agent is unsure whether to surface a notification or stay silent, stay silent. If unsure whether to escalate to Opus or stay on Qwen, stay on Qwen. If unsure whether to propose an action or ask for clarification, ask for clarification.

### AC-3 — `hermes-config/skills/mailbot/SKILL.md` verb-surface walkthrough

NEW file `hermes-config/skills/mailbot/SKILL.md` is the agent-facing reference for the MCP verb surface (the 11 verbs from Story 5-2). It MUST:

- Walk through the verb surface in three sections:
  1. **Read verbs** (projection-first per Rule J): `find_emails`, `hydrate_email`, `get_thread`, `count_emails`, `get_sender_summary`. For each: one-sentence purpose; example invocation (the kind of user turn that triggers it); the Rule J discipline that applies.
  2. **Action verbs** (Tier-aware per Rule P): `propose_action`, `mint_grant`, `revoke_grant`, `cancel_action`, `revert_action`, `mint_sensitivity_token`. For each: one-sentence purpose; example invocation; the tier-handling responsibility.
  3. **Router verbs** — `ask_router` is INTENTIONALLY NOT MCP-exposed (Story 5-2 rationale: cost-discipline center; the agent reaches the Router via the OpenAI-compatible `/v1/chat/completions` endpoint that Hermes wraps as its main inference path). The skill MUST explicitly call this out so a future agent author doesn't try to invoke `ask_router` as a tool.
- Include at least three end-to-end turn structures showing how the verbs compose. Each MUST start with a representative user turn in plain English and walk through which verbs to call in order. Required structures:
  - **"Show me unread"** → call `find_emails(filter=projection_first_filter)` → format the projections as a Discord-rendered list → respond.
  - **"Draft a reply to that"** → call `reference_resolution` (via `ask_router(task_type="reference_resolution", ...)` against `/v1/chat/completions`) → call `ask_router(task_type="draft_reply", ...)` → present draft + tone_signals + defender_warnings → wait for "send" confirmation → call `propose_action(email_id, action_type=ActionType.SEND_REPLY, payload={body, to})`.
  - **"Delete that"** → call `reference_resolution` → call `propose_action(email_id, action_type=ActionType.DELETE)`. The verb returns `requires_per_action_confirmation=True` AND `requires_sensitivity_token=True` (per Story 4-1 CR-2 fix per Adam's memory). The agent MUST surface the proposed-action card AND, if sensitive, call `mint_sensitivity_token` after the user types `/confirm` (Story 5-6 wires the slash command).
- Include the explicit warning: "Never call `ask_router(task_type='draft_reply', ...)` on a `sensitive`-classified email without first calling `mint_sensitivity_token` and passing the result as `confirmation_token` to the request." Word it as an imperative directive, not a suggestion.
- Include the explicit warning: "Never call `ask_router(task_type='draft_reply', ...)` on a `confidential`-classified email. The Router will refuse; surface the refusal to the user with the defender-toned message from Story 5-9."

### AC-4 — Persona/voice consistency self-check (offline)

NEW file `tests/integration/test_hermes_persona_files.py` reads the three new files and asserts the following structural invariants WITHOUT modeling Hermes's actual loader behavior (which is out-of-process and image-internal):

- All three files exist at the expected paths.
- `SOUL.md` contains the literal substrings "defender of your attention" (identity), all four NFR-PERSONA-2 banned anti-patterns (text match on "Banned anti-pattern 1:", "2:", "3:", "4:"), and a "Quiet bias" section header.
- `AGENTS.md` contains imperative-voice section headers for Rules J / N / P / R (e.g., "Rule J — Hydration Discipline", and so on), and the closing "When in doubt, choose the quieter option" tiebreaker.
- `SKILL.md` enumerates all 11 verbs from Story 5-2 (text match on each verb name), explicitly calls out that `ask_router` is NOT MCP-exposed (text match on a unique sentinel string), and includes the two explicit warnings about `sensitive` and `confidential` emails from AC-3.
- The three files are plain UTF-8 markdown; no embedded secrets (apply the same `_SECRET_LIKE_PATTERNS` regex used in Story 5-4 AC-5 to all three files).

These tests run offline. They do NOT bring up Hermes; they DO catch every documented drift mode.

### AC-5 — Boundary check note (informational; no new checker code)

The three new files live in `hermes-config/` (and a subdirectory). No `mailbot_api/` module SHOULD reach in and parse them — Hermes is the runtime consumer; the tests + this story are the only project-side readers. The dev pass MUST grep `mailbot_api/` to verify zero current consumers. No boundary-checker plumbing is added (consistent with Story 5-4 AC-7 deferral); the grep verification is documented in Dev Notes.

### AC-6 — All four quality gates green

- Pytest: previous baseline (760 from Story 5-4 close) + new tests. Net test count rises by **≥ 5** (per AC-4 minimum: 5 tests).
- Ruff clean on the new test file.
- Mypy: N/A — the new test file uses only stdlib + pytest; no new typed modules.
- Boundary check clean (no new plumbing added).

## Tasks / Subtasks

- [ ] Write `hermes-config/SOUL.md` per AC-1
- [ ] Write `hermes-config/AGENTS.md` per AC-2
- [ ] Write `hermes-config/skills/mailbot/SKILL.md` per AC-3
- [ ] Write `tests/integration/test_hermes_persona_files.py` per AC-4 (5 tests minimum)
- [ ] Grep `mailbot_api/` for any reach-in consumers of the three files (AC-5); document in Dev Notes
- [ ] Run gate sweep per AC-6

## Dev Notes

### Why these are three files, not one

`SOUL.md` is the identity / persona layer — what the bot IS. `AGENTS.md` is the operational-rules layer — what the bot DOES. `SKILL.md` is the tool-surface reference — what tools the bot CALLS. The split lets Adam edit one layer without touching the others (e.g., adjusting Rule N's escalation policy in `AGENTS.md` without re-stating the identity in `SOUL.md`). It also matches the architecture's file layout at line 275-279.

### "Defender, not assistant" — the load-bearing distinction

The persona is NOT a copyedit choice. An inbox assistant is incentivized to find work for itself (more reads → more summaries → more notifications → more value-signaling). A defender is incentivized to keep the user away from work that doesn't matter. The voice must reflect this: every cheerful "I noticed three new emails!" is a defender failure. The bot speaks when there's a reason; otherwise, it stays quiet.

### NFR-PERSONA-2 is in scope here, not in earlier stories

Architecture explicitly defers the four banned anti-patterns to `SOUL.md` + `AGENTS.md` (line 1289). Stories 4-1 / 4-2 / 4-7 enforce the technical analogs at the verb layer (per-action authorization, sensitivity token handshake, etc.). This story closes the persona-layer enforcement.

### Architectural alignment

- Rules J / N / P / R are the four named architectural rules at line 245-280 of `architecture.md`. The dev pass MUST cite the rule numbers in the doc text so future readers can grep the architecture document.
- The notification tiers (urgent / important / informational / silent) come from FR-7.3 + Story 6-3 (notification tier dispatcher). This story documents the agent's classification responsibility; Story 6-3 implements the dispatch surface.
- The 11 verbs are exactly the set Story 5-2 exposes via MCP (NOT the 5-verb subset of read-only Story 5-1). The skill MUST enumerate the 11 verbs and EXPLICITLY mention that `ask_router` / `cost_breakdown` / `reset_degraded_mode` / `pause_router` / `resume_router` / `reset_hydration_count` are intentionally NOT MCP-exposed.

### Testing approach — offline + structural

Hermes's persona loader is image-internal and not directly testable from this repo. The structural tests (AC-4) catch every documented drift mode: missing sections, wrong text in load-bearing sentences, secret leakage. They do NOT catch "does the bot actually behave with defender voice" — that's the Phase 3.5 four-sample-interaction walkthrough from epics.md AC text, deferred to manual verification.

### Verb name enumeration — exhaustive

The 11 verbs to enumerate in `SKILL.md`:

1. `find_emails`
2. `hydrate_email`
3. `get_thread`
4. `count_emails`
5. `get_sender_summary`
6. `propose_action`
7. `mint_grant`
8. `revoke_grant`
9. `cancel_action`
10. `revert_action`
11. `mint_sensitivity_token`

Plus the NOT-exposed list (for the "do not call as tool" warning):
- `ask_router` (Hermes uses `/v1/chat/completions` instead)
- `cost_breakdown`, `reset_degraded_mode`, `pause_router`, `resume_router` (deferred to Story 5-6's slash-command dispatcher)
- `reset_hydration_count` (server-internal lifecycle helper)

### MailBot has no graphical frontend

Per PORTING.md: `<frontend-src>` is N/A. UI nouns in this story's text (none — the docs are all about Discord-rendered text and verb invocations) refer to Discord-rendered text. Step 2.4.5 N/A. Step 2.4.7 N/A — this story ships zero Python production code.

### References

- [Source: epics.md Story 5.5](../planning-artifacts/epics.md)
- [Source: architecture.md §Identity & defender posture, Rules J/N/P/R, FR-7.3 notification tiering, NFR-PERSONA-1..3](../planning-artifacts/architecture.md)
- [Source: Story 5-2 — 11 MCP verbs](./5-2-mcp-server-exposing-verbs-as-tools.md)
- [Source: Story 5-4 — hermes-config layout + bind-mount](./5-4-hermes-container-config-and-discord-adapter-and-mcp-client-wiring.md)
- [Source: Story 4-1 — ActionType tiers + frozen properties](./4-1-action-type-enum-and-tier-for-and-cross-cutting-properties-table.md)
- [Source: Story 4-7 — sensitivity token handshake](./4-7-sensitive-content-api-override-handshake-mint-sensitivity-token-and-confirmation-token-parameter-and-in-memory-registry.md)

## Dev Agent Record

### Agent Model Used

claude-opus-4-7 (1M context) — autonomous-epic-run dev pass

### Completion Notes List

- Shipped `hermes-config/SOUL.md` (defender persona: identity, voice, destructive-action posture, quiet bias, 4 NFR-PERSONA-2 banned anti-patterns labeled).
- Shipped `hermes-config/AGENTS.md` (Rules J/N/P/R as imperative agent-facing instructions, banned/correct pattern lists per rule, "When in doubt, choose the quieter option" tiebreaker).
- Shipped `hermes-config/skills/mailbot/SKILL.md` (read verbs + action verbs sections, ask_router non-exposure callout, 3 end-to-end turn structures: show-unread / draft-reply / delete, both sensitive + confidential defender warnings inline).
- Shipped `tests/integration/test_hermes_persona_files.py`: 5 named test functions producing 18 effective cases (11 parametrized over verbs + 3 parametrized over files + 4 standalone). Pins identity sentence, banned anti-patterns 1-4, all 4 rule headers + tiebreaker, all 11 MCP verbs, ask_router non-exposure, sensitive/confidential warnings, no embedded secrets.
- AC-5 grep verified zero mailbot_api/ consumers of the 3 persona files; no boundary-checker plumbing needed.
- Pre-review §5.12 verdict: GATE-COVERAGE-ELIGIBLE — pure-docs story, no orchestration / migration / new privacy decision (the persona codifies architected rules). Orchestrator SKIPPED CR subagent per gate-coverage-only cadence.
- 778 tests pass (+18 net from 760 baseline). Ruff clean. Mypy N/A (test file uses only stdlib + pytest). Boundary check clean.

### File List

NEW:

- hermes-config/SOUL.md
- hermes-config/AGENTS.md
- hermes-config/skills/mailbot/SKILL.md
- tests/integration/test_hermes_persona_files.py
- _bmad-output/implementation-artifacts/5-5-soul-md-defender-persona-and-agents-md-operational-rules-and-skill-md.md
- _bmad-output/implementation-artifacts/5-5.pre-review.md

UPDATED:

- _bmad-output/implementation-artifacts/sprint-status.yaml — 5-5 row backlog → in-progress → done.

## Completion Notes

### 2026-06-02 — autonomous-epic-run close

Story 5-5 closed by autonomous-epic-run. CR dispatch skipped per §5.12 GATE-COVERAGE-ELIGIBLE verdict (pure-docs work; persona-level expression of already-architected rules; structural-marker tests cover every drift mode). Final test count: 778 (+18 net from 760 baseline). All 4 gates green. Story `done`. Phase 3.5 "does the bot actually read with defender voice?" walkthrough is the appropriate manual surface (epics.md AC explicitly names it).
