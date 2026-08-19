# Mailbot — Core Concepts

A plain-language glossary of the load-bearing concepts in the router / cost-discipline core. Each entry says what the thing is, where it lives in code, and what problem it solves. Written to be read cold by an engineer new to the project.

---

## Adapter

The uniform interface `ask_router` uses to call any supported LLM the same way, regardless of provider. Each concrete adapter (`OllamaAdapter` for local Qwen, `AnthropicAdapter` for Claude Haiku/Opus) hides its provider's specific API behind the shared `ModelAdapter` protocol and returns the same normalized `AdapterResponse`. This keeps `ask_router` provider-agnostic: it never has to know how any individual model's API works.

- **Code:** `mailbot_api/router/models.py` — `ModelAdapter` (protocol, ~L289), `OllamaAdapter` (~L653), `AnthropicAdapter` (~L1030), `AdapterResponse` (~L193).
- **Naming trap:** "OpenAI" in this repo (e.g. `OpenAIToolCall`) refers to the OpenAI-compatible **wire format** — the `/v1/chat/completions` JSON shape that Ollama/Qwen emit — **not** a provider. There is no OpenAI adapter. `Anthropic`/`Ollama` name *who you call*; `OpenAI` names *what the message looks like*.

---

## Pause

A global, system-wide flag (not per-request) that stops the bot from calling any model. When set, `ask_router` short-circuits *before adapter dispatch*, so no `ModelAdapter` is ever invoked. It's a guardrail that prevents two things at once: (1) spending money on LLM token consumption, and (2) triggering write actions against the mailbox (e.g. Microsoft Graph writes — sending or moving mail). Pause **fails closed**: if it can't read its own state (e.g. a DB error), it treats the system as *paused*, because a guardrail whose job is to stop writes must err toward stopping them rather than silently re-opening the write path.

- **Code:** `mailbot_api/router/pause.py` — `PauseState` class, `get_pause_state()` (the cross-process source-of-truth read).
- **Not to be confused with** per-request sensitivity classification (`SensitivityToken`). Pause is a *global on/off switch*; sensitivity is *per-request criticity*.
- **Cross-process gotcha:** the per-process in-memory mirror can go stale (a worker that never ran the pause verb keeps dispatching while the API process is "paused" — the F4 bug). `get_pause_state()` hits the DB singleton row at decision time to close that window.

---

## Graph (Microsoft Graph)

Microsoft's REST API that lets external applications communicate with Microsoft 365 services; in Mailbot it's how the bot reaches the user's Outlook mailbox. Graph calls split into two kinds: a **Graph read** fetches data (list emails, read a thread) with no lasting effect, while a **Graph write** mutates the mailbox (send, move, delete, mark-read) — a real, destructive, user-visible side effect. This read/write split is load-bearing for the whole safety design: it's the *writes* that pause, budget refusals, and sensitivity gating exist to stop, because a wrongly-sent or wrongly-deleted email can't be undone — whereas a read costs nothing and harms nothing.

- **Code:** `mailbot_api/sync/graph_client.py` (read side — sync/ingest), `mailbot_api/actions/graph_write.py` (write side — the `GraphWriteAdapter` protocol the drainer dispatches through).
- **Ties to:** [Pause](#pause) exists primarily to stop Graph *writes*; the same read-vs-write asymmetry is why writes are gated and reads are not.

---
