# `policy.user-overrides.yaml` — operator-driven routing overrides

**Story 9-1 contract.** Companion to `router/policy.yaml`, merged at load time with shallow-leaf semantics. Designed to survive image-rebuild deploys: `policy.yaml` ships in-image (source-of-truth, gitted); `policy.user-overrides.yaml` is bind-mounted (operator-state, gitignored) and persists in the host filesystem regardless of which container image is currently running.

## Why a companion file

`router/policy.yaml` is checked into git and bind-mounted read-only from the host. It is the source-of-truth for routing decisions and changes via PR review only. Operator-driven tactical changes — e.g., `/model qwen draft_reply` (Story 9-4) — MUST persist across image rebuilds: editing `policy.yaml` in place would either (a) be overwritten on next deploy, or (b) require git mutations from inside the running container. Neither is acceptable.

The companion file pattern:

- **Baseline `router/policy.yaml`** — ships in-image (eventually) / bind-mounted read-only; gitted; source-of-truth
- **Override `router/policy.user-overrides.yaml`** — bind-mounted read-write; gitignored; operator-state, written by Story 9-4 `set_model_persistent`
- **Merge happens at load time** + on every hot-reload (`watchfiles` watches both files)
- **Audit log** records every swap with the post-merge effective version

## File location

| File | Host path | Container path | Mount mode |
|---|---|---|---|
| Baseline | `./router/policy.yaml` | `/app/router/policy.yaml` | `:ro` |
| Overrides | `./router/policy.user-overrides.yaml` | `/app/router/policy.user-overrides.yaml` | read-write |

Bind-mounts are declared in `docker-compose.yml` under `services.mailbot-api.volumes`. The override mount must be read-write so Story 9-4 `set_model_persistent` can atomically rewrite the file via `os.replace()`.

## File shape

```yaml
# router/policy.user-overrides.yaml
# Operator-state — gitignored. Edit by hand or via /model persistent (Story 9-4).
# Every field is OPTIONAL. Specify only the fields you want to override.

tasks:
  draft_reply:
    model: claude-opus-4-7
  coarse_class:
    lane: interactive
    max_tokens_out: 512
```

The schema (`UserOverridesEntry`) mirrors `PolicyEntry` field-for-field with every field marked `Optional[T] = None`. Pydantic enforces `extra="forbid"` so a typo like `modle: claude-opus-4-7` raises rather than silently no-ops.

## Merge semantics — shallow-leaf

Four contract points:

1. **Override leaves replace baseline leaves (per-field, NOT per-task-block).** Specifying `tasks.draft_reply.model` replaces only that one field; other `draft_reply` fields keep baseline values.

2. **Unknown tasks are dropped with a warning.** An override on a task key not present in the baseline emits `event="policy.user-overrides.unknown_task"` and is discarded. Defensive: protects against typos that would otherwise create phantom task entries.

3. **None/absent fields = baseline preserved.** Pydantic `model_dump(exclude_none=True)` defines "which fields were actually set." An explicit `model: null` in YAML is treated as "not specified."

4. **The merge is total.** Every baseline task survives unless explicitly overridden. There is no negation primitive — overrides cannot DELETE a task.

### Examples

**Single-field override:**

```yaml
# Baseline
tasks:
  draft_reply:
    model: claude-haiku-4-5-20251001
    prompt_version: v3
    escalate: false
    lane: interactive
    sensitivity: any

# Override
tasks:
  draft_reply:
    model: claude-opus-4-7

# Merged result
tasks:
  draft_reply:
    model: claude-opus-4-7           # ← replaced
    prompt_version: v3                # ← preserved
    escalate: false                   # ← preserved
    lane: interactive                 # ← preserved
    sensitivity: any                  # ← preserved
```

**Multi-field override:**

```yaml
# Override
tasks:
  coarse_class:
    model: claude-haiku-4-5-20251001
    lane: interactive

# Merged result (coarse_class only)
tasks:
  coarse_class:
    model: claude-haiku-4-5-20251001  # ← replaced
    prompt_version: v1                 # ← preserved
    escalate: false                    # ← preserved
    max_tokens_out: 256                # ← preserved
    lane: interactive                  # ← replaced
    sensitivity: any                   # ← preserved
```

## Failure handling — non-fatal-overrides

Per architecture AR-D11-1, baseline validation failures are HARD (raise + lifespan dies). Overrides validation failures are SOFT — by design:

| Failure mode | Behavior |
|---|---|
| Overrides file absent | Baseline returned, no `+overrides:` suffix in version |
| Overrides file empty | Same as absent |
| Overrides YAML malformed | `policy.user-overrides.parse_failed` logged; baseline returned |
| Overrides schema violation (e.g., `model: 42`) | Same — `parse_failed` logged; baseline returned |
| `extra="forbid"` violation (typo field) | Same |
| Unknown task in overrides | `policy.user-overrides.unknown_task` logged; that one task entry discarded; other overrides applied |

