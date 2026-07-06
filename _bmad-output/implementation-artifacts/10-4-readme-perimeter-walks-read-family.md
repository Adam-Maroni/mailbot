---
baseline_commit: dab455b581b4ae4f21143639a8e1e0959dbe7bbb
---

# Story 10.4: Happy-path README perimeter walks — read family

Status: done (walk executed 2026-07-06 hybrid Adam-hands-on; 6 PASS / 5 FAIL / 0 EXCLUDED; Phase 3.5 Adam-delegated verification PASS WITH FINDINGS — WALK-10-4-F1 sanitization correction in-walk, evidence Amendment A1; all 4 AC verdicts PASS signed via delegation)

<!--
Walk story, Epic 10 README-as-charter UAT. NOT an implementation story: it produces walk
evidence (real captured chat output per README read-family example) + same-commit README
verified-tag updates per doc-drift rule (a), and defect FILINGS per N.5 — not code.

RUN-MODE BINDING (HYBRID, Adam-chosen option (a) in-session 2026-07-06): the chat cases are
Adam-hands-on — Adam types each case's message in the Discord channel and pastes MailBot's
reply back into the run session; the orchestrator (dev model) drives the case list, captures
DB-side provenance (router_calls watermark deltas, read-only mode=ro), asserts hard-assert
facts, composes evidence, and applies the README doc-drift edits. The digest case may be
harness-triggered (`hermes cron run mailbot-daily-digest`) with an induced-vs-scheduled
honesty tag if the 08:00 slot is missed. Dev agents do NOT halt at the walk — they orchestrate
it conversationally with Adam in-session (10-2 Task-7 pattern, but in-session not deferred).

PRE-RUN PRECONDITION (EXECUTED before story-file authoring, Adam-authorized "Reset now"):
degraded mode exited 2026-07-06T07:54:33Z via reset_degraded_mode verb (guard.initialize +
verb in-container) + `docker compose restart mailbot-api` so BOTH processes re-seeded
BudgetGuard from the cleared row (F4-pattern per-process-memory landmine avoided by restart).
Verified: degraded_mode_state=(0, entered 07-03T14:41Z, exited 07-06T07:54:33Z), /health ok.
NOTE: this is an OPERATOR ACTION on the documented product surface, not a fix — F-10-3-1
(inflated estimator counter) remains FILED and open. In-memory month counter still reads
$70.24 (inflated); Layer-3 re-entry requires a $30-cap CROSSING (prev < cap <= new), and
prev is already >> cap, so degraded mode CANNOT re-trip mid-walk (budget.py:126-131).

Scope fence (N.5 policy): findings are FILED with evidence, never fixed here. The ONLY
non-evidence file this story edits is README.md (doc-drift rule (a) is an explicit AC).
Any code/config/prompt change escalates CR per §5.12.
-->

## Story

As Adam,
I want every read-family example documented in the README walked against the live local stack — each documented example is one acceptance walk with captured real output,
So that the read perimeter's README claims are evidence-backed rather than illustrative.

## Acceptance Criteria

**AC-1 — Every documented read-family example walked with real output captured**
**Given** the README's read-family examples (query flows, projections, counts, sender summaries, thread summaries, digest)
**When** the walks fire
**Then** each documented example is executed as one walk case (~10-12 total) with real output captured in `10-4-walk-evidence.md`

**AC-2 — Doc-drift rule (b): hard-assert commands, soft-assert prose**
**Given** doc-drift rule (b)
**When** each case is asserted
**Then** command names are hard-assert (mismatch = FAIL); response prose is soft-assert (Hermes-persona-dependent — captured, not failed on wording)

**AC-3 — Doc-drift rule (a): README examples made real, same story same commit**
**Given** doc-drift rule (a)
**When** each case closes
**Then** the corresponding README example is updated with the real captured output + `<!-- verified 10-4, run_id ... -->` tag in the same story, same commit
**And** each case receives a named PASS / FAIL / EXCLUDED-with-reason verdict feeding Story 10.7's per-row table

**AC-4 — CR cadence**
**Given** this is a walk story
**When** CR cadence is evaluated per the 6 criteria
**Then** zero criteria fire → CR skipped per cadence binding; discovered defects are FILED per N.5 policy

