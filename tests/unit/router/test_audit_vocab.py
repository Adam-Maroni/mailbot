"""Unit tests for mailbot_api/router/audit_vocab.py (Story 9.2 AC-1, AC-2, AC-6).

The audit_vocab module owns the closed-set ModelChosenReason enum + three
templated helpers (policy_default, policy_escalation, degraded_mode_demotion).
Every router_calls.model_chosen_reason write goes through this module post-9.2.

Test layout mirrors AC-6's six required test categories:

1. Enum-shape tests: every member's .value + string-backed semantics.
2. Helper tests: positive returns + reject-empty/invalid input.
3. Audit validator round-trip: each shape passes through RouterCallRow.
4. Audit validator counter-tests: old-vocab + nonsense raise ValidationError.
5. Boundary-check positive: refactored router.py passes the new rule.
6. Boundary-check counter: a fixture violator file flags.

Boundary-check tests use tmp_path to avoid polluting the repo.
"""

from __future__ import annotations

import textwrap
from enum import Enum
from pathlib import Path

import pytest
from pydantic import ValidationError

from mailbot_api.observability.audit import RouterCallRow
from mailbot_api.router.audit_vocab import (
    ModelChosenReason,
    degraded_mode_demotion,
    policy_default,
    policy_escalation,
)

# ---------------------------------------------------------------------------
# Category 1 — Enum shape
# ---------------------------------------------------------------------------


def test_enum_is_string_backed() -> None:
    """ModelChosenReason members must satisfy isinstance(member, str) so the
    Pydantic str-typed model_chosen_reason field accepts member.value directly
    AND member-equality comparisons against raw strings work."""
    assert issubclass(ModelChosenReason, str)
    assert issubclass(ModelChosenReason, Enum)
    for member in ModelChosenReason:
        assert isinstance(member, str)


@pytest.mark.parametrize(
    ("member", "expected_value"),
    [
        (ModelChosenReason.OVERRIDE_API, "override:api:force_model"),
        (ModelChosenReason.OVERRIDE_SLASH_ONE_SHOT, "slash_command:one_shot:adam"),
        (ModelChosenReason.OVERRIDE_SLASH_PERSISTENT, "slash_command:persistent:adam"),
        (ModelChosenReason.FALLBACK_TIMEOUT, "fallback:timeout"),
        (ModelChosenReason.FALLBACK_BUDGET_REFUSAL_RETRY, "fallback:budget_refusal_retry"),
        (ModelChosenReason.BENCHMARK_FORCE_MODEL, "benchmark:force_model"),
        (ModelChosenReason.CACHE_HIT, "cache:response_cache_hit"),
        (ModelChosenReason.SENSITIVITY_GATE_REFUSED, "sensitivity_gate:refused"),
        (ModelChosenReason.SENSITIVITY_GATE_NORMAL, "sensitivity_gate:normal"),
    ],
)
def test_literal_members_have_stable_values(member: ModelChosenReason, expected_value: str) -> None:
    """The nine literal members must carry the exact stable strings per AC-1.
    Drift breaks downstream analytics + the report renderer's WHERE clause."""
    assert member.value == expected_value


@pytest.mark.parametrize(
    ("member", "expected_template"),
    [
        (ModelChosenReason.POLICY_DEFAULT, "policy:<task>:default"),
        (ModelChosenReason.POLICY_ESCALATION, "policy:escalation:<from>→<to>"),
        (ModelChosenReason.DEGRADED_MODE_DEMOTION, "degraded:<from>→<to>"),
    ],
)
def test_templated_members_carry_template_strings(
    member: ModelChosenReason, expected_template: str
) -> None:
    """The three templated members' .value is the template documentation,
    NOT a writable value. The actual write path goes through helpers."""
    assert member.value == expected_template


def test_enum_has_at_least_twelve_members() -> None:
    """AC-1 mandates AT LEAST 12 members. Adding members later is fine;
    losing members would break the contract."""
    assert len(list(ModelChosenReason)) >= 12


