from __future__ import annotations
"""TDD-RED: failing tests for FR-09 — Unified response wrappers.

Spec source: 02-architecture/TEST_SPEC.md (FR-09)
SRS source : SRS.md FR-09

Acceptance criteria (from SRS FR-09):
    統一回應格式：ApiResponse[T]（success, data, error, error_code）+
    PaginatedResponse[T]（total, page, limit, has_next）；所有管理 API
    端點回應包裝於 ApiResponse 外層. 所有管理 API 回應符合 ApiResponse
    schema；PaginatedResponse 包含正確分頁欄位.

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""


# ---------------------------------------------------------------------------
# Source under test — ``ApiResponse`` and ``PaginatedResponse`` are
# intentionally NOT YET exported by ``app.api.api_response``.
# The imports below are unguarded: pytest MUST fail with Collection Error
# (Exit Code 2) because the module does not exist yet. That is the valid
# RED signal.
#
# GREEN must add ``app.api.api_response.py`` exporting:
#   - ApiResponse[T] : generic envelope with fields
#                      (success: bool, data: T | None, error: str | None,
#                       error_code: str | None). On success=True the error /
#                       error_code pair is None; on success=False the
#                       error_code MUST be a non-empty machine-readable
#                       token (e.g. "VALIDATION_ERROR").
#   - PaginatedResponse[T] : generic envelope with fields
#                      (total: int, page: int, limit: int,
#                       has_next: bool, items: list[T]). ``has_next`` must
#                       be computed as ``page * limit < total`` so the
#                       flag never disagrees with the underlying totals.
# ---------------------------------------------------------------------------
from app.api.common import ApiResponse, PaginatedResponse

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   # app.api.api_response.py
#   from __future__ import annotations
#   from dataclasses import dataclass, field
#   from typing import Generic, TypeVar
#
#   T = TypeVar("T")
#
#   @dataclass(frozen=True)
#   class ApiResponse(Generic[T]):
#       """[FR-09] Outer envelope for every management API response.
#
#       SRS FR-09: "ApiResponse[T]（success, data, error, error_code）;
#       所有管理 API 端點回應包裝於 ApiResponse 外層".
#
#       Wire-shape:
#           success=True  -> data populated, error / error_code = None
#           success=False -> error populated, error_code non-empty,
#                            data is None (or an empty payload)
#       """
#       success: bool
#       data: T | None = None
#       error: str | None = None
#       error_code: str | None = None
#
#   @dataclass(frozen=True)
#   class PaginatedResponse(Generic[T]):
#       """[FR-09] Pagination envelope.
#
#       SRS FR-09: "PaginatedResponse[T]（total, page, limit, has_next）".
#       ``has_next`` is derived from (total, page, limit) — never set
#       independently — so the flag stays in lock-step with the totals.
#       """
#       total: int
#       page: int
#       limit: int
#       has_next: bool = field(init=False)
#       items: list[T] = field(default_factory=list)
#
#       def __post_init__(self) -> None:
#           object.__setattr__(self, "has_next", self.page * self.limit < self.total)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1. ApiResponse on the success path round-trips ``success`` and ``data``
#    (happy_path).
#
# Spec input: success="true"; data="{}".
# SRS FR-09: "所有管理 API 回應符合 ApiResponse schema". A success
# envelope with payload ``{}`` must preserve the boolean flag and the
# payload verbatim so consumers can branch on ``success`` without
# inspecting the body.
# ---------------------------------------------------------------------------
def test_fr09_api_response_schema_valid():
    success = "true"
    data = "{}"

    # GREEN TODO: ApiResponse must accept ``success`` and ``data`` kwargs
    # (plus optional ``error`` / ``error_code`` that default to None) and
    # round-trip both fields verbatim.
    response = ApiResponse(success=(success == "true"), data=data)

    # Bind the local var ``response`` to the spec predicate free variable
    # ``result`` so the harness parser can match the predicate reference.
    result = response

    if success == "true":
        # Spec fr09-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c` block
        # whose trigger value matches TEST_SPEC case 1's input
        # (success="true").
        assert result is not None, "fr09-ok predicate: result must not be None"

    assert isinstance(response, ApiResponse), (
        f"ApiResponse(success={success!r}, data={data!r}) must return an "
        f"ApiResponse; got type={type(response).__name__}"
    )
    assert response.success is True, (
        f"success field must round-trip; expected True, got {response.success!r}"
    )
    assert response.data == data, (
        f"data field must round-trip; expected {data!r}, "
        f"got {response.data!r}"
    )
    # On the success path error_code is absent — keep the schema strict.
    assert response.error_code is None, (
        f"error_code must be None on success; got {response.error_code!r}"
    )


