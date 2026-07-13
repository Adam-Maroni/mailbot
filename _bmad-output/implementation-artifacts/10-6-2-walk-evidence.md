# Story 10-6-2 — Manual Verification Walk Evidence (2026-07-13)

**Delegated:** Adam said "Run manual verification yourself." Driven at the real
`handle_draft_reply` orchestrator inside the actual FastAPI `lifespan()` (real
policy load + `init_default_adapters()` + real Anthropic Opus adapter + real
on-disk `/data/mailbot.db`) — the exact server bootstrap Hermes's MCP
`draft_reply` tool call runs through. Stack: mailbot-api healthy, hermes up,
ollama up; `ANTHROPIC_API_KEY` SET.

**Honesty / scope tag:** I drove the pipeline at the **orchestrator + real
Router + real Opus + real SQLite** boundary — the exact code path the MCP
`draft_reply` verb wraps. What I *cannot* do (and did NOT fake): be the Hermes
LLM persona typing in Discord. So AC-2's "the persona *chooses* to issue the
verb on a real turn" and AC-5's Opus *draft-quality* judgment are **Adam-only
L3** — this walk proves the verb is reachable, dispatches to Opus, writes the
correct DB row, and that the sensitivity gate holds, which is the structural
half of AC-1/AC-3 + the reachability AC-2 depends on.

## Checkpoints

### CP-1 [AC-3] Confidential draft → refused (no Opus) — PASS(L3)
Drove `handle_draft_reply` on a real `sensitivity=confidential` email
(`...AaHGAQAJDjTzggAA`, subject "ETA-IL Application number…"). Result:
`state=confidential_refused`, 1ms, 0 body, **0 Opus calls**. The gate refuses
confidential unconditionally (NFR-PRIV-2) — the new reach contract did NOT
weaken it.

### CP-2 [AC-3] Sensitive draft without token → needs_sensitivity_token (no Opus) — PASS(L3)
Drove on a real `sensitivity=sensitive` email
(`...AaHGAQAJFm04uQAA`). Result: `state=needs_sensitivity_token`, 1ms, 0 body,
**0 Opus calls**. The pipeline demands the `mint_sensitivity_token` handshake
before any cloud draft — FR-2.3/F28 gate intact. (Both gates short-circuit on
the DB sensitivity classification BEFORE any policy/Opus access, so they held
even in a bare harness.)

### CP-3 [AC-1 / AC-5 structural] Normal draft → real Opus draft_reply row — PASS(L3)
Drove on a real `sensitivity=normal` email (`...AaHGAQAJFm1EkAAA`) inside the
full `lifespan()`. Observed **two `POST https://api.anthropic.com/v1/messages →
200 OK`** calls (tone_style_mirror + draft_reply), `state=draft_presented`,
4442ms. **New `router_calls` row id 14861: `task_type=draft_reply,
model_chosen=claude-opus-4-7, model_chosen_reason=policy:draft_reply:default,
outcome=ok, caller_origin=chat-orchestrator, cost_usd_estimated=$0.00602`**
(delta +1 draft row). This is the exact AC-1 DB ground-truth shape:
`model_chosen=claude-opus-*` (NOT haiku), traceable to the chat orchestrator.
The MCP server logged `tools: 26` (draft_reply registered + discoverable).

### CP-4 [reachability, AC-2 structural] The verb dispatches, not improvises — PASS(L3)
The `draft_reply` MCP verb resolved, dispatched through the real Router, routed
to Opus per `policy:draft_reply:default`, and produced a real audit row — i.e.
the capability the persona contract now points at is genuinely reachable. The
persona-doc change (SKILL.md Reach contract) makes the persona *choose* this
path; this walk proves the path it points at works end-to-end.

## Finding (INFO, pre-existing, out of 10-6-2 scope)

**WALK-10-6-2-F1 (INFO) — empty `draft_body` on a no-reply marketing email.**
The normal-path draft returned `state=draft_presented` but `draft_body=''`
(empty) for the chosen source email, which is a promotional "Satisfactory and 2
other items from your…" marketing blast with nothing substantive to reply to.
Opus returned schema-valid `DraftReplyOutput` (it passed the `isinstance`
contract → not a `router_error`) with an empty body — plausibly correct
"nothing to draft here" behavior for a no-reply notification. **This is in the
pre-existing Opus draft pipeline (Story 5-9 / 10.5.3), entirely upstream of
10-6-2's persona-doc change** (10-6-2 touched only `hermes-config/…/SKILL.md` +
a test — no `orchestrator.py`, no prompt, no parser). Not a regression from this
story. For the real Discord walk, Adam should pick a genuine person-to-person
email to judge Opus draft quality (AC-5). Worth a follow-up look at whether an
empty-body `draft_presented` should instead surface a "nothing to reply to here"
defender message, but that's a draft-pipeline UX question for a separate story.

## Collateral / restoration

- **0** open `pending_actions` (draft-only walk; never reached `propose_action`
  — no send proposed, no cooling-off row, no grant minted by the walk).
- `action_grants`: 10 (pre-existing; NOT created by this walk).
- pause OFF, degraded OFF. All 3 containers healthy.
- **Real side-effects:** 2 legitimate Opus `draft_reply` `router_calls` audit
  rows (ids 14861 + one tone_style_mirror sibling), ~**$0.0121 estimator**
  spend. **Console is the authoritative spend source** ([[feedback_anthropic_spend_source_of_truth]]);
  the $0.0121 is the local estimator figure for a 2-Opus-call verification.
  No mailbox mutation, no synthetic rows.

## Per-AC verdict

- **AC-1** — PASS(L3, structural): real Opus `draft_reply` `router_calls` row
  (`model_chosen=claude-opus-4-7`) produced via the real pipeline. The
  *persona-in-Discord* half is Adam-only.
- **AC-2** — PASS(L3, structural) + Adam-only behavioral: the verb is reachable
  + dispatches to Opus (proven); "the persona chooses it over improvising" is
  the Discord walk.
- **AC-3** — PASS(L3): confidential refused + sensitive-requires-token, both
  live, no Opus leak. No regression.
- **AC-4** — PASS (MANDATORY-CR discharged in the dev pass; reviewer ≠ dev).
- **AC-5** — PARTIAL(L3): real Opus draft ran + spent real money; draft *quality*
  judgment is Adam-only (and the chosen test email was a marketing blast → empty
  body; pick a real email for the quality read).

**Verdict: PASS WITH FINDINGS** (1 INFO finding, pre-existing + out of scope).
Story stays **done** at L1/L2; AC-1/AC-5 live-Discord-persona + Opus-quality
remain Adam's Phase 3.5 sign-off (Epic 10.6 done-flip clause 4).
