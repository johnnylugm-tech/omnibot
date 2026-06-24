"""[FR-86] Unit tests for ``app.api.auth`` JWT verifier + route handlers.

Covers the previously-uncovered paths inside ``auth.py``:

    * ``get_current_user_role`` — every branch of the JWT verifier:
      empty token, malformed token (wrong segment count), bad
      signature, expired payload, valid admin claim, valid customer
      claim, and the catch-all ``except Exception`` branch.

    * ``_login_route`` (POST /api/v1/auth/login) — exercised via
      FastAPI's ``TestClient``: the rate-limit (429) branch, the
      successful login path, and the 401 path.

    * ``_assign_role_route`` (POST /api/v1/users/{id}/roles) — the
      200 / 403 outcome based on the caller's JWT-derived role.

The tests share the ``_make_jwt`` private helper from ``auth.py`` so
they exercise the production token format end-to-end.
"""

from __future__ import annotations

import json
import time

import pytest
from app.api import auth as auth_module
from app.api.auth import (
    _login_route,
    _make_jwt,
    get_current_user_role,
)
from app.api.auth import (
    router as auth_router,
)
from fastapi import FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _credentials(token: str) -> HTTPAuthorizationCredentials:
    """Build the HTTPAuthorizationCredentials object the verifier expects."""
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.fixture(autouse=True)
def _jwt_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the JWT env so tests are hermetic across runners.

    ``autouse=True`` means every test in this module gets a fresh
    env without needing to declare it as a parameter (which would
    otherwise trip Pyright's unused-parameter lint).
    """
    monkeypatch.setenv("OMNIBOT_JWT_SECRET", "test-jwt-secret-for-auth-coverage")
    monkeypatch.setenv("OMNIBOT_ADMIN_USER", "admin")


def _build_app_with_login_route() -> FastAPI:
    """Mount the auth router on a fresh app — router has prefix ``/auth``."""
    app = FastAPI()
    app.include_router(auth_router)
    return app


# ===========================================================================
# get_current_user_role — every branch of the JWT verifier.
# ===========================================================================


def test_get_current_user_role_empty_token_returns_anonymous() -> None:
    """Empty token string MUST resolve to ``"anonymous"``."""
    assert get_current_user_role(_credentials("")) == "anonymous"


def test_get_current_user_role_malformed_token_returns_anonymous() -> None:
    """A token that doesn't have exactly 3 dot-separated segments is rejected."""
    # Two segments (missing signature).
    assert get_current_user_role(_credentials("abc.def")) == "anonymous"
    # Four segments (over-long).
    assert get_current_user_role(_credentials("a.b.c.d")) == "anonymous"
    # No dots at all.
    assert get_current_user_role(_credentials("not-a-jwt")) == "anonymous"


def test_get_current_user_role_bad_signature_returns_anonymous() -> None:
    """A token whose signature doesn't match the verifier's HMAC MUST be rejected."""
    good_token = _make_jwt("admin")
    header_b64, payload_b64, _good_sig = good_token.split(".")
    tampered = f"{header_b64}.{payload_b64}.{_good_sig[:-2]}aa"

    assert get_current_user_role(_credentials(tampered)) == "anonymous"


def test_get_current_user_role_expired_token_returns_anonymous() -> None:
    """An expired JWT MUST resolve to ``"anonymous"`` (FR-86 NP-01 active)."""
    secret = b"test-jwt-secret-for-auth-coverage"
    import hmac as _hmac

    header_b64 = auth_module._b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = {
        "sub": "admin",
        "iat": int(time.time()) - 7200,
        "exp": int(time.time()) - 3600,  # already expired
    }
    payload_b64 = auth_module._b64url_encode(json.dumps(payload).encode())
    msg = f"{header_b64}.{payload_b64}".encode()
    sig_b64 = auth_module._b64url_encode(_hmac.new(secret, msg, "sha256").digest())
    expired = f"{header_b64}.{payload_b64}.{sig_b64}"

    assert get_current_user_role(_credentials(expired)) == "anonymous"


def test_get_current_user_role_admin_sub_returns_admin() -> None:
    """A valid JWT whose ``sub`` matches ``OMNIBOT_ADMIN_USER`` MUST resolve to ``"admin"``.

    The role MUST be ``"admin"`` because the management API feeds the
    return value directly into ``RBACEnforcer.check(role, resource,
    action)`` — and the only matching key in ``ROLE_PERMISSIONS`` is
    ``"admin"`` (NOT ``"system"``; ``"system"`` is a resource name,
    not a role). Returning ``"system"`` here would deny every admin
    request with 403.
    """
    token = _make_jwt("admin")
    assert get_current_user_role(_credentials(token)) == "admin"


def test_get_current_user_role_customer_sub_returns_customer() -> None:
    """A valid JWT whose ``sub`` is anything else MUST resolve to ``"customer"``."""
    token = _make_jwt("alice")
    assert get_current_user_role(_credentials(token)) == "customer"


def test_get_current_user_role_undecodable_payload_returns_anonymous() -> None:
    """A well-formed token with garbage in the payload MUST fall through to ``"anonymous"``."""
    # Build a 3-segment token whose payload isn't valid base64-encoded JSON.
    # The verifier catches the JSON-decode exception and returns "anonymous".
    secret = b"test-jwt-secret-for-auth-coverage"
    import hmac as _hmac

    header_b64 = auth_module._b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload_b64 = auth_module._b64url_encode(b"!!!not-json!!!")
    msg = f"{header_b64}.{payload_b64}".encode()
    sig_b64 = auth_module._b64url_encode(_hmac.new(secret, msg, "sha256").digest())
    bad_token = f"{header_b64}.{payload_b64}.{sig_b64}"

    assert get_current_user_role(_credentials(bad_token)) == "anonymous"


# ===========================================================================
# _login_route — POST /api/v1/auth/login.
# ===========================================================================


def test_login_route_returns_tokens_on_valid_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid admin creds MUST yield a 200 with ``access`` and ``refresh`` keys."""
    monkeypatch.setenv("OMNIBOT_ADMIN_USER", "admin")
    monkeypatch.setenv("OMNIBOT_ADMIN_PASS", "correct")

    app = _build_app_with_login_route()
    client = TestClient(app)

    response = client.post(
        "/auth/login",
        json={"username": "admin", "password": "correct"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "access" in body and isinstance(body["access"], str)
    assert "refresh" in body and isinstance(body["refresh"], str)


def test_login_route_returns_401_on_invalid_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bad creds MUST raise HTTPException(401) — NP-01 active (no enumeration)."""
    monkeypatch.setenv("OMNIBOT_ADMIN_USER", "admin")
    monkeypatch.setenv("OMNIBOT_ADMIN_PASS", "correct")

    app = _build_app_with_login_route()
    client = TestClient(app)

    response = client.post(
        "/auth/login",
        json={"username": "admin", "password": "WRONG"},
    )

    assert response.status_code == 401


def test_login_route_returns_429_when_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the in-process login rate limiter trips 429, the route MUST surface that."""
    from types import SimpleNamespace

    monkeypatch.setenv("OMNIBOT_ADMIN_USER", "admin")
    monkeypatch.setenv("OMNIBOT_ADMIN_PASS", "correct")

    # Patch the module-level rate limiter to always trip the 429 branch.
    # The route only reads ``.allow(platform=..., key=...).status``.
    class _AlwaysTrip:
        def allow(self, **_: object) -> object:
            return SimpleNamespace(status=429)

    monkeypatch.setattr(auth_module, "_login_rate_limiter", _AlwaysTrip())

    app = _build_app_with_login_route()
    client = TestClient(app)

    response = client.post(
        "/auth/login",
        json={"username": "admin", "password": "correct"},
    )

    assert response.status_code == 429
    assert response.json()["detail"] == "Too Many Requests"


def test_login_route_accepts_missing_request_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """``request.client`` MAY be ``None`` — the route MUST fall back to ``127.0.0.1``."""
    monkeypatch.setenv("OMNIBOT_ADMIN_USER", "admin")
    monkeypatch.setenv("OMNIBOT_ADMIN_PASS", "correct")

    # ``TestClient`` always populates ``request.client``; we exercise the
    # fallback by calling the function directly with a hand-rolled
    # request object whose ``client`` is ``None``.
    class _DummyRequest:
        client = None

    body = auth_module.LoginBody(username="admin", password="correct")
    result = _login_route(body=body, request=_DummyRequest())  # type: ignore[arg-type]

    assert isinstance(result, dict)
    assert "access" in result and "refresh" in result


# ===========================================================================
# _assign_role_route — POST /api/v1/users/{user_id}/roles.
# ===========================================================================


def test_assign_role_route_returns_200_for_admin() -> None:
    """An admin caller MUST be able to assign a role and get 200."""
    token = _make_jwt("admin")
    app = _build_app_with_login_route()
    client = TestClient(app)

    # The auth router has prefix ``/auth`` and the role route is mounted
    # at ``/users/{user_id}/roles`` — so the full URL is /auth/users/...
    response = client.post(
        "/auth/users/u-1/roles",
        json={"role": "system:write"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": 200}


def test_assign_role_route_returns_403_for_customer() -> None:
    """A non-admin caller MUST be rejected with 403 (NP-02 active)."""
    token = _make_jwt("alice")
    app = _build_app_with_login_route()
    client = TestClient(app)

    response = client.post(
        "/auth/users/u-1/roles",
        json={"role": "system:write"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_assign_role_route_returns_401_for_missing_auth_header() -> None:
    """A request without an Authorization header MUST yield 401.

    ``HTTPBearer`` (the FastAPI security dep) rejects requests with
    no ``Authorization`` header at the dependency layer, so the
    route's RBAC check never runs and the response is 401 (NOT 403).
    Documenting the actual behaviour here so a future refactor of
    ``HTTPBearer`` → optional doesn't silently change the contract.
    """
    app = _build_app_with_login_route()
    client = TestClient(app)

    response = client.post(
        "/auth/users/u-1/roles",
        json={"role": "system:write"},
    )

    assert response.status_code == 401


def test_assign_role_route_returns_403_for_anonymous_role_via_garbage_token() -> None:
    """A garbage Authorization token resolves to ``"anonymous"`` role.

    ``anonymous`` lacks ``system:write``, so the RBAC check denies
    with 403 — distinct from the 401 above for missing headers.
    """
    app = _build_app_with_login_route()
    client = TestClient(app)

    response = client.post(
        "/auth/users/u-1/roles",
        json={"role": "system:write"},
        headers={"Authorization": "Bearer not-a-valid-token"},
    )

    assert response.status_code == 403
