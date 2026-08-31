# MailBot

**A personal email agent that triages your inbox, drafts replies, and takes instructions in plain language over Discord — built to be cheap to run, safe to trust, and honest about what it can't do.**

MailBot syncs your Microsoft Outlook inbox, classifies and prioritizes every message through a **cost-disciplined multi-model LLM router**, and lets you act on your mail conversationally — with a layered authorization model that never sends or deletes anything without your consent, and a privacy invariant that keeps sensitive email bodies off the cloud entirely.

> **Status:** runs live on a local Docker stack against a real mailbox; VPS deployment is the remaining ship gate. This is an actively developed personal project — see [Current status & limitations](#current-status--limitations), which documents candidly where the product works and where it doesn't. That honesty is deliberate: see [Why this README tells you what's broken](#why-this-readme-tells-you-whats-broken).

```
  Outlook ──Graph delta sync──▶ SQLite ──ingest──▶ triaged, scored inbox
                                   │       (Qwen classify · Haiku enrich)
                                   │
  You, on Discord ◀── chat + MCP verbs ──┤   chat/tool-call lane: Claude Haiku
   "show me unread"                       │
   "draft a reply"  ──propose → grant → cool-off──▶ mailbox write-back
   "archive the newsletters"                        (tiered authorization)
```

---

## Three ideas it's built around

MailBot is small in scope — one person's inbox — but it's a deliberate exercise in three things that are hard to get right in an LLM product.

### 1. Cost-disciplined routing

Every LLM call flows through a single `ask_router` entry point, and **nothing bypasses the gates**. Work is routed to the cheapest model that can do it:

- **Local Qwen 3B** (free, on-host) — classification, sensitivity gating, intent parsing, summaries.
- **Claude Haiku** — the interactive chat/tool-call lane, importance scoring, action extraction.
- **Claude Opus** — draft replies and tone matching.

On top of routing sits a stack of cost controls: a response cache, a **per-call refusal threshold** ($0.20), a daily soft-warning, a **$30/month hard cap** that trips a bounded-cost *degraded mode* (paid lane falls back to the local model, safety gates unchanged), per-lane rate limits, and a loop detector. A real interactive "find my unread emails" turn costs about **$0.0037** — cents, not dollars — inside that hard cap.

> The founding thesis was "route the cheap work to a free local model." Testing narrowed it honestly: a 3B model *can't* faithfully execute an agent tool-call turn, so the cheap lane became a cheap *paid* model (Haiku at fractions of a cent) rather than a free one. The router architecture held; the assumption behind it got corrected by evidence. That arc is documented, not hidden.

### 2. Safety you can audit

MailBot can touch your real mailbox, so every mutation is **tier-classified** and nothing destructive happens on the model's say-so alone:

| Tier | Actions | What it takes |
| --- | --- | --- |
| 0 | read, search, count | free |
| 1 | mark read, categorize, triage-move | auto-applied, revertible for 24h |
| 2 | archive, batch move | a scoped grant you approve |
| 3 | **send, delete** | grant + explicit confirmation (sends also cool off 60s) |

Grants are **scoped** (to specific emails, one action, a bounded expiry), sends are held through a cooling-off window enforced to the second, and there's a hard cap of 20 sends/day. A cross-process kill-switch (`pause`/`resume`) stops all LLM dispatch instantly.

**The privacy invariant:** email bodies classified *sensitive* or *confidential* never reach a cloud API silently. Confidential bodies never leave the machine, period; sensitive ones require an explicit, single-use, per-email confirmation before any cloud task runs.

### 3. Honesty, measured

This is the part most projects skip. MailBot ships with an **evaluation harness** for the thing that's genuinely hard to pin down — *is the LLM actually making good decisions?* — separated cleanly from the deterministic "does the API call work" tests:

- A synthetic email **corpus** with hand-labeled ground truth (real inbox data is anonymized on-host and never committed — only synthetic templates are public).
- A **benchmark runner** that scores every (email × task × model × prompt) cell through the real router, with per-cell cost and token accounting.
- **Judge calibration done right:** for the subjective tasks (draft quality, summary quality), the LLM-as-judge is validated against a second evaluator using **Krippendorff's alpha** inter-rater agreement, with a drift tripwire that fires if the judge silently moves between runs. Most LLM-judge setups ship with *no* agreement measurement; this one measures it and quarantines contaminated baselines.

---

## Talking to MailBot

You talk to it in **plain natural language** on Discord — there's no slash-command surface (Discord's `/` prefix belongs to the host runtime). You just say what you want:

