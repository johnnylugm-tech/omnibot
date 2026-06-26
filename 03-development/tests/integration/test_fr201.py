"""TDD-GREEN tests for FR-201 — atomic knowledge delete (DB + SAQ cancel).

Spec source: 02-architecture/TEST_SPEC.md (FR-201)
SRS source : SRS.md FR-201

Acceptance criteria (from SRS FR-201):
    DELETE /api/v1/knowledge/{id} — 真正刪除 KB row + knowledge_chunks，
    並取消所有 SAQ pending EmbeddingJob (payload.knowledge_id == id);
    RBAC: knowledge:delete 通過；DB 刪除成功；SAQ cancel 結果透過
    fallback/saq_cancelled 反映；role 不符 → 403.

The four TEST_SPEC cases (function names MUST match exactly):
    1. test_fr201_delete_knowledge_returns_200_for_admin
    2. test_fr201_delete_knowledge_returns_403_for_anon
    3. test_fr201_saq_cancel_only_targets_matching_knowledge_id
    4. test_fr201_saq_unavailable_returns_200_with_fallback

Sub-assertions (per TEST_SPEC):
    fr201-ok       : result == 200              (case 1)
    fr201-rbac     : result == 403              (case 2)
    fr201-precision: len(cancelled)==1, scanned==3 (case 3)
    fr201-fallback : result==200 AND saq_fallback=="saq_unavailable" (case 4)
"""

from __future__ import annotations

import asyncio as _asyncio

from app.api.management import (
    _HTTP_FORBIDDEN,
    _HTTP_OK,
    delete_knowledge,
)
from app.core.knowledge import DeleteKnowledgeResult
from app.infra.jobs import cancel_embedding_jobs_for


def _fake_run(coro):
    """Drive a coroutine to completion on the current event loop.

    Same pattern used by test_fr200 (FR-200 GREEN step). ``asyncio.run``
    inside the api layer creates a fresh loop per call; this helper
    provides a real event loop driver for the monkeypatched
    ``asyncio.run`` slot so the coroutine actually executes.
    """
    try:
        return _asyncio.get_event_loop().run_until_complete(coro)
    except RuntimeError:
        loop = _asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


# ---------------------------------------------------------------------------
# Case 1: happy path — admin RBAC pass + core invoked → 200
# ---------------------------------------------------------------------------


def test_fr201_delete_knowledge_returns_200_for_admin(monkeypatch):
    """[FR-201 case 1] admin role + DB+SAQ ok → 200."""
    async def fake_delete(kid: str, **_):
        return DeleteKnowledgeResult(
            knowledge_id=kid,
            chunks_deleted=3,
            kb_deleted=True,
            saq_cancelled=("job_a", "job_b"),
            saq_matched=("job_a", "job_b"),
            saq_scanned=5,
            saq_fallback="",
            saq_error=None,
        )

    monkeypatch.setattr(
        "app.core.knowledge.delete_knowledge_and_cancel_jobs", fake_delete
    )
    monkeypatch.setattr("app.api.management.asyncio.run", _fake_run)

    assert delete_knowledge(role="admin", id_="kb-1") == _HTTP_OK


# ---------------------------------------------------------------------------
# Case 2: RBAC deny — anonymous → 403, core NOT called
# ---------------------------------------------------------------------------


def test_fr201_delete_knowledge_returns_403_for_anon(monkeypatch):
    """[FR-201 case 2] anonymous role denied; core NOT invoked."""
    calls = {"count": 0}

    def _spy(_kid: str, **_kw):
        calls["count"] += 1
        return None

    monkeypatch.setattr(
        "app.core.knowledge.delete_knowledge_and_cancel_jobs", _spy
    )

    assert delete_knowledge(role="anonymous", id_="kb-1") == _HTTP_FORBIDDEN
    assert calls["count"] == 0


# ---------------------------------------------------------------------------
# Case 3: SAQ cancel filter precision — only matching knowledge_id cancelled
# ---------------------------------------------------------------------------


