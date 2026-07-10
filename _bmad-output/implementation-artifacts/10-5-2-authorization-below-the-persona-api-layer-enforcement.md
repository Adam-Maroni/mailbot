---
baseline_commit: 5b36987
---

# Story 10.5.2: Authorization below the persona — API-layer enforcement + sensitivity-refusal envelope

Status: done

## Story

As Adam,
I want the approval/confirmation contracts — no agent self-mint of sensitivity tokens or grants, Tier-2 approval genuinely solicited, no agent self-edit of gitted skill files — enforced in `mailbot-api` rather than asserted in persona prose, and sensitivity refusals delivered as a structured envelope rendered at the Discord boundary,
So that the human-in-the-loop promises are true because the code enforces them, and a refusal never leaks an internal id or promises an action that doesn't work.

## Context: what Epic 10's walk found (retro §5.2, §8.5)

The persona (SKILL.md / AGENTS.md prose) enforces **nothing**. Within one Epic 10
walk the agent:

- **F-10-5-5 (HIGH)** — self-minted a valid sensitivity escalation token with **no
  user confirmation**. `mint_sensitivity_token` mints unconditionally whenever the
  email's own label is `"sensitive"` — the only gate is the email's classification,
  never a recorded user "yes". Log-proven self-mint succeeded twice (grants
  55cce7df / ddd63dbe). The privacy invariant held that turn only because the token
  *accidentally* failed to attach (session-binding mismatch, F-10-5-7) — defense in
  depth caught what the authorization contract did not.
- **F-10-5-8 (HIGH)** — minted a Tier-2 grant and queued 7 archive writes with **no
  user "yes"**. `mint_grant` validates only structural gates (tier ≥ 2, window ≤ 24h,
  batch ≤ 200); nothing records user approval. The documented "archive all of them?
  (yes / list them / no)" choreography never appeared. The only thing that ever held
  was the API-layer `pending_grant` status gate — which the agent itself flips by
  calling `mint_grant`.
- **F-10-5-7 (HIGH)** — sensitive escalation is **broken by construction**: the token
  binds to the MCP-session identity (survives `/new`), but chat dispatches carry a
  *different* session identity → the token can never attach; AND one attempt bricks
  the session (every later turn refused until manual `/new`). There is **no working
  chat path to escalate a sensitive email** today. A refusal message that offers
  "yes, escalate" while escalation is broken is worse than a raw error — it lies.
- **F-10-5-6 (MEDIUM)** — the router's refusal is correct errors-as-data internally
  (`RouterError(code=SENSITIVITY_BLOCKS_API)`), but the `/v1/chat/completions`
  boundary collapses it into a raw **HTTP-502** retry ladder that also **leaks the
  full Graph email id** into Discord — not the documented graceful prompt.
- **F-10-5-12 (HIGH)** — the agent self-edited its **gitted skill files** mid-turn
  with confabulated content (`skill_manage patch` ×2 against
  `hermes-config/skills/mailbot/SKILL.md`, reverted). The skill dir is bind-mounted
  RW from the repo into the Hermes container, so writes land in the working tree.

**Design principle (retro §6):** authorization contracts are only real at the API
layer. This story moves the contracts out of persona prose into `mailbot-api` code
(and, for the one surface that lives outside `mailbot-api`, into Hermes config —
see the Skill-file boundary note in Dev Notes).

## Acceptance Criteria

**AC-1 — No agent self-mint of sensitivity tokens or Tier-2 grants (F-10-5-5 + F-10-5-8)**
**Given** F-10-5-5 (self-mint sensitivity token, no confirmation) + F-10-5-8 (Tier-2 grant + 7 writes queued, no user "yes")
**When** an agent attempts to mint a sensitivity escalation token or a Tier-2 grant
**Then** the API layer refuses to mint without a genuine user-gated confirmation event — token/grant minting requires a recorded user "yes" that is **not agent-assertable** (an agent that only issues verb calls cannot self-authorize); verified by tests proving the mint refuses when no user-confirmation record exists and succeeds only when one does.

**AC-2 — Skill-file surface is not agent-writable at runtime (F-10-5-12)**
**Given** F-10-5-12 (agent self-edits its gitted skill files mid-turn with confabulated content)
**When** the agent's turn runs
**Then** the skill-file surface is not agent-writable at runtime (prevention at the boundary), so confabulated self-edits are structurally impossible. **Boundary note:** the write vector is the Hermes `file` / `skills` toolset against the RW bind-mount `hermes-config/skills/mailbot/**` — it lives **outside `mailbot_api/`**. This AC is satisfied by a Hermes-side hardening (toolset restriction and/or `:ro` bind-mount) plus a verification that a skill-file write attempt is rejected. Because the hardening is Hermes-config + docker (not `mailbot_api/` code), the config change is authored here but its **live verification is Adam-hands-on** (see Task 5 / run-mode binding).

**AC-3 — Structured sensitivity-refusal envelope rendered at the Discord boundary (B7 / F-10-5-6)**
**Given** the B7 design (retro §8.5) — the structured sensitivity-refusal envelope
**When** the router refuses a sensitive / confidential / not-yet-classified email
**Then** a typed envelope (`email_ref`, `task`, `classification`, `reason`, `user_facing_guidance`) is carried on the refusal and rendered at the Discord boundary as the **four-beat message** (name the state → consequence in user terms → the one action that works → expectations); the internal Graph email id is **not a printable field** (F-10-5-6 leak fixed by construction); the raw **HTTP-502 retry ladder is gone** (refusal carried as errors-as-data per AR-PAT-4, not an exception on the chat path).
**And** the three message shapes match the spec:
- **sensitive** offers "yes, escalate" (only because AC-4 makes escalation genuinely work);
- **confidential** offers **NO** escalation (none exists by design);
- **not-yet-classified** does **NOT** suggest `mailbot rederive` (it crashes until 10-5-4).

