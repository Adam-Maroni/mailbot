# F-10-6-1-W1 — qwen-on-CPU exceeds the 30s Ollama adapter timeout on full-context Discord tool-calls

**Filed:** 2026-07-13, from the Story 10-6-1 (AI-1 Phase 2) Discord live walk.
**Severity:** MEDIUM (blocks the cheap-lane end-user experience on this host; NOT a routing or safety regression).
**Class:** performance / infra. Epic 10.6 (Capability Reachability) follow-up. Adam-decided disposition (2026-07-13): file as a separate finding, keep 10-6-1 `done`.

## What 10-6-1 proved (context — this finding is NOT a 10-6-1 AC failure)

The Discord round-trip **confirmed AC-5 at the real user path**: a message typed in Discord ("find my unread emails") flowed persona → Router → and was **routed to `qwen2.5:3b-instruct-q4_K_M`** with `model_chosen_reason=policy:chat_completions_tool_call:default` — the cheap local lane is genuinely REACHED (DB `router_calls` rows at 2026-07-13T10:11:57 / 10:12:30 / 10:13:05Z, all `model_chosen=qwen`). Contrast the 2026-07-11 pre-fix log: HTTP 502 "the local fallback **cannot serve tools**". Now it serves tools; the reachability gap is closed. 10-6-1 stays `done`.

## The finding

On this CPU-only host (`ollama ps` → `100% CPU`, no GPU), qwen serving a **full-context** tool-call is slower than the hard-coded 30s Ollama adapter timeout:

| Payload | qwen latency |
|---|---|
| Minimal (1 tool, short prompt) — my direct-endpoint AC-5 proof | ~2.9s ✅ |
| Full context (~11 MCP tool schemas + sizable system prompt), 1 tool-call | **~20.0s** |
| Real Discord turn (full Hermes persona prompt + history + persona chains SEVERAL sequential tool-calls per turn) | **> 30s → `AdapterTimeout`** |

Discord surfaced it as: `HTTP 502 … AdapterTimeout: adapter timeout: model_id=qwen2.5:3b-instruct-q4_K_M timeout_seconds=30.0`, after Hermes's 3-retry ladder (each retry re-times-out).

**Root of the 30s number:** `mailbot_api/router/registry.py:52` and `:64` construct both `OllamaAdapter`s with `timeout_seconds=30.0` (default also at `models.py:512`).

**Secondary observation (not the finding, but noted):** in the full-context repro qwen picked `pull_pending_notifications` instead of `find_emails` — the ~90% tool-selection fidelity 10-6-1 documents on large prompts. Harmless (the model-independent propose_action → drain safety gate is the backstop), but it shows the 3B model is working hard on a big prompt, which compounds latency.

## Why this was not caught before the walk

- 10-6-1's dev tests + my direct-endpoint verification used **minimal** tool payloads (~1-3s) — well under 30s. The timeout only bites on the **full Hermes tool surface + multi-call turns**, which only the real Discord path exercises. Classic "wired+tested ≠ reached" tail — the reachability fix REACHED a new latency regime.

## Options (for the follow-up story — not decided here)

1. **Bump the Ollama adapter timeout** (`registry.py:52,64` 30s → e.g. 90-120s). Simplest. Trade-off: a genuinely-failing turn now hangs that long before erroring; and Hermes's own 3-retry ladder multiplies wall-clock.
2. **Trim the Hermes tool surface** offered per turn (fewer tools → smaller prompt → faster qwen ingest + fewer mis-picks). Structural; touches Hermes-config.
3. **GPU / faster host** for ollama. Removes the constraint entirely; infra/deploy decision (ties to CP-1 / local-viability priority).
4. **Smaller/faster local model** or a constrained-decoding shim for tool-calls. Larger scope.
5. **Reduce per-turn tool-call chaining** in the persona (dispatch fewer sequential calls).

Recommend (1) as an immediate unblock to re-walk end-to-end, with (2)/(3) as the durable fix — but that's the follow-up story's call.

## Repro

```
# routing proof (all qwen, all timed out):
docker exec mailbot-api python -c "import sqlite3,os; c=sqlite3.connect(os.environ['MAILBOT_DB_PATH']); print(c.execute(\"SELECT model_chosen,outcome FROM router_calls WHERE task_type='chat_completions_tool_call' ORDER BY rowid DESC LIMIT 3\").fetchall())"

# latency repro (full context ~20s, minimal ~3s): see the walk transcript in story-run-flags.md § Story 10-6-1 Manual Verification.
```

## Relationship

Sibling to Story **10-6-3** (scratch/ ruff — unrelated chore) under Epic 10.6. Does NOT reopen 10-6-1. Feeds the Epic 10.6 done-flip discussion: clause 3 ("cheap lane REACHED") is satisfied by the routing proof; this finding is about the cheap lane being *usable end-to-end within the latency budget on the target host*, which the retro/Adam may fold into the clause-3 acceptance or track as a CP-1/deploy-gated perf item.
