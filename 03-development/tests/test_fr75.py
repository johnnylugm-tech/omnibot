"""TDD-RED: failing tests for FR-75 — SAQ Worker configuration.

Spec source: 02-architecture/TEST_SPEC.md (FR-75)
SRS source : SRS.md FR-75 (Module 16: Background Job System)

Acceptance criteria (from SRS FR-75):
    SAQ Worker: queues=embedding(high, concurrency=3, timeout=30s)
              + maintenance(low, concurrency=1, timeout=60s)
              + notification(high, concurrency=5, timeout=10s);
              stop_grace_period=30s（SIGTERM 緩衝）.
    Worker 正確訂閱各 queue；SIGTERM 後等待 30s 完成當前任務.

The four TEST_SPEC cases (function names MUST match exactly):
    1. test_fr75_embedding_queue_high_concurrency_3
         Inputs: queue="embedding"; priority="high"; concurrency="3"
         Type  : happy_path
    2. test_fr75_notification_queue_high_concurrency_5
         Inputs: queue="notification"; priority="high"; concurrency="5"
         Type  : happy_path
    3. test_fr75_sigterm_waits_30s_grace
         Inputs: signal="SIGTERM"; grace_seconds="30"
         Type  : happy_path
    4. test_fr75_maintenance_queue_low_concurrency_1
         Inputs: queue="maintenance"; priority="low"; concurrency="1"
         Type  : boundary

Sub-assertion (per TEST_SPEC):
    fr75-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Test isolation — SAQ workers connect to a Redis broker and run async
# consumers. Both are real network I/O and must NOT happen in unit tests.
#
# GREEN contract for the worker module:
#   - The worker class MUST accept an injected Redis client (sync OR
#     async) so tests can pass fakeredis / a stub.
#   - ``setup_signal_handlers(loop)`` MUST be a method that takes an
#     asyncio event loop and registers SIGTERM/SIGINT handlers — but the
#     handlers themselves MUST read the grace period from a module-level
#     constant ``STOP_GRACE_PERIOD_SECONDS`` so the tests can pin the
#     value without intercepting OS signals.
#   - The 3-queue specification MUST be exposed as an immutable mapping
#     ``QUEUE_CONFIGS: Mapping[str, QueueConfig]`` (or a list of
#     ``QueueConfig``) at module scope so configuration tests can pin
#     priority/concurrency/timeout per queue without booting a worker.
#
# The autouse fixture below is a no-op during RED (the import below
# raises Collection Error before the fixture runs) and patches any
# real Redis construction once GREEN has landed.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_saq_redis(monkeypatch):
    """Prevent real Redis I/O during SAQ worker unit tests.

    The SAQ library normally builds its own Redis connection from a URL
    passed at startup; once GREEN lands, monkeypatch ``redis.Redis`` /
    ``redis.asyncio.Redis`` here so the test can never escape into a
    real socket. Tests assert configuration only, so the stub is
    sufficient.
    """
    yield


# ---------------------------------------------------------------------------
# Source under test.
#
# FR-75 (SRS.md line 173 + SAD §Module: jobs.py line 320) requires:
#
#   1. ``app.infra.jobs`` MUST export a ``QueueConfig`` dataclass
#      (frozen=True) with at minimum:
#         name        : str
#         priority    : Literal["high", "medium", "low"]
#         concurrency : int   (worker count for this queue)
#         timeout     : int | float   (per-job timeout in seconds)
#
#   2. ``app.infra.jobs`` MUST export a module-level
#      ``QUEUE_CONFIGS`` collection (Mapping or Sequence) that contains
#      EXACTLY three entries — one per SRS queue — with the spec values:
#         "embedding"     -> priority="high",   concurrency=3, timeout=30
#         "maintenance"   -> priority="low",    concurrency=1, timeout=60
#         "notification"  -> priority="high",   concurrency=5, timeout=10
#
#   3. ``app.infra.jobs`` MUST export a module-level constant
#      ``STOP_GRACE_PERIOD_SECONDS = 30`` that the SIGTERM handler
#      reads when deciding how long to wait for in-flight jobs.
#
#   4. The module MUST expose a ``get_queue_config(name) -> QueueConfig``
#      helper that returns the named queue's config (or raises
#      ``KeyError`` if the name is unknown).
#
# These imports are unguarded on purpose: pytest MUST fail with
# Collection Error (Exit Code 2) because ``app.infra.jobs`` is not yet
# defined. That is the valid RED signal — GREEN adds the module.
# ---------------------------------------------------------------------------
from app.infra.jobs import (  # noqa: E402,F401
    QUEUE_CONFIGS,
    STOP_GRACE_PERIOD_SECONDS,
    QueueConfig,
    get_queue_config,
)

# ---------------------------------------------------------------------------
# Spec-pinned trigger values — keep these in lock-step with TEST_SPEC.md.
# A drift here (e.g. changing "3" -> "4") will silently break the
# spec-coverage check's exact-match lookup.
# ---------------------------------------------------------------------------
_FR75_QUEUE_SPECS: dict[str, dict[str, object]] = {
    "embedding":    {"priority": "high", "concurrency": 3, "timeout": 30},
    "maintenance":  {"priority": "low",  "concurrency": 1, "timeout": 60},
    "notification": {"priority": "high", "concurrency": 5, "timeout": 10},
}


def _lookup_queue(name: str):
    """Return the QueueConfig for ``name`` regardless of container type.

    GREEN may choose either a Mapping (dict) or a Sequence (tuple/list)
    for ``QUEUE_CONFIGS``. Normalise both shapes to a single
    ``QueueConfig`` (or None if the queue is missing) so the four
    spec tests can share this lookup.
    """
    # GREEN TODO: QUEUE_CONFIGS must be a Mapping[str, QueueConfig]
    # OR a Sequence[QueueConfig] where each element carries ``name``.
    container = QUEUE_CONFIGS

    if hasattr(container, "items"):
        # Mapping[str, QueueConfig]
        cfg = container.get(name)  # type: ignore[union-attr]
    else:
        # Sequence[QueueConfig]
        cfg = None
        for entry in container:  # type: ignore[union-attr]
            if getattr(entry, "name", None) == name:
                cfg = entry  # type: ignore[assignment]
                break
    return cfg


# ---------------------------------------------------------------------------
# 1. The ``embedding`` queue MUST be configured with priority="high"
#    and concurrency=3 (SRS FR-75 acceptance: "Worker 正確訂閱各 queue").
#
# Spec input: queue="embedding"; priority="high"; concurrency="3".
# Spec sub-assertion: fr75-ok: result is not None.
# Test type: happy_path.
#
# A regression that dropped concurrency below 3 would slow knowledge-base
# ingestion past the FR-76 p95 <30s budget; a regression that flipped
# priority to "low" would starve embedding behind maintenance tasks.
# ---------------------------------------------------------------------------
def test_fr75_embedding_queue_high_concurrency_3():
    queue = "embedding"
    expected_priority = "high"
    expected_concurrency = 3

    # GREEN TODO: get_queue_config(name) must return the QueueConfig
    # for the embedding queue — see app/infra/jobs.py.
    cfg = get_queue_config(queue)

    # Spec fr75-ok predicate 'result is not None' applies_to case 1.
    result = cfg
    assert result is not None, "fr75-ok predicate: result must not be None"

    # Priority MUST be "high" for the embedding queue.
    actual_priority = getattr(cfg, "priority", None)
    assert actual_priority == expected_priority, (
        f"FR-75 queue={queue!r} priority must be "
        f"{expected_priority!r}; got {actual_priority!r}"
    )

    # Concurrency MUST equal 3 (SRS: "embedding ... concurrency=3").
    actual_concurrency = getattr(cfg, "concurrency", None)
    assert actual_concurrency == expected_concurrency, (
        f"FR-75 queue={queue!r} concurrency must be "
        f"{expected_concurrency}; got {actual_concurrency}"
    )

    # Defensive: the QUEUE_CONFIGS collection itself MUST carry the same
    # entry. A regression that wired ``get_queue_config`` correctly but
    # omitted the embedding entry from the module-level collection would
    # silently break the worker's boot-time subscription loop.
    container_cfg = _lookup_queue(queue)
    assert container_cfg is not None, (
        f"FR-75 QUEUE_CONFIGS must include the {queue!r} queue; "
        f"lookup returned None"
    )
    assert getattr(container_cfg, "priority", None) == expected_priority, (
        f"FR-75 QUEUE_CONFIGS[{queue!r}].priority must be "
        f"{expected_priority!r}; got "
        f"{getattr(container_cfg, 'priority', None)!r}"
    )
    assert getattr(container_cfg, "concurrency", None) == expected_concurrency, (
        f"FR-75 QUEUE_CONFIGS[{queue!r}].concurrency must be "
        f"{expected_concurrency}; got "
        f"{getattr(container_cfg, 'concurrency', None)}"
    )


# ---------------------------------------------------------------------------
# 2. The ``notification`` queue MUST be configured with priority="high"
#    and concurrency=5 (SRS FR-75).
#
# Spec input: queue="notification"; priority="high"; concurrency="5".
# Test type: happy_path.
#
# The notification queue has the highest concurrency (5) because
# customer-facing notifications fan out to many platforms; dropping
# concurrency below 5 would cause backlog during peak hours (FR-73
# EscalationQueueBacklog alert fires at depth=50).
# ---------------------------------------------------------------------------
def test_fr75_notification_queue_high_concurrency_5():
    queue = "notification"
    expected_priority = "high"
    expected_concurrency = 5

    # GREEN TODO: get_queue_config(name) must return the QueueConfig
    # for the notification queue.
    cfg = get_queue_config(queue)

    # Sanity: cfg must not be None (predicate 'fr75-ok' technically
    # applies to case 1 only, but a missing notification queue would
    # silently disable all customer notifications, which is worse than
    # a None result).
    assert cfg is not None, (
        f"FR-75 get_queue_config({queue!r}) must return a QueueConfig; "
        f"got None"
    )

    actual_priority = getattr(cfg, "priority", None)
    assert actual_priority == expected_priority, (
        f"FR-75 queue={queue!r} priority must be "
        f"{expected_priority!r}; got {actual_priority!r}"
    )

    actual_concurrency = getattr(cfg, "concurrency", None)
    assert actual_concurrency == expected_concurrency, (
        f"FR-75 queue={queue!r} concurrency must be "
        f"{expected_concurrency}; got {actual_concurrency}"
    )

    # Timeout MUST be 10s (SRS: "notification ... timeout=10s").
    expected_timeout = _FR75_QUEUE_SPECS["notification"]["timeout"]
    actual_timeout = getattr(cfg, "timeout", None)
    assert actual_timeout == expected_timeout, (
        f"FR-75 queue={queue!r} timeout must be "
        f"{expected_timeout}s; got {actual_timeout}"
    )


# ---------------------------------------------------------------------------
# 3. SIGTERM MUST trigger a 30-second grace period before the worker
#    is forced to exit (SRS FR-75: "stop_grace_period=30s（SIGTERM 緩衝）").
#
# Spec input: signal="SIGTERM"; grace_seconds="30".
# Test type: happy_path.
#
# A regression that shortened the grace period to e.g. 5s would cause
# in-flight embedding jobs to be killed mid-flight, leaving
# ``embedding_synced_at`` permanently NULL (FR-79 UI shows 🔴) and
# breaking the FR-77 searchable-within-2.5s guarantee. A regression
# that lengthened it to 120s would block k8s rolling updates past the
# default 30s terminationGracePeriodSeconds, causing CrashLoopBackOff.
# ---------------------------------------------------------------------------
def test_fr75_sigterm_waits_30s_grace():
    signal_name = "SIGTERM"
    expected_grace_seconds = 30

    # GREEN TODO: app.infra.jobs must export STOP_GRACE_PERIOD_SECONDS
    # as a module-level constant read by the SIGTERM handler at boot.
    actual_grace = STOP_GRACE_PERIOD_SECONDS

    # Spec fr75-ok predicate applies_to case 1; this is case 3 but the
    # local sanity check below covers the same shape — the grace
    # constant MUST be a positive number.
    assert actual_grace is not None, (
        "FR-75 STOP_GRACE_PERIOD_SECONDS must be exposed as a "
        "module-level constant"
    )

    # Type guard — must be numeric (int or float), not a string like
    # "30s" or None.
    assert isinstance(actual_grace, (int, float)) and not isinstance(
        actual_grace, bool
    ), (
        f"FR-75 STOP_GRACE_PERIOD_SECONDS must be a numeric value; "
        f"got {type(actual_grace).__name__}={actual_grace!r}"
    )

    # Exact-match assertion — 30s is the SRS-pinned grace period.
    assert actual_grace == expected_grace_seconds, (
        f"FR-75 SIGTERM grace period must be "
        f"{expected_grace_seconds}s; got {actual_grace}s"
    )

    # Lower-bound guard — a grace period <= 0 would mean SIGTERM kills
    # the worker immediately, which contradicts the spec.
    assert actual_grace > 0, (
        f"FR-75 SIGTERM grace period must be > 0s; got {actual_grace}s"
    )

    # Upper-bound guard — the value MUST be finite (no math.inf). An
    # infinite grace would defeat k8s rolling updates.
    import math
    assert math.isfinite(actual_grace), (
        f"FR-75 SIGTERM grace period must be finite; got {actual_grace}"
    )

    # Cross-check: the local trigger block matches the spec input.
    if signal_name == "SIGTERM" and expected_grace_seconds == 30:
        assert actual_grace == 30


# ---------------------------------------------------------------------------
# 4. The ``maintenance`` queue MUST be configured with priority="low"
#    and concurrency=1 (SRS FR-75).
#
# Spec input: queue="maintenance"; priority="low"; concurrency="1".
# Test type: boundary (concurrency=1 is the minimum).
#
# A regression that raised maintenance concurrency above 1 would let a
# runaway maintenance job starve the embedding queue (priority=high
# but shared worker pool). Concurrency=1 forces serial execution and
# makes budget overruns visible in the Prometheus
# ``escalation_queue_size`` gauge (FR-71 metric #6).
# ---------------------------------------------------------------------------
def test_fr75_maintenance_queue_low_concurrency_1():
    queue = "maintenance"
    expected_priority = "low"
    expected_concurrency = 1

    # GREEN TODO: get_queue_config(name) must return the QueueConfig
    # for the maintenance queue.
    cfg = get_queue_config(queue)

    assert cfg is not None, (
        f"FR-75 get_queue_config({queue!r}) must return a QueueConfig; "
        f"got None"
    )

    actual_priority = getattr(cfg, "priority", None)
    assert actual_priority == expected_priority, (
        f"FR-75 queue={queue!r} priority must be "
        f"{expected_priority!r}; got {actual_priority!r}"
    )

    actual_concurrency = getattr(cfg, "concurrency", None)
    assert actual_concurrency == expected_concurrency, (
        f"FR-75 queue={queue!r} concurrency must be "
        f"{expected_concurrency} (boundary: minimum); "
        f"got {actual_concurrency}"
    )

    # Timeout MUST be 60s (SRS: "maintenance ... timeout=60s").
    expected_timeout = _FR75_QUEUE_SPECS["maintenance"]["timeout"]
    actual_timeout = getattr(cfg, "timeout", None)
    assert actual_timeout == expected_timeout, (
        f"FR-75 queue={queue!r} timeout must be "
        f"{expected_timeout}s; got {actual_timeout}"
    )

    # Concurrency MUST be exactly 1 (boundary case). A regression that
    # bumped it to 2 or 3 would break the serial-execution invariant.
    assert actual_concurrency == 1, (
        f"FR-75 maintenance concurrency must be exactly 1; "
        f"got {actual_concurrency}"
    )
