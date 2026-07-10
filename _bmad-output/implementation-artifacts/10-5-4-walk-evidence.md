# Story 10-5-4 — Live Walk Evidence (delegated manual verification)

**Date:** 2026-07-10
**Mode:** Adam-DELEGATED ("Can you run the manual verification yourself") — orchestrator drove the live walk against the real local stack + production DB (`/data/mailbot.db`).
**Verdict proposed:** PASS WITH FINDINGS (see §Findings). Adam signs AC-1/AC-2 at Phase 3.5.

## Environment / honesty notes

- Stack up: mailbot-hermes / mailbot-api (healthy) / mailbot-ollama (healthy).
- **Code-load reality (load-bearing honesty note):** `docker inspect` shows `mailbot_api/` + `verbs/` are **bind-mounted rw** (live host code), but **`scripts/` is NOT mounted** — it is baked into the image, which predates this story. Therefore:
  - The shipped `mailbot_api/actions/resurrect.py`, `replay.py`, `reverter.py`, `db/queries.py` changes ARE live in the container and were exercised directly.
  - The `scripts/mailbot.py` CLI wrapper changes (the `_cmd_rederive` init swap + the `mailbot resurrect` subcommand) are NOT in the container. So the walk exercised the **underlying shipped functions the CLI wraps** (`init_pipeline_runtime`+`execute_rederive`, `resurrect_email`) directly via `python -c`, not the `mailbot <verb>` CLI surface. This is a faithful test of the shipped code paths; the CLI-wrapper-over-those-functions is thin and unit-tested (`test_rederive_cli_adapter_bootstrap_f10_6_3.py` drives `_cmd_rederive` itself; `test_resurrect.py::test_cmd_resurrect_cli_exit_codes` drives `_cmd_resurrect`). A future `docker build` (or mounting `scripts/`) is needed before the `mailbot rederive`/`mailbot resurrect` CLI verbs themselves run the fixed code in-container — filed as a finding.

## Checkpoint verdicts

### CP-1 [AC-1, F-10-6-3] `mailbot rederive` runs without crashing — **PASS (live)**

- `init_pipeline_runtime('/data/mailbot.db')` → adapter registry populated (`qwen2.5:3b-instruct-q4_K_M` registered). This is the exact step `_cmd_rederive` was missing (it called only `_load_policy_for_cli` → registry empty → `KeyError: no adapter registered` on every invocation).
- Real single-row dispatch: `plan_rederive(task='fine_class', since=2026-01-01)` → count=1; `execute_rederive` → **processed=1 succeeded=1 failed=0 aborted=False, zero errors, NO KeyError.** This exercises the `execute_rederive → ask_router → real Qwen adapter` path — the precise site that crashed pre-fix.
- Real `router_calls` row confirmed: `task_type=fine_class, model_chosen=qwen2.5:3b-instruct-q4_K_M, caller_origin=cli-rederive, outcome=retry_recovered, ts=2026-07-10T16:37:15Z`. Classification written: `class_fine='personal'`.
- **Spend:** $0 (qwen local).

### CP-2 [AC-2, F5/F6/B5] Resurrect the retained 10-1 walk subject — **PASS (local-DB verified; physical-Outlook is Adam's to eyeball)**

- Target unambiguously identified: **"The peaceful way to ship software, static outbound IPs and IPv6 in the CLI"** (Railway email), `deleted_at=2026-07-05T09:09:58Z`, `removed_reason='deleted'`, corroborating move action **id=4 `move_to_triage_folder`** (the 10-1 walk's action id=4). graph_id `…JKZe9rgAA`.
- `resurrect_email(GID)` (default path, corroborated by move action → no `--force`) → **ok=True.** BEFORE: `deleted_at='2026-07-05…', removed_reason='deleted'`. AFTER: `deleted_at=None, removed_reason=None`. Read-verb visible now (`deleted_at IS NULL`): **True.** No Graph write issued (local-DB-only repair).
- **Honesty scope:** verified the local DB row is repaired + read-verb-visible. The AC wording "verified in the Outlook client" — the *physical* email's presence in Outlook is Adam's to confirm by eye. Per 10-1/10-2 walk evidence the physical Railway email was already confirmed back-in-Inbox during those walks (sacrificial-folder move → manual restore); the F6 residue was purely the stale local DB row, now fixed. NOT overclaiming a physical-client check the orchestrator can't perform.

### CP-3 [AC-2 negative] `NO_MOVE_FAMILY_ACTION` guard — **PASS (live)**

- A real soft-deleted `removed_reason='deleted'` email with NO move-family `pending_actions` row → `resurrect_email` returns `ok=False, code=NO_MOVE_FAMILY_ACTION` (default path). `--force` NOT passed → the email stayed soft-deleted (no unwanted state change). Confirms CR-10-5-4-1 refuses to revive a phantom row for a possibly-permanently-deleted message.

### CP-4 [AC-2 idempotency] `NOT_SOFT_DELETED` on a live row — **PASS (live)**

- Re-resurrecting the now-live Railway row → `ok=False, already_live=True, code=NOT_SOFT_DELETED`. Not a silent double-success; no re-mutation.

### CP-5 [AC-3, F-10-6-2] replay `REPLAY_MOVE_TARGET_DELETED` — **PASS (code-L3 only; NOT reproduced live)**

- Every move-family `pending_actions` row in the production DB is `status=applied`, so `replay_action` refuses `ACTION_NOT_FAILED` before reaching the new move-family gate. Reproducing the branch live would require corrupting a prod row's status to `failed` — declined (avoid unnecessary destructive prod mutation). The branch is proven by integration test `test_replay_move_family_target_deleted_refuses_directs_to_revert` (green). Marked code-L3, honestly not claimed as a live production reproduction. (Optional checkpoint.)

## Findings

- **WALK-10-5-4-F1 (INFO → follow-up):** `scripts/` is not bind-mounted, so the `mailbot rederive` / `mailbot resurrect` **CLI verbs** in the running container still execute the pre-fix baked `scripts/mailbot.py`. The fixed logic lives in the bind-mounted `mailbot_api` modules (verified live) + the CLI wrapper (unit-tested), but a `docker build` (or adding a `scripts/` bind-mount) is required before the operator-facing CLI verbs themselves run the fix in this container. Not a code defect — a deploy/mount gap. File for the next image rebuild / CP-1.

## Real side effects (intended, not pollution)

1. One `fine_class` re-derivation (row → `class_fine='personal'`, one qwen router_call, $0).
2. The retained 10-1 Railway walk subject resurrected (local soft-delete cleared) — the deliberate B5 repair, discharging F5/F6.

No collateral mutations. CP-3 left its target soft-deleted (no `--force`). Stack healthy.