@pytest.mark.parametrize(
    "member",
    [
        ModelChosenReason.OVERRIDE_API,
        ModelChosenReason.OVERRIDE_SLASH_ONE_SHOT,
        ModelChosenReason.OVERRIDE_SLASH_PERSISTENT,
        ModelChosenReason.FALLBACK_TIMEOUT,
        ModelChosenReason.FALLBACK_BUDGET_REFUSAL_RETRY,
        ModelChosenReason.BENCHMARK_FORCE_MODEL,
        ModelChosenReason.CACHE_HIT,
        ModelChosenReason.SENSITIVITY_GATE_REFUSED,
        ModelChosenReason.SENSITIVITY_GATE_NORMAL,
    ],
)
def test_literal_member_reverse_lookup_by_value(member: ModelChosenReason) -> None:
    """CR-F2 (AC-6.1 reverse-lookup): ``ModelChosenReason(member.value)`` must
    return the same member instance. String-backed enum semantics rely on this
    for consumers that round-trip values through serialization (e.g., reading
    a string out of router_calls and reconstructing the enum member)."""
    assert ModelChosenReason(member.value) is member


# ---------------------------------------------------------------------------
# Category 2 — Helpers
# ---------------------------------------------------------------------------


def test_policy_default_returns_templated_string() -> None:
    assert policy_default("draft_reply") == "policy:draft_reply:default"
    assert policy_default("compose_digest") == "policy:compose_digest:default"


def test_policy_default_rejects_empty_task() -> None:
    with pytest.raises(ValueError, match="task"):
        policy_default("")


def test_policy_escalation_returns_templated_string() -> None:
    result = policy_escalation("claude-haiku-4-5-20251001", "claude-opus-4-7")
    assert result == "policy:escalation:claude-haiku-4-5-20251001→claude-opus-4-7"


def test_policy_escalation_accepts_ollama_model_ids_with_colons() -> None:
    """qwen IDs contain colons; the helper must accept them verbatim."""
    result = policy_escalation("qwen2.5:3b-instruct-q4_K_M", "claude-haiku-4-5-20251001")
    assert "qwen2.5:3b-instruct-q4_K_M" in result
    assert "claude-haiku-4-5-20251001" in result


def test_policy_escalation_rejects_empty_arms() -> None:
    with pytest.raises(ValueError):
        policy_escalation("", "claude-opus-4-7")
    with pytest.raises(ValueError):
        policy_escalation("claude-haiku-4-5-20251001", "")


def test_degraded_mode_demotion_returns_templated_string() -> None:
    result = degraded_mode_demotion("claude-opus-4-7", "claude-haiku-4-5-20251001")
    assert result == "degraded:claude-opus-4-7→claude-haiku-4-5-20251001"


def test_degraded_mode_demotion_rejects_empty_arms() -> None:
    with pytest.raises(ValueError):
        degraded_mode_demotion("", "qwen2.5:3b-instruct-q4_K_M")
    with pytest.raises(ValueError):
        degraded_mode_demotion("claude-opus-4-7", "")


# CR-F4: whitespace-only inputs must raise (semantically equivalent to empty
# for a task_type / model identifier — both are nonsense and indicate caller bugs).


@pytest.mark.parametrize("whitespace_input", [" ", "\t", "\n", "   "])
def test_policy_default_rejects_whitespace_only_task(whitespace_input: str) -> None:
    with pytest.raises(ValueError, match="whitespace"):
        policy_default(whitespace_input)


@pytest.mark.parametrize("whitespace_input", [" ", "\t", "\n", "   "])
def test_policy_escalation_rejects_whitespace_only_arms(whitespace_input: str) -> None:
    with pytest.raises(ValueError, match="whitespace"):
        policy_escalation(whitespace_input, "claude-opus-4-7")
    with pytest.raises(ValueError, match="whitespace"):
        policy_escalation("claude-opus-4-7", whitespace_input)


@pytest.mark.parametrize("whitespace_input", [" ", "\t", "\n", "   "])
def test_degraded_mode_demotion_rejects_whitespace_only_arms(whitespace_input: str) -> None:
    with pytest.raises(ValueError, match="whitespace"):
        degraded_mode_demotion(whitespace_input, "qwen2.5:3b-instruct-q4_K_M")
    with pytest.raises(ValueError, match="whitespace"):
        degraded_mode_demotion("claude-opus-4-7", whitespace_input)


# CR-F5 (documenting test, regex tightening deferred):
# POLICY_DEFAULT_RE currently accepts strings the helpers would never produce
# (uppercase, spaces, etc.) because the helper guards on emptiness/whitespace
# but the regex is permissive. This is a deliberate trade-off — the helper is
# the canonical write path, so the regex is the safety net not the primary
# enforcement. These tests document the current permissive behavior so any
# future tightening surfaces them as expected failures.


