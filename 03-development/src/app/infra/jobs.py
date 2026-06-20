"""[FR-75] SAQ Worker configuration — queue registry + SIGTERM grace.

Module 16 (Background Job System) — declares the three production queues
and the SIGTERM grace window the worker honors at shutdown.

[FR-75] Three SAQ queues MUST be configured exactly as the SRS pins:
   - ``embedding``    : priority="high", concurrency=3, timeout=30s
   - ``maintenance``  : priority="low",  concurrency=1, timeout=60s
   - ``notification`` : priority="high", concurrency=5, timeout=10s
   ``STOP_GRACE_PERIOD_SECONDS`` MUST equal ``30`` so SIGTERM waits 30s
   for in-flight jobs before the worker is forced to exit (k8s default
   ``terminationGracePeriodSeconds`` is 30s; longer would cause
   CrashLoopBackOff on rolling updates, shorter would kill mid-flight
   embedding jobs and break the FR-77 searchable-within-2.5s guarantee).

Citations:
- SRS.md FR-75 (description line 173)
- 02-architecture/TEST_SPEC.md FR-75 (line 1525, cases 1-4)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping


# ---------------------------------------------------------------------------
# Public configuration shapes.
# ---------------------------------------------------------------------------
Priority = Literal["high", "medium", "low"]


@dataclass(frozen=True)
class QueueConfig:
    """Immutable SAQ queue configuration pinned by FR-75.

    ``frozen=True`` so accidental boot-time mutation cannot shift a
    queue's concurrency after the worker pool is already sized.
    """

    name: str
    priority: Priority
    concurrency: int
    timeout: int | float


# SRS FR-75 — exact-match table; see TEST_SPEC.md line 1525.
QUEUE_CONFIGS: Mapping[str, QueueConfig] = {
    "embedding": QueueConfig(
        name="embedding", priority="high", concurrency=3, timeout=30,
    ),
    "maintenance": QueueConfig(
        name="maintenance", priority="low", concurrency=1, timeout=60,
    ),
    "notification": QueueConfig(
        name="notification", priority="high", concurrency=5, timeout=10,
    ),
}


# SRS FR-75 — SIGTERM grace window the worker honors at shutdown.
STOP_GRACE_PERIOD_SECONDS: int = 30


def get_queue_config(name: str) -> QueueConfig:
    """Return the ``QueueConfig`` for ``name``; raise ``KeyError`` if unknown."""
    return QUEUE_CONFIGS[name]