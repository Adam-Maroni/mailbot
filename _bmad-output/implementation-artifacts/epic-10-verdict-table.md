# Epic 10 — Complete Per-Row Verdict Table (README-as-charter UAT close-out)

**Published by Story 10-7 (2026-07-06)** — discharges epic-10 done-flip clause 2: *every README example AND all error-table rows carry a named PASS / FAIL / EXCLUDED-with-reason verdict, with citations into the 10-x walk-evidence files and induced-vs-simulated honesty tags carried through from 10-6.*

**Verdict provenance:** every verdict below is TRANSCRIBED from its signed 10-x walk-evidence file — none re-adjudicated here. Per-case verdicts were proposed by each walk and Adam-signed at that story's Phase 3.5 (10-4/10-5: signed via Adam-delegated verification; 10-6: signed at Phase 3.5). README line refs are as of this story's commit.

**Charter-count honesty (F-10-6-1, INFO):** the epic charter says "all 17 error rows"; the README common-errors table has **16 data rows** (verified at 3 commits in 10-6 §0). R15 carries 3 codes, walked as R15a/b/c → **18 error verdict rows**. This table uses the honest 16-rows/18-verdicts framing.

---

## Section 1 — README examples (walked anchors from Stories 10-1, 10-2, 10-4, 10-5)

Story 10-3 contributes no rows here by design: it was a read-only DB audit of the qwen batch lane (no README example anchors); its findings (F-10-3-1..6) feed the Limitations section and are cited by rows below where relevant.