### AC interpretation pins (code-reality; read before executing)

- **AC-1's "each documented example":** the README's read-family surface (§ "Querying your mail" README:21-69) documents exactly **8 anchors**: 3 fenced examples (list-unread :25-39, importance-filter :41-48, thread-summary :50-58), 4 "other queries" table rows (:62-67 — count-only, sender-reputation, one-body-read w/ 5-per-turn cap, filtered projection), and the 08:00 daily digest (:69). The roundtable's "~10-12" was an estimate; the case list is what the README actually documents (8 cases + a C0 smoke turn). Record the honest count + this rationale in evidence — do NOT fabricate cases to hit the estimate.
- **AC-2's "command names are hard-assert" for a natural-language surface:** the read family has no slash commands. Hard-assert = the mechanical claims embedded in the README prose: reads are projection-first (no body opened for list/count queries), body-reads capped 5/turn (the cap value as documented; happy path exercises 1 body-read, the cap-limit boundary itself is 10-6 fault-injection territory), counts/listings consistent with the live DB (cross-checked read-only), digest carries per-category counts + top-importance + short intro, digest schedule is 08:00. Soft-assert = reply wording, formatting, emoji, persona tone. Mismatched behavior = FAIL; mismatched wording = captured, not failed.
- **AC-3's "real captured output" vs privacy:** README is a gitted artifact; real replies contain real senders/subjects. Default: README examples get the real captured output **sanitized** (structure, counts, scores real; sender addresses + subjects masked to shape-preserving placeholders), with the `<!-- verified 10-4, run_id ... -->` tag + evidence pointer carrying the truth chain. Adam may per-example choose to keep real content. Evidence file itself follows Rule Q discipline (truncated subjects ≤60 chars, sender domain class, NO full bodies).
- **AC-3's run_id convention:** read walks produce no `action_id` (10-1/10-2 used `action-N`). Pin: `run_id 10-4-c<case>/<date>`, each case backed in evidence by its `router_calls` id range (watermark before/after the turn).
- **Verdict vocabulary:** PASS / FAIL / EXCLUDED-with-reason per case (10.7 table contract), PASS / PARTIAL-PASS / FAIL per AC section, Adam-signed at the Phase 3.5 gate.

## Tasks / Subtasks

- [ ] **Task 0 — Preconditions + baseline capture (BLOCKING)** (AC: 1)
  - [x] 0.1 Record the degraded-mode reset precondition into evidence (verb output, restart, post-state row, re-trip impossibility rationale) — executed pre-run, Adam-authorized — evidence § Precondition record
  - [x] 0.2 `docker ps` all three containers healthy; `curl localhost:8000/health` ok + sync heartbeat fresh (0.27 min)
  - [x] 0.3 Baselines into evidence header: commit dab455b, W0=13606/2026-07-06T07:46:03Z, 1928 live emails, policy-v1-2026-07-04
  - [x] 0.4 C0 smoke turn (Adam-hands-on) — PASS 08:05-08:06 UTC; reply arrived, rows 13607-13610 all `policy:hermes_aux:default` (zero degraded), gate open. Observation: 2 transient failed rows before ok → F-10-4-2
- [x] **Task 1 — Case-list freeze (AC-1, AC-2)**
  - [x] 1.1 Frozen into evidence before walking (8 cases C1-C8 + C0 smoke; honest-count rationale recorded). Pre-walk LANDMINE logged: `emails.is_read` not captured locally (Story 5-1 gap, queries.py:1124) — README C1/C4 "unread" semantics are an approximation, undisclosed in Limitations; candidate finding frozen BEFORE any turn fired
  - [x] 1.2 DB cross-check baselines captured at W0 (read-only): received-today=3, last-24h=11, importance>70-this-week=3, newsletters-this-week=10; C6 cap constant verified `_HYDRATION_LIMIT_PER_SESSION = 5` (hydrate_email.py:23) matches README's "5 body-reads per turn"
