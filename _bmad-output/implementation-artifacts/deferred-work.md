# Deferred Work

## Deferred from: code review of story-1-9 (2026-06-01)

- Consent-flow `?error=...` callback maps to exit code 2 [scripts/mint_refresh_token.py:373-385] — the spec's exit-code table doesn't enumerate this path; exit 2 is a defensible bucket. Could be tightened to a dedicated exit code in a future polish pass.
