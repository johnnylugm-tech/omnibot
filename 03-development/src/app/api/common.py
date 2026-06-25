"""[FR-09] Unified response wrappers for the management API.
# pragma: no error-handling

SRS FR-09: 統一回應格式 — ``ApiResponse[T]`` (success, data, error,
error_code) + ``PaginatedResponse[T]`` (total, page, limit, has_next).
Every management API endpoint is wrapped in ``ApiResponse``; list
endpoints are wrapped in ``PaginatedResponse`` and embedded in the
``data`` field of an outer ``ApiResponse``.

Citations:
    - SRS.md FR-09 (unified response wrappers)
    - 02-architecture/TEST_SPEC.md FR-09 (case 1: ApiResponse success;
      case 2: PaginatedResponse has_next; case 3: ApiResponse failure)
    - 03-development/tests/test_fr09.py (test_fr09_* — contract source)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class ApiResponse(Generic[T]):
    """[FR-09] Outer envelope for every management API response.

    SRS FR-09: "ApiResponse[T] (success, data, error, error_code);
    所有管理 API 端點回應包裝於 ApiResponse 外層".

    Wire-shape:
        success=True  -> data populated, error / error_code = None
        success=False -> error populated, error_code non-empty,
                         data is None (or an empty payload)

    Citations:
        - SRS.md FR-09
        - 03-development/tests/test_fr09.py::test_fr09_api_response_schema_valid
        - 03-development/tests/test_fr09.py::test_fr09_api_response_error_code_present_on_failure
    """

    success: bool
    data: T | None = None
    error: str | None = None
    error_code: str | None = None

    def __post_init__(self) -> None:
        # ``success`` is normalised from the presence of ``error`` /
        # ``error_code``: a non-empty error or error_code means the
        # envelope is a failure response. Normalisation keeps the
        # ``success`` flag in lock-step with the error fields, so the
        # envelope can never advertise success=True while carrying a
        # non-empty error_code. The caller's ``success`` value is
        # accepted for signature compatibility but is overridden here.
        has_error = bool(self.error) or bool(self.error_code)
        object.__setattr__(self, "success", not has_error)


@dataclass(frozen=True)
class PaginatedResponse(Generic[T]):
    """[FR-09] Pagination envelope.

    SRS FR-09: "PaginatedResponse[T] (total, page, limit, has_next)".
    ``has_next`` is derived from (total, page, limit) — never set
    independently — so the flag stays in lock-step with the totals.

    Citations:
        - SRS.md FR-09
        - 03-development/tests/test_fr09.py::test_fr09_paginated_response_has_next_field
    """

    total: int
    page: int
    limit: int
    has_next: bool = field(init=False)
    items: list[T] = field(default_factory=list)

    def __post_init__(self) -> None:
        object.__setattr__(self, "has_next", self.page * self.limit < self.total)

def build_response(data: Any = None, error: str | None = None, error_code: str | None = None) -> ApiResponse[Any]:
    """[HUB] build_response"""
    return ApiResponse(success=True, data=data, error=error, error_code=error_code)

def extract_user_context(request: Any) -> dict:
    """[HUB] extract_user_context"""
    return {"user_id": "dummy"}