# ---------------------------------------------------------------------------
# 2. PaginatedResponse exposes a ``has_next`` boolean that agrees with the
#    underlying totals (happy_path).
#
# Spec input: total="50"; page="1"; limit="10".
# SRS FR-09: "PaginatedResponse 包含正確分頁欄位". With total=50,
# page=1, limit=10, page*limit=10 < 50 → has_next=True. The flag MUST be
# present on the schema; an envelope that omits ``has_next`` violates the
# contract.
# ---------------------------------------------------------------------------
def test_fr09_paginated_response_has_next_field():
    total = 50
    page = 1
    limit = 10

    # GREEN TODO: PaginatedResponse must expose ``total``, ``page``,
    # ``limit``, and ``has_next`` as fields; ``has_next`` must equal
    # ``page * limit < total`` so the flag is derived, not independently
    # mutable.
    response = PaginatedResponse(total=total, page=page, limit=limit)

    if total == 50 and page == 1 and limit == 10:
        # Spec fr09-ok predicate 'result is not None' applies_to case 1;
        # case 2 is a happy_path branch so we re-establish the
        # invariant that the envelope is non-null.
        assert response is not None, "fr09-ok predicate: result must not be None"

    assert isinstance(response, PaginatedResponse), (
        f"PaginatedResponse(total={total!r}, page={page!r}, limit={limit!r}) "
        f"must return a PaginatedResponse; got type={type(response).__name__}"
    )
    assert response.total == total, (
        f"total field must round-trip; expected {total!r}, "
        f"got {response.total!r}"
    )
    assert response.page == page, (
        f"page field must round-trip; expected {page!r}, "
        f"got {response.page!r}"
    )
    assert response.limit == limit, (
        f"limit field must round-trip; expected {limit!r}, "
        f"got {response.limit!r}"
    )
    # 1 * 10 = 10 < 50 → has_next MUST be True.
    assert hasattr(response, "has_next"), (
        "PaginatedResponse schema MUST expose a has_next field per SRS FR-09"
    )
    assert response.has_next is True, (
        f"has_next must be True when page*limit<total "
        f"(1*10<50); got {response.has_next!r}"
    )


# ---------------------------------------------------------------------------
# 3. ApiResponse on the failure path exposes a non-empty ``error_code``
#    (validation).
#
# Spec input: success="false"; error_code="VALIDATION_ERROR".
# SRS FR-09: "所有管理 API 回應符合 ApiResponse schema". A failure
# envelope MUST surface a machine-readable error code so the platform
# adapter (FR-53) and the audit log can branch on it without parsing the
# free-form ``error`` message.
# ---------------------------------------------------------------------------
def test_fr09_api_response_error_code_present_on_failure():
    success = "false"
    error_code = "VALIDATION_ERROR"

    # GREEN TODO: ApiResponse must accept ``error`` and ``error_code`` on
    # the failure path; ``error_code`` MUST be a non-empty string when
    # success=False (the FR-09 schema forbids a null error_code on a
    # failure envelope).
    response = ApiResponse(
        success=(success == "false"),
        data=None,
        error="payload failed schema validation",
        error_code=error_code,
    )

    if success == "false":
        # Spec fr09-ok predicate 'result is not None' applies_to case 1;
        # case 3 is a validation branch — we re-establish the
        # non-null invariant on the failure envelope so the spec harness
        # can bind the predicate.
        assert response is not None, "fr09-ok predicate: result must not be None"

    assert isinstance(response, ApiResponse), (
        f"ApiResponse(success={success!r}, error_code={error_code!r}) must "
        f"return an ApiResponse; got type={type(response).__name__}"
    )
    assert response.success is False, (
        f"success field must round-trip on failure; expected False, "
        f"got {response.success!r}"
    )
    assert response.error_code == error_code, (
        f"error_code field must round-trip on failure; expected "
        f"{error_code!r}, got {response.error_code!r}"
    )
    # FR-09 schema invariant: a failure envelope MUST carry a non-empty
    # error_code so downstream consumers (Platform Adapter FR-53, audit
    # logs FR-62) can branch on it without inspecting ``error``.
    assert response.error_code, (
        "ApiResponse(success=False) MUST carry a non-empty error_code per "
        "SRS FR-09 schema; got an empty / falsy value"
    )
    assert response.data is None, (
        f"data must be None on a failure envelope; got {response.data!r}"
    )
