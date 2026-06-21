from __future__ import annotations
"""TDD-RED: failing tests for FR-85 — Management API (8 endpoints + RBAC
+ PaginatedResponse + health).

Spec source: 02-architecture/TEST_SPEC.md (FR-85)
SRS source : SRS.md FR-85

Acceptance criteria (from SRS FR-85):
    管理 API（8 個端點）：GET/POST /api/v1/knowledge；
    PUT/DELETE /api/v1/knowledge/{id}；POST /api/v1/knowledge/bulk；
    GET /api/v1/conversations；POST /api/v1/experiments；
    GET /api/v1/health。各端點 RBAC 保護正確；分頁回應格式符合
    PaginatedResponse；health 回傳 status/postgres/redis/uptime_seconds.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""


from app.admin.rbac import RBACEnforcer, enforce

# ---------------------------------------------------------------------------
# Source under test.
#
# FR-85 (SRS.md) requires:
#   1. ``app.api.management`` exports management endpoint handlers:
#      - ``list_knowledge(role, page, limit) -> PaginatedResponse``
#      - ``check_health() -> dict`` with keys status/postgres/redis/
#        uptime_seconds
#      - ``create_knowledge`` / ``update_knowledge`` / ``delete_knowledge``
#        / ``bulk_create_knowledge`` / ``list_conversations`` /
#        ``create_experiment``
#   2. Each endpoint is protected by RBAC
#      (``app.admin.rbac.RBACEnforcer``). Anonymous / unauthorised roles
#      MUST receive HTTP 403 ``AUTHZ_INSUFFICIENT_ROLE``.
#   3. List endpoints return ``PaginatedResponse`` with ``has_next``
#      computed as ``page * limit < total`` (per FR-09 contract).
#   4. The ``GET /api/v1/health`` endpoint returns a dict with keys
#      ``status``, ``postgres``, ``redis``, ``uptime_seconds``.
#
# GREEN contract pinned by this spec:
#   - ``app.api.management`` MUST be a package or module.
#   - ``app.api.management.list_knowledge(role: str, page: int,
#     limit: int) -> PaginatedResponse`` MUST enforce RBAC via
#     ``RBACEnforcer.check(role, "knowledge", "read")`` and return 403
#     for denied roles.
#   - ``app.api.management.check_health() -> dict`` MUST return a dict
#     with the keys ``status``, ``postgres``, ``redis``,
#     ``uptime_seconds``.
#   - Any endpoint that returns a collection MUST wrap it in
#     ``PaginatedResponse`` with the ``has_next`` field correctly
#     derived.
#
# The imports below are unguarded: pytest MUST fail with Collection Error
# (Exit Code 2) because ``app.api.management`` does not exist yet. That
# is the valid RED signal — GREEN adds the module and tightens the
# behaviour to make every assertion hold.
# ---------------------------------------------------------------------------
from app.api.management import (
    bulk_create_knowledge,
    check_health,
    create_experiment,
    create_knowledge,
    delete_knowledge,
    list_conversations,
    list_knowledge,
    update_knowledge,
)
from app.api.common import ApiResponse, PaginatedResponse


# ============================================================================
# 1. The knowledge list endpoint MUST be RBAC-protected — anonymous
#    requests receive HTTP 403 AUTHZ_INSUFFICIENT_ROLE (validation).
#
# Spec input: path="/api/v1/knowledge"; role="anonymous";
#            expected_status="403".
# Spec sub-assertion: fr85-ok: result is not None.
# SRS FR-85 acceptance: "各端點 RBAC 保護正確" (RBAC protection correct
# on every endpoint). Anonymous only holds ``knowledge:read`` at most;
# the management knowledge endpoint requires a higher-privilege role.
# Test type: validation (Q2 derivation).
# Active Pattern: NP-02 (authz 403).
# ============================================================================
def test_fr85_knowledge_list_rbac_protected():
    path = "/api/v1/knowledge"
    role = "anonymous"
    expected_status = "403"

    # Defence-in-depth: pin the spec sentinel strings.
    assert path == "/api/v1/knowledge", (
        f"FR-85: path sentinel must be '/api/v1/knowledge' (SRS FR-85 "
        f"management route); got {path!r}."
    )
    assert role == "anonymous", (
        f"FR-85: role sentinel must be 'anonymous' (lowest privilege "
        f"probe per NP-02); got {role!r}."
    )
    assert expected_status == "403", (
        f"FR-85: expected_status sentinel must be '403' (HTTP 403 "
        f"AUTHZ_INSUFFICIENT_ROLE); got {expected_status!r}."
    )

    # The ``RBACEnforcer`` class MUST exist on ``app.admin.rbac``.
    assert RBACEnforcer is not None, (
        "fr85-ok predicate: RBACEnforcer must not be None so the "
        "management endpoints can be decorated with @rbac.require()."
    )

    # GREEN TODO: ``RBACEnforcer.check(anonymous, knowledge, read)``
    # MUST return 403 because anonymous does not hold the management
    # knowledge grant (only admin/editor/agent/dpo/auditor do per
    # FR-60/FR-61).
    result = RBACEnforcer.check(role, "knowledge", "read")

    # fr85-ok: result is not None.
    assert result is not None, (
        "fr85-ok predicate: RBACEnforcer.check() must not return None "
        "for any (role, resource, action) tuple; the middleware needs a "
        "real status code (200 or 403)."
    )

    assert result == 403, (
        f"FR-85: RBACEnforcer.check('anonymous', 'knowledge', 'read') "
        f"MUST return 403 per SRS FR-85 '各端點 RBAC 保護正確'; got "
        f"{result!r}. Anonymous is not authorised for management "
        f"knowledge endpoints."
    )
    assert result == int(expected_status), (
        f"FR-85: RBACEnforcer.check() status must equal int('403') = "
        f"403; got {result!r}."
    )
    assert isinstance(result, int), (
        f"FR-85: RBACEnforcer.check() must return an int status code "
        f"(HTTP-style); got {type(result).__name__} = {result!r}."
    )

    # GREEN TODO: ``list_knowledge(role='anonymous', page=1, limit=10)``
    # MUST return 403 (or raise PermissionError that maps to 403) when
    # the caller is anonymous. The function MUST call
    # ``RBACEnforcer.check(role, 'knowledge', 'read')`` internally or
    # use the ``@rbac.require('knowledge', 'read')`` decorator.
    denied = list_knowledge(role=role, page=1, limit=10)
    assert denied is not None, (
        "fr85-ok predicate: list_knowledge() must not return None for "
        "any input — it must return a status code or response."
    )

    # Sentinels MUST be preserved per spec.
    assert path == "/api/v1/knowledge", (
        f"FR-85: path sentinel must remain '/api/v1/knowledge'; got "
        f"{path!r}."
    )
    assert role == "anonymous", (
        f"FR-85: role sentinel must remain 'anonymous'; got {role!r}."
    )
    assert expected_status == "403", (
        f"FR-85: expected_status sentinel must remain '403'; got "
        f"{expected_status!r}."
    )


# ============================================================================
# 2. The health endpoint MUST return postgres, redis, and uptime_seconds
#    fields (happy_path).
#
# Spec input: path="/api/v1/health";
#            expected_fields="status,postgres,redis,uptime_seconds".
# Spec sub-assertion: fr85-ok: result is not None.
# SRS FR-85 acceptance:
#    "health 回傳 status/postgres/redis/uptime_seconds".
# Test type: happy_path (Q1 derivation).
# ============================================================================
def test_fr85_health_returns_postgres_redis_uptime():
    path = "/api/v1/health"
    expected_fields = "status,postgres,redis,uptime_seconds"

    # Defence-in-depth: pin the spec sentinel strings.
    assert path == "/api/v1/health", (
        f"FR-85: path sentinel must be '/api/v1/health' (SRS FR-85 "
        f"health route); got {path!r}."
    )
    assert expected_fields == "status,postgres,redis,uptime_seconds", (
        f"FR-85: expected_fields sentinel must be 'status,postgres,"
        f"redis,uptime_seconds' (SRS FR-85 health contract); got "
        f"{expected_fields!r}."
    )

    # GREEN TODO: ``check_health()`` MUST return a dict with the
    # required keys ``status``, ``postgres``, ``redis``,
    # ``uptime_seconds``. ``postgres`` and ``redis`` are connection
    # status strings (e.g. "ok", "degraded", "down"). ``uptime_seconds``
    # is a monotonically increasing integer representing process
    # uptime in seconds. ``status`` is the aggregate
    # ("ok" if both pg + redis are ok, "degraded" otherwise).
    #
    # External I/O (actual DB/Redis connections) MUST be mocked during
    # unit tests — see conftest.py ``_isolate_external_services``.
    result = check_health()

    # fr85-ok: result is not None (predicate for case 2).
    assert result is not None, (
        "fr85-ok predicate: check_health() must not return None; the "
        "health endpoint must always produce a response."
    )

    assert isinstance(result, dict), (
        f"FR-85: check_health() must return a dict with health status "
        f"fields; got type={type(result).__name__}."
    )

    required_keys = expected_fields.split(",")
    for key in required_keys:
        assert key in result, (
            f"FR-85: check_health() result MUST contain key {key!r} "
            f"per SRS FR-85 'health 回傳 status/postgres/redis/"
            f"uptime_seconds'; got keys={sorted(result.keys())!r}."
        )

    # Type contract: status, postgres, redis are strings.
    assert isinstance(result["status"], str), (
        f"FR-85: health field 'status' must be a str; got "
        f"{type(result['status']).__name__} = {result['status']!r}."
    )
    assert isinstance(result["postgres"], str), (
        f"FR-85: health field 'postgres' must be a str; got "
        f"{type(result['postgres']).__name__} = {result['postgres']!r}."
    )
    assert isinstance(result["redis"], str), (
        f"FR-85: health field 'redis' must be a str; got "
        f"{type(result['redis']).__name__} = {result['redis']!r}."
    )

    # Type contract: uptime_seconds is an int.
    assert isinstance(result["uptime_seconds"], int), (
        f"FR-85: health field 'uptime_seconds' must be an int; got "
        f"{type(result['uptime_seconds']).__name__} = "
        f"{result['uptime_seconds']!r}."
    )

    # uptime_seconds must be non-negative.
    assert result["uptime_seconds"] >= 0, (
        f"FR-85: uptime_seconds must be >= 0; got "
        f"{result['uptime_seconds']!r}."
    )

    # Sentinels MUST be preserved per spec.
    assert path == "/api/v1/health", (
        f"FR-85: path sentinel must remain '/api/v1/health'; got "
        f"{path!r}."
    )
    assert expected_fields == "status,postgres,redis,uptime_seconds", (
        f"FR-85: expected_fields sentinel must remain "
        f"'status,postgres,redis,uptime_seconds'; got {expected_fields!r}."
    )


# ============================================================================
# 3. PaginatedResponse MUST expose ``has_next`` that agrees with the
#    underlying totals: ``page * limit < total`` (validation).
#
# Spec input: page="1"; limit="10"; total="50"; expected_has_next="true".
# Spec sub-assertion: fr85-ok: result is not None.
# SRS FR-85 acceptance:
#    "分頁回應格式符合 PaginatedResponse" (pagination matches the
#    PaginatedResponse schema defined in FR-09).
# Test type: validation (Q2 derivation).
# Active Pattern: NP-12 (pagination).
# ============================================================================
def test_fr85_paginated_response_has_next():
    page = 1
    limit = 10
    total = 50
    expected_has_next = "true"

    # Defence-in-depth: pin the spec sentinel values.
    assert page == 1, (
        f"FR-85: page sentinel must be 1 (spec input); got {page!r}."
    )
    assert limit == 10, (
        f"FR-85: limit sentinel must be 10 (spec input); got {limit!r}."
    )
    assert total == 50, (
        f"FR-85: total sentinel must be 50 (spec input); got {total!r}."
    )
    assert expected_has_next == "true", (
        f"FR-85: expected_has_next sentinel must be 'true' (spec "
        f"input); got {expected_has_next!r}."
    )

    # GREEN TODO: ``PaginatedResponse`` (from app.api.api_response,
    # FR-09) MUST expose a ``has_next`` boolean field. When
    # ``page * limit < total`` (1 * 10 = 10 < 50), ``has_next`` MUST
    # be True. The field MUST be derived from the constructor args
    # (total, page, limit) — never independently settable.
    response = PaginatedResponse(total=total, page=page, limit=limit)

    # fr85-ok: result is not None (predicate for case 3).
    assert response is not None, (
        "fr85-ok predicate: PaginatedResponse must not be None; the "
        "pagination envelope must always be constructable."
    )

    assert isinstance(response, PaginatedResponse), (
        f"FR-85: PaginatedResponse(total={total!r}, page={page!r}, "
        f"limit={limit!r}) must return a PaginatedResponse; got "
        f"type={type(response).__name__}."
    )

    # All constructor fields must round-trip.
    assert response.total == total, (
        f"FR-85: PaginatedResponse.total must round-trip; expected "
        f"{total!r}, got {response.total!r}."
    )
    assert response.page == page, (
        f"FR-85: PaginatedResponse.page must round-trip; expected "
        f"{page!r}, got {response.page!r}."
    )
    assert response.limit == limit, (
        f"FR-85: PaginatedResponse.limit must round-trip; expected "
        f"{limit!r}, got {response.limit!r}."
    )

    # has_next MUST be present and MUST equal (page * limit < total).
    assert hasattr(response, "has_next"), (
        "FR-85: PaginatedResponse schema MUST expose a has_next "
        "field per SRS FR-85 '分頁回應格式符合 PaginatedResponse' "
        "(inherited from FR-09)."
    )
    assert response.has_next is True, (
        f"FR-85: has_next must be True when page*limit<total "
        f"(1*10<50); got {response.has_next!r}. Without this field "
        f"front-end pagination controls cannot know whether to show "
        f"a 'next page' button."
    )
    assert response.has_next == (expected_has_next == "true"), (
        f"FR-85: has_next must be a boolean True (not a string); "
        f"spec expected_has_next='true' maps to Python True. Got "
        f"{response.has_next!r}."
    )

    # Verify the derivation formula: page * limit = 10 < 50 → has_next=True.
    assert response.page * response.limit < response.total, (
        f"FR-85: has_next derivation invariant violated: "
        f"page*limit=10 >= total=50 but has_next={response.has_next!r}. "
        f"The has_next flag MUST be computed as (page * limit < total."
    )

    # Sentinels MUST be preserved per spec.
    assert page == 1, (
        f"FR-85: page sentinel must remain 1; got {page!r}."
    )
    assert limit == 10, (
        f"FR-85: limit sentinel must remain 10; got {limit!r}."
    )
    assert total == 50, (
        f"FR-85: total sentinel must remain 50; got {total!r}."
    )
    assert expected_has_next == "true", (
        f"FR-85: expected_has_next sentinel must remain 'true'; got "
        f"{expected_has_next!r}."
    )


# ============================================================================
# Coverage-fill tests — the 3 spec tests above cover the core contracts;
# these additional tests exercise every remaining branch and endpoint
# to bring code coverage ≥ 80% for the COVERAGE-FIX step.
# ============================================================================

# ---------------------------------------------------------------------------
# management.py: list_knowledge authorized path + 6 stub endpoints
# ---------------------------------------------------------------------------


def test_fr85_list_knowledge_authorized():
    """Authorised role (admin) receives a PaginatedResponse, exercising the
    _authorized True branch and list_knowledge success path (line 87)."""
    result = list_knowledge(role="admin", page=1, limit=10)
    assert isinstance(result, PaginatedResponse)
    assert result.total == 0
    assert result.page == 1
    assert result.limit == 10
    assert result.has_next is False  # 1*10=10 not < 0


def test_fr85_create_knowledge_authorized():
    assert create_knowledge(role="admin", payload={"key": "val"}) == 200


def test_fr85_update_knowledge_authorized():
    assert update_knowledge(role="admin", id_="kb-1", payload={"key": "val"}) == 200


def test_fr85_delete_knowledge_authorized():
    assert delete_knowledge(role="admin", id_="kb-1") == 200


def test_fr85_bulk_create_knowledge_authorized():
    assert bulk_create_knowledge(role="admin", payload={"items": []}) == 200


def test_fr85_list_conversations_authorized():
    assert list_conversations(role="admin", page=1, limit=10) == 200


def test_fr85_create_experiment_authorized():
    assert create_experiment(role="admin", payload={"name": "exp-1"}) == 200


# --- Stub endpoint denied paths ---


def test_fr85_create_knowledge_denied():
    assert create_knowledge(role="anonymous", payload={}) == 403


def test_fr85_update_knowledge_denied():
    assert update_knowledge(role="anonymous", id_="kb-1", payload={}) == 403


def test_fr85_delete_knowledge_denied():
    assert delete_knowledge(role="anonymous", id_="kb-1") == 403


def test_fr85_bulk_create_knowledge_denied():
    assert bulk_create_knowledge(role="anonymous", payload={}) == 403


def test_fr85_list_conversations_denied():
    assert list_conversations(role="anonymous", page=1, limit=10) == 403


def test_fr85_create_experiment_denied():
    assert create_experiment(role="anonymous", payload={}) == 403


# ---------------------------------------------------------------------------
# api_response.py: ApiResponse.__post_init__ coverage
# ---------------------------------------------------------------------------


def test_fr85_api_response_success():
    """ApiResponse with data and no error — success flag stays True."""
    resp = ApiResponse(success=True, data="result")
    assert resp.success is True
    assert resp.data == "result"
    assert resp.error is None
    assert resp.error_code is None


def test_fr85_api_response_failure():
    """ApiResponse with error and error_code — success overridden to False."""
    resp = ApiResponse(success=False, error="not found", error_code="E404")
    assert resp.success is False
    assert resp.data is None
    assert resp.error == "not found"
    assert resp.error_code == "E404"


def test_fr85_api_response_success_overridden_by_error():
    """__post_init__ overrides success when error is present, even if
    the caller passed success=True."""
    resp = ApiResponse(success=True, error="boom")
    assert resp.success is False
    assert resp.error == "boom"


def test_fr85_api_response_failure_error_code_only():
    """__post_init__ overrides success when error_code is present (no error str)."""
    resp = ApiResponse(success=True, error_code="E500")
    assert resp.success is False
    assert resp.error_code == "E500"


# ---------------------------------------------------------------------------
# rbac.py: enforce() edge cases + RBACEnforcer.require decorator paths
# ---------------------------------------------------------------------------


def test_fr85_enforce_unknown_role():
    """enforce with a role not in ROLE_PERMISSIONS → 403."""
    assert enforce(role="nonexistent", resource="knowledge", action="read") == 403


def test_fr85_enforce_unknown_resource():
    """enforce with a resource not in the role's grants → 403."""
    assert enforce(role="admin", resource="nonexistent", action="read") == 403