def test_override_api_value_is_used_for_both_force_branches() -> None:
    """CR-F3: explicit collapse contract — both pre-9.2 distinctions
    (force=True → "force_override" / force=False → "override") now map to
    the SAME ModelChosenReason.OVERRIDE_API value. This test locks in the
    collapse at the enum-value layer (the router-level branch-coverage
    tests at test_router.py:177 + 693 exercise both branches against this
    same canonical value)."""
    # Pre-9.2: two distinct strings ("force_override" vs "override").
    # Post-9.2: one canonical value used by both router.py:240 branches.
    canonical = ModelChosenReason.OVERRIDE_API.value
    assert canonical == "override:api:force_model"
    # If a future story splits the collapse by adding OVERRIDE_API_FORCE,
    # this assertion will need updating to allow both members.
    override_members = [
        m for m in ModelChosenReason if m.name.startswith("OVERRIDE_API")
    ]
    assert len(override_members) == 1, (
        "Story 9.2 collapsed force_override+override into one member. "
        "Adding an OVERRIDE_API_FORCE member requires updating router.py:240 "
        "to write the new member when force=True. Update this test too."
    )


# CR-F8: validator round-trip for policy_escalation with Ollama-style from_model.


def test_router_call_row_accepts_policy_escalation_with_ollama_from_side() -> None:
    """CR-F8: round-trip validator test for the from-side Ollama colon case.
    `test_policy_escalation_accepts_ollama_model_ids_with_colons` exercises
    the helper but does NOT round-trip through RouterCallRow's validator —
    POLICY_ESCALATION_RE must accept colons on BOTH the from-side and the
    to-side. Add a validator round-trip test to catch any future regex
    tightening that breaks Ollama IDs on the from-side."""
    row = RouterCallRow(
        model_chosen_reason=policy_escalation(
            "qwen2.5:3b-instruct-q4_K_M", "claude-haiku-4-5-20251001"
        ),
        **_MINIMAL_KWARGS,
    )
    assert "qwen2.5:3b-instruct-q4_K_M" in row.model_chosen_reason
    assert "→" in row.model_chosen_reason


def test_router_call_row_accepts_degraded_with_ollama_on_to_side() -> None:
    """CR-F8 cousin: also verify the to-side colon case for degraded_mode_demotion
    (the existing test exercises to-side; this one is explicit defense)."""
    row = RouterCallRow(
        model_chosen_reason=degraded_mode_demotion(
            "claude-opus-4-7", "qwen2.5:3b-instruct-q4_K_M"
        ),
        **_MINIMAL_KWARGS,
    )
    assert "qwen2.5:3b-instruct-q4_K_M" in row.model_chosen_reason


# CR-F6: router_calls_by_reason validation tests.


@pytest.mark.asyncio
async def test_router_calls_by_reason_rejects_pre_9_2_vocab_string(tmp_path: Path) -> None:
    """CR-F6: passing a pre-9.2 string (e.g., "policy") raises ValueError
    instead of silently returning an empty list. Pre-9.2 rows in the DB
    remain SELECTable via raw SQL — the helper is forward-only."""
    from mailbot_api.observability.audit import router_calls_by_reason

    db_path = _temp_db_with_migrations(tmp_path)

    for old_vocab in ["policy", "override", "degraded", "response_cache_hit", "force_override"]:
        with pytest.raises(ValueError, match="post-9.2 vocabulary"):
            await router_calls_by_reason(db_path, old_vocab)


@pytest.mark.asyncio
async def test_router_calls_by_reason_rejects_nonsense_string(tmp_path: Path) -> None:
    """CR-F6: nonsense strings raise ValueError, not empty list."""
    from mailbot_api.observability.audit import router_calls_by_reason

    db_path = _temp_db_with_migrations(tmp_path)

    with pytest.raises(ValueError, match="post-9.2 vocabulary"):
        await router_calls_by_reason(db_path, "complete nonsense")