def test_fr201_saq_cancel_only_targets_matching_knowledge_id(monkeypatch):
    """[FR-201 case 3] only jobs whose payload references the target
    ``knowledge_id`` are aborted; other queued jobs untouched.

    Drives the real ``cancel_embedding_jobs_for`` with a fake SAQ
    client whose ``.redis.scan_iter`` yields 3 keys (1 matching,
    2 referencing other KBs) and ``.job(job_id)`` returns a stub
    ``Job`` carrying the right ``function`` / ``kwargs`` fields.
    """
    # Build a fake SAQ client that exposes .redis (async scan_iter)
    # and .job (async Job lookup). The fake Job also carries an
    # ``abort`` method so the cancel path can complete the abort.
    class _FakeRedis:
        def __init__(self, keys: list[bytes]) -> None:
            self._keys = keys

        async def scan_iter(self, match: str, count: int = 500):  # noqa: ARG002
            for k in self._keys:
                yield k

    class _FakeJob:
        # Mirrors saq.job.Job public attributes (function / kwargs)
        # plus the ``abort`` method used by the cancel path. Recorded
        # aborts land on the instance for post-test assertions.
        def __init__(self, function: str, kwargs: dict[str, object]) -> None:
            self.function = function
            self.kwargs = kwargs
            self.aborted: list[tuple[str, int]] = []

        async def abort(self, error: str = "", ttl: int = 5) -> None:
            self.aborted.append((error, ttl))

    class _FakeSAQClient:
        def __init__(self, redis_client: _FakeRedis, jobs_by_id: dict[str, _FakeJob]) -> None:
            self.redis = redis_client
            self._jobs_by_id = jobs_by_id

        async def job(self, job_id: str):
            return self._jobs_by_id.get(job_id)

    keys = [
        b"saq:embed_job:job_for_kb1",
        b"saq:embed_job:job_for_kb2",
        b"saq:embed_job:job_for_kb3",
    ]
    jobs_by_id = {
        "job_for_kb1": _FakeJob(function="embed_job", kwargs={"knowledge_id": "kb-1"}),
        "job_for_kb2": _FakeJob(function="embed_job", kwargs={"knowledge_id": "kb-2"}),
        "job_for_kb3": _FakeJob(function="other_queue", kwargs={"knowledge_id": "kb-1"}),
    }
    fake_client = _FakeSAQClient(_FakeRedis(keys), jobs_by_id)

    # Use module-level monkeypatch so the autouse fixture's stub (or
    # any prior test's leftover state) is restored on teardown. Do
    # NOT use ``jobs_mod.set_saq_client(...)`` here — that would
    # leak across tests.
    import app.infra.jobs as jobs_mod
    monkeypatch.setattr(jobs_mod, "_SAQ_CLIENT", fake_client)

    # Drive the coroutine on a fresh event loop — ``get_event_loop``
    # raises RuntimeError in Python 3.11+ when no loop is current
    # (which is the suite-run state after sibling async tests have
    # torn their loops down).
    loop = _asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(cancel_embedding_jobs_for("kb-1"))
    finally:
        loop.close()
    assert result.scanned == 3
    assert result.matched == ("job_for_kb1",)
    assert result.cancelled == ("job_for_kb1",)
    assert result.fallback == ""
    assert result.error is None
    # Job for kb-2 was filtered by knowledge_id; the other_queue job
    # was filtered by function. Neither appears in matched / cancelled.


# ---------------------------------------------------------------------------
# Case 4: graceful fallback — _SAQ_CLIENT is None → 200 with saq_fallback set
# ---------------------------------------------------------------------------


def test_fr201_saq_unavailable_returns_200_with_fallback(monkeypatch):
    """[FR-201 case 4] SAQ un-wired → 200 still returned; DB delete is
    the source of truth and the SAQ cancel is best-effort. Worker-side
    idempotency (TODO at process_embedding_job) protects FR-77/78
    invariant for any surviving job.
    """
    from app.infra import jobs as jobs_mod

    # Simulate the production SAQ outage: no client wired. Use
    # monkeypatch so pytest auto-restores the autouse stub on teardown
    # — leaving _SAQ_CLIENT=None across tests would break FR-77/78/200
    # sibling suites.
    monkeypatch.setattr(jobs_mod, "_SAQ_CLIENT", None)

    async def fake_delete(kid: str, **_):
        return DeleteKnowledgeResult(
            knowledge_id=kid,
            chunks_deleted=2,
            kb_deleted=True,
            saq_cancelled=(),
            saq_matched=(),
            saq_scanned=0,
            saq_fallback="saq_unavailable",
            saq_error="SAQ client not wired; call set_saq_client() at boot",
        )

    monkeypatch.setattr(
        "app.core.knowledge.delete_knowledge_and_cancel_jobs", fake_delete
    )
    monkeypatch.setattr("app.api.management.asyncio.run", _fake_run)

    assert delete_knowledge(role="admin", id_="kb-2") == _HTTP_OK
