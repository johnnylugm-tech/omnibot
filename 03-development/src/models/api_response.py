"""[FR-09] ApiResponse[T] and PaginatedResponse[T] — unified API envelope.

Citations:
  SRS.md FR-09: 統一回應格式：ApiResponse[T]（success, data, error, error_code）+
    PaginatedResponse[T]（total, page, limit, has_next）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass
class ApiResponse(Generic[T]):
    """[FR-09] Generic API envelope.

    Citations:
      SRS.md FR-09
    """

    success: bool
    data: Optional[T] = None
    error: Optional[str] = None
    error_code: Optional[str] = None


@dataclass
class PaginatedResponse(Generic[T]):
    """[FR-09] Paginated API envelope.

    Citations:
      SRS.md FR-09
    """

    data: list[T]
    total: int
    page: int
    limit: int
    has_next: bool
