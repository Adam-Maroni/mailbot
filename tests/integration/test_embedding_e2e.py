"""Story 3-4 AC-4, AC-5, AC-8: embed_email end-to-end + dispatch_embedding tests.

Spins up a real SQLite DB + real migrations + a fake _FakeEmbeddingAdapter
registered for the nomic-embed-text model id. Drives embed_email end-to-end
and asserts: write happens, router_calls row recorded, sensitivity precondition
honored, no SENSITIVITY_BLOCKS_API for local embeddings.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pytest

from mailbot_api.db.connection import execute_write, fetchall, fetchone
from mailbot_api.db.migrations_runner import apply_pending_migrations
from mailbot_api.db.queries import EMAIL_EMBEDDING_SELECT
from mailbot_api.ingest.embedding import embed_email, read_embedding
from mailbot_api.router import dispatch_embedding
from mailbot_api.router.budget import _reset_guard_for_test
from mailbot_api.router.errors import ErrorCode
from mailbot_api.router.lanes import _reset_semaphore_registry_for_test
from mailbot_api.router.limits import (
    _reset_loop_detector_for_test,
    _reset_rate_limiter_for_test,
)
from mailbot_api.router.models import EmbeddingResponse
from mailbot_api.router.pause import _reset_pause_state_for_test
from mailbot_api.router.policy import (
    _reset_policy_snapshot_for_test,
    load_policy,
    set_policy_snapshot,
)
from mailbot_api.router.registry import _reset_registry_for_test, register_adapter

_NOMIC = "nomic-embed-text"


class _FakeEmbeddingAdapter:
    """Returns a scripted EmbeddingResponse per embed call."""

    def __init__(self, vector: list[float]) -> None:
        self.model_id = _NOMIC
        self._vector = vector
        self.call_log: list[str] = []

    async def call(self, system: str, user: str, max_tokens_out: int, temperature: float = 0.0) -> Any:
        raise RuntimeError("_FakeEmbeddingAdapter does not support call()")

    async def embed(self, text: str) -> EmbeddingResponse:
        self.call_log.append(text)
        return EmbeddingResponse(
            vector=self._vector,
            dim=len(self._vector),
            tokens_in=len(text.split()),
            latency_ms=12,
            raw={"mock": True},
        )


_POLICY_YAML = f"""\
version: "test-embedding-v1"

tasks:
  embedding:
    model: "{_NOMIC}"
    prompt_version: "v1"
    escalate: false
    max_tokens_out: 0
    lane: "batch"
    sensitivity: "any"
"""


@pytest.fixture
def _clean_state():
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()
    yield
    _reset_policy_snapshot_for_test()
    _reset_registry_for_test()
    _reset_rate_limiter_for_test()
    _reset_semaphore_registry_for_test()
    _reset_guard_for_test()
    _reset_loop_detector_for_test()
    _reset_pause_state_for_test()


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(_POLICY_YAML, encoding="utf-8")
    set_policy_snapshot(load_policy(policy_yaml))
    return db_path


async def _seed_email(
    db_path: str, *, graph_id: str, sensitivity: str | None = None
) -> None:
    if sensitivity is None:
        await execute_write(
            db_path,
            "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview) "
            "VALUES (?, ?, ?, ?, ?)",
            (graph_id, "2026-06-01T00:00:00Z", "s", "x@y.com", "the body to embed"),
        )
    else:
        await execute_write(
            db_path,
            "INSERT INTO emails (graph_id, received_at, subject, from_address, body_preview, "
            "sensitivity, sensitivity_at, sensitivity_prompt_v, sensitivity_conf, sensitivity_model) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                graph_id, "2026-06-01T00:00:00Z", "s", "x@y.com", "the body to embed",
                sensitivity, "2026-06-01T00:01:00Z", "v1", 0.9, "qwen2.5:3b-instruct-q4_K_M",
            ),
        )


async def test_embed_email_happy_path_writes_and_records_audit(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-4 + AC-5: embed_email writes the embedding, records router_calls."""
    db_path = _setup(tmp_path)
    register_adapter(_NOMIC, _FakeEmbeddingAdapter(list(np.linspace(0.0, 1.0, 768))))
    await _seed_email(db_path, graph_id="e-1", sensitivity="normal")

    result = await embed_email(db_path=db_path, email_id="e-1")

    assert result.ok is True
    assert result.model == _NOMIC
    assert result.dim == 768
    assert result.error is None

    # Embedding round-trip preserves the vector.
    roundtrip = await read_embedding(db_path=db_path, email_id="e-1")
    assert roundtrip is not None
    assert roundtrip.shape == (768,)

    # router_calls row recorded with task_type=embedding.
    rows = await fetchall(
        db_path,
        "SELECT task_type, model_chosen, caller_origin, outcome FROM router_calls",
        (),
    )
    assert len(rows) == 1
    assert rows[0][0] == "embedding"
    assert rows[0][1] == _NOMIC
    assert rows[0][2] == "ingest-pipeline-embedding"
    assert rows[0][3] == "ok"


