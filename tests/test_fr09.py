"""[FR-09] Tests for 統一回應格式 — ApiResponse[T] + PaginatedResponse[T].

Citations:
  SRS.md FR-09
  TEST_SPEC.md FR-09
"""


def test_fr09_api_response_schema_valid():
    """[FR-09] api_response_schema_valid."""
    from src.models.api_response import ApiResponse

    resp: ApiResponse[dict] = ApiResponse(success=True, data={})
    assert resp.success is True
    assert resp.data == {}
    assert resp.error is None


def test_fr09_paginated_response_has_next_field():
    """[FR-09] paginated_response_has_next_field."""
    from src.models.api_response import PaginatedResponse

    pr: PaginatedResponse[str] = PaginatedResponse(
        data=["a", "b"], total=50, page=1, limit=10, has_next=True
    )
    assert pr.has_next is True
    assert pr.total == 50
    assert pr.page == 1


def test_fr09_api_response_error_code_present_on_failure():
    """[FR-09] api_response_error_code_present_on_failure."""
    from src.models.api_response import ApiResponse

    resp: ApiResponse[None] = ApiResponse(
        success=False, error="bad input", error_code="VALIDATION_ERROR"
    )
    assert resp.success is False
    assert resp.error_code == "VALIDATION_ERROR"
