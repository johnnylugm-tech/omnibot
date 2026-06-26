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

NFR Pattern markers (NP-01..NP-15) and layer markers (unit / integration / e2e)
are auto-assigned via `pytest_collection_modifyitems` below, derived from the
test filename (test_frNN.py) and TEST_SPEC.md FR→NP mapping. This avoids
editing all 108 test files individually.
"""

from __future__ import annotations

import os
import re
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

# ---------------------------------------------------------------------------
# Auto-assign NFR pattern + layer markers from filename
# ---------------------------------------------------------------------------

# FR → NP mapping (NP-01..NP-15). Built from TEST_SPEC.md NFR Pattern
# Activation table plus module-based fallback for FRs without explicit
# Active Patterns (Step 1b in derive_test_cases.md).
_FR_TO_NP: dict[int, list[str]] = {
    1: ["NP-01", "NP-03"], 2: ["NP-01", "NP-03"], 3: ["NP-01"], 4: ["NP-01"],
    5: ["NP-01", "NP-03"], 6: ["NP-01"], 9: ["NP-12"],
    10: ["NP-06", "NP-07", "NP-08", "NP-15"],
    11: ["NP-06", "NP-07", "NP-08", "NP-15"],
    12: ["NP-06", "NP-07", "NP-15"],
    13: ["NP-06", "NP-07", "NP-15"],
    14: ["NP-06", "NP-07", "NP-15"],
    15: ["NP-06", "NP-07", "NP-15"],
    16: ["NP-07", "NP-09", "NP-15"], 17: ["NP-07", "NP-09", "NP-15"],
    18: ["NP-08"], 19: ["NP-08"], 20: ["NP-09"],
    21: ["NP-03", "NP-07", "NP-13"], 22: ["NP-07"], 23: ["NP-02", "NP-07"],
    24: ["NP-07"], 25: ["NP-07"],
    26: ["NP-06", "NP-07", "NP-15"], 27: ["NP-06", "NP-07", "NP-15"],
    28: ["NP-07", "NP-15"], 29: ["NP-06", "NP-07", "NP-15"],
    30: ["NP-06", "NP-07", "NP-15"], 31: ["NP-07", "NP-15"],
    32: ["NP-07", "NP-15"], 33: ["NP-07", "NP-15"],
    34: ["NP-13"], 35: ["NP-13"], 36: ["NP-13"], 37: ["NP-13"],
    38: ["NP-06", "NP-13"],
    39: ["NP-07", "NP-15"], 40: ["NP-07", "NP-15"], 41: ["NP-07", "NP-15"],
    42: ["NP-07", "NP-15"], 43: ["NP-07", "NP-15"], 45: ["NP-07", "NP-15"],
    46: ["NP-06"],
    53: ["NP-12"], 54: ["NP-05", "NP-09"], 55: ["NP-06"], 56: ["NP-09"],
    57: ["NP-01", "NP-15"], 58: ["NP-01"], 59: ["NP-15"],
    60: ["NP-02"], 61: ["NP-02"], 62: ["NP-02"],
    65: ["NP-07", "NP-15"], 66: ["NP-07", "NP-15"], 67: ["NP-07", "NP-15"],
    68: ["NP-06", "NP-07", "NP-15"], 69: ["NP-07", "NP-15"],
    70: ["NP-09"], 71: ["NP-09"], 72: ["NP-09"],
    73: ["NP-06"], 74: ["NP-06"],
    75: ["NP-07", "NP-15"], 76: ["NP-07", "NP-15"], 77: ["NP-07", "NP-15"],
    78: ["NP-06", "NP-07", "NP-15"], 79: ["NP-07", "NP-15"],
    80: ["NP-13", "NP-15"], 81: ["NP-13"],
    82: ["NP-10"], 83: ["NP-11"], 84: ["NP-01", "NP-03", "NP-04"],
    85: ["NP-01", "NP-02", "NP-12"], 86: ["NP-01"], 87: ["NP-01"],
    88: ["NP-05", "NP-09"], 89: ["NP-14"], 90: ["NP-14"],
    91: ["NP-09", "NP-10"], 92: ["NP-05", "NP-09"], 94: ["NP-14"],
    96: ["NP-11", "NP-13"], 97: ["NP-06"], 98: ["NP-11"],
    99: ["NP-07", "NP-13", "NP-15"], 100: ["NP-07", "NP-15"],
    101: ["NP-06"], 103: ["NP-06"], 106: ["NP-06"],
}

# FR → test layer (unit / integration / e2e) derived from TEST_SPEC Classification
_FR_TO_LAYER: dict[int, str] = {
    1: "integration", 2: "integration", 3: "integration", 4: "integration",
    5: "integration", 6: "integration",
    7: "unit", 8: "unit", 9: "unit",
    10: "integration", 11: "integration", 12: "integration",
    13: "integration", 14: "integration", 15: "integration",
    16: "integration", 17: "integration",
    18: "unit", 19: "unit", 20: "unit",
    21: "integration", 22: "integration", 23: "integration",
    24: "integration", 25: "integration",
    26: "integration", 27: "integration", 28: "integration",
    29: "integration", 30: "integration", 31: "integration",
    32: "integration", 33: "integration",
    34: "unit", 35: "unit", 36: "unit", 37: "unit", 38: "unit",
    39: "unit", 40: "unit", 41: "unit", 42: "unit", 43: "unit", 45: "unit",
    46: "unit", 47: "unit", 48: "unit", 49: "unit",
    50: "unit", 51: "unit", 52: "unit", 53: "unit",
    54: "integration", 55: "integration", 56: "integration",
    57: "integration", 58: "integration", 59: "integration",
    60: "unit", 61: "unit", 62: "unit", 63: "unit", 64: "unit",
    65: "integration", 66: "integration", 67: "integration",
    68: "integration", 69: "integration",
    70: "integration", 71: "integration", 72: "integration",
    73: "integration", 74: "integration",
    75: "integration", 76: "integration", 77: "integration",
    78: "integration", 79: "integration",
    80: "integration", 81: "integration",
    82: "integration", 83: "integration",
    84: "integration", 85: "integration", 86: "integration",
    87: "integration", 88: "integration",
    89: "e2e", 90: "e2e", 91: "e2e", 92: "e2e", 93: "e2e", 94: "e2e", 95: "e2e",
    96: "e2e", 97: "e2e", 98: "e2e", 99: "e2e", 100: "e2e", 101: "e2e",
    102: "e2e", 103: "e2e", 104: "e2e", 105: "e2e", 106: "e2e", 107: "e2e", 108: "e2e",
}

_FR_FROM_FILENAME = re.compile(r"test_fr(\d+)\.py$")


class _RecordingSAQStub:
    """Module-level test double for the SAQ client surface used by
    ``app.infra.jobs``. Exposed here so tests that need to re-install
    the autouse stub (e.g. FR-201 case 4) can import it directly.

    Implements both the enqueue path (FR-77/78/200 — sync
    ``.enqueue(name, job)``) and the cancel path (FR-201 — async
    ``.abort(job_id, error, ttl)``). Does NOT actually touch Redis;
    tests that need the real cancel monkeypatch
    ``app.infra.jobs.cancel_embedding_jobs_for`` directly rather than
    relying on this stub.
    """

    def __init__(self) -> None:
        self.enqueued: list[tuple[str, object]] = []
        self.aborted: list[tuple[str, str, int]] = []

    def enqueue(self, queue: str, job: object) -> object:
        self.enqueued.append((queue, job))
        return job

    async def abort(self, job_id: str, error: str = "", ttl: int = 5) -> None:
        self.aborted.append((job_id, error, ttl))


def pytest_collection_modifyitems(config, items):  # pyright: ignore[reportUnusedParameter]
    """Auto-assign @pytest.mark.npXX and layer markers to test_fr*.py functions.

    Reads the FR number from the test filename, looks up the NFR patterns and
    test layer from the _FR_TO_NP / _FR_TO_LAYER dicts above, and applies
    markers via `item.add_marker`. This is the canonical F-06 fix: every
    test_fr*.py function now carries NP markers without per-file edits.
    """
    for item in items:
        m = _FR_FROM_FILENAME.search(str(item.fspath))
        if not m:
            continue
        fr_num = int(m.group(1))
        for np in _FR_TO_NP.get(fr_num, []):
            marker_name = np.lower().replace("-", "")  # NP-07 → np07
            item.add_marker(getattr(pytest.mark, marker_name))
        layer = _FR_TO_LAYER.get(fr_num)
        if layer:
            item.add_marker(getattr(pytest.mark, layer))

@pytest.fixture(autouse=True)
def _isolate_external_services(monkeypatch):  # pyright: ignore[reportUnusedFunction]
    # type: ignore[no-untyped-def]
    """Prevent real Redis/DB/HTTP I/O during unit tests."""
    # Test-mode env gate — production code paths read ``TESTING=1`` to
    # opt in to test-only overrides (e.g. ``RBACEnforcer._resolve_role``
    # accepts the ``role=`` kwarg only under this flag, preventing
    # production callers from forging a privileged role via kwargs).
    # Set here, not at module import time, so a test that explicitly
    # wants the production code path can clear it via monkeypatch.delenv
    # and observe the real failure mode.
    monkeypatch.setenv("TESTING", "1")
    # FR-77/FR-78 — install a recording SAQ stub so any call into
    # ``app.infra.jobs.enqueue_embedding_job`` succeeds instead of
    # raising the boot-time-misconfiguration ``RuntimeError`` the
    # production wiring enforces. Tests that explicitly want the
    # misconfiguration path can call ``set_saq_client(None)`` to
    # override the autouse stub.
    try:
        from app.infra.jobs import set_saq_client

        class _RecordingSAQStub:  # noqa: F811 — see module-level copy below
            """In-fixture copy (kept for try-block resilience); the
            canonical module-level ``_RecordingSAQStub`` above is the
            one tests import via ``from tests.conftest import
            _RecordingSAQStub``."""

            def __init__(self) -> None:
                self.enqueued: list[tuple[str, object]] = []
                self.aborted: list[tuple[str, str, int]] = []

            def enqueue(self, queue: str, job: object) -> object:
                self.enqueued.append((queue, job))
                return job

            async def abort(self, job_id: str, error: str = "", ttl: int = 5) -> None:
                self.aborted.append((job_id, error, ttl))

        _stub = _RecordingSAQStub()
        set_saq_client(_stub)
        yield
        set_saq_client(None)
    except ImportError:
        # Source module not yet importable (RED phase) — fall
        # through to the original no-op behaviour.
        yield
