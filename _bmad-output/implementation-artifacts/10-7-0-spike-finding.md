# Story 10.7.0 — Characterization Spike Finding: Harness-Fixable vs. Qwen-3B Ceiling

**Verdict: HARNESS-FIXABLE IN PRINCIPLE, BUT NOT BY THE CHEAP LEVER — and the real root cause is SELECTION-at-scale, not the `<tool_call>`-text FORMAT defect.** On a realistic 26-verb surface, qwen fixates on a single wrong tool (`pull_pending_notifications`) for "find my unread emails" and **no cheap lever tested recovers it** (weak system prompt, strong enumerating system prompt, and a natural-language `find_emails` description rewrite all measured **0/N correct**). The system-prompt lever that looked "decisive" on a 5-tool stub (14/20→20/20) is a **small-surface artifact** — it does not generalize to the real surface. This does **not** cleanly license "do-not-fire 10.7.4"; the epic needs a focused follow-up experiment (below) before its fire-list is treated as final.

**Generated:** 2026-07-15 by claude-opus-4-8 (dev), autonomous-story-run. **REVISED after MANDATORY code-review** (reviewer sonnet-5 ≠ dev opus-4-8) flagged that the original finding tested only a 5-tool stub and over-inferred "surface-coupled → no 3B ceiling." The review was correct; this revision re-ran against the real MCP surface and reversed the headline.

**Method:** direct-drive of the LIVE local `mailbot-ollama` qwen (`qwen2.5:3b-instruct-q4_K_M`) at temperature 0 via `ollama.AsyncClient`, bypassing Router/Hermes to isolate the MODEL. Real 26-verb surface pulled live from the `mailbot-api` FastMCP server (`localhost:8000/mcp/`, `scratch/mcp_walk_106.py` pattern). Harness: `scratch/qwen_toolcall_spike_107.py` (spike scaffolding, never staged). Run logs: `scratch/10-7-0-realsurface-run.log`, `-strong.log`, `-betterdesc.log`, `scratch/10-7-0-tool-descriptions.txt`.

