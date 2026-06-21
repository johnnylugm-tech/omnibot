"""TDD-RED: failing tests for FR-84 — Webhook API endpoints + error codes.

Spec source: 02-architecture/TEST_SPEC.md (FR-84)
SRS source : SRS.md FR-84 (Module 19: API 端點)

Acceptance criteria (from SRS FR-84):
    Webhook API 端點（6 個）：POST /api/v1/webhook/telegram, /line,
    /messenger(GET+POST), /whatsapp(GET+POST), POST /api/v1/web/guest-session,
    /web/message, /a2a/rpc；各端點錯誤碼規範（AUTH_INVALID_SIGNATURE /
    RATE_LIMIT_EXCEEDED / VALIDATION_ERROR / INTERNAL_ERROR / LLM_TIMEOUT /
    AUTH_TOKEN_EXPIRED / AUTHZ_INSUFFICIENT_ROLE）
    各端點存在且回傳正確 HTTP status；錯誤碼規範一致

The two TEST_SPEC cases (function names MUST match exactly):
    1. test_fr84_all_6_webhook_endpoints_exist
         Inputs: expected_paths="/telegram,/line,/messenger,/whatsapp,
                 /web/guest-session,/web/message,/a2a/rpc"
         Type  : happy_path (Q1)
    2. test_fr84_error_codes_consistent
         Inputs: expected_codes="AUTH_INVALID_SIGNATURE,RATE_LIMIT_EXCEEDED,
                 VALIDATION_ERROR,INTERNAL_ERROR,LLM_TIMEOUT,
                 AUTH_TOKEN_EXPIRED,AUTHZ_INSUFFICIENT_ROLE"
         Type  : validation (Q2)

Sub-assertion (per TEST_SPEC):
    fr84-ok: result is not None   (applies_to case 1)

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Source under test.
#
# Module ``app.api.webhook_routes`` does NOT exist yet — GREEN must create it
# and export at minimum:
#
#   - A FastAPI ``APIRouter`` instance named ``router`` that registers ALL 7
#     webhook endpoint paths (see expected_paths below).  Each route MUST
#     include the correct HTTP method(s):
#
#       POST   /api/v1/webhook/telegram
#       POST   /api/v1/webhook/line
#       GET    /api/v1/webhook/messenger
#       POST   /api/v1/webhook/messenger
#       GET    /api/v1/webhook/whatsapp
#       POST   /api/v1/webhook/whatsapp
#       POST   /api/v1/web/guest-session
#       POST   /api/v1/web/message
#       POST   /api/v1/a2a/rpc
#
#   - ``WEBHOOK_ERROR_CODES: tuple[str, ...]`` — the 7 standard error codes
#     returned by webhook endpoints, matching the spec exactly:
#       AUTH_INVALID_SIGNATURE, RATE_LIMIT_EXCEEDED, VALIDATION_ERROR,
#       INTERNAL_ERROR, LLM_TIMEOUT, AUTH_TOKEN_EXPIRED,
#       AUTHZ_INSUFFICIENT_ROLE
#
# The import below is unguarded: pytest MUST fail with Collection Error
# (Exit Code 2) because the module does not exist yet — that is the valid
# RED signal for this TDD step.
# ---------------------------------------------------------------------------
from app.api.webhook_routes import (
    WEBHOOK_ERROR_CODES,
)
from app.api.webhook_routes import (
    router as webhook_router,
)

# ===========================================================================
# Test isolation
#
# FR-84 tests assert route registration and error code constants — no real
# I/O.  If GREENʼs router construction triggers external imports (e.g. DB
# connections), GREEN should gate those behind a factory function so the
# module-level ``router`` remains side-effect-free for unit tests.
# ===========================================================================


# ---------------------------------------------------------------------------
# Expected constants — derived from TEST_SPEC.md FR-84 inputs
# ---------------------------------------------------------------------------

_EXPECTED_PATHS: set[str] = {
    "/api/v1/webhook/telegram",
    "/api/v1/webhook/line",
    "/api/v1/webhook/messenger",
    "/api/v1/webhook/whatsapp",
    "/api/v1/web/guest-session",
    "/api/v1/web/message",
    "/api/v1/a2a/rpc",
}

_EXPECTED_METHODS_BY_PATH: dict[str, set[str]] = {
    "/api/v1/webhook/telegram": {"POST"},
    "/api/v1/webhook/line": {"POST"},
    "/api/v1/webhook/messenger": {"GET", "POST"},
    "/api/v1/webhook/whatsapp": {"GET", "POST"},
    "/api/v1/web/guest-session": {"POST"},
    "/api/v1/web/message": {"POST"},
    "/api/v1/a2a/rpc": {"POST"},
}

_EXPECTED_ERROR_CODES: set[str] = {
    "AUTH_INVALID_SIGNATURE",
    "RATE_LIMIT_EXCEEDED",
    "VALIDATION_ERROR",
    "INTERNAL_ERROR",
    "LLM_TIMEOUT",
    "AUTH_TOKEN_EXPIRED",
    "AUTHZ_INSUFFICIENT_ROLE",
}


# ===========================================================================
# Test case 1 — all webhook endpoints registered
# ===========================================================================


def test_fr84_all_6_webhook_endpoints_exist() -> None:
    """[FR-84 | Q1 happy_path] All 7 webhook endpoint paths are registered
    with correct HTTP methods on the FastAPI router.

    Inputs (from TEST_SPEC):
        expected_paths = /telegram,/line,/messenger,/whatsapp,
                         /web/guest-session,/web/message,/a2a/rpc
    """
    # Collect registered paths and their HTTP methods from the router.
    registered: dict[str, set[str]] = {}
    for route in webhook_router.routes:
        path: str = getattr(route, "path", "")
        methods: set[str] = set(getattr(route, "methods", set()))
        if path in registered:
            registered[path] |= methods
        else:
            registered[path] = methods

    registered_paths: set[str] = set(registered.keys())

    # Assert: every expected path is registered.
    missing = _EXPECTED_PATHS - registered_paths
    assert not missing, (
        f"Missing webhook endpoints: {sorted(missing)}. "
        f"Registered: {sorted(registered_paths)}"
    )

    # Assert: no unexpected extra paths.
    extra = registered_paths - _EXPECTED_PATHS
    assert not extra, (
        f"Unexpected webhook endpoints: {sorted(extra)}. "
        f"Expected: {sorted(_EXPECTED_PATHS)}"
    )

    # Assert: HTTP methods match per endpoint.
    for path, expected_methods in _EXPECTED_METHODS_BY_PATH.items():
        actual_methods = registered.get(path, set())
        assert actual_methods == expected_methods, (
            f"Method mismatch for {path}: "
            f"expected={sorted(expected_methods)}, "
            f"got={sorted(actual_methods)}"
        )


# ===========================================================================
# Test case 2 — error codes consistent
# ===========================================================================


def test_fr84_error_codes_consistent() -> None:
    """[FR-84 | Q2 validation] All 7 standard error codes are defined
    and match the spec.

    Inputs (from TEST_SPEC):
        expected_codes = AUTH_INVALID_SIGNATURE,RATE_LIMIT_EXCEEDED,
                         VALIDATION_ERROR,INTERNAL_ERROR,LLM_TIMEOUT,
                         AUTH_TOKEN_EXPIRED,AUTHZ_INSUFFICIENT_ROLE
    """
    actual_codes: set[str] = set(WEBHOOK_ERROR_CODES)

    # Assert: all expected codes present.
    missing = _EXPECTED_ERROR_CODES - actual_codes
    assert not missing, (
        f"Missing error codes: {sorted(missing)}. "
        f"Found: {sorted(actual_codes)}"
    )

    # Assert: no unexpected extra codes.
    extra = actual_codes - _EXPECTED_ERROR_CODES
    assert not extra, (
        f"Unexpected error codes: {sorted(extra)}. "
        f"Expected: {sorted(_EXPECTED_ERROR_CODES)}"
    )
