"""[FR-81] Exponential backoff retry strategy.

Implements the FR-81 retry contract for transient-failure handling
across the omnibot subsystems. The strategy is parameterised and has
no external dependencies; callers inject the callable so the same
strategy can wrap sync or short-lived coroutines, and the test suite
can drive it without I/O.

[FR-81] ``delay = min(base_delay * 2 ** attempt, max_delay) *
       uniform(0.5, 1.0)`` when ``jitter`` is True. The jitter
       factor is drawn from ``[0.5, 1.0]`` so the jittered delay
       stays in ``[0.5 * capped, capped]`` — it never exceeds the
       cap and never drops below half the cap. With ``jitter``
       False the multiplicative factor is exactly 1.0 (deterministic).
       After ``max_retries`` unsuccessful invocations of the wrapped
       callable the original exception is re-raised. The attempt
       counter starts at 0, so ``max_retries=3`` permits at most
       3 calls before giving up. The jitter range is what prevents
       the thundering-herd collapse documented in SRS FR-81.

Citations:
- SRS.md FR-81 (Module 17: High Availability) — SRS.md:184 — max_retries=3,
  base_delay=1.0s, max_delay=30.0s, jitter=True, formula
  ``min(base * 2^attempt, max) * (0.5 + random())`` (jitter factor
  uniform on [0.5, 1.0] in this implementation; matches SRS
  acceptance criteria "delay 上限 30s" and "jitter 避免 thundering herd")
- SRS.md:1051 — EmbeddingJob retry contract shares the same
  max_retries=3 + exponential-backoff+jitter shape
- SRS.md:1092-1097 — FR-81 description & verification method
- 02-architecture/TEST_SPEC.md:1640-1657 — FR-81 cases (5):
  3-retries-then-stop, delay capped at 30s, jitter applied,
  base_delay=1s attempt=1 range, no thundering herd under
  concurrency; predicate ``fr81-ok`` ``result is not None`` applies
  to case 1
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from typing import Any


class RetryStrategy:
    """Exponential backoff retry strategy (FR-81).

    Parameters are keyword-only so the call site is self-documenting;
    the defaults match the SRS FR-81 mandate. ``compute_delay`` is
    pure (modulo ``random``) and is exposed so callers and tests can
    reason about the chosen delay without actually sleeping.
    ``execute_with_retry`` is the side-effectful wrapper that
    invokes the callable and sleeps between attempts.
    """

    def __init__(
        self,
        *,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        jitter: bool = True,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    def compute_delay(self, attempt: int) -> float:
        """Return the delay (seconds) before the next retry.

        Implements ``min(base_delay * 2 ** attempt, max_delay) *
        uniform(0.5, 1.0)`` when ``jitter`` is True. The jitter factor
        is drawn uniformly from ``[0.5, 1.0]`` so the jittered delay
        never exceeds the cap and the floor is half the cap — this
        both spreads concurrent retries (anti-thundering-herd) and
        keeps the upper bound equal to the raw exponential value.
        When ``jitter`` is False the multiplicative factor is exactly
        1.0 so the result is deterministic for tests that pin the seed.
        """
        raw = self.base_delay * (2 ** attempt)
        capped = min(raw, self.max_delay)
        if self.jitter:
            return capped * random.uniform(0.5, 1.0)
        return capped

    def execute_with_retry(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Invoke ``fn(*args, **kwargs)`` and retry on exception.

        On exception, sleep for ``compute_delay(attempt)`` and try
        again. After ``max_retries`` unsuccessful attempts the
        original exception is re-raised untouched. The attempt
        counter starts at 0, so ``max_retries=3`` permits at most
        3 calls before giving up.
        """
        attempt = 0
        while True:
            try:
                return fn(*args, **kwargs)
            except Exception:
                attempt += 1
                if attempt >= self.max_retries:
                    raise
                time.sleep(self.compute_delay(attempt))
