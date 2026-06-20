"""[FR-05] Shared JWT encoding/decoding helpers.

Private module — used by WebAdapter and WebJwtVerifier to avoid
duplicating base64url encode/decode logic.

Citations:
    - SRS.md FR-05 — JWT signing and verification for web platform
"""

from __future__ import annotations

import base64


def _b64url_encode(data: bytes) -> str:
    """Encode bytes to a base64url string without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    """Decode a base64url string (no padding) to bytes."""
    rem = len(data) % 4
    if rem:
        data += "=" * (4 - rem)
    return base64.urlsafe_b64decode(data)