- [ ] **Task 2 — Execute chat walks C1-C7 (Adam-hands-on Discord)** (AC: 1, 2)
  - [x] 2.1 Executed 08:05-08:23 UTC, all replies pasted verbatim + provenance captured (rows 13607-13644). Provisional: C1 PASS, C2 PASS, C3 FAIL (revised from PASS after log forensics — THREAD_NOT_FOUND dressed as "standalone"), C3b FAIL, C4 FAIL, C5 FAIL, C5b PASS, C6 PASS, C7 PASS
  - [x] 2.2 Projection-first held on C1/C2/C4/C7: zero hydrate_email calls in those turns (mcp.tool log sweep)
  - [x] 2.3 C6: exactly one hydrate_email (08:23:35); cap constant `_HYDRATION_LIMIT_PER_SESSION = 5` matches README
  - [x] 2.4 Honored: 4 FAILs filed (F-10-4-1/3/4/5), walk never stopped
- [x] **Task 3 — Digest case C8** (AC: 1, 2)
  - [x] 3.1 BOTH layers captured: today's SCHEDULED slot fired 08:49 local and FAILED under degraded mode (`tools_unsupported` in Discord — live F-10-3-1/2 blast radius, rows 13586-13588); manual trigger post-reset ran on the 10:26 scheduler tick, honesty-tagged manually-triggered
  - [x] 3.2 Delivered digest verified: posted to Discord (Adam-pasted), importance buckets 2+9=11 = last-24h DB baseline exact, top-importance list present. Intro hard-assert FAILED — no intro paragraph, `daily_digest_intro` ZERO rows all-time → F-10-4-6 HIGH. Case verdict FAIL
- [x] **Task 4 — README doc-drift rule (a) edits** (AC: 3)
  - [x] 4.1 C1/C2 examples replaced with real sanitized captured output + tags; C4/C5b/C6/C7 table rows tagged; digest sentence rewritten + tagged (c8)
  - [x] 4.2 README:19 blanket-illustrative sentence rescoped: read family verified 10-4, write/slash still illustrative pending 10-5
  - [x] 4.3 Honored: C3 example replaced with honest currently-broken note (no tag); C4 row marked explicit honest-FAIL documentation; behavioral defects FILED not fixed
- [x] **Task 5 — Findings FILED per N.5** (AC: 4)
  - [x] 5.1 F-10-4-1..6 in evidence findings table (3 HIGH / 2 MEDIUM / 1 LOW), mirrored to `epic-10-run-flags.md` § "Story 10-4 Run 1"
  - [x] 5.2 Zero fixes shipped — README edits are doc-drift corrections (explicit AC-3 scope), not defect fixes; degraded-mode reset was a pre-run Adam-authorized operator action, F-10-3-1 stays open
- [x] **Task 6 — Compose `10-4-walk-evidence.md`** (AC: 1, 2, 3)
  - [x] 6.1 Composed per convention: session header w/ precondition record + signature line, frozen case table (BEFORE walking), per-case blocks w/ provenance + cross-checks, findings table, verdict table (6 PASS / 5 FAIL / 0 EXCLUDED), per-AC proposed verdicts, footer
  - [x] 6.2 Honored: verbatim pastes (README versions lightly sanitized, inventory in footer); C3 correction APPENDED not rewritten; C8 manually-triggered tag; spend $0.1074 estimator (cents — Console read noted as not warranted, per durable memory)
- [x] **Task 7 — CR determination, run-flags, gates, sprint flip, stage (never commit)** (AC: 4)
  - [x] 7.1 Zero of 6 criteria fire (pre-review §5.12 GATE-COVERAGE-ELIGIBLE) — CR skipped per cadence binding, recorded in Dev Agent Record
  - [x] 7.2 Appended § "Story 10-4 Run 1" to `epic-10-run-flags.md`; flag report appended to `story-run-flags.md`
  - [x] 7.3 Gates green: ruff clean (tracked tree), mypy --strict clean (129 files), boundaries exit 0, pytest 1708+2+3 byte-identical to baseline
  - [x] 7.4 sprint-status flipped `review`; 7 files staged with explicit paths; `done` flips on Adam's signed verdicts; nothing committed

## Dev Notes

### Run-mode decision record (this session, 2026-07-06)

