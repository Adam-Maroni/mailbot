---
baseline_commit: 71eb6d715bddd57bbf9c0a94d73e8a2a142990ae
---

# Story 10.5: Happy-path README perimeter walks — write + slash family

Status: done (walk executed 2026-07-06 hybrid Adam-hands-on; 10 PASS / 6 FAIL / 0 EXCLUDED; Phase 3.5 Adam-DELEGATED verification PASS WITH FINDINGS — all 5 AC verdicts signed on live-captured evidence + offline AC-4/AC-5 re-derive, Docker-down at verify time so AC-1/2/3 rest on walk-captured rows + Adam's Console/Gmail/Outlook confirmations; 12 findings F-10-5-1..12 FILED per N.5, zero fixed)

<!--
Walk story, Epic 10 README-as-charter UAT. NOT an implementation story: it produces walk
evidence (real captured chat output per README write/slash example) + same-commit README
verified-tag updates per doc-drift rule (a), and defect FILINGS per N.5 — not code.

RUN-MODE BINDING (HYBRID, Adam-chosen "Hybrid hands-on now" in-session 2026-07-06): the
epics.md binding pins this story NOT compatible with pure /autonomous-story-run — it is the
epic's ONLY real-spend story (~$2-4 Anthropic, draft_reply is Opus), it performs a REAL SEND
and REAL Tier-2 mailbox writes, and every chat turn runs through Adam's Discord client.
Resolution mirrors 10-4 Run 1: Adam types each case's message in Discord and pastes MailBot's
reply back; Adam authorizes spend and reads Console truth; the orchestrator (dev model)
drives the case list, captures DB-side provenance read-only (router_calls watermarks,
mode=ro), asserts hard-assert facts, composes evidence, and applies README doc-drift edits.
Dev agents do NOT halt at the walk — they orchestrate it conversationally with Adam
in-session (10-4 pattern).

SPEND CONTRACT (AC-3): pre-flight estimate ~$2-4 real Anthropic. Adam reads the Anthropic
Console BEFORE the first spend-bearing case (baseline) and AFTER the last one (delta);
Console is the SOLE spend truth per durable memory feedback_anthropic_spend_source_of_truth.md
— local estimator figures are recorded as estimator-only, never as truth. Epic 9.5 retro A2
cost-truth fixes shipped (verified per-model pricing), but the Console-as-truth rule stands.

Scope fence (N.5 policy): findings are FILED with evidence, never fixed here. The ONLY
non-evidence file this story edits is README.md (doc-drift rule (a) is an explicit AC).
Any code/config/prompt change escalates CR per §5.12. NOTE the /model-persistent case
writes router/policy.user-overrides.yaml THROUGH THE PRODUCT SURFACE — that is product
behavior under test, not a repo edit; the case protocol must plan state restoration.
-->

## Story

As Adam,
I want every write-family and slash-family example documented in the README walked against the live local stack in a hands-on session,
So that the perimeter's authorization, cooling-off, sensitivity, and operator-control claims are evidence-backed under real conditions — including the real-spend draft/send path.

## Acceptance Criteria

**AC-1 — Write-family walks executed with evidence**
**Given** the README's write-family examples
**When** the write walks fire
**Then** the following are executed as walk cases with evidence captured in `10-5-walk-evidence.md`: draft→refine→send with cooling-off + `/cancel`; Tier-2 batch archive with scoped grant; sensitive `/confirm` escalation; confidential refusal (no body leak, standard refusal surfaced)

**AC-2 — Slash-family walks executed per documented examples**
**Given** the README's slash-command table (12 commands)
**When** the slash walks fire
**Then** the `/model` family + `/spend` + `/pause` + `/resume` + `/budget reset` + `/mute` + `/unmute` are each walked per their documented examples

**AC-3 — Real spend recorded, Console as truth**
**Given** this story consumes real Anthropic budget
**When** the session completes
**Then** actual spend is recorded against the ~$2-4 pre-flight estimate, with spend truth read from the Anthropic Console per durable memory `feedback_anthropic_spend_source_of_truth.md` — never local placeholder estimates

**AC-4 — Doc-drift rules (a) + (b)**
**Given** doc-drift rules (a) + (b)
**When** each case closes
**Then** hard-assert on command names + error codes, soft-assert on prose; README examples updated with real captured output + `<!-- verified 10-5, run_id ... -->` tags same story, same commit; per-case verdicts feed Story 10.7's table

**AC-5 — CR cadence**
**Given** this is a walk story
**When** CR cadence is evaluated per the 6 criteria
**Then** zero criteria fire → CR skipped per cadence binding; discovered defects are FILED per N.5 policy

### AC interpretation pins (code-reality; read before executing)

- **AC-1's four write cases map to README anchors:** W1 draft→refine→send+cooling-off+`/cancel` (README:69-107 fenced example — walked as TWO sub-cases: W1a a send that is `/cancel`led during cooling-off, W1b a send allowed to complete; both against an Adam-owned recipient address, never a third party); W2 Tier-2 batch archive w/ scoped grant (README:120-130); W3 sensitive `/confirm` escalation (README:169-177); W4 confidential refusal (README:179-184). W2 archives REAL emails — pick a batch Adam is willing to archive (archive is not auto-revertible; Tier-2 pre_state is audit-only per 10-2). W3/W4 need live emails already classified `sensitive`/`confidential` — verify candidates exist in the DB at case-freeze; if none exist for a class, that sub-case is EXCLUDED-with-reason (never reclassify data to fabricate a pass).
- **AC-2's "each walked per their documented examples":** 7 command groups = 9 cases: S1 `/model` (table), S2 `/model <model>` one-shot, S3 `/model <task> <model>` persistent (+ restoration step returning the override to its pre-walk state — restoration is part of the case protocol, not a fix), S4 `/spend`, S5 `/pause` (+ documented `⏸` ack), S6 `/resume`, S7 `/budget reset`, S8 `/mute <category>`, S9 `/unmute <category>`. `/cost` appears in the README table but is NOT in AC-2's list — walk it opportunistically if cheap, else record honest-count note (10-4 precedent: the case list is what the AC pins, don't fabricate). `/cancel` is exercised inside W1a; `/confirm` inside W3.
- **Known-landmine pins (from 10-1/10-3/10-4 evidence, frozen BEFORE walking):** (1) 10-1 F1 — router pause also blocks Hermes chat (`hermes_aux` → PAUSED, 3×502 raw in Discord): S5's documented `⏸ Router paused` ack may be unable to surface, and S6's `/resume` turn may itself fail while paused; the case protocol must plan the observation channel (e.g., `mailbot status` ROUTER section read-only) and an unpause fallback via CLI `mailbot resume`. A FAIL here corroborates FILED F1, it does not re-file it. (2) 10-1 F4 — pause does NOT gate the worker drainer; no reliance on pause as a safety net during W2. (3) Degraded mode is NOT active (exited 2026-07-06T07:54:33Z, 10-4 precondition); S7 `/budget reset` therefore exercises the not-degraded path — expected honest outcome is a no-op/informational ack, captured as-is against the README's illustrative `Degraded mode cleared.`; re-trip mid-walk impossible (crossing-only Layer-3 entry, budget.py). (4) sends hard-cap 20/UTC-day — baseline `sends today` count captured at Task 0.
- **AC-4's "real captured output" vs privacy:** same sanitization default as 10-4 AC-3 pin (WALK-10-4-F1 lesson): README examples get real captured output with sender addresses + subjects + names masked to shape-preserving placeholders; structure/counts/tier language real. Evidence file follows Rule Q (subjects ≤60 chars truncated, sender domain class, NO full bodies). W1 drafts contain Adam-authored content — README version masks recipient + personal specifics.
- **run_id convention:** write cases produce action ids → `run_id action-N/2026-07-06` (10-1/10-2 convention). Slash cases produce no action id → `run_id 10-5-sN/2026-07-06` backed by router_calls id ranges (10-4 convention).
- **Verdict vocabulary:** PASS / FAIL / EXCLUDED-with-reason per case (10.7 table contract), PASS / PARTIAL-PASS / FAIL per AC section, Adam-signed at the Phase 3.5 gate.

## Tasks / Subtasks

- [x] **Task 0 — Preconditions + baseline capture (BLOCKING)** (AC: 1, 3)
  - [x] 0.1 `docker ps` all three containers healthy; `curl localhost:8000/health` ok; sync heartbeat fresh
  - [x] 0.2 Degraded-mode state read-only check (expect exited 07-06T07:54:33Z, still exited); router not paused; OAuth green
  - [x] 0.3 Baselines into evidence header: commit, router_calls watermark W0, sends-today count vs 20-cap, pending actions by tier, mute-state table, policy.user-overrides.yaml pre-walk content (for S3 restoration)
  - [x] 0.4 Sensitivity candidates read-only: counts + candidate email ids for `sensitive` and `confidential` classes (W3/W4 feasibility; EXCLUDED-with-reason if a class is empty)
  - [x] 0.5 **Adam reads Anthropic Console spend baseline** (AC-3 pre-figure, Console-as-truth)
- [x] **Task 1 — Case-list freeze (AC: 1, 2)**
  - [x] 1.1 Freeze the case table into evidence BEFORE walking: W1a/W1b/W2/W3/W4 + S1-S9 (+ optional /cost), with per-case README anchor lines, hard-asserts, and landmine notes
  - [x] 1.2 Freeze W1 recipient (Adam-owned address), W2 batch definition (which emails, expected count), W3/W4 subject emails (from 0.4)
- [x] **Task 2 — Slash-family walks S1-S9 (Adam-hands-on Discord)** (AC: 2)
  - [x] 2.1 Walk cheap/read-only slash cases first (S1, S4, S8, S9, S7); capture replies verbatim + provenance
  - [x] 2.2 S2 one-shot + S3 persistent override walked with audit-row capture (`slash_command:*:adam` model_chosen_reason); S3 restoration executed + verified
  - [x] 2.3 S5/S6 pause/resume walked LAST among slash cases (F1 landmine protocol: status read via CLI while paused; CLI `mailbot resume` fallback armed)
- [x] **Task 3 — Write-family walks W1-W4 (Adam-hands-on, real spend)** (AC: 1)
  - [x] 3.1 W4 confidential refusal (no spend, no writes) — assert refusal + zero body egress via router_calls
  - [x] 3.2 W3 sensitive `/confirm` escalation — token minted, single-use, task completes; audit rows captured
  - [x] 3.3 W2 Tier-2 batch archive — scoped grant minted in chat, N emails archived, grant scope asserted (N emails, that action); Outlook-verified by Adam
  - [x] 3.4 W1a draft→refine→propose→`/cancel` during cooling-off — cancel ack + no send dispatched (DB+log proven)
  - [x] 3.5 W1b draft→send→60s cooling-off→real dispatch — Adam verifies receipt at the recipient mailbox; sends-today counter increments
- [x] **Task 4 — Spend truth (AC: 3)**
  - [x] 4.1 **Adam reads Anthropic Console post-walk**; record delta vs ~$2-4 estimate + estimator figure side-by-side (estimator-only label)
- [x] **Task 5 — README doc-drift rule (a) edits** (AC: 4)
  - [x] 5.1 Write-family examples (README:69-185) updated with real sanitized captured output + `<!-- verified 10-5, run_id ... -->` tags; FAIL cases get honest currently-broken notes, no tag
  - [x] 5.2 Slash-table (README:192-207) example-output column updated to real captured outputs + tags for walked rows; README:19-rescope sentence updated again (write/slash now walked)
  - [x] 5.3 Error-table rows incidentally exercised (e.g., PAUSED, budget rows) get corroboration notes only — fault-injection stays 10-6 scope
- [x] **Task 6 — Findings FILED per N.5** (AC: 5)
  - [x] 6.1 F-10-5-N findings table in evidence, mirrored to `epic-10-run-flags.md`; zero fixes shipped
- [x] **Task 7 — Compose `10-5-walk-evidence.md`** (AC: 1, 2, 3, 4)
  - [x] 7.1 Session header w/ spend record + signature line, frozen case table, per-case blocks w/ provenance + cross-checks, findings table, verdict table, per-AC proposed verdicts
- [x] **Task 8 — CR determination, run-flags, gates, sprint flip, stage (never commit)** (AC: 5)
  - [x] 8.1 CR-cadence determination recorded (expect zero criteria — zero code)
  - [x] 8.2 Append § "Story 10-5 Run 1" to `epic-10-run-flags.md`; flag report to `story-run-flags.md`
  - [x] 8.3 Gates: ruff/mypy/boundaries/pytest expected byte-identical to baseline (docs-only)
  - [x] 8.4 sprint-status flip `review`; explicit-path staging; `done` on Adam-signed verdicts; nothing committed

## Dev Notes

### Run-mode decision record (this session, 2026-07-06)

Invoked as `autononomous story run 10-5`. Phase 0.4 blocker scan surfaced the story's hard RUN-MODE BINDING (NOT compatible with /autonomous-story-run — real spend, real sends, Adam's Discord). Adam chose **"Hybrid hands-on now"** (10-4 Run 1 pattern): Adam drives Discord + spend authorization + Console reads; orchestrator drives case protocol, read-only provenance, evidence, doc-drift.

### Write-path pipeline pins

- Draft chain: `draft_reply` is Opus policy; first draft to a NEW recipient costs an extra Opus tone-fingerprint call (cached 30 days) — README:107. Refine loop capped at 5 iterations (README:106).
- Send choreography: propose (Tier 3) → grant + confirmation → 60s cooling-off (`/cancel <action_id>` window) → drainer dispatch. Hard cap 20 sends/UTC-day (`daily_send_cap_exceeded`).
- Tier-2 archive: grant scoped to exactly the enumerated emails + action + expiry (README:130). Archive captures pre_state for audit but is NOT auto-revertible (10-2 limitation, README:368).
- Sensitivity: `sensitive` → `/confirm <email_id> <task>` or "yes, escalate" mints single-use 10-min token; `confidential` → no override, body never leaves machine (NFR-PRIV-2; 9.5.2 AC-3 verified the refusal at L3 — this walk re-confirms via the README's documented phrasing).

### Live-DB access pattern (unchanged from 10-3/10-4)

`docker compose exec -T mailbot-api python -c "import sqlite3, ...; sqlite3.connect('file:/data/mailbot.db?mode=ro', uri=True)"` — image has no sqlite3 CLI; live DB is the `mailbot_db` volume; MSYS_NO_PATHCONV=1 for bare path args (durable memory `ops_msys_path_mangling_docker_exec.md`).

### Known landmines this walk must respect

- **10-1 F1 (pause kills Hermes chat):** S5/S6 sequenced last among slash cases with a CLI fallback armed; observation of paused-state via `mailbot status` not chat.
- **10-1 F4 (pause doesn't gate the drainer):** never rely on pause to contain W2/W1b; containment = batch selection + recipient choice.
- **10-4 F-10-4-2 (transient 529s):** Hermes 3-attempt retry absorbs; failed-then-ok router rows are known noise, not findings.
- **W1 recipient is Adam-owned** — a real send to a third party is out of the question. New-recipient tone-fingerprint cost is expected spend, record it.
- **S3 persistent override mutates `router/policy.user-overrides.yaml` via the product surface** — capture pre-state at 0.3, restore at 2.2, verify restored. The file is runtime config (bind-mounted), not a repo edit.
- **`/budget reset` walks the not-degraded path** (degraded exited 07-06); honest capture vs illustrative README output — the degraded-path reset was already exercised as the 10-4 precondition (operator verb, not slash), cross-reference it.

### Project Structure Notes

Files this story may touch — and ONLY these: `README.md` (doc-drift rule (a) — explicit AC), `_bmad-output/implementation-artifacts/10-5-walk-evidence.md` (new), `epic-10-run-flags.md` (append), `sprint-status.yaml` (flips), this story file, `story-run-flags.md` (run report). ZERO changes under `mailbot_api/`, `scripts/`, `router/` (repo copy), `hermes-config/`, `docker/`, `tests/`. Runtime `policy.user-overrides.yaml` mutation happens only through the product surface with in-case restoration.

### References

- [Source: _bmad-output/planning-artifacts/epics.md § "Epic 10 Detail" + § "Story 10.5"] — ACs verbatim, RUN-MODE BINDING, doc-drift rules, N.5 scope fence
- [Source: README.md:69-207 + :277-299 + :362-372] — write-family + slash-table surface under walk; error-table + limitations context
- [Source: _bmad-output/implementation-artifacts/10-4-readme-perimeter-walks-read-family.md + 10-4-walk-evidence.md] — hybrid run-mode pattern, sanitization pin (WALK-10-4-F1), run_id conventions, honest-count precedent
- [Source: _bmad-output/implementation-artifacts/10-1-walk-evidence.md + epic-10-run-flags.md] — F1/F4 pause landmines, blast-radius discipline
- [Source: _bmad-output/implementation-artifacts/9.5.2-walk-evidence.md] — slash_command:one_shot/persistent audit-vocab precedent, sensitivity-refusal L3 precedent
- [Source: memory feedback_anthropic_spend_source_of_truth.md, project_epic_6_scope_cleave.md (N.5), feedback_oauth_token_handling.md] — durable rules binding this walk

## Dev Agent Record

### Agent Model Used

claude-fable-5 (Claude Fable 5) — inline create-story + walk orchestration + evidence + doc-drift edits, hybrid `autonomous story run 10-5` session 2026-07-06. Adam types every Discord turn, authorizes spend, reads Console truth, signs verdicts at Phase 3.5.

### Debug Log References

- `10-5-walk-evidence.md` (frozen case table, 16 per-case blocks w/ verbatim replies + router_calls/log/DB provenance, findings table F-10-5-1..12, verdict table, spend record, doc-drift + Rule-Q inventory)
- `epic-10-run-flags.md` § "Story 10-5 Run 1" (run record, findings mirror, CR determination)

### Completion Notes List

- **AC-1 (write walks): PASS** — all 4 documented write cases walked (W1 as W1a cancel + W1b send), evidence in §2. W4 confidential refusal PASS (zero body egress DB-proven); W3 sensitive escalation FAIL (broken by construction — self-mint + session-binding mismatch + session-bricking; privacy invariant HELD across 12 refusals); W2 Tier-2 archive FAIL on documented choreography (approval never solicited, stuck pending_grant, false success) but capability-verified (7 archived, Outlook-confirmed); W1a cancel PASS (37s in-window abort, zero dispatch); W1b send PASS at L3 (60s cooling-off enforced, real Graph send, Gmail receipt Adam-confirmed).
- **AC-2 (slash walks): PARTIAL-PASS** — all 7 command groups + `/model` 3 arities walked (9 slash cases). Systemic F-10-5-1: literal `/command` forms never reach the agent (Hermes owns the `/` prefix); capabilities verified via slash-dropped chat forms. S1b/S2/S3/S4b/S7/S8/S9 PASS via chat; S1/S4 literal FAIL; S5/S6 pause/resume FAIL (F-10-5-4 deadlock). `/cost` not walked (not in AC-2 list; honest-count note).
- **AC-3 (spend truth): PASS** — Console $26.94→$28.25 Adam-read (delta $1.31 over ~6h window incl. background ingest, vs ~$2-4 estimate); estimator $0.2498 walk-attributable recorded as estimator-only; ZERO Opus dispatched — the $2-4 premise assumed the Opus draft path, which is unwired from chat (F-10-5-11).
- **AC-4 (doc-drift a+b): PASS** — README write/slash/sensitivity sections + slash table + Limitations made evidence-real same session (7 `verified 10-5` PASS tags + honest currently-broken notes for FAILs); hard-assert = command-name reachability (the F-10-5-1 slash-prefix failure IS the hard-assert result), prose soft-asserted.
- **AC-5 (CR cadence): PASS** — zero code staged by this story. The agent's uncommanded SKILL.md self-edit (F-10-5-12) was captured verbatim then reverted (`git restore` + rm references/); working tree carries zero `mailbot_api/`/`router/`/`hermes-config/` changes. Zero of 6 CR criteria fire → CR skipped per cadence binding.
- **Findings F-10-5-1..12 FILED per N.5, zero fixed** (6 HIGH: slash-prefix interception, PAUSED chat deadlock, sensitivity self-mint, sensitivity session-binding-break/session-bricking, Tier-2 approval unenforced, Opus-draft-pipeline unwired, agent self-edits gitted skill files; 4 MEDIUM: sensitivity refusal UX/id-leak, mint-before-propose stuck state, false-success narration; 2 LOW: NL 1-arg model mapping, overrides-file wholesale replace). Severity tally: 6 HIGH (F-10-5-1/4/5/7/8/11) + 1 HIGH (F-10-5-12) = 7 HIGH, 3 MEDIUM (F-10-5-6/9/10), 2 LOW (F-10-5-2/3) = 12 total.
- Gates at close: ruff clean on tracked tree (2 pre-existing T201 in untracked `scratch/walk_bootstrap.py`, same residual class as 10-1..10-4), mypy --strict clean (129 files), boundaries exit 0, pytest **1708 passed + 2 skipped + 3 deselected in 217.20s** — byte-identical to baseline (docs+evidence-only confirmed; zero source touched).

### File List

None — documentation/walk story, no source files modified. Artifacts:

- `README.md` (§"Talking to MailBot on Discord" write-family + sensitivity + slash-table + Limitations made evidence-real, doc-drift rule (a))
- `_bmad-output/implementation-artifacts/10-5-readme-perimeter-walks-write-and-slash-family.md` (this file)
- `_bmad-output/implementation-artifacts/10-5-walk-evidence.md` (new)
- `_bmad-output/implementation-artifacts/epic-10-run-flags.md` (§ Story 10-5 Run 1 appended)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status flips)
- `router/policy.user-overrides.yaml` — mutated THROUGH THE PRODUCT SURFACE during S3 then restored to pre-walk `tasks: {}` (gitignored runtime file; NOT a repo edit, NOT staged)
- `hermes-config/skills/mailbot/SKILL.md` + `references/tier2-grant-pitfall.md` — agent self-edited (F-10-5-12), captured, then REVERTED; NOT staged, working tree clean

### Change Log

- 2026-07-06 — Write+slash README perimeter walked live (hybrid Adam-hands-on): 16 cases, 10 PASS / 6 FAIL, 12 findings filed per N.5 (7 HIGH), README write/slash sections made evidence-real with verified tags; real Tier-3 send + Tier-2 archive verified at L3; agent self-edit reverted; zero code changes; Console spend $26.94→$28.25.
