from __future__ import annotations

import base64 as _base64


def _b64url_encode(data: bytes) -> str:
    """[FR-05] base64url encode WITHOUT padding (JWT spec).

    Citations:
        - RFC 7519 §2 — base64url encoding for JWT segments.
    """
    return _base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

def _b64url_decode(data: str) -> bytes:
    """[FR-05] base64url decode WITH automatic padding restore.

    JWT segments may arrive with or without trailing ``=`` padding;
    we restore to a multiple of 4 so ``urlsafe_b64decode`` does not
    raise ``binascii.Error``.
    """
    padding = "=" * (-len(data) % 4)
    return _base64.urlsafe_b64decode(data + padding)

def _verify_challenge(
    mode: str, token: str, challenge: str, verify_token: str
) -> str | None:
    """[FR-03 / FR-04] Validate GET ``hub.challenge`` parameters.

    Returns ``challenge`` when ``mode == "subscribe"`` AND ``token``
    matches the configured ``verify_token``; returns ``None`` on any
    mismatch so the caller responds with HTTP 403.
    """
    if mode != "subscribe":  # pragma: no cover
        return None
    if token != verify_token:
        return None
    return challenge

