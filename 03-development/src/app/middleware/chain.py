"""[FR-24] Middleware chain orchestrator.

Acceptance criteria (SRS FR-24):
    攔截鏈順序：TLS → IP Whitelist → Webhook Signature Validation
    → Platform Adapter Parse → Rate Limiting → RBAC

    - 各層按順序執行
    - IP 攔截在 signature 驗證前
    - Rate Limiting 在 Platform Adapter 解析 user_id 後

Citations:
- SRS.md FR-24 (description and spec block)
- 02-architecture/TEST_SPEC.md FR-24 (ip_block_before_signature_validation,
  rate_limit_after_platform_parse, middleware_chain_full_order)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("omnibot.middleware.chain")


@dataclass
class ChainResult:
    """Outcome of running a request through the FR-24 middleware chain.

    Attributes:
        status: HTTP-shaped status (200 / 400 / 401 / 403 / 422 / 429).
        body: Response body bytes.
        reason: Machine-readable short reason, e.g. "IP_BLOCKED",
            "RATE_LIMIT_EXCEEDED", "AUTHZ_INSUFFICIENT_ROLE".
        user_id: Resolved by the platform adapter at the parse stage, or
            ``None`` if the chain short-circuited before parse.
        platform: Resolved by the platform adapter at the parse stage, or
            ``None`` if the chain short-circuited before parse.
        stage_completed: Name of the last stage that finished executing,
            drawn from ``MiddlewareChain.CHAIN_ORDER``.
    """

    status: int
    body: bytes = b""
    reason: str = ""
    user_id: str | None = None
    platform: str | None = None
    stage_completed: str = ""


class MiddlewareChain:
    """Strict-order orchestrator for the FR-24 middleware chain.

    The class attribute ``CHAIN_ORDER`` is the single source of truth for
    execution order; :meth:`process` iterates that tuple so reordering the
    stages is a one-line change with an auditable diff.

    Short-circuit semantics:
        - Any stage that returns a non-success result causes the chain to
          return immediately. Subsequent stages are NOT invoked (this is
          what guarantees IP-deny never reaches the signature validator
          and rate-limit never blocks the parse path).
    """

    # Hard-coded execution order per SRS FR-24. Tests assert on this
    # tuple directly via ``MiddlewareChain.CHAIN_ORDER``; do not rename
    # or reorder without updating SRS FR-24.
    CHAIN_ORDER = ("tls", "ip", "signature", "parse", "rate", "rbac")

    def __init__(
        self,
        *,
        ip_whitelist,
        signature_validator,
        platform_adapter,
        rate_limiter,
        rbac_enforcer,
        tls_check=None,
    ) -> None:
        self.tls_check = tls_check
        self.ip_whitelist = ip_whitelist
        self.signature_validator = signature_validator
        self.platform_adapter = platform_adapter
        self.rate_limiter = rate_limiter
        self.rbac_enforcer = rbac_enforcer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def process(self, request) -> ChainResult:
        """Run ``request`` through every stage in ``CHAIN_ORDER``.

        Returns a :class:`ChainResult` reflecting the first non-success
        stage, or a 200 result if every stage passes.
        """
        # 1. TLS termination check (optional pass-through when None).
        if self.tls_check is not None:
            tls_outcome = self.tls_check(request)
            if not getattr(tls_outcome, "allowed", True):
                return ChainResult(
                    status=getattr(tls_outcome, "status", 400),
                    body=getattr(tls_outcome, "body", b""),
                    reason="TLS_CHECK_FAILED",
                    stage_completed="tls",
                )

        # 2. IP Whitelist — FR-24 mandates this BEFORE signature validation.
        ip_outcome = self.ip_whitelist.is_allowed(request)
        if not getattr(ip_outcome, "allowed", False):
            return ChainResult(
                status=ip_outcome.status,
                body=ip_outcome.body,
                reason="IP_BLOCKED",
                stage_completed="ip",
            )

        # 3. Webhook Signature Validation.
        if not self.signature_validator.verify(request):
            return ChainResult(
                status=401,
                reason="SIGNATURE_INVALID",
                stage_completed="signature",
            )

        # 4. Platform Adapter Parse — produces the user_id used as the
        # rate-limiter key in the next stage.
        ctx = self.platform_adapter.parse(request)

        # 5. Rate Limiting — keyed by the parsed user_id, not the raw IP.
        rate_outcome = self.rate_limiter.allow(
            platform=ctx.platform,
            key=ctx.user_id,
        )
        if getattr(rate_outcome, "status", 200) == 429:
            return ChainResult(
                status=429,
                reason="RATE_LIMIT_EXCEEDED",
                user_id=ctx.user_id,
                platform=ctx.platform,
                stage_completed="rate",
            )

        # 6. RBAC — final authorization gate.
        rbac_outcome = self.rbac_enforcer.enforce(
            ctx.user_id, "webhook", "receive"
        )
        if not getattr(rbac_outcome, "allowed", False):
            return ChainResult(
                status=403,
                reason="AUTHZ_INSUFFICIENT_ROLE",
                user_id=ctx.user_id,
                platform=ctx.platform,
                stage_completed="rbac",
            )

        return ChainResult(
            status=200,
            user_id=ctx.user_id,
            platform=ctx.platform,
            stage_completed="rbac",
        )