**AC-4 — Sensitive escalation genuinely works end-to-end (F-10-5-7)**
**Given** the load-bearing rule (retro §8.5) — a message may only offer actions that actually work
**When** the sensitive refusal offers "yes, escalate"
**Then** F-10-5-7 is fixed **in this story** so the offer is genuine: escalation is user-confirmed, correctly session-bound, attaches, and does not brick the session — demonstrated by a **live sensitive-escalation walk that succeeds end-to-end** (Adam-hands-on; real sensitive email → "yes, escalate" → token attaches → draft/summary dispatches → no session brick).

**AC-5 — CR cadence (MANDATORY-CR, reviewer ≠ dev)**
**Given** this story touches the authorization / token-mint seam
**When** CR cadence is evaluated per the 6 criteria
**Then** criterion 6 (load-bearing) + criterion (security-adjacent) fire → **MANDATORY-CR per §5.12**, full scope, reviewer model ≠ dev model.

## Tasks / Subtasks

### Task 1 — API-layer user-confirmation primitive so mints are not agent-assertable (AC: 1) — DONE
- [x] **RED:** write tests asserting `mint_sensitivity_token` and `mint_grant` REFUSE when no user-confirmation record exists for the (email/action, task/action_type) scope, and SUCCEED only when a genuine user-confirmation record is present. Tests must prove an agent that only issues verb calls cannot manufacture the record. → `tests/integration/test_mint_requires_user_confirmation.py` (8 tests).
- [x] Introduce a **user-confirmation event** primitive in `mailbot-api` that both mint paths consult:
  - The confirmation record is created by a distinct, **user-gated** operation — NOT by an agent verb call. Candidate mechanism (decide at dev time, record the decision in Completion Notes): a `pending_confirmation` row keyed to a real inbound user message/turn id that the Discord boundary stamps, OR a confirmation token that only the `/v1/chat/completions` user-message path (not the tool-call path) can create. The invariant that must hold: **the agent's tool-call surface cannot produce the record** — only a genuine user turn can.
  - `mint_sensitivity_token` (`mailbot_api/verbs/mint_sensitivity_token.py:100`) gains a precondition: refuse with a distinct error code (e.g. `NEEDS_USER_CONFIRMATION`) unless a valid user-confirmation record for this (email_id, task_type) exists.
  - `mint_grant` (`mailbot_api/actions/authorization.py:96`) gains the same precondition for the Tier-2 grant path: refuse to mint unless a user-confirmation record for this (action_type, email scope) exists.
- [ ] Preserve the existing structural gates (tier, window, batch, sensitivity-label) — the new gate is **additive**, checked before mint.
- [ ] Emit an audit row on the refused-mint path (reuse the Rule-C `record_router_call` / existing audit-row writer pattern per 10-5-1; no new raw SQL — keep `check_boundaries.py` green).
- [ ] **GREEN + REFACTOR.** Keep the AR-D12-1 in-memory-registry invariant for the token itself (dies on restart); the confirmation record is the new gate, not a replacement for the registry.

