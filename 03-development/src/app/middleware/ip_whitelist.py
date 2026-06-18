"""[FR-23] CIDR-based IP whitelist with X-Forwarded-For support.

Acceptance criteria (SRS FR-23):
    - CIDR format, up to 100 entries, loaded from ``IP_WHITELIST_CIDRS``
      (comma-separated).
    - Read X-Forwarded-For's leftmost IP first; fall back to
      ``request.client.host``; direct ``ip`` argument overrides both.
    - No match → 403 Forbidden with empty body.
    - Empty whitelist or missing IP header → 400 + WARNING log.

Citations:
- SRS.md FR-23 (description line ~62, spec block)
- 02-architecture/TEST_SPEC.md FR-23 (whitelisted_ip_passes,
  nonwhitelisted_ip_403_empty_body, x_forwarded_for_leftmost_used,
  empty_whitelist_400_warning, fallback_to_request_client_host)
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass

logger = logging.getLogger("omnibot.ip_whitelist")


@dataclass(frozen=True)
class IPCheckResult:
    """Outcome of an IP whitelist check.

    Attributes:
        status: HTTP-shaped status — 200 allowed, 403 denied, 400 misconfig.
        body: Response body bytes. Empty for 200/403 per FR-23; non-empty
            for 400 so the caller can surface the reason.
        allowed: True iff the request should proceed.
    """

    status: int
    body: bytes = b""
    allowed: bool = False

    @classmethod
    def allow(cls) -> IPCheckResult:
        """Caller IP matched the whitelist — request may proceed."""
        return cls(status=200, allowed=True)

    @classmethod
    def deny(cls) -> IPCheckResult:
        """Caller IP did not match — FR-23 mandates an empty body for 403."""
        return cls(status=403)

    @classmethod
    def misconfigured(cls, body: bytes) -> IPCheckResult:
        """Caller IP could not be evaluated (empty config / no IP)."""
        return cls(status=400, body=body, allowed=False)


class IPWhitelist:
    """CIDR membership check with X-Forwarded-For resolution.

    Args:
        cidrs: Either a list of CIDR strings (``["10.0.0.0/8"]``) or a
            comma-separated string (``"10.0.0.0/8, 192.168.0.0/16"``).
            Empty input is allowed at construction; the misconfiguration
            surfaces as a 400 in :meth:`is_allowed`.
    """

    _MAX_ENTRIES = 100  # FR-25 cap

    def __init__(self, cidrs) -> None:
        if isinstance(cidrs, str):
            cidrs = [piece.strip() for piece in cidrs.split(",")]
        else:
            cidrs = list(cidrs)

        # Filter empty fragments (e.g. trailing comma in env var) but
        # remember whether the input was effectively empty.
        self._cidrs: list[str] = [c for c in cidrs if c]
        self._networks: list[ipaddress._BaseNetwork] = [
            ipaddress.ip_network(c, strict=False) for c in self._cidrs
        ]

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
    def _resolve_ip(
        x_forwarded_for: str | None,
        ip: str | None,
        client_host: str | None,
    ) -> str | None:
        """Return the caller IP per FR-23 resolution order, or ``None``."""
        if x_forwarded_for:
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
