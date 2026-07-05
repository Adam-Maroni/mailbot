# Epic 10 run flags — Full-Perimeter Live Validation (README-as-Charter UAT)

Modeled on `epic-9-5-run-flags.md`. One section per story run; halts, path decisions, findings dispositions, and CR-cadence determinations land here.

---

## Story 10-1 Run 1 — 2026-07-05 — EXECUTED (Adam-hands-on walk, Claude-assisted; COMPLETE)

**Invocation:** Adam typed `create-story 10-1` (context-engineering session), then chose "Execute the walk hands-on" in the same session — RUN-MODE BINDING satisfied: Adam drove every mailbox-touching action (folder creation, Discord prompt, Outlook verification, drag-and-drop restore) and green-lit the Path B propose ("go"); Claude performed read-only checks, SQL/log evidence capture, and evidence drafting. No dev-agent halt was required.

**Walk record (full detail in `10-1-walk-evidence.md`):**

- Task 0 preflight PASS (OAuth green, drainer live at 2s ticks, DB baselines; degraded-mode-on recorded as non-blocking — $0 walk).
- **Path A (Discord → Hermes) BLOCKED by F1:** router pause (the story's Contract-Pin-4 safety choreography) also blocks Hermes chat (`hermes_aux` → `ask_router` → PAUSED, 3×502 surfaced raw in Discord). `propose_action` never invoked; zero rows queued.
- **Path B (direct verb-level `propose_action`, Adam-green-lit) EXECUTED:** action id=4, `move_to_triage_folder`, tier 1, correct staged `destination_folder_id`. **F4 (CRITICAL) discovered at this instant:** the worker-process drainer dispatched the real Graph write **259 ms after propose, while the router was paused** — `PauseState` is a per-process in-memory singleton; the kill-switch does not cover mailbox writes in the production two-process topology. Blast-radius-by-construction (sacrificial staging) was the only real containment.
- Chain L3-verified: Graph `parentFolderId` == sacrificial folder; **Adam verified in desktop Outlook**; manual drag-and-drop restore; server-side back-in-Inbox confirmed; `router_calls` untouched ($0, Pin 7); Tier-1 silence observed (Pin 5); `GRANT_NOT_NEEDED` + `INVERSE_UNAVAILABLE` refusals captured live verbatim.
- **Findings F1-F6 + B1 ALL FILED per N.5, zero fixed in-walk** (F4 CRITICAL pause-bypass; F5 move soft-deletes local row as `'deleted'`; F6 `EMAIL_UPSERT` never resurrects — walk subject email deliberately left soft-deleted locally as live evidence). pre_state field list for 10-2 delivered (6 items, §5 of evidence).
- **Optional Path A′ (unpaused Discord retry) DECLINED** — with F6 the subject email is invisible to read verbs (mis-resolution risk) and with F4 a mis-resolved Tier-1 move is unstoppable; deferred to 10-5 after 10-2 ships revert.
- README doc-drift discharged same-story (tier-table row 1, verified pipeline-trace example — deliberately NOT a fabricated chat transcript — limitations rewrite; `<!-- verified 10-1, run_id action-4/2026-07-05 -->` convention introduced).

**CR-cadence determination (story AC-5):** zero of the 6 criteria fire — no code authored or changed (evidence/docs/tracking files only; the two ruff T201 hits are in untracked pre-existing `scratch/` from a prior session, outside story scope). **CR skipped per cadence binding.**

**Epic 10.5 triage inputs from this run:** F4 (CRITICAL, safety), F5+F6 (HIGH, local-DB truth), F1+F2 (Hermes/pause UX), F3 (audit), B1 (charter bookkeeping: error table is 16 rows, not 17).