> **Sample-size honesty (review Finding #5):** each "N" below = (distinct turns) × (temp-0 deterministic repeats). Temp 0 makes each (turn, surface, system) cell deterministic, so repeats confirm *no drift*, they are not independent trials. The real independent axis is the **4 unread-email paraphrases**. Read the ratios as "4 turns, each repeated" — not 20/32 independent samples.

---

## 1. The measurement that flips the verdict — 5-tool STUB vs. REAL 26-verb surface (AC-1, AC-2)

| Mode | Surface | System prompt | right+structured | wrong pick | text-emission |
|---|---|---|---|---|---|
| baseline | 5-tool stub | none | **14/20** | 6/20 (`count_emails`) | 0 |
| sysprompt | 5-tool stub | strong (enumerate) | **20/20** | 0 | 0 |
| droppeer | 5-tool stub (no send_message) | none | 15/20 | 5/20 | 0 |
| **realsurface** | **real 26 verbs** | none | **0/32** | 32/32 (`pull_pending_notifications`) | 0 |
| **realsurface_persona** | **real 26 verbs** | persona boilerplate | **0/32** | 32/32 (`pull_pending_notifications`) | 0 |
| **realsurface_sysprompt** | **real 26 verbs** | persona + ablated hygiene | **0/32** | 32/32 (`pull_pending_notifications`) | 0 |
| **realsurface_strong** | **real 26 verbs** | strong (enumerate find_emails) | **0/12** | 12/12 (`pull_pending_notifications`) | 0 |
| **realsurface_betterdesc** | **real 26 verbs** | none, find_emails desc rewritten | **0/16** | 16/16 (`pull_pending_notifications`) | 0 |

**The 5-tool stub result does not generalize.** On the real 26-verb surface, selection collapses to **0 correct across every mode tried** — qwen picks `pull_pending_notifications` 100% of the time. Even the strong enumerating prompt ("call find_emails… never send_message") and a natural-language `find_emails` description rewrite fail 0/N. This is exactly the over-inference the code-review flagged (its Finding #1): a null result on a 5-tool stub did NOT license concluding the defect was surface-coupled or that the model can select correctly with a prompt.

**Why `pull_pending_notifications` wins** (`scratch/10-7-0-tool-descriptions.txt`): its description leads "**Pull up to limit… urgent-tier notifications… FIFO**" — qwen maps "find my **unread** emails" onto "**pull** pending **notifications**." Meanwhile `find_emails` leads with implementation jargon — "Return up to `limit` email **projections** matching `filter`… **Rule J** projections only" — and never says *unread*, *search*, or *inbox*. The attractor is dominant: rewriting `find_emails`'s description to natural language did **not** overcome it (0/16), so this is not a one-line description tweak.

## 2. SELECTION vs. FORMAT attribution — corrected (AC-2)

- **FORMAT (`<tool_call>` text):** did NOT reproduce on ANY direct-drive mode (0 text-emission across 5-tool AND 26-verb surfaces, 152 calls total). **Honest scope (review Finding #1/#2):** this means the `<tool_call>`-as-text emission observed at the walk (router_calls id=14937) is **NOT reproducible via direct ollama drive under any surface/prompt tested here** — it appears specific to the real Hermes chat-template / request assembly, which this spike did not replicate. It is *plausibly* Hermes-template-coupled, but the spike **cannot prove** it is absent from the model under Hermes's actual templating. The rescue parser (10.7.1) therefore remains justified as defensive.
- **SELECTION (right tool): this is the load-bearing defect, and it is SEVERE at real scale.** Root cause is a combination of (a) `find_emails`'s poor, jargon-first tool description and (b) a dominant distractor (`pull_pending_notifications`) whose wording over-matches "unread/pull" — with qwen-3B unable to disambiguate among 26 tools even with prompt help. Whether the residual after description-fixes is a *model* ceiling or still a *harness* (description/surface) problem is **not yet resolved** — see §4.

## 3. Lever A/B results — corrected (AC-3, AC-4)

- **System prompt (10.7.2): NOT the fix at real scale.** Decisive on the 5-tool stub (→20/20), **0/N on the real surface** in both ablated and strong forms. The stub result was a surface-size artifact. Do NOT treat a system prompt as the load-bearing clause-3 fix on the evidence here.
- **Tool-description rewrite (new lever, surfaced by the real-surface run): tested, insufficient alone.** Rewriting `find_emails`'s description to natural language did not flip selection (0/16) because the `pull_pending_notifications` attractor still dominates. The untested-but-promising variant is rewriting **both** — sharpen `find_emails` AND de-attract `pull_pending_notifications` (and possibly trim the surface so notification/digest verbs aren't offered on a "find emails" turn). This is a `mailbot_api` MCP-registration + hermes-config lever, $0.
- **Rescue parser (10.7.1): feasibility still unmeasured — no direct-drive text to parse** (0/152). Justified as defensive against the Hermes-template path only; the sole wire-shape evidence remains the single walk sample (id=14937). Honest: this lever's *need* is unproven by this spike; its *cost* is low.
- **Surface trim (10.7.3): re-opened.** On the stub, dropping `send_message` didn't help (the mis-pick was a sibling verb). But on the real surface the mis-pick is `pull_pending_notifications`, a notification verb that arguably should NOT be on a chat "find emails" surface at all — so surface-scoping is back in play as a *selection* lever, contrary to the original finding's "do-not-fire." Needs the §4 experiment to confirm.
- **Temp-0 argument fidelity (AC-4): PRESERVED where selection succeeded** — 3/3 exact arg round-trip incl. a Graph-style id under the stub sysprompt lever. **Honest caveat (review Finding #3):** 3 samples cannot confirm the invariant against the AI-1 baseline's own ~10-20% silent-corruption rate on adversarial ids; this is a spot-check, not a fidelity SLA. A real fidelity re-check at AI-1-comparable N is **owed at 10.7.2 implementation time** and is flagged as such, not claimed discharged here.

## 4. Recommendation (AC-5) — corrected fire-list + a required follow-up experiment

**The original "HARNESS-FIXABLE via system prompt, do-not-fire 10.7.4" is WITHDRAWN.** Corrected disposition:

1. **REQUIRED before the epic fire-list is final — a focused selection-recovery experiment** (small, $0, can be folded into 10.7.2 or a 10.7.0 follow-up): on the **real surface**, test the combined lever — (a) rewrite `find_emails` to natural language, (b) de-attract / rewrite `pull_pending_notifications`, (c) trim the chat surface so notification/digest/cron verbs are not offered on an email-reading turn — and measure whether selection recovers to an acceptable rate. This directly resolves the open "harness vs. ceiling" question that the stub falsely answered.
2. **10.7.3 (surface trim) — RE-OPENED, likely FIRE.** The real mis-pick is a notification verb that plausibly shouldn't be on the surface; scoping the chat turn to email-reading verbs is now a live selection lever (reversing the original do-not-fire).
3. **10.7.2 (system prompt) — DEMOTED from primary.** Necessary-but-insufficient at real scale; keep it as one ingredient combined with description/surface fixes, not the load-bearing lever. Must re-validate under Hermes concatenation (review Finding #9) and re-check temp-0 fidelity at real N (review Finding #3).
4. **10.7.1 (rescue parser) — KEEP as defensive** (unchanged), pending a real-Hermes-path `<tool_call>`-text sample.
5. **10.7.4 (model swap) — DO NOT CLOSE.** "No 3B ceiling" is **not** established — it was downstream of the withdrawn surface-coupling inference. The real-surface data (0/N even with a strong prompt) is *consistent with* a 3B disambiguation ceiling at 26 tools; the §4.1 experiment must run first to distinguish "fixable by description/surface work" from "genuine ceiling." If §4.1 fails to recover selection, 10.7.4 is back on the table (staying LOCAL/$0 per `project_local_model_is_safety_net`), and if even a bigger local model fails, escalate to Adam as a founding-assumption decision.
6. **CANDIDATE LEVER (Adam-proposed 2026-07-15) — hierarchical / tree-structured tool selection.** Instead of presenting all 26 tools flat, present a small *category* menu first (e.g. read-email / notifications / send / admin), then only the 3–5 tools inside the chosen branch. This directly matches the measured failure mode ("poor discrimination across a 26-way flat choice"): qwen scored 14–20/20 on 5-tool menus but 0/N on 26, so shrinking every individual decision to a small menu is the strongest scalable form of the §4.1 "trim the surface" idea. **The catch (must be measured, not assumed):** the tree does not remove the hard choice — it moves it to the *top split*, which is exactly where qwen already failed (it heard "find my **unread** emails" and jumped to the *notifications* category). A wrong first turn is unrecoverable (the model never sees `find_emails`). So this lever helps **only if the top-level categories are ones qwen can reliably discriminate** — an empirical question. **De-risk cheaply first:** using the existing `scratch/qwen_toolcall_spike_107.py` harness ($0), give qwen ONLY the ~4 category choices (sharp plain-English category descriptions) and measure whether "find my unread emails" routes to the email-reading branch. If it nails the top split → the tree is likely the answer; if it fumbles the top split like the flat menu → the tree alone won't save it (and that is itself strong evidence toward a genuine 3B ceiling → 10.7.4). **Cost note:** a tree implies multiple model round-trips per turn (pick category → pick tool), which adds latency on the CPU-bound local model — weigh against the Epic 10.6 latency work (`project_qwen_cpu_toolcall_latency`).

**Net:** the epic does NOT collapse to "just 10.7.2." The evidence points at a **description + surface-scoping** fix (10.7.3 re-opened + tool-description work) as the most promising cheap path; the **hierarchical/tree tool-selection** lever (item 6) is the stronger, more scalable variant of that same "fewer choices at once" principle and is worth measuring (top-split probe first) if the flat description/trim fixes don't get selection reliable enough. 10.7.4 stays explicitly open pending the §4.1 experiment.

### 4.2 Top-split probe RESULT (2026-07-15, post-close follow-up) — points HARNESS-FIXABLE

Ran the item-6 top-split probe on the live model (`scratch/… tree`, log `scratch/10-7-0-topsplit.log`): offer qwen ONLY 4 category choices (`email_reading` / `notifications` / `email_actions` / `admin`, sharp plain-English descriptions that frame notifications as "app-generated alerts, NOT your emails"), and measure whether "find my unread emails" + paraphrases route to `email_reading`.

| Mode | correct category (`email_reading`) | structured |
|---|---|---|
| topsplit (bare, no hint) | **20/20** | 20/20 |
| topsplit_hint (+ ablated hygiene prompt) | **20/20** | 20/20 |

**The same model that scored 0/N on the flat 26-tool surface makes the coarse 4-way split perfectly (20/20).** This is strong evidence the defect is **discrimination-across-a-large-flat-option-set, NOT comprehension and NOT a hard 3B ceiling** — collapsing the choice to a few well-separated, well-worded categories recovers selection completely. Critically, the top split is exactly where the failure could have recurred (qwen had jumped to *notifications* on the flat menu); it did **not**, because the category descriptions separate "your emails" from "app-generated alerts." **The `pull_pending_notifications` distractor problem dissolves with category-level wording.**

**Implications for the fire-list:**
- **HARNESS-FIXABLE is now the leading hypothesis** (was "unresolved"). 10.7.4 (model swap) drops toward unlikely — keep open only as a fallback, no longer co-equal.
- **A tree/hierarchical design is viable** (top-split proven). It is also indirect evidence the cheaper flat **trim + description** lever (10.7.3 + description work) can work, since both rest on "fewer/clearer choices."
- **Residual still owed (do NOT over-claim):** this proves qwen picks the right *branch*, not yet the right *leaf tool inside* the branch. That is a 3–5-tool menu — the regime where it already scored 14–20/20 — so low risk, but a leaf-level probe (offer the ~4 email-reading tools, confirm `find_emails` over `count_emails`/`get_thread`) should run before committing the design.
- **Cost:** a true tree = 2 model round-trips/turn on the CPU-bound local model — weigh against Epic 10.6 latency work (`project_qwen_cpu_toolcall_latency`). A single well-scoped flat menu (if it tests reliable at the leaf level) avoids the extra hop.

### 4.3 Leaf-level probe RESULT (2026-07-15) — the branch is NOT free; combination fix needed (still no ceiling)

Ran the owed leaf probe (`scratch/… leaves`, log `scratch/10-7-0-leaf.log`): offer ONLY the 5 real email_reading tools (`find_emails`, `count_emails`, `get_thread`, `get_sender_summary`, `hydrate_email`) with their **real production MCP descriptions** (incl. find_emails's jargon "email projections… Rule J"), and measure whether qwen picks `find_emails` for "find my unread emails".

| Mode | find_emails correct | wrong pick | no tool (just chatted) |
|---|---|---|---|
| leaf (bare, real descriptions) | **0/20** | 11 (count_emails / get_thread) | 9 |
| leaf_hint (+ ablated hygiene prompt) | **15/20** | 5 (count_emails) | 0 |

**The leaf choice is NOT free — this corrects the §4.2 "low risk" optimism.** With the bare real descriptions qwen scored 0/20: it either picked a sibling or **didn't call any tool at all** (9×), instead starting to chat ("To find your unread emails, I will need to query… how many do you want?"). The jargon description actively pushed it toward a clarifying question rather than acting. **But a light hygiene prompt recovered it 0→15/20** — so the leaf level is fixable, it just genuinely needs help.

**The consistent pattern across all three probe levels:**
- Coarse 4-category split → works on **good descriptions alone** (20/20, no prompt needed).
- 5-tool leaf pick → needs **good descriptions AND/OR a prompt nudge** (real jargon descriptions alone = 0/20; + light prompt = 15/20).
- Flat 26 → fails even with a strong prompt (0/N) — too many choices at once.

**Conclusion: HARNESS-FIXABLE, but by a COMBINATION, not a single lever.** The fix is (a) shrink each choice (tree or scoped flat menu) + (b) fix `find_emails`'s description — its "projections/Rule J" wording is *measurably* harmful (drove the 0/20 + the chat-instead-of-act behavior) + (c) a light system prompt. Every failure mode responded to a cheap $0 harness lever — **no 3B ceiling surfaced at any level.** 15/20 is not yet production-grade, so the fix stories (10.7.2 prompt + 10.7.3 trim + description work) still own the tuning to push it higher (a sharper `find_emails` description + stronger prompt should lift it) — but the direction is now measured, not guessed. 10.7.4 (model swap) recedes further toward unlikely-fallback.

## 5. Cost thesis + safety framing (AC-6)

- **Cost thesis intact — $0.** Every lever discussed (system prompt, tool descriptions, surface trim, even a model swap) stays local. No paid API floor introduced. `project_local_model_is_safety_net` holds.
- **Safety pipeline untouched.** This spike changed no product code; the model-independent propose→grant→drain pipeline (F28 gate, `pending_actions` has no model column) is unperturbed. Framing check only, no regression risk.

## 6. Discharges

- **Epic 10.7 done-flip clause 1** — DISCHARGED: this spike is done with a recorded go/no-go finding + recommended fix path. The path is "run the §4.1 combined-lever experiment; fire 10.7.3 + tool-description work; keep 10.7.1 defensive; do NOT close 10.7.4," which is a legitimate go/no-go outcome (measure-before-fix surfaced that the cheap lever is insufficient — exactly the 10.6.4 `num_ctx` discipline working as intended).
- **Clause 3 (load-bearing = Epic 10.6 clause 3b) is NOT yet de-risked.** Contrary to the original finding, the spike does not give high confidence a system prompt will produce a faithful qwen `find_emails` call on a real turn — it shows the opposite at real scale. The §4.1 experiment is the next gate.

## Appendix — reproduce

```
docker ps                                                     # mailbot-ollama :11434, mailbot-api :8000
SPIKE_N=8 .venv/Scripts/python.exe scratch/qwen_toolcall_spike_107.py all    # 5-tool stub modes
SPIKE_N=8 .venv/Scripts/python.exe scratch/qwen_toolcall_spike_107.py real   # real 26-verb modes
SPIKE_N=3 .venv/Scripts/python.exe scratch/qwen_toolcall_spike_107.py realsurface_strong
SPIKE_N=4 .venv/Scripts/python.exe scratch/qwen_toolcall_spike_107.py realsurface_betterdesc
.venv/Scripts/python.exe scratch/qwen_toolcall_spike_107.py detail           # per-turn stub picks
```

Every "wrong pick" cell on the real surface = `pull_pending_notifications` (100%), captured in the `tool picks:` line of each mode's output and the `-run.log` / `-strong.log` / `-betterdesc.log` artifacts.
