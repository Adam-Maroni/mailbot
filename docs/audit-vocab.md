# `router_calls.model_chosen_reason` Vocabulary (Story 9.2)

This document describes the closed-set vocabulary for the
`router_calls.model_chosen_reason` column, the migration from the pre-9.2
free-form vocabulary, and the query patterns downstream consumers (the
Story 9.9 report renderer, ad-hoc analytics, future routing dashboards)
must use to handle the mixed-vocab table.

## Vocabulary Source of Truth

The closed-set vocabulary is owned by
[`mailbot_api/router/audit_vocab.py`](../mailbot_api/router/audit_vocab.py).
The `ModelChosenReason(str, Enum)` class enumerates all valid values; the
three module-level helpers (`policy_default`, `policy_escalation`,
`degraded_mode_demotion`) produce the concrete strings for the three
templated members.

### Nine literal members

These nine values are written verbatim from `<member>.value`:

| Enum member                       | Stable string                       |
| --------------------------------- | ----------------------------------- |
| `OVERRIDE_API`                    | `override:api:force_model`          |
| `OVERRIDE_SLASH_ONE_SHOT`         | `slash_command:one_shot:adam`       |
| `OVERRIDE_SLASH_PERSISTENT`       | `slash_command:persistent:adam`    |
| `FALLBACK_TIMEOUT`                | `fallback:timeout`                  |
| `FALLBACK_BUDGET_REFUSAL_RETRY`   | `fallback:budget_refusal_retry`     |
| `BENCHMARK_FORCE_MODEL`           | `benchmark:force_model`             |
| `CACHE_HIT`                       | `cache:response_cache_hit`          |
| `SENSITIVITY_GATE_REFUSED`        | `sensitivity_gate:refused`          |
| `SENSITIVITY_GATE_NORMAL`         | `sensitivity_gate:normal`           |

### Three templated members

These three carry the literal template string with placeholders as
`<member>.value`; the actual write goes through the helper:

| Enum member               | Template                         | Helper                                              |
| ------------------------- | -------------------------------- | --------------------------------------------------- |
| `POLICY_DEFAULT`          | `policy:<task>:default`          | `policy_default(task)`                              |
| `POLICY_ESCALATION`       | `policy:escalation:<from>→<to>`  | `policy_escalation(from_model, to_model)`           |
| `DEGRADED_MODE_DEMOTION`  | `degraded:<from>→<to>`           | `degraded_mode_demotion(from_model, to_model)`      |

The arrow character is U+2192 RIGHTWARDS ARROW (`→`), encoded as UTF-8
three-byte sequence `e2 86 92`. SQLite stores it without translation.

## Migration from Pre-9.2 Vocabulary

Pre-9.2 callsites wrote the following raw strings:

| Pre-9.2 value                                | Post-9.2 equivalent                                                   |
| -------------------------------------------- | --------------------------------------------------------------------- |
| `"policy"`                                   | `policy_default(task_type)` → e.g., `"policy:draft_reply:default"`    |
| `"override"`                                 | `ModelChosenReason.OVERRIDE_API` → `"override:api:force_model"`       |
| `"force_override"`                           | `ModelChosenReason.OVERRIDE_API` → `"override:api:force_model"`       |
| `"degraded"`                                 | `degraded_mode_demotion(from, to)` → e.g., `"degraded:claude-opus-4-7→claude-haiku-4-5-20251001"` |
| `"response_cache_hit"`                       | `ModelChosenReason.CACHE_HIT` → `"cache:response_cache_hit"`          |
| `"escalated_from_<X>"`                       | `policy_escalation(from, to)` → e.g., `"policy:escalation:qwen2.5:3b-instruct-q4_K_M→claude-haiku-4-5-20251001"` |

### Vocabulary consolidation: `force_override` → `OVERRIDE_API`

Pre-9.2 distinguished `"force_override"` (when `force=True` on
`ask_router`) from `"override"` (when `force_model` is set but `force=False`).
Post-9.2 both collapse to `ModelChosenReason.OVERRIDE_API`. The `force`
boolean still gates degraded-mode behavior internally; the audit row no
longer separates the two branches because routing-analytics observers
slicing `router_calls` care that the model came from an API override,
not which boolean flag was set.

### Forward-only contract

Story 9.2 makes NO data migration of existing rows. Pre-9.2 rows in
`router_calls` keep their old `model_chosen_reason` values verbatim.
However:

- **Reads** — old rows are still SELECTable via raw SQL (the column is
  `TEXT` and unchanged).
- **Reconstruction** — `RouterCallRow(model_chosen_reason="policy")` for
  an old value raises `ValidationError`. The new validator (Story 9.2
  AC-2) only accepts the four post-9.2 shapes.

If a downstream tool needs to reconstruct `RouterCallRow` instances from
historical rows for some reason, it must filter to post-9.2 rows in SQL
first (e.g., `WHERE ts >= '<story-9.2-deploy-ts>'`).