async def test_embed_email_refuses_when_sensitivity_unclassified(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-5: FR-2.3 precondition fires — unclassified email blocks embedding."""
    db_path = _setup(tmp_path)
    register_adapter(_NOMIC, _FakeEmbeddingAdapter([0.1] * 768))
    await _seed_email(db_path, graph_id="e-1", sensitivity=None)

    result = await embed_email(db_path=db_path, email_id="e-1")

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.SENSITIVITY_NOT_CLASSIFIED

    # No write happened.
    row = await fetchone(db_path, EMAIL_EMBEDDING_SELECT, ("e-1",))
    assert row is not None
    blob, _, _ = row
    assert blob is None


async def test_embed_email_allows_sensitive_classified(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-5: sensitive emails CAN be embedded locally (FR-2.5)."""
    db_path = _setup(tmp_path)
    register_adapter(_NOMIC, _FakeEmbeddingAdapter([0.5] * 768))
    await _seed_email(db_path, graph_id="e-1", sensitivity="sensitive")

    result = await embed_email(db_path=db_path, email_id="e-1")
    assert result.ok is True

    # Even confidential — local-only is fine.
    await _seed_email(db_path, graph_id="e-2", sensitivity="confidential")
    result2 = await embed_email(db_path=db_path, email_id="e-2")
    assert result2.ok is True


async def test_embed_email_records_failure_on_adapter_exception(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-5: adapter exceptions translate to RouterError + failed audit row."""
    db_path = _setup(tmp_path)

    class _BoomAdapter:
        model_id = _NOMIC

        async def call(self, *args, **kwargs):
            raise RuntimeError("never called")

        async def embed(self, text: str) -> EmbeddingResponse:
            from mailbot_api.router.models import AdapterProviderError

            raise AdapterProviderError(model_id=self.model_id, sanitized_message="kaboom")

    register_adapter(_NOMIC, _BoomAdapter())
    await _seed_email(db_path, graph_id="e-1", sensitivity="normal")

    result = await embed_email(db_path=db_path, email_id="e-1")

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == ErrorCode.PROVIDER_ERROR
    assert "kaboom" in result.error.message

    # Failed audit row recorded.
    rows = await fetchall(
        db_path, "SELECT task_type, outcome FROM router_calls", ()
    )
    assert len(rows) == 1
    assert rows[0][0] == "embedding"
    assert rows[0][1] == "failed"


async def test_dispatch_embedding_refuses_when_task_not_in_policy(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-5: dispatch_embedding refuses if policy.tasks['embedding'] missing.

    Policy has at least one task (Pydantic min-length=1) but NOT 'embedding'.
    """
    db_path = str(tmp_path / "t.db")
    apply_pending_migrations(db_path)
    policy_yaml = tmp_path / "policy.yaml"
    policy_yaml.write_text(
        'version: "no-embedding-v1"\n'
        'tasks:\n'
        '  coarse_class:\n'
        '    model: "qwen2.5:3b-instruct-q4_K_M"\n'
        '    prompt_version: "v1"\n'
        '    escalate: false\n'
        '    max_tokens_out: 256\n'
        '    lane: "batch"\n'
        '    sensitivity: "any"\n',
        encoding="utf-8",
    )
    set_policy_snapshot(load_policy(policy_yaml))

    result = await dispatch_embedding(
        text="hello", db_path=db_path, email_id=None
    )
    assert result.ok is False
    assert result.error is not None
    assert "not in policy" in result.error.message


async def test_dispatch_embedding_email_id_none_bypasses_precondition(
    tmp_path: Path, _clean_state: Any
) -> None:
    """AC-5: ad-hoc embedding (no email_id) bypasses the sensitivity precondition."""
    db_path = _setup(tmp_path)
    register_adapter(_NOMIC, _FakeEmbeddingAdapter([0.1] * 768))

    result = await dispatch_embedding(text="hello world", db_path=db_path, email_id=None)
    assert result.ok is True
    assert result.dim == 768


async def test_dispatch_embedding_paused_refuses_cross_process(
    tmp_path: Path, _clean_state: Any
) -> None:
    """Story 10.5.1 (AC-2 CLASS + AC-4, CR fix) — the third pause site.

    A pause written to the DB by "process A" (no `initialize()` on the checking
    instance) must refuse the embedding dispatch via the authoritative
    cross-process read (`is_paused_now`), not the stale `is_paused()` mirror,
    and must leave a `pause_gate:refused` audit row.
    """
    from mailbot_api.db.connection import fetchall
    from mailbot_api.router.pause import PauseState, _reset_pause_state_for_test

    db_path = _setup(tmp_path)
    register_adapter(_NOMIC, _FakeEmbeddingAdapter([0.1] * 768))

    # "Process A" pauses (writes the DB row); reset the singleton so the
    # checking path has a stale/False in-memory mirror.
    api_state = PauseState()
    await api_state.initialize(db_path)
    await api_state.pause(db_path, reason="operator-pause")
    _reset_pause_state_for_test()

    result = await dispatch_embedding(
        text="hello world", db_path=db_path, email_id=None
    )
    assert result.ok is False
    assert result.error is not None
    assert "paused" in result.error.message

    rows = await fetchall(
        db_path,
        "SELECT model_chosen_reason, outcome FROM router_calls "
        "WHERE model_chosen_reason = ?",
        ("pause_gate:refused",),
    )
    assert len(rows) == 1
    assert rows[0][1] == "failed"

    _reset_pause_state_for_test()
