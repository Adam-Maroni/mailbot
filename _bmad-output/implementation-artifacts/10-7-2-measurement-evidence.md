# Story 10.7.2 — Measurement Evidence (AC-4, AC-6)

**Generated:** 2026-07-16 by claude-opus-4-8 (dev), autonomous-story-run.
**Harness:** `scratch/qwen_toolcall_10_7_2_measure.py` (scratch-only, never staged) — imports the ACTUAL production instruction `_QWEN_TOOLCALL_SYSTEM_INSTRUCTION` from `router.py` and drives the LIVE local `mailbot-ollama` qwen (`qwen2.5:3b-instruct-q4_K_M`) directly at temp 0, reusing the 10-7-0 spike surfaces.
**Reproduce:**
```
docker ps    # mailbot-ollama :11434, mailbot-api :8000 both up
SPIKE_N=5 PYTHONPATH="<repo>;<repo>/scratch" \
  MAILBOT_OLLAMA_HOST=http://localhost:11434 MAILBOT_MCP_URL=http://localhost:8000/mcp/ \
  .venv/Scripts/python.exe scratch/qwen_toolcall_10_7_2_measure.py
```

## Purpose

The 10.7.0 spike (§4.4) measured that a system prompt adds ZERO on a GOOD tool
description (leaf selection 20/20 with or without a prompt). This story ships a
DEFENSIVE qwen-only instruction anyway (belt-and-suspenders for the real Hermes
path). AC-4 requires proving, with the ACTUAL production string, that the
instruction (a) does NOT REGRESS selection below the description-only baseline,
and (b) does NOT perturb the load-bearing temp-0 argument fidelity.

## Results (SPIKE_N=5 → 20 selection samples + 20 fidelity samples)

### (a) Selection — leaf surface + production `find_emails` description (10.7.5, shipped) + PRODUCTION instruction

| Metric | Result | Baseline (description-only, spike §4.4) |
|---|---|---|
| `find_emails` right+structured | **20/20** | 20/20 |
| tool picks | `{'find_emails': 20}` | `{'find_emails': 20}` |

**No regression.** The production instruction holds selection at the
description-only 20/20 — consistent with the spike's finding that a good prompt
adds nothing on a good description (and, critically here, subtracts nothing).

### (b) Argument fidelity — adversarial Graph-style id round-trip + PRODUCTION instruction

| Metric | Result |
|---|---|
| exact id round-trip | **20/20** |
| expected | `AAMkAGI2TG93AAA=ABC123XyZ789` |
| sample got | `AAMkAGI2TG93AAA=ABC123XyZ789` |
| mismatches | 0 |

**Fidelity preserved.** The adversarial long, mixed-case, digit-dense id (the
class the AI-1 probe saw corrupt `ABC123`→`ABC132` at non-zero temp) round-trips
EXACTLY at temp 0 WITH the instruction in the system message. The instruction
does not perturb the load-bearing temp-0 argument fidelity invariant.

## Sample-size honesty (carried from 10-7-0 spike §4.3/§4.4)

Each "20" = 4 unread-email paraphrases × 5 temp-0 deterministic repeats (fidelity:
4 × 5 repeats of the same adversarial-id turn). Temp 0 makes each cell
deterministic, so the repeats confirm NO DRIFT — they are not 20 independent
trials. The real independent axis is the paraphrase set. This is also
**direct-ollama drive, NOT the real Hermes chat path** — it confirms the
production instruction is neutral-or-better on selection and fidelity-safe, but
it does NOT discharge Epic 10.7 clause 3 (a live Discord turn), which remains
the load-bearing gate owed at the epic live walk.

## Disposition (AC-6)

**Ship ON-by-default (unconditional on the qwen tool-call path).** The data
clears both AC-4 conditions: selection is neutral (20/20, no regression) AND
fidelity is exact (20/20). There is no measured downside, so gating it OFF would
add dead config for no benefit; shipping it on gives the real Hermes path the
cheap defensive nudge this story exists to provide. It is composed as an
additional system block AFTER the client's persona blocks (never replacing
them), and injected ONLY for `qwen2.5:*` (the `claude-*` path is byte-for-byte
unchanged).

- **Cost thesis:** $0/local. No paid API floor introduced.
- **Safety pipeline:** untouched. No model-column change anywhere; a faithful
  qwen tool call is still gated by reversibility at drain
  (propose→grant→drain, F28), per `project_local_model_is_safety_net`.
- **Clause 3 NOT discharged:** this is defensive scaffolding UNDER the
  load-bearing live-Discord gate, not the gate itself.
