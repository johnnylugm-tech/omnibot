"""[FR-23][FR-25] CIDR-based IP whitelist with X-Forwarded-For support
and fail-secure error handling.

Acceptance criteria (SRS FR-23):
    - CIDR format, up to 100 entries, loaded from ``IP_WHITELIST_CIDRS``
      (comma-separated).
    - Read X-Forwarded-For's leftmost IP first; fall back to
      ``request.client.host``; direct ``ip`` argument overrides both.
    - No match → 403 Forbidden with empty body.
    - Empty whitelist or missing IP header → 400 + WARNING log.

Acceptance criteria (SRS FR-25):
    - Invalid CIDR at startup → raise ``IPWhitelistError`` so the app
      fails fast instead of silently loading a broken whitelist.
    - Invalid IP in :meth:`IPWhitelist.is_allowed` → return False (deny)
      without raising; the request must not surface a 500 to the caller.

Citations:
- SRS.md FR-23 (description line ~62, spec block)
- 02-architecture/TEST_SPEC.md FR-23 (whitelisted_ip_passes,
  nonwhitelisted_ip_403_empty_body, x_forwarded_for_leftmost_used,
  empty_whitelist_400_warning, fallback_to_request_client_host)
- SRS.md FR-25 (description line ~63, spec block)
- 02-architecture/TEST_SPEC.md FR-25
  (test_fr25_valid_cidr_startup_succeeds,
   test_fr25_invalid_cidr_raises_IPWhitelistError_at_startup,
   test_fr25_invalid_ip_returns_false_no_exception)
"""

from __future__ import annotations

import ipaddress
import logging
from collections.abc import Iterable
from dataclasses import dataclass

logger = logging.getLogger("omnibot.ip_whitelist")


class IPWhitelistError(Exception):
    """Raised at startup when the IP whitelist config is malformed.

    [FR-25] fail-secure: an invalid CIDR must abort initialization so the
    application cannot start with a silently-broken whitelist that might
    let unauthorized traffic through.
    """


@dataclass(frozen=True)
class IPCheckResult:
    """Outcome of an IP whitelist check.

    Attributes:
        status_code: HTTP-shaped status — 200 allowed, 403 denied, 400 misconfig.
        body: Response body bytes. Empty for 200/403 per FR-23; non-empty
            for 400 so the caller can surface the reason.
        allowed: True iff the request should proceed.
    """

    status_code: int
    body: bytes = b""
    allowed: bool = False

    @property
    def status(self) -> int:
        """Backward-compat alias for ``status_code``."""
        return self.status_code

    @classmethod
    def allow(cls) -> IPCheckResult:
        """Caller IP matched the whitelist — request may proceed."""
        return cls(status_code=200, allowed=True)

    @classmethod
    def deny(cls) -> IPCheckResult:
        """Caller IP did not match — FR-23 mandates an empty body for 403."""
        return cls(status_code=403)

    @classmethod
    def misconfigured(cls, body: bytes) -> IPCheckResult:
        """Caller IP could not be evaluated (empty config / no IP)."""
        return cls(status_code=400, body=body, allowed=False)


class IPWhitelist:
    """CIDR membership check with X-Forwarded-For resolution.

    Args:
        cidrs: Either a list of CIDR strings (``["10.0.0.0/8"]``) or a
            comma-separated string (``"10.0.0.0/8, 192.168.0.0/16"``).
            Empty input is allowed at construction; the misconfiguration
            surfaces as a 400 in :meth:`is_allowed`.
    """

    _MAX_ENTRIES = 100  # FR-25 cap

    def __init__(self, cidrs: str | Iterable[str]) -> None:
        # Normalize: accept either a comma-separated string or any iterable.
        # Strip whitespace and drop empty fragments (e.g. trailing comma in
        # an env var) so downstream validation sees only meaningful entries.
        self._cidrs: list[str] = self._normalize_cidrs(cidrs)

        # [FR-25] Cap the number of configured CIDR blocks. Exceeding the
        # cap is a startup-time configuration error, surfaced as
        # IPWhitelistError so the application refuses to come up rather
        # than silently accepting an unbounded config.
        if len(self._cidrs) > self._MAX_ENTRIES:
            raise IPWhitelistError(
                f"ip_whitelist_too_many_entries: got {len(self._cidrs)} "
                f"cidrs, max is {self._MAX_ENTRIES}"
            )

        # [FR-25] Parse each CIDR entry. A malformed entry (e.g.
        # "256.0.0.0/8" — octet > 255, or a missing slash) raises
        # ValueError from ipaddress.ip_network. Re-raise as
        # IPWhitelistError so the startup path has a single, well-defined
        # exception type to catch and the application fails fast.
        self._networks = self._parse_networks(self._cidrs)

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_cidrs(cidrs: str | Iterable[str]) -> list[str]:
        """Return the non-empty CIDR strings from the input.

        Accepts either a comma-separated string (``"10.0.0.0/8, 192.168/16"``)
        or any iterable of CIDR strings. String entries are stripped;
        iterable entries are passed through (the caller is responsible for
        whitespace). Empty fragments are dropped.
        """
        if isinstance(cidrs, str):
            return [piece.strip() for piece in cidrs.split(",") if piece.strip()]
        return [c for c in cidrs if c]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def is_allowed(
        self,
        ip: str | None = None,
        x_forwarded_for: str | None = None,
        client_host: str | None = None,
    ) -> IPCheckResult:
        """Resolve the caller IP and check membership in the whitelist.

        Resolution order:
            1. ``x_forwarded_for`` (leftmost, comma-separated)
            2. ``ip``
            3. ``client_host``
        """
        if not self._networks:
            logger.warning(
                "ip_whitelist_empty_config",
                extra={"cidrs": self._cidrs},
            )
            return IPCheckResult.misconfigured(b"ip whitelist is empty")

        resolved = self._resolve_ip(x_forwarded_for, ip, client_host)
        if resolved is None:
            logger.warning(
                "ip_whitelist_missing_ip_header",
                extra={
                    "x_forwarded_for": x_forwarded_for,
                    "ip": ip,
                    "client_host": client_host,
                },
            )
            return IPCheckResult.misconfigured(b"no client ip available")

        return (
            IPCheckResult.allow()
            if self._matches(resolved)
            else IPCheckResult.deny()
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_networks(
        cidrs: list[str],
    ) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        """Parse each CIDR into a network, surfacing malformed entries as ``IPWhitelistError``."""
        networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for cidr in cidrs:
            try:
                networks.append(ipaddress.ip_network(cidr, strict=False))
            except ValueError as exc:
                raise IPWhitelistError(
                    f"ip_whitelist_invalid_cidr: {cidr!r} ({exc})"
                ) from exc
        return networks

    @staticmethod
    def _resolve_ip(
        x_forwarded_for: str | None,
        ip: str | None,
        client_host: str | None,
    ) -> str | None:
        """Return the caller IP per FR-23 resolution order, or ``None``."""
        tcp_client = ip if ip else client_host
        is_trusted = False
        if tcp_client:
            try:
                addr = ipaddress.ip_address(tcp_client.strip())
                is_trusted = addr.is_private or addr.is_loopback
            except ValueError:
                pass

        if x_forwarded_for and is_trusted:
            leftmost = x_forwarded_for.split(",", 1)[0].strip()
            if leftmost:
                return leftmost
        if ip:
            return ip.strip()
        if client_host:
            return client_host.strip()
        return None

    def _matches(self, ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(addr in net for net in self._networks)