### Task 2 — Structured sensitivity-refusal envelope on RouterError + errors-as-data at the chat boundary (AC: 3)
- [ ] **RED:** write tests asserting that a sensitive / confidential / not-yet-classified refusal from `dispatch_tool_call` and `ask_router` carries a typed envelope with exactly the fields `{email_ref, task, classification, reason, user_facing_guidance}` and that the raw Graph email id is NOT present in any user-facing field; assert the `/v1/chat/completions` endpoint returns the refusal **as a rendered refusal message (200-shape errors-as-data), NOT HTTP-502**.
- [ ] Add a typed `SensitivityRefusal` envelope (reuse the `RecoveryAction` shape `mailbot_api/actions/recovery_action.py:27` as the model for `user_facing_guidance`; the envelope's explicit field allow-list is what makes the Graph id structurally unprintable). Carry it on `RouterError` (`mailbot_api/router/errors.py:66`) via an additive optional field (e.g. `refusal_envelope: SensitivityRefusal | None`).
- [ ] `email_ref` is a **safe reference** (e.g. the short display ref the user already sees), never the internal Graph message id — enforce by construction (the id is not a field on the envelope).
- [ ] Populate the envelope at the three router refusal sites: `router.py` `dispatch_tool_call` precondition layer (`:1879`/`:1912`/`:1951`/`:1987`) and `ask_router` precondition layer (`:514-579` / `:537-557` / `:558-579`).
- [ ] Fix the boundary seam: `mailbot_api/main.py` `_raise_router_error_if_failed` (`:712-724`) and the text-path block (`:617-627`) must **render a sensitivity refusal as a graceful message** (200-shape OpenAI completion whose content is the four-beat prose) instead of `raise HTTPException(502)`. Non-sensitivity errors (provider failure, timeout) keep their existing 502 behavior — only the sensitivity refusal codes (`SENSITIVITY_BLOCKS_API`, `SENSITIVITY_NOT_CLASSIFIED`, `NEEDS_SENSITIVITY_CONFIRMATION`, `NEEDS_USER_CONFIRMATION`) route to the graceful render.
- [ ] **GREEN + REFACTOR.**

### Task 3 — Three four-beat message shapes (AC: 3)
- [ ] **RED:** tests pinning the exact four-beat structure per classification (name state → consequence → the one action that works → expectations) and the offer rules:
  - **sensitive:** offers "yes, escalate" — wording per retro §8.5 ("⚠️ That email is classified sensitive… reply **'yes, escalate'** (authorizes this one email, this one task, 10 minutes).").
  - **confidential:** offers NO escalation ("🔒 Classified confidential. No cloud override exists — by design. Read it in Outlook.").
  - **not-yet-classified:** does NOT suggest `mailbot rederive` ("⏳ Not sensitivity-classified yet. The ingest worker does this automatically within minutes — try again shortly.").
- [ ] Implement the message builder (pure function: `(classification, task, reason) → user_facing_guidance` four-beat string). No internal id, no trace, no dead-end instruction.
- [ ] Assert the not-yet-classified message contains **no** `rederive` token (guard against re-introducing the F-10-6-3 dead-end until 10-5-4 ships).
- [ ] **GREEN + REFACTOR.**

### Task 4 — Genuine sensitive-escalation path: user-confirmed, session-bound, attaches, no brick (AC: 4, code portion)
- [ ] **RED:** integration test booting the real router path proving: (a) with a valid user-confirmation record + minted token, a sensitive email escalation **attaches and dispatches** through the same identity the chat path uses (not a divergent MCP-session identity — the F-10-5-7 root cause); (b) a failed/absent escalation does **NOT** poison subsequent turns (no session brick) — a later unrelated turn on a normal email succeeds.
- [ ] Fix the session-binding mismatch (F-10-5-7): the token/confirmation must be keyed to an identity that is **stable across the mint→dispatch hop on the chat path** (the walk showed grants mint on MCP-session identity but chat dispatch carries a different one). Decide the correct binding key at dev time (e.g. bind to email_id + task_type + user-confirmation record rather than a session id that diverges) and record it.
- [ ] Remove the session-brick behavior: a sensitivity refusal must be a **per-request** errors-as-data refusal (Task 2 already makes it so), not a state that persists and refuses every later turn.
- [ ] **GREEN + REFACTOR.** (The live end-to-end walk itself is Task 5 — Adam-hands-on.)

### Task 5 — Adam-hands-on: Hermes skill-file hardening verification + live sensitive-escalation walk (AC: 2 live, AC: 4 live) — HALT
- [ ] **HALT to review here.** Tasks 1–4 (code + tests + MANDATORY-CR) are dev-story/autonomous-story-run compatible. Task 5 is **Adam-hands-on** and is NOT executed autonomously. Dev/autonomous agents flip the story to `review` and log to `epic-10-5-run-flags.md`.
- [ ] **AC-2 live:** author the Hermes-side hardening (restrict the `file`/`skills` write toolsets for the Discord gateway session in `hermes-config/config.yaml`, and/or make the `hermes-config/skills/mailbot/` bind-mount `:ro`); Adam verifies a `skill_manage patch` / `write_file` against `hermes-config/skills/mailbot/SKILL.md` is **rejected** at runtime.
- [ ] **AC-4 live:** real stack + real Discord + one real sensitive email → refusal envelope renders the four-beat sensitive message → Adam replies "yes, escalate" → user-confirmation record created → token attaches → draft/summary dispatches (small real Anthropic/Opus spend, recorded against pre-flight estimate, Console-sourced per `feedback_anthropic_spend_source_of_truth.md`) → confirm NO session brick (a later normal-email turn succeeds). Evidence → `10-5-2-walk-evidence.md`.

### Task 6 — MANDATORY-CR (AC: 5)
- [ ] Reviewer model ≠ dev model (dev = opus-4-8 this run → reviewer = sonnet-5). Full scope: authorization/token-mint seam is load-bearing + security-adjacent. Apply security + correctness findings; document deferrals.

### Task 7 — Gates
- [ ] ruff check (mailbot_api / tests / scripts) clean (pre-existing untracked `scratch/` T201 out of scope).
- [ ] mypy --strict clean.
- [ ] check_boundaries.py clean (audit rows via Rule-C writer; no new raw SQL outside `queries.py`).
- [ ] pytest full suite green; record +N net vs baseline 1728+2+3 (10-5-1's post-walk suite count — confirm actual baseline at dev time via `git` / a clean run).

### Review Findings (MANDATORY-CR, reviewer sonnet-5 ≠ dev opus-4-8, 2026-07-10)

Three parallel adversarial layers (Blind Hunter — diff only; Edge Case Hunter — diff + project read access; Acceptance Auditor — diff + spec + Dev Notes) reviewed the full working-tree diff (~2100 lines incl. new files). Findings below are deduplicated/triaged across all three layers; several converged independently, which raises confidence.

**Pre-review §4 escalated item — resolved: fix-now.** The `ask_router` sensitive-no-token refusal path not calling `record_pending_sensitive_refusal` is confirmed present in the diff (router.py, `ask_router` precondition layer around the `SENSITIVITY_BLOCKS_API`/sensitive branch). Rationale for fix-now rather than defer: the envelope's `user_facing_guidance` for `classification="sensitive"` unconditionally offers "yes, escalate" regardless of which code path produced the refusal (`build_guidance` has no path-awareness) — so the message is a live, load-bearing promise on this path too, not a dead branch. AC-4's own text is "a message may only offer actions that actually work"; today it doesn't on this path. Auditor layer found the live blast radius is currently narrowed (no production caller reaches `ask_router` with a real `email_id` yet — `handle_draft_reply` unwired, `main.py`'s direct `ask_router` call passes no `email_id`), but this is fragile/incidental, not a designed guarantee, and Task Item 2 below found a second, more clearly live instance of the same root cause inside `dispatch_tool_call` itself. Fixing both call sites now (same helper, same call shape as the already-correct sibling branch) is low-risk and closes the gap for good rather than leaving a latent trap for the next surface that wires `ask_router` with a real `email_id`.

- [ ] [Review][Patch] `ask_router`'s sensitive-no-token and `NEEDS_SENSITIVITY_CONFIRMATION` refusal branches never call `record_pending_sensitive_refusal`, unlike `dispatch_tool_call`'s equivalent branch [mailbot_api/router/router.py: `ask_router` precondition layer, ~:580-600 and ~:610-635] — a "yes, escalate" reply on this path finds no pending row (`confirm_pending_escalation` returns `None`) and silently no-ops with no user feedback, even though the rendered message promises escalation works. Pre-review §4 escalated this; resolved fix-now (see rationale above).
- [ ] [Review][Patch] `dispatch_tool_call`'s invalid/expired/mismatched-token branch (`NEEDS_SENSITIVITY_CONFIRMATION`, ~router.py:2043-2056) also builds a `classification="sensitive"` envelope (which always offers "yes, escalate") but never calls `record_pending_sensitive_refusal` — only the sibling "no token supplied at all" branch (~router.py:1985-1997) does. Same dead-end-promise failure mode as the item above, same fix shape.
- [ ] [Review][Patch] `record_grant_confirmation` (the only writer of `scope='grant'` confirmation rows) has zero production callers — `main.py`'s chat-boundary wiring only detects the sensitivity-escalation phrase (`is_escalation_confirmation` / `_confirm_escalation`), with no equivalent phrase-detection or call for grant approval. Since `mint_grant` (`mailbot_api/actions/authorization.py:169`) now unconditionally requires and consumes a grant confirmation that nothing in production can ever create, every Tier-2 grant mint is now permanently blocked rather than merely user-gated — a functional regression beyond AC-1's intent (AC-1 asks for user-gated, not user-impossible). `propose_action` still emits a `RecoveryAction` hint telling the agent to call `mint_grant`, which will now always fail with `NEEDS_USER_CONFIRMATION`.
- [ ] [Review][Patch] Grant confirmation is scoped to `action_type` only, not `email_ids` — `consume_grant_confirmation` / `USER_CONFIRMATION_FIND_GRANT` (`mailbot_api/db/queries.py:140-144`) filter on `scope='grant' AND action_type = ?` only; the `email_ids` JSON stored by `record_grant_confirmation` is never read back or compared. Once grant confirmation is wired to production (see item above), a user's "yes" to archive 2 specific emails would authorize `mint_grant` for an agent-chosen batch of up to `MAX_BATCH_SIZE` different emails of the same `action_type` — the blast radius (which/how many emails) remains agent-controlled, defeating the story's own "non-agent-assertable" goal for that dimension.
- [ ] [Review][Patch] `pending_sensitive_refusal` is keyed only by `caller_origin` (PK, one row per caller; `PENDING_SENSITIVE_REFUSAL_UPSERT` does `ON CONFLICT(caller_origin) DO UPDATE`) — a second sensitive refusal (different email) from the same caller before the first is confirmed silently overwrites the pending state, so a "yes, escalate" intended for email A instead escalates email B. No per-email/task disambiguation.
- [ ] [Review][Patch] `confirm_pending_escalation` has a read-then-write race: `fetchone(PENDING_SENSITIVE_REFUSAL_SELECT)` is a plain read outside the transaction that follows, then `record_sensitivity_confirmation` + `PENDING_SENSITIVE_REFUSAL_DELETE` are separate `execute_write` calls. Two near-simultaneous "yes, escalate" turns for the same `caller_origin` (e.g. a Discord double-send or client retry) can both observe the not-yet-deleted pending row and both proceed, minting two independent single-use confirmations from one user "yes."
- [ ] [Review][Patch] Task 1's "Emit an audit row on the refused-mint path" subtask (currently unchecked in Task 1 above) is genuinely unimplemented — neither `mint_sensitivity_token.py`'s nor `authorization.py`'s `NEEDS_USER_CONFIRMATION` refusal branch emits an audit row via the Rule-C writer. Completion Notes claims "AC-1: DONE" without flagging this gap; the story's own checklist already correctly leaves it unchecked. Flagging so it isn't lost at story close-out.
- [ ] [Review][Decision] `caller_origin` (the correlation key for `pending_sensitive_refusal` / the AC-4 fix) is sourced directly from the client-supplied `X-Mailbot-Caller-Origin` header with no authentication, signature, or allowlist check (`mailbot_api/main.py:537`). This is a pre-existing trust pattern in the codebase (used elsewhere for pause/audit correlation), but this story is the first to make it a security-relevant correlation key for an authorization escalation — any caller can set the header to another caller's origin value and consume that caller's pending refusal, or omit the header entirely and collide with every other header-omitting caller on the shared default `"unknown-external"`. Needs an explicit call: is `X-Mailbot-Caller-Origin` trusted infrastructure-side (e.g. stamped by an internal proxy, not client-settable in the real deployment topology), in which case this is fine and should be documented as such — or does it need a stronger identity source before AC-4's live walk (Task 5)? Cannot be patched unambiguously without knowing the deployment trust boundary.
- [ ] [Review][Defer] `_consume`'s `ORDER BY id DESC LIMIT 1` find-then-atomic-consume can let two concurrent mint calls each independently find and consume a *different* row if more than one matching un-consumed confirmation exists for the same scope (e.g. two escalation confirmations queued back-to-back) — pre-existing-shape TOCTOU already accepted-with-rationale in the pre-review self-audit (§3) for the single-row case; this generalizes it to the multi-row case. Low real-world likelihood (requires two confirmations + concurrent mints); deferred as a hardening item rather than a story blocker.
- [ ] [Review][Defer] `is_escalation_confirmation`'s punctuation stripping (`.strip(".!")`) misses `?`, trailing commas, and quote marks — "yes, escalate?" or "\"yes, escalate\"" silently fail to match, leaving the user believing they confirmed with no error feedback. UX polish, not a security or correctness gap; defer.
- [ ] [Review][Defer] `_sensitivity_refusal_completion` / `_plain_text_completion_sse_chunks` use `id(raw_request)` (CPython object memory address) as the synthetic `chatcmpl-mailbot-...` completion id, which can collide across requests once objects are GC'd — matches the pre-existing pattern already used elsewhere in `main.py` (e.g. the non-tools success path at ~main.py:676) for the same purpose, so not a regression introduced by this story; cosmetic, defer.
- [ ] [Review][Defer] The non-tools (`ask_router`/`hermes_aux`) chat-completions path does not branch on `request.stream` at all (success or refusal) — always returns a plain JSON dict. Pre-existing gap predating this story (Dev Notes/F13 comment: "text-only path continues to ignore [stream], no use case has driven streaming for aux tasks"); the story's refusal-render code correctly mirrors the path's existing non-streaming behavior rather than introducing a new inconsistency. Defer — fix belongs to whichever story first drives streaming need on this path.
- [ ] [Review][Defer] `RouterError.message` on the `SENSITIVITY_NOT_CLASSIFIED` branch (`router.py:1890`, `f"email {eid!r} sensitivity must be classified..."`) still interpolates the raw Graph id. Confirmed pre-existing at baseline commit 5b36987 (not introduced by this story). Not currently reachable to the user — `main.py`'s `_sensitivity_refusal_completion` only ever renders `envelope.user_facing_guidance`, never `.message` — but is a latent landmine if any future consumer logs or surfaces `.message` externally. Defer; consider a follow-up sweep of internal error `.message` strings for id-safety as a hardening pass, not scoped to this story.
- [ ] [Review][Dismiss] `email_ref_for`'s 8-hex-char SHA-256 prefix has a theoretical collision space (~4 billion); already identified and accepted-with-rationale in the pre-review self-audit (§3) as display-only/never-a-key. No new information changes that verdict.

### CR resolution (dev pass, 2026-07-10) — 7 Patches applied, 1 Decision deferred-to-Task-5, 5 Defers, 1 Dismiss

**Applied (7/7 Patches = 100%):**
- [x] **CR-1** — `ask_router` sensitive-no-token + `NEEDS_SENSITIVITY_CONFIRMATION` branches now call `record_pending_sensitive_refusal` (router.py). Parity with dispatch_tool_call — the "yes, escalate" offer is genuine on the ask_router path too.
- [x] **CR-2** — `dispatch_tool_call` `NEEDS_SENSITIVITY_CONFIRMATION` (invalid/expired-token) branch now records the pending refusal (router.py). Same fix shape.
- [x] **CR-3** — grant confirmation is now wired to production: new `pending_grant_approval` table + `record_pending_grant_approval`/`confirm_pending_grant` + `is_grant_approval` phrase detector + boundary wiring (`_record_pending_grant_approvals_from_messages` scans the transcript's `propose_action(<grant-requiring>)` tool calls; a user "yes"/"approve" confirms). Tier-2 grants are user-gated, no longer permanently blocked.
- [x] **CR-4** — grant confirmation is now email-scoped: `USER_CONFIRMATION_FIND_GRANT` matches `(action_type, canonical email_ids)`; `consume_grant_confirmation` takes `email_ids`; `record_grant_confirmation` stores `json.dumps(sorted(email_ids))`. A user "yes" to {e1,e2} does NOT authorize a mint for {e1,e3}. Blast radius is the user-approved set.
- [x] **CR-5** — documented as intentional last-refusal semantics (the user is responding to what they just saw); the upsert is by design. Comment added on `record_pending_sensitive_refusal`.
- [x] **CR-6** — `confirm_pending_escalation` + `confirm_pending_grant` now use atomic `DELETE ... RETURNING` claims (`PENDING_SENSITIVE_REFUSAL_CLAIM` / `PENDING_GRANT_APPROVAL_CLAIM`) so two concurrent "yes" turns can't both mint from one user approval.
- [x] **CR-7** — refused-mint paths (`NEEDS_USER_CONFIRMATION` in both mint verbs) now emit a structured audit log event (`sensitivity.token.mint_refused` / `action.grant.mint_refused`); Task 1's audit subtask discharged; Completion Notes corrected (was over-claimed).

**Decision — deferred to Task 5 (Adam-hands-on):**
- [ ] **CR-8** — `caller_origin` (from the unauthenticated `X-Mailbot-Caller-Origin` header) is now a security-relevant correlation key. **This is a deployment-trust question for Adam at the Task 5 live walk:** is the header stamped by the internal Hermes→mailbot-api proxy (trusted, not client-settable in the real topology) or does it need a stronger identity source? Documented for the walk; the header is a pre-existing trust pattern (pause/audit correlation) that this story is the first to make authorization-relevant. Fail-safe: worst case a mis-set header lets a caller consume their OWN colliding default `unknown-external` pending row — never an over-authorization beyond a single user-approved (email,task) or (action,email-set).

**Deferred (5, all reasonable — pre-existing patterns / UX polish):** multi-row `_consume` TOCTOU (low likelihood); escalation phrase punctuation edge (`?`/quotes — partially addressed: `_normalize_phrase` now strips `?"'` too); `id(raw_request)` completion id (pre-existing pattern); non-tools path no stream branch (pre-existing); `RouterError.message` id interpolation on SENSITIVITY_NOT_CLASSIFIED (pre-existing at baseline, not user-reachable — the render only ever uses `user_facing_guidance`).

**Dismissed (1):** email_ref 8-hex collision — display-only, accepted in pre-review §3.

Gates re-green post-CR: ruff clean, mypy --strict clean (131 files), boundaries clean, full suite green (see run-flags for count).

## Dev Notes

### Technical requirements
- Stack: Python 3.12, FastAPI, SQLite (WAL), Pydantic v2, pytest + pytest-asyncio. Test runner: `.venv/Scripts/python.exe -m pytest`. Lint: `ruff`; types: `mypy --strict`; boundary: `scripts/check_boundaries.py`.
- **AR-PAT-4 (errors-as-data)** is the governing pattern (epics.md:251): verbs/Router never raise to the agent; refusals are models with an optional `error` field. The bug this story fixes is that a correct errors-as-data refusal is re-thrown as `HTTPException(502)` at the `main.py` chat boundary — carry it as data all the way to the render.

### Exact code seams (verified against source this story)
- **Sensitivity token mint (self-mint gap, F-10-5-5):** `mailbot_api/verbs/mint_sensitivity_token.py:53-116` (mints unconditionally at `:100` on `"sensitive"` label). Registry: `mailbot_api/actions/sensitivity_tokens.py:69-121` (`mint`/`consume`, in-memory `_REGISTRY`, 10-min TTL, AR-D12-1 dies-on-restart invariant — DO NOT persist).
- **Grant mint (self-mint gap, F-10-5-8):** `mailbot_api/actions/authorization.py:96-201` (`mint_grant`; structural gates only, no user-consent). Promotion `PENDING_GRANT_PROMOTE_FOR_ACTION_TYPE` = `mailbot_api/db/queries.py:829-832` (filters by `action_type` only). Propose queues `pending_grant` without consulting grants: `mailbot_api/actions/propose.py:281-282`, emits a `mint_grant` RecoveryAction hint at `:337-363`.
- **Verb dispatch surface:** `mailbot_api/mcp_server.py` — all agent-callable tools in the dispatch dict (`:854-888`); `mint_grant` registered `:861`, `mint_sensitivity_token` `:865`. No agent-vs-user distinction enforced in code today (only advisory instruction text `:1163-1176`). `ask_router` is deliberately NOT MCP-exposed (`:50-56`).
- **Router refusal sites (errors-as-data, in-process):** `dispatch_tool_call` precondition layer `router.py:1879-1996` (`SENSITIVITY_NOT_CLASSIFIED` `:1882`, `SENSITIVITY_BLOCKS_API` confidential `:1912`, sensitive-no-token `:1951`, `NEEDS_SENSITIVITY_CONFIRMATION` `:1987`); `ask_router` precondition layer `router.py:514-579`. Refusal audit helper `_emit_sensitivity_refusal_audit_row` (`router.py:202`).
- **The 502 seam (F-10-5-6):** `mailbot_api/main.py` `_raise_router_error_if_failed:712-724` (tool-call path) and the text-path block `:617-627` — both collapse every non-ok result into HTTP-502, discarding the structured `ErrorCode`. This is where the graceful render must replace the raise for sensitivity codes.
- **Error shapes:** `mailbot_api/router/errors.py` — `ErrorCode` enum `:40-63` (relevant: `SENSITIVITY_BLOCKS_API`/`NEEDS_SENSITIVITY_CONFIRMATION`/`SENSITIVITY_NOT_CLASSIFIED` `:57-59`); `RouterError` `:66-72`; `RouterResult` `:75-106`; `ToolCallResult` `:191-222`; `sanitize_error()` `:225-265`.
- **Envelope shape to reuse:** `RecoveryAction` `mailbot_api/actions/recovery_action.py:27-70` — frozen `{tool_name, args_hint, user_facing_guidance}`. Produced in `verbs/propose_action.py:89-101` + `actions/propose.py:337-363`; carried on `<Verb>Out.recovery_action`; rendered to prose per "Rule S" (`hermes-config/AGENTS.md:277-318`; SKILL.md `hermes-config/skills/mailbot/SKILL.md:485-582`).

### Skill-file boundary note (AC-2 — F-10-5-12 lives OUTSIDE mailbot_api)
The self-edit vector is entirely Hermes-side: the `file` / `skills` write toolsets (`hermes-config/skills/autonomous-ai-agents/hermes-agent/SKILL.md:404-437`) acting on the RW bind-mount of `hermes-config/skills/mailbot/**` (bind-mount documented `hermes-config/config.yaml:1-6`). `mailbot_api/` has **no** file-write verb over skill files (the only runtime file write in the verb surface is `set_model_persistent` writing `router/policy.user-overrides.yaml` — a different surface). Therefore AC-2 **cannot** be honestly satisfied by `mailbot_api/` code; it is a Hermes `config.yaml` toolset restriction and/or `:ro` bind-mount. This story authors that config change and defers its live verification to Task 5 (Adam-hands-on). Do NOT fabricate a `mailbot_api`-side "fix" for F-10-5-12 — that would be the exact persona-prose-pretending-to-be-enforcement failure this epic exists to end.

### Run-mode binding (HYBRID)
- **Tasks 1–4 + 6 + 7 (code + tests + MANDATORY-CR + gates)** ARE dev-story / autonomous-story-run compatible.
- **Task 5 (Hermes skill-file hardening live verification + live sensitive-escalation walk)** is **Adam-hands-on** — real stack, real Discord, small real Opus spend. Dev/autonomous agents HALT at Task 5, flip to `review`, log to `epic-10-5-run-flags.md`. Pattern mirrors 10-5-1 Task 5.

### Sequencing constraint
- not-yet-classified refusal must NOT offer `mailbot rederive` (crashes until 10-5-4, F-10-6-3). 10-5-2 depends on nothing else (epics.md:4037) but should precede 10-5-6 (its `user_facing_guidance` field is 10-5-6's delivery vehicle for canonical control-phrases).

### Testing requirements
- Unit tests for the message builder (pure function, three shapes, no-id / no-rederive guards).
- Integration tests booting the real router + real SQLite for the mint-refusal gate (Task 1) and the escalation attach / no-brick behavior (Task 4) — per the Middleware-Real-Bootstrap gate (§2.4.7): the token-mint + escalation seam is a state-changing authorization path and MUST be exercised against the real router + real DB, not a mocked `ask_router`.
- Endpoint test via `TestClient(app)` asserting `/v1/chat/completions` returns a graceful 200-shape refusal (not 502) for a sensitivity-blocked request, with no Graph id in the body.

### References
- `_bmad-output/planning-artifacts/epics.md` § Story 10.5.2 (`:4104-4136`); Epic 10.5 Detail (`:4020-4070`); AR-PAT-4 (`:251`).
- `_bmad-output/implementation-artifacts/epic-10-retro-2026-07-07.md` §8.5 (B7 envelope design, `:123-141`), §6 (authorization-at-API-layer principle).
- `_bmad-output/implementation-artifacts/10-5-walk-evidence.md` (F-10-5-5/6/7/8/12 evidence, `:261-266`, `:342-349`).
- `_bmad-output/implementation-artifacts/epic-10-5-run-flags.md` § Story 10-5-1 (audit-row + authoritative-read + allowlist patterns; MANDATORY-CR sonnet-5 ≠ opus-4-8).
- Code seams: enumerated above under "Exact code seams".

## Dev Agent Record

### Agent Model Used

claude-opus-4-8[1m] (dev, autonomous-story-run). Review model: claude-sonnet-5 (MANDATORY-CR, Task 6, reviewer ≠ dev).

### Debug Log

- **AC-2 (F-10-5-12) is honestly out of `mailbot_api` code scope.** The seam map proved the skill-file self-edit vector is entirely Hermes-side (`file`/`skills` write toolsets on the RW bind-mount `hermes-config/skills/mailbot/**`); `mailbot_api/` has no file-write verb over skill files. The Hermes-config hardening + its live verification are deferred to Task 5 (Adam-hands-on). No `mailbot_api` "fix" was fabricated — that would reproduce the persona-prose-pretending-to-be-enforcement failure this epic exists to end.
- **User-confirmation primitive design (Task 1):** the invariant "not agent-assertable" is realized by making the confirmation record creatable ONLY at the `/v1/chat/completions` boundary from a genuine **user-role** message. The MCP tool-call surface (where agents live) has no path to `record_*_confirmation`. The mint verbs consume single-use.
- **F-10-5-7 session-binding fix (Task 4):** the confirmation is keyed on `(email_id, task_type)` and the pending-refusal correlation on `caller_origin` — NEITHER uses a session id. That divergent-session-identity binding WAS the F-10-5-7 bug; removing session identity from the key fixes it by construction. No-brick comes from Task 2 making refusals per-request errors-as-data (not persistent session state).
- **Contract change ripple:** requiring a confirmation broke 32 pre-existing tests that minted without one (correct — they predated the gate). Fixed by seeding a confirmation before each setup-mint (inline where few sites; a per-file autouse `mint_grant` wrapper where many). The gate itself is covered by the dedicated new test files.
- Boundary escalation-detection is gated behind `is_escalation_confirmation` (deterministic exact-phrase) so non-confirmation turns incur no extra DB read.

### Completion Notes List

- **AC-1 (no agent self-mint):** DONE. New `user_confirmations` table (migration 026) + `actions/user_confirmation.py` primitive; `mint_sensitivity_token` and `mint_grant` now refuse `NEEDS_USER_CONFIRMATION` unless a genuine user-gated confirmation exists (consumed single-use). Refused-mint paths emit a structured audit log event (CR-7). Grants are user-gated via the CR-3 `pending_grant_approval` boundary handshake (email-scoped per CR-4), not permanently blocked. Proven by `test_mint_requires_user_confirmation.py` (8) + the grant-handshake tests in `test_sensitive_escalation_handshake.py` (CR-3/CR-4/CR-6).
- **AC-2 (skill-file non-writable):** CODE-side N/A in `mailbot_api` (boundary-honest — see Debug Log); Hermes-config hardening + live reject-verification are Task 5 (Adam-hands-on). Flagged in run-flags.
- **AC-3 (refusal envelope, no 502, no id leak):** DONE. Typed `SensitivityRefusal` envelope on `RouterError.refusal_envelope`; populated at all 7 router refusal sites (`ask_router` ×4, `dispatch_tool_call` ×4 minus shared); `/v1/chat/completions` renders sensitivity refusals as graceful 200s (four-beat message) instead of HTTP-502; Graph id structurally unprintable (`email_ref` is a one-way hash). Proven by `test_sensitivity_refusal_envelope.py` (9) + `test_sensitivity_refusal_envelope_boundary.py` (4). Three message shapes (sensitive offers escalate / confidential offers none / not-classified never suggests rederive) pinned.
- **AC-4 (genuine escalation, code portion):** DONE. `pending_sensitive_refusal` correlation (keyed by caller_origin, not session) + `confirm_pending_escalation` turns a real user "yes, escalate" into a single-use confirmation for (email, task); mint that previously refused now succeeds. No-brick verified. Proven by `test_sensitive_escalation_handshake.py` (13). **Live end-to-end walk = Task 5 (Adam-hands-on).**
- **AC-5 (MANDATORY-CR):** pending Task 6 (reviewer sonnet-5 ≠ dev opus-4-8).
- **Gates:** ruff clean; mypy --strict clean (131 files, +2 new modules); check_boundaries.py clean; pytest full suite green (see run-flags for net count).
- **Task 5 HALT:** Adam-hands-on — Hermes skill-file hardening live-verify (AC-2) + live sensitive-escalation walk (AC-4, small real Opus spend). Story flipped to `review`.

### File List

Source:
- `mailbot_api/db/migrations/026_user_confirmations.sql` (new) — user_confirmations + pending_sensitive_refusal + pending_grant_approval tables
- `mailbot_api/actions/user_confirmation.py` (new) — confirmation record/consume primitive + escalation correlation
- `mailbot_api/router/sensitivity_refusal.py` (new) — SensitivityRefusal envelope + four-beat message builder
- `mailbot_api/db/queries.py` — user_confirmation + pending_sensitive_refusal SQL constants
- `mailbot_api/router/errors.py` — `RouterError.refusal_envelope` field + import
- `mailbot_api/router/router.py` — populate envelope at refusal sites + record pending sensitive refusal
- `mailbot_api/verbs/mint_sensitivity_token.py` — NEEDS_USER_CONFIRMATION gate
- `mailbot_api/actions/authorization.py` — NEEDS_USER_CONFIRMATION gate on mint_grant
- `mailbot_api/main.py` — graceful sensitivity-refusal render (200 not 502) + SSE variant + boundary escalation-confirmation detection

Docs / infra:
- `docs/DATABASE.md` — schema-doc entries for user_confirmations + pending_sensitive_refusal + pending_grant_approval + escalation_armed (§5.2.1 pre-review gate)
- `docker-compose.yml` — AC-2 fix: nested `:ro` bind-mount on `hermes-config/skills/mailbot` (F-10-5-12 closure)

Live-walk fix (F-10-5-2-W1):
- `mailbot_api/db/migrations/027_escalation_armed.sql` (new) — escalation_armed singleton (ordering-independent escalation arm)
- (arm/consume helpers added to `mailbot_api/actions/user_confirmation.py`; boundary arm-on-yes-escalate in `mailbot_api/main.py`; arm-consume in `mailbot_api/verbs/mint_sensitivity_token.py`)

Walk evidence:
- `_bmad-output/implementation-artifacts/10-5-2-walk-evidence.md`

Tests (new):
- `tests/unit/router/test_sensitivity_refusal_envelope.py`
- `tests/integration/test_sensitivity_refusal_envelope_boundary.py`
- `tests/integration/test_mint_requires_user_confirmation.py`
- `tests/integration/test_sensitive_escalation_handshake.py`

Tests (updated for the new confirmation contract — seed a confirmation before setup-mints):
- `tests/unit/actions/test_authorization.py`, `test_drainer.py`, `test_drainer_send_cap.py`, `test_replay.py`, `test_sensitivity_tokens.py`
- `tests/integration/test_pending_grant_promotion_lifecycle.py`, `test_worker_drainer_wiring.py`, `test_mcp_server.py`, `test_router_sensitivity_handshake.py`, `test_actions_delete_sensitivity_handshake.py`

### Change Log

- 2026-07-10 — Story 10.5.2 Tasks 1-4 + 7 (code + tests + gates) shipped: API-layer user-confirmation primitive makes token/grant minting non-agent-assertable (F-10-5-5/F-10-5-8); structured sensitivity-refusal envelope rendered gracefully at the Discord boundary with no id leak and no 502 (F-10-5-6); genuine session-independent sensitive-escalation handshake (F-10-5-7). AC-2 (F-10-5-12) + AC-4 live walk deferred to Task 5 (Adam-hands-on). Story → review pending MANDATORY-CR (Task 6).

## Phase 3.5 — Live Walk Verdicts (Adam-signed 2026-07-10)

Full evidence: `10-5-2-walk-evidence.md`. Real stack (rebuilt image ed18774792db
+ arm-fix), real Discord, real Hermes agent.

- **AC-1 (no agent self-mint): PASS (live)** — agent's `mint_sensitivity_token`
  refused `NEEDS_USER_CONFIRMATION` in Discord (self-mint attack blocked in code).
- **AC-2 (skill-file not agent-writable): PASS (live)** — `:ro` mount; agent's
  `skill_manage patch` rejected ("read-only filesystem"), SKILL.md byte-unchanged,
  no false-success narration.
- **AC-3 (refusal envelope, no 502, no id leak): PASS (live)** — real endpoint
  returned 200 four-beat message, Graph id not in body.
- **AC-4 (sensitive escalation): PASS at code-L3 (Adam-signed)** — API-layer
  contract proven on real infra (confirmation recorded on "yes, escalate"; mint
  against it returns ok=True). Live end-to-end dispatch BLOCKED by the persona
  layer (agent re-parrots the refusal template instead of re-dispatching) —
  filed **F-10-5-2-W2, owned by Story 10-5-6** (recognized-phrase dispatch).
- **AC-5 (MANDATORY-CR): PASS** — sonnet-5 ≠ opus-4-8, 7/7 Patches applied.

**Findings:** F-10-5-2-W1 (turn-ordering) FIXED in-session (migration 027 arm);
F-10-5-2-W2 (persona no-re-dispatch) FILED → 10-5-6; F-10-5-2-W3 (migration-edit-
after-apply) process finding recorded; CR-8 (caller_origin=unknown-external)
live-confirmed, sidestepped by the singleton arm, standing decision documented.

**Done at L3** on AC-1/AC-2/AC-3 live + AC-4 code-L3 (Adam "Sign all — flip to
done", 2026-07-10). Suite 1779+2+3. Staged, not committed.