Pre-flight found two blockers: (1) degraded mode still active (F-10-3-1) making Hermes tool-call turns qwen-fail (F-10-3-2, 18/18); (2) the walk surface is Discord chat, which an autonomous run cannot drive. Adam resolved both in-session: "Reset now" (executed — see banner comment) and option (a) Adam-hands-on chat walk. This story therefore runs as a HYBRID: orchestrator-driven case protocol, Adam-typed Discord turns, DB-side provenance captured read-only.

### Chat-turn pipeline pins (what a walk turn looks like in router_calls)

- Hermes agent turn → `POST /v1/chat/completions` with `tools=[...]` → task `chat_completions_tool_call` (022 tool-call columns), policy model haiku (`hermes_aux` is the no-tools pass-through variant). Read verbs the agent invokes (find_emails / hydrate_email / get_thread / count_emails / get_sender_summary — Story 5-1/5-2) are MCP tools, free, NO router_calls rows.
- `intent_parsing_chat` + `reference_resolution` are qwen-policy escalate:true tasks — C3's "that thread" resolution may legitimately show `escalated_from_qwen…` haiku rows.
- Digest chain (cron-jobs.md §3, verified live 2026-06-04 + F11 closed since): `digest_prepare.py` → `compose_digest` MCP tool → agent renders + posts → `finalize_digest_delivery`; intro = `daily_digest_intro` (qwen policy).
- Expected walk spend: haiku cents on chat turns (epic's real-spend allocation is 10-5's; record actual delta honestly).

### Live-DB access pattern (unchanged from 10-3)

`docker compose exec -T mailbot-api python -c "import sqlite3, ...; sqlite3.connect('file:/data/mailbot.db?mode=ro', uri=True)"` — image has no sqlite3 CLI; live DB is the `mailbot_db` volume, NOT the repo-root `mailbot.db`; MSYS_NO_PATHCONV=1 for any bare path args (durable memory `ops_msys_path_mangling_docker_exec.md`).

### Known landmines this walk must respect

- **F-10-3-2 residue:** July's qwen-era failed ingest rows (action_extraction ~45% fail etc.) exist in the DB; digest content quality may reflect them. That is EVIDENCE (captured + cross-referenced to filed findings), not a new walk failure — unless a documented README claim itself breaks.
- **10-1 F5/F6 residue:** the 10-1/10-2 walk subject email history includes soft-delete churn; exclude `removed_reason IS NOT NULL` rows from DB cross-checks.
- **Pause is NOT used in this walk** (10-1 F1: pause kills Hermes chat; F4: it doesn't gate the worker anyway). No pause choreography needed for reads.
- **README:19 blanket-illustrative sentence** must be rescoped in the same commit (Task 4.2) or the verified tags contradict the section preamble.

### Project Structure Notes

Files this story may touch — and ONLY these: `README.md` (doc-drift rule (a) — explicit AC), `_bmad-output/implementation-artifacts/10-4-walk-evidence.md` (new), `epic-10-run-flags.md` (append), `sprint-status.yaml` (flips), this story file, `story-run-flags.md` (run report). ZERO changes under `mailbot_api/`, `scripts/`, `router/`, `hermes-config/`, `docker/`, `tests/`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md § "Epic 10 Detail" + § "Story 10.4"] — ACs verbatim, doc-drift rules (a)/(b), N.5 scope fence
- [Source: README.md:17-69] — the read-family surface under walk (8 documented anchors)
- [Source: hermes-config/skills/mailbot/cron-jobs.md §3-§4] — digest job contract, manual-trigger command, verified-live registration
- [Source: _bmad-output/implementation-artifacts/10-3-walk-evidence.md] — F-10-3-1/2 (degraded mode + qwen tool-call fail), policy expectation table, schema pins
- [Source: _bmad-output/implementation-artifacts/10-1-walk-evidence.md + 10-2-walk-evidence.md + epic-10-run-flags.md] — walk-evidence conventions, verified-tag convention, live-stack facts
- [Source: mailbot_api/router/budget.py:64-173] — BudgetGuard per-process singleton, crossing-only Layer-3 entry (re-trip impossibility)
- [Source: memory feedback_anthropic_spend_source_of_truth.md, project_epic_6_scope_cleave.md (N.5), feedback_l1_l2_l3_done_layers.md] — durable rules binding this walk