```text
You:  anything important this week?
MailBot:  Three important emails this week (importance ≥70):
          Stripe — Failed $10.19 payment. Importance: 86
          LinkedIn — embedded-systems job application prompt. Importance: 85
          Hostinger — your VPS expired. Importance: 80
          Two action items: fix the Stripe payment and your VPS is down.

You:  draft a reply to "Coffee Thursday?"
MailBot:  Hey — Thursday at 3pm works great. I'll meet you near the office.
          Does this work, or want me to adjust?
You:  send
MailBot:  Reply queued (action 14, cooling-off active). Say "cancel 14"
          in the next 60 seconds if you change your mind.
```

Read and status intents are parsed freely; control verbs that touch your mailbox or the kill-switch (`cancel`, `pause`, `resume`, `yes, escalate`) are matched by exact phrase so they're understood **reliably**, not just usually. A daily digest lands at 08:00 automatically.

Full walked transcripts — including the ones that *fail* — are in [docs/STATUS.md](docs/STATUS.md).

---

## Architecture

- **3-container Docker stack:** `mailbot-hermes` (Discord adapter, agent runtime, cron), `mailbot-api` (router + [MCP](https://modelcontextprotocol.io) verbs + Graph sync worker; sole holder of the Anthropic key), `ollama` (local Qwen 3B + embeddings).
- **Router** (`router/policy.yaml`, hot-reloaded): 17 task types → model assignments, overridable per-task at runtime.
- **Storage:** stdlib `sqlite3` with WAL + raw-SQL migrations, no ORM by design.
- **Enforced code boundaries** (ruff-checked): router / sync / db / config / audit isolation — the LLM adapter is the only site that imports `anthropic`/`ollama`.
- Python 3.12, FastAPI, Pydantic v2.

```
mailbot_api/          db/ · router/ · sync/ · verbs/ · ingest/ · actions/
router/               runtime routing config (policy.yaml + overrides)
evals/ benchmark/     eval corpus, rubrics, calibration + benchmark runner
tests/                pytest suite
docs/                 deep dives + full walked-evidence STATUS
```

### Run it

```bash
git clone <this repo> && cd mailbot
python3.12 -m venv .venv && source .venv/bin/activate   # Windows: py -3.12 -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r requirements.txt

make test      # pytest
make lint      # ruff + mypy --strict
make local     # start the local dev stack
```

First-time setup (Entra app registration, Outlook token minting, `.env`) is in [docs/](docs/). MailBot is Outlook-specific today.

---

## Why this README tells you what's broken

Most project READMEs are marketing. This one has a [limitations section](#current-status--limitations) that names, by ID, exactly where the product diverges from its own documentation — because MailBot was built with a **walked-evidence discipline**: features are verified by driving them end-to-end against a real mailbox and recording what actually happened, including the failures. Claims in the detailed docs carry `verified` tags tied to specific runs.

The point of the project isn't a flawless demo. It's the engineering judgment around a hard, non-deterministic system: routing for cost, gating for safety, and *measuring* whether it works instead of asserting it. Honesty about the gaps is part of that discipline, not a disclaimer bolted on.

---

## Current status & limitations

An honest snapshot (mid-2026). The [full walked-evidence log is in docs/STATUS.md](docs/STATUS.md); highlights:

- **Local Docker only.** Live-verified on the dev machine against a real mailbox; VPS deployment is the final ship gate and hasn't happened yet.
- **Send flow works end-to-end** — draft → your confirmation → 60s cooling-off (enforced to the second) → real Graph dispatch → confirmed in the recipient inbox; in-window cancel aborts cleanly.
- **Tier-2 batch archive: the writes work, the approval choreography doesn't.** Scoped grants and real archival are verified, but the agent currently mints the grant without soliciting your approval first, and can narrate success before the write applies. The API-layer grant gate — not the conversational "yes" — is what actually blocks unapproved writes.
- **Privacy invariant holds** — 12 escalation attempts, every one refused, zero body egress in the last walk. Confidential refusal is clean; the sensitive-escalation *chat* path was rebuilt at the API layer and is pending a final live walk.
- **Read-family gaps:** unread state is now synced, but delta-sync currently ingests fewer rows than the live mailbox holds; person-lookup by display name isn't implemented yet.
- **Benchmark calibration is ongoing** — model-per-task assignments carry promote/demote hypotheses still being measured; expect routing to shift as results land.

---

## License

[Apache-2.0](LICENSE) © 2026 Adam Maroni.

MailBot is a personal project shared for reference and learning. Issues and observations are welcome; it is not (yet) a supported product.
