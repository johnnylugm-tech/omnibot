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

import pytest


@pytest.fixture(autouse=True)
def _isolate_external_services(monkeypatch):
    """Prevent real Redis/DB/HTTP I/O during unit tests."""
    yield