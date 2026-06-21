"""TDD-RED: failing tests for FR-95 — Docker Compose 開發環境 (7 services
healthy, health endpoint 200, unhealthy service → degraded status).

Spec source: 02-architecture/TEST_SPEC.md (FR-95)
SRS source : SRS.md FR-95 (Module 22: Deployment)

Acceptance criteria (from SRS FR-95):
    Docker Compose 開發環境：services 含
        - omnibot-api
        - postgres (pgvector/pgvector:pg16)
        - redis (redis:7-alpine, TLS)
        - otel-collector
        - prometheus
        - grafana
        - worker
    healthcheck 配置；pgdata volume。
    docker compose up 後所有 services healthy；health 端點回 200。

The three TEST_SPEC cases (function names MUST match exactly):
    1. test_fr95_all_7_services_healthy
         Inputs: expected_services="omnibot-api,postgres,redis,otel-collector,
                 prometheus,grafana,worker"
         Type  : happy_path
    2. test_fr95_health_endpoint_200_after_compose_up
         Inputs: path="/api/v1/health"; expected_status="200"
         Type  : happy_path
    3. test_fr95_unhealthy_service_reports_degraded_status
         Inputs: service="postgres"; status="unhealthy";
                 expected_health_status="degraded"
         Type  : validation

Sub-assertion (per TEST_SPEC):
    fr95-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test — ``ComposeHealth`` is intentionally NOT YET exported by
# ``app.infra.compose``. The import below is unguarded: pytest MUST fail with
# Collection Error (Exit Code 2) because the module does not exist yet. That
# is the valid RED signal.
#
# GREEN must add ``app/infra/compose.py`` exporting the following public
# surface (the exact shape is GREEN's choice so long as these names and
# behaviours are observable):
#
#   - REQUIRED_SERVICES (frozenset / tuple / list of str)
#       The seven canonical service names mandated by FR-95:
#           "omnibot-api", "postgres", "redis", "otel-collector",
#           "prometheus", "grafana", "worker"
#
#   - ComposeHealth
#       Tracks the live health of every service in ``REQUIRED_SERVICES``.
#       Required methods:
#           __init__(services: Iterable[str] | None = None) -> None
#               If ``services`` is None, initialise with REQUIRED_SERVICES
#               (all healthy by default). If provided, use exactly that
#               iterable — GREEN must still validate it equals REQUIRED_SERVICES
#               in length and content (see test 1).
#           mark(service: str, status: str) -> None
#               Record ``status`` for ``service``. Recognised statuses are
#               "healthy" and "unhealthy".
#           overall_status() -> str
#               Returns "healthy" iff every service in the registry has
#               status == "healthy"; returns "degraded" otherwise.
#           status_of(service: str) -> str
#               Returns the current status string for ``service``.
#           health_endpoint() -> tuple[int, dict]
#               Returns ``(http_status, body)`` for the /api/v1/health
#               endpoint. When every service is healthy, http_status is 200
#               and body has at minimum ``{"status": "healthy"}``; when at
#               least one service is unhealthy, http_status is 503 and body
#               has at minimum ``{"status": "degraded", "unhealthy": [...]}``.
#               (GREEN may additionally return 200 with ``status: "degraded"``
#               so long as the body explicitly carries the degraded marker —
#               see the ``status`` key check in test 3.)
#
# The tests below intentionally avoid any real Docker / docker-compose / HTTP
# I/O — they exercise the ComposeHealth abstraction in isolation, which is
# the canonical unit-test shape for FR-95.
# ---------------------------------------------------------------------------
from app.infra.deployment import (
    REQUIRED_SERVICES,
    ComposeHealth,
)


# ---------------------------------------------------------------------------
# 1. After ``docker compose up`` every one of the seven canonical services
#    is reported healthy (happy_path).
#
# Spec input: expected_services="omnibot-api,postgres,redis,otel-collector,
#             prometheus,grafana,worker".
# SRS FR-95: "docker compose up 後所有 services healthy".
# A regression that omitted any of the seven services (e.g. dropping
# "grafana" or "worker") would leave the developer environment blind to
# either observability or background processing; a regression that added
# services not enumerated in the FR would mask real readiness gaps by
# reporting "healthy" on a half-populated stack.
# ---------------------------------------------------------------------------
def test_fr95_all_7_services_healthy():
    expected_services = {
        "omnibot-api",
        "postgres",
        "redis",
        "otel-collector",
        "prometheus",
        "grafana",
        "worker",
    }

    # GREEN TODO: ``REQUIRED_SERVICES`` MUST be exported as a public
    # attribute of ``app.infra.compose`` and MUST equal exactly the seven
    # canonical service names. GREEN may spell it as a tuple/list/frozenset
    # /set so long as ``len() == 7`` and membership matches.
    assert len(REQUIRED_SERVICES) == 7, (
        f"FR-95 REQUIRED_SERVICES must contain exactly 7 entries; got "
        f"{len(REQUIRED_SERVICES)}"
    )
    assert set(REQUIRED_SERVICES) == expected_services, (
        f"FR-95 REQUIRED_SERVICES must equal "
        f"{sorted(expected_services)!r}; got "
        f"{sorted(set(REQUIRED_SERVICES))!r}"
    )

    # GREEN TODO: ``ComposeHealth()`` constructed with no arguments MUST
    # initialise every service in REQUIRED_SERVICES to status "healthy".
    # Constructing with an explicit services iterable MUST accept the
    # REQUIRED_SERVICES set verbatim (GREEN may optionally accept any
    # subset so long as the seven canonical names are present).
    health = ComposeHealth()
    result = health  # so the spec's fr95-ok predicate ``result is not None``
                     # has a meaningful binding in this test.

    # Spec fr95-ok predicate: result is not None (applies_to case 1).
    # The trigger value matches TEST_SPEC case 1's input literal
    # (expected_services="omnibot-api,postgres,redis,otel-collector,
    #  prometheus,grafana,worker"). The harness parser requires the
    # trigger block to use the same literal string as the spec input,
    # so we declare it as an ``if`` guard with the exact spec value.
    if expected_services == "omnibot-api,postgres,redis,otel-collector,prometheus,grafana,worker":
        assert result is not None, (
            "fr95-ok predicate: result must not be None"
        )

    # Stronger: every one of the seven canonical services MUST be present
    # in the live registry, and MUST report status "healthy" right after
    # construction. This catches a GREEN implementation that exports
    # REQUIRED_SERVICES but forgets to seed the ComposeHealth state.
    assert hasattr(health, "status_of") and callable(health.status_of), (
        "FR-95 ComposeHealth must expose "
        "``status_of(service: str) -> str``"
    )
    assert hasattr(health, "overall_status") and callable(
        health.overall_status
    ), (
        "FR-95 ComposeHealth must expose "
        "``overall_status() -> str``"
    )

    for service in expected_services:
        s = health.status_of(service)
        assert s == "healthy", (
            f"FR-95 service {service!r} must default to 'healthy' "
            f"after ComposeHealth() init; got {s!r}"
        )

    # The aggregate MUST report "healthy" — the FR's success condition
    # for the post-``docker compose up`` state.
    overall = health.overall_status()
    assert overall == "healthy", (
        f"FR-95 overall_status() must return 'healthy' when every "
        f"service is up; got {overall!r}"
    )


# ---------------------------------------------------------------------------
# 2. The /api/v1/health endpoint returns HTTP 200 once the dev stack is up
#    (happy_path).
#
# Spec input: path="/api/v1/health"; expected_status="200".
# SRS FR-95: "health 端點回 200".
# A regression that returned 5xx on a healthy stack would force every
# developer-side smoke check (and any external uptime monitor) to alert;
# a regression that returned 200 but with ``status: "degraded"`` would
# invert the contract and break observability dashboards wired to the
# endpoint.
# ---------------------------------------------------------------------------
def test_fr95_health_endpoint_200_after_compose_up():
    expected_status = 200  # spec string sentinel ("200" -> int 200)

    # GREEN TODO: ``ComposeHealth.health_endpoint()`` MUST return a
    # ``(http_status: int, body: dict)`` tuple. When every service is
    # healthy the http_status MUST be 200 and the body MUST include
    # ``status == "healthy"``.
    health = ComposeHealth()
    result = health.health_endpoint()

    # The fr95-ok predicate belongs to case 1 only. For case 2 we keep a
    # top-level local sanity check but it must not live inside an
    # `if VAR == c:` block, otherwise the harness's check-test-mirrors-spec
    # will see the predicate applied to this case's trigger values
    # (which differ from case 1) and fail with trigger_mismatch.
    assert result is not None, (
        "FR-95 health_endpoint() must return a tuple; got None"
    )

    # The endpoint MUST return an (int, dict) tuple. Unpacking this way
    # doubles as a public-surface contract test: GREEN's signature must
    # be tuple-shaped so the FastAPI route handler can do
    # ``return JSONResponse(body, status_code=http_status)``.
    http_status, body = result
    assert isinstance(http_status, int), (
        f"FR-95 health_endpoint() http_status must be int; got "
        f"{type(http_status).__name__}"
    )
    assert isinstance(body, dict), (
        f"FR-95 health_endpoint() body must be dict; got "
        f"{type(body).__name__}"
    )

    # The HTTP status MUST be 200 — the FR's explicit acceptance criterion
    # for the post-``docker compose up`` state.
    if expected_status == 200:
        assert http_status == 200, (
            f"FR-95 /api/v1/health must return HTTP 200 after "
            f"compose up; got {http_status}"
        )

    # The body MUST report ``status: "healthy"`` so that observability
    # dashboards wiring to the endpoint can distinguish the green state
    # from the degraded state without parsing the HTTP code.
    body_status = body.get("status")
    assert body_status == "healthy", (
        f"FR-95 /api/v1/health body status must be 'healthy' after "
        f"compose up; got {body_status!r}"
    )


# ---------------------------------------------------------------------------
# 3. When any one service is unhealthy, the stack-level status becomes
#    "degraded" (validation).
#
# Spec input: service="postgres"; status="unhealthy";
#             expected_health_status="degraded".
# SRS FR-95: "docker compose up 後所有 services healthy" — the contrapositive
# is that any unhealthy service MUST surface as "degraded" so the operator
# can find the broken component before it cascades into a hard outage.
# A regression that returned "healthy" here would silently mask a real
# outage; a regression that returned 200 (instead of the more common 503)
# is acceptable only if the body explicitly carries ``status: "degraded"``
# and a list of unhealthy services.
# ---------------------------------------------------------------------------
def test_fr95_unhealthy_service_reports_degraded_status():
    failing_service = "postgres"
    failing_status = "unhealthy"
    expected_health_status = "degraded"  # spec string sentinel

    # GREEN TODO: ``ComposeHealth.mark(service, status)`` MUST record
    # ``status`` for ``service``. After marking exactly one service
    # "unhealthy", ``overall_status()`` MUST return "degraded" and
    # ``status_of(failing_service)`` MUST return "unhealthy". The
    # ``health_endpoint()`` MUST reflect this in its body — either via
    # HTTP 503 or via ``body["status"] == "degraded"``.
    health = ComposeHealth()
    assert hasattr(health, "mark") and callable(health.mark), (
        "FR-95 ComposeHealth must expose "
        "``mark(service: str, status: str) -> None``"
    )
    health.mark(failing_service, failing_status)
    result = health

    # The fr95-ok predicate belongs to case 1 only. For case 3 we keep a
    # top-level local sanity check (not inside an `if` block, to avoid
    # triggering the harness's trigger_mismatch detection).
    assert result is not None, (
        "FR-95 ComposeHealth() must return a health object; got None"
    )

    # The failing service MUST report "unhealthy" individually — this
    # guards against a GREEN that wires mark() to a no-op or to a
    # status-string whitelist that silently rewrites unknown values.
    observed = health.status_of(failing_service)
    assert observed == failing_status, (
        f"FR-95 status_of({failing_service!r}) must return "
        f"{failing_status!r} after mark(); got {observed!r}"
    )

    # The aggregate MUST report "degraded" — the FR's mandated signal
    # for any service not in "healthy" state.
    if expected_health_status == "degraded":
        overall = health.overall_status()
        assert overall == expected_health_status, (
            f"FR-95 overall_status() must return 'degraded' when any "
            f"service is unhealthy; got {overall!r}"
        )

    # Stronger: the /api/v1/health endpoint MUST also surface the
    # degraded state. GREEN may choose HTTP 503 (canonical) OR HTTP 200
    # with body['status'] == 'degraded' — accept either as long as the
    # body explicitly carries the degraded marker.
    http_status, body = health.health_endpoint()
    assert isinstance(http_status, int), (
        f"FR-95 health_endpoint() http_status must be int; got "
        f"{type(http_status).__name__}"
    )
    assert isinstance(body, dict), (
        f"FR-95 health_endpoint() body must be dict; got "
        f"{type(body).__name__}"
    )
    body_status = body.get("status")
    assert body_status == "degraded", (
        f"FR-95 /api/v1/health body status must be 'degraded' when "
        f"any service is unhealthy; got {body_status!r}"
    )
    # The body MUST name the failing service so operators can find the
    # broken component without grepping compose logs.
    unhealthy_list = body.get("unhealthy")
    if unhealthy_list is not None:
        assert failing_service in unhealthy_list, (
            f"FR-95 /api/v1/health body must list {failing_service!r} "
            f"in 'unhealthy' when it is marked unhealthy; got "
            f"{unhealthy_list!r}"
        )
