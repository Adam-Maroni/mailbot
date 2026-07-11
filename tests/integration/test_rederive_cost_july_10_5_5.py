"""Story 10.5.5 (AC-1, R4 / F-10-3-1) — July cost re-derive integration test.

Real-SQLite, no mocks. Seeds inflated July `router_calls` rows (Opus rows
priced at the old 3x $15/$75 rate) carrying their TRUE per-call tokens, plus a
`degraded_mode_state.active=1` row and a BudgetGuard seeded with the inflated
~$70 counter. Runs the re-derive and asserts:

  * per-row `cost_usd_estimated` is corrected to A2 pricing ($5/$25 for Opus),
  * the corrected July total is ~$26 (< $30 cap),
  * the BudgetGuard `this_month_spend_usd` counter is re-seeded to the honest ~$26,
  * `degraded_mode_state.active` flips to 0,
  * a subsequent small `add_spend` does NOT re-enter degraded (proves the trip
    cannot recur from stale July history).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mailbot_api.db.connection import fetchall, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.observability.audit import RouterCallRow, record_router_call
from mailbot_api.observability.rederive_cost import rederive_month_cost
from mailbot_api.router.budget import (
    MONTHLY_HARD_CAP_USD,
    _reset_guard_for_test,
    get_guard,
)
from mailbot_api.router.pricing import estimate_cost_usd

_OPUS = "claude-opus-4-7"
_HAIKU = "claude-haiku-4-5-20251001"

# The pre-A2 3x-overstated Opus rate as a per-Mtok pair, used only to fabricate
# the inflated stored figures the re-derive must correct.
_OLD_OPUS_IN = 15.0
_OLD_OPUS_OUT = 75.0


def _old_inflated_opus_cost(tokens_in: int, tokens_out: int, cached_in: int) -> float:
    fresh_in = max(0, tokens_in - cached_in)
    return (
        fresh_in * _OLD_OPUS_IN / 1_000_000.0
        + cached_in * (_OLD_OPUS_IN * 0.1) / 1_000_000.0
        + tokens_out * _OLD_OPUS_OUT / 1_000_000.0
    )


@pytest.fixture
def _clean_guard() -> Any:
    _reset_guard_for_test()
    yield
    _reset_guard_for_test()


async def _seed_row(
    db_path: str,
    *,
    ts: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    cached_in: int,
    stored_cost: float,
) -> None:
    row = RouterCallRow(
        ts=ts,
        task_type="anchor_calibrated_eval",
        prompt_version="v1",
        model_chosen=model,
        model_chosen_reason="policy:anchor_calibrated_eval:default",
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cached_tokens_in=cached_in,
        cost_usd_estimated=stored_cost,
        latency_ms=100,
        outcome="ok",
        caller_origin="benchmark",
    )
    await record_router_call(row, db_path=db_path)


async def _july_total(db_path: str) -> float:
    row = await fetchone(
        db_path,
        "SELECT COALESCE(SUM(cost_usd_estimated), 0) FROM router_calls "
        "WHERE ts >= ? AND ts < ?",
        ("2026-07-01T00:00:00Z", "2026-08-01T00:00:00Z"),
    )
    return float(row[0]) if row else 0.0


async def _degraded_active(db_path: str) -> int:
    row = await fetchone(
        db_path, "SELECT active FROM degraded_mode_state WHERE id = 1", ()
    )
    return int(row[0]) if row else 0


async def _set_degraded(db_path: str) -> None:
    await fetchall(db_path, "SELECT 1", ())  # touch connection
    from mailbot_api.db import connection, queries

    await connection.execute_write(
        db_path, queries.DEGRADED_MODE_ENTER, ("2026-07-03T14:41:24Z",)
    )


async def test_july_rederive_corrects_ledger_and_clears_degraded(
    tmp_path: Path, _clean_guard: Any
) -> None:
    db_path = str(tmp_path / "rederive.db")
    apply_pending_migrations(db_path)

    # Seed 197 Opus rows sized so the OLD inflated total lands ~$62 and the
    # corrected A2 total lands ~1/3 of that (Opus dropped exactly 3x). Each row:
    # 2000 in / 800 out, no cache.
    # 8000 in / 3200 out per row → corrected ~$0.12/row, inflated (3x) ~$0.36/row.
    # 197 rows → corrected ~$23.6 (< $30 cap), inflated ~$70.9 (mirrors the real
    # F-10-3-1 $70.24 / 234% figure).
    t_in, t_out, cache = 8000, 3200, 0
    n_opus = 197
    for i in range(n_opus):
        # spread across July days so ts stays in-window and unique-ish
        day = (i % 28) + 1
        ts = f"2026-07-{day:02d}T12:00:{(i % 60):02d}.000000Z"
        await _seed_row(
            db_path,
            ts=ts,
            model=_OPUS,
            tokens_in=t_in,
            tokens_out=t_out,
            cached_in=cache,
            stored_cost=_old_inflated_opus_cost(t_in, t_out, cache),
        )

    # A few haiku rows (already correctly priced — re-derive is a no-op on cost).
    for i in range(5):
        ts = f"2026-07-15T09:00:{i:02d}.000000Z"
        await _seed_row(
            db_path,
            ts=ts,
            model=_HAIKU,
            tokens_in=1000,
            tokens_out=200,
            cached_in=0,
            stored_cost=estimate_cost_usd(_HAIKU, 1000, 200, 0, strict=False),
        )

    # Pre-state: inflated total ~$62 (> $30 cap), degraded active, guard seeded high.
    pre_total = await _july_total(db_path)
    assert pre_total > MONTHLY_HARD_CAP_USD, f"expected inflated pre-total, got {pre_total}"
    await _set_degraded(db_path)
    assert await _degraded_active(db_path) == 1

    guard = get_guard()
    await guard.initialize(db_path)  # seeds counter from the inflated ledger
    # (this_month_spend_usd is the current-UTC-month sum; the seeded July rows
    # only count toward it if run in July. The re-derive re-seeds regardless.)

    result = await rederive_month_cost(db_path=db_path, month="2026-07")

    # Post-state: corrected total ~1/3 of inflated, under cap.
    post_total = await _july_total(db_path)
    expected_opus_each = estimate_cost_usd(_OPUS, t_in, t_out, cache, strict=False)
    assert post_total < MONTHLY_HARD_CAP_USD
    assert post_total == pytest.approx(result.new_total_usd, abs=1e-6)
    # The correction really shrank the ledger (roughly 3x on the Opus mass).
    assert post_total < pre_total / 2

    # Per-row Opus cost is now the A2 figure, not the 3x one.
    opus_rows = await fetchall(
        db_path,
        "SELECT cost_usd_estimated FROM router_calls WHERE model_chosen = ?",
        (_OPUS,),
    )
    assert all(
        r[0] == pytest.approx(expected_opus_each, abs=1e-9) for r in opus_rows
    )

    # degraded cleared.
    assert await _degraded_active(db_path) == 0
    assert result.degraded_was_active is True
    assert result.degraded_now_active is False

    # Guard counter re-seeded honest (equals current-UTC-month sum off corrected
    # ledger). It must not exceed the cap.
    assert guard.this_month_spend_usd < MONTHLY_HARD_CAP_USD


async def test_small_add_spend_after_rederive_does_not_retrip(
    tmp_path: Path, _clean_guard: Any
) -> None:
    """Proves the trip cannot recur from stale July history: after the re-derive
    re-seeds the honest counter, a small add_spend stays under the cap."""
    db_path = str(tmp_path / "rederive2.db")
    apply_pending_migrations(db_path)

    # Seed enough inflated Opus mass to be over-cap pre-derive.
    for i in range(197):
        day = (i % 28) + 1
        ts = f"2026-07-{day:02d}T12:00:{(i % 60):02d}.000000Z"
        await _seed_row(
            db_path,
            ts=ts,
            model=_OPUS,
            tokens_in=8000,
            tokens_out=3200,
            cached_in=0,
            stored_cost=_old_inflated_opus_cost(8000, 3200, 0),
        )
    await _set_degraded(db_path)

    guard = get_guard()
    await guard.initialize(db_path)
    await rederive_month_cost(db_path=db_path, month="2026-07")

    # A small spend must not re-enter degraded.
    assert guard.is_degraded() is False
    await guard.add_spend(db_path, 0.05)
    assert guard.is_degraded() is False
    assert await _degraded_active(db_path) == 0


async def test_rederive_past_month_does_not_touch_guard_or_clear_degraded(
    tmp_path: Path, _clean_guard: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 1: a RETROSPECTIVE (`--month <past>`) re-derive corrects the
    historical rows but must NOT re-seed the live guard counter (which reflects
    the CURRENT month's real spend) and must NOT clear a degraded trip the
    current month may justify.

    "Now" is pinned to 2026-08 while we re-derive July 2026.
    """
    import datetime as _dt

    from mailbot_api.observability import rederive_cost as _rc

    class _FixedDatetime(_dt.datetime):
        @classmethod
        def now(cls, tz: Any = None) -> Any:  # type: ignore[override]
            return _dt.datetime(2026, 8, 5, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(_rc, "datetime", _FixedDatetime)

    db_path = str(tmp_path / "rederive_past.db")
    apply_pending_migrations(db_path)

    # Inflated July rows (the past month we re-derive).
    for i in range(197):
        day = (i % 28) + 1
        ts = f"2026-07-{day:02d}T12:00:{(i % 60):02d}.000000Z"
        await _seed_row(
            db_path,
            ts=ts,
            model=_OPUS,
            tokens_in=8000,
            tokens_out=3200,
            cached_in=0,
            stored_cost=_old_inflated_opus_cost(8000, 3200, 0),
        )
    # An August row (later-month) — must NOT count toward July's old/new totals.
    await _seed_row(
        db_path,
        ts="2026-08-02T09:00:00.000000Z",
        model=_HAIKU,
        tokens_in=1000,
        tokens_out=200,
        cached_in=0,
        stored_cost=estimate_cost_usd(_HAIKU, 1000, 200, 0, strict=False),
    )
    await _set_degraded(db_path)

    guard = get_guard()
    # Pin a live counter value that a past-month re-derive must NOT clobber.
    guard.this_month_spend_usd = 99.0
    counter_before = guard.this_month_spend_usd

    result = await rederive_month_cost(db_path=db_path, month="2026-07")

    # July rows corrected (per-row A2 Opus figure), August row untouched.
    july_total = await _july_total(db_path)
    assert july_total == pytest.approx(result.new_total_usd, abs=1e-6)
    assert july_total < MONTHLY_HARD_CAP_USD

    # Live guard counter left UNTOUCHED (no re-seed for a past month).
    assert guard.this_month_spend_usd == counter_before == 99.0

    # Degraded trip NOT cleared by a past-month re-derive.
    assert result.degraded_was_active is True
    assert result.degraded_now_active is True
    assert await _degraded_active(db_path) == 1


async def test_old_total_is_window_bounded_not_over_counted(
    tmp_path: Path, _clean_guard: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 2: `old_total_usd` reflects ONLY the requested window even when
    later-month rows exist — it must not include the August row's cost."""
    import datetime as _dt

    from mailbot_api.observability import rederive_cost as _rc

    class _FixedDatetime(_dt.datetime):
        @classmethod
        def now(cls, tz: Any = None) -> Any:  # type: ignore[override]
            return _dt.datetime(2026, 8, 5, 12, 0, 0, tzinfo=tz)

    monkeypatch.setattr(_rc, "datetime", _FixedDatetime)

    db_path = str(tmp_path / "rederive_oldtotal.db")
    apply_pending_migrations(db_path)

    # One July Opus row (inflated) + one August Opus row (correctly priced, big).
    july_stored = _old_inflated_opus_cost(2000, 800, 0)
    await _seed_row(
        db_path,
        ts="2026-07-10T10:00:00.000000Z",
        model=_OPUS,
        tokens_in=2000,
        tokens_out=800,
        cached_in=0,
        stored_cost=july_stored,
    )
    aug_stored = 50.0  # a large later-month figure that WOULD leak via SPEND_SINCE
    await _seed_row(
        db_path,
        ts="2026-08-01T10:00:00.000000Z",
        model=_OPUS,
        tokens_in=2000,
        tokens_out=800,
        cached_in=0,
        stored_cost=aug_stored,
    )

    result = await rederive_month_cost(db_path=db_path, month="2026-07")

    # old_total reflects ONLY July's single row, NOT July+August.
    assert result.old_total_usd == pytest.approx(july_stored, abs=1e-9)
    assert result.old_total_usd < aug_stored


@pytest.mark.parametrize("bad_month", ["2026-13", "july", "2026", "2026-1-1"])
async def test_cli_rederive_cost_malformed_month_clean_exit(
    tmp_path: Path, _clean_guard: Any, capsys: Any, bad_month: str
) -> None:
    """Finding 4: a malformed `--month` produces a clean FATAL exit-2, not a raw
    traceback."""
    from scripts import mailbot as cli

    db_path = str(tmp_path / "cli_month.db")
    apply_pending_migrations(db_path)

    exit_code = await cli._cmd_rederive_cost(month=bad_month, db_path_arg=db_path)

    assert exit_code == 2
    err = capsys.readouterr().err
    assert err.startswith("FATAL:")
    assert "month" in err.lower()


async def test_rederive_is_idempotent(tmp_path: Path, _clean_guard: Any) -> None:
    db_path = str(tmp_path / "rederive3.db")
    apply_pending_migrations(db_path)

    await _seed_row(
        db_path,
        ts="2026-07-10T10:00:00.000000Z",
        model=_OPUS,
        tokens_in=2000,
        tokens_out=800,
        cached_in=0,
        stored_cost=_old_inflated_opus_cost(2000, 800, 0),
    )
    guard = get_guard()
    await guard.initialize(db_path)

    first = await rederive_month_cost(db_path=db_path, month="2026-07")
    second = await rederive_month_cost(db_path=db_path, month="2026-07")

    assert first.new_total_usd == pytest.approx(second.new_total_usd, abs=1e-9)
    # Second pass recomputes to identical stored values.
    total = await _july_total(db_path)
    assert total == pytest.approx(first.new_total_usd, abs=1e-9)
