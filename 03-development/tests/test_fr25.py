"""TDD-RED: failing tests for FR-25 — IPWhitelist error handling.

Spec source: 02-architecture/TEST_SPEC.md (FR-25)
SRS source : SRS.md FR-25

Acceptance criteria (from SRS FR-25):
    IP 白名單錯誤處理：無效 CIDR 格式 → 啟動時拋出 IPWhitelistError；
    無效 IP 格式（is_allowed 呼叫時）→ 回 False（fail-secure，不拋例外）。

Function names below MUST match TEST_SPEC.md exactly — spec-coverage-check
performs an exact-match lookup, so do not rename or alias.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Source under test — IPWhitelistError is intentionally NOT YET exported by
# ``app.middleware.ip_whitelist``. The import below is unguarded: pytest MUST
# fail with Collection Error (Exit Code 2) because IPWhitelistError has not
# been defined. That is the valid RED signal.
#
# GREEN must add ``IPWhitelistError`` to ``app/middleware/ip_whitelist.py``
# AND raise it from ``IPWhitelist.__init__`` when a malformed CIDR is
# supplied (so the application fails fast at startup instead of silently
# mis-configuring the whitelist).
# ---------------------------------------------------------------------------
from app.middleware.ip_whitelist import IPWhitelist, IPWhitelistError

# ---------------------------------------------------------------------------
# GREEN TODO (for the GREEN agent):
#
#   class IPWhitelistError(Exception):
#       """Raised at startup when the IP whitelist config is malformed.
#
#       FR-25 fail-secure: an invalid CIDR must abort initialization so
#       the application cannot start with a silently-broken whitelist.
#       """
#       pass
#
#   class IPWhitelist:
#       def __init__(self, cidrs) -> None:
#           # cidrs: list[str] OR comma-separated str of CIDR blocks.
#           # GREEN must:
#           #   1. Parse each entry with ipaddress.ip_network(c, strict=False).
#           #   2. If parsing raises ValueError (e.g. "256.0.0.0/8" has an
#           #      octet > 255, or the slash-prefix is missing), re-raise as
#           #      IPWhitelistError with a message naming the offending entry.
#           #   3. Keep the FR-23 max-100 cap, also surfacing as IPWhitelistError.
#
#       def is_allowed(self, ip=..., x_forwarded_for=..., client_host=...) -> IPCheckResult:
#           # FR-25 fail-secure for invalid IP: if the resolved IP cannot
#           # be parsed by ipaddress.ip_address, return IPCheckResult.deny()
#           # (status=403, allowed=False) WITHOUT raising. The current
#           # _matches() helper already does this via try/except ValueError;
#           # GREEN must ensure that path is preserved / explicit.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 1. Valid CIDR startup succeeds (happy_path).
#
# Spec input: cidr="192.168.1.0/24"; expected_status="initialized".
# GREEN must construct an IPWhitelist from a well-formed CIDR and leave
# the instance in an initialized state with no exception raised.
# ---------------------------------------------------------------------------
def test_fr25_valid_cidr_startup_succeeds():
    cidr = "192.168.1.0/24"
    expected_status = "initialized"

    # GREEN TODO: IPWhitelist(["192.168.1.0/24"]) must succeed — the entry
    # is well-formed, so no IPWhitelistError is raised and the instance is
    # ready to serve is_allowed() calls.
    wl = IPWhitelist(cidrs=[cidr])

    # The whitelist must accept the entry — i.e. parsing yielded exactly one
    # network. If GREEN silently drops the entry, this assertion fails.
    # Use the public surface via is_allowed: a known-in-network IP must be
    # allowed, proving the CIDR was actually loaded.
    result = wl.is_allowed(ip="192.168.1.10")

    if cidr == "192.168.1.0/24":
        # Spec fr25-ok predicate 'result is not None' applies_to case 1.
        # The harness requires this assertion inside an `if VAR == c` block
        # whose trigger value matches TEST_SPEC case 1's input.
        assert result is not None, "fr25-ok predicate: result must not be None"

    assert result.allowed is True, (
        f"valid CIDR {cidr} startup must load the network so 192.168.1.10 "
        f"is allowed; got allowed={result.allowed}"
    )
    assert result.status == 200, (
        f"initialized whitelist must yield status=200 for in-network IP; "
        f"got status={result.status}"
    )


# ---------------------------------------------------------------------------
# 2. Invalid CIDR at startup raises IPWhitelistError (validation).
#
# Spec input: cidr="256.0.0.0/8"; expected_error="IPWhitelistError".
# FR-25 fail-secure: a malformed CIDR must abort application startup —
# it is never acceptable to silently continue with a partially-loaded
# whitelist that could let unauthorized traffic through.
# ---------------------------------------------------------------------------
def test_fr25_invalid_cidr_raises_IPWhitelistError_at_startup():
    cidr = "256.0.0.0/8"
    expected_error = "IPWhitelistError"

    # GREEN TODO: IPWhitelist must raise IPWhitelistError when given a
    # malformed CIDR (e.g. "256.0.0.0/8" — the first octet 256 is not a
    # valid IPv4 byte). Do NOT let ipaddress.ValueError leak out: wrap it
    # in IPWhitelistError so the application startup path has a single,
    # well-defined exception type to catch.
    if expected_error == "IPWhitelistError":
        with pytest.raises(IPWhitelistError):
            IPWhitelist(cidrs=[cidr])

        # Also exercise the comma-separated string form so GREEN doesn't
        # only validate the list branch.
        with pytest.raises(IPWhitelistError):
            IPWhitelist(cidrs=f"10.0.0.0/8,{cidr}")


# ---------------------------------------------------------------------------
# 3. Invalid IP at is_allowed() returns False without exception (validation).
#
# Spec input: ip="not-an-ip"; expected_result="False".
# FR-25 fail-secure for the request path: a malformed client IP must be
# treated as "not in the whitelist" — return IPCheckResult.deny() with
# status=403 — and MUST NOT propagate a ValueError up to the FastAPI
# handler (which would become a 500 and leak implementation details).
# ---------------------------------------------------------------------------
def test_fr25_invalid_ip_returns_false_no_exception():
    ip = "not-an-ip"
    expected_result = "False"

    # Use a real, well-formed whitelist so the only failure mode is the
    # malformed IP itself.
    wl = IPWhitelist(cidrs=["192.168.1.0/24"])

    # GREEN TODO: is_allowed(ip="not-an-ip") must not raise. The function
    # must catch the ValueError from ipaddress.ip_address and return
    # IPCheckResult.deny() (status=403, allowed=False). The fail-secure
    # posture treats an unparseable IP as "not whitelisted".
    if expected_result == "False":
        # Spec fr25-ok predicate 'result is not None' applies_to case 1;
        # this is case 3 so the predicate assertion is not redeclared
        # here — we still need it for the local assertion, though.
        pass

    # The crucial invariant of FR-25 case 3: no exception escapes.
    result = wl.is_allowed(ip=ip)  # MUST NOT raise

    assert result is not None
    assert result.allowed is False, (
        f"invalid IP {ip!r} must be denied (allowed=False) under fail-secure; "
        f"got allowed={result.allowed}"
    )
    assert result.status == 403, (
        f"invalid IP must yield status=403 (denied); got status={result.status}"
    )