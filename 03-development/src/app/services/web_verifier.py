"""[FR-05] Web JWT Bearer Token Verifier.

Validates JWT Bearer tokens for the Web Platform Adapter using HMAC-SHA256
(HS256). Returns bool — never raises, so the caller (WebAdapter) controls
the HTTP error mapping.

Citations:
    - SRS.md FR-05 — "JWT BearerAuth 傳訊; JWT 驗證失敗回 401"
    - TEST_SPEC.md FR-05:96-100 — WebJwtVerifier contract:
      __init__(self, jwt_secret: str), verify(self, token: str) -> bool
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from app.services._jwt_utils import _b64url_decode


class WebJwtVerifier:
    """[FR-05] Validates JWT Bearer tokens signed with HS256.

    Citations:
        - SRS.md FR-05 — JWT verification for web platform
        - TEST_SPEC.md FR-05:96-100 — contract: verify() -> bool, never raises
    """

    def __init__(self, jwt_secret: str = "", secret: str = "") -> None:
        """Initialise with the shared JWT signing secret.

        Citations:
            - TEST_SPEC.md FR-05:97 — __init__(self, jwt_secret: str)
        """
        self._jwt_secret = jwt_secret or secret

    def verify(self, token: str) -> bool:
        """Verify JWT signature and expiration.  Returns True iff valid.

        Returns False on any failure: malformed token, bad signature,
        expired, or missing claims.  Never raises.

        Citations:
            - TEST_SPEC.md FR-05:99-100 — verify contract
            - SRS.md FR-05 — "JWT 驗證失敗回 401 AUTH_TOKEN_EXPIRED"
        """
        try:
            segments = token.split(".")
            if len(segments) != 3:
                return False

            header_b64, payload_b64, sig_b64 = segments

            # Verify alg header
            header_bytes = _b64url_decode(header_b64)
            header = json.loads(header_bytes)
            if header.get("alg") != "HS256":
                return False

            # Verify HMAC-SHA256 signature
            signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
            expected_sig = hmac.new(
                self._jwt_secret.encode("utf-8"),
                signing_input,
                hashlib.sha256,
            ).digest()
            actual_sig = _b64url_decode(sig_b64)
            if not hmac.compare_digest(expected_sig, actual_sig):
                return False

            # Decode payload and check expiration
            payload_bytes = _b64url_decode(payload_b64)
            payload = json.loads(payload_bytes)
            exp = payload.get("exp", 0)
            return time.time() <= exp
        except Exception:
            return False

    def create_guest_session(self) -> dict:
        """[FR-108] Create a guest session returning a JWT token.

        Returns a dict with a ``"jwt"`` key containing a non-trivial
        JWT string for anonymous/guest web users.

        Citations:
            - 03-development/tests/test_fr108.py:1012-1018 — contract
        """
        import base64

        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            json.dumps({
                "sub": "guest",
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
            }).encode()
        ).rstrip(b"=").decode()
        sig = base64.urlsafe_b64encode(
            hmac.new(
                (self._jwt_secret or "default").encode(),
                f"{header}.{payload}".encode(),
                hashlib.sha256,
            ).digest()
        ).rstrip(b"=").decode()
        return {"jwt": f"{header}.{payload}.{sig}"}
