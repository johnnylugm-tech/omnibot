"""TDD-GREEN tests for FR-200 — Knowledge Update re-embed.

Spec source: 02-architecture/TEST_SPEC.md (FR-200)
SRS source : SRS.md FR-200

Acceptance criteria (from SRS FR-200):
    PUT /api/v1/knowledge/{id} — 真正更新 KB row (title/content) 並重
    embed 所有 chunks（超時走 enqueue_embedding_job）；RBAC: knowledge:write
    通過；知識存在；回傳 200；role 不符 → 403；chunks 已用新向量覆寫；
    < 2.5s SLO.

The three TEST_SPEC cases (function names MUST match exactly):
    1. test_fr200_update_knowledge_returns_200_for_admin
    2. test_fr200_update_knowledge_returns_403_for_anon
    3. test_fr200_update_knowledge_reembed_chunks_enqueued

Sub-assertions (per TEST_SPEC):
    fr200-ok   : result == 200               (case 1)
    fr200-rbac : result == 403               (case 2)
    fr200-enq  : enqueue_embedding_job
                 .call_count >= 1            (case 3)
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.api.management import (
    _HTTP_FORBIDDEN,
    _HTTP_OK,
    update_knowledge,
)


def test_fr200_update_knowledge_returns_200_for_admin(monkeypatch):
    """[FR-200 case 1] admin role passes RBAC and returns 200."""
    # Drive async core via asyncio.run interception.
    fake_result = MagicMock()
    monkeypatch.setattr("app.api.management.asyncio.run", lambda _: fake_result)
    spy = MagicMock(return_value=fake_result)
    monkeypatch.setattr(
        "app.core.knowledge.update_knowledge_with_reembed", spy
    )

    result = update_knowledge(
        role="admin",
        id_="kb_seed_001",
        payload={"title": "new", "content": "new"},
    )
    assert result == _HTTP_OK
    assert spy.call_count == 1


def test_fr200_update_knowledge_returns_403_for_anon():
    """[FR-200 case 2] anonymous role denied at RBAC, no core call."""
    result = update_knowledge(
        role="anonymous",
        id_="kb_seed_001",
        payload={"title": "x", "content": "x"},
    )
    assert result == _HTTP_FORBIDDEN


def test_fr200_update_knowledge_reembed_chunks_enqueued(monkeypatch):
    """[FR-200 case 3] update should drive enqueue_embedding_job >= 1."""
    # The core function does ``from app.infra.jobs import
    # enqueue_embedding_job`` inside its body, so the active binding
    # at call time lives in ``app.infra.jobs``. Patch there.
    enqueue_spy = MagicMock()
    monkeypatch.setattr("app.infra.jobs.enqueue_embedding_job", enqueue_spy)

    # Drive async core via asyncio.run interception. The fake must
    # actually await the coroutine so the core function body executes
    # (and calls enqueue_embedding_job inside its loop). Replace
    # asyncio.run with a sync wrapper that runs the coroutine to
    # completion via a fresh event loop.
    import asyncio as _asyncio

    def _fake_run(coro):
        try:
            return _asyncio.get_event_loop().run_until_complete(coro)
        except RuntimeError:
            loop = _asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

    monkeypatch.setattr("app.api.management.asyncio.run", _fake_run)

    result = update_knowledge(
        role="admin",
        id_="kb_seed_002",
        payload={"title": "T", "content": "C"},
    )
    assert result == _HTTP_OK
    assert enqueue_spy.call_count >= 1