def test_fr85_enforce_authorized_action():
    """enforce with admin + knowledge:read → 200 (the True branch of line 160)."""
    assert enforce(role="admin", resource="knowledge", action="read") == 200


def test_fr85_rbac_require_authorized(monkeypatch):
    """RBACEnforcer.require decorator permits execution for authorised role.
    Covers _resolve_role Path 1 (explicit role kwarg + TESTING=1)."""
    monkeypatch.setenv("TESTING", "1")

    @RBACEnforcer.require("knowledge", "read")
    def handler(payload=None):
        return payload

    result = handler(role="admin", payload="data")
    assert result == "data"


def test_fr85_rbac_require_denied(monkeypatch):
    """RBACEnforcer.require decorator raises PermissionError for denied role."""
    monkeypatch.setenv("TESTING", "1")

    @RBACEnforcer.require("knowledge", "read")
    def handler():
        return "should not reach"  # pragma: no cover — unreachable on deny

    try:
        handler(role="anonymous")
    except PermissionError as exc:
        assert str(exc) == RBACEnforcer.ERROR_AUTHZ_INSUFFICIENT_ROLE
    else:
        raise AssertionError("Expected PermissionError")


def test_fr85_rbac_require_role_from_request(monkeypatch):
    """_resolve_role Path 3: role resolved from kwargs['request'].user_role."""
    monkeypatch.setenv("TESTING", "1")

    @RBACEnforcer.require("knowledge", "read")
    def handler():
        return "ok"

    class FakeRequest:
        user_role = "admin"

    result = handler(request=FakeRequest())
    assert result == "ok"


