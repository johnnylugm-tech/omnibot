"""TDD-RED: failing tests for FR-23 — IP Whitelist (CIDR + X-Forwarded-For).

Spec source: 02-architecture/TEST_SPEC.md (FR-23)
SRS source : SRS.md FR-23

Acceptance criteria (from SRS FR-23):
    IP 白名單：CIDR 格式（最多 100 個），從 ``IP_WHITELIST_CIDRS`` 環境變數
    載入（逗號分隔）；優先讀取 X-Forwarded-For 最左側 IP，
    fallback request.client.host；無匹配 → 403 Forbidden（空 body）；
    白名單空或無 IP header 回 400 + warning log。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import logging

import pytest

# ---------------------------------------------------------------------------
# Source under test — does NOT exist yet. The import below is intentionally
# unguarded: pytest MUST fail with Collection Error (Exit Code 2) on this
# line because ``app.middleware.ip_whitelist`` has not been implemented.
# That is the valid RED signal.
#
# GREEN must create ``app/middleware/ip_whitelist.py`` exposing the
# ``IPWhitelist`` class and ``IPCheckResult`` dataclass with the shape
# dictated by the test inputs below.
# ---------------------------------------------------------------------------
from app.middleware.ip_whitelist import IPWhitelist  # noqa: F401  -- RED expected


# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   class IPWhitelist:
#       def __init__(self, cidrs):
#           # cidrs: list[str] OR comma-separated str of CIDR blocks
#           # GREEN must reject >100 entries with IPWhitelistError (FR-25).
#           # GREEN must reject malformed CIDR with IPWhitelistError (FR-25).
#
#       def is_allowed(
#           self,
#           ip: str | None = None,
#           x_forwarded_for: str | None = None,
#           client_host: str | None = None,
#       ) -> IPCheckResult:
#           # Resolution order:
#           #   1. If x_forwarded_for is set → use the LEFTMOST IP
#           #      (split on comma, strip whitespace, take [0]).
#           #   2. Else if ip is set → use ip.
#           #   3. Else if client_host is set → use client_host.
#           #   4. Else → IPCheckResult(status=400, body=b"...", allowed=False)
#           #      AND emit WARNING log "ip_whitelist_missing_ip_header".
#           #
#           # Empty whitelist handling (ip_whitelist_cidrs == "" or []):
#           #   - return IPCheckResult(status=400, body=b"...",
#           #     allowed=False) AND emit WARNING log
#           #     "ip_whitelist_empty_config".
#           #
#           # Membership check (use Python stdlib ``ipaddress``):
#           #   - if resolved_ip ∈ any parsed CIDR network → allowed
#           #     → IPCheckResult(status=200, body=b"", allowed=True)
#           #   - else → IPCheckResult(status=403, body=b"", allowed=False)
#
#   @dataclass(frozen=True)
#   class IPCheckResult:
#       status: int       # 200, 400, 403
#       body: bytes = b""
#       allowed: bool = False
# ---------------------------------------------------------------------------


def _make_ip(cidr: str):
    """Build an IPWhitelist from a single CIDR (helper for the happy path)."""
    return IPWhitelist(cidrs=[cidr])


# ---------------------------------------------------------------------------
# 1. Whitelisted IP passes (happy_path).
# ---------------------------------------------------------------------------
def test_fr23_whitelisted_ip_passes():
    ip = "192.168.1.10"
    cidr = "192.168.1.0/24"

    wl = _make_ip(cidr)

    # GREEN TODO: is_allowed(ip="192.168.1.10") must resolve the IP, check
    # membership in 192.168.1.0/24, and return IPCheckResult(200, b"",
    # allowed=True).
    result = wl.is_allowed(ip=ip)

    # Spec fr23-ok predicate 'result is not None' applies_to case 1.
    assert result is not None, "fr23-ok predicate: result must not be None"
    assert result.allowed is True, (
        f"IP {ip} in CIDR {cidr} must be allowed; got allowed={result.allowed}"
    )
    assert result.status == 200, (
        f"whitelisted IP must yield status=200; got {result.status}"
    )


# ---------------------------------------------------------------------------
# 2. Non-whitelisted IP → 403 with empty body (validation).
# ---------------------------------------------------------------------------
def test_fr23_nonwhitelisted_ip_403_empty_body():
    ip = "10.0.0.1"
    cidr = "192.168.1.0/24"

    wl = _make_ip(cidr)

    # GREEN TODO: is_allowed(ip="10.0.0.1") must reject because 10.0.0.1
    # is NOT in 192.168.1.0/24, returning status=403 with an empty body
    # (the spec mandates an empty body for the 403 case so attackers get
    # no information about why the request was blocked).
    result = wl.is_allowed(ip=ip)

    # Spec fr23-ok applies_to case 1; this is case 2 so the predicate
    # assertion is not redeclared here.
    assert result is not None
    assert result.allowed is False, (
        f"IP {ip} not in CIDR {cidr} must be denied; got allowed={result.allowed}"
    )
    assert result.status == 403, (
        f"non-whitelisted IP must yield status=403; got {result.status}"
    )
    assert result.body == b"", (
        f"FR-23 mandates an empty body for 403; got body={result.body!r}"
    )


# ---------------------------------------------------------------------------
# 3. X-Forwarded-For — LEFTMOST IP is used (happy_path).
#
# Setup: leftmost (1.2.3.4) IS in whitelist; rightmost (5.6.7.8) is NOT.
# If GREEN naively used the rightmost or the entire chain as one IP, the
# membership check would fail and we would see 403.
# ---------------------------------------------------------------------------
def test_fr23_x_forwarded_for_leftmost_used():
    x_forwarded_for = "1.2.3.4, 5.6.7.8"
    expected_ip = "1.2.3.4"

    # Whitelist covers only 1.2.3.0/24 — leftmost IP is in, rightmost is out.
    wl = IPWhitelist(cidrs=["1.2.3.0/24"])

    # GREEN TODO: is_allowed(x_forwarded_for=...) must split the header on
    # commas, strip whitespace, and check membership of the FIRST element
    # (1.2.3.4) — not the last element (5.6.7.8) and not the entire string.
    result = wl.is_allowed(x_forwarded_for=x_forwarded_for)

    # Spec fr23-ok applies_to case 1; this is case 3 so the predicate
    # assertion is not redeclared here.
    assert result is not None
    assert result.allowed is True, (
        f"leftmost X-Forwarded-For IP {expected_ip} must be allowed "
        f"(whitelist=1.2.3.0/24); got allowed={result.allowed}"
    )
    assert result.status == 200, (
        f"leftmost X-Forwarded-For IP must yield status=200; got {result.status}"
    )


# ---------------------------------------------------------------------------
# 4. Empty whitelist (boundary) → 400 + warning log.
#
# The spec says: "白名單空或無 IP header 回 400 + warning log".
# We exercise the empty-whitelist branch with a non-empty IP so the
# 400 comes from the config, not from a missing IP header.
# ---------------------------------------------------------------------------
def test_fr23_empty_whitelist_400_warning(caplog):
    ip_whitelist_cidrs = ""

    # GREEN TODO: IPWhitelist must accept an empty string for ``cidrs``
    # (NOT raise at init — the 400 path is per-request). When ``is_allowed``
    # is called and the configured whitelist is empty, return
    # IPCheckResult(status=400, body=b"...", allowed=False) and emit
    # a WARNING log entry on logger ``omnibot.ip_whitelist``.
    wl = IPWhitelist(cidrs=ip_whitelist_cidrs)

    with caplog.at_level(logging.WARNING, logger="omnibot.ip_whitelist"):
        result = wl.is_allowed(ip="8.8.8.8")

    # Spec fr23-ok applies_to case 1; this is case 4 so the predicate
    # assertion is not redeclared here.
    assert result is not None
    assert result.status == 400, (
        f"empty whitelist must yield status=400; got {result.status}"
    )

    # Empty whitelist is a misconfiguration — must surface as a WARNING.
    warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert warning_records, (
        "FR-23 requires a WARNING log entry when the whitelist is empty; "
        "no WARNING-level record was emitted"
    )


# ---------------------------------------------------------------------------
# 5. Fallback to request.client.host when X-Forwarded-For is empty
#    (happy_path).
# ---------------------------------------------------------------------------
def test_fr23_fallback_to_request_client_host():
    x_forwarded_for = ""
    client_host = "192.168.1.10"

    # Whitelist covers 192.168.1.0/24 — client_host 192.168.1.10 is in.
    wl = _make_ip("192.168.1.0/24")

    # GREEN TODO: when x_forwarded_for is an empty string (or not provided),
    # is_allowed must fall back to client_host and use it for the
    # membership check. Returning allowed=True here proves the fallback
    # path was actually taken (not the X-Forwarded-For branch).
    result = wl.is_allowed(x_forwarded_for=x_forwarded_for, client_host=client_host)

    # Spec fr23-ok applies_to case 1; this is case 5 so the predicate
    # assertion is not redeclared here.
    assert result is not None
    assert result.allowed is True, (
        f"client_host {client_host} must be allowed via fallback "
        f"(whitelist=192.168.1.0/24); got allowed={result.allowed}"
    )
    assert result.status == 200, (
        f"client_host fallback must yield status=200; got {result.status}"
    )