## Dev Agent Record

### Agent Model Used

claude-fable-5 (Claude Fable 5) — inline create-story + walk orchestration + evidence + doc-drift edits, single `autonomous story run 10-4` session 2026-07-06. Adam typed every Discord turn (hybrid run-mode, option (a) Adam-chosen) and signs verdicts at Phase 3.5.

### Debug Log References

- `10-4-walk-evidence.md` (frozen case table, per-case blocks w/ verbatim replies + router_calls/mcp-log provenance + read-only DB cross-checks, findings, verdict tables)
- `epic-10-run-flags.md` § "Story 10-4 Run 1" (run record, findings mirror, CR determination)

### Completion Notes List

- **AC-1:** all 8 README read-family anchors walked live as 11 cases (C0 smoke + C1-C8 + C3b/C5b sub-cases), 08:05-08:27 UTC, every reply captured verbatim and DB-cross-checked read-only (C1 3/3, C2 3/3, C5b 41-email aggregates exact, C7 7/7 in-window, C8 buckets 2+9=11 = last-24h baseline). Honest case-count note recorded (README documents 8 anchors; the roundtable's "~10-12" was an estimate — nothing fabricated).
- **AC-2:** hard-asserts enforced on mechanical claims — 5 FAILs named (C3/C3b thread lookup, C4 unread count, C5 name-form sender query, C8 intro+scheduled-slot); prose/persona differences captured, never failed. Projection-first held on every list/count turn; C6 exactly one hydration, cap constant 5 verified.
- **AC-3:** README § "Querying your mail" made evidence-real same session: C1/C2 real sanitized output + tags, C3 replaced with honest currently-broken note, C4/C5 rows corrected to walked truth, digest sentence rewritten with both caveats, :19 blanket-illustrative sentence rescoped. 7 `<!-- verified 10-4, run_id 10-4-cN/2026-07-06 -->` tags placed. Verdict table (6 PASS / 5 FAIL / 0 EXCLUDED) published for 10-7.
- **AC-4:** zero of the 6 CR criteria fire — zero code touched (README + evidence/tracking only). **CR skipped per cadence binding.** Findings **F-10-4-1..6 FILED per N.5, zero fixed** (3 HIGH: get_thread unreachable-by-construction from chat; enrichment layer never runs — 0/727 senders, 0/1753 threads; daily_digest_intro zero rows all-time. 2 MEDIUM: is_read never synced; no display-name search. 1 LOW: transient 529s absorbed by Hermes retries).
- **Precondition (Adam-authorized "Reset now"):** degraded mode exited 07:54:33Z via `reset_degraded_mode` verb + `mailbot-api` restart (per-process BudgetGuard re-seed); re-trip impossible mid-walk (crossing-only Layer-3). Operator action on the product surface — F-10-3-1 remains FILED and open.
- Gates at close: ruff clean on tracked tree (2 pre-existing T201 in untracked `scratch/`, same residual as 10-1/10-2/10-3), mypy --strict clean (129 files), boundaries exit 0, pytest **1708 passed + 2 skipped + 3 deselected in 219.46s** — byte-identical to baseline (docs-only confirmed).

### File List

None — documentation/walk story, no source files modified. Artifacts:

- `README.md` (§ "Talking to MailBot on Discord" read-family examples made evidence-real, doc-drift rule (a))
- `_bmad-output/implementation-artifacts/10-4-readme-perimeter-walks-read-family.md` (this file)
- `_bmad-output/implementation-artifacts/10-4-walk-evidence.md` (new)
- `_bmad-output/implementation-artifacts/epic-10-run-flags.md` (§ Story 10-4 Run 1 appended)
- `_bmad-output/implementation-artifacts/sprint-status.yaml` (status flips)

### Change Log

- 2026-07-06 — Read-family README perimeter walked live (hybrid Adam-hands-on): 11 cases, 6 PASS / 5 FAIL, 6 findings filed per N.5, README read-family section made evidence-real with verified tags; zero code changes.