def test_policy_default_re_accepts_permissive_task_shapes_documenting() -> None:
    """CR-F5: documenting test. The regex POLICY_DEFAULT_RE accepts shapes
    the helpers would never produce — this is the current state.
    If a future story tightens the regex to e.g. ``^policy:[a-z][a-z0-9_]*:default$``
    this test must be updated to flip these to rejections."""
    from mailbot_api.router.audit_vocab import POLICY_DEFAULT_RE

    # Currently accepted (overly permissive — documenting):
    assert POLICY_DEFAULT_RE.match("policy:UPPER_CASE:default") is not None
    assert POLICY_DEFAULT_RE.match("policy:task with spaces:default") is not None
    assert POLICY_DEFAULT_RE.match("policy:has-hyphens:default") is not None
    # Always rejected (sanity):
    assert POLICY_DEFAULT_RE.match("policy::default") is None  # empty task
    assert POLICY_DEFAULT_RE.match("policy:task:Default") is None  # wrong suffix case
    assert POLICY_DEFAULT_RE.match("notpolicy:task:default") is None  # wrong prefix
    with pytest.raises(ValueError):
        degraded_mode_demotion("claude-opus-4-7", "")


# ---------------------------------------------------------------------------
# Category 3 — Audit validator round-trip (positive)
# ---------------------------------------------------------------------------


_MINIMAL_KWARGS = {
    "task_type": "draft_reply",
    "prompt_version": "v1",
    "model_chosen": "claude-haiku-4-5-20251001",
    "outcome": "ok",
}


@pytest.mark.parametrize(
    "member",
    [
        ModelChosenReason.OVERRIDE_API,
        ModelChosenReason.OVERRIDE_SLASH_ONE_SHOT,
        ModelChosenReason.OVERRIDE_SLASH_PERSISTENT,
        ModelChosenReason.FALLBACK_TIMEOUT,
        ModelChosenReason.FALLBACK_BUDGET_REFUSAL_RETRY,
        ModelChosenReason.BENCHMARK_FORCE_MODEL,
        ModelChosenReason.CACHE_HIT,
        ModelChosenReason.SENSITIVITY_GATE_REFUSED,
        ModelChosenReason.SENSITIVITY_GATE_NORMAL,
    ],
)
def test_router_call_row_accepts_every_literal_member(member: ModelChosenReason) -> None:
    """Every literal enum member's .value must pass through RouterCallRow's
    Pydantic validator. Failure means the audit validator's accepted-shapes
    list is out of sync with the enum."""
    row = RouterCallRow(model_chosen_reason=member.value, **_MINIMAL_KWARGS)
    assert row.model_chosen_reason == member.value


def test_router_call_row_accepts_policy_default_template() -> None:
    row = RouterCallRow(
        model_chosen_reason=policy_default("draft_reply"), **_MINIMAL_KWARGS
    )
    assert row.model_chosen_reason == "policy:draft_reply:default"


def test_router_call_row_accepts_policy_escalation_template() -> None:
    row = RouterCallRow(
        model_chosen_reason=policy_escalation(
            "claude-haiku-4-5-20251001", "claude-opus-4-7"
        ),
        **_MINIMAL_KWARGS,
    )
    assert "policy:escalation:" in row.model_chosen_reason


def test_router_call_row_accepts_degraded_mode_template_with_ollama_ids() -> None:
    """Ollama IDs contain colons; the validator's regex must accept them."""
    row = RouterCallRow(
        model_chosen_reason=degraded_mode_demotion(
            "claude-haiku-4-5-20251001", "qwen2.5:3b-instruct-q4_K_M"
        ),
        **_MINIMAL_KWARGS,
    )
    assert "qwen2.5:3b-instruct-q4_K_M" in row.model_chosen_reason


# ---------------------------------------------------------------------------
# Category 4 — Audit validator counter-tests (negative)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_value",
    [
        "some_new_reason",
        "policy",  # old vocab (pre-9.2)
        "override",  # old vocab
        "degraded",  # old vocab
        "response_cache_hit",  # old vocab
        "force_override",  # old vocab
        "escalated_from_claude-haiku-4-5-20251001",  # old vocab (legacy regex)
        "",  # empty
        "policy:",  # malformed templated
        "degraded::",  # malformed templated
    ],
)
def test_router_call_row_rejects_invalid_reason(bad_value: str) -> None:
    """Both old vocab AND nonsense must raise. Backwards-compat is forward-only:
    old rows live in SQLite as-is, but new RouterCallRow construction rejects
    old vocab. This is the AC-7 forward-only contract."""
    with pytest.raises(ValidationError):
        RouterCallRow(model_chosen_reason=bad_value, **_MINIMAL_KWARGS)