## Query Patterns for Downstream Consumers

### The two-vocabulary IN clause

Until pre-9.2 rows are retired (no current plan to do so), any query
slicing by `model_chosen_reason` must cover BOTH vocabularies for the
relevant semantic category. Examples:

```sql
-- "All policy-default dispatches" across pre-9.2 + post-9.2 rows
SELECT * FROM router_calls
WHERE model_chosen_reason IN ('policy', 'policy:draft_reply:default',
                              'policy:compose_digest:default', /* ... */);

-- "All cache hits" across both vocabs
SELECT * FROM router_calls
WHERE model_chosen_reason IN ('response_cache_hit', 'cache:response_cache_hit');

-- "All overrides" — both API-force-override branches collapse to one
SELECT * FROM router_calls
WHERE model_chosen_reason IN ('override', 'force_override', 'override:api:force_model');
```

### The `LIKE` prefix pattern (preferred for templated categories)

For semantic categories that map to a templated member (e.g., "all
escalations" or "all degraded-mode demotions"), a `LIKE` prefix scan
covers both the pre-9.2 raw form AND the post-9.2 templated form:

```sql
-- All escalations (pre-9.2: 'escalated_from_<X>'; post-9.2: 'policy:escalation:<from>→<to>')
SELECT * FROM router_calls
WHERE model_chosen_reason LIKE 'escalated_from_%'
   OR model_chosen_reason LIKE 'policy:escalation:%';

-- All degraded-mode demotions (pre-9.2: 'degraded'; post-9.2: 'degraded:<from>→<to>')
SELECT * FROM router_calls
WHERE model_chosen_reason = 'degraded'
   OR model_chosen_reason LIKE 'degraded:%';
```

### The Python helper for literal-member queries

For querying by a single literal post-9.2 member, use the helper:

```python
from mailbot_api.observability.audit import router_calls_by_reason
from mailbot_api.router.audit_vocab import ModelChosenReason

# All cache hits, capped at 100 rows
rows = await router_calls_by_reason(db_path, ModelChosenReason.CACHE_HIT)

# All API overrides (collapses force=True and force=False)
rows = await router_calls_by_reason(db_path, ModelChosenReason.OVERRIDE_API)
```

The helper does NOT cover pre-9.2 vocabulary — it's a forward-only API
that returns `list[RouterCallRow]`. Callers that need historical coverage
must use raw SQL with `IN (?, ?)` or `LIKE` patterns.

## Boundary Enforcement

The `forbid_raw_model_chosen_reason_strings` rule in
[`scripts/check_boundaries.py`](../scripts/check_boundaries.py) prevents
new code from bypassing the enum. The rule scans for three shapes:

1. Keyword argument `model_chosen_reason="<prefix>:..."` inside any `Call`
2. Bare assignment `model_chosen_reason = "<prefix>:..."`
3. Annotated assignment `model_chosen_reason: str = "<prefix>:..."`

The allowlist exempts:
- `mailbot_api/router/audit_vocab.py` — defines the literal values
- `mailbot_api/observability/audit.py` — references them in validator
  documentation

Adding a new routing-decision kind requires:
1. Adding an enum member to `audit_vocab.py` (with either a stable literal
   value OR a template + a helper function)
2. If the new member is a NEW template shape, extending
   `audit.py`'s `_check_reason` validator (currently four accepted shapes)
3. If the new member's stable prefix isn't already in
   `_MODEL_CHOSEN_REASON_PREFIX_RE` (line ~238 of `check_boundaries.py`),
   adding it there too

## References

- Enum + helpers + regex constants:
  [`mailbot_api/router/audit_vocab.py`](../mailbot_api/router/audit_vocab.py)
- Validator (the four accepted shapes):
  [`mailbot_api/observability/audit.py`](../mailbot_api/observability/audit.py)
- Query helper (`router_calls_by_reason`):
  [`mailbot_api/observability/audit.py`](../mailbot_api/observability/audit.py)
- Boundary check (`_MODEL_CHOSEN_REASON_LITERAL_ALLOW` +
  `_MODEL_CHOSEN_REASON_PREFIX_RE`):
  [`scripts/check_boundaries.py`](../scripts/check_boundaries.py)
- Unit tests (52 tests covering enum shape, validator, boundary, query
  helper round-trip):
  [`tests/unit/router/test_audit_vocab.py`](../tests/unit/router/test_audit_vocab.py)
- Integration tests (3 tests covering forward-only contract + mixed-vocab
  IN-clause):
  [`tests/integration/test_audit_vocab_backwards_compat.py`](../tests/integration/test_audit_vocab_backwards_compat.py)
- Story 9.2 spec:
  [`_bmad-output/planning-artifacts/epics.md#3157`](../_bmad-output/planning-artifacts/epics.md)