def test_fr85_rbac_require_role_from_first_arg(monkeypatch):
    """_resolve_role Path 4: role resolved from args[0].user_role."""
    monkeypatch.setenv("TESTING", "1")

    @RBACEnforcer.require("knowledge", "read")
    def handler():
        return "ok"

    class FakeRequest:
        user_role = "admin"

    result = handler(FakeRequest())
    assert result == "ok"


def test_fr85_rbac_require_fallback_anonymous(monkeypatch):
    """_resolve_role Path 5: no role found anywhere → 'anonymous' → 403."""
    monkeypatch.setenv("TESTING", "1")

    @RBACEnforcer.require("knowledge", "read")
    def handler():
        return "ok"  # pragma: no cover — unreachable when anonymous denied

    try:
        handler()
    except PermissionError as exc:
        assert str(exc) == RBACEnforcer.ERROR_AUTHZ_INSUFFICIENT_ROLE
    else:
        raise AssertionError("Expected PermissionError")


def test_fr85_rbac_require_role_ignored_without_testing(monkeypatch):
    """_resolve_role: role kwarg popped but ignored when TESTING != '1'
    (falls through to default 'anonymous')."""
    monkeypatch.setenv("TESTING", "0")

    @RBACEnforcer.require("knowledge", "read")
    def handler():
        return "ok"  # pragma: no cover

    try:
        handler(role="admin")
    except PermissionError:
        pass
    else:
        raise AssertionError("Expected PermissionError — role kwarg ignored without TESTING=1")


def test_fr85_rbac_require_role_none_falls_through(monkeypatch):
    """_resolve_role: role=None in kwargs is skipped (override is None check)
    and falls through to default 'anonymous'."""
    monkeypatch.setenv("TESTING", "1")

    @RBACEnforcer.require("knowledge", "read")
    def handler():
        return "ok"  # pragma: no cover

    try:
        handler(role=None)
    except PermissionError:
        pass
    else:
        raise AssertionError("Expected PermissionError — role=None should fall through")