| # | Anchor (README ref) | Walk case | Verdict | Evidence citation | Notes / honesty tags |
| --- | --- | --- | --- | --- | --- |
| 1 | Tier-1 triage-move pipeline trace (:147-155) | 10-1 full-chain move walk | **PASS** | `10-1-walk-evidence.md` §2/§4/§6, run_id action-4/2026-07-05 | Real Graph dispatch, Outlook-verified both directions; findings 10-1 F1-F6 FILED (pause-bypass F4 CRITICAL, local soft-delete F5/F6); example deliberately a pipeline trace, not a chat transcript (chat can't propose moves — no folder-name lookup) |
| 2 | Triage-move revert claims (:157, :380 limitations bullet) | 10-2 live revert walk | **PASS** | `10-2-walk-evidence.md` §2-§7, run_id action-6/2026-07-05 | pre_state captured strictly pre-dispatch; revert applied byte-identical to source; local row repaired; `PRE_STATE_MISSING` + `ALREADY_REVERTED` refusals captured verbatim |
| 3 | Smoke turn (no README anchor) | 10-4 C0 | **PASS** | `10-4-walk-evidence.md` §C0 | Gate case: chat chain live post-degraded-reset |
| 4 | List unread example (:25-39) | 10-4 C1 | **PASS** | `10-4-walk-evidence.md` §C1, run_id 10-4-c1/2026-07-06 | 3/3 exact DB match, projection-first; "unread"→"from today" reframe filed F-10-4-1 |
| 5 | Importance filter example (:43-54) | 10-4 C2 | **PASS** | `10-4-walk-evidence.md` §C2, run_id 10-4-c2/2026-07-06 | 3/3 exact match on importance>70-this-week |
| 6 | Thread summary (:56, honest-broken note) | 10-4 C3 | **FAIL** | `10-4-walk-evidence.md` §C3 + retroactive correction, run_id 10-4-c3/2026-07-06 | `THREAD_NOT_FOUND` log-proven; reply dressed the error as "standalone notification" (F-10-4-3) |
| 7 | Thread summary, rich-thread sub-case (:56) | 10-4 C3b | **FAIL** | `10-4-walk-evidence.md` §C3b, run_id 10-4-c3b/2026-07-06 | Same failure on a real 6-message thread; continuity notes 0/1753 all-time (F-10-4-3, F-10-4-4) |
| 8 | Count-only query row (:62) | 10-4 C4 | **FAIL** | `10-4-walk-evidence.md` §C4, run_id 10-4-c4/2026-07-06 | Documented count flow refuses honestly — `is_read` never synced (F-10-4-1); README row now documents the refusal |
| 9 | Sender summary, name form (:63) | 10-4 C5 | **FAIL** | `10-4-walk-evidence.md` §C5, run_id 10-4-c5/2026-07-06 | 0 of 52 existing emails found by name; `get_sender_summary` never invoked (F-10-4-4, F-10-4-5) |
| 10 | Sender summary, address form (:63) | 10-4 C5b | **PASS** | `10-4-walk-evidence.md` §C5b, run_id 10-4-c5b/2026-07-06 | Aggregates exact (41 emails, 2016→Jun 1); cached reputation summary NULL mailbox-wide (F-10-4-4); README address masked per WALK-10-4-F1 |
| 11 | One body read row (:64) | 10-4 C6 | **PASS** | `10-4-walk-evidence.md` §C6, run_id 10-4-c6/2026-07-06 | Exactly one `hydrate_email`; 5-per-turn cap constant verified |
| 12 | Filtered projection row (:65) | 10-4 C7 | **PASS** | `10-4-walk-evidence.md` §C7, run_id 10-4-c7/2026-07-06 | 7/7 exact set match in the agent's stated window |
| 13 | Daily digest (:67) | 10-4 C8 | **FAIL** | `10-4-walk-evidence.md` §C8, run_id 10-4-c8/2026-07-06 | **Honesty tag: successful run manually triggered.** Delivery chain + bucket counts exact (11 = 2+9); scheduled slot failed that morning (degraded-mode victim, ~49 min late) and "short intro" has never existed (F-10-4-6) |
| 14 | `/model` native slash form (:200, :213 note) | 10-5 S1 | **FAIL** | `10-5-walk-evidence.md` §S1, run_id 10-5-s1/2026-07-06 | Hermes runtime UI intercepts; `inspect_policy` never fires (0 rows) — systemic F-10-5-1 |
| 15 | Policy table via chat (:213) | 10-5 S1b | **PASS** | `10-5-walk-evidence.md` §S1b, run_id 10-5-s1b/2026-07-06 | Full 17-task table truthful vs DB + files |
| 16 | One-shot model override (:214) | 10-5 S2 | **PASS** | `10-5-walk-evidence.md` §S2, run_id 10-5-s2/2026-07-06 | Armed + audit vocab + TTL; 9.5.2 arm/consume race reproduced (documented contract fact); NL 1-arg mapping gap F-10-5-2 |
| 17 | Persistent per-task override (:215) | 10-5 S3 | **PASS** | `10-5-walk-evidence.md` §S3, run_id 10-5-s3/2026-07-06 | Write + hot-reload observed; overrides file restored post-case; wholesale-replace filed F-10-5-3 |
| 18 | `/spend` literal slash form (:205) | 10-5 S4 | **FAIL** | `10-5-walk-evidence.md` §S4, run_id 10-5-s4/2026-07-06 | "Unknown command" bounce — F-10-5-1 (systemic for the whole slash table) |
| 19 | Spend chart via chat (:205) | 10-5 S4b | **PASS** | `10-5-walk-evidence.md` §S4b, run_id 10-5-s4b/2026-07-06 | `render_spend_chart` + PNG + summary; renders the inflated estimator ledger (F-10-3-1 corroborated) |
| 20 | Pause (:206) | 10-5 S5 | **FAIL** | `10-5-walk-evidence.md` §S5, run_id 10-5-s5/2026-07-06 | Pause itself works server-side; documented `⏸` ack unreachable by construction (10-1 F1) — raw 502s |
| 21 | Resume (:207) | 10-5 S6 | **FAIL** | `10-5-walk-evidence.md` §S6, run_id 10-5-s6/2026-07-06 | Chat resume impossible while paused (F-10-5-4); CLI fallback verified |
| 22 | Cancel during cooling-off (:208) | 10-5 W1a (cancel leg) | **PASS** | `10-5-walk-evidence.md` §W1a, run_id action-14/2026-07-06 | Aborted 37s into the window, zero dispatch |
| 23 | Budget reset (:209) | 10-5 S7 | **PASS** | `10-5-walk-evidence.md` §S7, run_id 10-5-s7/2026-07-06 | Truthful idempotent not-degraded branch; degraded-clearing branch verb-verified as the 10-4 precondition |
| 24 | Mute (:210) | 10-5 S8 | **PASS** | `10-5-walk-evidence.md` §S8, run_id 10-5-s8/2026-07-06 | DB row exact; truthful "indefinitely" |
| 25 | Unmute (:211) | 10-5 S9 | **PASS** | `10-5-walk-evidence.md` §S9, run_id 10-5-s9/2026-07-06 | Round-trip clean; mute state left as found |
| 26 | Confidential refusal (:184-192) | 10-5 W4 | **PASS** | `10-5-walk-evidence.md` §W4, run_id 10-5-w4/2026-07-06 | Refusal + metadata-only + ZERO body egress (DB-proven) |
| 27 | Sensitive escalation (:194, honest-broken note; also `confirm` row :212) | 10-5 W3 | **FAIL** | `10-5-walk-evidence.md` §W3 (4 parts), run_id 10-5-w3/2026-07-06 | Escalation impossible in every form (F-10-5-5/6/7 — self-mint, session-binding mismatch, session-bricking); **privacy invariant HELD: 12 refusals, 0 egress** |
| 28 | Tier-2 batch archive example (:122-145) | 10-5 W2 | **FAIL** | `10-5-walk-evidence.md` §W2, run_id action-7..13/2026-07-06 | Approval never solicited + stuck `pending_grant` + false success ×2 (F-10-5-8/9/10); capability-verified once promoted: 7 archived, Outlook-confirmed, pre_state captured |
| 29 | Draft→refine→send transcript (:71-109) | 10-5 W1a+W1b | **PASS** | `10-5-walk-evidence.md` §W1a/§W1b, run_id action-14+action-15/2026-07-06 | 60s cooling-off enforced (61.7s propose→apply), real Graph send, Gmail receipt Adam-confirmed; Opus draft pipeline UNWIRED from chat (F-10-5-11), premature "Sent." (F-10-5-10) — both documented in the README section |

**Section 1 tally: 18 PASS / 11 FAIL / 0 EXCLUDED across 29 walked rows.** Every FAIL is backed by a FILED finding and is documented honestly at its README anchor (no FAIL carries a clean PASS-style tag).

### Section 1b — README examples honestly NOT walked (EXCLUDED-with-reason)

| # | Anchor (README ref) | Verdict | Reason |
| --- | --- | --- | --- |
| E1 | Tier-1 undo chat example (:159-164) | **EXCLUDED — chat form not walked** | The underlying Tier-1 revert machinery is L3-verified (10-2 walk, CLI `mailbot revert` + "undo that" equivalence at the verb layer), but the illustrative chat transcript was never exercised; marked *illustrative* in the README (10-7) |
| E2 | Tier-3 delete example (:166-175) | **EXCLUDED — deliberately never walked** | Destructive with no revert path; kept out of every Epic 10 walk's blast radius by design (10-5 case-table note). Marked *illustrative* in the README (10-7) with F-10-5-1/7 caveats on its `/confirm` choreography |
| E3 | `cost` slash row (:204) | **EXCLUDED — not walked** | Not in 10-5 AC-2's enumerated command list (honest-count note, 10-5 §1); row marked *illustrative — not walked* in the README since 10-5 |
| E4 | `mailbot status` sample board (:237-283) | **EXCLUDED — illustrative by design** | Marked *illustrative* in the README; the real status surface was exercised repeatedly across 10-1/10-2/10-6 walks (OAUTH/ROUTER/ACTIONS/BUDGET sections all live-asserted), but the sample board is a composite, not a captured output |

---

## Section 2 — Error-table rows (Story 10-6 fault injection; 16 README rows / 18 verdict rows)

Verdicts + induced-vs-simulated tags transcribed verbatim from `10-6-walk-evidence.md` §5. Per-row PASS = code surfaces as documented AND fix works AND recovers; FAIL = any of those breaks (every FAIL received a same-commit README correction in 10-6). README refs :295-310 (current numbering).

| Row | README ref | Code(s) | Honesty tag | Verdict | Evidence citation | Reason (FAIL rows) |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | :295 | `sensitivity_blocks_api` / `needs_sensitivity_confirmation` | INDUCED | **PASS** | `10-6-walk-evidence.md` §R1, run_id 10-6-r1/2026-07-06 | — (token engine ✓; documented `/confirm` choreography separately FILED-broken F-10-5-1/7, corroborated) |
| R2 | :296 | `sensitivity_blocks_api` (confidential) | INDUCED | **PASS** | §R2, run_id 10-6-r2/2026-07-06 | — |
| R3 | :297 | `sensitivity_not_classified` | INDUCED (staged synthetic subject — tagged) | **FAIL** | §R3, run_id 10-6-r3/2026-07-06 | Primary "wait" fix works; documented `mailbot rederive` fix clause BROKEN — CLI crashes every invocation (F-10-6-3 HIGH) |
| R4 | :298 | `CONFIDENTIAL_HYDRATION_BLOCKED` | INDUCED | **PASS** | §R4, run_id 10-6-r4/2026-07-06 | — |
| R5 | :299 | status `pending_grant` | INDUCED | **PASS** | §R5, run_id action-16/2026-07-06 | — |
| R6 | :300 | `per_call_threshold_exceeded` | INDUCED | **PASS** | §R6, run_id 10-6-r6/2026-07-06 | — |
| R7 | :301 | `monthly_budget_exceeded` → `degraded_mode_blocked` | SIMULATED (staged month counter; real crossing + blocking code paths) | **FAIL** | §R7, run_id 10-6-r7/2026-07-06 | `degraded_mode_blocked` + demotion + reset path all ✓; `monthly_budget_exceeded` is dead code — zero raising sites (F-10-6-5) |
| R8 | :302 | `budget.daily.soft_warn` | SIMULATED (staged daily counter; real crossing code path) | **PASS** | §R8, run_id 10-6-r8/2026-07-06 | — |
| R9 | :303 | `rate_limited` | INDUCED | **PASS** | §R9, run_id 10-6-r9/2026-07-06 | — |
| R10 | :304 | `loop_detected` | INDUCED | **PASS** | §R10, run_id 10-6-r10/2026-07-06 | — (logs step needs `PYTHONIOENCODING=utf-8` on Windows — F-10-6-7) |
| R11 | :305 | "PAUSED" | INDUCED | **FAIL** | §R11, run_id 10-6-r11/2026-07-06 | Behavior + fix ✓, but refusal code is `PROVIDER_ERROR` — no stable `PAUSED` code exists (F-10-6-6); README Code cell corrected |
| R12 | :306 | `oauth_refresh_failing` | SIMULATED (D3 expensive-row carve-out; real refresh token never touched) | **PASS** | §R12, run_id 10-6-r12/2026-07-06 | — (auto-pause/Discord-alert hop + token-remint fix cited from code, not induced — caveat carried in the tag) |
| R13 | :307 | `schema_validation_failed` | INDUCED | **PASS** | §R13, run_id 10-6-r13/2026-07-06 | — (escalate-to-Haiku prose over-generalization corrected; rederive clause shares F-10-6-3) |
| R14 | :308 | `daily_send_cap_exceeded` | SIMULATED (staged send-count; never 20 real sends) | **PASS** | §R14, run_id action-37/2026-07-06 | — |
| R15a | :309 | `target_deleted` | **INDUCED (genuine)** | **FAIL** | §R15a, run_id action-17/2026-07-06 | Code surfaces ✓; documented `mailbot replay` fix clause INERT for move-induced soft-delete (F-10-6-2); repair-then-replay works |
| R15b | :309 | `state_drift_etag` | SIMULATED (staged change marker) | **PASS** | §R15b, run_id action-18/2026-07-06 | — (fix asserted structurally within blast-radius limits) |
| R15c | :309 | `state_drift_noop` | n/a — unreachable | **FAIL** | §R15c, run_id 10-6-r15c/2026-07-06 | Zero raising sites — code can never surface (F-10-6-4); dropped from the README table |
| R16 | :310 | `INVALID_ACTION_TYPE` | INDUCED | **PASS** | §R16, run_id 10-6-r16/2026-07-06 | — |

**Section 2 tally: 13 PASS / 5 FAIL / 0 EXCLUDED across 18 verdict rows** (16 README rows; R15 = 3 sub-cases). Honesty split carried from 10-6: 12 INDUCED / 5 SIMULATED / 1 n/a-unreachable — no simulated row recorded as induced. Every FAIL is a documentation-contract defect (dead or mislabeled code, broken fix clause), zero product-capability regressions; every code that CAN surface DID surface and every system state recovered.

---

## Epic-level roll-up

| Scope | PASS | FAIL | EXCLUDED | Rows |
| --- | --- | --- | --- | --- |
| README examples (Section 1) | 18 | 11 | — | 29 walked |
| README examples not walked (Section 1b) | — | — | 4 (each with reason) | 4 |
| Error table (Section 2) | 13 | 5 | 0 | 18 |
| **Total** | **31** | **16** | **4** | **51** |

- **Every FAIL is FILED, none absorbed** (N.5 policy): 10-1 F1-F6+B1; F-10-3-1..6; F-10-4-1..6; F-10-5-1..12; F-10-6-1..7 — 38 findings total across the epic, zero fixed in-epic except 10-2's single pre-declared scope (pre_state/revert).
- **Every FAIL anchor is honest in the README**: FAIL rows carry explicit FAIL/honest-broken documentation at their README site (verified tags with `(FAIL, documented honestly)` markers or rewritten honest-broken notes) — no illustrative output survives at any walked anchor.
- **Done-flip clause 2 discharged by this table**; clause 3 (verified tags) and clause 4 (limitations honesty) discharged by the 10-7 README sweep — see `10-7-walk-evidence.md`.
