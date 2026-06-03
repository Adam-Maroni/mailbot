# Deferred Work

## Deferred from: code review of story-1-9 (2026-06-01)

- Consent-flow `?error=...` callback maps to exit code 2 [scripts/mint_refresh_token.py:373-385] — the spec's exit-code table doesn't enumerate this path; exit 2 is a defensible bucket. Could be tightened to a dedicated exit code in a future polish pass.

## Deferred from: code review of 6-2-mailbot-logs-mailbot-pause-mailbot-resume-cli (2026-06-03)

- Per-call `import json as _json` inside `_filter_log_line` body [scripts/mailbot.py:726] — re-imports the module on every line processed; Python caches module imports so this is functionally a dict lookup, not a real module load. Unconventional in a hot-path per-line function but not a defect. Move import to module level in a future cleanup pass.