This asymmetric discipline (hard-baseline, soft-overrides) reflects the trust model: `policy.yaml` is reviewed and gitted; `policy.user-overrides.yaml` is operator-edited and can be partially-broken at any time without taking down the system.

## Audit log events

| Event | Trigger | Log level |
|---|---|---|
| `policy.startup.loaded` | Lifespan startup completes the initial load | INFO |
| `policy.reloaded` | Baseline-only change OR override no-op reload | INFO |
| `policy.user-overrides.swap` | Override file gained, lost, or its hash changed | INFO |
| `policy.user-overrides.unknown_task` | Override on a task not in baseline | WARNING |
| `policy.user-overrides.parse_failed` | Override YAML/schema/IO failure | ERROR |
| `policy.user-overrides.empty_entry` | Override entry with all fields None (no-op) | DEBUG |
| `policy.reload.failed` | Baseline `PolicyValidationError` on reload | ERROR |
| `policy.reload.loop.error` | Defensive catch-all in the reloader | ERROR |
| `policy.user-overrides.absent_at_runtime` | Override file deleted at runtime (Story 9-1.5 F35 closure) | WARNING |

## Version-suffix derivation

The post-merge `PolicyTable.version` field carries provenance:

- **No overrides** (file absent OR empty): `version = "<baseline.version>"` (no suffix)
- **Overrides present** (any content, even `tasks: {}`): `version = "<baseline.version>+overrides:<sha256[:8]>"`

The SHA-256 first-8-hex-chars is content-addressed: same YAML content → same suffix; any byte change (including whitespace) → new suffix. This flows into:

- `router_calls.policy_version` (if such a column is added) — every call records which merged policy it ran under
- Story 9-6 `benchmark_runs.cohort_key` — fourth tuple element distinguishes "baseline-only" cohorts from "with-override" cohorts so Pareto/DEMOTE-PROMOTE suggestions don't silently mix them

## Forward references

- **Story 9-4** is the consumer of this contract — `set_model_persistent` writes to `router/policy.user-overrides.yaml` atomically via `os.replace()` + tempfile + `fsync`, then relies on the hot-reload (this story's AC-3) to make the change effective within 2 seconds.
- **Story 9-6** consumes the post-merge `version` for `benchmark_runs.cohort_key.router_policy_version`.
- **Story 9-7+** (eval/calibration) need cohort_key consistency to compute DEMOTE/PROMOTE verdicts against comparable runs only.

## Hot-reload contract limitation — file-must-exist-at-startup

`watchfiles.awatch` raises `FileNotFoundError` on any non-existent path. As a result, the override file MUST EXIST on the host filesystem at the moment `mailbot-api` starts up in order to be watched. Workflow implications:

| Scenario | Hot-reload picks up changes? |
|---|---|
| Override file exists at startup, content changes | ✅ Yes |
| Override file exists at startup, file deleted at runtime | ⚠ Detected: ONE `policy.user-overrides.swap` event swaps to baseline-only, ONE `policy.user-overrides.absent_at_runtime` WARNING fires, then subsequent watchfiles spurious fires are silently coalesced (Story 9-1.5 F35 closure). Operator must restart `mailbot-api` to re-arm the watcher. |
| Override file ABSENT at startup, operator creates it at runtime | ❌ No — `mailbot-api` must restart to watch it |

**Operator-flow implication for Story 9-4:** the first `/model <task> <model>` call against a fresh deploy (where the override file doesn't yet exist) will create the file but the change will NOT take effect until the next mailbot-api restart. Story 9-4's verb response should surface this requirement explicitly. Subsequent calls (against an existing file) propagate via hot-reload within ~2 seconds.

**First-deploy bootstrap:** consider `touch router/policy.user-overrides.yaml` in `setup_vps.sh` (or equivalent) so the file exists from day one. Empty file is fine — it's a no-op.

**Runtime delete recovery (Story 9-1.5 F35 closure):** if an operator directly `rm`'s `router/policy.user-overrides.yaml` while mailbot-api is running, the loop emits a single `policy.user-overrides.absent_at_runtime` WARNING and stops emitting further per-fire log lines for the deleted path. To restore the override surface, the operator must (a) recreate the override file on disk (or the bootstrap `cp .example`) AND (b) restart mailbot-api so `watchfiles.awatch()` can re-bind a fresh descriptor to the new file. This restart is the same F33 contract that applies to first-time override creation.

## Hot-reload race semantics

Architecture AR-D11-2 applies symmetrically across both files: a Router call captures the snapshot at dispatch and uses that snapshot for the entire call's lifecycle. A hot-reload (or override file change) that happens mid-call does NOT affect the in-flight call — it sees the post-swap snapshot only on its NEXT dispatch.

This is intentional. The alternative — atomic mid-call swap with a lock — would be a per-call performance cost for a race window measured in milliseconds. The audit log + `router_calls.policy_version` field make the swap observable post-hoc.
