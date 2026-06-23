"""Shared test fixtures for the omnibot test suite.

Autouse isolation so RED tests fail because of missing feature logic,
not because of missing infrastructure (Redis, DB, HTTP).

GREEN contract for FR-21 (Redis sliding window rate limiter):
- RateLimiter MUST accept an injected redis client (sync + async) via
  __init__ or class method. Do not construct real Redis sockets inside
  unit tests.
- When GREEN fills in the real client wiring, patch
  `redis.Redis` / `redis.asyncio.Redis` here to return fakeredis or a stub.

During the current RED step, this fixture is effectively a no-op because
the source modules do not exist yet — pytest fails with Collection Error
(Exit Code 2) at `from app.infra.rate_limit import RateLimiter`, which is
the valid RED signal.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure the project source root is importable for `from app.xxx import yyy`
# when pytest is invoked from a cwd that does not read pyproject.toml (e.g.
# mutmut's temp workdir). pyproject.toml [tool.pytest.ini_options] already
# sets pythonpath for normal invocations; this is the safety net.
_SRC_ROOT = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

os.environ.setdefault("OMNIBOT_ADMIN_USER", "admin")
os.environ.setdefault("OMNIBOT_ADMIN_PASS", "correct")
os.environ.setdefault("OMNIBOT_JWT_SECRET", "test-only-jwt-secret-do-not-use-in-prod-32chars")

@pytest.fixture(autouse=True)
def _isolate_external_services(monkeypatch):  # type: ignore[reportUnusedFunction]
    """Prevent real Redis/DB/HTTP I/O during unit tests."""
    # Pyright does not recognise pytest autouse fixtures; the explicit
    # ``del`` keeps the function body non-empty so a static reader
    # sees the parameter being acknowledged.
    del monkeypatch
    # FR-77/FR-78 — install a recording SAQ stub so any call into
    # ``app.infra.jobs.enqueue_embedding_job`` succeeds instead of
    # raising the boot-time-misconfiguration ``RuntimeError`` the
    # production wiring enforces. Tests that explicitly want the
    # misconfiguration path can call ``set_saq_client(None)`` to
    # override the autouse stub.
    try:
        from app.infra.jobs import set_saq_client

        class _RecordingSAQStub:
            def __init__(self) -> None:
                self.enqueued: list[object] = []

            def enqueue(self, queue: str, job: object) -> None:
                self.enqueued.append((queue, job))

        _stub = _RecordingSAQStub()
        set_saq_client(_stub)
        yield
        set_saq_client(None)
    except ImportError:
        # Source module not yet importable (RED phase) — fall
        # through to the original no-op behaviour.
        yield
