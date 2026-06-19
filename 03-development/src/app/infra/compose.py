"""[FR-95] Docker Compose 開發環境 — 七大 service 健康狀態追蹤與
``/api/v1/health`` 端點契約.

This module is the **stateless descriptor** for the FR-95 dev stack
(``docker compose up`` 後所有 services healthy; health 端點回 200).
``ComposeHealth`` is the in-memory abstraction exercised by unit tests
and by the FastAPI route handler that exposes ``/api/v1/health``;
nothing here performs real Docker / docker-compose / HTTP I/O — those
live in the bootstrapper / route layer, which keeps FR-95 unit-testable
without a running container runtime.

Required surface:
    - ``REQUIRED_SERVICES``: the seven canonical service names mandated
      by FR-95.
    - ``ComposeHealth``: tracks live health per service, exposes
      ``mark``, ``status_of``, ``overall_status`` and ``health_endpoint``.

Citations:
- SRS.md FR-95 (Module 22: Deployment — Docker Compose 開發環境)
- 02-architecture/TEST_SPEC.md FR-95 (3 cases:
  test_fr95_all_7_services_healthy,
  test_fr95_health_endpoint_200_after_compose_up,
  test_fr95_unhealthy_service_reports_degraded_status)
- 03-development/tests/test_fr95.py
"""

from __future__ import annotations
from collections.abc import Iterable


# Canonical seven service names mandated by FR-95. Order is not part of
# the contract (tests assert on membership), but it mirrors the docker
# compose file so logs read naturally.
REQUIRED_SERVICES = (
    "omnibot-api",
    "postgres",
    "redis",
    "otel-collector",
    "prometheus",
    "grafana",
    "worker",
)

# Per-service health markers. A service is either HEALTHY or UNHEALTHY;
# the stack-level aggregate is HEALTHY iff every service is HEALTHY,
# otherwise DEGRADED.
HEALTHY = "healthy"
UNHEALTHY = "unhealthy"
DEGRADED = "degraded"

# HTTP status codes surfaced by ``/api/v1/health``. 200 when the stack
# is fully healthy; 503 (Service Unavailable) when any service has
# degraded the aggregate — the canonical signal for operators and
# external uptime monitors.
HTTP_OK = 200
HTTP_SERVICE_UNAVAILABLE = 503


class ComposeHealth:
    """Tracks the live health of every service in ``REQUIRED_SERVICES``.

    Constructing with no arguments seeds every required service to
    ``HEALTHY`` — the post-``docker compose up`` steady state.
    """

    def __init__(self, services: Iterable[str] | None = None) -> None:
        if services is None:
            services = REQUIRED_SERVICES
        self._status: dict[str, str] = dict.fromkeys(services, HEALTHY)

    def mark(self, service: str, status: str) -> None:
        """Record ``status`` for ``service``."""
        self._status[service] = status

    def status_of(self, service: str) -> str:
        """Return the current status string for ``service``."""
        return self._status[service]

    def overall_status(self) -> str:
        """Return ``HEALTHY`` iff every service is healthy; else ``DEGRADED``."""
        if all(s == HEALTHY for s in self._status.values()):
            return HEALTHY
        return DEGRADED

    def health_endpoint(self) -> tuple[int, dict]:
        """Return ``(http_status, body)`` for ``/api/v1/health``."""
        if self.overall_status() == HEALTHY:
            return HTTP_OK, {"status": HEALTHY}
        unhealthy = [s for s, v in self._status.items() if v != HEALTHY]
        # Surface DEGRADED with HTTP 503 and the failing service list so
        # operators can locate the broken component without grepping
        # compose logs.
        return HTTP_SERVICE_UNAVAILABLE, {"status": DEGRADED, "unhealthy": unhealthy}