# ---------------------------------------------------------------------------
# Category 5 — Boundary-check positive (real router.py passes)
# ---------------------------------------------------------------------------


def test_boundary_check_passes_on_refactored_router_py() -> None:
    """After Task 3, mailbot_api/router/router.py must have ZERO raw
    model_chosen_reason string writes. The new boundary rule scans for them."""
    from scripts.check_boundaries import check_file

    repo_root = Path(__file__).resolve().parents[3]
    router_py = repo_root / "mailbot_api" / "router" / "router.py"
    violations = check_file(router_py, repo_root)
    raw_reason_violations = [v for v in violations if "model_chosen_reason" in v]
    assert raw_reason_violations == [], (
        "router.py must use the audit_vocab enum/helpers; found raw writes: "
        f"{raw_reason_violations}"
    )


def test_boundary_check_passes_on_audit_vocab_module() -> None:
    """audit_vocab.py legitimately defines the literal strings — it must be
    in the boundary-check allowlist."""
    from scripts.check_boundaries import check_file

    repo_root = Path(__file__).resolve().parents[3]
    audit_vocab_py = repo_root / "mailbot_api" / "router" / "audit_vocab.py"
    violations = check_file(audit_vocab_py, repo_root)
    raw_reason_violations = [v for v in violations if "model_chosen_reason" in v]
    assert raw_reason_violations == [], (
        "audit_vocab.py is the canonical literal definition site — "
        f"unexpected violations: {raw_reason_violations}"
    )


# ---------------------------------------------------------------------------
# Category 6 — Boundary-check counter (fixture violator flags)
# ---------------------------------------------------------------------------


def test_boundary_check_flags_raw_model_chosen_reason_literal(tmp_path: Path) -> None:
    """A non-allowlisted file containing a raw model_chosen_reason write must
    trip the new boundary rule."""
    from scripts.check_boundaries import check_file

    # Create a fake mailbot_api/<somewhere>/violator.py with a raw write.
    fake_repo_root = tmp_path
    pkg_dir = fake_repo_root / "mailbot_api" / "router"
    pkg_dir.mkdir(parents=True)
    violator = pkg_dir / "violator.py"
    violator.write_text(
        textwrap.dedent(
            """
            from mailbot_api.observability.audit import RouterCallRow

            row = RouterCallRow(
                task_type="draft_reply",
                prompt_version="v1",
                model_chosen="claude-haiku-4-5-20251001",
                model_chosen_reason="policy:draft_reply:default",
                outcome="ok",
            )
            """
        ).strip()
        + "\n"
    )

    violations = check_file(violator, fake_repo_root)
    raw_reason_violations = [v for v in violations if "model_chosen_reason" in v]
    assert len(raw_reason_violations) >= 1, (
        "Boundary check must flag the raw string write; got: " f"{violations}"
    )


def test_boundary_check_flags_raw_assignment(tmp_path: Path) -> None:
    """A bare assignment `model_chosen_reason = "policy"` (not kwarg) must also flag."""
    from scripts.check_boundaries import check_file

    fake_repo_root = tmp_path
    pkg_dir = fake_repo_root / "mailbot_api" / "router"
    pkg_dir.mkdir(parents=True)
    violator = pkg_dir / "assigner.py"
    violator.write_text(
        textwrap.dedent(
            """
            def pick_reason() -> str:
                model_chosen_reason = "policy:draft_reply:default"
                return model_chosen_reason
            """
        ).strip()
        + "\n"
    )

    violations = check_file(violator, fake_repo_root)
    raw_reason_violations = [v for v in violations if "model_chosen_reason" in v]
    assert len(raw_reason_violations) >= 1, (
        "Boundary check must flag bare assignments too; got: " f"{violations}"
    )


# ---------------------------------------------------------------------------
# Category 7 — Query helper `router_calls_by_reason` round-trip (AC-5)
# ---------------------------------------------------------------------------


_FRESH_DB_KWARGS = {
    "prompt_version": "v1",
    "model_chosen": "claude-haiku-4-5-20251001",
    "outcome": "ok",
}


def _temp_db_with_migrations(tmp_path: Path) -> str:
    """Apply migrations to a fresh temp DB and return its path."""
    from mailbot_api.db.migrations_runner import apply_pending_migrations

    db_path = str(tmp_path / "audit_vocab_round_trip.db")
    apply_pending_migrations(db_path)
    return db_path


@pytest.mark.asyncio
async def test_router_calls_by_reason_round_trips_literal_member(tmp_path: Path) -> None:
    """Every literal enum member's value round-trips through INSERT+SELECT."""
    from mailbot_api.observability.audit import (
        record_router_call,
        router_calls_by_reason,
    )

    db_path = _temp_db_with_migrations(tmp_path)

    # Seed one row per literal member.
    literal_members = [m for m in ModelChosenReason if "<" not in m.value]
    for i, member in enumerate(literal_members):
        row = RouterCallRow(
            ts=f"2026-06-13T00:00:{i:02d}.000000Z",
            task_type="draft_reply",
            model_chosen_reason=member.value,
            **_FRESH_DB_KWARGS,
        )
        await record_router_call(row, db_path=db_path)

    # Each member queried individually returns exactly one row.
    for member in literal_members:
        rows = await router_calls_by_reason(db_path, member)
        assert len(rows) == 1, f"expected 1 row for {member}; got {len(rows)}"
        assert rows[0].model_chosen_reason == member.value


@pytest.mark.asyncio
async def test_router_calls_by_reason_round_trips_templated_value(tmp_path: Path) -> None:
    """policy_default() / policy_escalation() / degraded_mode_demotion()
    return concrete strings that round-trip through the helper."""
    from mailbot_api.observability.audit import (
        record_router_call,
        router_calls_by_reason,
    )

    db_path = _temp_db_with_migrations(tmp_path)

    cases = [
        ("draft_reply", policy_default("draft_reply")),
        ("compose_digest", policy_default("compose_digest")),
        (
            "draft_reply",
            policy_escalation("claude-haiku-4-5-20251001", "claude-opus-4-7"),
        ),
        (
            "coarse_class",
            degraded_mode_demotion("claude-opus-4-7", "qwen2.5:3b-instruct-q4_K_M"),
        ),
    ]

    for i, (task, reason_str) in enumerate(cases):
        row = RouterCallRow(
            ts=f"2026-06-13T01:00:{i:02d}.000000Z",
            task_type=task,
            model_chosen_reason=reason_str,
            **_FRESH_DB_KWARGS,
        )
        await record_router_call(row, db_path=db_path)

    for _task, reason_str in cases:
        rows = await router_calls_by_reason(db_path, reason_str)
        assert len(rows) == 1, f"expected 1 row for {reason_str!r}; got {len(rows)}"
        assert rows[0].model_chosen_reason == reason_str


@pytest.mark.asyncio
async def test_router_calls_by_reason_rejects_non_enum_non_str(tmp_path: Path) -> None:
    """Type guard: passing an int (or anything not enum/str) raises TypeError."""
    from mailbot_api.observability.audit import router_calls_by_reason

    db_path = _temp_db_with_migrations(tmp_path)

    with pytest.raises(TypeError, match="ModelChosenReason or str"):
        await router_calls_by_reason(db_path, 42)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_router_calls_by_reason_returns_empty_list_when_no_match(
    tmp_path: Path,
) -> None:
    """Empty result is the natural "no rows found" signal — not an error."""
    from mailbot_api.observability.audit import router_calls_by_reason

    db_path = _temp_db_with_migrations(tmp_path)

    rows = await router_calls_by_reason(db_path, ModelChosenReason.CACHE_HIT)
    assert rows == []


@pytest.mark.asyncio
async def test_router_calls_by_reason_respects_limit(tmp_path: Path) -> None:
    """Limit param caps the row count."""
    from mailbot_api.observability.audit import (
        record_router_call,
        router_calls_by_reason,
    )

    db_path = _temp_db_with_migrations(tmp_path)

    # Seed 5 rows under the same reason.
    for i in range(5):
        row = RouterCallRow(
            ts=f"2026-06-13T02:00:{i:02d}.000000Z",
            task_type="draft_reply",
            model_chosen_reason=ModelChosenReason.CACHE_HIT.value,
            **_FRESH_DB_KWARGS,
        )
        await record_router_call(row, db_path=db_path)

    capped = await router_calls_by_reason(db_path, ModelChosenReason.CACHE_HIT, limit=3)
    assert len(capped) == 3
